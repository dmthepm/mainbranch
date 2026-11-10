"""Shared envelope primitives for /mb-site atoms.

Lifted from `dmthepm/companyctx`'s schema.py. The shape is the contract:
every atom emits exactly one Envelope-shape JSON document on stdout. Agents
branch on `error.code` (a closed Literal per atom). Humans read `error.message`
and act on `error.suggestion`.

Each atom defines its own concrete Envelope class binding:
    - `data` to its result Pydantic model
    - `error` to a per-atom EnvelopeError subclass with a closed `code` Literal

This module exports only the shared building blocks. Atom-specific shapes live
in the atom file (e.g. `domain.py`).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "0.1.0"

# Appended to every missing-credential message the atoms print, so an agent
# reading the runtime output hands off instead of trying a prompt it cannot open.
OWNER_HANDOFF = (
    "Credential entry happens in the owner's own terminal, because the hidden prompt "
    "needs a real terminal; the agent hands off, then resumes its readiness check."
)

# Porkbun needs two secrets but a custom `mb connect` provider holds one, so the
# owner stores them as one value, "<api key>:<secret key>", and runs the script
# through this command (the same text is printed wherever Porkbun is missing).
PORKBUN_CONNECT_STORE = 'mb connect porkbun --custom --account "Porkbun"'
SCRIPTS_DIR = ".claude/skills/mb-site/scripts"


def porkbun_command(script_args: str, *, with_cloudflare: bool = False) -> str:
    """The one runnable command that gives `script_args` the Porkbun credential.

    `with_cloudflare` is for dns.py, which needs the Cloudflare token and account
    id as well. One `mb connect exec` run holds one provider, so the Cloudflare run
    wraps the Porkbun one and each keeps exactly the names the script reads.
    """
    run = f"mb connect exec porkbun --env PORKBUN_CREDENTIALS -- python3 {SCRIPTS_DIR}/{script_args}"
    if not with_cloudflare:
        return run
    inner = run.replace(
        "--env PORKBUN_CREDENTIALS",
        "--env PORKBUN_CREDENTIALS --keep-env CLOUDFLARE_API_TOKEN --keep-env CF_ACCOUNT_ID",
    )
    return f"CF_ACCOUNT_ID=<id> mb connect exec cloudflare --keep-env CF_ACCOUNT_ID -- {inner}"


def porkbun_howto(script_args: str, *, with_cloudflare: bool = False) -> str:
    """Owner guidance with one exact, runnable command (script_args: e.g. `dns.py ensure example.com`)."""
    cloudflare = (
        " It also needs the Cloudflare connection (`mb connect cloudflare`) and your "
        "Cloudflare account id (not a secret), which replaces `<id>`."
        if with_cloudflare
        else ""
    )
    return (
        "Both keys go in one secret, `<api key>:<secret key>`, typed at the hidden prompt: "
        f"`{PORKBUN_CONNECT_STORE}`. The API key part must not contain a colon "
        "(the secret key part may)."
        f"{cloudflare} Then run, from the repo root, through `mb connect exec`: "
        f"`{porkbun_command(script_args, with_cloudflare=with_cloudflare)}`."
    )


def porkbun_keys() -> tuple[str, str] | None:
    """Split PORKBUN_CREDENTIALS into (api key, secret key); None when absent or malformed."""
    api_key, sep, secret_key = os.environ.get("PORKBUN_CREDENTIALS", "").strip().partition(":")
    if not sep or not api_key or not secret_key:
        return None
    return api_key, secret_key


def scrub_porkbun(text: object, *extra_keys: str) -> str:
    """Return text with both Porkbun key parts (and the combined value) removed.

    Provider and exception text can reflect a key back; scrub it before it is
    printed or stored. `extra_keys` covers keys passed in rather than read from env.
    """
    out = str(text)
    keys = set(extra_keys)
    combined = os.environ.get("PORKBUN_CREDENTIALS", "").strip()
    if combined:
        keys.add(combined)
    pair = porkbun_keys()
    if pair:
        keys.update(pair)
    for key in sorted((k for k in keys if k), key=len, reverse=True):
        out = out.replace(key, "[redacted]")
    return out


EnvelopeStatus = Literal["ok", "partial", "degraded"]
ProviderStatus = Literal["ok", "degraded", "failed", "not_configured"]


class ProviderRunMetadata(BaseModel):
    """Per-provider provenance row. Attach one per upstream call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ProviderStatus
    latency_ms: int
    error: str | None = None
    provider_version: str
    cost_incurred: int = 0
    """Cost charged by this attempt, in US cents. Free providers stay 0."""


def validate_status_consistency(envelope: BaseModel) -> BaseModel:
    """Status ⟺ error invariant. Call from each atom's @model_validator(mode="after")."""
    status = getattr(envelope, "status", None)
    err = getattr(envelope, "error", None)
    if status == "ok" and err is not None:
        raise ValueError('status="ok" must not include an error')
    if status != "ok" and err is None:
        raise ValueError('status!="ok" requires a structured error')
    return envelope


def emit(envelope: BaseModel) -> int:
    """Print envelope to stdout as indented JSON. Returns POSIX exit code.

    Exit codes:
        ok       → 0
        partial  → 0   (data returned with caveats; not an operational failure)
        degraded → 1   (operational failure; agent should branch on error.code)
    """
    sys.stdout.write(envelope.model_dump_json(indent=2) + "\n")
    sys.stdout.flush()

    status = getattr(envelope, "status", None)
    if status in ("ok", "partial"):
        return 0
    return 1


def log(msg: str) -> None:
    """Write a log line to stderr. Stdout is reserved for the envelope JSON."""
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


__all__ = [
    "SCHEMA_VERSION",
    "porkbun_howto",
    "scrub_porkbun",
    "EnvelopeStatus",
    "ProviderStatus",
    "ProviderRunMetadata",
    "validate_status_consistency",
    "emit",
    "log",
]
