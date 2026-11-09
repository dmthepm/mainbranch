#!/usr/bin/env python3
"""dns.py — DNS operations atom.

Credential entry happens in the owner's own terminal, because the hidden prompt needs a real terminal; the agent hands off, then resumes its readiness check.

Subcommand:
    ensure   Idempotent: ensure a Cloudflare zone exists for <domain>, swap
             nameservers at the registrar if needed (Porkbun-registered only),
             poll until propagation confirmed.

Invocation: `python3 dns.py ensure <domain> [--registrar cloudflare|porkbun]`
Output: companyctx-shape envelope JSON on stdout, logs on stderr.

Live integration with Cloudflare and Porkbun is wired but deferred to the
first real-project domain (per #94: no money on junk fixtures, no zones
created against test domains we don't own).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal

import click
import requests
from pydantic import BaseModel, ConfigDict, Field, model_validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _envelope import (  # noqa: E402
    OWNER_HANDOFF,
    PORKBUN_HOWTO,
    SCHEMA_VERSION,
    EnvelopeStatus,
    ProviderRunMetadata,
    emit,
    log,
    porkbun_keys,
    validate_status_consistency,
)

CF_API_BASE = "https://api.cloudflare.com/client/v4"
PORKBUN_API_BASE = "https://api.porkbun.com/api/json/v3"
CF_NS_SUFFIX = ".ns.cloudflare.com"

# Loose domain validator. Real validation happens upstream on first API call.
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")

# ---------------------------------------------------------------------------
# Envelope shape
# ---------------------------------------------------------------------------

DnsEnsureErrorCode = Literal[
    "invalid_domain",
    "cf_account_id_missing",
    "cf_unauthenticated",
    "cf_rate_limited",
    "cf_request_failed",
    "zone_already_exists",  # 1097: zone owned by another CF account
    "registrar_required",  # need NS swap but no registrar specified/detected
    "registrar_unsupported",
    "porkbun_unauthenticated",
    "porkbun_ns_update_failed",
    "dig_unavailable",
    "propagation_timeout",
    "network_timeout",
]


class DnsEnsureError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: DnsEnsureErrorCode
    message: str
    suggestion: str | None = None


class DnsEnsureData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str
    zone_id: str | None = None
    ns_pair: list[str] = Field(default_factory=list)
    zone_created_now: bool = False
    registrar: Literal["cloudflare", "porkbun"] | None = None
    ns_swap_performed: bool = False
    propagated: bool = False
    propagation_seconds: int | None = None


class DnsEnsureEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    status: EnvelopeStatus
    data: DnsEnsureData
    provenance: dict[str, ProviderRunMetadata] = Field(default_factory=dict)
    error: DnsEnsureError | None = None

    @model_validator(mode="after")
    def _v(self) -> DnsEnsureEnvelope:
        return validate_status_consistency(self)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# CF API helpers
# ---------------------------------------------------------------------------


class CfResult(BaseModel):
    """Internal: a Cloudflare API response normalized for atom consumption."""

    model_config = ConfigDict(extra="forbid")
    ok: bool
    latency_ms: int
    status_code: int
    payload: dict | list | None = None
    error_code: int | None = None
    error_message: str | None = None


def _cf_call(method: str, path: str, token: str, json_body: dict | None = None) -> CfResult:
    url = f"{CF_API_BASE}{path}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    start = time.monotonic()
    try:
        resp = requests.request(method, url, headers=headers, json=json_body, timeout=30)
    except requests.Timeout:
        return CfResult(
            ok=False,
            latency_ms=int((time.monotonic() - start) * 1000),
            status_code=0,
            error_message="timeout",
        )
    except requests.RequestException as exc:
        return CfResult(
            ok=False,
            latency_ms=int((time.monotonic() - start) * 1000),
            status_code=0,
            error_message=f"request_exception: {exc.__class__.__name__}",
        )

    latency_ms = int((time.monotonic() - start) * 1000)
    try:
        body = resp.json()
    except ValueError:
        return CfResult(
            ok=False,
            latency_ms=latency_ms,
            status_code=resp.status_code,
            error_message="non_json_response",
        )

    success = bool(body.get("success", False))
    errors = body.get("errors") or []
    err_code = errors[0].get("code") if errors else None
    err_msg = errors[0].get("message") if errors else None
    return CfResult(
        ok=success,
        latency_ms=latency_ms,
        status_code=resp.status_code,
        payload=body.get("result"),
        error_code=err_code,
        error_message=err_msg,
    )


# CF error codes that indicate auth problems regardless of HTTP status.
# 10000 / 10001 — generic auth token error in body
# 6003 / 6111 — malformed Authorization header (HTTP 400 path)
# 9106 / 9107 — missing X-Auth-Email / X-Auth-Key (legacy auth path)
# 9109 — token format OK but invalid/revoked (HTTP 403 path)
_CF_AUTH_ERROR_CODES = frozenset({10000, 10001, 6003, 6111, 9106, 9107, 9109})


def _cf_classify_error(result: CfResult) -> tuple[DnsEnsureErrorCode, str]:
    """Map a failed CF response to a closed-enum error code + suggestion."""
    if result.error_message == "timeout":
        return "network_timeout", "Cloudflare API timed out. Retry; check connectivity."
    if (
        result.status_code == 401
        or (result.error_code is not None and result.error_code in _CF_AUTH_ERROR_CODES)
    ):
        return (
            "cf_unauthenticated",
            "Verify CLOUDFLARE_API_TOKEN exists, isn't revoked, and has "
            "Zone:Edit + DNS:Edit + Pages:Edit scopes. Create at "
            "https://dash.cloudflare.com/profile/api-tokens.",
        )
    if result.status_code == 429:
        return "cf_rate_limited", "Cloudflare rate-limited the request. Back off and retry."
    if result.error_code == 1097:
        return (
            "zone_already_exists",
            "Zone exists in another Cloudflare account. Manual cleanup required at "
            "dash.cloudflare.com before retrying.",
        )
    return (
        "cf_request_failed",
        f"Cloudflare API rejected: {result.error_message or 'unknown'} "
        f"(http {result.status_code}, code {result.error_code}).",
    )


# ---------------------------------------------------------------------------
# Porkbun NS update helper
# ---------------------------------------------------------------------------


def _porkbun_update_ns(
    domain: str, nameservers: list[str], api_key: str, secret_key: str
) -> tuple[bool, int, str | None]:
    url = f"{PORKBUN_API_BASE}/domain/updateNs/{domain}"
    body = {
        "apikey": api_key,
        "secretapikey": secret_key,
        "ns": nameservers,
    }
    start = time.monotonic()
    try:
        resp = requests.post(url, json=body, timeout=30)
    except requests.Timeout:
        return False, int((time.monotonic() - start) * 1000), "timeout"
    except requests.RequestException as exc:
        return False, int((time.monotonic() - start) * 1000), f"request_exception: {exc!s}"

    latency_ms = int((time.monotonic() - start) * 1000)
    try:
        body_json = resp.json()
    except ValueError:
        return False, latency_ms, f"non_json_response: http {resp.status_code}"

    status = body_json.get("status")
    if status != "SUCCESS":
        return False, latency_ms, body_json.get("message", "unknown_error")
    return True, latency_ms, None


# ---------------------------------------------------------------------------
# Propagation polling
# ---------------------------------------------------------------------------


def _dig_ns(domain: str) -> tuple[list[str] | None, str | None]:
    """Query 1.1.1.1 for the domain's NS records. Returns (ns_list, error)."""
    dig_bin = shutil.which("dig")
    if not dig_bin:
        return None, "dig_unavailable"
    try:
        proc = subprocess.run(
            [dig_bin, "+short", "NS", domain, "@1.1.1.1"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return None, "dig_timeout"
    if proc.returncode != 0:
        return None, f"dig_exit_{proc.returncode}"
    lines = [ln.strip().rstrip(".").lower() for ln in proc.stdout.splitlines() if ln.strip()]
    return lines, None


def _wait_for_propagation(
    domain: str, expected_ns: list[str], timeout_seconds: int
) -> tuple[bool, int, str | None]:
    """Poll dig +short NS until expected_ns appear. Returns (propagated, elapsed_s, error)."""
    expected_lower = {ns.lower().rstrip(".") for ns in expected_ns}
    start = time.monotonic()
    while True:
        observed, err = _dig_ns(domain)
        if err == "dig_unavailable":
            return False, int(time.monotonic() - start), "dig_unavailable"
        if observed and expected_lower.issubset(set(observed)):
            return True, int(time.monotonic() - start), None
        elapsed = int(time.monotonic() - start)
        if elapsed >= timeout_seconds:
            return False, elapsed, "timeout"
        log(f"  [{elapsed:>4}s] NS observed: {observed or '(none)'} — waiting for {sorted(expected_lower)}")
        time.sleep(min(30, max(5, timeout_seconds // 30)))


# ---------------------------------------------------------------------------
# Registrar selection
# ---------------------------------------------------------------------------


def _detect_registrar(explicit: str | None) -> tuple[str | None, DnsEnsureError | None]:
    if explicit:
        return explicit, None
    if os.environ.get("CLOUDFLARE_API_TOKEN_REGISTRAR"):
        return "cloudflare", None
    if porkbun_keys():
        return "porkbun", None
    return None, DnsEnsureError(
        code="registrar_required",
        message="Cannot determine registrar; pass --registrar or set CF/Porkbun env vars.",
        suggestion=(
            "Pass --registrar=cloudflare or --registrar=porkbun. "
            "Or store the registrar credential with `mb connect` and run this through "
            "`mb connect exec` (CLOUDFLARE_API_TOKEN_REGISTRAR for CF-registered; "
            "for Porkbun-registered: store the Porkbun credential with `mb connect`. "
            + PORKBUN_HOWTO
            + " "
            + OWNER_HANDOFF
        ),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """dns.py — DNS operations atom."""


@cli.command("ensure")
@click.argument("domain")
@click.option(
    "--registrar",
    type=click.Choice(["cloudflare", "porkbun"]),
    default=None,
    help="Where the domain is registered. Auto-detected from env if omitted.",
)
@click.option(
    "--timeout-seconds",
    default=600,
    show_default=True,
    type=int,
    help="Max wait for NS propagation before returning propagation_timeout.",
)
@click.option(
    "--skip-propagation-poll",
    is_flag=True,
    help="Skip the propagation poll. Use only if a downstream caller will poll itself.",
)
def ensure(
    domain: str, registrar: str | None, timeout_seconds: int, skip_propagation_poll: bool
) -> None:
    """Ensure DOMAIN has a Cloudflare zone with NS pointing at CF.

    Idempotent: existing zones are reused; existing CF nameservers are not re-pushed.
    """
    domain = domain.strip().lower().rstrip(".")
    provenance: dict[str, ProviderRunMetadata] = {}

    if not _DOMAIN_RE.match(domain):
        env = DnsEnsureEnvelope(
            status="degraded",
            data=DnsEnsureData(domain=domain),
            error=DnsEnsureError(
                code="invalid_domain",
                message=f"Domain {domain!r} doesn't look like a valid apex.",
                suggestion="Pass a registrable apex like 'example.com' (no scheme, no path).",
            ),
        )
        sys.exit(emit(env))

    cf_token = os.environ.get("CLOUDFLARE_API_TOKEN")
    cf_account_id = os.environ.get("CF_ACCOUNT_ID")

    if not cf_token:
        env = DnsEnsureEnvelope(
            status="degraded",
            data=DnsEnsureData(domain=domain),
            error=DnsEnsureError(
                code="cf_unauthenticated",
                message="CLOUDFLARE_API_TOKEN not set.",
                suggestion=(
                    "Store a token with Zone:Edit + DNS:Edit permissions using "
                    "`mb connect cloudflare` (it prompts with hidden input), then run this through "
                    "`mb connect exec cloudflare -- <command>`. "
                    + OWNER_HANDOFF
                ),
            ),
        )
        sys.exit(emit(env))

    if not cf_account_id:
        env = DnsEnsureEnvelope(
            status="degraded",
            data=DnsEnsureData(domain=domain),
            error=DnsEnsureError(
                code="cf_account_id_missing",
                message="CF_ACCOUNT_ID not set.",
                suggestion=(
                    "CF_ACCOUNT_ID is not a secret (find it at dash.cloudflare.com → "
                    "right sidebar of any zone). `mb connect exec` drops it unless "
                    "you name it: CF_ACCOUNT_ID=<id> mb connect exec cloudflare "
                    "--keep-env CF_ACCOUNT_ID -- <command>."
                ),
            ),
        )
        sys.exit(emit(env))

    selected_registrar, reg_err = _detect_registrar(registrar)
    if reg_err is not None:
        env = DnsEnsureEnvelope(
            status="degraded",
            data=DnsEnsureData(domain=domain),
            error=reg_err,
        )
        sys.exit(emit(env))

    # Step 1: look up existing zone
    log(f"Looking up Cloudflare zone for {domain}...")
    lookup = _cf_call(
        "GET", f"/zones?name={domain}&account.id={cf_account_id}", cf_token
    )
    provenance["cf_zone_lookup"] = ProviderRunMetadata(
        status="ok" if lookup.ok else "failed",
        latency_ms=lookup.latency_ms,
        error=None if lookup.ok else (lookup.error_message or "unknown"),
        provider_version="cloudflare-api-v4",
    )
    if not lookup.ok:
        code, suggestion = _cf_classify_error(lookup)
        env = DnsEnsureEnvelope(
            status="degraded",
            data=DnsEnsureData(domain=domain, registrar=selected_registrar),  # type: ignore[arg-type]
            provenance=provenance,
            error=DnsEnsureError(code=code, message=lookup.error_message or "lookup_failed", suggestion=suggestion),
        )
        sys.exit(emit(env))

    zones = lookup.payload if isinstance(lookup.payload, list) else []
    zone_id: str | None = None
    ns_pair: list[str] = []
    zone_created_now = False

    if zones:
        zone = zones[0]
        zone_id = zone.get("id")
        ns_pair = list(zone.get("name_servers") or [])
        log(f"Zone exists: id={zone_id}, ns={ns_pair}")
    else:
        # Step 2: create zone
        log(f"Creating Cloudflare zone for {domain}...")
        create = _cf_call(
            "POST",
            "/zones",
            cf_token,
            json_body={"name": domain, "account": {"id": cf_account_id}},
        )
        provenance["cf_zone_create"] = ProviderRunMetadata(
            status="ok" if create.ok else "failed",
            latency_ms=create.latency_ms,
            error=None if create.ok else (create.error_message or "unknown"),
            provider_version="cloudflare-api-v4",
        )
        if not create.ok:
            code, suggestion = _cf_classify_error(create)
            env = DnsEnsureEnvelope(
                status="degraded",
                data=DnsEnsureData(domain=domain, registrar=selected_registrar),  # type: ignore[arg-type]
                provenance=provenance,
                error=DnsEnsureError(
                    code=code, message=create.error_message or "create_failed", suggestion=suggestion
                ),
            )
            sys.exit(emit(env))

        zone = create.payload if isinstance(create.payload, dict) else {}
        zone_id = zone.get("id")
        ns_pair = list(zone.get("name_servers") or [])
        zone_created_now = True
        log(f"Zone created: id={zone_id}, ns={ns_pair}")

    if not ns_pair or not all(ns.endswith(CF_NS_SUFFIX) for ns in ns_pair):
        env = DnsEnsureEnvelope(
            status="degraded",
            data=DnsEnsureData(
                domain=domain,
                zone_id=zone_id,
                ns_pair=ns_pair,
                zone_created_now=zone_created_now,
                registrar=selected_registrar,  # type: ignore[arg-type]
            ),
            provenance=provenance,
            error=DnsEnsureError(
                code="cf_request_failed",
                message="Cloudflare returned no nameservers for the zone.",
                suggestion="Check the zone in dash.cloudflare.com; it may be in a non-standard plan/state.",
            ),
        )
        sys.exit(emit(env))

    # Step 3: NS swap if registrar is porkbun
    ns_swap_performed = False
    if selected_registrar == "porkbun":
        pb_keys = porkbun_keys()
        if not pb_keys:
            env = DnsEnsureEnvelope(
                status="degraded",
                data=DnsEnsureData(
                    domain=domain,
                    zone_id=zone_id,
                    ns_pair=ns_pair,
                    zone_created_now=zone_created_now,
                    registrar="porkbun",
                ),
                provenance=provenance,
                error=DnsEnsureError(
                    code="porkbun_unauthenticated",
                    message="PORKBUN_CREDENTIALS not set, or not in <api key>:<secret key> form.",
                    suggestion=(
                        "Store the Porkbun credential with `mb connect`. "
                        + PORKBUN_HOWTO.replace("<script>", "dns.py")
                        + " "
                        + OWNER_HANDOFF
                    ),
                ),
            )
            sys.exit(emit(env))

        log(f"Updating Porkbun nameservers for {domain} → {ns_pair}")
        ok, lat, err = _porkbun_update_ns(domain, ns_pair, *pb_keys)
        provenance["porkbun_update_ns"] = ProviderRunMetadata(
            status="ok" if ok else "failed",
            latency_ms=lat,
            error=err,
            provider_version="porkbun-api-v3",
        )
        if not ok:
            env = DnsEnsureEnvelope(
                status="degraded",
                data=DnsEnsureData(
                    domain=domain,
                    zone_id=zone_id,
                    ns_pair=ns_pair,
                    zone_created_now=zone_created_now,
                    registrar="porkbun",
                ),
                provenance=provenance,
                error=DnsEnsureError(
                    code="porkbun_ns_update_failed",
                    message=f"Porkbun rejected NS update: {err or 'unknown'}",
                    suggestion="Verify the domain is in the Porkbun account whose API keys you supplied.",
                ),
            )
            sys.exit(emit(env))
        ns_swap_performed = True

    # Step 4: propagation poll
    propagated = False
    propagation_seconds: int | None = None
    if not skip_propagation_poll:
        log(f"Polling NS propagation (timeout {timeout_seconds}s)...")
        propagated, elapsed, prop_err = _wait_for_propagation(
            domain, ns_pair, timeout_seconds
        )
        propagation_seconds = elapsed
        provenance["dns_propagation_poll"] = ProviderRunMetadata(
            status="ok" if propagated else "failed",
            latency_ms=elapsed * 1000,
            error=prop_err,
            provider_version="dig+1.1.1.1",
        )
        if prop_err == "dig_unavailable":
            env = DnsEnsureEnvelope(
                status="degraded",
                data=DnsEnsureData(
                    domain=domain,
                    zone_id=zone_id,
                    ns_pair=ns_pair,
                    zone_created_now=zone_created_now,
                    registrar=selected_registrar,  # type: ignore[arg-type]
                    ns_swap_performed=ns_swap_performed,
                    propagated=False,
                    propagation_seconds=elapsed,
                ),
                provenance=provenance,
                error=DnsEnsureError(
                    code="dig_unavailable",
                    message="`dig` binary not on PATH; cannot poll propagation.",
                    suggestion="brew install bind (provides dig). Or pass --skip-propagation-poll.",
                ),
            )
            sys.exit(emit(env))
        if not propagated:
            env = DnsEnsureEnvelope(
                status="degraded",
                data=DnsEnsureData(
                    domain=domain,
                    zone_id=zone_id,
                    ns_pair=ns_pair,
                    zone_created_now=zone_created_now,
                    registrar=selected_registrar,  # type: ignore[arg-type]
                    ns_swap_performed=ns_swap_performed,
                    propagated=False,
                    propagation_seconds=elapsed,
                ),
                provenance=provenance,
                error=DnsEnsureError(
                    code="propagation_timeout",
                    message=f"NS did not propagate to Cloudflare within {timeout_seconds}s.",
                    suggestion=(
                        "Check the registrar dashboard — NS update may be queued. "
                        "Re-run `dns.py ensure` once the registrar shows the new NS."
                    ),
                ),
            )
            sys.exit(emit(env))

    env = DnsEnsureEnvelope(
        status="ok",
        data=DnsEnsureData(
            domain=domain,
            zone_id=zone_id,
            ns_pair=ns_pair,
            zone_created_now=zone_created_now,
            registrar=selected_registrar,  # type: ignore[arg-type]
            ns_swap_performed=ns_swap_performed,
            propagated=propagated,
            propagation_seconds=propagation_seconds,
        ),
        provenance=provenance,
    )
    sys.exit(emit(env))


if __name__ == "__main__":
    cli()
