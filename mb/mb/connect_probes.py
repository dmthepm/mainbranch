"""Read-only provider validation probes."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from mb.connect_registry import (
    META_READ_SMOKE_COMMANDS,
    UNVERIFIED_STATE,
    VALIDATION_TIMEOUT_SECONDS,
    CommandRunner,
    Provider,
    Which,
)


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
    from mb import connect

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
        result = connect._probe_stripe(provider, secret)
    elif provider.id == "github":
        result = connect._probe_github(provider, secret)
    elif provider.id == "ga4":
        result = connect._probe_ga4(provider, secret, metadata)
    elif provider.id == "meta":
        return connect._validate_meta_with_cli(
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


def _cloudflare_token_type(metadata: dict[str, Any], secret: str = "") -> str:
    from mb import connect

    return connect._cloudflare_token_type(metadata, secret)


def _http_get_json(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    provider_name: str = "provider",
    endpoint_family: str = "unknown",
    response_headers: tuple[str, ...] = (),
) -> dict[str, Any]:
    from mb import connect

    return connect._http_get_json(
        url,
        headers,
        provider_name=provider_name,
        endpoint_family=endpoint_family,
        response_headers=response_headers,
    )


def _meta_prerequisite_state(
    *, which_func: Which | None = None, command_runner: CommandRunner | None = None
) -> str:
    from mb import connect

    return connect._meta_prerequisite_state(which_func=which_func, command_runner=command_runner)


def _meta_repair(state: str, missing: list[str] | None = None) -> dict[str, str]:
    from mb import connect

    return connect._meta_repair(state, missing)


def _now() -> str:
    from mb import connect

    return connect._now()


def _run_command(
    args: list[str],
    cwd: Path | None = None,
    timeout: float = 5.0,
    *,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    from mb import connect

    return connect._run_command(args, cwd, timeout, env=env)


def _unverified_repair(provider: Provider) -> dict[str, str]:
    from mb import connect

    return connect._unverified_repair(provider)
