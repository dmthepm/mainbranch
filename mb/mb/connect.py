"""Integration registry and credential metadata for ``mb connect``."""

from __future__ import annotations

import errno
import hashlib
import hmac
import json
import math
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

import yaml

from mb import http_safe
from mb._credential_helper import STAGE_SUFFIX
from mb.credential_store import (
    KEYCHAIN_REPAIR_ALL_COMMAND,
    KEYCHAIN_REPAIR_COMMAND,
    CredentialStoreError,
    SecretProbe,
    SecretStore,
    backend_repair,
    list_keychain_refs,
    new_credential_deadline,
    select_secret_backend,
)
from mb.durable import atomic_write_text

CONFIG_RELATIVE_PATH = Path(".mb") / "connect.yaml"
USER_SCOPE_RELATIVE_PATH = Path("connect") / "user-scope.yaml"
SENSITIVE_KEY_PARTS = ("token", "secret", "password", "credential", "api_key", "apikey", "key")
SAFE_METADATA_KEYS = {
    "token_type",
    "token_scope",
    "api_token_type",
    "key_name",
    "onepassword_item",
    "source",
}
CONNECT_SCOPES = {"repo", "user"}
VALIDATION_TIMEOUT_SECONDS = 8
SECRET_REPLACEMENT = "<redacted>"
CommandRunner = Callable[..., dict[str, Any]]
Which = Callable[[str], str | None]

SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b"
    r"(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|token|secret|password|"
    r"credential|authorization)"
    r"([ \t]*[:=][ \t]*)(bearer[ \t]+)?([^\s,;]+)"
)
SECRET_PHRASE_RE = re.compile(
    r"(?i)\b"
    r"((?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|authorization)[ \t]+)"
    r"(bearer[ \t]+)?([A-Za-z0-9._~+/=-]{12,})"
)
BEARER_SECRET_RE = re.compile(r"(?i)\bbearer[ \t]+[^\s,;]+")

BACKEND_FAILURE_STATE = "backend_unavailable"
# A credential is stored and readable, but no provider call has ever confirmed
# it works. Distinct from `unvalidated` ("`mb connect test` has not been run"):
# running the test again cannot clear this state when the provider has no probe.
UNVERIFIED_STATE = "stored_unverified"
# An aggregate command (`mb connect status`/`list`, `mb doctor`) ran out of its
# shared credential budget before it could read this credential. Nothing is
# known, so nothing is reported broken and nothing is suggested for repair; a
# single-provider `mb connect status <id>` gets its own budget (#1151).
NOT_CHECKED_STATE = "credential_not_checked"
NOT_CHECKED_BACKEND_STATE = "not_checked"


# Providers with a real read-only probe in `_validate_with_provider`. Kept as
# one named set because the exit-code contract turns on it: a provider with a
# probe can be verified by running `mb connect test`, and one without cannot be
# verified by anything the operator runs.
# `test_probe_provider_set_matches_validate_with_provider` guards the drift.
PROBE_PROVIDERS: frozenset[str] = frozenset(
    {"cloudflare", "apify", "meta", "stripe", "github", "ga4"}
)
# Providers whose probe depends on how the connection was made. `google` is
# probed only in OAuth mode (its entry records an `oauth_grant`; see
# `mb/google_probe.py`); an access-token `google` connection stays probe-less,
# so it keeps exiting 0 as it always has. Disjoint from `PROBE_PROVIDERS`.
CONDITIONAL_PROBE_PROVIDERS: frozenset[str] = frozenset({"google"})


# `mb connect token` without `--print` when stdout is a terminal or a pipe.
# Distinct from 1 (credential missing or unreadable, store failure) and 2
# (usage error or any other refusal), so a script can tell "refused by design"
# from "no credential". Stable: documented in docs/connect.md.
TOKEN_REFUSED_EXIT_CODE = 3


class ConnectRefusal(ValueError):
    """A connect policy refused an action. ``rule`` names the policy, never a value."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


def _refuse(rule: str, message: str) -> NoReturn:
    """Raise every connect refusal from one place.

    ``rule`` is a stable machine name for the policy that fired; ``message``
    tells the operator what to do instead. Neither ever carries a secret value.
    """
    raise ConnectRefusal(rule, message)


def has_provider_probe(provider_id: str, entry: Any = None) -> bool:
    """Can Main Branch confirm this provider's credential by calling it?

    ``entry`` is the connection's recorded entry. It matters only for
    `CONDITIONAL_PROBE_PROVIDERS`: `google` has a probe only when the entry
    records an OAuth grant. Without an entry the answer is the unconditional one.
    """
    if provider_id in PROBE_PROVIDERS:
        return True
    if provider_id in CONDITIONAL_PROBE_PROVIDERS:
        return _entry_records_slot(entry, GOOGLE_OAUTH_GRANT_SLOT)
    return False


def provider_needs_action(item: dict[str, Any]) -> bool:
    """Is there something the operator can actually do about this provider?

    Process exit codes answer this question rather than "is everything
    verified". A red that nobody can clear gets ignored, and a probe-less
    provider can never turn green until a probe exists upstream, so it warns
    without failing. Everything else that is not `ok` is actionable: run the
    test, replace the credential, or fix the backend.
    """
    if item.get("ok"):
        return False
    if item.get("state") == NOT_CHECKED_STATE:
        # Nothing is known to be wrong, so there is nothing to fix.
        return False
    if item.get("state") == UNVERIFIED_STATE:
        # A status item carries `has_probe`, computed from its entry, which is
        # what a conditional probe needs; a bare item falls back to the id.
        if "has_probe" in item:
            return bool(item["has_probe"])
        return has_provider_probe(str(item.get("provider") or ""))
    return True


def _provider_verified(validation: dict[str, Any]) -> bool:
    """Read the "a provider call confirmed this credential" fact, failing closed.

    Releases through 0.5.2 recorded ``state: ready`` for providers that were
    never probed, so an absent ``provider_verified`` key is not evidence of a
    successful provider call. Absent reads as unverified until `mb connect test`
    records the fact, which costs one re-test and never overclaims readiness.
    """
    return validation.get("provider_verified") is True


def _verified_at(validation: dict[str, Any]) -> str:
    """Timestamp of the last *successful* provider call, or "" if never.

    Preserved across a later failure: it records when the credential last
    worked, which stays true even when the current check fails.
    """
    return str(validation.get("verified_at") or "")


def _backend_repair(reason: str) -> dict[str, str]:
    """Sanitized summary/repair for a credential-backend reason code."""

    return backend_repair(reason)


KeychainError = CredentialStoreError
_select_secret_backend = select_secret_backend


def _shown_user_scope_path(path: Path) -> str:
    """The user-scope file as an operator sees it: ``~/...`` under the home folder."""

    with suppress(ValueError, RuntimeError):
        return f"~/{path.relative_to(Path.home())}"
    return str(path)


def _shell_repo_arg(repo: Path) -> str:
    """A ``--repo`` value to paste into a shell: ``~/...`` under the home folder."""

    with suppress(ValueError, RuntimeError):
        relative = repo.relative_to(Path.home())
        return "~" if relative == Path(".") else f"~/{shlex.quote(str(relative))}"
    return shlex.quote(str(repo))


def _shell_replay_command(command: list[str], repo: Path) -> str:
    """Show a replayable command without exposing an absolute home path."""

    parts = [shlex.quote(part) for part in command]
    parts[command.index("--repo") + 1] = _shell_repo_arg(repo)
    return " ".join(parts)


def _user_scope_write_failure(exc: OSError) -> tuple[str, str]:
    """What went wrong writing the user-scope file, and what to fix first.

    Built from the error number only, so no path, backend text or value
    from the exception reaches the operator.
    """

    if exc.errno in {errno.ENOSPC, errno.EDQUOT}:
        return "the disk is full", "Free some disk space"
    if exc.errno == errno.EROFS:
        return "its file system is read-only", "Make that file system writable"
    if isinstance(exc, PermissionError):
        folder = _shown_user_scope_path(_user_scope_path().parent)
        return f"permission to write in its folder {folder} was denied", "Make that folder writable"
    code = errno.errorcode.get(exc.errno or 0, "")
    cause = f"the file system reported an error ({code})" if code else "a file system error"
    return cause, "Check that disk and folder"


class UserScopeReadOnlyError(ConnectRefusal):
    """The user-scope file is read-only, so it was left as it is (rule ``user_scope_read_only``)."""

    def __init__(self, path: Path) -> None:
        shown = _shown_user_scope_path(path)
        self.shown = shown
        super().__init__(
            "user_scope_read_only",
            f"the user-scope connect file {shown} is read-only, so it was not changed. "
            "Make it writable or move it, then rerun the command. Nothing else was changed.",
        )


class ConfigBoundaryError(ValueError):
    """Raised when local connect metadata is outside the selected repo boundary."""


class MetadataWriteError(RuntimeError):
    """A credential was stored, but its metadata and rollback both failed."""


class UserScopeRecordRestoreError(OSError):
    """The user-scope write failed and the prior record could not be restored."""


class ConfigCorruptError(ValueError):
    """Raised when local connect metadata cannot be parsed safely.

    `file_path` and `problem` (what is wrong with it, as a short clause) are set
    for a file that holds the wrong thing, so `mb doctor` can name it instead of failing.
    """

    def __init__(
        self, message: str = "", *, file_path: Path | None = None, problem: str = ""
    ) -> None:
        super().__init__(message)
        self.file_path = file_path
        self.problem = problem


# Optional `google` slot holding one OAuth grant (client and refresh token) as
# a single credential-store item. Its presence makes the connection OAuth mode.
GOOGLE_OAUTH_GRANT_SLOT = "oauth_grant"
# Repo metadata key the sign-in writes: the Google products it granted.
GOOGLE_OAUTH_GRANTS_METADATA = "oauth_grants"
# The products a Google sign-in can grant, and the per-product outcomes a
# check records (`google_probe`); status shows only these.
GOOGLE_OAUTH_PRODUCTS: tuple[str, ...] = ("search_console", "ga4")
GOOGLE_PRODUCT_STATES = frozenset({"ok", "grant_missing", "unvalidated", "invalid", "not_checked"})
_GOOGLE_PRODUCT_RULE_RE = re.compile(r"[a-z][a-z0-9_]{0,63}")
# State a read records when Google refuses the stored grant (`invalid_grant`).
GOOGLE_REAUTH_REQUIRED_STATE = "reauth_required"


@dataclass(frozen=True)
class Provider:
    """Provider registry entry.

    ``required_secrets`` names are local credential slots, not values. They are
    safe to write into repo metadata because actual secret material is stored
    through ``SecretStore``. ``optional_secrets`` are slots a connection may
    record; status reports one only when the entry records it, and a missing
    optional slot never makes a connection ``missing_secret``.
    """

    id: str
    name: str
    category: str
    auth: str
    required_secrets: tuple[str, ...]
    metadata_fields: tuple[str, ...]
    description: str
    env_vars: tuple[str, ...] = ()
    # Expected prefixes for the primary secret. Empty = no shape check.
    # Used to refuse malformed credentials at intake without ever echoing
    # the value itself.
    key_prefixes: tuple[str, ...] = ()
    optional_secrets: tuple[str, ...] = ()


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        id="google",
        name="Google",
        category="workspace",
        auth="oauth_or_service_account",
        required_secrets=("access_token",),
        metadata_fields=("account_email", "workspace"),
        description="Google Workspace, Drive, Docs, Sheets, Slides, and future analytics sync.",
        env_vars=("GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_OAUTH_TOKEN"),
        optional_secrets=(GOOGLE_OAUTH_GRANT_SLOT,),
    ),
    Provider(
        id="meta",
        name="Meta",
        category="ads",
        auth="meta_ads_cli_read_only",
        required_secrets=("access_token",),
        metadata_fields=("ad_account_id", "business_id", "page_id", "pixel_id"),
        description=(
            "Meta Ads account access through Meta's official Ads CLI, with local "
            "credential storage and read-only account smoke before skills use live facts."
        ),
        env_vars=("ACCESS_TOKEN", "META_ACCESS_TOKEN"),
    ),
    Provider(
        id="cloudflare",
        name="Cloudflare",
        category="site",
        auth="api_token",
        required_secrets=("api_token",),
        metadata_fields=("account_id", "zone_id"),
        description="Cloudflare Pages, DNS, Workers, and deployment metadata.",
        env_vars=("CLOUDFLARE_API_TOKEN",),
    ),
    Provider(
        id="stripe",
        name="Stripe",
        category="payments",
        auth="api_key",
        required_secrets=("api_key",),
        metadata_fields=("account_id", "mode"),
        description=(
            "Stripe payments: checkout, products, customers, and webhook "
            "configuration. Store the secret or restricted key locally; keys "
            "never enter chat or committed repo files. Record `mode` metadata "
            "(test or live) so agents can verify the key matches the intent."
        ),
        env_vars=("STRIPE_SECRET_KEY", "STRIPE_API_KEY"),
        key_prefixes=("sk_", "rk_"),
    ),
    Provider(
        id="resend",
        name="Resend",
        category="email",
        auth="api_key",
        required_secrets=("api_key",),
        metadata_fields=("sender_domain", "audience_id"),
        description=(
            "Resend transactional and lifecycle email: sending, domains, and "
            "audiences. The sender domain lives in metadata so agents read "
            "identity from recorded facts instead of live provider state."
        ),
        env_vars=("RESEND_API_KEY",),
        key_prefixes=("re_",),
    ),
    Provider(
        id="postiz",
        name="Postiz",
        category="social",
        auth="api_key",
        required_secrets=("api_key",),
        metadata_fields=("workspace",),
        description="Postiz social scheduling and publishing workflows.",
        env_vars=("POSTIZ_API_KEY",),
    ),
    Provider(
        id="apify",
        name="Apify",
        category="research",
        auth="api_token",
        required_secrets=("api_token",),
        metadata_fields=("default_actor",),
        description="Apify research actors and scrape jobs.",
        env_vars=("APIFY_TOKEN",),
    ),
    Provider(
        id="github",
        name="GitHub",
        category="work",
        auth="api_token",
        # `api_key` matches the slot a GitHub token connected with `--custom`
        # before this entry existed already uses, so those keep resolving.
        required_secrets=("api_key",),
        metadata_fields=("owner",),
        description=(
            "A GitHub token for scripts and agents that call the GitHub API directly. "
            "Day-to-day issue and pull request work still goes through `gh`."
        ),
        env_vars=("GITHUB_TOKEN", "GH_TOKEN"),
    ),
    Provider(
        id="ga4",
        name="Google Analytics 4",
        category="analytics",
        auth="oauth_access_token",
        required_secrets=("access_token",),
        metadata_fields=("property_id",),
        description=(
            "Read access to one Google Analytics 4 property. Record the numeric "
            "`property_id` so the probe knows which property to check."
        ),
    ),
    Provider(
        id="hledger",
        name="hledger",
        category="finance",
        auth="local_file",
        required_secrets=(),
        metadata_fields=("journal_path", "vault_path"),
        description=(
            "Local hledger journal metadata for the private books vault. "
            "`core/finance/books.md` is the source of truth for storage mode; "
            "real ledgers stay outside the tracked business repo."
        ),
    ),
    Provider(
        id="transcription",
        name="Whisper / transcription",
        category="media",
        auth="api_key_or_local",
        required_secrets=("api_key",),
        metadata_fields=("engine", "model"),
        description="Whisper-compatible transcription provider or local transcription engine.",
        env_vars=("OPENAI_API_KEY", "WHISPER_API_KEY"),
    ),
)

PROVIDER_GUIDANCE: dict[str, dict[str, Any]] = {
    "github": {
        "priority": 1,
        "why": (
            "GitHub is the task, proposal, review, and shipped-work layer for the business repo."
        ),
        "use_when": (
            "Use for daily task tracking, public issue drafts, pull requests, reviews, "
            "and team visibility."
        ),
        "defer_when": (
            "You can start solo local setup without it, but issue, proposal, and team "
            "loops will be limited."
        ),
        "status_command": "mb connect doctor --json",
    },
    "cloudflare": {
        "priority": 2,
        "why": (
            "Cloudflare is the default low-lock-in rail for sites, DNS, Pages, and future Workers."
        ),
        "use_when": (
            "Use when the business needs a landing page, custom domain, deploy, or DNS check."
        ),
        "defer_when": "Defer until you are ready to publish or connect a domain.",
        "status_command": "mb connect doctor --json",
    },
    "google": {
        "priority": 3,
        "why": (
            "Google/Workspace is the bridge for existing Docs, Sheets, Drive, and workspace assets."
        ),
        "use_when": (
            "Use when the business has source material in Google Drive or needs "
            "spreadsheet/docs context."
        ),
        "defer_when": (
            "Do not connect it just because a Google account exists; connect it when "
            "a workflow needs it."
        ),
        "status_command": "mb connect doctor --json",
    },
    "meta": {
        "priority": 4,
        "why": (
            "Meta Ads readiness lets ad workflows use account, campaign, insights, "
            "creative, and pixel context through Meta's official Ads CLI."
        ),
        "use_when": (
            "Use when the business is generating, reviewing, or learning from Meta/Facebook ads. "
            "Main Branch stores the token outside the repo and only treats live account "
            "access as ready after read-only CLI smoke passes."
        ),
        "defer_when": (
            "Defer for organic, research, or site work that does not need ad-account facts."
        ),
        "status_command": "mb connect doctor --json",
    },
    "apify": {
        "priority": 5,
        "why": (
            "Apify is the optional research sidecar for scraping, YouTube, Instagram, "
            "and web mining."
        ),
        "use_when": (
            "Use when research or organic workflows need structured external data collection."
        ),
        "defer_when": "Defer for first-pass reference setup or local-only thinking.",
        "status_command": "mb connect doctor --json",
    },
}

META_SETUP_REQUIREMENTS = (
    "Meta Business Portfolio / Business Manager access",
    "An ad account assigned to the user or system user",
    "The Business portfolio ID from Meta business info when available",
    "A Meta developer app selected during token generation",
    "A system user token or individual user token with assigned assets",
    "Possible second-admin approval in stricter Business Manager setups",
)

META_TOKEN_SCOPES = (
    "business_management",
    "ads_management",
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_ads",
    "catalog_management",
    "read_insights",
)

META_READ_SMOKE_COMMANDS: tuple[tuple[str, list[str], bool], ...] = (
    ("adaccount_list", ["meta", "-o", "json", "ads", "adaccount", "list"], False),
    ("campaign_list", ["meta", "-o", "json", "ads", "campaign", "list"], False),
    (
        "insights_get",
        [
            "meta",
            "-o",
            "json",
            "ads",
            "insights",
            "get",
            "--fields",
            "spend,impressions,clicks,ctr,cpc",
        ],
        False,
    ),
    ("dataset_list", ["meta", "-o", "json", "ads", "dataset", "list"], True),
)


def provider_map() -> dict[str, Provider]:
    return {provider.id: provider for provider in PROVIDERS}


def provider_registry() -> list[dict[str, Any]]:
    return [
        {
            "id": provider.id,
            "name": provider.name,
            "category": provider.category,
            "auth": provider.auth,
            "required_secrets": list(provider.required_secrets),
            "metadata_fields": list(provider.metadata_fields),
            "description": provider.description,
            "env_vars": list(provider.env_vars),
        }
        for provider in PROVIDERS
    ]


CUSTOM_PROVIDER_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
CUSTOM_IDENTITY_METADATA_ORDER = (
    "role",
    "access_level",
    "data_domain",
    "auth_state",
    "environment",
    "source_system",
    "account_ref",
    "workspace",
    "tenant_id",
)


def _custom_provider(provider_id: str) -> Provider:
    """Synthesize a registry entry for an operator-named provider.

    Custom providers ride every existing rail (SecretStore, user scope,
    `mb connect token`, status) with a single `api_key` secret slot.
    """
    return Provider(
        id=provider_id,
        name=provider_id,
        category="custom",
        auth="api_key",
        required_secrets=("api_key",),
        metadata_fields=(),
        description="Operator-defined custom provider.",
    )


def normalize_provider(provider_id: str, *, allow_custom: bool = False) -> Provider:
    key = provider_id.strip().lower().replace("_", "-")
    aliases = {"whisper": "transcription", "cloudflare-pages": "cloudflare"}
    key = aliases.get(key, key)
    providers = provider_map()
    if key in providers:
        return providers[key]
    if allow_custom:
        if not CUSTOM_PROVIDER_RE.fullmatch(key):
            raise ValueError(
                f"custom provider id {quoted_input(provider_id)} must be 2-31 chars of "
                "lowercase letters, digits, and hyphens"
            )
        return _custom_provider(key)
    supported = ", ".join(sorted(providers))
    raise ValueError(
        f"unknown provider {quoted_input(provider_id)}; supported providers: {supported}. "
        "For an operator-defined provider, rerun with --custom."
    )


def _is_custom_provider_id(provider_id: str) -> bool:
    key = provider_id.strip().lower().replace("_", "-")
    return key not in provider_map() and bool(CUSTOM_PROVIDER_RE.fullmatch(key))


def _connect_command(provider: Provider, *, token_stdin: bool = False) -> str:
    custom_flag = " --custom" if provider.category == "custom" else ""
    token_flag = " --token-stdin" if token_stdin else ""
    return f"mb connect {provider.id}{custom_flag}{token_flag}"


GOOGLE_SIGN_IN_COMMAND = "mb connect google --oauth"


def _reconnect_command(
    provider: Provider, entry: Any = None, *, grant_readable: bool = True
) -> str:
    """The next step that stores (or replaces) a provider's credential.

    Google's names the sign-in: ``--oauth`` with no connection, ``--oauth
    --reauth`` on a sign-in entry whose stored grant (and so its OAuth client)
    can be read, and ``--oauth --reauth --client-file ...`` when it cannot,
    since ``--reauth`` alone is then refused. Only a legacy access-token entry
    keeps ``--token-stdin``, the one path that replaces that token in place.
    """

    if provider.id != "google":
        return _connect_command(provider, token_stdin=True)
    if _entry_records_slot(entry, GOOGLE_OAUTH_GRANT_SLOT):
        from mb import google_connect

        if grant_readable:
            return google_connect.REAUTH_COMMAND
        return google_connect.REAUTH_WITH_CLIENT_COMMAND
    if _entry_records_slot(entry, "access_token"):
        return _connect_command(provider, token_stdin=True)
    return GOOGLE_SIGN_IN_COMMAND


def _reconnect_step(provider: Provider, google_sign_in: bool) -> str:
    """The sentence tail for rotate's "reconnect" advice; Google's is a sign-in."""

    if google_sign_in:
        return f"sign in with `{GOOGLE_SIGN_IN_COMMAND}`"
    return f"reconnect with `{_connect_command(provider, token_stdin=True)}`"


def _safe_identity_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    """Return custom-provider metadata safe enough for identity diagnostics.

    The output is still operator-facing (`safe_to_share: false`), but this
    avoids echoing hand-edited secret-like metadata keys if a repo config is
    malformed.
    """

    recorded: dict[str, str] = {}
    for key in CUSTOM_IDENTITY_METADATA_ORDER:
        value = metadata.get(key)
        if value is not None and value != "":
            recorded[key] = str(value)
    for raw_key, value in metadata.items():
        key = str(raw_key)
        lowered = key.lower().replace("-", "_")
        if key in recorded or value is None or value == "":
            continue
        if metadata_value_rule(str(value)) or metadata_value_rule(key):
            continue
        if lowered not in SAFE_METADATA_KEYS and any(
            part in lowered for part in SENSITIVE_KEY_PARTS
        ):
            continue
        recorded[key] = str(value)
    return recorded


def _metadata_key_looks_sensitive(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return lowered not in SAFE_METADATA_KEYS and any(
        part in lowered for part in SENSITIVE_KEY_PARTS
    )


def _safe_status_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    """Filter hand-edited metadata before it enters safe-to-share status JSON."""
    recorded: dict[str, str] = {}
    for raw_key, raw_value in metadata.items():
        key = str(raw_key)
        if raw_value is None or raw_value == "":
            continue
        value = str(raw_value)
        # A key that is itself secret-shaped is dropped like a secret value:
        # this output is marked safe to share.
        if metadata_value_rule(value) or metadata_value_rule(key):
            continue
        if key.lower().replace("-", "_") not in SAFE_METADATA_KEYS:
            flagged, _reason = _classify_credential_value(key, value)
            if flagged or _metadata_key_looks_sensitive(key):
                continue
        recorded[key] = value
    return recorded


def _safe_status_label(value: Any) -> str:
    label = str(value or "")
    flagged, _reason = _classify_credential_value("account_label", label)
    return SECRET_REPLACEMENT if flagged else label


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _home() -> Path:
    return Path(os.environ.get("MAINBRANCH_HOME", Path.home() / ".mainbranch")).expanduser()


def _config_path(repo: Path) -> Path:
    return repo / CONFIG_RELATIVE_PATH


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _checked_config_path(repo: Path) -> Path:
    root = repo.resolve()
    path = _config_path(root)
    config_dir = path.parent

    if config_dir.is_symlink() or path.is_symlink():
        raise ConfigBoundaryError(
            "Refusing to use .mb/connect.yaml because the local state path is a symlink."
        )
    if config_dir.exists() and not config_dir.is_dir():
        raise ConfigBoundaryError(
            "Refusing to use .mb/connect.yaml because the local state directory is invalid."
        )

    parent_resolved = config_dir.resolve(strict=False)
    path_resolved = path.resolve(strict=False)
    if not _is_within(parent_resolved, root) or not _is_within(path_resolved, root):
        raise ConfigBoundaryError(
            "Refusing to use .mb/connect.yaml because it is outside the selected repo boundary."
        )
    return path


def _empty_config() -> dict[str, Any]:
    return {"version": 1, "repo_id": "", "repo_identity": {}, "providers": {}}


def _read_config(repo: Path) -> dict[str, Any]:
    path = _checked_config_path(repo)
    if not path.exists():
        return _empty_config()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigCorruptError(
            "Refusing to update .mb/connect.yaml because it is unreadable or invalid YAML. "
            "Fix or move the file, then rerun the command.",
            file_path=path,
            problem="it is not valid YAML",
        ) from exc
    if not isinstance(raw, dict):
        raise ConfigCorruptError(
            "Refusing to update .mb/connect.yaml because it does not contain a YAML object. "
            "Fix or move the file, then rerun the command.",
            file_path=path,
            problem="it does not contain a YAML object",
        )
    providers = raw.get("providers")
    if not isinstance(providers, dict):
        providers = {}
    try:
        version = int(raw.get("version") or 1)
    except (TypeError, ValueError):
        version = 1
    return {
        "version": version,
        "repo_id": str(raw.get("repo_id") or ""),
        "repo_identity": raw.get("repo_identity")
        if isinstance(raw.get("repo_identity"), dict)
        else {},
        "providers": providers,
    }


def _git_output(repo: Path, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _normalized_remote(value: str) -> str:
    remote = value.strip()
    if remote.startswith("git@") and ":" in remote:
        host, path = remote.removeprefix("git@").split(":", 1)
        return f"https://{host}/{path}".removesuffix(".git")
    parsed = urllib.parse.urlparse(remote)
    if parsed.scheme and parsed.netloc:
        host = parsed.hostname or parsed.netloc
        path = parsed.path.lstrip("/")
        if path:
            return f"https://{host}/{path}".removesuffix(".git")
    return remote.removesuffix(".git")


def _github_repo_full_name(remote: str) -> str:
    normalized = _normalized_remote(remote)
    parsed = urllib.parse.urlparse(normalized)
    if parsed.hostname != "github.com":
        return ""
    path = parsed.path.strip("/")
    if path.count("/") < 1:
        return ""
    owner, repo_name, *_ = path.split("/")
    return f"{owner}/{repo_name.removesuffix('.git')}" if owner and repo_name else ""


def _repo_identity(repo: Path) -> dict[str, str]:
    remote = _git_output(repo, ["config", "--get", "remote.origin.url"])
    if remote:
        source = "git_remote"
        basis = _normalized_remote(remote)
    else:
        common_dir = _git_output(repo, ["rev-parse", "--git-common-dir"])
        if common_dir:
            source = "git_common_dir"
            basis = str(
                (repo / common_dir).resolve()
                if not Path(common_dir).is_absolute()
                else Path(common_dir).resolve()
            )
        else:
            source = "path"
            basis = str(repo.resolve())
    digest = hashlib.sha256(f"mainbranch-connect-v2:{source}:{basis}".encode()).hexdigest()
    return {"source": source, "repo_id": digest[:32], "basis_sha256": digest}


def _ensure_repo_id(config: dict[str, Any], repo: Path) -> str:
    identity = _repo_identity(repo)
    existing = str(config.get("repo_id") or "").strip()
    repo_id = existing or identity["repo_id"]
    config["repo_id"] = repo_id
    config["repo_identity"] = {
        "source": identity["source"],
        "basis_sha256": identity["basis_sha256"],
        "repo_id_source": "existing_config" if existing else identity["source"],
    }
    return repo_id


def _write_config(repo: Path, config: dict[str, Any]) -> Path:
    path = _checked_config_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Re-check after creating .mb so a swapped local-state path cannot escape the repo.
    path = _checked_config_path(repo)
    text = yaml.safe_dump(config, sort_keys=False)
    atomic_write_text(path, text)
    return path


def config_tracked_by_git(repo: Path) -> bool:
    """Is ``.mb/connect.yaml`` tracked by git in ``repo``?

    Business repos ignore it, but an older or hand-made repo may track it.
    Automatic recordings (a read's ``reauth_required``, a check's outcome)
    skip a tracked file, so nothing leaves it modified without a person asking.
    When git cannot answer (missing, a timeout, an error such as dubious
    ownership) inside a git checkout, the file counts as tracked.
    """

    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"}
    }
    try:
        completed = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", CONFIG_RELATIVE_PATH.as_posix()],
            cwd=str(repo),
            env=env,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return _inside_git_checkout(repo)
    if completed.returncode in {0, 1}:
        return completed.returncode == 0
    return _inside_git_checkout(repo)


def _inside_git_checkout(repo: Path) -> bool:
    """Does ``repo`` or an ancestor hold a ``.git`` (directory or worktree file)?"""

    try:
        start = repo.resolve()
    except (OSError, RuntimeError):
        start = repo
    for directory in (start, *start.parents):
        with suppress(OSError):
            if (directory / ".git").exists():
                return True
    return False


def _user_scope_path() -> Path:
    return _home() / USER_SCOPE_RELATIVE_PATH


def _empty_user_scope() -> dict[str, Any]:
    return {"version": 1, "repos": {}}


def _read_user_scope() -> dict[str, Any]:
    path = _user_scope_path()
    if not path.exists():
        return _empty_user_scope()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, yaml.YAMLError) as exc:
        # ValueError covers bytes that are not UTF-8 (UnicodeDecodeError).
        raise ConfigCorruptError(
            "Refusing to update connect user-scope metadata because it is unreadable or "
            "invalid YAML. Fix or move the file, then rerun the command.",
            file_path=path,
            problem="it is not valid YAML",
        ) from exc
    if not isinstance(raw, dict):
        raise ConfigCorruptError(
            "Refusing to update connect user-scope metadata because it does not contain a YAML "
            "object. Fix or move the file, then rerun the command.",
            file_path=path,
            problem="it does not contain a YAML object",
        )
    repos = raw.get("repos")
    if not isinstance(repos, dict):
        repos = {}
    try:
        version = int(raw.get("version") or 1)
    except (TypeError, ValueError):
        version = 1
    # Keys this module does not own come back as they were, so a rewrite keeps them.
    data = dict(raw)
    data["version"] = version
    data["repos"] = repos
    return data


def _ensure_user_scope_writable() -> None:
    """Refuse when mode bits or the OS deny writing the user-scope file.

    Call it before storing a credential that a user-scope entry will record,
    so a refusal leaves the credential store unchanged.
    """

    path = _user_scope_path()
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return
    if not mode & stat.S_IWUSR:
        raise UserScopeReadOnlyError(path)
    # No truncation or creation: ask the OS about ownership and ACLs too.
    # A stat denial is a folder access error, while an open denial on an
    # existing writable file means the file itself is protected.
    try:
        fd = os.open(path, os.O_WRONLY)
        os.close(fd)
    except PermissionError:
        raise UserScopeReadOnlyError(path) from None


def _write_user_scope(data: dict[str, Any]) -> Path:
    """Rewrite the user-scope file (YAML comments are not kept).

    A read-only file is left alone: it is neither made
    writable nor replaced.
    """

    path = _user_scope_path()
    _ensure_user_scope_writable()
    previous = path.read_bytes() if path.exists() else None
    previous_mode = path.stat().st_mode & 0o777 if previous is not None else None
    path.parent.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        path.parent.chmod(0o700)
    try:
        atomic_write_text(path, yaml.safe_dump(data, sort_keys=False), mode=0o600)
    except OSError as exc:
        # Normally the replace is the final operation. Restore as well if a
        # writer reports an error after replacing the record.
        try:
            current = path.read_bytes() if path.exists() else None
            current_mode = path.stat().st_mode & 0o777 if current is not None else None
            if (current, current_mode) != (previous, previous_mode):
                if previous is None:
                    path.unlink()
                else:
                    atomic_write_text(path, previous.decode("utf-8"), mode=previous_mode)
        except OSError:
            raise UserScopeRecordRestoreError("user-scope record restore failed") from None
        if (
            isinstance(exc, PermissionError)
            and previous is not None
            and os.access(path.parent, os.W_OK | os.X_OK)
        ):
            # The folder lets us in, so the file is what refused. A closed folder
            # re-raises, and `_user_scope_write_failure` names it.
            raise UserScopeReadOnlyError(path) from None
        raise
    return path


def _user_scope_provider_entry(repo_id: str, provider_id: str) -> dict[str, Any] | None:
    data = _read_user_scope()
    raw_repo = data["repos"].get(repo_id)
    repo_entry = raw_repo if isinstance(raw_repo, dict) else {}
    providers = repo_entry.get("providers") if isinstance(repo_entry.get("providers"), dict) else {}
    raw_entry = providers.get(provider_id) if isinstance(providers, dict) else None
    return raw_entry if isinstance(raw_entry, dict) else None


def _write_user_scope_provider(
    repo_id: str,
    *,
    repo_identity: dict[str, Any],
    provider_id: str,
    entry: dict[str, Any],
) -> Path:
    data = _read_user_scope()
    raw_repos = data.get("repos")
    repos: dict[str, Any] = raw_repos if isinstance(raw_repos, dict) else {}
    data["repos"] = repos
    raw_repo = repos.get(repo_id)
    repo_entry = raw_repo if isinstance(raw_repo, dict) else {}
    raw_providers = repo_entry.get("providers")
    providers: dict[str, Any] = raw_providers if isinstance(raw_providers, dict) else {}
    repo_entry["repo_identity"] = repo_identity
    repo_entry["updated_at"] = _now()
    repo_entry["providers"] = providers
    providers[provider_id] = entry
    repos[repo_id] = repo_entry
    return _write_user_scope(data)


def _snapshot_conclusive(previous: SecretProbe) -> bool:
    """True when the snapshot says the item is present or definitely absent.

    A read that was refused, timed out or never happened (``not_checked``) says
    nothing about what the item holds, so nothing may be written over it.
    """

    return previous.backend_ok and not previous.not_checked


def _restore_secret(store: SecretStore, ref: str, previous: SecretProbe, written: str) -> bool:
    """Put a credential back as it was (or remove the one just created).

    Recovery gets its own bounded attempt even if the original command has
    exhausted its credential deadline. Never exposes backend exception text or
    credential values: it only says whether the restore worked. A credential
    that was absent before is deleted only if it still holds exactly the value
    this command wrote; anything else is another writer's and stays.
    """

    try:
        if previous.present:
            store.set(ref, previous.value, deadline=new_credential_deadline())
            return True
        if not _snapshot_conclusive(previous):
            return False
        current = store.probe(ref, deadline=new_credential_deadline())
        if not current.backend_ok or current.not_checked:
            return False
        if not current.present:
            return True
        if not hmac.compare_digest(current.value.encode(), written.encode()):
            return False
        store.delete(ref)
    except Exception:
        return False
    return True


def _restore_secrets(
    store: SecretStore, snapshots: list[tuple[str, str, SecretProbe, str]]
) -> list[str]:
    """Put each ``(label, ref, previous, written)`` credential back.

    Returns the labels that stayed changed. Every slot gets its own attempt: one
    failed restore must not skip the next.
    ``written`` is the value this command stored, used to prove a new item is its own.
    """

    return [
        label
        for label, ref, previous, written in snapshots
        if not _restore_secret(store, ref, previous, written)
    ]


def _user_scope_record_failure(exc: Exception) -> tuple[str, str, str]:
    """The file as shown, what went wrong with it, and what to fix first.

    Shared by every command that stores a credential and then records it in
    the user-scope file. Built from the error number only: no path, backend
    text or value from the exception reaches the operator.
    """

    if isinstance(exc, UserScopeReadOnlyError):
        return exc.shown, "is read-only", "Make that file writable"
    shown = _shown_user_scope_path(_user_scope_path())
    if isinstance(exc, ConfigCorruptError):
        return shown, "is unreadable or invalid YAML", "Fix or move that file"
    if isinstance(exc, UserScopeRecordRestoreError):
        return (
            shown,
            "could not be written, and its previous contents could not be restored",
            "Inspect and repair that file",
        )
    assert isinstance(exc, OSError)
    reason, fix = _user_scope_write_failure(exc)
    return shown, f"could not be written: {reason}", fix


def _drop_user_scope_metadata_only(repo_id: str, provider_id: str) -> bool:
    """Remove this repo's user-scope entry for a provider when it holds no credential.

    Best effort, for a first sign-in recorded in repo scope over a
    ``--metadata``-only user-scope entry: the repo entry now carries that
    metadata. An entry that records any secret ref is never touched.
    """

    try:
        data = _read_user_scope()
    except ConfigCorruptError:
        return False
    repo_entry = data["repos"].get(repo_id)
    providers = repo_entry.get("providers") if isinstance(repo_entry, dict) else None
    entry = providers.get(provider_id) if isinstance(providers, dict) else None
    if not isinstance(providers, dict) or not isinstance(entry, dict):
        return False
    raw_secrets = entry.get("secrets")
    secrets = raw_secrets if isinstance(raw_secrets, dict) else {}
    if any(isinstance(slot, dict) and slot.get("ref") for slot in secrets.values()):
        return False
    del providers[provider_id]
    try:
        _write_user_scope(data)
    except (OSError, UserScopeReadOnlyError):
        return False
    return True


def _secret_ref(repo_id: str, provider_id: str, field: str) -> str:
    digest = hashlib.sha256(f"{repo_id}:{provider_id}:{field}".encode()).hexdigest()[:24]
    return f"mainbranch://{digest}/{provider_id}/{field}"


def _unverified_repair(provider: Provider) -> dict[str, str]:
    """Guidance for a stored credential no provider call has confirmed.

    Split on whether a probe exists, so guidance matches the exit code: a
    provider that exits 1 always names something to run, and a provider that
    exits 0 never sends the operator after a fix that cannot work.
    """
    if has_provider_probe(provider.id):
        # Reachable through metadata that recorded readiness without recording
        # a provider call. Running the probe is a real next step.
        return {
            "summary": (
                f"{provider.name} has a stored credential whose readiness was recorded "
                "without a provider call."
            ),
            "repair": f"Run `mb connect test {provider.id}` to confirm it with the provider.",
            "repair_command": f"mb connect test {provider.id}",
        }
    # No probe exists, so rerunning `mb connect test` would record the same
    # unverified result. Pointing at it would be busywork dressed as a fix.
    return {
        "summary": (
            f"{provider.name} has a stored credential, but Main Branch has no "
            "automated way to confirm it works with the provider."
        ),
        "repair": (
            f"Confirm the {provider.name} credential in the provider's own dashboard, "
            "or treat the first real workflow run as the check."
        ),
        "repair_command": "",
    }


def _not_checked_repair(provider: Provider) -> dict[str, str]:
    """Guidance for a credential an aggregate command did not get to read.

    Not a repair: nothing is known to be wrong. The one useful step is a
    single-provider status, which has its own credential budget.
    """

    command = f"mb connect status {provider.id}"
    return {
        "summary": (
            f"{provider.name} credential not checked: this command ran out of its "
            "credential-read time before reaching it. Nothing is known to be wrong."
        ),
        "repair": (
            f"Nothing to repair. Run `{command}` to check this one credential on its own; "
            f"`mb connect exec {provider.id}` reads it the same way."
        ),
        "repair_command": command,
    }


def _google_grant_repair(*, gone: bool, readable: bool) -> dict[str, str]:
    """Status's next step when the recorded Google sign-in grant cannot mint a token."""

    from mb import google_connect

    command = (
        google_connect.REAUTH_COMMAND if readable else google_connect.REAUTH_WITH_CLIENT_COMMAND
    )
    what = "is missing from the credential store" if gone else "is unreadable or incomplete"
    return {
        "summary": f"The stored Google sign-in {what}; a person must sign in again.",
        "repair": f"Run `{command}` in a terminal (a person, not an agent).",
        "repair_command": command,
    }


def _repair(
    provider: Provider,
    state: str,
    missing: list[str] | None = None,
    validation: dict[str, Any] | None = None,
    backend_reason: str = "",
    entry: Any = None,
    secrets: dict[str, Any] | None = None,
) -> dict[str, str]:
    if state == BACKEND_FAILURE_STATE:
        # Wins over every provider-level repair: reconnecting a provider
        # cannot succeed while the credential backend itself is unhealthy.
        detail = _backend_repair(backend_reason)
        return {
            "summary": (
                f"{provider.name} credentials cannot be read. {detail['summary']} "
                "The stored metadata is intact."
            ),
            "repair": detail["repair"],
            "repair_command": detail["repair_command"],
        }
    if state == NOT_CHECKED_STATE:
        return _not_checked_repair(provider)
    validation = validation or {}
    validation_repair = str(validation.get("repair") or "")
    validation_repair_command = str(validation.get("repair_command") or "")
    # `--reauth` reads the OAuth client from the stored grant; when the grant
    # cannot be read, the command must carry the client file or it is refused.
    raw_grant = (secrets or {}).get(GOOGLE_OAUTH_GRANT_SLOT)
    grant_readable = not isinstance(raw_grant, dict) or (
        raw_grant.get("present") is True and raw_grant.get("readable") is True
    )
    if (
        _records_oauth_grant(provider, entry)
        and isinstance(raw_grant, dict)
        and raw_grant.get("usable") is not True
    ):
        # A grant that is gone or cannot mint decides the next step before
        # any recorded check, by the rule `mb connect test google` uses.
        return _google_grant_repair(gone=raw_grant.get("present") is False, readable=grant_readable)
    validation_summary = str(validation.get("summary") or "")
    if validation_repair or validation_repair_command:
        return {
            "summary": validation_summary or f"{provider.name} needs metadata repair.",
            "repair": validation_repair,
            "repair_command": validation_repair_command,
        }
    if state == UNVERIFIED_STATE:
        # Ahead of the Meta special-case: `_meta_repair` has no answer for this
        # state, and `_unverified_repair` is already probe-aware, so Meta gets
        # "run `mb connect test meta`" rather than a generic fallback.
        return _unverified_repair(provider)
    if provider.id == "meta":
        return _meta_repair(state, missing)
    missing_fields = ", ".join(missing or provider.required_secrets)
    connect_command = _reconnect_command(provider, entry, grant_readable=grant_readable)
    if state == "not_connected":
        if provider.required_secrets:
            return {
                "summary": f"{provider.name} is not connected.",
                "repair": f"Run `{connect_command}` to store the credential outside the repo.",
                "repair_command": connect_command,
            }
        return {
            "summary": f"{provider.name} metadata is not connected.",
            "repair": f"Run `mb connect {provider.id}` with the needed metadata.",
            "repair_command": f"mb connect {provider.id}",
        }
    if state == "missing_secret":
        return {
            "summary": f"{provider.name} metadata exists, but local secret material is missing.",
            "repair": (
                f"Run `{connect_command}` to replace the missing credential ({missing_fields})."
            ),
            "repair_command": connect_command,
        }
    if state == "unvalidated":
        return {
            "summary": f"{provider.name} has stored credentials, but they have not been validated.",
            "repair": f"Run `mb connect test {provider.id}`.",
            "repair_command": f"mb connect test {provider.id}",
        }
    if state == "invalid":
        return {
            "summary": f"{provider.name} validation failed without exposing the provider response.",
            "repair": (
                f"Run `{connect_command}` to replace the credential, then "
                f"`mb connect test {provider.id}`."
            ),
            "repair_command": connect_command,
        }
    return {
        "summary": f"{provider.name} is ready.",
        "repair": "",
        "repair_command": "",
    }


def _meta_repair(state: str, missing: list[str] | None = None) -> dict[str, str]:
    connect_command = "mb connect meta --token-stdin --metadata ad_account_id=<act_id>"
    install_command = "pipx install --python <python3.12-or-newer> meta-ads"
    if state == "wrong_python":
        return {
            "summary": "Meta Ads CLI requires Python 3.12 or newer.",
            "repair": (
                "Install Python 3.12+, then install Meta's official Ads CLI with "
                f"`{install_command}`."
            ),
            "repair_command": install_command,
        }
    if state == "missing_cli":
        return {
            "summary": "Meta Ads CLI is not installed or `meta --version` failed.",
            "repair": (
                "Install Meta's official Ads CLI with Python 3.12+, then rerun "
                "`mb connect test meta`."
            ),
            "repair_command": install_command,
        }
    if state == "not_connected":
        return {
            "summary": "Meta Ads is not connected.",
            "repair": (
                "Prepare the Meta Business Portfolio, ad account, app, assigned assets, "
                f"and token, then run `{connect_command}`."
            ),
            "repair_command": connect_command,
        }
    if state == "missing_secret":
        missing_fields = ", ".join(missing or ("access_token",))
        return {
            "summary": "Meta Ads metadata exists, but local token material is missing.",
            "repair": (
                f"Run `{connect_command}` to replace the missing credential ({missing_fields})."
            ),
            "repair_command": connect_command,
        }
    if state == "missing_metadata":
        return {
            "summary": "Meta Ads needs non-secret `ad_account_id` metadata before validation.",
            "repair": (
                "Run `mb connect meta --metadata ad_account_id=<act_id>`, then "
                "`mb connect test meta`."
            ),
            "repair_command": "mb connect meta --metadata ad_account_id=<act_id>",
        }
    if state == "unvalidated":
        return {
            "summary": "Meta Ads has local setup metadata, but read-only smoke has not passed.",
            "repair": "Run `mb connect test meta`.",
            "repair_command": "mb connect test meta",
        }
    if state == "waiting_for_admin_approval":
        return {
            "summary": "Meta needs another business admin to approve this connection.",
            "repair": (
                "Meta needs another business admin to approve this connection. "
                "Nothing is broken locally."
            ),
            "repair_command": "",
        }
    if state == "auth_failed":
        return {
            "summary": "Meta Ads auth did not pass.",
            "repair": (
                "Check token scopes, app, system user, assigned assets, and ad account "
                "metadata, then rerun `mb connect test meta`."
            ),
            "repair_command": "mb connect test meta",
        }
    if state == "read_smoke_failed":
        return {
            "summary": "Meta Ads auth passed, but read-only account smoke failed.",
            "repair": (
                "Check ad account access and token scopes, then rerun `mb connect test meta`."
            ),
            "repair_command": "mb connect test meta",
        }
    return {
        "summary": "Meta Ads read-only account context is ready.",
        "repair": "",
        "repair_command": "",
    }


# Public credential grammars, one per provider family: the prefix plus the
# shape of the generated part. Each is matched in full, so a word that merely
# shares a prefix ("re_engagement", "pk_test_publishable") is not a key, and a
# real-shaped key is caught whatever its characters ("ghp_" plus lowercase).
# The rule name keeps the prefix so a refusal says which family matched.
METADATA_SECRET_GRAMMARS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sk_", re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{8,}")),
    ("rk_", re.compile(r"rk_(?:live|test)_[A-Za-z0-9]{8,}")),
    ("pk_live_", re.compile(r"pk_live_[A-Za-z0-9]{8,}")),
    ("whsec_", re.compile(r"whsec_[A-Za-z0-9+/=]{16,}")),
    ("re_", re.compile(r"re_[A-Za-z0-9]{8}_[A-Za-z0-9]{16,}")),
    ("sk-", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("ghp_", re.compile(r"ghp_[A-Za-z0-9]{30,}")),
    ("gho_", re.compile(r"gho_[A-Za-z0-9]{30,}")),
    ("ghu_", re.compile(r"ghu_[A-Za-z0-9]{30,}")),
    ("ghs_", re.compile(r"ghs_[A-Za-z0-9]{30,}")),
    ("ghr_", re.compile(r"ghr_[A-Za-z0-9]{30,}")),
    ("github_pat_", re.compile(r"github_pat_[A-Za-z0-9_]{16,}")),
    ("glpat-", re.compile(r"glpat-[A-Za-z0-9_\-]{20,}")),
    ("xox", re.compile(r"xox[abposr]-[A-Za-z0-9\-]{10,}")),
    ("AKIA", re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}")),
    ("AIza", re.compile(r"AIza[A-Za-z0-9_\-]{35}")),
    ("cfat_", re.compile(r"cfat_[A-Za-z0-9_\-]{20,}")),
)
_JWT_RE = re.compile(r"^eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]*$")
# "Bearer <anything>" as the whole value, or "Bearer <long token>" after a
# label; "bearer" inside an ordinary phrase is not a credential.
_BEARER_RE = re.compile(r"^bearer\s+\S|\sbearer\s+[A-Za-z0-9._~+/=\-]{16,}", re.IGNORECASE)
_TOKEN_CHARSET_RE = re.compile(r"^[A-Za-z0-9+/=_.\-]+$")
# Split a value into words so a credential behind a short label ("note: <key>")
# is judged on its own: first on spaces, commas and semicolons, then on `:`
# and `=`. Structured references (URLs, op:// refs, emails) are not split on
# `:`/`=`; a URL's query values are judged one by one instead.
_METADATA_CHUNK_SPLIT_RE = re.compile(r"[\s,;]+")
_METADATA_LABEL_SPLIT_RE = re.compile(r"[:=]")
_METADATA_URL_START_RE = re.compile(r"(?<![A-Za-z0-9+.\-])[A-Za-z][A-Za-z0-9+.\-]*://")
_METADATA_URL_PIECE_RE = re.compile(r"[/&?;#@]")
_METADATA_IPV4_RE = re.compile(r"[0-9]{1,3}(?:\.[0-9]{1,3}){3}")
_METADATA_URL_DECODE_PASSES = 3
_METADATA_URL_MAX_DEPTH = 3
_METADATA_EMAIL_RE = re.compile(r"^[^@\s:=/]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
METADATA_ENTROPY_MIN_LENGTH = 24
METADATA_ENTROPY_MIN_BITS = 3.5
# CamelCase and digit segments: "AcmeProd2026" -> Acme, Prod, 2026.
_METADATA_SEGMENT_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")
_METADATA_VERSION_TAIL_RE = re.compile(r"[A-Z][0-9]{1,3}$")
_VOWELS = frozenset("aeiouyAEIOUY")
# Abbreviations with digits between words ("CloudflareR2Storage",
# "B2BMarketing"): capital and digit segments that together form a short code.
_METADATA_CODE_PART_RE = re.compile(r"[A-Z]+|[0-9]+")
_METADATA_CODE_MAX_LENGTH = 4
# At the start or end of a value only the tightest code shape counts ("S3",
# "B2B"), next to a word of at least this many letters.
_METADATA_EDGE_CODE_RE = re.compile(r"[A-Z][0-9]{1,2}[A-Z]?")
_METADATA_EDGE_WORD_MIN_LENGTH = 6
_METADATA_WORD_RE = re.compile(r"[A-Z][a-z]{3,}")
_METADATA_CONSONANT_RUN_RE = re.compile(r"[^aeiouyAEIOUY]{4,}")
# Share of segments that look generated rather than written. Labels are made
# of words ("Us", "Api", "Name", "2026") and score near 0; random tokens break
# into single letters, vowel-less runs and lone digits and score well above.
# Miss rates for this threshold are measured in docs/connect.md.
METADATA_MIN_GENERATED_SEGMENT_SHARE = 0.3


def _shannon_bits_per_char(value: str) -> float:
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    total = len(value)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def _reads_as_word(segment: str) -> bool:
    """A capitalised, pronounceable word of four or more letters."""
    if not _METADATA_WORD_RE.fullmatch(segment):
        return False
    vowels = sum(char in _VOWELS for char in segment)
    return vowels * 10 >= 3 * len(segment) and not _METADATA_CONSONANT_RUN_RE.search(segment)


def _merge_metadata_codes(segments: list[str]) -> list[str | None]:
    """Replace short letter-digit codes between words with ``None`` (a word).

    "CloudflareR2Storage" segments as Cloudflare, R, 2, Storage; R and 2 read
    as generated on their own. Merged, R2 sits between two real words and
    counts as one word. Random tokens rarely put a code between pronounceable
    words, so the miss rates in docs/connect.md hold.
    """
    merged: list[str | None] = []
    index = 0
    while index < len(segments):
        if not _METADATA_CODE_PART_RE.fullmatch(segments[index]):
            merged.append(segments[index])
            index += 1
            continue
        end = index
        while end < len(segments) and _METADATA_CODE_PART_RE.fullmatch(segments[end]):
            end += 1
        run = segments[index:end]
        code = "".join(run)
        left = segments[index - 1] if index > 0 else None
        right = segments[end] if end < len(segments) else None
        if left is not None and right is not None:
            beside_words = _reads_as_word(left) and _reads_as_word(right)
        else:
            neighbour = left if left is not None else right
            beside_words = (
                neighbour is not None
                and _reads_as_word(neighbour)
                and len(neighbour) >= _METADATA_EDGE_WORD_MIN_LENGTH
                and bool(_METADATA_EDGE_CODE_RE.fullmatch(code))
            )
        if (
            len(run) > 1
            and len(code) <= _METADATA_CODE_MAX_LENGTH
            and any(char.isdigit() for char in code)
            and beside_words
        ):
            merged.append(None)
        else:
            merged.extend(run)
        index = end
    return merged


def _segment_is_generated(segment: str) -> bool:
    if segment.isdigit():
        return len(segment) == 1
    return len(segment) == 1 or not any(char in _VOWELS for char in segment)


def _generated_segment_share(value: str) -> float:
    """Share of CamelCase/digit segments that do not read as words.

    A segment counts as generated when it is a single letter, a letter run
    with no vowel, or a lone digit. A trailing version such as ``V2`` counts
    as a word. A short code between words such as ``R2`` or ``B2B`` counts
    as a word only when every other segment reads as a word too, apart from
    a final lone digit (``S3ProductionBucketUsWest2``); a code next to a
    generated tail ("<words>R2<words>Qe7Lo") is judged letter by letter.
    """
    body = value
    version = _METADATA_VERSION_TAIL_RE.search(value)
    if version:
        body = value[: version.start()]
    raw = _METADATA_SEGMENT_RE.findall(body)
    segments = _merge_metadata_codes(raw)
    if None in segments:
        others = [segment for segment in segments if segment is not None]
        if others and others[-1].isdigit() and segments[-1] is not None:
            others = others[:-1]
        if any(_segment_is_generated(segment) for segment in others):
            segments = list(raw)
    total = len(segments) + (1 if version else 0)
    if not total:
        return 0.0
    generated = sum(
        1 for segment in segments if segment is not None and _segment_is_generated(segment)
    )
    return generated / total


def _word_secret_rule(word: str) -> str:
    for prefix, grammar in METADATA_SECRET_GRAMMARS:
        if grammar.fullmatch(word):
            return f"credential_prefix:{prefix}"
    if _JWT_RE.fullmatch(word):
        return "jwt_shape"
    # Long random-looking strings: mixed case, nothing but token characters,
    # enough entropy, and segments that do not read as words. Hex ids, UUIDs,
    # numeric ids, URLs, emails, lowercase paths and CamelCase labels fall
    # outside this on purpose.
    if (
        len(word) >= METADATA_ENTROPY_MIN_LENGTH
        and _TOKEN_CHARSET_RE.fullmatch(word)
        and any(char.isupper() for char in word)
        and any(char.islower() for char in word)
        and _shannon_bits_per_char(word) >= METADATA_ENTROPY_MIN_BITS
        and _generated_segment_share(word) >= METADATA_MIN_GENERATED_SEGMENT_SHARE
    ):
        return "high_entropy"
    return ""


def _metadata_words(value: str) -> list[str]:
    """The words of a metadata value that are judged one by one.

    A URL stays whole and contributes its decoded parts: user name,
    password, path segments, query keys and values, and fragment pieces.
    Each part is split on ``:`` and ``=`` like a bare value, so
    ``?campaign=<label>`` is judged as the label and ``/token=<key>``,
    ``#token:<key>`` or ``?token=<key>`` as the key. An email or env
    reference stays whole. Anything else is split on ``:`` and ``=`` so
    "note: <key>" is caught.
    """
    words: list[str] = []
    for chunk in _METADATA_CHUNK_SPLIT_RE.split(value):
        if _METADATA_EMAIL_RE.fullmatch(chunk) or _looks_like_env_reference(chunk):
            words.append(chunk)
            continue
        url = _METADATA_URL_START_RE.search(chunk)
        label = chunk[: url.start()] if url else chunk
        words.extend(word for word in _METADATA_LABEL_SPLIT_RE.split(label) if word)
        if url:
            reference = chunk[url.start() :]
            words.append(reference)
            for part in _url_parts(reference):
                words.extend(word for word in _METADATA_LABEL_SPLIT_RE.split(part) if word)
    return words


def _fully_unquote(text: str) -> str:
    """Percent-decode until stable, at most ``_METADATA_URL_DECODE_PASSES`` times."""
    for _ in range(_METADATA_URL_DECODE_PASSES):
        decoded = urllib.parse.unquote(text)
        if decoded == text:
            break
        text = decoded
    return text


def _url_host_labels(netloc: str) -> list[str]:
    """Host labels as written (case kept), minus IP addresses and punycode."""
    host = netloc.rpartition("@")[2]
    if host.startswith("["):
        return []
    host = host.split(":", 1)[0]
    if _METADATA_IPV4_RE.fullmatch(host):
        return []
    return [label for label in host.split(".") if not label.lower().startswith("xn--")]


def _url_parts(reference: str, depth: int = 0) -> list[str]:
    """Decoded user name, password, host labels, path, query and fragment pieces.

    Each component is fully decoded before it is split, so an encoded
    separator (``%2F``) or a double-encoded token is judged as written. A URL
    nested inside a component is inspected the same way, up to
    ``_METADATA_URL_MAX_DEPTH`` levels.
    """
    try:
        parsed = urllib.parse.urlsplit(reference)
        # Reading every field validates it: a bad port or bracket raises here.
        components = [parsed.username or "", parsed.password or ""]
        _ = (parsed.hostname, parsed.port)
    except ValueError:
        # Unparseable: judge the decoded raw pieces instead.
        return [piece for piece in _METADATA_URL_PIECE_RE.split(_fully_unquote(reference)) if piece]
    parts = list(_url_host_labels(parsed.netloc))
    components += [parsed.path, parsed.query, parsed.fragment]
    for component in components:
        decoded = _fully_unquote(component)
        nested = _METADATA_URL_START_RE.search(decoded)
        if nested and depth < _METADATA_URL_MAX_DEPTH:
            parts.extend(_url_parts(decoded[nested.start() :], depth + 1))
            decoded = decoded[: nested.start()]
        parts.extend(piece for piece in _METADATA_URL_PIECE_RE.split(decoded) if piece)
    return parts


def metadata_value_rule(value: str) -> str:
    """Name the secret-shape rule a metadata value trips, or "" when it is safe.

    Judges the value, never the key: a label under a key called ``key_name``
    is fine, and a live key under an innocent key name is not. The value is
    judged whole and word by word, so a short label in front of a key does
    not hide it. The returned rule name is safe to show; the value never is.
    """
    candidate = value.strip()
    if _BEARER_RE.search(candidate):
        return "bearer_credential"
    if (
        _looks_like_env_reference(candidate)
        or _looks_like_placeholder(candidate)
        or _looks_like_iso_datetime(candidate)
    ):
        return ""
    words = [candidate, *_metadata_words(candidate)]
    for word in words:
        if _looks_like_env_reference(word) or _looks_like_placeholder(word):
            continue
        rule = _word_secret_rule(word)
        if rule:
            return rule
    return ""


# Operator input an error may quote back: short names, ids and command paths.
# Anything longer, oddly shaped or secret-shaped is described, never echoed,
# so a credential pasted into the wrong argument does not come back on stderr.
_ECHOABLE_INPUT_RE = re.compile(r"^[A-Za-z0-9_.~/@+:-]{1,64}$")
HIDDEN_INPUT = "(not shown: it may be a credential)"


def echoable_input(value: object) -> str:
    """Return ``value`` when an error may show it, or "" when it must not."""
    text = str(value).strip()
    if not _ECHOABLE_INPUT_RE.fullmatch(text) or metadata_value_rule(text):
        return ""
    return text


def quoted_input(value: object) -> str:
    """Quote operator input for an error message, or say it is not shown."""
    text = echoable_input(value)
    return repr(text) if text else HIDDEN_INPUT


def _parse_metadata(pairs: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for position, pair in enumerate(pairs, start=1):
        if "=" not in pair:
            # Echo the key part only: a bare secret pasted without `=` must
            # not come back in the error.
            _refuse(
                "metadata_format",
                "metadata must be key=value; one --metadata argument has no `=`.",
            )
        key, value = pair.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            _refuse("metadata_format", "metadata keys cannot be empty")
        rule = metadata_value_rule(value)
        if rule:
            _refuse(
                "metadata_secret_value",
                f"metadata value for {quoted_input(key)} (--metadata argument {position}) "
                f"looks like a secret (rule: {rule}). "
                "Nothing was stored. Pass the credential with --token-stdin; "
                "metadata holds labels and ids only.",
            )
        key_rule = metadata_value_rule(key)
        if key_rule:
            _refuse(
                "metadata_secret_key",
                f"metadata key {HIDDEN_INPUT} (--metadata argument {position}) "
                f"looks like a secret (rule: {key_rule}). "
                "Nothing was stored. Pass the credential with --token-stdin; "
                "metadata keys are names such as zone_id.",
            )
        metadata[key] = value
    return metadata


def merge_recorded_metadata(existing: Any, given: dict[str, str]) -> dict[str, str]:
    """The recorded metadata updated with ``given``.

    Keys given are set, keys given with an empty value are removed, every other
    recorded key is kept. Recorded keys whose value is empty are dropped.
    """

    merged = (
        {str(key): str(value) for key, value in existing.items() if value not in (None, "")}
        if isinstance(existing, dict)
        else {}
    )
    merged.update(given)
    return {key: value for key, value in merged.items() if value != ""}


def _cloudflare_token_type(metadata: dict[str, Any], secret: str = "") -> str:
    if secret.strip().startswith("cfat_"):
        return "account"
    raw = (
        metadata.get("token_type")
        or metadata.get("token_scope")
        or metadata.get("api_token_type")
        or metadata.get("api_scope")
        or ""
    )
    value = str(raw).strip().lower().replace("_", "-")
    if value in {"account", "account-scoped", "account-owned", "account-token"}:
        return "account"
    return "user"


def _python_version_ok(value: str) -> bool:
    parts = value.strip().split(".")
    if len(parts) < 2:
        return False
    try:
        major = int(parts[0])
        minor = int(parts[1])
    except ValueError:
        return False
    return (major, minor) >= (3, 12)


def _meta_python_ready(
    *,
    which_func: Which | None = None,
    command_runner: CommandRunner | None = None,
) -> bool:
    if sys.version_info >= (3, 12):
        return True
    which = which_func or shutil.which
    run = command_runner or _run_command
    python312 = which("python3.12")
    if not python312:
        return False
    result = run(
        [
            python312,
            "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
        ],
        None,
        3.0,
    )
    return bool(result.get("ok")) and _python_version_ok(str(result.get("stdout") or ""))


def _meta_prerequisite_state(
    *,
    which_func: Which | None = None,
    command_runner: CommandRunner | None = None,
) -> str:
    which = which_func or shutil.which
    run = command_runner or _run_command
    if which("meta"):
        version = run(["meta", "--version"], None, 5.0)
        if version.get("ok"):
            return ""
        return "missing_cli"
    if not _meta_python_ready(which_func=which, command_runner=run):
        return "wrong_python"
    return "missing_cli"


def _meta_setup() -> dict[str, Any]:
    return {
        "requirements": list(META_SETUP_REQUIREMENTS),
        "token_scopes": list(META_TOKEN_SCOPES),
        "credential_paths": ["--token-stdin", "--from-env", "hidden prompt"],
        "safe_metadata": [
            "ad_account_id (use the act_ ad account ID)",
            "business_id (Meta calls this Business portfolio ID)",
            "account label",
        ],
        "test_command": "mb connect test meta --json",
        "safe_to_share": True,
    }


def _validate_key_shape(provider: Provider, token: str, metadata: dict[str, str]) -> None:
    """Refuse malformed credentials at intake.

    Error messages must never echo the credential value — only its expected
    shape and, for Stripe, whether it is a test or live key.
    """
    if not token or not provider.key_prefixes:
        return
    if not token.startswith(provider.key_prefixes):
        shapes = ", ".join(f"{prefix}…" for prefix in provider.key_prefixes)
        slot = provider.required_secrets[0] if provider.required_secrets else "credential"
        _refuse(
            "key_shape",
            f"the {provider.name} {slot} does not match the expected key shape "
            f"({shapes}). Nothing was stored; check the value and reconnect.",
        )
    if provider.id == "stripe":
        mode = str(metadata.get("mode") or "").strip().lower()
        if mode == "live" and token.startswith(("sk_test_", "rk_test_")):
            _refuse(
                "stripe_mode_mismatch",
                "The mode is live (metadata says mode=live) and this is a Stripe TEST key. "
                "Nothing was stored. To switch this connection to test mode, rerun with "
                "`--metadata mode=test`; otherwise use a live key.",
            )
        if mode == "test" and token.startswith(("sk_live_", "rk_live_")):
            _refuse(
                "stripe_mode_mismatch",
                "The mode is test (metadata says mode=test) and this is a Stripe LIVE key. "
                "Nothing was stored. To switch this connection to live mode, rerun with "
                "`--metadata mode=live`; otherwise use a test key.",
            )


def connect_provider(
    provider_id: str,
    repo: str | Path = ".",
    *,
    token: str = "",
    account_label: str | None = None,
    metadata_pairs: list[str] | None = None,
    secret_backend: str | None = None,
    scope: str = "repo",
    custom: bool = False,
    source: str = "",
) -> dict[str, Any]:
    """Connect a provider by writing repo metadata and local secrets.

    Storing a secret for a provider that already has an entry replaces the
    secret only: the recorded ``metadata`` and ``account_label`` stay unless the
    call gives new values. ``account_label=None`` keeps the label, a string
    replaces it, and ``""`` clears it. A metadata pair ``key=value`` updates that
    key and ``key=`` removes it. A tokenless edit on an already-recorded
    provider follows the same rule and keeps the secret reference. A first
    connect records exactly what it was given.

    ``source`` is a non-secret reference to where the credential lives, such
    as ``op://vault/item/field``; it is stored as ``metadata.source`` so
    `mb connect rotate` can read the credential again. When ``source`` is the
    only metadata given, the existing metadata is kept and the source added.
    """

    if custom:
        provider = normalize_provider(provider_id, allow_custom=True)
    else:
        # Reconnecting an existing custom provider works without the flag.
        provider = resolve_provider(provider_id, repo)
    normalized_scope = scope.strip().lower().replace("_", "-") or "repo"
    if normalized_scope not in CONNECT_SCOPES:
        raise ValueError("scope must be repo or user")
    target = Path(repo).resolve()
    metadata = _parse_metadata(metadata_pairs or [])
    source = source.strip()
    if source:
        _check_source_ref(source)
    config = _read_config(target)
    repo_id = _ensure_repo_id(config, target)
    credential_deadline = new_credential_deadline()
    providers = config["providers"]
    raw_existing_entry = providers.get(provider.id)
    if not token and provider.id not in providers:
        raw_existing_entry = _user_scope_provider_entry(repo_id, provider.id)
    existing_entry = raw_existing_entry if isinstance(raw_existing_entry, dict) else {}
    oauth_candidate: Any = None
    if token and GOOGLE_OAUTH_GRANT_SLOT in provider.optional_secrets:
        # A token reconnect rebuilds `secrets` from the primary slot only, which
        # would drop the grant ref and orphan its credential-store item.
        oauth_candidate = providers.get(provider.id)
        if not isinstance(oauth_candidate, dict):
            oauth_candidate = _user_scope_provider_entry(repo_id, provider.id)
    if _records_oauth_grant(provider, oauth_candidate):
        _refuse(
            "oauth_connection_exists",
            f"this {provider.name} connection uses a Google sign-in (OAuth). Storing a token "
            "here would drop the sign-in and orphan its stored grant. Renew the sign-in with "
            "`mb connect google --oauth --reauth`. Nothing was stored.",
        )
    # What a later connect keeps: the repo entry, else the user-scope record. A
    # first connect has none and records exactly what it was given.
    prior_entry: dict[str, Any] | None = None
    if not token:
        prior_entry = existing_entry if isinstance(raw_existing_entry, dict) else None
    else:
        raw_prior = providers.get(provider.id)
        if not isinstance(raw_prior, dict) and normalized_scope == "user":
            # Only a user-scope store reads the user-scope file, so a repo-scope
            # store never depends on it being readable.
            raw_prior = _user_scope_provider_entry(repo_id, provider.id)
        prior_entry = raw_prior if isinstance(raw_prior, dict) else None
    if prior_entry is not None and not _records_oauth_grant(provider, prior_entry):
        # A Google sign-in merges its own metadata below.
        metadata = merge_recorded_metadata(prior_entry.get("metadata"), metadata)
    if source:
        if not metadata_pairs:
            raw_existing_metadata = existing_entry.get("metadata")
            if isinstance(raw_existing_metadata, dict):
                metadata = {str(key): str(value) for key, value in raw_existing_metadata.items()}
        metadata["source"] = source
    _validate_key_shape(provider, token, metadata)
    if normalized_scope == "user":
        # Before any credential is stored, so a refusal leaves the store unchanged.
        _ensure_user_scope_writable()

    secrets: dict[str, dict[str, str]] = {}
    previous_secret: SecretProbe | None = None
    required = list(provider.required_secrets)
    if required:
        primary = required[0]
        if token:
            store = SecretStore(secret_backend)
            ref = _secret_ref(repo_id, provider.id, primary)
            try:
                if normalized_scope == "user":
                    # The rollback snapshot is a separate bounded read. The write
                    # and final status read retain their original shared budget.
                    previous_secret = store.probe(ref, deadline=new_credential_deadline())
                    if not previous_secret.backend_ok:
                        raise KeychainError(previous_secret.reason)
                    if previous_secret.not_checked:
                        # Nothing is known about the item: writing could lose its value.
                        raise KeychainError("credential_store_timeout")
                    credential_deadline = new_credential_deadline()
                store.set(ref, token, deadline=credential_deadline)
            except KeychainError as exc:
                # Fail before any metadata is written, so a backend outage
                # cannot leave `connected: true` next to an unstored secret.
                detail = _backend_repair(exc.reason)
                raise KeychainError(
                    exc.reason,
                    f"{detail['summary']} Nothing was stored and the repo metadata is "
                    f"unchanged. {detail['repair']}",
                ) from exc
            secrets[primary] = {"ref": ref, "backend": store.backend}
        else:
            raw_existing_secrets = existing_entry.get("secrets")
            existing_secrets = (
                raw_existing_secrets if isinstance(raw_existing_secrets, dict) else {}
            )
            raw_primary = existing_secrets.get(primary)
            existing_primary = raw_primary if isinstance(raw_primary, dict) else {}
            existing_ref = str(existing_primary.get("ref") or "")
            if existing_ref:
                existing_backend = str(existing_primary.get("backend") or "local-file")
                # Tokenless reconnects may update safe metadata or scope, but
                # they cannot migrate a secret. Validate and retain the exact
                # recorded store/ref instead of orphaning the existing value.
                store = SecretStore(existing_backend)
                secrets = {
                    str(field): {
                        str(key): str(value)
                        for key, value in raw_secret.items()
                        if key in {"ref", "backend"}
                    }
                    for field, raw_secret in existing_secrets.items()
                    if isinstance(raw_secret, dict)
                }
                if _records_oauth_grant(provider, existing_entry):
                    from mb import google_connect

                    # Which Google products the sign-in granted is recorded by
                    # the sign-in itself; a metadata edit neither drops nor sets
                    # it. The edit updates the keys given and keeps the rest, so
                    # the `--metadata` repair `mb connect test google` names for
                    # one product leaves the other product's id in place.
                    # An empty value (`--metadata search_console_site=`) removes
                    # that key, so the reads refuse with `site_not_recorded`.
                    metadata.pop(GOOGLE_OAUTH_GRANTS_METADATA, None)
                    metadata = google_connect.merge_oauth_metadata(
                        existing_entry.get("metadata"), metadata
                    )
            else:
                # A tokenless first connect records metadata and source only.
                # No ref points at an item that was never written, and the
                # entry is not connected until a secret is stored (#991).
                store = SecretStore(secret_backend)
    else:
        store = SecretStore(secret_backend)

    if prior_entry is not None and account_label is None:
        recorded_label = str(prior_entry.get("account_label") or "")
    else:
        recorded_label = (account_label or "").strip()
    providers[provider.id] = {
        "provider": provider.id,
        "connected": bool(secrets) or not required,
        "scope": normalized_scope,
        "account_label": recorded_label,
        "connected_at": _now(),
        "last_checked_at": _now(),
        "auth": provider.auth,
        "secrets": secrets,
        "metadata": metadata,
    }
    raw_oauth = existing_entry.get("oauth")
    if not token and _records_oauth_grant(provider, existing_entry) and isinstance(raw_oauth, dict):
        # The sign-in's coarse refresh-token expiry outlives a metadata edit.
        providers[provider.id]["oauth"] = dict(raw_oauth)
    user_scope_path = ""
    if normalized_scope == "user":
        try:
            user_scope_path = str(
                _write_user_scope_provider(
                    repo_id,
                    repo_identity=config.get("repo_identity") or {},
                    provider_id=provider.id,
                    entry=providers[provider.id],
                )
            )
        except (UserScopeReadOnlyError, ConfigCorruptError, OSError) as exc:
            # A read-only file is the expected case; any other failure to write
            # the record (a full disk, an I/O error, a failed rename, a file
            # that no longer parses) gets the same restore of the credential.
            shown, cause, fix = _user_scope_record_failure(exc)
            unrestored = (
                _restore_secrets(
                    store, [(f"the {provider.name} credential", ref, previous_secret, token)]
                )
                if previous_secret is not None
                else []
            )
            if unrestored:
                assert previous_secret is not None
                command = [
                    "mb",
                    "connect",
                    provider.id,
                    "--token-stdin",
                    "--scope",
                    "user",
                    "--repo",
                    str(target),
                ]
                if provider.category == "custom":
                    command.append("--custom")
                if recorded_label:
                    command.extend(["--account", recorded_label])
                for key, value in metadata.items():
                    command.extend(["--metadata", f"{key}={value}"])
                action = "replaced" if previous_secret.present else "stored"
                record_state = (
                    "The repo metadata is unchanged, but the user-scope record may have changed."
                    if isinstance(exc, UserScopeRecordRestoreError)
                    else "The repo metadata is unchanged."
                )
                raise MetadataWriteError(
                    f"The {provider.name} credential was {action} but not recorded: "
                    f"the user-scope connect file {shown} {cause}, and the "
                    f"previous credential state could not be restored "
                    f"({' and '.join(unrestored)} stayed changed). {record_state} "
                    f"{fix} first, then rerun "
                    f"`{_shell_replay_command(command, target)}` with the credential again."
                ) from None
            if isinstance(exc, OSError):
                if previous_secret is None:
                    undone = "No credential was changed."
                elif previous_secret.present:
                    undone = "The previous credential was restored."
                else:
                    undone = "The new credential was removed, so nothing was stored."
                if isinstance(exc, UserScopeRecordRestoreError):
                    raise MetadataWriteError(
                        f"The {provider.name} user-scope record {shown} could not be restored "
                        f"after a write error. {undone} The repo metadata is unchanged, but "
                        f"the user-scope record may have changed. {fix}, then rerun the command."
                    ) from None
                raise MetadataWriteError(
                    f"The {provider.name} connection was not recorded: the user-scope "
                    f"connect file {shown} {cause}. {undone} The repo metadata is "
                    f"unchanged. {fix}, then rerun the command."
                ) from None
            raise
    path = _write_config(target, config)
    status = status_provider(
        provider.id,
        target,
        _credential_deadline=credential_deadline,
    )
    result: dict[str, Any] = {
        "ok": status["state"] not in {"missing_secret", BACKEND_FAILURE_STATE},
        "ready": bool(status["ok"]),
        "provider": provider.id,
        "scope": normalized_scope,
        "config_path": str(path),
        "user_scope_path": user_scope_path,
        "hydrated": normalized_scope == "user",
        "credential_backend": store.backend,
        "credential_boundary": store.boundary(),
        # Kept as empty compatibility fields for callers from earlier releases.
        # Credentials are repo_id-scoped and must never rotate another business.
        "rotated_sibling_refs": [],
        "stale_sibling_refs": [],
        "setup": _meta_setup() if provider.id == "meta" else {},
        "status": status,
    }
    if prior_entry is not None:
        result["reconnect"] = _reconnect_changes(prior_entry, recorded_label, metadata)
    return result


def _reconnect_changes(
    prior_entry: dict[str, Any],
    recorded_label: str,
    metadata: dict[str, str],
) -> dict[str, Any]:
    """Which recorded fields a re-stored secret kept, replaced or cleared.

    Names only, never values; a key that looks like a secret is left out.
    """

    previous_label = str(prior_entry.get("account_label") or "")
    if recorded_label == previous_label:
        label_change = "kept"
    elif recorded_label:
        label_change = "replaced"
    else:
        label_change = "cleared"
    previous = prior_entry.get("metadata")
    before = (
        {str(key): str(value) for key, value in previous.items() if value not in (None, "")}
        if isinstance(previous, dict)
        else {}
    )
    shown = {
        "kept": sorted(key for key in metadata if key in before and metadata[key] == before[key]),
        "set": sorted(key for key in metadata if before.get(key) != metadata[key]),
        "removed": sorted(key for key in before if key not in metadata),
    }
    return {
        "account_label": label_change,
        "metadata": {
            name: [key for key in keys if not _metadata_key_looks_sensitive(key)]
            for name, keys in shown.items()
        },
    }


def _secret_statuses(
    provider: Provider,
    entry: dict[str, Any],
    *,
    deadline: float | None = None,
    probes: dict[str, SecretProbe] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    secrets: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    stored_secrets = entry.get("secrets") if isinstance(entry.get("secrets"), dict) else {}
    for field in provider.required_secrets:
        raw = stored_secrets.get(field) if isinstance(stored_secrets, dict) else None
        raw = raw if isinstance(raw, dict) else {}
        ref = str(raw.get("ref") or "")
        backend = str(raw.get("backend") or "local-file")
        probe = probes.get(field) if probes is not None else None
        if probe is None:
            probe = _probe_secret_ref(backend, ref, deadline=deadline, allow_not_checked=True)
        if not probe.present and not probe.not_checked:
            missing.append(field)
        secrets[field] = {
            "present": _present_value(probe),
            "presence": _secret_presence(probe),
            "ref": ref,
            "backend": backend,
            "backend_ok": probe.backend_ok,
            "backend_state": _probe_backend_state(probe),
        }
    for field in provider.optional_secrets:
        raw = stored_secrets.get(field) if isinstance(stored_secrets, dict) else None
        raw = raw if isinstance(raw, dict) else {}
        ref = str(raw.get("ref") or "")
        if not ref:
            # Only a slot the entry records is reported, so connections that
            # never used it keep their status output unchanged.
            continue
        backend = str(raw.get("backend") or "local-file")
        probe = probes.get(field) if probes is not None else None
        if probe is None:
            probe = _probe_secret_ref(backend, ref, deadline=deadline, allow_not_checked=True)
        secrets[field] = {
            "present": _present_value(probe),
            "presence": _secret_presence(probe),
            "ref": ref,
            "backend": backend,
            "backend_ok": probe.backend_ok,
            "backend_state": _probe_backend_state(probe),
            "optional": True,
        }
        if field == GOOGLE_OAUTH_GRANT_SLOT and probe.not_checked:
            # Not read, so nothing is known about the grant: no `readable` or
            # `usable` claim, and it is not counted as gone.
            continue
        if field == GOOGLE_OAUTH_GRANT_SLOT:
            from mb import google_connect

            if probe.backend_ok and not probe.present:
                # A recorded sign-in grant that is gone. Presence only.
                missing.append(field)
            # The rule `mb connect test` and `--reauth` use: `readable` when
            # `--reauth` can read its OAuth client from the grant, `usable` when
            # the grant can mint an access token. Only booleans leave here.
            grant_repair = google_connect.grant_repair_command(
                probe.value if probe.present else None
            )
            secrets[field]["readable"] = grant_repair != google_connect.REAUTH_WITH_CLIENT_COMMAND
            secrets[field]["usable"] = not grant_repair
    return secrets, missing


def _google_grant_unusable(secrets: dict[str, Any]) -> bool:
    """Is a recorded Google sign-in grant present but unable to mint a token?"""

    raw = secrets.get(GOOGLE_OAUTH_GRANT_SLOT)
    return isinstance(raw, dict) and raw.get("present") is True and raw.get("usable") is False


def _entry_records_slot(entry: Any, slot: str) -> bool:
    """Does this entry record a ref for ``slot``? Reads metadata only."""

    if not isinstance(entry, dict):
        return False
    stored_secrets = entry.get("secrets")
    raw = stored_secrets.get(slot) if isinstance(stored_secrets, dict) else None
    return isinstance(raw, dict) and bool(raw.get("ref"))


def _records_oauth_grant(provider: Provider, entry: Any) -> bool:
    """Does this entry record a Google OAuth grant (OAuth mode)?"""

    if GOOGLE_OAUTH_GRANT_SLOT not in provider.optional_secrets:
        return False
    return _entry_records_slot(entry, GOOGLE_OAUTH_GRANT_SLOT)


def _credential_mode(provider: Provider, entry: dict[str, Any]) -> dict[str, Any]:
    """``credential_mode`` for providers with optional slots, else nothing.

    `google` reads ``oauth`` once its entry records an OAuth grant and
    ``access_token`` otherwise. Other providers carry no key at all.
    """

    if GOOGLE_OAUTH_GRANT_SLOT not in provider.optional_secrets:
        return {}
    if not _records_oauth_grant(provider, entry):
        return {"credential_mode": "access_token"}
    from mb import google_connect

    # A coarse date only, and "" unless Google put a time limit on the sign-in.
    expires_on = google_connect.refresh_token_expires_on(entry)
    raw_metadata = entry.get("metadata")
    raw_grants = (
        raw_metadata.get(GOOGLE_OAUTH_GRANTS_METADATA) if isinstance(raw_metadata, dict) else ""
    )
    granted = {label.strip() for label in str(raw_grants or "").split(",")}
    return {
        "credential_mode": "oauth",
        "oauth": {
            "refresh_token_expires_on": expires_on,
            # Which products the sign-in granted, from a fixed list.
            "grants": [label for label in GOOGLE_OAUTH_PRODUCTS if label in granted],
        },
    }


def _probe_backend_state(probe: SecretProbe) -> str:
    if probe.not_checked:
        return NOT_CHECKED_BACKEND_STATE
    return probe.reason or "ready"


def _secrets_not_checked(secrets: dict[str, Any]) -> list[str]:
    """Slots an aggregate command did not get to read (see ``NOT_CHECKED_STATE``)."""

    return [
        field
        for field, raw in secrets.items()
        if isinstance(raw, dict) and raw.get("backend_state") == NOT_CHECKED_BACKEND_STATE
    ]


def _secret_presence(probe: SecretProbe) -> str:
    """``present``, ``absent``, or ``unknown`` when the backend could not answer."""

    if not probe.backend_ok or probe.not_checked:
        return "unknown"
    return "present" if probe.present else "absent"


def _present_value(probe: SecretProbe) -> bool | None:
    """``present`` is only ever false for a credential known to be absent.

    A locked or unavailable backend cannot say whether the credential exists,
    so it reads ``None`` rather than a ``False`` that looks like a missing
    secret (#976). ``presence`` carries the same fact as a string.
    """

    return probe.present if probe.backend_ok and not probe.not_checked else None


def _probe_secret_ref(
    backend: str,
    ref: str,
    *,
    deadline: float | None = None,
    interactive: bool = False,
    allow_not_checked: bool = False,
) -> SecretProbe:
    """Probe stored metadata without letting a foreign backend crash status."""

    try:
        return SecretStore(backend).probe(
            ref,
            deadline=deadline,
            interactive=interactive,
            allow_not_checked=allow_not_checked,
        )
    except (CredentialStoreError, ValueError):
        return SecretProbe("", False, False, "backend_incompatible")


def _backend_failure_reason(secrets: dict[str, Any]) -> str:
    """First backend reason code across a provider's secrets, else ``""``."""

    for raw in secrets.values():
        entry = raw if isinstance(raw, dict) else {}
        if not entry.get("backend_ok", True):
            return str(entry.get("backend_state") or "keychain_unavailable")
    return ""


def _unhydrated_status(
    provider: Provider, entry: dict[str, Any], *, deadline: float | None = None
) -> dict[str, Any]:
    secrets, missing = _secret_statuses(provider, entry, deadline=deadline)
    raw_metadata = entry.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    backend_reason = _backend_failure_reason(secrets)
    not_checked = _secrets_not_checked(secrets)
    if backend_reason:
        state = BACKEND_FAILURE_STATE
        repair = _repair(provider, state, missing, None, backend_reason)
        ok = False
    elif missing:
        repair = _repair(provider, "missing_secret", missing, entry=entry, secrets=secrets)
        state = "missing_secret"
        ok = False
    elif not_checked:
        state = NOT_CHECKED_STATE
        repair = _repair(provider, state)
        ok = False
    else:
        repair = {
            "summary": (
                f"{provider.name} exists in user scope, but this workspace is not hydrated."
            ),
            "repair": "Run `mb connect hydrate --repo .` from this workspace.",
            "repair_command": "mb connect hydrate --repo .",
        }
        state = "needs_hydration"
        ok = False
    raw_validation = entry.get("validation")
    stored_validation: dict[str, Any] = raw_validation if isinstance(raw_validation, dict) else {}
    return {
        "provider": provider.id,
        "name": provider.name,
        "connected": bool(entry.get("connected", True)),
        "configured": True,
        "ok": ok,
        "state": state,
        "stored": bool(provider.required_secrets)
        and not missing
        and not backend_reason
        and not not_checked,
        **_credential_mode(provider, entry),
        "has_probe": has_provider_probe(provider.id, entry),
        "provider_verified": _provider_verified(stored_validation),
        "verified_at": _verified_at(stored_validation),
        "summary": repair["summary"],
        "repair": repair["repair"],
        "repair_command": repair["repair_command"],
        "safe_to_share": True,
        "account_label": _safe_status_label(entry.get("account_label")),
        "metadata": _safe_status_metadata(metadata),
        "secrets": secrets,
        "last_checked_at": str(entry.get("last_checked_at") or ""),
        "scope": "user",
        "user_scope_available": True,
        "hydrated": False,
        "validation": {
            "state": state,
            "checked_at": "",
            "provider_verified": _provider_verified(stored_validation),
            "verified_at": _verified_at(stored_validation),
            "summary": repair["summary"],
        },
    }


def resolve_provider(provider_id: str, repo: str | Path = ".") -> Provider:
    """Resolve a provider id against the registry, then connected customs.

    Read paths (status, token, test, hydrate) use this so an already
    connected custom provider keeps working without re-passing --custom.
    """
    try:
        return normalize_provider(provider_id)
    except ValueError:
        key = provider_id.strip().lower().replace("_", "-")
        if CUSTOM_PROVIDER_RE.fullmatch(key):
            target = Path(repo).resolve()
            config = _read_config(target)
            if isinstance(config["providers"].get(key), dict):
                return _custom_provider(key)
            repo_id = str(config.get("repo_id") or _repo_identity(target)["repo_id"])
            if _user_scope_provider_entry(repo_id, key) is not None:
                return _custom_provider(key)
        raise


def status_provider(
    provider_id: str,
    repo: str | Path = ".",
    *,
    which_func: Which | None = None,
    command_runner: CommandRunner | None = None,
    _credential_deadline: float | None = None,
    _secret_probes: dict[str, SecretProbe] | None = None,
) -> dict[str, Any]:
    provider = resolve_provider(provider_id, repo)
    target = Path(repo).resolve()
    config = _read_config(target)
    identity = _repo_identity(target)
    repo_id = str(config.get("repo_id") or identity["repo_id"])
    entry = config["providers"].get(provider.id)
    if not isinstance(entry, dict):
        user_entry = _user_scope_provider_entry(repo_id, provider.id)
        if user_entry is not None:
            return _unhydrated_status(provider, user_entry, deadline=_credential_deadline)
    if provider.id == "meta":
        prereq_state = _meta_prerequisite_state(
            which_func=which_func,
            command_runner=command_runner,
        )
        raw_entry = entry if isinstance(entry, dict) else {}
        raw_meta_metadata = raw_entry.get("metadata")
        meta_metadata: dict[str, Any] = (
            raw_meta_metadata if isinstance(raw_meta_metadata, dict) else {}
        )
        raw_meta_validation = raw_entry.get("validation")
        meta_validation: dict[str, Any] = (
            raw_meta_validation if isinstance(raw_meta_validation, dict) else {}
        )
        stored_secrets = (
            raw_entry.get("secrets") if isinstance(raw_entry.get("secrets"), dict) else {}
        )
        raw_secret = stored_secrets.get("access_token") if isinstance(stored_secrets, dict) else {}
        raw_secret = raw_secret if isinstance(raw_secret, dict) else {}
        ref = str(raw_secret.get("ref") or "")
        backend = str(raw_secret.get("backend") or "local-file")
        probe = _secret_probes.get("access_token") if _secret_probes is not None else None
        if probe is None:
            probe = _probe_secret_ref(
                backend, ref, deadline=_credential_deadline, allow_not_checked=True
            )
        secret_present = probe.present
        meta_backend_reason = "" if probe.backend_ok else (probe.reason or "keychain_unavailable")
        meta_stored = bool(secret_present and not meta_backend_reason)
        validation_state = str(meta_validation.get("state") or "unvalidated")
        if prereq_state:
            state = prereq_state
            ok = False
        elif not isinstance(entry, dict):
            state = "not_connected"
            ok = False
        elif meta_backend_reason:
            state = BACKEND_FAILURE_STATE
            ok = False
        elif probe.not_checked:
            state = NOT_CHECKED_STATE
            ok = False
        elif not secret_present:
            state = "missing_secret"
            ok = False
        elif not str(meta_metadata.get("ad_account_id") or "").strip():
            state = "missing_metadata"
            ok = False
        elif validation_state == "ready" and _provider_verified(meta_validation):
            state = "ready"
            ok = True
        elif validation_state == "ready":
            # Recorded ready without a recorded provider call (pre-0.5.3).
            state = UNVERIFIED_STATE
            ok = False
        elif validation_state in {
            "waiting_for_admin_approval",
            "auth_failed",
            "read_smoke_failed",
            "missing_cli",
            "wrong_python",
            "missing_metadata",
        }:
            state = validation_state
            ok = False
        else:
            state = "unvalidated"
            ok = False
        repair = _repair(
            provider,
            state,
            ["access_token"] if not secret_present and not probe.not_checked else [],
            meta_validation,
            meta_backend_reason,
        )
        return {
            "provider": provider.id,
            "name": provider.name,
            "connected": bool(isinstance(entry, dict) and raw_entry.get("connected", False)),
            "configured": isinstance(entry, dict),
            "ok": ok,
            "state": state,
            "stored": meta_stored,
            "has_probe": has_provider_probe(provider.id),
            "provider_verified": _provider_verified(meta_validation),
            "verified_at": _verified_at(meta_validation),
            "summary": repair["summary"],
            "repair": repair["repair"],
            "repair_command": repair["repair_command"],
            "safe_to_share": True,
            "account_label": _safe_status_label(raw_entry.get("account_label")),
            "metadata": _safe_status_metadata(meta_metadata),
            "secrets": {
                "access_token": {
                    "present": _present_value(probe),
                    "presence": _secret_presence(probe),
                    "ref": ref,
                    "backend": backend,
                    "backend_ok": probe.backend_ok,
                    "backend_state": _probe_backend_state(probe),
                }
            },
            "last_checked_at": str(raw_entry.get("last_checked_at") or ""),
            "scope": str(raw_entry.get("scope") or "repo"),
            "user_scope_available": bool(raw_entry.get("scope") == "user"),
            "hydrated": bool(raw_entry.get("scope") == "user"),
            "setup": _meta_setup(),
            "validation": {
                "state": str(meta_validation.get("state") or state),
                "checked_at": str(meta_validation.get("checked_at") or ""),
                "provider_verified": _provider_verified(meta_validation),
                "verified_at": _verified_at(meta_validation),
                "summary": str(meta_validation.get("summary") or ""),
                "upstream": meta_validation.get("upstream")
                if isinstance(meta_validation.get("upstream"), dict)
                else {},
                "repair": str(meta_validation.get("repair") or ""),
                "repair_command": str(meta_validation.get("repair_command") or ""),
                "safe_to_share": True,
            },
        }
    if not isinstance(entry, dict):
        repair = _repair(provider, "not_connected")
        return {
            "provider": provider.id,
            "name": provider.name,
            "connected": False,
            "configured": False,
            "ok": False,
            "state": "not_connected",
            "stored": False,
            "has_probe": has_provider_probe(provider.id),
            "provider_verified": False,
            "verified_at": "",
            "summary": repair["summary"],
            "repair": repair["repair"],
            "repair_command": repair["repair_command"],
            "safe_to_share": True,
            "account_label": "",
            "metadata": {},
            "secrets": {},
            "last_checked_at": "",
            "scope": "repo",
            "user_scope_available": False,
            "hydrated": False,
            "validation": {
                "state": "not_connected",
                "checked_at": "",
                "provider_verified": False,
                "verified_at": "",
                "summary": "",
            },
        }

    secrets, missing = _secret_statuses(
        provider,
        entry,
        deadline=_credential_deadline,
        probes=_secret_probes,
    )

    raw_metadata = entry.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    raw_validation = entry.get("validation")
    validation: dict[str, Any] = raw_validation if isinstance(raw_validation, dict) else {}
    backend_reason = _backend_failure_reason(secrets)
    not_checked = _secrets_not_checked(secrets)
    # "stored" is about credential material only: a provider that needs no
    # secret (hledger) has nothing stored, even though it can still be ready.
    stored = (
        bool(provider.required_secrets) and not missing and not backend_reason and not not_checked
    )
    if backend_reason:
        state = BACKEND_FAILURE_STATE
        ok = False
    elif missing:
        state = "missing_secret"
        ok = False
    elif not_checked:
        state = NOT_CHECKED_STATE
        ok = False
    elif not provider.required_secrets:
        state = "ready"
        ok = True
    else:
        validation_state = str(validation.get("state") or "unvalidated")
        if validation_state == "invalid":
            state = "invalid"
            ok = False
        elif validation_state == GOOGLE_REAUTH_REQUIRED_STATE and _records_oauth_grant(
            provider, entry
        ):
            # Recorded by a read that Google refused (`mb connect token`/`exec`);
            # status itself never calls Google.
            state = GOOGLE_REAUTH_REQUIRED_STATE
            ok = False
        elif _google_grant_unusable(secrets):
            # The stored grant cannot mint an access token, so an earlier
            # passing check no longer holds; `mb connect test` says the same.
            state = "invalid"
            ok = False
        elif _provider_verified(validation):
            state = "ready"
            ok = True
        elif validation_state in {"ready", UNVERIFIED_STATE}:
            # A check ran but never confirmed the credential with the provider.
            # Pre-0.5.3 metadata reaches here too: it recorded "ready" without
            # recording a provider call, so it is read as unverified.
            state = UNVERIFIED_STATE
            ok = False
        else:
            state = "unvalidated"
            ok = False
    repair = _repair(provider, state, missing, validation, backend_reason, entry, secrets)
    return {
        "provider": provider.id,
        "name": provider.name,
        "connected": bool(entry.get("connected", False)),
        "configured": True,
        "ok": ok,
        "state": state,
        "stored": stored,
        **_credential_mode(provider, entry),
        "has_probe": has_provider_probe(provider.id, entry),
        "provider_verified": _provider_verified(validation),
        "verified_at": _verified_at(validation),
        "summary": repair["summary"],
        "repair": repair["repair"],
        "repair_command": repair["repair_command"],
        "safe_to_share": True,
        "account_label": _safe_status_label(entry.get("account_label")),
        "metadata": _safe_status_metadata(metadata),
        "secrets": secrets,
        "last_checked_at": str(entry.get("last_checked_at") or ""),
        "scope": str(entry.get("scope") or "repo"),
        "user_scope_available": bool(entry.get("scope") == "user"),
        "hydrated": bool(entry.get("scope") == "user"),
        "validation": {
            "state": str(validation.get("state") or state),
            "checked_at": str(validation.get("checked_at") or ""),
            "provider_verified": _provider_verified(validation),
            "verified_at": _verified_at(validation),
            "summary": str(validation.get("summary") or ""),
            "upstream": validation.get("upstream")
            if isinstance(validation.get("upstream"), dict)
            else {},
            "repair": str(validation.get("repair") or ""),
            "repair_command": str(validation.get("repair_command") or ""),
            "safe_to_share": True,
            **_safe_probe_details(validation),
        },
    }


def _safe_probe_details(validation: dict[str, Any]) -> dict[str, Any]:
    """Recorded probe facts, re-typed so a hand-edited config cannot inject values."""
    details: dict[str, Any] = {}
    scopes = validation.get("scopes")
    if isinstance(scopes, dict):
        details["scopes"] = {
            str(name): str(verdict)
            for name, verdict in scopes.items()
            if verdict in {"allowed", "refused", "unknown"}
        }
    kind = validation.get("token_kind")
    if kind in GITHUB_TOKEN_KIND_NAMES:
        details["token_kind"] = kind
    token_scopes = validation.get("token_scopes")
    if isinstance(token_scopes, list):
        details["token_scopes"] = [
            str(scope)
            for scope in token_scopes
            if GITHUB_SCOPE_RE.fullmatch(str(scope)) and not metadata_value_rule(str(scope))
        ]
    products = validation.get("products")
    if isinstance(products, dict):
        safe_products: dict[str, dict[str, str]] = {}
        for name in GOOGLE_OAUTH_PRODUCTS:
            product = products.get(name)
            if not isinstance(product, dict) or product.get("state") not in GOOGLE_PRODUCT_STATES:
                continue
            rule = str(product.get("rule") or "")
            safe_products[name] = {
                "state": str(product["state"]),
                "rule": rule if _GOOGLE_PRODUCT_RULE_RE.fullmatch(rule) else "",
            }
        if safe_products:
            details["products"] = safe_products
    withheld = validation.get("token_scopes_withheld")
    if isinstance(withheld, int) and not isinstance(withheld, bool):
        details["token_scopes_withheld"] = withheld
    return details


def hydrate(
    repo: str | Path = ".",
    *,
    provider_id: str = "",
) -> dict[str, Any]:
    """Materialize ignored repo-local provider metadata from user scope."""

    target = Path(repo).resolve()
    config = _read_config(target)
    repo_id = _ensure_repo_id(config, target)
    data = _read_user_scope()
    raw_repo = data["repos"].get(repo_id)
    repo_entry = raw_repo if isinstance(raw_repo, dict) else {}
    raw_providers = repo_entry.get("providers")
    providers = raw_providers if isinstance(raw_providers, dict) else {}
    selected_ids: list[str]
    if provider_id:
        provider = resolve_provider(provider_id, repo)
        selected_ids = [provider.id]
    else:
        selected_ids = sorted(str(key) for key in providers)

    hydrated: list[str] = []
    missing: list[str] = []
    for selected in selected_ids:
        raw_entry = providers.get(selected)
        if not isinstance(raw_entry, dict):
            missing.append(selected)
            continue
        config["providers"][selected] = raw_entry
        hydrated.append(selected)

    path = ""
    if hydrated:
        path = str(_write_config(target, config))

    statuses = [status_provider(provider, target) for provider in hydrated]
    return {
        "ok": bool(hydrated) and not missing,
        "repo": str(target),
        "repo_id": repo_id,
        "config_path": path or str(_checked_config_path(target)),
        "user_scope_path": str(_user_scope_path()),
        "hydrated": hydrated,
        "missing": missing,
        "statuses": statuses,
        "safe_to_share": True,
        "repair_command": ""
        if hydrated
        else "mb connect <provider> --scope user --token-stdin --repo .",
    }


def _recorded_keychain_refs(repo: Path) -> list[tuple[str, str, str]]:
    """``(provider, field, ref)`` for every macOS Keychain secret ``repo`` records.

    Repo config wins over the user-scope entry for the same provider.
    """

    config = _read_config(repo)
    repo_id = str(config.get("repo_id") or _repo_identity(repo)["repo_id"])
    entries: dict[str, dict[str, Any]] = {}
    user_repo = _read_user_scope()["repos"].get(repo_id)
    user_repo = user_repo if isinstance(user_repo, dict) else {}
    user_providers = user_repo.get("providers")
    if isinstance(user_providers, dict):
        entries.update(
            {str(key): value for key, value in user_providers.items() if isinstance(value, dict)}
        )
    entries.update(
        {str(key): value for key, value in config["providers"].items() if isinstance(value, dict)}
    )
    recorded: list[tuple[str, str, str]] = []
    for provider_id in sorted(entries):
        raw_secrets = entries[provider_id].get("secrets")
        secrets = raw_secrets if isinstance(raw_secrets, dict) else {}
        for field in sorted(str(key) for key in secrets):
            raw = secrets.get(field)
            raw = raw if isinstance(raw, dict) else {}
            ref = str(raw.get("ref") or "")
            backend = str(raw.get("backend") or "local-file")
            try:
                selected = select_secret_backend(backend)
            except (CredentialStoreError, ValueError):
                continue
            if selected != "macos-keychain" or not ref:
                continue
            recorded.append((provider_id, field, ref))
    return recorded


def _repair_keychain_ref(
    ref: str, *, interactive: bool = False, command: str = KEYCHAIN_REPAIR_COMMAND
) -> dict[str, Any]:
    """Repair one macOS Keychain item; the same path for one repo or every item.

    An unattended read first: it also moves a legacy item this Python can
    read. Only an item whose read would need a dialog gets the interactive
    read, and only a fresh unattended read that finds the item owned by
    ``security`` counts as ``repaired``. Never returns the value.
    """

    backend = "macos-keychain"
    probe = _probe_secret_ref(backend, ref)
    before = probe.reason or ("ready" if probe.present else "missing")
    state = before
    migrated = probe.migrated
    if probe.present and probe.owner != "security":
        # Readable, but by this Python only: the next Python change would
        # prompt again. Not a repair until `security` owns it.
        state = "readable_not_migrated"
    if probe.reason == "keychain_prompt_pending" and interactive:
        answered = _probe_secret_ref(backend, ref, interactive=True)
        if answered.present:
            # The answered read also moves the item when this Python may
            # remove it. Only a fresh unattended read that finds the item
            # owned by `security` proves the repair.
            after = _probe_secret_ref(backend, ref)
            migrated = answered.migrated or after.migrated
            if not after.present:
                state = "still_pending"
            elif after.owner == "security":
                state = "repaired"
            else:
                state = "readable_not_migrated"
        else:
            state = answered.reason or "missing"
    return {
        "before": before,
        "state": state,
        "migrated": migrated,
        "summary": _keychain_repair_summary(state, migrated=migrated, command=command),
    }


KEYCHAIN_PENDING_STATES = frozenset(
    {"keychain_prompt_pending", "still_pending", "readable_not_migrated"}
)


def repair_keychain(repo: str | Path = ".", *, interactive: bool = False) -> dict[str, Any]:
    """Move every macOS Keychain credential of this repo to ``/usr/bin/security``.

    Every other command reads with keychain interaction disabled, so an item
    this mb install is not yet trusted to read reports
    ``keychain_prompt_pending`` instead of waiting on a dialog. This is the one
    place that dialog may appear, and only when the caller passes
    ``interactive=True`` from a real terminal. Each successful read migrates
    the item, so it is asked about at most once. Values are never returned.
    """

    target = Path(repo).resolve()
    items: list[dict[str, Any]] = []
    for provider_id, field, ref in _recorded_keychain_refs(target):
        items.append(
            {
                "provider": provider_id,
                "field": field,
                **_repair_keychain_ref(
                    ref, interactive=interactive, command=KEYCHAIN_REPAIR_COMMAND
                ),
            }
        )
    pending = [item for item in items if item["state"] in KEYCHAIN_PENDING_STATES]
    failed = [item for item in items if item["state"] not in {"ready", "repaired", "missing"}]
    return {
        "ok": not failed,
        "repo": str(target),
        "interactive": interactive,
        "items": items,
        "pending": len(pending),
        "safe_to_share": True,
        "repair_command": KEYCHAIN_REPAIR_COMMAND if pending else "",
    }


def _keychain_ref_owners(repo: Path) -> dict[str, dict[str, str]]:
    """Map recorded keychain refs to the hub and provider that use them.

    Sources, first label wins: ``repo`` itself, then every hub checkout in the
    ``mb fleet`` hub list. A hub list that is missing or invalid, or a source
    that is not a business repo, adds nothing. Reads metadata only.
    """

    sources: list[tuple[str, Path]] = [(repo.name, repo)]
    from mb import fleet as fleet_mod

    try:
        hubs = fleet_mod.load_config()["hubs"]
    except (fleet_mod.FleetConfigError, OSError, ValueError):
        hubs = []
    for hub in hubs:
        for checkout in (hub.get("checkout"), hub.get("connect_checkout")):
            if isinstance(checkout, Path) and checkout.is_dir():
                sources.append((str(hub["name"]), checkout.resolve()))
    owners: dict[str, dict[str, str]] = {}
    for label, checkout in sources:
        try:
            recorded = _recorded_keychain_refs(checkout)
        except (ValueError, OSError):
            continue
        for provider_id, field, ref in recorded:
            owners.setdefault(
                ref,
                {"hub": label, "hub_path": str(checkout), "provider": provider_id, "field": field},
            )
    return owners


def _ref_provider_field(ref: str) -> tuple[str, str]:
    """Provider and field from an ``mainbranch://<digest>/<provider>/<field>`` ref."""

    parts = ref.removeprefix("mainbranch://").split("/")
    if ref.startswith("mainbranch://") and len(parts) == 3:
        return parts[1], parts[2]
    return "", ""


def repair_keychain_all(repo: str | Path = ".", *, interactive: bool = False) -> dict[str, Any]:
    """Repair every Main Branch item in the macOS Keychain in one pass.

    Lists the ``mainbranch`` service's items by attributes only (no values, no
    dialog), then runs each through the same path as ``repair_keychain``. A
    staged copy (``<ref>.mbstage``) is not repaired itself: its ref is read,
    which finishes or undoes the interrupted move. Items are labelled with the
    hub and provider when a known hub records the ref, otherwise by the ref.

    A listing cut at the helper's cap, or one that does not say it is whole
    (a helper from another mb version), is never a clean pass: the result says
    ``complete: false`` with how many items were left out when known, is not
    ``ok``, and points at the per-hub repair for the rest, since a rerun lists
    the same first items again.
    """

    target = Path(repo).resolve()
    listing = list_keychain_refs()
    listed = listing.refs
    refs = {ref for ref in listed if not ref.endswith(STAGE_SUFFIX)}
    staged_only = {
        ref.removesuffix(STAGE_SUFFIX) for ref in listed if ref.endswith(STAGE_SUFFIX)
    } - refs
    owners = _keychain_ref_owners(target)
    items: list[dict[str, Any]] = []
    for ref in sorted(refs | staged_only):
        owner = owners.get(ref)
        provider_id, field = (
            (owner["provider"], owner["field"]) if owner else _ref_provider_field(ref)
        )
        items.append(
            {
                "hub": owner["hub"] if owner else "",
                "hub_path": owner["hub_path"] if owner else "",
                "provider": provider_id,
                "field": field,
                "ref": ref,
                "staged_only": ref in staged_only,
                **_repair_keychain_ref(
                    ref, interactive=interactive, command=KEYCHAIN_REPAIR_ALL_COMMAND
                ),
            }
        )
    counts: dict[str, int] = {}
    for item in items:
        counts[item["state"]] = counts.get(item["state"], 0) + 1
    pending = [item for item in items if item["state"] in KEYCHAIN_PENDING_STATES]
    failed = [item for item in items if item["state"] not in {"ready", "repaired", "missing"}]
    # None: the helper did not say how many it found, so the gap is unknown.
    unlisted: int | None = 0
    if not listing.complete:
        unlisted = listing.found - len(listed) if listing.found is not None else None
    repair_command = ""
    if pending:
        repair_command = KEYCHAIN_REPAIR_ALL_COMMAND
    elif not listing.complete:
        # A rerun of --all lists the same first items, so name the per-hub path.
        repair_command = KEYCHAIN_REPAIR_COMMAND
    return {
        "ok": not failed and listing.complete,
        "complete": listing.complete,
        "listed": len(listed),
        "unlisted": unlisted,
        "list_limit": listing.limit,
        "scope": "all",
        "repo": str(target),
        "interactive": interactive,
        "items": items,
        "total": len(items),
        "counts": dict(sorted(counts.items())),
        "pending": len(pending),
        "unmapped": sum(1 for item in items if not item["hub"]),
        "safe_to_share": True,
        "repair_command": repair_command,
    }


def _keychain_repair_summary(
    state: str, *, migrated: bool = False, command: str = KEYCHAIN_REPAIR_COMMAND
) -> str:
    moved = "moved to the macOS security tool; Python changes no longer prompt"
    if state == "ready":
        return (
            moved if migrated else "owned by the macOS security tool; Python changes do not prompt"
        )
    if state == "repaired":
        return f"allowed and {moved}"
    if state == "readable_not_migrated":
        return (
            "readable by this Python only; the move to the macOS security tool did not "
            f"finish, so a Python change would prompt again: run `{command}` again"
        )
    if state == "still_pending":
        return (
            "read once, but unattended reads still need a prompt: choose Always Allow "
            f"(not Allow) and run `{command}` again"
        )
    if state == "missing":
        return "no stored value"
    return _backend_repair(state)["summary"]


def render_keychain_repair(result: dict[str, Any]) -> None:
    if result.get("scope") == "all":
        _render_keychain_repair_all(result)
        return
    print(f"mb connect repair --keychain  {result['repo']}")
    if not result["items"]:
        print("no macOS Keychain credentials are recorded for this repo")
    for item in result["items"]:
        note = item["summary"]
        if item["before"] != item["state"]:
            note = f"{note} (was {state_label(item['before'])})"
        print(f"  {item['provider']}.{item['field']}: {state_label(item['state'])}  {note}")
    if result.get("repair_command"):
        print(
            f"next: run `{result['repair_command']}` from a terminal and choose Always Allow "
            "when macOS asks"
        )


def _render_keychain_repair_all(result: dict[str, Any]) -> None:
    print("mb connect repair --keychain --all  (every Main Branch item in the macOS Keychain)")
    if not result["items"]:
        print("no Main Branch items in the macOS Keychain")
    for item in result["items"]:
        where = item["hub"] or item["ref"]
        name = f"{item['provider']}.{item['field']}" if item["provider"] else "item"
        note = item["summary"]
        if item["before"] != item["state"]:
            note = f"{note} (was {state_label(item['before'])})"
        if item["staged_only"]:
            note = f"{note}; recovered from an interrupted move"
        print(f"  {where}  {name}: {state_label(item['state'])}  {note}")
    counts = ", ".join(f"{count} {state_label(state)}" for state, count in result["counts"].items())
    print(
        f"summary: {result['total']} items"
        + (f" ({counts})" if counts else "")
        + f", {result['pending']} pending"
    )
    if result["unmapped"]:
        print(
            f"{result['unmapped']} item(s) are shown by ref: no hub in this repo or the "
            "`mb fleet` hub list records them"
        )
    if not result["complete"]:
        if result["unlisted"] is None:
            reason = (
                f"the keychain listing did not say whether it is complete ({result['listed']} "
                "listed; a helper from another mb version does this, and `mb update` fixes it)"
            )
        else:
            reason = (
                "the keychain holds more Main Branch items than one pass lists "
                f"({result['listed']} listed, {result['unlisted']} not checked)"
            )
        print(
            f"incomplete: {reason}. Run `{KEYCHAIN_REPAIR_COMMAND}` from a terminal in each "
            "hub for the rest"
        )
    if result.get("repair_command"):
        print(
            f"next: run `{result['repair_command']}` from a terminal and choose Always Allow "
            "when macOS asks"
        )


def _entry_secret_probe(
    entry: dict[str, Any], field: str, *, deadline: float | None = None
) -> SecretProbe:
    stored_secrets = entry.get("secrets") if isinstance(entry.get("secrets"), dict) else {}
    raw = stored_secrets.get(field) if isinstance(stored_secrets, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    ref = str(raw.get("ref") or "")
    backend = str(raw.get("backend") or "local-file")
    return _probe_secret_ref(backend, ref, deadline=deadline)


def _entry_secret_probes(
    provider: Provider, entry: dict[str, Any], *, deadline: float | None = None
) -> dict[str, SecretProbe]:
    return {
        field: _entry_secret_probe(entry, field, deadline=deadline)
        for field in provider.required_secrets
    }


def _entry_secret_value(entry: dict[str, Any], field: str) -> str:
    return _entry_secret_probe(entry, field).value


def _stored_secret(provider: Provider, entry: dict[str, Any]) -> str:
    if not provider.required_secrets:
        return ""
    return _entry_secret_value(entry, provider.required_secrets[0])


def read_token(provider_id: str, repo: str | Path = ".") -> dict[str, Any]:
    """Resolve the stored primary credential for scripted consumers.

    The returned ``token`` exists to be written to stdout exactly once;
    callers must never log it, persist it, or embed it in shareable output.
    Falls back to user scope when the repo config has no entry, so worktrees
    and scheduled tasks resolve the same credential as the primary checkout.
    A `google` entry with an OAuth grant returns a freshly minted access
    token instead of the stored one; the grant itself is never returned.
    """
    provider = resolve_provider(provider_id, repo)
    if not provider.required_secrets:
        raise ValueError(f"provider {provider.id!r} stores no secrets")
    field = provider.required_secrets[0]
    target = Path(repo).resolve()
    config = _read_config(target)
    identity = _repo_identity(target)
    repo_id = str(config.get("repo_id") or identity["repo_id"])
    entry = config["providers"].get(provider.id)
    source = "repo"
    if not isinstance(entry, dict):
        entry = _user_scope_provider_entry(repo_id, provider.id)
        source = "user"
    if _records_oauth_grant(provider, entry):
        # OAuth mode: mint a short-lived access token from the stored grant.
        from mb import google_connect

        return google_connect.read_minted_token(entry, source=source, target=target)
    if not isinstance(entry, dict):
        repair_command = _reconnect_command(provider)
        return {
            "ok": False,
            "provider": provider.id,
            "field": field,
            "source": "",
            "token": "",
            "state": "not_connected",
            "backend_state": "",
            "error": f"{provider.name} is not connected",
            "repair_command": repair_command,
        }
    probe = _entry_secret_probe(entry, field)
    if not probe.backend_ok:
        detail = _backend_repair(probe.reason)
        error = detail["summary"]
        if probe.reason == "keychain_prompt_pending":
            error = f"{provider.name} credential: keychain prompt pending"
        return {
            "ok": False,
            "provider": provider.id,
            "field": field,
            "source": source,
            "token": "",
            "state": BACKEND_FAILURE_STATE,
            "backend_state": probe.reason,
            "error": error,
            "repair_command": detail["repair_command"],
        }
    if not probe.present:
        repair_command = _reconnect_command(provider, entry)
        return {
            "ok": False,
            "provider": provider.id,
            "field": field,
            "source": source,
            "token": "",
            "state": "missing_secret",
            "backend_state": "ready",
            "error": f"{provider.name} credential is missing from the secret store",
            "repair_command": repair_command,
        }
    return {
        "ok": True,
        "provider": provider.id,
        "field": field,
        "source": source,
        "token": probe.value,
        "state": "ready",
        "backend_state": "ready",
        "error": "",
        "repair_command": "",
    }


def read_metadata(provider_id: str, repo: str | Path = ".") -> dict[str, str]:
    """Return a connection's non-secret metadata (for example ``account_id``).

    Resolves the same repo-then-user-scope entry as :func:`read_token`. Returns
    an empty dict when the provider is not connected.
    """
    provider = resolve_provider(provider_id, repo)
    target = Path(repo).resolve()
    config = _read_config(target)
    repo_id = str(config.get("repo_id") or _repo_identity(target)["repo_id"])
    entry = config["providers"].get(provider.id)
    if not isinstance(entry, dict):
        entry = _user_scope_provider_entry(repo_id, provider.id)
    if not isinstance(entry, dict):
        return {}
    metadata = entry.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    return _safe_status_metadata(metadata)


# Variable `mb connect exec` sets when `--env` is not given: the provider's
# first registered env var, except where that name is not what the provider's
# own CLI reads (the Stripe CLI reads STRIPE_API_KEY) or does not hold a token
# (GOOGLE_APPLICATION_CREDENTIALS is a key-file path). Custom providers and
# providers with no registered env var get MB_SECRET.
EXEC_DEFAULT_ENV: dict[str, str] = {
    "stripe": "STRIPE_API_KEY",
    "google": "GOOGLE_OAUTH_TOKEN",
}
EXEC_FALLBACK_ENV = "MB_SECRET"
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def exec_env_name(provider_id: str, override: str = "") -> str:
    """Name of the variable that carries the secret into the child."""
    registered = provider_map().get(provider_id)
    default = EXEC_DEFAULT_ENV.get(provider_id) or (
        registered.env_vars[0] if registered and registered.env_vars else EXEC_FALLBACK_ENV
    )
    name = override.strip() or default
    if not ENV_NAME_RE.fullmatch(name):
        _refuse(
            "exec_env_name",
            "--env must be a shell variable name: letters, digits and underscores, "
            "not starting with a digit.",
        )
    return name


def exec_with_secret(
    provider_id: str,
    command: list[str],
    repo: str | Path = ".",
    *,
    env_name: str = "",
    runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> dict[str, Any]:
    """Run ``command`` with the stored credential in its environment only.

    For an OAuth-mode `google` connection that credential is the short-lived
    access token `read_token` mints; the refresh token never reaches the child.

    No shell is involved and stdin, stdout and stderr are inherited, so the
    secret travels in the child's environment and nowhere else: it is never
    printed, logged, or put in the returned dict. ``returncode`` is the
    child's own exit code.
    """
    if not command:
        _refuse(
            "exec_no_command",
            "mb connect exec needs a command after `--`, for example "
            "`mb connect exec stripe -- stripe products list`.",
        )
    result = read_token(provider_id, repo)
    name = exec_env_name(str(result["provider"]), env_name)
    outcome: dict[str, Any] = {
        "ok": False,
        "provider": result["provider"],
        "env_name": name,
        "returncode": 1,
        "error": "",
        "repair_command": "",
    }
    if result.get("not_recorded_note"):
        # Shown on stderr by the CLI; never part of the child's output.
        outcome["not_recorded_note"] = str(result["not_recorded_note"])
    if not result["ok"]:
        outcome["error"] = result["error"]
        outcome["repair_command"] = result["repair_command"]
        return outcome
    env = dict(os.environ)
    env[name] = result["token"]
    shown = echoable_input(command[0]) or HIDDEN_INPUT
    try:
        completed = runner(command, env=env, check=False)
    except FileNotFoundError:
        outcome["returncode"] = 127
        outcome["error"] = f"command not found: {shown}"
        return outcome
    except PermissionError:
        outcome["returncode"] = 126
        outcome["error"] = f"command is not executable: {shown}"
        return outcome
    except OSError as exc:
        # ENOEXEC (a text file without a shebang) and every other launch
        # failure. Only the errno name goes out: the exception's own text or
        # a traceback could carry the child environment.
        outcome["returncode"] = 126
        reason = errno.errorcode.get(exc.errno or 0, "OSError")
        outcome["error"] = f"command could not be started ({reason}): {shown}"
        return outcome
    returncode = int(completed.returncode)
    # A child killed by a signal reports -N; shells report 128+N.
    outcome["returncode"] = 128 - returncode if returncode < 0 else returncode
    outcome["ok"] = outcome["returncode"] == 0
    return outcome


def stdout_exposes_secret(stream: Any = None) -> bool:
    """Would a raw secret written to ``stream`` land somewhere an agent reads?

    A terminal is read by whoever (or whatever) is watching it, and a pipe
    feeds the secret into another process's text, which is how secrets end up
    in agent transcripts. A redirect to a file is the one scripted path that
    stays allowed. When the descriptor cannot be inspected, assume exposure.
    """
    target = stream if stream is not None else sys.stdout
    try:
        if target.isatty():
            return True
        mode = os.fstat(target.fileno()).st_mode
    except (AttributeError, OSError, ValueError):
        return True
    return stat.S_ISFIFO(mode)


ONEPASSWORD_REF_PREFIX = "op://"
ROTATE_READ_TIMEOUT_SECONDS = 60.0


def _check_source_ref(source: str) -> None:
    """A source is a pointer to the secret, never the secret itself."""
    rule = metadata_value_rule(source)
    if rule:
        _refuse(
            "source_secret_value",
            f"--source looks like a secret (rule: {rule}), not a reference to one. "
            "Nothing was stored. Pass a reference such as op://vault/item/field.",
        )


def _connected_entry(provider: Provider, repo: Path) -> tuple[dict[str, Any] | None, str]:
    config = _read_config(repo)
    entry = config["providers"].get(provider.id)
    if isinstance(entry, dict):
        return entry, "repo"
    repo_id = str(config.get("repo_id") or _repo_identity(repo)["repo_id"])
    user_entry = _user_scope_provider_entry(repo_id, provider.id)
    if isinstance(user_entry, dict):
        return user_entry, "user"
    return None, ""


def _read_onepassword_ref(
    ref: str,
    *,
    which_func: Which | None = None,
    command_runner: CommandRunner | None = None,
) -> str:
    """Read one secret with `op read`. The value is returned, never printed."""
    which = which_func or shutil.which
    run = command_runner or _run_command
    if not which("op"):
        _refuse(
            "rotate_op_missing",
            "the 1Password CLI (`op`) is not installed or not on PATH. Install it and "
            "sign in (`op signin`), then rerun `mb connect rotate`.",
        )
    result = run(["op", "read", "--no-newline", ref], None, ROTATE_READ_TIMEOUT_SECONDS)
    if not result.get("ok"):
        stderr = str(result.get("stderr") or "").lower()
        if any(marker in stderr for marker in ("signed in", "sign in", "signin")):
            _refuse(
                "rotate_op_signed_out",
                "the 1Password CLI is not signed in. Run `op signin` (or unlock the "
                "1Password app), then rerun `mb connect rotate`.",
            )
        _refuse(
            "rotate_op_read_failed",
            f"`op read` could not read the recorded source (exit {result.get('returncode')}). "
            "Check the op:// reference with `mb connect status`, then rerun.",
        )
    value = str(result.get("stdout") or "")
    if value.endswith("\n"):
        value = value[:-1]
    if not value:
        _refuse(
            "rotate_empty_value",
            "the recorded source returned an empty value. Nothing was stored.",
        )
    return value


def rotate_provider(
    provider_id: str,
    repo: str | Path = ".",
    *,
    which_func: Which | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Re-read a credential from its recorded source, store it, then probe it."""
    provider = resolve_provider(provider_id, repo)
    target = Path(repo).resolve()
    if not provider.required_secrets:
        _refuse("rotate_no_secret", f"{provider.name} stores no secret to rotate.")
    entry, _where = _connected_entry(provider, target)
    # Google connects with a sign-in, which has no source to re-read; only a
    # legacy access-token entry keeps the --token-stdin and --source path.
    google_sign_in = provider.id == "google" and not (
        entry is not None
        and _entry_records_slot(entry, "access_token")
        and not _records_oauth_grant(provider, entry)
    )
    if entry is None:
        if google_sign_in:
            _refuse(
                "rotate_not_connected",
                f"{provider.name} is not connected. Sign in with `{GOOGLE_SIGN_IN_COMMAND}`; "
                "a sign-in has no source to re-read, so it is renewed rather than rotated. "
                "Nothing was changed.",
            )
        _refuse(
            "rotate_not_connected",
            f"{provider.name} is not connected. Connect it with a source first: "
            f"`{_connect_command(provider, token_stdin=True)} --source op://vault/item/field`.",
        )
    if _records_oauth_grant(provider, entry):
        from mb import google_connect

        grant_slot = entry.get("secrets", {}).get(GOOGLE_OAUTH_GRANT_SLOT)
        if isinstance(grant_slot, dict) and grant_slot.get("ref"):
            probe = _probe_secret_ref(
                str(grant_slot.get("backend") or "local-file"), str(grant_slot["ref"])
            )
            if not probe.backend_ok:
                detail = _backend_repair(probe.reason)
                _refuse(
                    "rotate_backend_unavailable",
                    f"{provider.name} credentials cannot be read. {detail['summary']} "
                    f"{detail['repair']} The renewal can run once the store unlocks. "
                    "Nothing was changed.",
                )
        _refuse(
            "rotate_oauth_use_reauth",
            f"this {provider.name} connection uses a Google sign-in (OAuth), which has no "
            f"source to re-read. Renew it with `{google_connect.reauth_command(entry)}` when "
            "status says reauth_required. Nothing was changed.",
        )
    raw_metadata = entry.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    source = str(metadata.get("source") or "").strip()
    if not source and google_sign_in:
        _refuse(
            "rotate_no_source",
            f"{provider.name} has no stored credential to rotate. Sign in with "
            f"`{GOOGLE_SIGN_IN_COMMAND}`; a sign-in has no source to re-read, so it is "
            "renewed rather than rotated. Nothing was changed.",
        )
    if not source:
        _refuse(
            "rotate_no_source",
            f"{provider.name} has no recorded source, so Main Branch does not know where "
            "to read the new credential from. Record one with "
            f"`mb connect {provider.id} --source op://vault/item/field`, or reconnect "
            f"the new credential with `{_connect_command(provider, token_stdin=True)}`.",
        )
    if not source.startswith(ONEPASSWORD_REF_PREFIX):
        _refuse(
            "rotate_unsupported_source",
            "mb connect rotate reads only 1Password references (op://...). For any other "
            f"source, {_reconnect_step(provider, google_sign_in)}.",
        )
    secret = _read_onepassword_ref(source, which_func=which_func, command_runner=command_runner)
    raw_secrets = entry.get("secrets")
    secrets = raw_secrets if isinstance(raw_secrets, dict) else {}
    raw_primary = secrets.get(provider.required_secrets[0])
    primary = raw_primary if isinstance(raw_primary, dict) else {}
    backend = str(primary.get("backend") or "") or None
    connected = connect_provider(
        provider.id,
        target,
        token=secret,
        account_label=str(entry.get("account_label") or ""),
        metadata_pairs=[f"{key}={value}" for key, value in metadata.items()],
        secret_backend=backend,
        scope=str(entry.get("scope") or "repo"),
        custom=provider.category == "custom",
    )
    tested = test_provider(
        provider.id,
        target,
        which_func=which_func,
        command_runner=command_runner,
        record_in_tracked_config=True,
    )
    return {
        "ok": bool(connected["ok"]) and bool(tested["ok"]),
        "provider": provider.id,
        "source_kind": "1password",
        "stored": bool(connected["ok"]),
        "provider_verified": bool(tested.get("provider_verified")),
        "validation": tested.get("validation") or {},
        "status": tested["status"],
        "safe_to_share": True,
    }


def _provider_error_summary(provider_name: str, upstream: dict[str, Any]) -> str:
    status = upstream.get("http_status")
    messages = [str(item) for item in upstream.get("error_messages", []) if str(item)]
    base = messages[0] if messages else ""
    if status in {400, 401}:
        return f"{provider_name} rejected the credential. Create a fresh token and reconnect it."
    if status == 403:
        return (
            f"{provider_name} accepted the request shape but denied access. "
            "Check token permissions, account binding, and account_id metadata."
        )
    if status == 404:
        return (
            f"{provider_name} could not find the requested account/token resource. "
            "Check account_id metadata and token ownership."
        )
    if status == 429:
        return f"{provider_name} rate-limited validation. Retry `mb connect test` later."
    if isinstance(status, int) and status >= 500:
        return (
            f"{provider_name} validation returned HTTP {status}. Retry after the provider recovers."
        )
    if base:
        return f"{provider_name} validation failed: {base}"
    return f"{provider_name} validation could not complete."


def _header_secret_candidates(headers: dict[str, str] | None) -> list[str]:
    if not headers:
        return []
    candidates: list[str] = []
    for key, value in headers.items():
        key_text = str(key).lower()
        value_text = str(value)
        if not value_text:
            continue
        if key_text == "authorization":
            candidates.append(value_text)
            parts = value_text.split()
            if len(parts) >= 2 and parts[0].lower() == "bearer":
                candidates.append(parts[1])
        elif any(part in key_text for part in SENSITIVE_KEY_PARTS):
            candidates.append(value_text)
    return candidates


def _redact_sensitive_text(value: Any, secret_values: tuple[str, ...] = ()) -> str:
    text = str(value)
    for secret in sorted(set(secret_values), key=len, reverse=True):
        if len(secret) >= 4:
            text = text.replace(secret, SECRET_REPLACEMENT)
    text = BEARER_SECRET_RE.sub(f"Bearer {SECRET_REPLACEMENT}", text)
    text = SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{match.group(3) or ''}{SECRET_REPLACEMENT}",
        text,
    )
    text = SECRET_PHRASE_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2) or ''}{SECRET_REPLACEMENT}",
        text,
    )
    return text


def _extract_upstream_errors(
    payload: Any, secret_values: tuple[str, ...] = ()
) -> tuple[list[str], list[str]]:
    if not isinstance(payload, dict):
        return [], []
    codes: list[str] = []
    messages: list[str] = []
    for field in ("errors", "messages"):
        raw_items = payload.get(field)
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            code = item.get("code")
            message = item.get("message")
            if code not in {None, ""}:
                codes.append(str(code))
            if message:
                messages.append(_redact_sensitive_text(message, secret_values))
    return codes, messages


RESPONSE_HEADER_MAX_CHARS = 512
PROVIDER_REDIRECT_RULE = "provider_unexpected_redirect"


def _http_get_json(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    provider_name: str = "provider",
    endpoint_family: str = "unknown",
    response_headers: tuple[str, ...] = (),
) -> dict[str, Any]:
    """GET ``url`` and report a share-safe outcome.

    ``response_headers`` names non-secret response headers to hand back under
    ``headers`` (for example GitHub's ``X-OAuth-Scopes``). The body is never
    returned.
    """
    request = urllib.request.Request(url, headers=headers or {})
    secret_values = tuple(_header_secret_candidates(headers))

    def picked(raw: Any) -> dict[str, str]:
        # A response header is provider-controlled text: redact anything the
        # request sent as a secret and cap its length before handing it back.
        found: dict[str, str] = {}
        for name in response_headers:
            value = raw.get(name) if raw is not None else None
            if value is not None:
                text = _redact_sensitive_text(value, secret_values)
                found[name] = text[:RESPONSE_HEADER_MAX_CHARS]
        return found

    upstream: dict[str, Any] = {
        "endpoint_family": endpoint_family,
        "http_status": None,
        "response_received": False,
        "error_codes": [],
        "error_messages": [],
        "safe_to_share": True,
    }
    got_headers: dict[str, str] = {}
    try:
        with http_safe.open_no_redirect(request, timeout=VALIDATION_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, "status", 0) or 0)
            body = response.read(8192)
            got_headers = picked(getattr(response, "headers", None))
    except urllib.error.HTTPError as exc:
        got_headers = picked(exc.headers)
        if http_safe.is_redirect(int(exc.code)):
            # The credential is never sent to a second URL. A redirect says
            # nothing about the credential, so it is not "invalid" and nothing
            # asks the person to reconnect.
            with suppress(OSError):
                exc.close()
            upstream.update(
                {
                    "http_status": int(exc.code),
                    "response_received": True,
                    "rule": PROVIDER_REDIRECT_RULE,
                }
            )
            return {
                "ok": False,
                "state": "unvalidated",
                "summary": (
                    f"{provider_name} answered with a redirect (HTTP {int(exc.code)}), which "
                    "Main Branch never follows with a credential. Retry later."
                ),
                "upstream": upstream,
                "safe_to_share": True,
                "headers": got_headers,
            }
        body = b""
        with suppress(OSError):
            body = exc.read(8192)
        payload: Any = {}
        if body:
            with suppress(json.JSONDecodeError, UnicodeDecodeError):
                payload = json.loads(body.decode("utf-8"))
        codes, messages = _extract_upstream_errors(payload, secret_values)
        upstream.update(
            {
                "http_status": int(exc.code),
                "response_received": True,
                "error_codes": codes,
                "error_messages": messages,
            }
        )
        state = "invalid" if exc.code in {400, 401, 403, 404} else "unvalidated"
        return {
            "ok": False,
            "state": state,
            "summary": _provider_error_summary(provider_name, upstream),
            "upstream": upstream,
            "safe_to_share": True,
            "headers": got_headers,
        }
    except (urllib.error.URLError, TimeoutError, OSError):
        return {
            "ok": False,
            "state": "unvalidated",
            "summary": f"{provider_name} validation could not reach the service.",
            "upstream": upstream,
            "safe_to_share": True,
            "headers": got_headers,
        }
    payload = {}
    if body:
        with suppress(json.JSONDecodeError, UnicodeDecodeError):
            payload = json.loads(body.decode("utf-8"))
    codes, messages = _extract_upstream_errors(payload, secret_values)
    upstream.update(
        {
            "http_status": status,
            "response_received": True,
            "error_codes": codes,
            "error_messages": messages,
        }
    )
    if status < 200 or status >= 300:
        state = "invalid" if status in {400, 401, 403, 404} else "unvalidated"
        return {
            "ok": False,
            "state": state,
            "summary": _provider_error_summary(provider_name, upstream),
            "upstream": upstream,
            "safe_to_share": True,
            "headers": got_headers,
        }
    if isinstance(payload, dict) and payload.get("success") is False:
        return {
            "ok": False,
            "state": "invalid",
            "summary": _provider_error_summary(provider_name, upstream),
            "upstream": upstream,
            "safe_to_share": True,
            "headers": got_headers,
        }
    token_status = ""
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        token_status = str(payload["result"].get("status") or "")
    if token_status and token_status != "active":
        upstream["token_status"] = token_status
        return {
            "ok": False,
            "state": "invalid",
            "summary": f"{provider_name} token is {token_status}; reconnect an active token.",
            "upstream": upstream,
            "safe_to_share": True,
            "headers": got_headers,
        }
    return {
        "ok": True,
        "state": "ready",
        "summary": f"{provider_name} credential validated with provider.",
        "upstream": upstream,
        "safe_to_share": True,
        "headers": got_headers,
    }


def _meta_env(secret: str, metadata: dict[str, Any]) -> dict[str, str]:
    keep = ("PATH", "HOME", "LANG", "LC_ALL", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env["ACCESS_TOKEN"] = secret
    env["AD_ACCOUNT_ID"] = str(metadata.get("ad_account_id") or "").strip()
    business_id = str(metadata.get("business_id") or "").strip()
    if business_id:
        env["BUSINESS_ID"] = business_id
    return env


def _safe_command_check(name: str, args: list[str], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "command": " ".join(args),
        "ok": bool(result.get("ok")),
        "returncode": int(result.get("returncode") or 0),
        "stdout_present": bool(str(result.get("stdout") or "")),
        "stderr_present": bool(str(result.get("stderr") or "")),
        "safe_to_share": True,
    }


def _run_meta_command(
    run: CommandRunner,
    args: list[str],
    repo: Path,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        return run(args, repo, VALIDATION_TIMEOUT_SECONDS, env=env)
    except TypeError:
        return run(args, repo, VALIDATION_TIMEOUT_SECONDS)


def _looks_like_admin_approval(result: dict[str, Any]) -> bool:
    text = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}".lower()
    admin_words = ("admin", "business admin", "administrator")
    approval_words = ("approval", "approve", "pending", "waiting")
    return any(word in text for word in admin_words) and any(
        word in text for word in approval_words
    )


def _meta_validation_result(
    *,
    ok: bool,
    state: str,
    checked_at: str,
    summary: str,
    checks: list[dict[str, Any]],
    repair: str = "",
    repair_command: str = "",
) -> dict[str, Any]:
    return {
        "ok": ok,
        "state": state,
        "checked_at": checked_at,
        # Meta's only success path is a passing read-only account smoke, which
        # is a real provider call.
        "provider_verified": ok,
        "summary": summary,
        "repair": repair,
        "repair_command": repair_command,
        "safe_to_share": True,
        "upstream": {
            "endpoint_family": "meta_ads_cli",
            "checks": checks,
            "safe_to_share": True,
        },
    }


def _validate_meta_with_cli(
    provider: Provider,
    secret: str,
    metadata: dict[str, Any],
    repo: Path,
    *,
    which_func: Which | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    checked_at = _now()
    checks: list[dict[str, Any]] = []
    prereq_state = _meta_prerequisite_state(
        which_func=which_func,
        command_runner=command_runner,
    )
    if prereq_state:
        repair = _meta_repair(prereq_state)
        checks.append(
            {
                "name": "local_prerequisites",
                "ok": False,
                "state": prereq_state,
                "safe_to_share": True,
            }
        )
        return _meta_validation_result(
            ok=False,
            state=prereq_state,
            checked_at=checked_at,
            summary=repair["summary"],
            checks=checks,
            repair=repair["repair"],
            repair_command=repair["repair_command"],
        )
    if not secret:
        repair = _meta_repair("missing_secret", ["access_token"])
        return _meta_validation_result(
            ok=False,
            state="missing_secret",
            checked_at=checked_at,
            summary=repair["summary"],
            checks=checks,
            repair=repair["repair"],
            repair_command=repair["repair_command"],
        )
    ad_account_id = str(metadata.get("ad_account_id") or "").strip()
    if not ad_account_id:
        repair = _meta_repair("missing_metadata")
        return _meta_validation_result(
            ok=False,
            state="missing_metadata",
            checked_at=checked_at,
            summary=repair["summary"],
            checks=checks,
            repair=repair["repair"],
            repair_command=repair["repair_command"],
        )

    run = command_runner or _run_command
    env = _meta_env(secret, metadata)
    auth_args = ["meta", "auth", "status"]
    auth = _run_meta_command(run, auth_args, repo, env)
    checks.append(_safe_command_check("auth_status", auth_args, auth))
    if not auth.get("ok"):
        state = "waiting_for_admin_approval" if _looks_like_admin_approval(auth) else "auth_failed"
        repair = _meta_repair(state)
        return _meta_validation_result(
            ok=False,
            state=state,
            checked_at=checked_at,
            summary=repair["summary"],
            checks=checks,
            repair=repair["repair"],
            repair_command=repair["repair_command"],
        )

    for name, args, needs_business_id in META_READ_SMOKE_COMMANDS:
        if needs_business_id and not str(metadata.get("business_id") or "").strip():
            checks.append(
                {
                    "name": name,
                    "command": " ".join(args),
                    "ok": True,
                    "skipped": True,
                    "reason": "business_id metadata not set",
                    "safe_to_share": True,
                }
            )
            continue
        result = _run_meta_command(run, args, repo, env)
        checks.append(_safe_command_check(name, args, result))
        if not result.get("ok"):
            state = (
                "waiting_for_admin_approval"
                if _looks_like_admin_approval(result)
                else "read_smoke_failed"
            )
            repair = _meta_repair(state)
            return _meta_validation_result(
                ok=False,
                state=state,
                checked_at=checked_at,
                summary=repair["summary"],
                checks=checks,
                repair=repair["repair"],
                repair_command=repair["repair_command"],
            )

    return _meta_validation_result(
        ok=True,
        state="ready",
        checked_at=checked_at,
        summary=f"{provider.name} read-only account smoke passed.",
        checks=checks,
    )


# Read-only resources the Stripe probe lists to learn what a key may read.
# Each is a GET with limit=1; the body is never returned.
STRIPE_SCOPE_PROBES: tuple[tuple[str, str], ...] = (
    ("products", "https://api.stripe.com/v1/products?limit=1"),
    ("prices", "https://api.stripe.com/v1/prices?limit=1"),
    ("customers", "https://api.stripe.com/v1/customers?limit=1"),
    ("charges", "https://api.stripe.com/v1/charges?limit=1"),
    ("balance", "https://api.stripe.com/v1/balance"),
)
GITHUB_API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "mainbranch-mb-connect",
}
GITHUB_TOKEN_KINDS: tuple[tuple[str, str], ...] = (
    ("github_pat_", "fine_grained"),
    ("ghp_", "classic"),
    ("gho_", "oauth"),
    ("ghu_", "app_user"),
    ("ghs_", "app_installation"),
)
# Share-safe probe facts carried from a probe into the recorded validation.
PROBE_DETAIL_KEYS: tuple[str, ...] = (
    "scopes",
    "token_kind",
    "token_scopes",
    "token_scopes_withheld",
)
GITHUB_TOKEN_KIND_NAMES = frozenset({kind for _prefix, kind in GITHUB_TOKEN_KINDS} | {"unknown"})
GA4_PROPERTY_RE = re.compile(r"^(?:properties/)?(\d{1,20})$")


def _probe_stripe(provider: Provider, secret: str) -> dict[str, Any]:
    """Which of a fixed set of read resources does this key allow?

    A 2xx means allowed and a 403 means the key is valid but restricted from
    that resource. A 401 anywhere means Stripe rejected the key itself.
    """
    scopes: dict[str, str] = {}
    first_upstream: dict[str, Any] = {}
    for resource, url in STRIPE_SCOPE_PROBES:
        result = _http_get_json(
            url,
            {"Authorization": f"Bearer {secret}"},
            provider_name=provider.name,
            endpoint_family=f"stripe_{resource}_read",
        )
        raw_upstream = result.get("upstream")
        upstream: dict[str, Any] = raw_upstream if isinstance(raw_upstream, dict) else {}
        if not first_upstream:
            first_upstream = upstream
        status = upstream.get("http_status")
        if status == 401:
            return {**result, "state": "invalid", "scopes": scopes}
        if result.get("ok"):
            scopes[resource] = "allowed"
        elif status == 403:
            scopes[resource] = "refused"
        else:
            scopes[resource] = "unknown"
    allowed = [name for name, verdict in scopes.items() if verdict == "allowed"]
    refused = [name for name, verdict in scopes.items() if verdict == "refused"]
    if not allowed and not refused:
        return {
            "ok": False,
            "state": "unvalidated",
            "summary": "Stripe validation could not reach the service or got no clear answer.",
            "upstream": first_upstream,
            "scopes": scopes,
        }
    if allowed:
        summary = f"Stripe key validated; reads allowed: {', '.join(allowed)}"
    else:
        summary = "Stripe key validated, but every probed read was refused"
    if refused:
        summary += f"; refused: {', '.join(refused)}"
    return {
        "ok": True,
        "state": "ready",
        "summary": summary + ".",
        "upstream": first_upstream,
        "scopes": scopes,
    }


def _github_token_kind(secret: str) -> str:
    for prefix, kind in GITHUB_TOKEN_KINDS:
        if secret.startswith(prefix):
            return kind
    return "unknown"


GITHUB_SCOPE_RE = re.compile(r"[a-z][a-z_]{0,31}(?::[a-z][a-z_]{0,31})?")


def _probe_github(provider: Provider, secret: str) -> dict[str, Any]:
    """Authenticated-user read, plus the scopes GitHub reports for the token."""
    result = _http_get_json(
        "https://api.github.com/user",
        {"Authorization": f"Bearer {secret}", **GITHUB_API_HEADERS},
        provider_name=provider.name,
        endpoint_family="github_authenticated_user",
        response_headers=("X-OAuth-Scopes",),
    )
    kind = _github_token_kind(secret)
    raw_headers = result.get("headers")
    headers: dict[str, Any] = raw_headers if isinstance(raw_headers, dict) else {}
    raw_scopes = headers.get("X-OAuth-Scopes")
    reported = (
        [scope.strip() for scope in str(raw_scopes).split(",") if scope.strip()]
        if raw_scopes is not None
        else []
    )
    # Only scope names in GitHub's own grammar ("repo", "read:org") go into
    # output and stored validation; anything else is counted, never shown.
    token_scopes = [scope for scope in reported if GITHUB_SCOPE_RE.fullmatch(scope)]
    withheld = len(reported) - len(token_scopes)
    probed = {**result, "token_kind": kind, "token_scopes": token_scopes}
    if withheld:
        probed["token_scopes_withheld"] = withheld
    if result.get("ok"):
        if raw_scopes is not None:
            listed = ", ".join(token_scopes) or "none"
            note = f" ({withheld} unrecognized value(s) withheld)" if withheld else ""
            probed["summary"] = f"GitHub token authenticated; scopes: {listed}{note}."
        else:
            probed["summary"] = (
                "GitHub token authenticated. GitHub does not list a fine-grained or app "
                "token's permissions through the API; check them in the token's settings."
            )
    return probed


def _probe_ga4(provider: Provider, secret: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """Read one property's metadata from the GA4 Admin API."""
    raw_property = str(metadata.get("property_id") or "").strip()
    match = GA4_PROPERTY_RE.fullmatch(raw_property)
    if not match:
        reason = "is not a numeric GA4 property id" if raw_property else "is not recorded"
        return {
            "ok": False,
            "state": "unvalidated",
            "summary": f"GA4 validation needs `property_id` metadata, which {reason}.",
            "repair": (
                "Find the numeric property id under GA4 Admin > Property details, then run "
                "`mb connect ga4 --metadata property_id=<property-id>` and "
                "`mb connect test ga4`."
            ),
            "repair_command": "mb connect ga4 --metadata property_id=<property-id>",
            "upstream": {
                "endpoint_family": "ga4_property_read",
                "http_status": None,
                "response_received": False,
                "error_codes": [],
                "error_messages": [],
                "safe_to_share": True,
            },
        }
    return _http_get_json(
        f"https://analyticsadmin.googleapis.com/v1beta/properties/{match.group(1)}",
        {"Authorization": f"Bearer {secret}"},
        provider_name=provider.name,
        endpoint_family="ga4_property_read",
    )


def _validate_with_provider(
    provider: Provider,
    secret: str,
    metadata: dict[str, Any] | None = None,
    *,
    repo: Path | None = None,
    which_func: Which | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    checked_at = _now()
    metadata = metadata or {}
    if provider.id == "cloudflare":
        token_type = _cloudflare_token_type(metadata, secret)
        if token_type == "account":
            account_id = str(metadata.get("account_id") or "").strip()
            if not account_id:
                return {
                    "ok": False,
                    "state": "unvalidated",
                    "checked_at": checked_at,
                    "summary": (
                        "Cloudflare account-token validation requires non-secret "
                        "`account_id` metadata."
                    ),
                    "repair": (
                        "Run `mb connect cloudflare --metadata token_type=account "
                        "--metadata account_id=<account-id>`, then "
                        "`mb connect test cloudflare`."
                    ),
                    "repair_command": (
                        "mb connect cloudflare --metadata token_type=account "
                        "--metadata account_id=<account-id>"
                    ),
                    "safe_to_share": True,
                    "upstream": {
                        "endpoint_family": "cloudflare_account_token_verify",
                        "http_status": None,
                        "response_received": False,
                        "error_codes": [],
                        "error_messages": [],
                        "safe_to_share": True,
                    },
                }
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/tokens/verify"
            endpoint_family = "cloudflare_account_token_verify"
        else:
            url = "https://api.cloudflare.com/client/v4/user/tokens/verify"
            endpoint_family = "cloudflare_user_token_verify"
        result = _http_get_json(
            url,
            {"Authorization": f"Bearer {secret}"},
            provider_name=provider.name,
            endpoint_family=endpoint_family,
        )
        raw_upstream = result.get("upstream")
        upstream: dict[str, Any] = raw_upstream if isinstance(raw_upstream, dict) else {}
        if token_type == "account" and upstream.get("http_status") == 404:
            fallback = _http_get_json(
                f"https://api.cloudflare.com/client/v4/accounts/{account_id}",
                {"Authorization": f"Bearer {secret}"},
                provider_name=provider.name,
                endpoint_family="cloudflare_account_read",
            )
            raw_fallback_upstream = fallback.get("upstream")
            fallback_upstream: dict[str, Any] = (
                raw_fallback_upstream if isinstance(raw_fallback_upstream, dict) else {}
            )
            fallback_upstream["fallback_from"] = endpoint_family
            fallback["upstream"] = fallback_upstream
            if fallback.get("ok"):
                fallback["summary"] = (
                    "Cloudflare account-scoped credential validated with account read fallback."
                )
            result = fallback
    elif provider.id == "apify":
        result = _http_get_json(
            "https://api.apify.com/v2/users/me",
            {"Authorization": f"Bearer {secret}"},
            provider_name=provider.name,
            endpoint_family="apify_user_me",
        )
    elif provider.id == "stripe":
        result = _probe_stripe(provider, secret)
    elif provider.id == "github":
        result = _probe_github(provider, secret)
    elif provider.id == "ga4":
        result = _probe_ga4(provider, secret, metadata)
    elif provider.id == "meta":
        return _validate_meta_with_cli(
            provider,
            secret,
            metadata,
            repo or Path.cwd(),
            which_func=which_func,
            command_runner=command_runner,
        )
    else:
        # No safe read-only probe exists for this provider, so the only fact
        # available is that a credential is stored. Saying "ready" here would
        # claim a provider call that never happened.
        return {
            "ok": False,
            "state": UNVERIFIED_STATE,
            "checked_at": checked_at,
            "provider_verified": False,
            "summary": (
                f"{provider.name} has a stored credential, but Main Branch has no "
                "automated way to confirm it works with the provider."
            ),
            "repair": _unverified_repair(provider)["repair"],
            "safe_to_share": True,
        }
    return {
        "ok": bool(result["ok"]),
        "state": str(result["state"]),
        "checked_at": checked_at,
        "provider_verified": bool(result["ok"]),
        "summary": str(result["summary"]),
        "repair": str(result.get("repair") or ""),
        "repair_command": str(result.get("repair_command") or ""),
        "safe_to_share": True,
        "upstream": result.get("upstream", {}),
        **{key: result[key] for key in PROBE_DETAIL_KEYS if key in result},
    }


def _user_scope_not_recorded_detail(
    exc: OSError | UserScopeReadOnlyError | ConfigCorruptError,
) -> str:
    """Why a check could not be written to the user-scope file, for an operator.

    Built from the error number only: no backend text, value or absolute home path.
    """

    shown, cause, fix = _user_scope_record_failure(exc)
    changed = ", so it may have changed" if isinstance(exc, UserScopeRecordRestoreError) else ""
    return f"the user-scope connect file {shown} {cause}{changed}. {fix}, then rerun the check"


def _record_validation(
    target: Path,
    config: dict[str, Any],
    provider_id: str,
    entry: dict[str, Any],
) -> dict[str, Any]:
    """Write a tested entry back: repo metadata, and user scope for a user-scope entry.

    A check only needs to read the user-scope file. When it is read-only, or
    cannot be written (a full disk, an I/O error), the repo metadata is still
    written, the file is left as it was, and this returns the result keys
    that say so (empty when the check was recorded everywhere). A file that
    cannot be read (unreadable or invalid) is different: nothing is recorded
    anywhere, so ``.mb/connect.yaml`` is put back as it was.
    """

    config_path = _checked_config_path(target)
    previous_config = config_path.read_bytes() if config_path.exists() else None
    config["providers"][provider_id] = entry
    _write_config(target, config)
    if entry.get("scope") == "user":
        identity = {
            "source": str(config.get("repo_identity", {}).get("source") or ""),
            "basis_sha256": str(config.get("repo_identity", {}).get("basis_sha256") or ""),
            "repo_id_source": str(config.get("repo_identity", {}).get("repo_id_source") or ""),
        }
        try:
            _write_user_scope_provider(
                str(config.get("repo_id") or _repo_identity(target)["repo_id"]),
                repo_identity=identity,
                provider_id=provider_id,
                entry=entry,
            )
        except UserScopeReadOnlyError:
            return {"recorded": False, "not_recorded_reason": "user_scope_read_only"}
        except ConfigCorruptError as exc:
            # All or nothing: the repo metadata goes back as it was.
            detail = _user_scope_not_recorded_detail(exc)
            if previous_config is not None:
                try:
                    atomic_write_text(config_path, previous_config.decode("utf-8"))
                except OSError:
                    detail += (
                        "; .mb/connect.yaml could not be put back either, so it "
                        "still shows this check"
                    )
            return {
                "recorded": False,
                "not_recorded_reason": "user_scope_write_failed",
                "not_recorded_detail": detail,
                "exit_follows_check": True,
            }
        except OSError as exc:
            return {
                "recorded": False,
                "not_recorded_reason": "user_scope_write_failed",
                "not_recorded_detail": _user_scope_not_recorded_detail(exc),
            }
    return {}


def test_provider(
    provider_id: str,
    repo: str | Path = ".",
    *,
    which_func: Which | None = None,
    command_runner: CommandRunner | None = None,
    record_in_tracked_config: bool = False,
) -> dict[str, Any]:
    """Check a stored credential with the provider and record the outcome.

    The outcome is not written into a git-tracked ``.mb/connect.yaml`` unless
    ``record_in_tracked_config`` (a command that already wrote it, such as
    ``mb connect rotate``).
    """
    provider = resolve_provider(provider_id, repo)
    target = Path(repo).resolve()
    config = _read_config(target)
    entry = config["providers"].get(provider.id)
    deadline = new_credential_deadline()
    probes = (
        _entry_secret_probes(provider, entry, deadline=deadline) if isinstance(entry, dict) else {}
    )
    status = status_provider(
        provider.id,
        target,
        which_func=which_func,
        command_runner=command_runner,
        _credential_deadline=deadline,
        _secret_probes=probes,
    )
    if not isinstance(entry, dict) or status["state"] in {
        "not_connected",
        "missing_secret",
        BACKEND_FAILURE_STATE,
    }:
        return {
            "ok": False,
            "provider": provider.id,
            "stored": bool(status.get("stored")),
            "provider_verified": bool(status.get("provider_verified")),
            "verified_at": str(status.get("verified_at") or ""),
            "status": status,
            "safe_to_share": True,
        }

    if _records_oauth_grant(provider, entry):
        # OAuth-mode `google`: mint from the grant and read each granted
        # product once. A legacy access-token entry never reaches this.
        from mb import google_probe

        return google_probe.test_google(
            provider,
            target,
            source="repo",
            before=status,
            status_again=lambda: status_provider(
                provider.id,
                target,
                which_func=which_func,
                command_runner=command_runner,
                _credential_deadline=deadline,
                _secret_probes=probes,
            ),
        )

    if not provider.required_secrets:
        # Nothing is stored and nothing can be verified with a provider: this
        # readiness is about repo-local metadata, so it never sets
        # `provider_verified`.
        validation = {
            "ok": True,
            "state": "ready",
            "checked_at": _now(),
            "provider_verified": False,
            "summary": f"{provider.name} uses repo-local metadata and has no secret to validate.",
            "safe_to_share": True,
        }
    else:
        secret = probes[provider.required_secrets[0]].value
        if not secret:
            return {
                "ok": False,
                "provider": provider.id,
                "stored": bool(status.get("stored")),
                "provider_verified": bool(status.get("provider_verified")),
                "verified_at": str(status.get("verified_at") or ""),
                "status": status,
                "safe_to_share": True,
            }
        raw_metadata = entry.get("metadata")
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        validation = _validate_with_provider(
            provider,
            secret,
            metadata,
            repo=target,
            which_func=which_func,
            command_runner=command_runner,
        )

    raw_previous = entry.get("validation")
    previous: dict[str, Any] = raw_previous if isinstance(raw_previous, dict) else {}
    provider_verified = bool(validation.get("provider_verified"))
    verified_at = validation["checked_at"] if provider_verified else _verified_at(previous)
    entry["validation"] = {
        "state": validation["state"],
        "checked_at": validation["checked_at"],
        "provider_verified": provider_verified,
        "verified_at": verified_at,
        "summary": validation["summary"],
        "safe_to_share": True,
    }
    if validation.get("repair") or validation.get("repair_command"):
        entry["validation"]["repair"] = validation.get("repair", "")
        entry["validation"]["repair_command"] = validation.get("repair_command", "")
    if isinstance(validation.get("upstream"), dict):
        entry["validation"]["upstream"] = validation["upstream"]
    for key in PROBE_DETAIL_KEYS:
        if key in validation:
            entry["validation"][key] = validation[key]
    entry["last_checked_at"] = validation["checked_at"]
    # Recording writes .mb/connect.yaml; a tracked one is left as it is.
    tracked = not record_in_tracked_config and config_tracked_by_git(target)
    not_recorded: dict[str, Any] = {}
    if not tracked:
        not_recorded = _record_validation(target, config, provider.id, entry)
    status = status_provider(
        provider.id,
        target,
        which_func=which_func,
        command_runner=command_runner,
        _credential_deadline=deadline,
        _secret_probes=probes,
    )
    result: dict[str, Any] = {
        "ok": bool(validation["ok"]),
        "provider": provider.id,
        "stored": bool(status.get("stored")),
        "provider_verified": provider_verified,
        "verified_at": verified_at,
        "validation": entry["validation"],
        "status": status,
        "safe_to_share": True,
    }
    result.update(not_recorded)
    if not_recorded.get("exit_follows_check"):
        # Nothing was recorded, so the stored status is stale: exit on the check itself.
        result["needs_action"] = _check_needs_action(validation, status, provider.id)
    if tracked:
        result["recorded"] = False
        result["not_recorded_reason"] = "connect_yaml_tracked"
        # The CLI exits on the check itself, by the same rule as a status item:
        # a probe-less provider left unverified warns without failing.
        result["needs_action"] = _check_needs_action(validation, status, provider.id)
    return result


def _check_needs_action(
    validation: dict[str, Any], status: dict[str, Any], provider_id: str
) -> bool:
    """The exit rule for a check that was not recorded, by the check's own outcome."""

    return provider_needs_action(
        {
            "ok": bool(validation["ok"]),
            "state": validation["state"],
            "has_probe": bool(status.get("has_probe")),
            "provider": provider_id,
        }
    )


def status_all(
    repo: str | Path = ".",
    *,
    include_all: bool = False,
    github: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = Path(repo).resolve()
    deadline = new_credential_deadline()
    config = _read_config(target)
    identity = _repo_identity(target)
    repo_id = str(config.get("repo_id") or identity["repo_id"])
    user_repo = _read_user_scope()["repos"].get(repo_id)
    user_repo = user_repo if isinstance(user_repo, dict) else {}
    user_providers = user_repo.get("providers")
    configured = {
        str(key).strip().lower().replace("_", "-")
        for key in config["providers"]
        if str(key).strip()
    }
    if isinstance(user_providers, dict):
        configured.update(
            str(key).strip().lower().replace("_", "-") for key in user_providers if str(key).strip()
        )
    providers = []
    for provider in PROVIDERS:
        if include_all or provider.id in configured:
            providers.append(status_provider(provider.id, target, _credential_deadline=deadline))
    custom_ids = sorted(
        provider_id for provider_id in configured if _is_custom_provider_id(provider_id)
    )
    for provider_id in custom_ids:
        providers.append(status_provider(provider_id, target, _credential_deadline=deadline))
    # Every recorded entry counts, including one connected without a token
    # yet (#991): it is configured and reports `missing_secret` to act on.
    connected = [item for item in providers if item.get("configured", item["connected"])]
    unverified = [item for item in connected if item["state"] == UNVERIFIED_STATE]
    # Not read for want of credential budget: nothing is known to be wrong, so
    # it is never counted as broken, but `ok` still refuses to call it healthy.
    not_checked = [item for item in connected if item["state"] == NOT_CHECKED_STATE]
    # A stored-but-unverified provider is not broken: nothing is known to be
    # wrong with it and no repair command would change that. Counting it
    # separately keeps `needs_repair` meaning "there is something to fix",
    # while `ok` still refuses to call the repo fully healthy.
    broken = [
        item
        for item in connected
        if not item["ok"] and item["state"] not in {UNVERIFIED_STATE, NOT_CHECKED_STATE}
    ]
    unvalidated = [item for item in connected if item["state"] == "unvalidated"]
    summary = {
        "configured": len(connected),
        "healthy": len([item for item in connected if item["ok"]]),
        "needs_repair": len(broken),
        "unvalidated": len(unvalidated),
        "unverified": len(unverified),
        "actionable": len([item for item in connected if provider_needs_action(item)]),
    }
    if not_checked:
        # Only present when something was not read, so every other status
        # output keeps exactly the keys it had.
        summary["not_checked"] = len(not_checked)
    return {
        "ok": not broken and not unverified and not not_checked,
        "repo": str(target),
        "config_path": str(_checked_config_path(target)),
        "repo_id": repo_id,
        "user_scope_path": str(_user_scope_path()),
        "providers": providers,
        "github": github or github_context(target),
        "credential_backend": _status_backend_health(providers, deadline=deadline),
        "safe_to_share": True,
        "summary": summary,
    }


def _run_command(
    args: list[str],
    cwd: Path | None = None,
    timeout: float = 5.0,
    *,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError:
        return {"ok": False, "returncode": 127, "stdout": "", "stderr": f"{args[0]} not found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": 124, "stdout": "", "stderr": "command timed out"}
    except subprocess.SubprocessError:
        return {"ok": False, "returncode": 1, "stdout": "", "stderr": "command failed"}
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def github_context(
    repo: str | Path = ".",
    *,
    which_func: Which | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    target = Path(repo).resolve()
    which = which_func or shutil.which
    run = command_runner or _run_command
    if not which("gh"):
        return {
            "ok": False,
            "state": "missing_cli",
            "summary": "GitHub CLI is not installed.",
            "repair": "Install GitHub CLI, then run `gh auth login`.",
            "repair_command": "gh auth login",
            "safe_to_share": True,
        }

    git = run(["git", "rev-parse", "--is-inside-work-tree"], target, 3.0)
    if not git["ok"] or git["stdout"].strip() != "true":
        return {
            "ok": False,
            "state": "not_git_repo",
            "summary": "This folder is not a git repo.",
            "repair": "Run `git init` if this should be a business repo.",
            "repair_command": "git init",
            "safe_to_share": True,
        }

    remote = run(["git", "config", "--get", "remote.origin.url"], target, 3.0)
    remote_value = remote["stdout"].strip() if remote["ok"] else ""
    if "github.com" not in remote_value:
        return {
            "ok": False,
            "state": "missing_github_remote",
            "summary": "This repo does not have a GitHub origin remote.",
            "repair": "Add a GitHub origin remote before relying on GitHub tasks or proposals.",
            "repair_command": "gh repo create --source . --remote origin --push",
            "safe_to_share": True,
        }

    auth = run(["gh", "auth", "status"], target, 5.0)
    if not auth["ok"]:
        full_name = _github_repo_full_name(remote_value)
        reachable = (
            run(["gh", "repo", "view", full_name, "--json", "nameWithOwner"], target, 5.0)
            if full_name
            else {"ok": False, "stdout": "", "stderr": ""}
        )
        if reachable["ok"]:
            return {
                "ok": True,
                "state": "ready_reachable",
                "summary": (
                    "GitHub repo is reachable even though `gh auth status` reports stale "
                    "auth metadata."
                ),
                "repair": "",
                "repair_command": "",
                "repo": full_name,
                "auth_status_ok": False,
                "repo_view_ok": True,
                "safe_to_share": True,
            }
        return {
            "ok": False,
            "state": "unauthenticated",
            "summary": "GitHub CLI is installed but not authenticated.",
            "repair": "Run `gh auth login`.",
            "repair_command": "gh auth login",
            "safe_to_share": True,
        }

    return {
        "ok": True,
        "state": "ready",
        "summary": "GitHub CLI auth and repo remote are ready.",
        "repair": "",
        "repair_command": "",
        "repo": _github_repo_full_name(remote_value),
        "auth_status_ok": True,
        "repo_view_ok": False,
        "safe_to_share": True,
    }


def list_providers(repo: str | Path = ".") -> dict[str, Any]:
    status = status_all(repo, include_all=True)
    by_id = {item["provider"]: item for item in status["providers"]}
    providers = []
    for registry_entry in provider_registry():
        state = by_id[registry_entry["id"]]["state"]
        guidance = PROVIDER_GUIDANCE.get(registry_entry["id"], {})
        providers.append({**registry_entry, **guidance, "state": state, "custom": False})
    custom_providers = []
    for item in status["providers"]:
        if not _is_custom_provider_id(item["provider"]):
            continue
        custom_provider = _custom_provider(item["provider"])
        custom = {
            "id": custom_provider.id,
            "name": custom_provider.name,
            "category": custom_provider.category,
            "auth": custom_provider.auth,
            "required_secrets": list(custom_provider.required_secrets),
            "metadata_fields": list(custom_provider.metadata_fields),
            "description": custom_provider.description,
            "env_vars": list(custom_provider.env_vars),
            "state": item["state"],
            "custom": True,
            "connected": bool(item["connected"]),
            "ready": bool(item["ok"]),
            "account_label": item.get("account_label", ""),
            "scope": item.get("scope", "repo"),
            "repair_command": item.get("repair_command", ""),
        }
        providers.append(custom)
        custom_providers.append(custom)
    return {
        "ok": True,
        "providers": providers,
        "custom_providers": custom_providers,
        "config_path": status["config_path"],
    }


def provider_plan(repo: str | Path = ".") -> dict[str, Any]:
    """Return noob-safe provider setup choices backed by readiness facts."""

    status = status_all(repo, include_all=True)
    by_id = {item["provider"]: item for item in status["providers"]}
    github = status["github"]
    steps: list[dict[str, Any]] = [
        {
            "id": "github",
            "name": "GitHub",
            "category": "work",
            "priority": PROVIDER_GUIDANCE["github"]["priority"],
            "ready": bool(github["ok"]),
            "state": github["state"],
            "summary": github["summary"],
            "why": PROVIDER_GUIDANCE["github"]["why"],
            "use_when": PROVIDER_GUIDANCE["github"]["use_when"],
            "defer_when": PROVIDER_GUIDANCE["github"]["defer_when"],
            "status_command": PROVIDER_GUIDANCE["github"]["status_command"],
            "next_command": github["repair_command"] or "gh auth status",
            "safe_to_share": bool(github.get("safe_to_share", True)),
        }
    ]
    provider_ids = sorted(
        (provider_id for provider_id in PROVIDER_GUIDANCE if provider_id != "github"),
        key=lambda provider_id: int(PROVIDER_GUIDANCE[provider_id]["priority"]),
    )
    for provider_id in provider_ids:
        item = by_id.get(provider_id)
        if item is None:
            continue
        guidance = PROVIDER_GUIDANCE[provider_id]
        steps.append(
            {
                "id": provider_id,
                "name": item["name"],
                "category": normalize_provider(provider_id).category,
                "priority": guidance["priority"],
                "ready": bool(item["ok"]),
                "state": item["state"],
                "summary": item["summary"],
                "why": guidance["why"],
                "use_when": guidance["use_when"],
                "defer_when": guidance["defer_when"],
                "status_command": guidance["status_command"],
                "next_command": (
                    item["repair_command"]
                    or (
                        "mb educational provider-readiness"
                        if item["state"] in {"planned", "readiness"}
                        else f"mb connect test {provider_id}"
                    )
                ),
                "safe_to_share": bool(item.get("safe_to_share", True)),
            }
        )
    ready = len([step for step in steps if step["ready"]])
    return {
        "ok": True,
        "readiness_ok": status["ok"],
        "repo": status["repo"],
        "steps": sorted(steps, key=lambda step: int(step["priority"])),
        "summary": {
            "total": len(steps),
            "ready": ready,
            "needs_setup": len(steps) - ready,
        },
        "safe_to_share": True,
    }


def doctor_check(repo: str | Path = ".", *, status: dict[str, Any] | None = None) -> dict[str, Any]:
    status = status or status_all(repo)
    summary = status["summary"]
    if summary["configured"] == 0:
        return {
            "name": "integration-credentials",
            "ok": True,
            "detail": "no providers connected",
            "severity": "info",
            "repair": "",
            "repair_command": "",
            "safe_to_share": True,
        }
    if summary["needs_repair"]:
        repairs = [
            item
            for item in status["providers"]
            if not item["ok"] and item["state"] != NOT_CHECKED_STATE
        ]
        # A broken credential backend explains every other provider failure,
        # so it leads the briefing instead of a per-provider reconnect.
        repairs.sort(key=lambda item: item["state"] != BACKEND_FAILURE_STATE)
        first = repairs[0] if repairs else {}
        names = ", ".join(item["provider"] for item in repairs[:3])
        backend_broken = first.get("state") == BACKEND_FAILURE_STATE
        detail = (
            f"{summary['needs_repair']} of {summary['configured']} connected provider(s) "
            f"need repair ({names}); run `mb connect doctor`."
        )
        if backend_broken:
            detail = (
                f"credential backend is unhealthy, so {summary['needs_repair']} of "
                f"{summary['configured']} connected provider(s) cannot be read ({names}); "
                "run `mb connect doctor`."
            )
        return {
            "name": "integration-credentials",
            "ok": False,
            "detail": detail,
            "severity": "warn",
            "repair": str(first.get("repair") or "Run `mb connect doctor`."),
            "repair_command": str(first.get("repair_command") or "mb connect doctor"),
            "safe_to_share": True,
        }
    if summary.get("not_checked"):
        skipped = [item for item in status["providers"] if item["state"] == NOT_CHECKED_STATE]
        names = ", ".join(item["provider"] for item in skipped[:3])
        return {
            "name": "integration-credentials",
            "ok": False,
            "detail": (
                f"{summary['not_checked']} of {summary['configured']} connected provider(s) "
                f"not checked ({names}): this command ran out of credential-read time. "
                "Nothing is known to be wrong."
            ),
            "severity": "info",
            "repair": str(skipped[0].get("repair") or ""),
            "repair_command": str(skipped[0].get("repair_command") or ""),
            "safe_to_share": True,
        }
    if summary.get("unverified"):
        unverified = [item for item in status["providers"] if item["state"] == UNVERIFIED_STATE]
        # Split on whether a probe exists, so the detail never contradicts the
        # repair line sitting next to it. Providers that can be verified lead,
        # because those are the ones with something to run.
        testable = [item for item in unverified if item.get("has_probe")]
        untestable = [item for item in unverified if not item.get("has_probe")]
        first = (testable or unverified)[0]
        parts = []
        if testable:
            names = ", ".join(item["provider"] for item in testable[:3])
            parts.append(f"{len(testable)} never confirmed with the provider ({names})")
        if untestable:
            names = ", ".join(item["provider"] for item in untestable[:3])
            parts.append(f"{len(untestable)} Main Branch cannot verify ({names})")
        return {
            "name": "integration-credentials",
            "ok": False,
            "detail": (
                f"{summary['unverified']} of {summary['configured']} connected provider(s) "
                f"have an unverified credential: {'; '.join(parts)}."
            ),
            "severity": "warn",
            "repair": str(first.get("repair") or ""),
            "repair_command": str(first.get("repair_command") or ""),
            "safe_to_share": True,
        }
    return {
        "name": "integration-credentials",
        "ok": True,
        "detail": f"{summary['healthy']} connected provider(s) verified ready",
        "severity": "ok",
        "repair": "",
        "repair_command": "",
        "safe_to_share": True,
    }


def credential_backend_health(
    backend: str | None = None, *, deadline: float | None = None
) -> dict[str, Any]:
    """Read-only health probe of the local credential backend."""

    try:
        return SecretStore(backend).health(deadline=deadline)
    except (CredentialStoreError, ValueError) as exc:
        reason = exc.reason if isinstance(exc, CredentialStoreError) else "backend_incompatible"
        detail = _backend_repair(reason)
        return {
            "backend": str(backend or "auto"),
            "ok": False,
            "state": reason,
            "summary": detail["summary"],
            "repair": detail["repair"],
            "repair_command": detail["repair_command"],
            "safe_to_share": True,
        }


def _configured_credential_backends(status: dict[str, Any]) -> list[str]:
    backends: set[str] = set()
    raw_providers = status.get("providers")
    providers = raw_providers if isinstance(raw_providers, list) else []
    for raw_provider in providers:
        provider = raw_provider if isinstance(raw_provider, dict) else {}
        raw_secrets = provider.get("secrets")
        secrets = raw_secrets if isinstance(raw_secrets, dict) else {}
        for raw_secret in secrets.values():
            secret = raw_secret if isinstance(raw_secret, dict) else {}
            backend = str(secret.get("backend") or "")
            # A slot with no ref (a tokenless first connect, #991) never asked
            # its backend anything, so it cannot vouch for that backend's health.
            if backend and secret.get("ref"):
                backends.add(backend)
    return sorted(backends)


def _backends_never_read(providers: list[Any]) -> list[str]:
    """Backends with recorded credentials where none of them was read."""

    read: set[str] = set()
    skipped: set[str] = set()
    for raw_provider in providers:
        provider = raw_provider if isinstance(raw_provider, dict) else {}
        raw_secrets = provider.get("secrets")
        secrets = raw_secrets if isinstance(raw_secrets, dict) else {}
        for raw_secret in secrets.values():
            secret = raw_secret if isinstance(raw_secret, dict) else {}
            backend = str(secret.get("backend") or "")
            if not backend or not secret.get("ref"):
                continue
            if secret.get("backend_state") == NOT_CHECKED_BACKEND_STATE:
                skipped.add(backend)
            else:
                read.add(backend)
    return sorted(skipped - read)


def _configured_backend_health(status: dict[str, Any]) -> dict[str, Any] | None:
    backends = _configured_credential_backends(status)
    if not backends:
        return None
    raw_providers = status.get("providers")
    providers = raw_providers if isinstance(raw_providers, list) else []
    for raw_provider in providers:
        provider = raw_provider if isinstance(raw_provider, dict) else {}
        raw_secrets = provider.get("secrets")
        secrets = raw_secrets if isinstance(raw_secrets, dict) else {}
        for raw_secret in secrets.values():
            secret = raw_secret if isinstance(raw_secret, dict) else {}
            if secret.get("backend_ok", True):
                continue
            reason = str(secret.get("backend_state") or "keychain_unavailable")
            detail = _backend_repair(reason)
            return {
                "backend": str(secret.get("backend") or "unknown"),
                "ok": False,
                "state": reason,
                "summary": detail["summary"],
                "repair": detail["repair"],
                "repair_command": detail["repair_command"],
                "safe_to_share": True,
            }
    # The per-provider probes already proved each configured backend answered.
    # Re-probing here would multiply the command's native-store deadline.
    names = ", ".join(backends)
    unread = _backends_never_read(providers)
    if unread:
        # Only a read proves a backend answered. A backend whose every
        # recorded credential went unread has not been asked at all.
        return {
            "backend": names,
            "ok": True,
            "state": NOT_CHECKED_BACKEND_STATE,
            "summary": (
                f"Credential backend(s) not checked this time: {', '.join(unread)}. "
                "Nothing is known to be wrong."
            ),
            "repair": "",
            "repair_command": "",
            "safe_to_share": True,
        }
    return {
        "backend": names,
        "ok": True,
        "state": "ready",
        "summary": f"Configured credential backend(s) are ready: {names}.",
        "repair": "",
        "repair_command": "",
        "safe_to_share": True,
    }


def _status_backend_health(
    providers: list[dict[str, Any]], *, deadline: float | None = None
) -> dict[str, Any]:
    """Credential-backend health for `mb connect status`, with or without providers.

    Reuses the per-provider probes when a recorded secret names a backend, so
    the backend is not asked twice. Otherwise it probes the backend a new
    connect would use, so a fresh repo can still see a locked or missing
    store before the first `mb connect` fails on it (#976).
    """

    health = _configured_backend_health({"providers": providers})
    if health is None:
        health = credential_backend_health(deadline=deadline)
    return health


def _probe_gap(status: dict[str, Any]) -> dict[str, Any]:
    """Connected providers Main Branch has no way to verify.

    Surfaced so a permanent `stored, unverified` reads as a known upstream gap
    that someone can close by writing a probe, rather than as a mystery the
    operator keeps trying to fix locally.
    """
    providers = sorted(
        str(item.get("provider") or "")
        for item in status.get("providers") or []
        if item.get("configured", item.get("connected"))
        and item.get("secrets")
        and not item.get("has_probe")
    )
    if not providers:
        return {"providers": [], "summary": "", "safe_to_share": True}
    return {
        "providers": providers,
        "summary": (
            f"{len(providers)} connected provider(s) have no automated probe "
            f"({', '.join(providers[:3])}); Main Branch cannot verify them until one "
            "exists upstream, so they warn without failing."
        ),
        "safe_to_share": True,
    }


def doctor(repo: str | Path = ".") -> dict[str, Any]:
    github = github_context(repo)
    status = status_all(repo, github=github)
    github = status["github"]
    checks = [
        {
            "name": "github-context",
            "ok": bool(github["ok"]),
            "state": github["state"],
            "summary": github["summary"],
            "repair": github["repair"],
            "repair_command": github["repair_command"],
            "safe_to_share": True,
        },
    ]
    # Backend health is checked before any provider repair is suggested: a
    # locked Keychain makes "reconnect the provider" advice unfollowable. Only
    # when a provider is actually connected, so a fresh repo does not warn
    # about a backend nothing depends on yet.
    backend = _configured_backend_health(status)
    if backend is not None:
        checks.append(
            {
                "name": "credential-backend",
                "ok": bool(backend["ok"]),
                "state": backend["state"],
                "summary": backend["summary"],
                "repair": backend["repair"],
                "repair_command": backend["repair_command"],
                "safe_to_share": True,
            }
        )
    checks += [
        {
            "name": f"provider:{item['provider']}",
            "provider": item["provider"],
            "ok": bool(item["ok"]),
            "state": item["state"],
            "summary": item["summary"],
            "repair": item["repair"],
            "repair_command": item["repair_command"],
            "safe_to_share": True,
        }
        for item in status["providers"]
    ]
    # `ok` stays truthful: it is false whenever anything is unverified. The
    # exit code is a separate question — see `provider_needs_action`.
    needs_action = any(
        not check["ok"] for check in checks if not str(check["name"]).startswith("provider:")
    ) or any(provider_needs_action(item) for item in status["providers"])
    return {
        "ok": all(check["ok"] for check in checks),
        "needs_action": needs_action,
        "probe_gap": _probe_gap(status),
        "repo": status["repo"],
        "checks": checks,
        "integrations": status,
        "safe_to_share": True,
    }


# --- Credential hygiene (mb connect hygiene) -------------------------------
#
# Read-only scan of known agent-config surfaces for PLAINTEXT credentials that
# violate the agent-access-dossier never-print doctrine. The scan reports the
# surface, the dotted location, and a length-only mask — it NEVER emits the
# secret value itself. Findings carry a one-line keychain/env remediation.

# Value-shape prefixes that betray a real credential regardless of key name.
CREDENTIAL_VALUE_PREFIXES: tuple[str, ...] = (
    "sk_",
    "rk_",
    "re_",
    "sk-",
    "fal-",
    "AIza",
    "ghp_",
    "gho_",
    "github_pat_",
    "xoxb-",
    "xoxp-",
    "glpat-",
    "AKIA",
)
_HYGIENE_SECRET_KEY_RE = re.compile(
    r"(?i)(token|api[_-]?key|secret|password|passwd|bearer|authorization|"
    r"access[_-]?key|developer[_-]?token|client[_-]?secret|private[_-]?key)"
)
# A value that is wholly or partly an env reference (${VAR}, $VAR) is correctly
# externalized — not a plaintext leak.
_ENV_REFERENCE_RE = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?")
# A value is "externalized" only if it is WHOLLY env reference(s) (optionally a
# Bearer prefix) — not a literal secret with an env ref tacked on. Matching a
# bare .search() let "${ENV}sk-realsecret" pass as safe (false negative).
_ENV_REFERENCE_FULL_RE = re.compile(r"(?i)^(bearer\s+)?(\$\{?[A-Za-z_][A-Za-z0-9_]*\}?)+$")
_PLACEHOLDER_VALUES = frozenset(
    {"", "changeme", "change-me", "todo", "none", "null", "example", "redacted"}
)
# An ISO-8601 date or timestamp is not a secret. Housekeeping fields like
# `claudeCodeFirstTokenDate` match the secret-named-key heuristic ("Token")
# but hold a date string — excluding the shape keeps the count honest.
_ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$"
)

# JSON config surfaces scanned by default. TOML surfaces (e.g. ~/.codex/
# config.toml) are a follow-up slice (tomllib is 3.11+; the matrix includes
# 3.10), tracked on the hygiene issue.
HYGIENE_HOME_SURFACES: tuple[str, ...] = (".claude.json",)
HYGIENE_REPO_SURFACES: tuple[str, ...] = (
    ".mcp.json",
    ".claude/settings.json",
    ".claude/settings.local.json",
)


def _looks_like_env_reference(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    # Safe only if the WHOLE value is env reference(s) (e.g. "Bearer ${FAL_KEY}").
    # A literal secret mixed with an env ref is NOT safe.
    return bool(_ENV_REFERENCE_FULL_RE.match(stripped))


def _looks_like_iso_datetime(value: str) -> bool:
    return bool(_ISO_DATETIME_RE.match(value.strip()))


def _looks_like_placeholder(value: str) -> bool:
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered in _PLACEHOLDER_VALUES:
        return True
    if stripped.startswith("<") and stripped.endswith(">"):
        return True
    if lowered.startswith(("your_", "your-", "<your", "xxx")):
        return True
    return bool(stripped and set(stripped) <= {"x", "X", "*", "•", "."})


def _credential_value_prefix(value: str) -> str:
    candidate = value.strip()
    if candidate.lower().startswith("bearer "):
        candidate = candidate[7:].strip()
    for prefix in CREDENTIAL_VALUE_PREFIXES:
        if candidate.startswith(prefix):
            return prefix
    return ""


def _classify_credential_value(key: str, value: str) -> tuple[bool, str]:
    """Return (flagged, reason) without ever surfacing the value."""
    if not isinstance(value, str):
        return False, ""
    if (
        _looks_like_env_reference(value)
        or _looks_like_placeholder(value)
        or _looks_like_iso_datetime(value)
    ):
        return False, ""
    prefix = _credential_value_prefix(value)
    if prefix:
        return True, f"value carries the `{prefix}` credential prefix"
    # A secret-named key holding a non-referenced, non-placeholder literal with
    # some entropy (a digit or mixed case) reads as a real plaintext credential.
    if (
        _HYGIENE_SECRET_KEY_RE.search(key)
        and len(value.strip()) >= 12
        and (any(ch.isdigit() for ch in value) or not value.islower())
    ):
        return True, f"secret-named key `{key}` holds a plaintext value"
    return False, ""


def _walk_json_for_secrets(
    node: Any, path: str, surface: str, findings: list[dict[str, Any]]
) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else str(key)
            if isinstance(value, str):
                flagged, reason = _classify_credential_value(str(key), value)
                if flagged:
                    findings.append(
                        {
                            "surface": surface,
                            "location": child_path,
                            "key": str(key),
                            "reason": reason,
                            "mask": f"••• ({len(value)} chars)",
                            "remediation": (
                                "move the value into the OS keychain "
                                "(`mb connect <provider> --token-stdin`) or a gitignored "
                                "env.sh, then reference it as ${ENV_VAR} in this config"
                            ),
                            "safe_to_share": True,
                        }
                    )
            else:
                _walk_json_for_secrets(value, child_path, surface, findings)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk_json_for_secrets(value, f"{path}[{index}]", surface, findings)


def _scan_surface(path: Path, label: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Scan one JSON surface. Returns (findings, skip_record_or_None)."""
    if not path.exists():
        return [], None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return [], {"surface": label, "reason": "unreadable"}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [], {"surface": label, "reason": "not valid JSON"}
    findings: list[dict[str, Any]] = []
    _walk_json_for_secrets(data, "", label, findings)
    return findings, None


def scan_credential_hygiene(
    repo: str | Path = ".", *, home: str | Path | None = None
) -> dict[str, Any]:
    """Flag plaintext credentials in known agent-config surfaces (read-only).

    Never emits a secret value — findings carry the surface, dotted location,
    a length-only mask, and a keychain/env remediation. ``home`` overrides the
    home directory (tests, alternate profiles).
    """
    repo_path = Path(repo).expanduser().resolve()
    # Agent configs (~/.claude.json) live in the real home directory, not the
    # mainbranch secret-store home (_home()).
    home_path = Path(home).expanduser().resolve() if home is not None else Path.home()

    findings: list[dict[str, Any]] = []
    scanned: list[str] = []
    skipped: list[dict[str, Any]] = []

    surfaces: list[tuple[Path, str]] = [
        (home_path / name, f"~/{name}") for name in HYGIENE_HOME_SURFACES
    ]
    surfaces += [(repo_path / name, name) for name in HYGIENE_REPO_SURFACES]

    for path, label in surfaces:
        if not path.exists():
            continue
        surface_findings, skip = _scan_surface(path, label)
        if skip is not None:
            skipped.append(skip)
            continue
        scanned.append(label)
        findings.extend(surface_findings)

    # A surface that could not be scanned was NOT proven clean — it must not
    # yield a clean machine verdict (gates/automation read ok + the exit code).
    ok = not findings and not skipped
    if not findings:
        summary = f"no plaintext credentials found across {len(scanned)} scanned config surface(s)"
    else:
        summary = (
            f"{len(findings)} plaintext credential(s) in agent config — move them "
            "to the keychain/env and reference via ${ENV_VAR}"
        )
    # Surface unscannable files loudly — a config that could not be parsed was
    # NOT proven clean; silence there would be a false all-clear.
    if skipped:
        labels = ", ".join(str(item["surface"]) for item in skipped)
        summary += (
            f" — WARNING: {len(skipped)} surface(s) could not be scanned "
            f"(not proven clean): {labels}"
        )
    return {
        "ok": ok,
        "repo": str(repo_path),
        "home": str(home_path),
        "surfaces_scanned": scanned,
        "surfaces_skipped": skipped,
        "findings": findings,
        "summary": summary,
        "safe_to_share": True,
    }


def render_credential_hygiene(result: dict[str, Any]) -> None:
    print(f"mb connect hygiene  {result['repo']}")
    print(result["summary"])
    for finding in result["findings"]:
        print(f"  warn  {finding['surface']} → {finding['location']}")
        print(f"        {finding['reason']} {finding['mask']}")
        print(f"        next: {finding['remediation']}")
    for skip in result["surfaces_skipped"]:
        print(f"  skip  {skip['surface']}: {skip['reason']}")
    if result["ok"]:
        print("  ok    every scanned surface references secrets indirectly")


# --- Canonical business identity (mb connect identity) ---------------------
#
# Agents must read identity (ad account, pixel, page, sender domain, Stripe
# account/mode) from RECORDED facts, never infer it from live provider state
# (mining friction #1). Each provider's registry metadata_fields IS the
# canonical identity schema; this surface aggregates the recorded values and
# names what's still unrecorded. Output carries business identifiers, so it is
# operator-facing (safe_to_share=False) — never paste into public artifacts.


def business_identity(repo: str | Path = ".") -> dict[str, Any]:
    """Aggregate recorded business-identity metadata across connected providers."""
    target = Path(repo).resolve()
    status = status_all(target)
    pmap = provider_map()
    providers_out: list[dict[str, Any]] = []
    for item in status["providers"]:
        # Configured, not only connected: a metadata-only first connect (#991)
        # records identity fields before any secret is stored.
        if not item.get("configured", item["connected"]):
            continue
        provider = pmap.get(item["provider"])
        metadata = item.get("metadata") or {}
        metadata = metadata if isinstance(metadata, dict) else {}
        if provider:
            fields = provider.metadata_fields
            if not fields:
                continue
            recorded = {field: str(metadata.get(field, "")) for field in fields}
            missing = [field for field in fields if not recorded[field]]
            schema = "registry"
        elif _is_custom_provider_id(str(item["provider"])):
            recorded = _safe_identity_metadata(metadata)
            if not recorded:
                continue
            missing = []
            schema = "custom_metadata"
        else:
            continue
        providers_out.append(
            {
                "provider": item["provider"],
                "name": item["name"],
                "custom": provider is None,
                "identity_schema": schema,
                "identity": recorded,
                "missing_fields": missing,
                "complete": not missing,
            }
        )
    total_missing = sum(len(item["missing_fields"]) for item in providers_out)
    if not providers_out:
        summary = "no connected providers carry identity metadata yet"
    elif total_missing == 0:
        summary = f"all {len(providers_out)} connected provider(s) have complete recorded identity"
    else:
        summary = (
            f"{total_missing} identity field(s) unrecorded across "
            f"{len(providers_out)} connected provider(s) — record them with "
            "`mb connect <provider> --metadata <field>=<value>` so agents read "
            "facts, not live state"
        )
    return {
        "ok": True,
        "repo": str(target),
        "providers": providers_out,
        "summary": summary,
        # Carries ad account / pixel / page / sender-domain identifiers.
        "safe_to_share": False,
    }


def render_identity(result: dict[str, Any]) -> None:
    print(f"mb connect identity  {result['repo']}")
    print(result["summary"])
    for item in result["providers"]:
        mark = "ok" if item["complete"] else "warn"
        print(f"  {mark}  {item['provider']}")
        for field, value in item["identity"].items():
            shown = value if value else "(unrecorded)"
            print(f"        {field}: {shown}")


def render_list(result: dict[str, Any]) -> None:
    for provider in result["providers"]:
        print(
            f"{provider['id']:<14} {provider['state']:<14} "
            f"{provider['auth']:<22} {provider['description']}"
        )


def render_plan(result: dict[str, Any]) -> None:
    print(f"mb connect plan  {result['repo']}")
    print("Choose the provider that matches the business job in front of you:")
    for index, step in enumerate(result["steps"], start=1):
        state = "ready" if step["ready"] else step["state"]
        print(f"{index}. {step['name']} ({state})")
        print(f"   why: {step['why']}")
        print(f"   use when: {step['use_when']}")
        if not step["ready"]:
            print(f"   next: {step['next_command']}")


def state_label(state: str) -> str:
    """Human phrasing for a provider state. JSON keeps the machine value."""
    if state == NOT_CHECKED_STATE:
        return "not checked"
    return "stored, unverified" if state == UNVERIFIED_STATE else state


def render_status(result: dict[str, Any]) -> None:
    summary = result["summary"]
    print(f"mb connect status  {result['repo']}")
    line = (
        f"configured: {summary['configured']}  "
        f"healthy: {summary['healthy']}  needs repair: {summary['needs_repair']}"
    )
    if summary.get("unverified"):
        line += f"  unverified: {summary['unverified']}"
    if summary.get("not_checked"):
        line += f"  not checked: {summary['not_checked']}"
    print(line)
    github = result.get("github") or {}
    if github:
        state = "ok" if github.get("ok") else "warn"
        print(f"  {state}  github: {github.get('state')}")
        if github.get("repair_command"):
            print(f"       next: {github['repair_command']}")
    if not result["providers"]:
        print("no providers connected")
        return
    for item in result["providers"]:
        state = "ok" if item["ok"] else "warn"
        label = f" ({item['account_label']})" if item["account_label"] else ""
        print(f"  {state}  {item['provider']}{label}: {state_label(item['state'])}")
        if item["repair_command"]:
            print(f"       next: {item['repair_command']}")


def render_provider_status(result: dict[str, Any]) -> None:
    state = "ok" if result["ok"] else "warn"
    label = f" ({result['account_label']})" if result["account_label"] else ""
    print(
        f"mb connect status {result['provider']}{label}: {state} ({state_label(result['state'])})"
    )
    if result.get("summary"):
        print(f"summary: {result['summary']}")
    if result.get("credential_mode") == "oauth":
        _render_google_products(result)
    if result.get("repair_command"):
        print(f"next: {result['repair_command']}")


def _render_google_products(result: dict[str, Any]) -> None:
    """One line per Google product: granted or not, and its last recorded check."""

    raw_oauth = result.get("oauth")
    grants = raw_oauth.get("grants") if isinstance(raw_oauth, dict) else None
    granted = set(grants) if isinstance(grants, list) else set()
    raw_validation = result.get("validation")
    raw_products = raw_validation.get("products") if isinstance(raw_validation, dict) else None
    products = raw_products if isinstance(raw_products, dict) else {}
    # A read that Google refused records reauth_required without product checks.
    unchecked = (
        "not checked since the sign-in expired"
        if result.get("state") == GOOGLE_REAUTH_REQUIRED_STATE
        else "not checked yet"
    )
    for name in GOOGLE_OAUTH_PRODUCTS:
        if name not in granted:
            print(f"  {name}: not granted")
            continue
        raw_product = products.get(name)
        product: dict[str, Any] = raw_product if isinstance(raw_product, dict) else {}
        state = product.get("state")
        if not state or state == "not_checked":
            last = unchecked
        elif state in {"ok", "grant_missing"}:
            last = state
        else:
            last = f"{state} ({product.get('rule') or 'no rule'})"
        print(f"  {name}: granted, last check: {last}")


def render_doctor(result: dict[str, Any]) -> None:
    print(f"mb connect doctor  {result['repo']}")
    for check in result["checks"]:
        state = "ok" if check["ok"] else "warn"
        print(f"  {state}  {check['name']}: {state_label(check['state'])}")
        if check["repair_command"]:
            print(f"       next: {check['repair_command']}")
    probe_gap = result.get("probe_gap") or {}
    if probe_gap.get("providers"):
        print(f"  note  no provider probe: {', '.join(probe_gap['providers'])}")
        print(f"       {probe_gap['summary']}")


def render_test_result(result: dict[str, Any]) -> None:
    if result.get("provider") == "google" and "products" in result:
        from mb import google_probe

        google_probe.render_test_result(result)
        return
    status = result["status"]
    state = "ok" if result["ok"] else "warn"
    validation = result.get("validation") or status.get("validation") or {}
    # An unrecorded check shows its own outcome; status still holds the last one.
    shown = (
        str(validation.get("state") or status["state"])
        if result.get("not_recorded_reason")
        else status["state"]
    )
    print(f"mb connect test {result['provider']}: {state} ({state_label(shown)})")
    summary = validation.get("summary")
    if summary:
        print(f"summary: {summary}")
    upstream = validation.get("upstream") if isinstance(validation, dict) else {}
    if isinstance(upstream, dict) and upstream.get("endpoint_family"):
        details = [f"endpoint: {upstream['endpoint_family']}"]
        if upstream.get("http_status") is not None:
            details.append(f"http: {upstream['http_status']}")
        codes = upstream.get("error_codes")
        if isinstance(codes, list) and codes:
            details.append(f"codes: {', '.join(str(code) for code in codes[:3])}")
        print("provider: " + "  ".join(details))
    scopes = validation.get("scopes") if isinstance(validation, dict) else None
    if isinstance(scopes, dict) and scopes:
        print("reads: " + "  ".join(f"{name}={verdict}" for name, verdict in scopes.items()))
    if result.get("not_recorded_reason") == "connect_yaml_tracked":
        print(
            "recorded: no (.mb/connect.yaml is tracked by git, so checks are not written to "
            f"it; `mb connect status {result['provider']}` shows the last check a person "
            "recorded)"
        )
        next_command = str(validation.get("repair_command") or "")
    else:
        next_command = str(status.get("repair_command") or "")
    if result.get("not_recorded_reason") == "user_scope_read_only":
        render_user_scope_not_recorded()
    elif result.get("not_recorded_reason") == "user_scope_write_failed":
        render_user_scope_write_failed(result)
    if next_command:
        print(f"next: {next_command}")


def render_user_scope_not_recorded() -> None:
    shown = UserScopeReadOnlyError(_user_scope_path()).shown
    print(f"recorded: no (the user-scope connect file {shown} is read-only)")


def not_recorded_line(detail: str) -> str:
    """The ``recorded: no (...)`` line, as ``mb connect test`` shows it."""

    return f"recorded: no ({detail})"


def render_user_scope_write_failed(result: dict[str, Any]) -> None:
    detail = result.get("not_recorded_detail") or "the user-scope file was not written"
    print(not_recorded_line(str(detail)))


def render_rotate_result(result: dict[str, Any]) -> None:
    stored = "stored" if result["stored"] else "not stored"
    print(f"mb connect rotate {result['provider']}: re-read from 1Password, {stored}")
    render_test_result(result)


def render_hydrate_result(result: dict[str, Any]) -> None:
    print(f"mb connect hydrate  {result['repo']}")
    if result["hydrated"]:
        print(f"hydrated: {', '.join(result['hydrated'])}")
        print(f"metadata: {result['config_path']}")
    else:
        print("no user-scoped provider metadata found for this repo")
    if result["missing"]:
        print(f"missing: {', '.join(result['missing'])}")
    if result.get("repair_command"):
        print(f"next: {result['repair_command']}")


def render_connect_result(result: dict[str, Any]) -> None:
    status = result["status"]
    setup = result.get("setup") if result["provider"] == "meta" else {}
    if isinstance(setup, dict) and setup.get("requirements"):
        print("Meta Ads setup requirements:")
        for item in setup["requirements"]:
            print(f"  - {item}")
    if status["state"] == "ready":
        print(f"connected {result['provider']} and ready")
    elif status["state"] == "unvalidated":
        print(f"stored {result['provider']} credential; validation still needed")
    elif status["state"] == BACKEND_FAILURE_STATE:
        print(f"connected {result['provider']} metadata; credential backend is unhealthy")
        print(f"summary: {status['summary']}")
        print(f"repair: {status['repair']}")
    elif not result["ok"]:
        print(f"connected {result['provider']} metadata; credential still needs repair")
    else:
        print(f"connected {result['provider']} metadata")
    print(f"metadata: {result['config_path']}")
    if result.get("scope") == "user":
        print(f"user scope: {result['user_scope_path']}")
    print(f"secrets: {result['credential_boundary']}")
    rotated = result.get("rotated_sibling_refs") or []
    if rotated:
        print(
            f"rotated {len(rotated)} sibling ref(s) to the new credential (other repos/worktrees)"
        )
    stale = result.get("stale_sibling_refs") or []
    if stale:
        print(
            f"WARNING: {len(stale)} sibling ref(s) could not be updated "
            "and still hold the OLD credential:"
        )
        for ref in stale:
            print(f"  - {ref}")
    source = result.get("credential_source") or {}
    if source.get("type") == "env" and source.get("env_var"):
        print(f"credential source: env {source['env_var']}")
    if status["repair_command"]:
        print(f"next: {status['repair_command']}")


def read_stdin_token() -> str:
    if sys.stdin.isatty():
        print(
            "Paste the credential, then press Ctrl-D on a new line to finish.",
            file=sys.stderr,
        )
    value = sys.stdin.read()
    # Treat one final line ending as the stdin transport delimiter. Preserve
    # every other leading, trailing, and embedded character exactly.
    if value.endswith("\r\n"):
        return value[:-2]
    if value.endswith("\n"):
        return value[:-1]
    return value
