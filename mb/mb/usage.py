"""Read local usage snapshots without contacting providers or changing state."""

from __future__ import annotations

import importlib
import json
import math
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

KEY = re.compile(r"[a-z0-9][a-z0-9-]{0,39}\Z")
STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z")
COMMON = {"schema_version", "written_at", "taken_at", "source"}
READING = {"taken_at", "used_pct", "session_pct", "window_end", "session_end"}
QUESTION = "Do you want to use one now? mb won't do it; use your runtime's own screen."


class Refused(ValueError):
    """A safe reason code for an unreadable snapshot."""


def timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not STAMP.fullmatch(value):
        raise ValueError("invalid UTC stamp")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _percentage(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100


def _fields(data: Any, allowed: set[str], required: set[str]) -> None:
    if not isinstance(data, dict) or not required <= data.keys():
        raise Refused("malformed")
    if data.keys() - allowed:
        raise Refused("unknown_field")


def _reading(data: Any) -> None:
    _fields(data, READING, {"taken_at", "used_pct"})
    timestamp(data["taken_at"])
    if not _percentage(data["used_pct"]):
        raise Refused("malformed")
    if "session_pct" in data and not _percentage(data["session_pct"]):
        raise Refused("malformed")
    for key in ("window_end", "session_end"):
        if key in data:
            timestamp(data[key])


def _credit_shape(data: Any) -> None:
    _fields(
        data,
        {"status", "read_at", "available_count", "credits", "source", "note", "reason"},
        {"status"},
    )
    if data["status"] == "UNKNOWN":
        if not isinstance(data.get("reason"), str):
            raise Refused("malformed")
        return
    if data["status"] != "read":
        raise Refused("malformed")
    _fields(
        data,
        {"status", "read_at", "available_count", "credits", "source", "note"},
        {"status", "read_at", "available_count", "credits"},
    )
    timestamp(data["read_at"])
    if (
        type(data["available_count"]) is not int
        or not 0 <= data["available_count"] <= 10000
        or not isinstance(data["credits"], list)
    ):
        raise Refused("malformed")
    for credit in data["credits"]:
        _fields(
            credit, {"expires_at", "granted_at", "status"}, {"expires_at", "granted_at", "status"}
        )
        timestamp(credit["expires_at"])
        timestamp(credit["granted_at"])
        if credit["status"] not in ("available", "expired", "used"):
            raise Refused("malformed")


def _read_file(path: Path, multi: bool) -> dict[str, Any]:
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_mode & 0o022 or before.st_size > 16384:
            raise Refused("unsafe_file")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            actual = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(actual.st_mode)
                or actual.st_mode & 0o022
                or (actual.st_dev, actual.st_ino) != (before.st_dev, before.st_ino)
            ):
                raise Refused("unsafe_file")
            raw = stream.read(16385)
        if len(raw) > 16384:
            raise Refused("unsafe_file")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise Refused("malformed")
        if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise Refused("schema_unknown")
        allowed = COMMON | (
            {"accounts"} if multi else {"used_pct", "window_end", "window_minutes", "reset_credits"}
        )
        _fields(data, allowed, COMMON - {"source"} | ({"accounts"} if multi else {"used_pct"}))
        timestamp(data["written_at"])
        timestamp(data["taken_at"])
        if multi:
            if not isinstance(data["accounts"], dict) or not data["accounts"]:
                raise Refused("malformed")
            for key, reading in data["accounts"].items():
                if not KEY.fullmatch(key):
                    raise Refused("bad_account_key")
                _reading(reading)
        else:
            _reading({k: v for k, v in data.items() if k in READING})
            if "window_minutes" in data and (
                type(data["window_minutes"]) is not int or data["window_minutes"] <= 0
            ):
                raise Refused("malformed")
        if "reset_credits" in data:
            _credit_shape(data["reset_credits"])
        return data
    except FileNotFoundError:
        raise
    except Refused:
        raise
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        raise Refused("malformed") from exc


def _age_reason(taken: datetime, written: datetime, now: datetime) -> str | None:
    if taken > now or (taken - written).total_seconds() > 300:
        return "clock_skew"
    if (now - taken).total_seconds() > 10800:
        return "reading_stale"
    return None


def _credits(raw: Any, now: datetime, fresh: bool) -> dict[str, Any] | None:
    if raw is None:
        return None
    unknown: dict[str, Any] = {
        "state": "unknown",
        "available": None,
        "expires": [],
        "information_only": True,
    }
    try:
        _fields(
            raw,
            {"status", "read_at", "available_count", "credits", "source", "note", "reason"},
            {"status"},
        )
        if raw["status"] != "read" or not fresh:
            return unknown
        read_at = timestamp(raw["read_at"])
        count = raw["available_count"]
        if (
            read_at > now
            or (now - read_at).total_seconds() > 10800
            or type(count) is not int
            or not 0 <= count <= 10000
            or not isinstance(raw["credits"], list)
        ):
            return unknown
        available = []
        for credit in raw["credits"]:
            _fields(
                credit,
                {"expires_at", "granted_at", "status"},
                {"expires_at", "granted_at", "status"},
            )
            expires = timestamp(credit["expires_at"])
            timestamp(credit["granted_at"])
            if credit["status"] not in ("available", "expired", "used"):
                return unknown
            if credit["status"] == "available" and expires > now:
                available.append(credit["expires_at"])
        if count != len(available):
            return unknown
        return {
            "state": "fresh",
            "available": count,
            "expires": sorted(available),
            "information_only": True,
        }
    except (ValueError, KeyError, TypeError, OverflowError):
        return unknown


def load_config() -> dict[str, Any]:
    """Read only the local usage table; never expose raw config errors."""
    base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    path = base / "mainbranch" / "config.toml"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError) as exc:
        raise ValueError("usage_config_unreadable") from exc
    try:
        tomllib = importlib.import_module("tomllib")
        data = tomllib.loads(text).get("usage", {})
    except (ImportError, ValueError) as exc:
        raise ValueError("usage_config_invalid_or_toml_unavailable") from exc
    if not isinstance(data, dict):
        raise ValueError("usage_config_invalid")
    return data


def _config(config: dict[str, Any]) -> None:
    if config.keys() - {"dir", "accounts", "role_accounts"}:
        raise ValueError("usage_config_invalid")
    directory = config.get("dir")
    if directory is not None and (
        not isinstance(directory, str) or not Path(directory).is_absolute()
    ):
        raise ValueError("usage_dir_must_be_absolute")
    for name in ("accounts", "role_accounts"):
        mapping = config.get(name, {})
        if not isinstance(mapping, dict):
            raise ValueError("usage_config_invalid")
        for key, value in mapping.items():
            if not isinstance(key, str) or not KEY.fullmatch(key) or not isinstance(value, str):
                raise ValueError("usage_config_invalid")
            if name == "role_accounts" and not KEY.fullmatch(value):
                raise ValueError("usage_config_invalid")
            if name == "accounts" and (not value or len(value) > 80 or not value.isprintable()):
                raise ValueError("usage_config_invalid")


def _roles(
    repo: Path, config: dict[str, Any], accounts: list[dict[str, Any]], now: datetime
) -> list[dict[str, Any]]:
    result = []
    by_key = {a["key"]: a for a in accounts}
    for path in sorted((repo / "core" / "team").glob("*.md")):
        if path.name == "README.md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
            if not text.startswith("---\n"):
                continue
            if "\n---" not in text[4:]:
                raise ValueError("role_profile_invalid")
            profile = yaml.safe_load(text[4:].split("\n---", 1)[0])
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ValueError("role_profile_invalid") from exc
        if not isinstance(profile, dict) or not ({"budget", "budget_cap"} & profile.keys()):
            continue
        budget = profile.get("budget")
        account_key = config.get("role_accounts", {}).get(path.stem)
        role: dict[str, Any] = {
            "id": path.stem,
            "account": account_key,
            "stop_at_pct": None,
            "state": "not_verified",
            "reason": "cap_not_structured",
            "budget_cap": profile.get("budget_cap")
            if isinstance(profile.get("budget_cap"), str)
            else None,
        }
        if "budget" in profile:
            if (
                not isinstance(budget, dict)
                or budget.keys() - {"stop_at_pct", "near_within"}
                or type(budget.get("stop_at_pct")) is not int
                or not 1 <= budget["stop_at_pct"] <= 100
                or type(budget.get("near_within", 5)) is not int
                or not 0 <= budget.get("near_within", 5) <= 100
            ):
                raise ValueError("budget_invalid")
            cap = budget["stop_at_pct"]
            role["stop_at_pct"] = cap
            role["reason"] = "account_unknown"
            account = by_key.get(account_key)
            if account is not None:
                role["reason"] = account["reason"]
                if account["state"] == "fresh":
                    if account["window_end"] and timestamp(account["window_end"]) <= now:
                        role["reason"] = "window_passed"
                    else:
                        used = account["used_pct"]
                        role["state"] = (
                            "at_cap"
                            if used >= cap
                            else "near"
                            if used >= cap - budget.get("near_within", 5)
                            else "under"
                        )
        result.append(role)
    return result


def collect(
    *,
    directory: str | None = None,
    now: str | None = None,
    repo: Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one snapshot pair. Codes rank config, cap, unknown, healthy."""
    result: dict[str, Any] = {
        "safe_to_share": False,
        "configured": False,
        "now_overridden": now is not None,
        "accounts": [],
        "roles": [],
        "errors": [],
        "warnings": [],
        "actions": [],
    }
    current = datetime.now(timezone.utc)
    try:
        if now is not None:
            current = timestamp(now)
        result["evaluated_at"] = current.strftime("%Y-%m-%dT%H:%M:%SZ")
        settings = dict(load_config() if config is None else config)
        if directory is not None:
            settings["dir"] = directory
        _config(settings)
        result["configured"] = bool(settings.get("dir"))
        labels = settings.get("accounts", {})
        if not result["configured"]:
            result["warnings"].append(
                {
                    "code": "usage_dir_unset",
                    "message": (
                        "Set usage.dir in local config.toml; consult your runtime's usage screen."
                    ),
                }
            )
        else:
            for filename in ("claude.json", "codex.json"):
                try:
                    multi = filename == "claude.json"
                    data = _read_file(Path(settings["dir"]) / filename, multi)
                except FileNotFoundError:
                    result["warnings"].append({"file": filename, "code": "missing_file"})
                    continue
                except Refused as exc:
                    result["accounts"].append(
                        {
                            "key": filename[:-5],
                            "label": filename[:-5],
                            "state": "not_verified",
                            "reason": str(exc),
                            "used_pct": None,
                            "window_end": None,
                        }
                    )
                    continue
                written = timestamp(data["written_at"])
                file_reason = (
                    "clock_skew"
                    if (written - current).total_seconds() > 300
                    else "snapshot_stale"
                    if (current - written).total_seconds() > 3600
                    else None
                )
                file_reason = file_reason or _age_reason(
                    timestamp(data["taken_at"]), written, current
                )
                readings = data["accounts"] if multi else {"codex": data}
                for key, reading in readings.items():
                    taken = timestamp(reading["taken_at"])
                    reason = file_reason or _age_reason(taken, written, current)
                    end = timestamp(reading["window_end"]) if reading.get("window_end") else None
                    hours = (end - current).total_seconds() / 3600 if end else None
                    account = {
                        "key": key,
                        "label": labels.get(key, key),
                        "state": "not_verified" if reason else "fresh",
                        "reason": reason,
                        "used_pct": reading["used_pct"],
                        "session_pct": reading.get("session_pct"),
                        "window_end": reading.get("window_end"),
                        "session_end": None,
                        "reading_age_seconds": max(0, int((current - taken).total_seconds())),
                        "sustainable_pct_per_hour": None,
                        "reset_credits": _credits(
                            reading.get("reset_credits"), current, reason is None
                        ),
                        "window_passed": hours is not None and hours <= 0,
                    }
                    if (
                        reading.get("session_end")
                        and 0
                        < (timestamp(reading["session_end"]) - current).total_seconds()
                        <= 21600
                    ):
                        account["session_end"] = reading["session_end"]
                    if reason is None and hours is not None and 0 < hours <= 192:
                        account["sustainable_pct_per_hour"] = round(
                            (100 - reading["used_pct"]) / hours, 2
                        )
                    result["accounts"].append(account)
                    credits = account["reset_credits"]
                    if (
                        reason is None
                        and hours is not None
                        and hours > 0
                        and reading["used_pct"] == 100
                        and credits
                        and credits["state"] == "fresh"
                        and credits["available"] > 0
                    ):
                        result["actions"].append(
                            {
                                "kind": "owner_question",
                                "account": key,
                                "message": (
                                    f"{account['label']} is at 100% for this week. "
                                    f"You have {credits['available']} banked reset(s). {QUESTION}"
                                ),
                            }
                        )
            if not result["accounts"]:
                result["warnings"].append({"code": "no_snapshot"})
        known = {a["key"] for a in result["accounts"] if a.get("used_pct") is not None}
        if any(key not in known for key in settings.get("role_accounts", {}).values()):
            raise ValueError("role_account_not_in_snapshot")
        result["roles"] = _roles(repo or Path.cwd(), settings, result["accounts"], current)
    except (ValueError, TypeError, OverflowError) as exc:
        code = (
            str(exc)
            if str(exc)
            in {
                "usage_config_unreadable",
                "usage_config_invalid_or_toml_unavailable",
                "usage_config_invalid",
                "usage_dir_must_be_absolute",
                "role_profile_invalid",
                "budget_invalid",
                "role_account_not_in_snapshot",
            }
            else "invalid_now"
        )
        result["errors"].append({"code": code})
    accounts, roles = result["accounts"], result["roles"]
    summary = {
        "fresh": sum(a["state"] == "fresh" for a in accounts),
        "not_verified": sum(a["state"] != "fresh" for a in accounts),
        "roles_at_cap": sum(r["state"] == "at_cap" for r in roles),
        "roles_near": sum(r["state"] == "near" for r in roles),
    }
    result["summary"] = summary
    full = any(
        a["state"] == "fresh" and a["used_pct"] == 100 and not a.get("window_passed")
        for a in accounts
    )
    result["exit_code"] = (
        2
        if result["errors"]
        else 1
        if full or summary["roles_at_cap"]
        else 3
        if not accounts
        or summary["not_verified"]
        or any(r["state"] == "not_verified" for r in roles)
        else 0
    )
    result["ok"] = result["exit_code"] == 0
    return result


def status_view(*, repo: Path, now: datetime) -> dict[str, Any]:
    try:
        settings = load_config()
    except ValueError:
        return {"configured": False, "errors": [{"code": "usage_config_invalid"}]}
    if not settings.get("dir"):
        return {"configured": False}
    result = collect(repo=repo, now=now.strftime("%Y-%m-%dT%H:%M:%SZ"), config=settings)
    if not result["configured"] and not result["errors"]:
        return {"configured": False}
    return {
        "configured": result["configured"],
        "safe_to_share": False,
        "summary": result["summary"],
        "evaluated_at": result["evaluated_at"],
        "accounts": [
            {k: a[k] for k in ("key", "label", "state", "used_pct", "window_end")}
            for a in result["accounts"]
        ],
        "roles": [r for r in result["roles"] if r["state"] in ("near", "at_cap")],
        "errors": result["errors"],
    }


def status_line(view: dict[str, Any]) -> str:
    if view.get("errors"):
        return "Usage: unknown (configuration error). Run: mb usage"
    parts = []
    for account in view.get("accounts", []):
        if account["state"] != "fresh":
            parts.append(f"{account['label']} unknown")
            continue
        text = f"{account['label']} {account['used_pct']}%"
        if account["window_end"]:
            hours = (
                timestamp(account["window_end"]) - timestamp(view["evaluated_at"])
            ).total_seconds() / 3600
            text += f" (resets in {hours:.1f} h)" if hours > 0 else " (reading predates reset)"
        parts.append(text)
    line = "Usage: " + (", ".join(parts) or "unknown. Run: mb usage")
    if view.get("roles"):
        roles = ", ".join(f"{r['id']} ({r['stop_at_pct']}%)" for r in view["roles"])
        line += f". Near cap: {roles}. Run: mb usage"
    return line


def render(result: dict[str, Any]) -> str:
    lines = [
        f"Usage  {result['summary']['fresh']} accounts fresh, "
        f"{result['summary']['not_verified']} unknown"
    ]
    for warning in result["warnings"]:
        lines.append(warning.get("message", warning["code"]))
    for error in result["errors"]:
        lines.append("Usage error: " + error["code"])
    for a in result["accounts"]:
        if a["state"] != "fresh":
            last = f", was {a['used_pct']}%" if a["used_pct"] is not None else ""
            age = a.get("reading_age_seconds")
            old = f", reading {age // 60} min old" if age is not None else ""
            lines.append(f"  {a['label']}: unknown ({a['reason']}){last}{old}")
            if a.get("reset_credits"):
                lines.append("    banked resets: unknown, information only")
            continue
        line = f"  {a['label']}: {a['used_pct']}% used"
        if a.get("session_pct") is not None:
            line += f" (session {a['session_pct']}%)"
        if a["window_end"]:
            remaining = (
                timestamp(a["window_end"]) - timestamp(result["evaluated_at"])
            ).total_seconds() / 3600
            line += f"; window ends {a['window_end']} (in {remaining:.1f} h)"
        lines.append(line)
        lines.append(f"    reading {a['reading_age_seconds'] // 60} min old")
        if a.get("session_end"):
            lines.append(f"    session ends {a['session_end']}")
        if a.get("window_passed"):
            lines.append("    This reading predates the reset, so usage is likely lower now.")
        if a.get("sustainable_pct_per_hour") is not None:
            lines.append(f"    pace: {a['sustainable_pct_per_hour']}%/h sustainable")
        credits = a.get("reset_credits")
        if credits:
            count = credits["available"] if credits["state"] == "fresh" else "unknown"
            lines.append(f"    banked resets: {count}, information only")
            if credits["expires"]:
                lines.append("    expire: " + ", ".join(credits["expires"]))
    if result["roles"]:
        lines.append("Roles")
        for r in result["roles"]:
            if r["stop_at_pct"] is None:
                lines.append(f"  {r['state']} {r['id']}: {r['budget_cap'] or 'cap unknown'}")
                continue
            lines.append(
                f"  {r['state']} {r['id']}: cap {r['stop_at_pct']}%, "
                f"account {r['account'] or 'unknown'}"
            )
    lines.extend(a["message"] for a in result["actions"])
    return "\n".join(lines)
