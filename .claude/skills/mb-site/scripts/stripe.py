#!/usr/bin/env python3
"""stripe.py — Stripe payment-link automation atom.

Subcommands:
    create-payment-link <offer-slug>
        Idempotent: ensures a Stripe product + price + payment link exist
        for the given offer slug. Returns the payment-link URL the
        minisite hero CTA links to.

    list-products
        Lists active products with `mb_offer` metadata. Debug helper.

    archive-product <product-id>
        Marks a product inactive (Stripe doesn't support hard delete).

Invocation: `python3 stripe.py <subcommand> [args]`
Output: companyctx-shape envelope JSON on stdout, logs on stderr.
Exit code: 0 on ok|partial, 1 on degraded.

Idempotency model (per `noontide-co/noontide-ops`
decisions/2026-04-27-credential-provisioning.md):

  1. Search products by metadata `mb_offer:<slug>` AND `mb_kind:deposit`.
     If found AND product has stashed `mb_payment_link_url` in metadata
     → return that URL.
  2. If not found, create product (with `default_price_data`) and payment
     link. Stash the payment-link URL in product metadata for future
     idempotency lookups. Use Stripe Idempotency-Key headers on every
     create call to survive transient retries within the search-API's
     eventual-consistency window (~minutes-to-hours).

Spec: see `references/minisite.md` ("Stripe payment-link
defaults" table) for the canonical defaults this atom encodes.

Test mode vs live mode: the atom is mode-agnostic — it uses whatever key
is in `STRIPE_API_KEY`. Test keys start `sk_test_`, live keys `sk_live_`.
Use test mode while iterating; live mode for real offers.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Literal

import click
import requests
from pydantic import BaseModel, ConfigDict, Field, model_validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _envelope import (  # noqa: E402
    SCHEMA_VERSION,
    EnvelopeStatus,
    ProviderRunMetadata,
    emit,
    log,
    validate_status_consistency,
)

STRIPE_API_BASE = "https://api.stripe.com/v1"

# Stripe limits.
STATEMENT_DESCRIPTOR_MAX = 22
STATEMENT_DESCRIPTOR_RE = re.compile(r"^[A-Za-z0-9 .\-]{5,22}$")
# Stripe's documented minimum charge is $0.50 USD (50 cents).
MIN_AMOUNT_CENTS = 50

DEFAULT_STATEMENT_DESCRIPTOR = "NOONTIDE"

# Main Branch metadata keys per minisite spec. The `mb_` prefix namespaces
# our products from anything else in the operator's Stripe account.
META_OFFER = "mb_offer"
META_KIND = "mb_kind"
META_KIND_VALUE = "deposit"
META_PAYMENT_LINK_URL = "mb_payment_link_url"
META_CREATED_AT = "mb_created_at"

# ---------------------------------------------------------------------------
# Envelope shape
# ---------------------------------------------------------------------------

StripeErrorCode = Literal[
    "stripe_unauthenticated",
    "stripe_rate_limited",
    "network_timeout",
    "invalid_amount",
    "invalid_currency",
    "invalid_offer_slug",
    "invalid_statement_descriptor",
    "invalid_success_url",
    "missing_api_key",
    "account_not_configured",
    "stripe_request_failed",
    "product_not_found",
]


class StripeError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: StripeErrorCode
    message: str
    suggestion: str | None = None


class CreatePaymentLinkData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offer_slug: str
    payment_link_url: str | None = None
    payment_link_id: str | None = None
    product_id: str | None = None
    price_id: str | None = None
    amount_cents: int | None = None
    currency: str | None = None
    statement_descriptor: str | None = None
    success_url: str | None = None
    created_now: bool = False
    """True if this run created the product. False = returned existing (idempotent)."""


class ListProductsData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    products: list[dict] = Field(default_factory=list)
    count: int = 0


class ArchiveProductData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str
    archived: bool = False


class CreatePaymentLinkEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    status: EnvelopeStatus
    data: CreatePaymentLinkData
    provenance: dict[str, ProviderRunMetadata] = Field(default_factory=dict)
    error: StripeError | None = None

    @model_validator(mode="after")
    def _v(self) -> CreatePaymentLinkEnvelope:
        return validate_status_consistency(self)  # type: ignore[return-value]


class ListProductsEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    status: EnvelopeStatus
    data: ListProductsData
    provenance: dict[str, ProviderRunMetadata] = Field(default_factory=dict)
    error: StripeError | None = None

    @model_validator(mode="after")
    def _v(self) -> ListProductsEnvelope:
        return validate_status_consistency(self)  # type: ignore[return-value]


class ArchiveProductEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    status: EnvelopeStatus
    data: ArchiveProductData
    provenance: dict[str, ProviderRunMetadata] = Field(default_factory=dict)
    error: StripeError | None = None

    @model_validator(mode="after")
    def _v(self) -> ArchiveProductEnvelope:
        return validate_status_consistency(self)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Stripe HTTP helpers
# ---------------------------------------------------------------------------


class StripeResult(BaseModel):
    """Internal: a Stripe API response normalized for atom consumption."""

    model_config = ConfigDict(extra="forbid")
    ok: bool
    latency_ms: int
    status_code: int
    payload: dict | None = None
    error_type: str | None = None  # Stripe's `error.type`
    error_code: str | None = None  # Stripe's `error.code`
    error_message: str | None = None


def _form_encode(data: dict, prefix: str = "") -> list[tuple[str, str]]:
    """Stripe's API uses application/x-www-form-urlencoded with bracket nesting.

    Examples:
      {"line_items": [{"price": "p_1"}]}
        → [("line_items[0][price]", "p_1")]
      {"metadata": {"mb_offer": "x"}}
        → [("metadata[mb_offer]", "x")]
      {"default_price_data": {"unit_amount": 10000, "currency": "usd"}}
        → [("default_price_data[unit_amount]", "10000"),
           ("default_price_data[currency]", "usd")]
    """
    out: list[tuple[str, str]] = []
    for k, v in data.items():
        key = f"{prefix}[{k}]" if prefix else k
        if isinstance(v, dict):
            out.extend(_form_encode(v, key))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    out.extend(_form_encode(item, f"{key}[{i}]"))
                else:
                    out.append((f"{key}[{i}]", str(item)))
        elif isinstance(v, bool):
            out.append((key, "true" if v else "false"))
        elif v is None:
            continue
        else:
            out.append((key, str(v)))
    return out


def _stripe_call(
    method: str,
    path: str,
    api_key: str,
    body: dict | None = None,
    idempotency_key: str | None = None,
    query: dict | None = None,
) -> StripeResult:
    url = f"{STRIPE_API_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Stripe-Version": "2024-06-20",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    form_data = _form_encode(body) if body else None
    start = time.monotonic()
    try:
        resp = requests.request(
            method,
            url,
            headers=headers,
            data=form_data,
            params=query,
            timeout=30,
        )
    except requests.Timeout:
        return StripeResult(
            ok=False,
            latency_ms=int((time.monotonic() - start) * 1000),
            status_code=0,
            error_message="timeout",
        )
    except requests.RequestException as exc:
        return StripeResult(
            ok=False,
            latency_ms=int((time.monotonic() - start) * 1000),
            status_code=0,
            error_message=f"request_exception: {exc.__class__.__name__}",
        )

    latency_ms = int((time.monotonic() - start) * 1000)
    try:
        payload = resp.json()
    except ValueError:
        return StripeResult(
            ok=False,
            latency_ms=latency_ms,
            status_code=resp.status_code,
            error_message="non_json_response",
        )

    if resp.ok:
        return StripeResult(
            ok=True,
            latency_ms=latency_ms,
            status_code=resp.status_code,
            payload=payload,
        )

    err = payload.get("error") or {}
    return StripeResult(
        ok=False,
        latency_ms=latency_ms,
        status_code=resp.status_code,
        payload=payload,
        error_type=err.get("type"),
        error_code=err.get("code"),
        error_message=err.get("message"),
    )


def _classify_error(result: StripeResult) -> tuple[StripeErrorCode, str]:
    """Map a failed Stripe response to a closed-enum error code + suggestion."""
    if result.error_message == "timeout":
        return "network_timeout", "Stripe API timed out. Retry; check connectivity."
    if result.status_code == 401 or result.error_type == "invalid_request_error" and (
        result.error_code in ("api_key_expired", "api_key_invalid")
    ):
        return (
            "stripe_unauthenticated",
            "Verify STRIPE_API_KEY is correct (sk_test_... or sk_live_...) and not revoked. "
            "Manage at https://dashboard.stripe.com/apikeys.",
        )
    if result.status_code == 401:
        return (
            "stripe_unauthenticated",
            "Stripe rejected the API key. Confirm STRIPE_API_KEY is set and current.",
        )
    if result.status_code == 429:
        return "stripe_rate_limited", "Stripe rate-limited the request. Back off and retry."
    if result.status_code == 404:
        return (
            "product_not_found",
            "The referenced product does not exist or was archived.",
        )
    # account_not_configured: 400-class with messages about missing Stripe account setup.
    if result.status_code == 400 and result.error_message and (
        "account" in result.error_message.lower()
        and ("complete" in result.error_message.lower() or "activate" in result.error_message.lower())
    ):
        return (
            "account_not_configured",
            "Complete Stripe account setup (business profile, bank account) at "
            "https://dashboard.stripe.com/settings/account.",
        )
    return (
        "stripe_request_failed",
        f"Stripe rejected the request: {result.error_message or 'unknown'} "
        f"(http {result.status_code}, type {result.error_type}, code {result.error_code}).",
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

# Lowercased slug: alphanumeric + hyphen + underscore. Matches typical offer
# directory naming under core/offers/<slug>/.
OFFER_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


def _validate_offer_slug(slug: str) -> str | None:
    if not OFFER_SLUG_RE.match(slug):
        return (
            f"Offer slug {slug!r} is invalid. Use lowercase letters, digits, "
            "hyphens, or underscores; start with alphanumeric; max 63 chars."
        )
    return None


def _validate_statement_descriptor(descriptor: str) -> str | None:
    if not STATEMENT_DESCRIPTOR_RE.match(descriptor):
        return (
            f"Statement descriptor {descriptor!r} is invalid. "
            "Stripe requires 5–22 chars, ASCII letters/digits/spaces/dots/hyphens, "
            "no special characters."
        )
    return None


def _truncate_descriptor(value: str) -> str:
    """Trim whitespace and truncate to Stripe's 22-char limit."""
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned[:STATEMENT_DESCRIPTOR_MAX]


# ---------------------------------------------------------------------------
# Search + create flow
# ---------------------------------------------------------------------------


def _search_existing_product(
    api_key: str, offer_slug: str, provenance: dict[str, ProviderRunMetadata]
) -> tuple[dict | None, StripeResult | None]:
    """Search for an existing product matching this offer.

    Returns (product_dict, result). If product_dict is None and result.ok is
    True, no match was found (clean run, just empty). If result.ok is False,
    the API call itself failed.
    """
    query = (
        f'metadata[\'{META_OFFER}\']:\'{offer_slug}\' '
        f'AND metadata[\'{META_KIND}\']:\'{META_KIND_VALUE}\' '
        f"AND active:'true'"
    )
    result = _stripe_call(
        "GET",
        "/products/search",
        api_key,
        query={"query": query, "limit": 1},
    )
    provenance["stripe_products_search"] = ProviderRunMetadata(
        status="ok" if result.ok else "failed",
        latency_ms=result.latency_ms,
        error=result.error_message,
        provider_version="stripe-2024-06-20",
    )
    if not result.ok:
        return None, result
    data = (result.payload or {}).get("data") or []
    if not data:
        return None, result
    return data[0], result


def _update_product_metadata(
    api_key: str,
    product_id: str,
    metadata_updates: dict[str, str],
    provenance: dict[str, ProviderRunMetadata],
) -> StripeResult:
    body = {"metadata": metadata_updates}
    result = _stripe_call("POST", f"/products/{product_id}", api_key, body=body)
    provenance["stripe_product_update"] = ProviderRunMetadata(
        status="ok" if result.ok else "failed",
        latency_ms=result.latency_ms,
        error=result.error_message,
        provider_version="stripe-2024-06-20",
    )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """stripe.py — Stripe payment-link automation atom."""


@cli.command("create-payment-link")
@click.argument("offer_slug")
@click.option("--amount", "amount_cents", type=int, required=True, help="Deposit amount in US cents (e.g., 10000 for $100).")
@click.option("--currency", default="usd", show_default=True, help="ISO currency code (V1: USD only).")
@click.option("--description", default=None, help="Product description shown to customers.")
@click.option(
    "--statement-descriptor",
    default=None,
    help=f"Card statement descriptor (max {STATEMENT_DESCRIPTOR_MAX} chars). Defaults to {DEFAULT_STATEMENT_DESCRIPTOR!r}.",
)
@click.option(
    "--success-url",
    required=True,
    help="URL Stripe redirects to after successful payment. Must be HTTPS.",
)
@click.option(
    "--product-name",
    default=None,
    help="Product name shown in Stripe dashboard. Defaults to the offer slug.",
)
def create_payment_link(
    offer_slug: str,
    amount_cents: int,
    currency: str,
    description: str | None,
    statement_descriptor: str | None,
    success_url: str,
    product_name: str | None,
) -> None:
    """Ensure a Stripe payment link exists for OFFER_SLUG, returning the URL."""
    provenance: dict[str, ProviderRunMetadata] = {}

    # --- Input validation ---
    slug_err = _validate_offer_slug(offer_slug)
    if slug_err:
        env = CreatePaymentLinkEnvelope(
            status="degraded",
            data=CreatePaymentLinkData(offer_slug=offer_slug),
            error=StripeError(
                code="invalid_offer_slug",
                message=slug_err,
                suggestion="Use the offer's directory name from core/offers/.",
            ),
        )
        sys.exit(emit(env))

    if amount_cents < MIN_AMOUNT_CENTS:
        env = CreatePaymentLinkEnvelope(
            status="degraded",
            data=CreatePaymentLinkData(offer_slug=offer_slug, amount_cents=amount_cents),
            error=StripeError(
                code="invalid_amount",
                message=f"Amount {amount_cents} is below Stripe's minimum of {MIN_AMOUNT_CENTS} cents.",
                suggestion=f"Pass --amount with at least {MIN_AMOUNT_CENTS} (50 cents).",
            ),
        )
        sys.exit(emit(env))

    if not currency.isalpha() or len(currency) != 3:
        env = CreatePaymentLinkEnvelope(
            status="degraded",
            data=CreatePaymentLinkData(offer_slug=offer_slug, currency=currency),
            error=StripeError(
                code="invalid_currency",
                message=f"Currency {currency!r} is not a 3-letter ISO code.",
                suggestion="Pass --currency=usd (V1 only supports USD).",
            ),
        )
        sys.exit(emit(env))
    currency_lower = currency.lower()

    descriptor = _truncate_descriptor(statement_descriptor or DEFAULT_STATEMENT_DESCRIPTOR)
    desc_err = _validate_statement_descriptor(descriptor)
    if desc_err:
        env = CreatePaymentLinkEnvelope(
            status="degraded",
            data=CreatePaymentLinkData(offer_slug=offer_slug, statement_descriptor=descriptor),
            error=StripeError(
                code="invalid_statement_descriptor",
                message=desc_err,
                suggestion="Use 5–22 ASCII letters/digits/spaces/dots/hyphens.",
            ),
        )
        sys.exit(emit(env))

    if not success_url.startswith("https://"):
        env = CreatePaymentLinkEnvelope(
            status="degraded",
            data=CreatePaymentLinkData(offer_slug=offer_slug, success_url=success_url),
            error=StripeError(
                code="invalid_success_url",
                message=f"Success URL must be HTTPS: {success_url!r}",
                suggestion="Pass --success-url=https://<domain>/start/thanks/.",
            ),
        )
        sys.exit(emit(env))

    api_key = os.environ.get("STRIPE_API_KEY", "").strip()
    if not api_key:
        env = CreatePaymentLinkEnvelope(
            status="degraded",
            data=CreatePaymentLinkData(offer_slug=offer_slug),
            error=StripeError(
                code="missing_api_key",
                message="STRIPE_API_KEY is not set in the environment.",
                suggestion="Add `export STRIPE_API_KEY=sk_test_...` to ~/.config/vip/env.sh and `source` it.",
            ),
        )
        sys.exit(emit(env))

    # --- Idempotency check via product search ---
    log(f"Checking for existing mb_offer={offer_slug} product...")
    existing, search_result = _search_existing_product(api_key, offer_slug, provenance)
    if search_result is not None and not search_result.ok:
        code, suggestion = _classify_error(search_result)
        env = CreatePaymentLinkEnvelope(
            status="degraded",
            data=CreatePaymentLinkData(offer_slug=offer_slug),
            provenance=provenance,
            error=StripeError(code=code, message=search_result.error_message or "search failed", suggestion=suggestion),
        )
        sys.exit(emit(env))

    if existing:
        existing_url = (existing.get("metadata") or {}).get(META_PAYMENT_LINK_URL)
        if existing_url:
            log(f"Found existing product {existing.get('id')} with payment link, returning idempotent.")
            env = CreatePaymentLinkEnvelope(
                status="ok",
                data=CreatePaymentLinkData(
                    offer_slug=offer_slug,
                    payment_link_url=existing_url,
                    product_id=existing.get("id"),
                    price_id=existing.get("default_price"),
                    amount_cents=amount_cents,
                    currency=currency_lower,
                    statement_descriptor=descriptor,
                    success_url=success_url,
                    created_now=False,
                ),
                provenance=provenance,
            )
            sys.exit(emit(env))
        log(f"Found existing product {existing.get('id')} but no stashed payment link — creating one.")
        product_id = existing.get("id")
        price_id = existing.get("default_price")
    else:
        # --- Create product (with default_price_data) ---
        log(f"Creating new Stripe product for offer={offer_slug}...")
        created_at = str(int(time.time()))
        product_body = {
            "name": product_name or offer_slug,
            "active": True,
            "default_price_data": {
                "currency": currency_lower,
                "unit_amount": amount_cents,
            },
            "metadata": {
                META_OFFER: offer_slug,
                META_KIND: META_KIND_VALUE,
                META_CREATED_AT: created_at,
            },
        }
        if description:
            product_body["description"] = description
        if descriptor:
            product_body["statement_descriptor"] = descriptor

        product_result = _stripe_call(
            "POST",
            "/products",
            api_key,
            body=product_body,
            idempotency_key=f"mb-{offer_slug}-product",
        )
        provenance["stripe_product_create"] = ProviderRunMetadata(
            status="ok" if product_result.ok else "failed",
            latency_ms=product_result.latency_ms,
            error=product_result.error_message,
            provider_version="stripe-2024-06-20",
        )
        if not product_result.ok:
            code, suggestion = _classify_error(product_result)
            env = CreatePaymentLinkEnvelope(
                status="degraded",
                data=CreatePaymentLinkData(offer_slug=offer_slug),
                provenance=provenance,
                error=StripeError(code=code, message=product_result.error_message or "create failed", suggestion=suggestion),
            )
            sys.exit(emit(env))

        product = product_result.payload or {}
        product_id = product.get("id")
        # Stripe expands default_price as ID string by default, full object with ?expand.
        default_price = product.get("default_price")
        price_id = default_price if isinstance(default_price, str) else (
            (default_price or {}).get("id") if isinstance(default_price, dict) else None
        )

    if not product_id or not price_id:
        env = CreatePaymentLinkEnvelope(
            status="degraded",
            data=CreatePaymentLinkData(offer_slug=offer_slug),
            provenance=provenance,
            error=StripeError(
                code="stripe_request_failed",
                message="Stripe product create succeeded but response missing id or default_price.",
                suggestion="Re-run; if persistent, inspect the raw provenance entry.",
            ),
        )
        sys.exit(emit(env))

    # --- Create payment link ---
    log(f"Creating payment link for product={product_id} price={price_id}...")
    link_body = {
        "line_items": [
            {"price": price_id, "quantity": 1},
        ],
        "after_completion": {
            "type": "redirect",
            "redirect": {"url": success_url},
        },
        "metadata": {
            META_OFFER: offer_slug,
            META_KIND: META_KIND_VALUE,
        },
    }
    link_result = _stripe_call(
        "POST",
        "/payment_links",
        api_key,
        body=link_body,
        idempotency_key=f"mb-{offer_slug}-link",
    )
    provenance["stripe_payment_link_create"] = ProviderRunMetadata(
        status="ok" if link_result.ok else "failed",
        latency_ms=link_result.latency_ms,
        error=link_result.error_message,
        provider_version="stripe-2024-06-20",
    )
    if not link_result.ok:
        code, suggestion = _classify_error(link_result)
        env = CreatePaymentLinkEnvelope(
            status="degraded",
            data=CreatePaymentLinkData(
                offer_slug=offer_slug,
                product_id=product_id,
                price_id=price_id,
            ),
            provenance=provenance,
            error=StripeError(code=code, message=link_result.error_message or "payment link create failed", suggestion=suggestion),
        )
        sys.exit(emit(env))

    payment_link = link_result.payload or {}
    payment_link_url = payment_link.get("url")
    payment_link_id = payment_link.get("id")

    # --- Stash payment link URL on product metadata for future idempotency ---
    if payment_link_url:
        update_result = _update_product_metadata(
            api_key,
            product_id,
            {META_PAYMENT_LINK_URL: payment_link_url},
            provenance,
        )
        if not update_result.ok:
            log(f"Warning: failed to stash payment_link_url on product metadata: {update_result.error_message}")

    env = CreatePaymentLinkEnvelope(
        status="ok",
        data=CreatePaymentLinkData(
            offer_slug=offer_slug,
            payment_link_url=payment_link_url,
            payment_link_id=payment_link_id,
            product_id=product_id,
            price_id=price_id,
            amount_cents=amount_cents,
            currency=currency_lower,
            statement_descriptor=descriptor,
            success_url=success_url,
            created_now=existing is None,
        ),
        provenance=provenance,
    )
    sys.exit(emit(env))


@cli.command("list-products")
@click.option("--offer-slug", default=None, help="Filter by mb_offer metadata.")
@click.option("--limit", default=20, show_default=True, type=int, help="Max products to return (1-100).")
def list_products(offer_slug: str | None, limit: int) -> None:
    """List active products. Filter to Main Branch products via --offer-slug."""
    provenance: dict[str, ProviderRunMetadata] = {}
    api_key = os.environ.get("STRIPE_API_KEY", "").strip()
    if not api_key:
        env = ListProductsEnvelope(
            status="degraded",
            data=ListProductsData(),
            error=StripeError(
                code="missing_api_key",
                message="STRIPE_API_KEY is not set in the environment.",
                suggestion="Add `export STRIPE_API_KEY=sk_test_...` to ~/.config/vip/env.sh.",
            ),
        )
        sys.exit(emit(env))

    if offer_slug:
        slug_err = _validate_offer_slug(offer_slug)
        if slug_err:
            env = ListProductsEnvelope(
                status="degraded",
                data=ListProductsData(),
                error=StripeError(code="invalid_offer_slug", message=slug_err, suggestion=None),
            )
            sys.exit(emit(env))

    if offer_slug:
        query = (
            f'metadata[\'{META_OFFER}\']:\'{offer_slug}\' '
            f'AND metadata[\'{META_KIND}\']:\'{META_KIND_VALUE}\' '
            f"AND active:'true'"
        )
        result = _stripe_call(
            "GET",
            "/products/search",
            api_key,
            query={"query": query, "limit": max(1, min(limit, 100))},
        )
    else:
        result = _stripe_call(
            "GET",
            "/products",
            api_key,
            query={"active": "true", "limit": max(1, min(limit, 100))},
        )
    provenance["stripe_products_list"] = ProviderRunMetadata(
        status="ok" if result.ok else "failed",
        latency_ms=result.latency_ms,
        error=result.error_message,
        provider_version="stripe-2024-06-20",
    )

    if not result.ok:
        code, suggestion = _classify_error(result)
        env = ListProductsEnvelope(
            status="degraded",
            data=ListProductsData(),
            provenance=provenance,
            error=StripeError(code=code, message=result.error_message or "list failed", suggestion=suggestion),
        )
        sys.exit(emit(env))

    items = (result.payload or {}).get("data") or []
    # Trim to the fields callers actually need (id, name, default_price, metadata, created).
    trimmed = [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "active": p.get("active"),
            "default_price": p.get("default_price"),
            "metadata": p.get("metadata") or {},
            "created": p.get("created"),
        }
        for p in items
    ]

    env = ListProductsEnvelope(
        status="ok",
        data=ListProductsData(products=trimmed, count=len(trimmed)),
        provenance=provenance,
    )
    sys.exit(emit(env))


@cli.command("archive-product")
@click.argument("product_id")
def archive_product(product_id: str) -> None:
    """Mark a product inactive (Stripe doesn't support hard delete)."""
    provenance: dict[str, ProviderRunMetadata] = {}
    api_key = os.environ.get("STRIPE_API_KEY", "").strip()
    if not api_key:
        env = ArchiveProductEnvelope(
            status="degraded",
            data=ArchiveProductData(product_id=product_id),
            error=StripeError(
                code="missing_api_key",
                message="STRIPE_API_KEY is not set in the environment.",
                suggestion="Add `export STRIPE_API_KEY=sk_test_...` to ~/.config/vip/env.sh.",
            ),
        )
        sys.exit(emit(env))

    if not product_id.startswith("prod_"):
        env = ArchiveProductEnvelope(
            status="degraded",
            data=ArchiveProductData(product_id=product_id),
            error=StripeError(
                code="invalid_offer_slug",
                message=f"Product id {product_id!r} doesn't look like a Stripe product id (expected prod_...).",
                suggestion="Pass the prod_... id from `stripe.py list-products`.",
            ),
        )
        sys.exit(emit(env))

    result = _stripe_call("POST", f"/products/{product_id}", api_key, body={"active": False})
    provenance["stripe_product_archive"] = ProviderRunMetadata(
        status="ok" if result.ok else "failed",
        latency_ms=result.latency_ms,
        error=result.error_message,
        provider_version="stripe-2024-06-20",
    )

    if not result.ok:
        code, suggestion = _classify_error(result)
        env = ArchiveProductEnvelope(
            status="degraded",
            data=ArchiveProductData(product_id=product_id),
            provenance=provenance,
            error=StripeError(code=code, message=result.error_message or "archive failed", suggestion=suggestion),
        )
        sys.exit(emit(env))

    env = ArchiveProductEnvelope(
        status="ok",
        data=ArchiveProductData(product_id=product_id, archived=True),
        provenance=provenance,
    )
    sys.exit(emit(env))


if __name__ == "__main__":
    cli()
