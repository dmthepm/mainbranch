"""Read-only ads account summaries."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from contextlib import suppress
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from mb import connect as connect_mod

CommandRunner = Callable[..., dict[str, Any]]

SUMMARY_SCHEMA_VERSION = "1.0"
MAX_WINDOW_DAYS = 90


class AdsSummaryError(ValueError):
    """Raised for invalid summary arguments."""


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _checked_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_iso_date(value: str, *, option: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AdsSummaryError(f"{option} must be YYYY-MM-DD") from exc


def _window_from_args(
    *, window: str = "7d", since: str = "", until: str = "", today: date | None = None
) -> dict[str, Any]:
    current = today or _today()
    if since or until:
        if not since or not until:
            raise AdsSummaryError("--since and --until must be provided together")
        since_date = _parse_iso_date(since, option="--since")
        until_date = _parse_iso_date(until, option="--until")
        label = f"{since_date.isoformat()}..{until_date.isoformat()}"
    else:
        match = re.fullmatch(r"([1-9][0-9]*)d", window.strip().lower())
        if not match:
            raise AdsSummaryError("--window must use a day window like 7d")
        days = int(match.group(1))
        if days > MAX_WINDOW_DAYS:
            raise AdsSummaryError(f"--window must be {MAX_WINDOW_DAYS}d or less")
        until_date = current
        since_date = current - timedelta(days=days)
        label = f"{days}d"

    days_inclusive = (until_date - since_date).days
    if days_inclusive <= 0:
        raise AdsSummaryError("--until must be after --since")
    if days_inclusive > MAX_WINDOW_DAYS:
        raise AdsSummaryError(f"date range must be {MAX_WINDOW_DAYS} days or less")
    return {
        "label": label,
        "since": since_date.isoformat(),
        "until": until_date.isoformat(),
        "days": days_inclusive,
    }


def _read_json(stdout: str) -> Any:
    with suppress(json.JSONDecodeError):
        return json.loads(stdout or "")
    return {}


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "items", "results", "campaigns", "adaccounts", "datasets"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return [payload] if payload else []


def _first_string(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and value != "":
            return str(value)
    return ""


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _spend_range(amount: Decimal) -> str:
    if amount <= 0:
        return "no recent spend detected"
    if amount < Decimal("100"):
        return "recent spend under 100"
    if amount < Decimal("1000"):
        return "recent spend 100-999"
    if amount < Decimal("10000"):
        return "recent spend 1k-9.9k"
    return "recent spend 10k+"


def _active_campaigns(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    for item in items:
        raw_status = (
            item.get("effective_status")
            or item.get("configured_status")
            or item.get("status")
            or ""
        )
        status = str(raw_status).strip().upper()
        if status in {"ACTIVE", "ENABLED"}:
            active.append(item)
    return active


def _empty_summary(
    *,
    ok: bool,
    state: str,
    readiness: dict[str, Any],
    window_info: dict[str, Any],
    checked_at: str,
    errors: list[str] | None = None,
    actions: list[str] | None = None,
) -> dict[str, Any]:
    repair_command = str(readiness.get("repair_command") or "")
    return {
        "ok": ok,
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "safe_to_share": False,
        "provider": "meta",
        "command": "mb ads meta summary",
        "state": state,
        "checked_at": checked_at,
        "window": {
            "label": window_info["label"],
            "since": window_info["since"],
            "until": window_info["until"],
        },
        "privacy": {
            "raw_payload_written": False,
            "tracked_files_written": False,
            "account_ids_redacted": True,
            "business_ids_redacted": True,
            "exact_spend_included": False,
            "campaign_names_included": False,
        },
        "readiness": {
            "state": str(readiness.get("state") or state),
            "summary": str(readiness.get("summary") or ""),
            "repair": str(readiness.get("repair") or ""),
            "repair_command": repair_command,
            "support_level": "meta_ads_cli_read_only",
            "command_source": "mb connect",
        },
        "account": {
            "label": str(readiness.get("account_label") or "Meta Ads"),
            "currency": "",
            "timezone": "",
            "ad_account_id": "<redacted>",
            "business_id": "<redacted>",
        },
        "campaigns": {"active_count": 0, "names": [], "names_redacted": True},
        "spend": {"amount": "redacted", "range_label": "unknown", "currency": ""},
        "performance_direction": {
            "state": "unknown",
            "summary": "Not enough prior-window context to compare direction.",
        },
        "datasets": {"state": "not_read", "count": None},
        "creatives": {"state": "not_read", "count": None, "naming_patterns": []},
        "findings": [],
        "next_actions": [],
        "errors": errors or [],
        "actions": actions if actions is not None else ([repair_command] if repair_command else []),
    }


def _run_json(
    run: CommandRunner,
    args: list[str],
    repo: Path,
    env: dict[str, str],
) -> tuple[dict[str, Any], Any]:
    result = connect_mod._run_meta_command(run, args, repo, env)
    return result, _read_json(str(result.get("stdout") or "")) if result.get("ok") else {}


def _load_meta_secret_and_metadata(repo: Path) -> tuple[str, dict[str, Any]]:
    config = connect_mod._read_config(repo)
    entry = config.get("providers", {}).get("meta")
    if not isinstance(entry, dict):
        return "", {}
    provider = connect_mod.normalize_provider("meta")
    secret = connect_mod._stored_secret(provider, entry, repo)
    raw_metadata = entry.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    return secret, metadata


def meta_summary(
    *,
    repo: str | Path = ".",
    window: str = "7d",
    since: str = "",
    until: str = "",
    include_campaign_names: bool = False,
    include_exact_spend: bool = False,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Return a compact, read-only Meta Ads account summary."""

    target = Path(repo).resolve()
    window_info = _window_from_args(window=window, since=since, until=until)
    checked_at = _checked_at()
    readiness = connect_mod.status_provider("meta", target)
    if readiness.get("state") != "ready":
        state = str(readiness.get("state") or "not_ready")
        summary = _empty_summary(
            ok=False,
            state=state,
            readiness=readiness,
            window_info=window_info,
            checked_at=checked_at,
            errors=[str(readiness.get("summary") or "Meta Ads is not ready.")],
        )
        summary["findings"] = [
            "Meta Ads is not ready, so no live account data was read.",
        ]
        if readiness.get("repair_command"):
            summary["next_actions"] = [str(readiness["repair_command"])]
        else:
            summary["next_actions"] = [
                "Continue from repo files, exported screenshots, or manual Ads Manager notes.",
            ]
        return summary

    secret, metadata = _load_meta_secret_and_metadata(target)
    if not secret:
        readiness = connect_mod.status_provider("meta", target)
        return _empty_summary(
            ok=False,
            state="missing_secret",
            readiness=readiness,
            window_info=window_info,
            checked_at=checked_at,
            errors=["Meta Ads local token material is missing."],
        )

    run = command_runner or connect_mod._run_command
    env = connect_mod._meta_env(secret, metadata)
    account_args = ["meta", "-o", "json", "ads", "adaccount", "list"]
    campaign_args = ["meta", "-o", "json", "ads", "campaign", "list"]
    insights_args = [
        "meta",
        "-o",
        "json",
        "ads",
        "insights",
        "get",
        "--fields",
        "spend,impressions,clicks,ctr,cpc",
        "--since",
        window_info["since"],
        "--until",
        window_info["until"],
    ]
    dataset_args = ["meta", "-o", "json", "ads", "dataset", "list"]
    business_id = str(metadata.get("business_id") or "").strip()

    account_result, account_payload = _run_json(run, account_args, target, env)
    campaign_result, campaign_payload = _run_json(run, campaign_args, target, env)
    insights_result, insights_payload = _run_json(run, insights_args, target, env)
    if business_id:
        dataset_result, dataset_payload = _run_json(run, dataset_args, target, env)
        dataset_skipped = False
    else:
        dataset_result = {"ok": True, "skipped": True, "reason": "business_id metadata not set"}
        dataset_payload = {}
        dataset_skipped = True

    upstream = {
        "account": account_result,
        "campaigns": campaign_result,
        "insights": insights_result,
        "datasets": dataset_result,
    }
    failed = [name for name, result in upstream.items() if not result.get("ok")]
    if failed:
        summary = _empty_summary(
            ok=False,
            state="read_failed",
            readiness=readiness,
            window_info=window_info,
            checked_at=checked_at,
            errors=[f"Meta Ads read-only summary failed for: {', '.join(failed)}"],
            actions=["mb connect test meta"],
        )
        summary["findings"] = [
            "Meta Ads readiness was ready, but one or more read-only summary calls failed.",
        ]
        summary["next_actions"] = [
            "Run `mb connect test meta --json` to refresh the readiness state.",
        ]
        return summary

    account_items = _items(account_payload)
    account = account_items[0] if account_items else {}
    currency = _first_string(account, ("currency", "account_currency"))
    timezone = _first_string(account, ("timezone_name", "timezone", "account_timezone"))
    campaign_items = _items(campaign_payload)
    active = _active_campaigns(campaign_items)
    insight_items = _items(insights_payload)
    exact_spend = sum((_decimal(item.get("spend")) for item in insight_items), Decimal("0"))
    dataset_items = _items(dataset_payload)
    dataset_count = len(dataset_items) if not dataset_skipped else None

    summary = _empty_summary(
        ok=True,
        state="ready",
        readiness=readiness,
        window_info=window_info,
        checked_at=checked_at,
    )
    summary["privacy"]["exact_spend_included"] = bool(include_exact_spend)
    summary["privacy"]["campaign_names_included"] = bool(include_campaign_names)
    summary["readiness"]["command_source"] = "Meta Ads CLI"
    summary["account"]["currency"] = currency
    summary["account"]["timezone"] = timezone
    summary["campaigns"] = {
        "active_count": len(active),
        "names": [
            str(item.get("name") or "") for item in active if str(item.get("name") or "").strip()
        ]
        if include_campaign_names
        else [],
        "names_redacted": not include_campaign_names,
    }
    summary["spend"] = {
        "amount": str(exact_spend) if include_exact_spend else "redacted",
        "range_label": _spend_range(exact_spend),
        "currency": currency,
    }
    summary["datasets"] = {
        "state": "not_configured"
        if dataset_skipped
        else "readable"
        if dataset_count
        else "none_detected",
        "count": dataset_count,
    }
    summary["findings"] = [
        "Meta account context is readable for a bounded summary.",
    ]
    if active:
        summary["findings"].append("Active campaign context is present.")
    else:
        summary["findings"].append("No active campaign context was detected.")
    summary["next_actions"] = [
        (
            "Use this summary to choose whether to generate new creative, audit active "
            "campaigns, or work from repo reference files."
        ),
    ]
    return summary


def render_meta_summary_human(summary: dict[str, Any]) -> None:
    print(f"Meta Ads summary: {summary['state']}")
    for finding in summary.get("findings", []):
        print(f"- {finding}")
    for action in summary.get("next_actions", []):
        print(f"next: {action}")
