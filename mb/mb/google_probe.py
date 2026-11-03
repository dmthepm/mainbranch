"""``mb connect test google`` on a Google sign-in: one read-only call per granted product.

Only an OAuth-mode ``google`` connection (its entry records ``oauth_grant``)
is checked here. A legacy access-token ``google`` connection keeps the
probe-less path in ``connect._validate_with_provider``.

The check mints an access token through ``google_connect.read_minted_token``
(the same per-process cache and ``reauth_required`` recording as
``mb connect token``/``exec``), then, for each product the sign-in granted and
whose metadata is recorded:

- Search Console: ``searchAnalytics.query`` on ``search_console_site`` for one
  past day, ``rowLimit: 1``, no dimensions;
- GA4: ``runReport`` on ``ga4_property_id``, metric ``activeUsers``, one
  explicit past date, ``limit: 1``.

Verified means every recorded product passed. A product the sign-in did not
grant is skipped (``grant_missing``) and is not a failure of the others.

Outcomes carry stable ``rule`` names and fixed text. Google's response bodies
are parsed only to match a short allowlist of error reasons; no Google text,
token or row ever reaches the output or the recorded validation. A network
failure, a server error, a quota answer or an unreadable answer says nothing
about the sign-in, so the recorded state is left as it was.
"""

from __future__ import annotations

import http.client
import json
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mb import connect as connect_mod
from mb import google_connect as gc
from mb import google_oauth as go

SEARCH_CONSOLE = "search_console"
GA4 = "ga4"
PRODUCTS: tuple[str, ...] = (SEARCH_CONSOLE, GA4)
PRODUCT_NAMES = {SEARCH_CONSOLE: "Search Console", GA4: "Analytics (GA4)"}

SEARCH_CONSOLE_QUERY_URL = (
    "https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"
)
GA4_RUN_REPORT_URL = "https://analyticsdata.googleapis.com/v1beta/properties/{property}:runReport"
ENDPOINT_FAMILIES = {
    SEARCH_CONSOLE: "search_console_search_analytics_query",
    GA4: "ga4_run_report",
}
PROBE_TIMEOUT_SECONDS = 8.0
# Search Console data lags by a few days; any finished past day answers.
PROBE_DAYS_BACK = 3

TEST_COMMAND = "mb connect test google"
SITE_COMMAND = "mb connect google --metadata search_console_site=<site>"
PROPERTY_COMMAND = "mb connect google --metadata ga4_property_id=<property-id>"

# States a product (and the whole check) can end in.
STATE_OK = "ok"
STATE_GRANT_MISSING = "grant_missing"
STATE_NOT_CHECKED = "not_checked"

# Google error reasons matched by exact value (never shown, never stored as
# Google sent them): the API is not enabled in the client's Cloud project, or
# a quota or rate limit answered.
_API_DISABLED_REASONS = frozenset({"SERVICE_DISABLED", "accessNotConfigured"})
_QUOTA_REASONS = frozenset(
    {
        "RATE_LIMIT_EXCEEDED",
        "RESOURCE_EXHAUSTED",
        "quotaExceeded",
        "rateLimitExceeded",
        "userRateLimitExceeded",
        "dailyLimitExceeded",
    }
)

# Test seams. The CLI uses these defaults; tests replace them.
api_sender: go.Sender | None = None


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


today: Callable[[], date] = _utc_today


@dataclass(frozen=True)
class _Outcome:
    """Fixed text for one product outcome, keyed by rule."""

    state: str
    summary: str
    repair: str = ""
    repair_command: str = ""
    # Recorded to the entry: the outcome is a fact about the sign-in or the
    # metadata, not a network, server or quota blip.
    recordable: bool = True


def _outcomes(product: str) -> dict[str, _Outcome]:
    name = PRODUCT_NAMES[product]
    later = _Outcome(
        state=go.STATE_UNVALIDATED,
        summary="",
        repair=f"Nothing about the sign-in is known to be wrong; run `{TEST_COMMAND}` again later.",
        repair_command=TEST_COMMAND,
        recordable=False,
    )
    if product == SEARCH_CONSOLE:
        not_recorded = _Outcome(
            state=go.STATE_UNVALIDATED,
            summary="Search Console is granted, but no search_console_site is recorded.",
            repair=(
                f"Run `{SITE_COMMAND}` with the property as Search Console names it "
                "(sc-domain:example.com, or a URL prefix such as https://www.example.com/), "
                f"then `{TEST_COMMAND}`."
            ),
            repair_command=SITE_COMMAND,
        )
        no_access = _Outcome(
            state=go.STATE_INVALID,
            summary=(
                "Search Console refused the recorded site: the signed-in Google account cannot "
                "read it, or it is not a Search Console property."
            ),
            repair=(
                "In Search Console, add the signed-in Google account to this property under "
                "Settings > Users and permissions (Restricted is enough), or record the right "
                f"property with `{SITE_COMMAND}`; then run `{TEST_COMMAND}`."
            ),
            repair_command=TEST_COMMAND,
        )
        api = "Google Search Console API"
    else:
        not_recorded = _Outcome(
            state=go.STATE_UNVALIDATED,
            summary="Analytics (GA4) is granted, but no ga4_property_id is recorded.",
            repair=(
                "Find the numeric property id under GA4 Admin > Property details, then run "
                f"`{PROPERTY_COMMAND}` and `{TEST_COMMAND}`."
            ),
            repair_command=PROPERTY_COMMAND,
        )
        no_access = _Outcome(
            state=go.STATE_INVALID,
            summary=(
                "Google Analytics refused the recorded property: the signed-in Google account "
                "cannot read it, or the property id is wrong."
            ),
            repair=(
                "In Google Analytics, give the signed-in Google account at least the Viewer "
                "role on this property under Admin > Property access management, or record "
                f"the right id with `{PROPERTY_COMMAND}`; then run `{TEST_COMMAND}`."
            ),
            repair_command=TEST_COMMAND,
        )
        api = "Google Analytics Data API"
    prefix = "search_console" if product == SEARCH_CONSOLE else "ga4"
    return {
        STATE_OK: _Outcome(state=STATE_OK, summary=f"{name} read with the sign-in."),
        STATE_GRANT_MISSING: _Outcome(
            state=STATE_GRANT_MISSING,
            summary=f"{name} was not granted at sign-in, so it was skipped.",
            repair=(
                "To add it, a person signs in again with `mb connect google --oauth --reauth` "
                "and ticks its box."
            ),
        ),
        f"{prefix}_{'site' if product == SEARCH_CONSOLE else 'property'}_not_recorded": (
            not_recorded
        ),
        f"{prefix}_no_access": no_access,
        f"{prefix}_api_disabled": _Outcome(
            state=go.STATE_INVALID,
            summary=(
                f"The {api} is not enabled in the Google Cloud project that owns the OAuth client."
            ),
            repair=(
                f"Enable the {api} in that Cloud project (APIs & Services > Library), wait a few "
                f"minutes, then run `{TEST_COMMAND}`."
            ),
            repair_command=TEST_COMMAND,
        ),
        f"{prefix}_auth_rejected": _Outcome(
            state=go.STATE_INVALID,
            summary=f"{name} rejected the access token minted from the sign-in.",
            repair=(
                f"A person signs in again in a terminal: `{gc.REAUTH_COMMAND}`, then "
                f"`{TEST_COMMAND}`."
            ),
            repair_command=gc.REAUTH_COMMAND,
        ),
        f"{prefix}_request_rejected": _Outcome(
            state=go.STATE_INVALID,
            summary=f"{name} refused the read-only check request.",
            repair=(
                "Check the recorded site and property with `mb connect status google`, record "
                f"the right one with `mb connect google --metadata ...`, then run `{TEST_COMMAND}`."
            ),
            repair_command=TEST_COMMAND,
        ),
        f"{prefix}_quota_exhausted": _Outcome(
            state=later.state,
            summary=f"{name} answered with a quota or rate limit.",
            repair=later.repair,
            repair_command=later.repair_command,
            recordable=False,
        ),
        f"{prefix}_server_error": _Outcome(
            state=later.state,
            summary=f"{name} answered with a server error.",
            repair=later.repair,
            repair_command=later.repair_command,
            recordable=False,
        ),
        f"{prefix}_unreachable": _Outcome(
            state=later.state,
            summary=f"{name} could not be reached.",
            repair=later.repair,
            repair_command=later.repair_command,
            recordable=False,
        ),
        f"{prefix}_unexpected_redirect": _Outcome(
            state=later.state,
            summary=f"{name} answered with a redirect, which is never followed.",
            repair=later.repair,
            repair_command=later.repair_command,
            recordable=False,
        ),
        f"{prefix}_response_malformed": _Outcome(
            state=later.state,
            summary=f"{name} returned an unreadable answer.",
            repair=later.repair,
            repair_command=later.repair_command,
            recordable=False,
        ),
    }


OUTCOMES: dict[str, dict[str, _Outcome]] = {product: _outcomes(product) for product in PRODUCTS}


def probe_date() -> str:
    """The one past day both checks read (UTC date, a few days back)."""

    return (today() - timedelta(days=PROBE_DAYS_BACK)).isoformat()


def search_console_request(site: str, day: str) -> tuple[str, dict[str, Any]]:
    url = SEARCH_CONSOLE_QUERY_URL.format(site=urllib.parse.quote(site, safe=""))
    return url, {"startDate": day, "endDate": day, "rowLimit": 1}


def ga4_request(property_id: str, day: str) -> tuple[str, dict[str, Any]]:
    url = GA4_RUN_REPORT_URL.format(property=property_id)
    return url, {
        "dateRanges": [{"startDate": day, "endDate": day}],
        "metrics": [{"name": "activeUsers"}],
        "limit": 1,
    }


def _reasons(payload: Any) -> set[str]:
    """Error reasons Google put in a JSON error body, for allowlist matching only."""

    found: set[str] = set()
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return found
    for key in ("status",):
        if isinstance(error.get(key), str):
            found.add(error[key])
    for list_key in ("errors", "details"):
        items = error.get(list_key)
        if isinstance(items, list):
            for item in items[:16]:
                if isinstance(item, dict) and isinstance(item.get("reason"), str):
                    found.add(item["reason"])
    return found


def _upstream(product: str) -> dict[str, Any]:
    return {
        "endpoint_family": ENDPOINT_FAMILIES[product],
        "http_status": None,
        "response_received": False,
        "safe_to_share": True,
    }


def _call(product: str, url: str, body: dict[str, Any], token: str) -> tuple[str, dict[str, Any]]:
    """POST one check and return ``(rule, upstream)``. Nothing Google sent is returned."""

    prefix = "search_console" if product == SEARCH_CONSOLE else "ga4"
    upstream = _upstream(product)
    send = api_sender if api_sender is not None else go._urllib_sender
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        status, raw = send(url, json.dumps(body).encode("utf-8"), headers, PROBE_TIMEOUT_SECONDS)
    except (OSError, ValueError, http.client.HTTPException):
        return f"{prefix}_unreachable", upstream
    upstream["http_status"] = int(status)
    upstream["response_received"] = True
    payload: Any = None
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, ValueError, RecursionError):
        payload = None
    if 200 <= status < 300:
        return (STATE_OK if isinstance(payload, dict) else f"{prefix}_response_malformed"), upstream
    reasons = _reasons(payload)
    if status == 429 or reasons & _QUOTA_REASONS:
        return f"{prefix}_quota_exhausted", upstream
    if status >= 500:
        return f"{prefix}_server_error", upstream
    if 300 <= status < 400:
        # `_urllib_sender` never follows a redirect, so the token never
        # reaches a second URL.
        return f"{prefix}_unexpected_redirect", upstream
    if status == 401:
        return f"{prefix}_auth_rejected", upstream
    if status == 403 and reasons & _API_DISABLED_REASONS:
        return f"{prefix}_api_disabled", upstream
    if status in {403, 404}:
        return f"{prefix}_no_access", upstream
    return f"{prefix}_request_rejected", upstream


def _granted(metadata: dict[str, Any]) -> set[str]:
    raw = str(metadata.get(gc.METADATA_GRANTS) or "")
    return {label.strip() for label in raw.split(",") if label.strip()}


def _recorded_site(metadata: dict[str, Any]) -> str:
    value = str(metadata.get(gc.METADATA_SITE) or "").strip()
    if not value:
        return ""
    try:
        return gc.normalize_search_console_site(value)
    except connect_mod.ConnectRefusal:
        return ""


def _recorded_property(metadata: dict[str, Any]) -> str:
    value = str(metadata.get(gc.METADATA_PROPERTY) or "").strip()
    if not value:
        return ""
    try:
        return gc.normalize_ga4_property_id(value)
    except connect_mod.ConnectRefusal:
        return ""


def _product_result(product: str, rule: str, upstream: dict[str, Any] | None) -> dict[str, Any]:
    outcome = OUTCOMES[product][rule]
    return {
        "state": outcome.state,
        "rule": rule,
        "summary": outcome.summary,
        "repair": outcome.repair,
        "repair_command": outcome.repair_command,
        "recordable": outcome.recordable,
        "upstream": upstream or _upstream(product),
        "safe_to_share": True,
    }


def check_products(metadata: dict[str, Any], token: str) -> dict[str, dict[str, Any]]:
    """Run the check for every product, in a fixed order."""

    granted = _granted(metadata)
    day = probe_date()
    results: dict[str, dict[str, Any]] = {}
    for product in PRODUCTS:
        if product not in granted:
            results[product] = _product_result(product, STATE_GRANT_MISSING, None)
            continue
        if product == SEARCH_CONSOLE:
            site = _recorded_site(metadata)
            if not site:
                results[product] = _product_result(
                    product, "search_console_site_not_recorded", None
                )
                continue
            url, body = search_console_request(site, day)
        else:
            property_id = _recorded_property(metadata)
            if not property_id:
                results[product] = _product_result(product, "ga4_property_not_recorded", None)
                continue
            url, body = ga4_request(property_id, day)
        rule, upstream = _call(product, url, body, token)
        results[product] = _product_result(product, rule, upstream)
    return results


def _overall(products: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Fold the product results into one validation outcome."""

    checked = [p for p in products.values() if p["state"] != STATE_GRANT_MISSING]
    failed_hard = [p for p in checked if p["state"] == go.STATE_INVALID]
    transient = [p for p in checked if p["state"] != STATE_OK and not p["recordable"]]
    unrecorded_metadata = [
        p for p in checked if p["state"] == go.STATE_UNVALIDATED and p["recordable"]
    ]
    if not checked:
        return {
            "ok": False,
            "state": go.STATE_UNVALIDATED,
            "rule": STATE_GRANT_MISSING,
            "summary": "The Google sign-in granted neither Search Console nor Analytics.",
            "repair": (
                f"A person signs in again with `{gc.REAUTH_COMMAND}` and ticks the read-only boxes."
            ),
            "repair_command": gc.REAUTH_COMMAND,
            "record": True,
        }
    if failed_hard:
        first = failed_hard[0]
        return {**_lead(first), "ok": False, "state": go.STATE_INVALID, "record": True}
    if transient:
        return {**_lead(transient[0]), "ok": False, "state": go.STATE_UNVALIDATED, "record": False}
    if unrecorded_metadata:
        return {
            **_lead(unrecorded_metadata[0]),
            "ok": False,
            "state": go.STATE_UNVALIDATED,
            "record": True,
        }
    read = " and ".join(
        PRODUCT_NAMES[name] for name, p in products.items() if p["state"] == STATE_OK
    )
    skipped = [
        PRODUCT_NAMES[name] for name, p in products.items() if p["state"] == STATE_GRANT_MISSING
    ]
    summary = f"Google sign-in verified: {read} read with it."
    if skipped:
        summary += f" {' and '.join(skipped)} not granted (skipped)."
    return {
        "ok": True,
        "state": "ready",
        "rule": STATE_OK,
        "summary": summary,
        "repair": "",
        "repair_command": "",
        "record": True,
    }


def _lead(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule": product["rule"],
        "summary": product["summary"],
        "repair": product["repair"],
        "repair_command": product["repair_command"],
    }


def _token_failure(minted: dict[str, Any]) -> dict[str, Any]:
    """The check outcome when no access token could be minted."""

    state = str(minted.get("state") or go.STATE_UNVALIDATED)
    error = str(minted.get("error") or "the Google sign-in could not be read")
    summary = error[:1].upper() + error[1:] + "."
    # `reauth_required` is recorded by `read_minted_token` itself. A rejected
    # client or an unreadable or missing grant is a fact about the sign-in, so
    # it is recorded as `invalid`. Nothing else is.
    record = state in {go.STATE_INVALID, "missing_secret"}
    return {
        "ok": False,
        "state": go.STATE_INVALID if record else state,
        "rule": str(minted.get("rule") or minted.get("backend_state") or "token_not_minted"),
        "summary": summary,
        "repair": "",
        "repair_command": str(minted.get("repair_command") or ""),
        "record": record,
    }


def _validation_record(
    overall: dict[str, Any],
    products: dict[str, dict[str, Any]],
    previous: dict[str, Any],
    checked_at: str,
) -> dict[str, Any]:
    verified = bool(overall["ok"])
    record: dict[str, Any] = {
        "state": overall["state"],
        "checked_at": checked_at,
        "provider_verified": verified,
        "verified_at": checked_at if verified else connect_mod._verified_at(previous),
        "summary": overall["summary"],
        "safe_to_share": True,
        "rule": overall["rule"],
        "products": {
            name: {"state": p["state"], "rule": p["rule"]} for name, p in products.items()
        },
    }
    if overall["repair"] or overall["repair_command"]:
        record["repair"] = overall["repair"] or (
            f"Run `{overall['repair_command']}`." if overall["repair_command"] else ""
        )
        record["repair_command"] = overall["repair_command"]
    upstream = {
        name: p["upstream"] for name, p in products.items() if p["upstream"]["response_received"]
    }
    if upstream:
        record["upstream"] = {"endpoint_family": "google_read_only_check", "products": upstream}
    return record


def test_google(
    provider: connect_mod.Provider,
    target: Path,
    *,
    source: str,
    before: dict[str, Any],
    status_again: Callable[[], dict[str, Any]],
    access_token: str | None = None,
    record_in_tracked_config: bool = False,
) -> dict[str, Any]:
    """``mb connect test google`` for an OAuth-mode entry (see the module docstring).

    ``access_token`` is the sign-in's own freshly exchanged token, so its last
    step checks without minting; ``mb connect test`` always mints.
    """

    config = connect_mod._read_config(target)
    repo_id = connect_mod._bound_repo_id(target, config)
    entry = config["providers"].get(provider.id)
    if not isinstance(entry, dict):
        entry = connect_mod._user_scope_provider_entry(repo_id, provider.id) or {}
    if access_token:
        minted: dict[str, Any] = {"ok": True, "token": access_token}
    else:
        minted = gc.read_minted_token(entry, source=source, target=target)
    checked_at = connect_mod._now()
    if minted["ok"]:
        raw_metadata = entry.get("metadata")
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        products = check_products(metadata, str(minted["token"]))
        overall = _overall(products)
    else:
        products = {
            name: {
                "state": STATE_NOT_CHECKED,
                "rule": "token_not_minted",
                "summary": "",
                "repair": "",
                "repair_command": "",
                "recordable": False,
                "upstream": _upstream(name),
                "safe_to_share": True,
            }
            for name in PRODUCTS
        }
        overall = _token_failure(minted)

    recorded = False
    not_recorded_reason = ""
    not_recorded_detail = ""
    validation: dict[str, Any]
    # Recording writes .mb/connect.yaml; a tracked one is left as it is.
    tracked = not record_in_tracked_config and connect_mod.config_tracked_by_git(target)
    if tracked:
        not_recorded_reason = "connect_yaml_tracked"
    if overall["record"] and not tracked:
        # Re-read: minting may have just cleared a recorded `reauth_required`.
        config = connect_mod._read_config(target)
        repo_entry = config["providers"].get(provider.id)
        live = repo_entry if isinstance(repo_entry, dict) else entry
        raw_previous = live.get("validation")
        previous: dict[str, Any] = raw_previous if isinstance(raw_previous, dict) else {}
        validation = _validation_record(overall, products, previous, checked_at)
        live["validation"] = validation
        live["last_checked_at"] = checked_at
        not_recorded = connect_mod._record_validation(target, config, provider.id, live)
        recorded = not not_recorded
        not_recorded_reason = str(not_recorded.get("not_recorded_reason") or "")
        not_recorded_detail = str(not_recorded.get("not_recorded_detail") or "")
    else:
        validation = _validation_record(overall, products, {}, checked_at)
        # `read_minted_token` has already recorded this one for status.
        recorded = overall["state"] == gc.STATE_REAUTH_REQUIRED and not tracked
        if minted.get("not_recorded_note"):
            # `read_minted_token` could not write the user-scope file.
            recorded = False
            not_recorded_reason = str(
                minted.get("not_recorded_reason") or "user_scope_write_failed"
            )
            not_recorded_detail = str(minted["not_recorded_note"])
    status = status_again()
    result = {
        "ok": bool(overall["ok"]),
        "provider": provider.id,
        "stored": bool(status.get("stored", before.get("stored"))),
        "provider_verified": bool(overall["ok"]),
        "verified_at": str(status.get("verified_at") or ""),
        "state": overall["state"],
        "rule": overall["rule"],
        "summary": overall["summary"],
        "repair_command": overall["repair_command"],
        "recorded": recorded,
        "not_recorded_reason": not_recorded_reason,
        # The CLI exits 1 on this even when an unrecorded failure leaves the
        # stored status green.
        "needs_action": not overall["ok"],
        "products": {
            name: {key: value for key, value in p.items() if key != "recordable"}
            for name, p in products.items()
        },
        "validation": validation,
        "status": status,
        "safe_to_share": True,
    }
    if not_recorded_detail:
        result["not_recorded_detail"] = not_recorded_detail
    return result


def render_products(products: dict[str, dict[str, Any]], indent: str = "  ") -> None:
    for name in PRODUCTS:
        product = products.get(name)
        if not product or product["state"] == STATE_NOT_CHECKED:
            continue
        state = product["state"]
        label = (
            state if state in {STATE_OK, STATE_GRANT_MISSING} else f"{state} ({product['rule']})"
        )
        print(f"{indent}{name}: {label}")
        if state not in {STATE_OK, STATE_NOT_CHECKED} and product.get("repair"):
            print(f"{indent}  {product['repair']}")


def render_test_result(result: dict[str, Any]) -> None:
    state = "ok" if result["ok"] else "warn"
    print(f"mb connect test google: {state} ({connect_mod.state_label(result['state'])})")
    if result.get("summary"):
        print(f"summary: {result['summary']}")
    render_products(result.get("products") or {})
    if result.get("not_recorded_reason") == "connect_yaml_tracked":
        print(
            "recorded: no (.mb/connect.yaml is tracked by git, so checks are not written to "
            "it; `mb connect status google` shows the last check a person recorded)"
        )
    elif result.get("not_recorded_reason") == "user_scope_read_only":
        connect_mod.render_user_scope_not_recorded()
    elif result.get("not_recorded_reason") == "user_scope_write_failed":
        connect_mod.render_user_scope_write_failed(result)
    elif not result["ok"] and not result.get("recorded"):
        print(
            "recorded: no (this says nothing about the sign-in itself; "
            f"status still reads {connect_mod.state_label(str(result['status'].get('state')))})"
        )
    if result.get("repair_command"):
        print(f"next: {result['repair_command']}")
