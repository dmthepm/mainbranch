"""Provider catalog, states, and setup guidance."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

VALIDATION_TIMEOUT_SECONDS = 8

CommandRunner = Callable[..., dict[str, Any]]

Which = Callable[[str], str | None]

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
# A recorded ref that is not the one this repo, provider and field derive.
REF_MISMATCH_STATE = "credential_ref_mismatch"


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


# `mb connect token` without `--print`, caller policy and env-dump refusals.
# Distinct from 1 (credential missing or unreadable, store failure) and 2
# (usage error or other refusals), so a script can tell "refused by design"
# from "no credential". Stable: documented in docs/connect.md.
TOKEN_REFUSED_EXIT_CODE = 3

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
