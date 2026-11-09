"""Shared envelope primitives for /mb-site atoms.

Lifted from `dmthepm/companyctx`'s schema.py. The shape is the contract:
every atom emits exactly one Envelope-shape JSON document on stdout. Agents
branch on `error.code` (a closed Literal per atom). Humans read `error.message`
and act on `error.suggestion`.

Credential entry happens in the owner's own terminal, because the hidden prompt needs a real terminal; the agent hands off, then resumes its readiness check.

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
PORKBUN_CONNECT_RUN = (
    "mb connect exec porkbun --env PORKBUN_CREDENTIALS -- python3 <script> ..."
)
PORKBUN_HOWTO = (
    "Both keys go in one secret, `<api key>:<secret key>`, typed at the hidden prompt: "
    f"`{PORKBUN_CONNECT_STORE}`. Then run through `mb connect exec`: `{PORKBUN_CONNECT_RUN}`."
)


def porkbun_keys() -> tuple[str, str] | None:
    """Split PORKBUN_CREDENTIALS into (api key, secret key); None when absent or malformed."""
    api_key, sep, secret_key = os.environ.get("PORKBUN_CREDENTIALS", "").strip().partition(":")
    if not sep or not api_key or not secret_key:
        return None
    return api_key, secret_key


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
    "EnvelopeStatus",
    "ProviderStatus",
    "ProviderRunMetadata",
    "validate_status_consistency",
    "emit",
    "log",
]
