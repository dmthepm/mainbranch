#!/usr/bin/env python3
"""domain.py — domain operations atom.

Subcommands:
    check  Wraps the `domain-check` brew CLI (RDAP, no auth) for availability lookups.
    buy    Unavailable placeholder that emits a structured error; use the registrar
           dashboard until live registration support lands behind guardrails.

Invocation: `python3 domain.py <subcommand> [args]`
Output: companyctx-shape envelope JSON on stdout, logs on stderr.
Exit code: 0 on ok|partial, 1 on degraded.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal

import click
from pydantic import BaseModel, ConfigDict, Field, model_validator

# Allow `python3 path/to/domain.py` when run directly (script lookup).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _envelope import (  # noqa: E402
    OWNER_HANDOFF,
    porkbun_howto,
    SCHEMA_VERSION,
    EnvelopeStatus,
    ProviderRunMetadata,
    emit,
    log,
    porkbun_keys,
    validate_status_consistency,
)

DOMAIN_CHECK_BIN = shutil.which("domain-check") or "/opt/homebrew/bin/domain-check"

# ---------------------------------------------------------------------------
# domain check
# ---------------------------------------------------------------------------

DomainCheckErrorCode = Literal[
    "domain_check_unavailable",
    "domain_check_failed",
    "tld_not_supported",
    "invalid_name",
    "network_timeout",
]


class DomainCheckError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: DomainCheckErrorCode
    message: str
    suggestion: str | None = None


class DomainCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str
    available: bool
    method_used: str | None = None


class DomainCheckData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    tlds_checked: list[str]
    results: list[DomainCheckResult]
    available: list[str] = Field(default_factory=list)


class DomainCheckEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    status: EnvelopeStatus
    data: DomainCheckData
    provenance: dict[str, ProviderRunMetadata] = Field(default_factory=dict)
    error: DomainCheckError | None = None

    @model_validator(mode="after")
    def _v(self) -> DomainCheckEnvelope:
        return validate_status_consistency(self)  # type: ignore[return-value]


def _run_domain_check(domains: list[str]) -> tuple[list[dict], int, str | None]:
    """Run the brew `domain-check` CLI in JSON mode. Returns (rows, latency_ms, error)."""
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [DOMAIN_CHECK_BIN, *domains, "--json", "--batch", "--yes"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return [], int((time.monotonic() - start) * 1000), "binary_missing"
    except subprocess.TimeoutExpired:
        return [], int((time.monotonic() - start) * 1000), "timeout"

    latency_ms = int((time.monotonic() - start) * 1000)

    if proc.returncode != 0:
        return [], latency_ms, f"exit_{proc.returncode}: {proc.stderr.strip()[:200]}"

    try:
        rows = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return [], latency_ms, f"json_parse: {exc}"

    if not isinstance(rows, list):
        return [], latency_ms, f"unexpected_shape: {type(rows).__name__}"

    return rows, latency_ms, None


@click.group()
def cli() -> None:
    """domain.py — domain operations atom."""


@cli.command("check")
@click.argument("name")
@click.option(
    "--tlds",
    default=".com,.co,.xyz",
    show_default=True,
    help="Comma-separated TLDs to check (with or without leading dot).",
)
@click.option(
    "--full-domain",
    is_flag=True,
    help="Treat NAME as a fully qualified domain; ignore --tlds.",
)
def check(name: str, tlds: str, full_domain: bool) -> None:
    """Check availability for NAME across one or more TLDs (RDAP via domain-check)."""
    name = name.strip().lower()
    if not name:
        env = DomainCheckEnvelope(
            status="degraded",
            data=DomainCheckData(name=name, tlds_checked=[], results=[]),
            error=DomainCheckError(
                code="invalid_name",
                message="Empty name argument.",
                suggestion="Pass a domain stem (e.g. 'mybrand') or a full domain with --full-domain.",
            ),
        )
        sys.exit(emit(env))

    if full_domain:
        if "." not in name:
            env = DomainCheckEnvelope(
                status="degraded",
                data=DomainCheckData(name=name, tlds_checked=[], results=[]),
                error=DomainCheckError(
                    code="invalid_name",
                    message=f"--full-domain set but {name!r} has no TLD.",
                    suggestion="Pass a fully qualified domain like 'example.com', or drop --full-domain to use --tlds.",
                ),
            )
            sys.exit(emit(env))
        domains = [name]
        tlds_checked = [name.split(".", 1)[1]]
    else:
        tld_list = [t.strip().lstrip(".") for t in tlds.split(",") if t.strip()]
        if not tld_list:
            env = DomainCheckEnvelope(
                status="degraded",
                data=DomainCheckData(name=name, tlds_checked=[], results=[]),
                error=DomainCheckError(
                    code="tld_not_supported",
                    message="No TLDs supplied to --tlds.",
                    suggestion="Pass a comma-separated list like '.com,.co,.xyz'.",
                ),
            )
            sys.exit(emit(env))
        domains = [f"{name}.{tld}" for tld in tld_list]
        tlds_checked = tld_list

    rows, latency_ms, err = _run_domain_check(domains)

    if err == "binary_missing":
        env = DomainCheckEnvelope(
            status="degraded",
            data=DomainCheckData(name=name, tlds_checked=tlds_checked, results=[]),
            provenance={
                "domain_check": ProviderRunMetadata(
                    status="not_configured",
                    latency_ms=latency_ms,
                    error="binary_missing",
                    provider_version="domain-check",
                )
            },
            error=DomainCheckError(
                code="domain_check_unavailable",
                message=f"`domain-check` binary not found at {DOMAIN_CHECK_BIN}.",
                suggestion="brew install domain-check",
            ),
        )
        sys.exit(emit(env))

    if err == "timeout":
        env = DomainCheckEnvelope(
            status="degraded",
            data=DomainCheckData(name=name, tlds_checked=tlds_checked, results=[]),
            provenance={
                "domain_check": ProviderRunMetadata(
                    status="failed",
                    latency_ms=latency_ms,
                    error="timeout",
                    provider_version="domain-check",
                )
            },
            error=DomainCheckError(
                code="network_timeout",
                message="domain-check did not return within 60s.",
                suggestion="Retry with fewer TLDs, or check your network connection.",
            ),
        )
        sys.exit(emit(env))

    if err is not None:
        env = DomainCheckEnvelope(
            status="degraded",
            data=DomainCheckData(name=name, tlds_checked=tlds_checked, results=[]),
            provenance={
                "domain_check": ProviderRunMetadata(
                    status="failed",
                    latency_ms=latency_ms,
                    error=err,
                    provider_version="domain-check",
                )
            },
            error=DomainCheckError(
                code="domain_check_failed",
                message=f"domain-check failed: {err}",
                suggestion="Run with --debug locally and report the failure shape.",
            ),
        )
        sys.exit(emit(env))

    # Parse rows. Each row: {"domain": "...", "available": bool, "method_used": "..."}
    results = []
    available = []
    for row in rows:
        domain = row.get("domain", "")
        avail = bool(row.get("available", False))
        method = row.get("method_used")
        results.append(DomainCheckResult(domain=domain, available=avail, method_used=method))
        if avail:
            available.append(domain)

    env = DomainCheckEnvelope(
        status="ok",
        data=DomainCheckData(
            name=name,
            tlds_checked=tlds_checked,
            results=results,
            available=available,
        ),
        provenance={
            "domain_check": ProviderRunMetadata(
                status="ok",
                latency_ms=latency_ms,
                provider_version="domain-check",
            )
        },
    )
    sys.exit(emit(env))


# ---------------------------------------------------------------------------
# domain buy (unavailable until live registrar support lands)
# ---------------------------------------------------------------------------

DomainBuyErrorCode = Literal[
    "domain_unavailable",
    "already_owned",
    "registrar_unauthenticated",
    "price_exceeds_ceiling",
    "tld_not_supported",
    "rate_limited",
    "network_timeout",
    "registrar_rejected",
    "registrar_unsupported",
    "no_registrar_configured",
    "user_declined",
]


class DomainBuyError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: DomainBuyErrorCode
    message: str
    suggestion: str | None = None


class DomainBuyData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str
    registrar: Literal["cloudflare", "porkbun"] | None = None
    price_usd: float | None = None
    purchased: bool = False
    already_owned: bool = False
    expiry: str | None = None  # ISO date string
    years: int = 1


class DomainBuyEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    status: EnvelopeStatus
    data: DomainBuyData
    provenance: dict[str, ProviderRunMetadata] = Field(default_factory=dict)
    error: DomainBuyError | None = None

    @model_validator(mode="after")
    def _v(self) -> DomainBuyEnvelope:
        return validate_status_consistency(self)  # type: ignore[return-value]


def _select_registrar(
    explicit: str | None, domain: str = "DOMAIN"
) -> tuple[str | None, DomainBuyError | None]:
    """Pick a registrar based on explicit flag and env vars. Returns (registrar, error)."""
    if explicit:
        return explicit, None
    if os.environ.get("CLOUDFLARE_API_TOKEN_REGISTRAR"):
        return "cloudflare", None
    if porkbun_keys():
        return "porkbun", None
    return None, DomainBuyError(
        code="no_registrar_configured",
        message="No registrar credentials found.",
        suggestion=(
            "Use CLOUDFLARE_API_TOKEN_REGISTRAR (preferred) or Porkbun: "
            + porkbun_howto(f"domain.py buy {domain} --registrar porkbun")
            + " "
            + OWNER_HANDOFF
        ),
    )


@cli.command("buy")
@click.argument("name")
@click.option(
    "--registrar",
    type=click.Choice(["cloudflare", "porkbun"]),
    default=None,
    help="Override registrar selection. Default: env-detected (cloudflare > porkbun).",
)
@click.option("--years", default=1, show_default=True, type=int)
@click.option(
    "--max-price",
    default=30.0,
    show_default=True,
    type=float,
    help="Refuse to register if listed price exceeds this ceiling (USD).",
)
@click.option(
    "--yes",
    "assume_yes",
    is_flag=True,
    help="Skip the confirmation prompt. Required for non-interactive use.",
)
def buy(name: str, registrar: str | None, years: int, max_price: float, assume_yes: bool) -> None:
    """Register a domain. NAME must be a full domain (e.g. 'mybrand.com').

    NOTE: live registrar calls are not wired. This command validates inputs
    and emits a structured `registrar_unsupported` error so `/mb-site` cannot
    imply that Main Branch can buy the domain.
    """
    name = name.strip().lower()

    if "." not in name:
        env = DomainBuyEnvelope(
            status="degraded",
            data=DomainBuyData(domain=name, years=years),
            error=DomainBuyError(
                code="tld_not_supported",
                message=f"buy expects a full domain; got {name!r} with no TLD.",
                suggestion="Pass a fully qualified domain like 'example.com'.",
            ),
        )
        sys.exit(emit(env))

    selected, err = _select_registrar(registrar, name)
    if err is not None:
        env = DomainBuyEnvelope(
            status="degraded",
            data=DomainBuyData(domain=name, years=years),
            error=err,
        )
        sys.exit(emit(env))

    # Cost-spending atoms require explicit confirmation.
    if not assume_yes:
        log(
            f"About to register {name} at {selected} for {years}yr (max ${max_price:.2f}). "
            "Pass --yes to proceed."
        )
        env = DomainBuyEnvelope(
            status="degraded",
            data=DomainBuyData(domain=name, registrar=selected, years=years),  # type: ignore[arg-type]
            error=DomainBuyError(
                code="user_declined",
                message="Registration requires --yes confirmation.",
                suggestion=f"Re-run with --yes if you actually want to spend money on {name}.",
            ),
        )
        sys.exit(emit(env))

    # Registrar API integration not yet wired (V1 scope: code lands, live test deferred).
    env = DomainBuyEnvelope(
        status="degraded",
        data=DomainBuyData(domain=name, registrar=selected, years=years),  # type: ignore[arg-type]
        error=DomainBuyError(
            code="registrar_unsupported",
            message=f"Registrar API for {selected!r} not yet wired in this build.",
            suggestion=(
                "Buy the domain in the registrar dashboard, then rerun `/mb-site` "
                "after you own the full domain."
            ),
        ),
    )
    sys.exit(emit(env))


if __name__ == "__main__":
    cli()
