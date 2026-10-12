"""``mb fleet checkin``: one read-only card per business (#1177).

Reads the user-level hub list, runs ``mb status --json --peek`` for each hub
that has a local checkout (a bounded child process of this interpreter, never
the ``mb`` on PATH), and folds in the cached fleet snapshot. Writes nothing:
no file in a business repo, the hub list, connect state or the cache. It does
not fetch, prompt, repair a keychain, call a paid API or a model, send, or
schedule. Delivery and timing belong to the caller.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mb import fleet

CHECKIN_SCHEMA = "mb.fleet.checkin"
CHECKIN_SCHEMA_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 60
STALE_SNAPSHOT_SECONDS = 86400
CAPPED_LIST = 5  # status lists active/due/overdue bets cut to five
SECTION_NAMES = ("loop", "bets", "exposure", "checkpoint", "github", "connections", "sites")

# What a status child returns: (parsed JSON or None, short safe error text).
StatusRunner = Callable[[Path, int], tuple[dict[str, Any] | None, str]]


# ---------------------------------------------------------------------------
# Gathering one hub's status
# ---------------------------------------------------------------------------


def run_status_child(checkout: Path, timeout: int) -> tuple[dict[str, Any] | None, str]:
    """Run ``mb status <checkout> --json --peek`` in a bounded child process.

    The child leads its own process group so a timeout takes `gh` and `git`
    grandchildren down with it. Only stdout is parsed; stderr never reaches a card.
    """
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"  # `git status` must not rewrite .git/index
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "mb", "status", str(checkout), "--json", "--peek"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
            text=True,
        )
    except OSError:
        return None, "mb status could not be started"
    try:
        stdout, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            os.killpg(proc.pid, signal.SIGKILL)
        with contextlib.suppress(Exception):
            proc.communicate(timeout=5)
        return None, f"mb status did not finish within {timeout} seconds"
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None, "mb status gave no readable result"
    if not isinstance(payload, dict):
        return None, "mb status gave no readable result"
    if "readiness" not in payload:
        errors = payload.get("errors")
        first = errors[0] if isinstance(errors, list) and errors else None
        message = first.get("message") if isinstance(first, dict) else first
        return None, str(message or "mb status could not read this repo")[:200]
    return payload, ""


# ---------------------------------------------------------------------------
# The cached fleet snapshot (read-only)
# ---------------------------------------------------------------------------


def read_snapshot(path: Path) -> tuple[dict[str, Any] | None, str]:
    """Read the newest cached snapshot without creating or changing anything."""
    if not path.is_file():
        return None, "missing"
    try:
        uri = f"{path.absolute().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            row = db.execute("SELECT payload FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
    except sqlite3.Error:
        return None, "unreadable"
    if not row:
        return None, "missing"
    try:
        payload = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return None, "unreadable"
    return (payload, "ok") if isinstance(payload, dict) else (None, "unreadable")


def _snapshot_block(
    snapshot: dict[str, Any] | None, state: str, now: datetime
) -> tuple[dict[str, Any], dict[str, Any]]:
    block: dict[str, Any] = {
        "state": state,
        "refreshed_at": "",
        "age_seconds": None,
        "refresh_errors": 0,
        "stale": False,
    }
    if snapshot is None:
        return block, {}
    refreshed = fleet._parse_time(str(snapshot.get("refreshed_at") or ""))
    age = int((now - refreshed).total_seconds()) if refreshed else None
    block.update(
        refreshed_at=str(snapshot.get("refreshed_at") or ""),
        age_seconds=age,
        refresh_errors=len(snapshot.get("refresh_errors") or []),
        stale=age is None or age > STALE_SNAPSHOT_SECONDS,
    )
    if block["stale"]:
        block["state"] = "stale"
    return block, snapshot


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _tilde(path: Path | str, home: str) -> str:
    text = str(path)
    if home and (text == home or text.startswith(home + os.sep)):
        return "~" + text[len(home) :]
    return Path(text).name


def _scrub(value: Any, home: str) -> Any:
    """Replace the home directory with ``~`` in every string of the output."""
    if isinstance(value, str):
        return value.replace(home, "~") if home and home in value else value
    if isinstance(value, list):
        return [_scrub(item, home) for item in value]
    if isinstance(value, dict):
        return {key: _scrub(item, home) for key, item in value.items()}
    return value


def _section(state: str, as_of: str, source: str, text: str, **facts: Any) -> dict[str, Any]:
    return {"state": state, "as_of": as_of, "source": source, "text": text, **facts}


def _plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one}" if count == 1 else f"{count} {many or one + 's'}"


def _more(count: int) -> str:
    return f"{count}+" if count >= CAPPED_LIST else str(count)


STATUS_SOURCE = "mb status --json --peek"
FLEET_SOURCE = "mb fleet status (cached snapshot)"


def _not_checked(source: str, text: str) -> dict[str, Any]:
    return _section("not_checked", "", source, text)


# ---------------------------------------------------------------------------
# Sections from one status payload
# ---------------------------------------------------------------------------


def _loop_section(status: dict[str, Any], as_of: str) -> dict[str, Any]:
    level = str(_dict(status.get("readiness")).get("level") or "unknown")
    actions = [_dict(item) for item in _list(status.get("ranked_actions"))]
    top = actions[0] if actions else {}
    title = str(top.get("title") or "")
    words = {
        "ready": "Ready to work.",
        "needs_attention": "Needs attention.",
        "not_ready": "Not ready yet.",
    }
    text = words.get(level, "Readiness not known.")
    if title and level != "ready":
        text += f" Next: {title}."
    return _section(
        "ok" if level == "ready" else "attention",
        as_of,
        STATUS_SOURCE,
        text,
        level=level,
        top_action={"title": title, "severity": str(top.get("severity") or "")} if title else None,
    )


def _bets_section(status: dict[str, Any], as_of: str) -> dict[str, Any]:
    bets = _dict(_dict(status.get("brain")).get("bets"))
    active = [_dict(item) for item in _list(bets.get("active"))]
    due_soon = _list(bets.get("due_soon"))
    overdue = _list(bets.get("overdue"))
    signals = _list(_dict(bets.get("exit_criteria")).get("triggered_failure_signals"))
    items = []
    for bet in active:
        item: dict[str, Any] = {
            "title": str(bet.get("title") or ""),
            "status": str(bet.get("status") or ""),
            "deadline": str(bet.get("deadline") or ""),
        }
        for key in ("stage", "commitment"):
            if bet.get(key):
                item[key] = bet[key]
        items.append(item)
    count = len(active)
    if not count:
        text = "No active bets."
    else:
        text = _plural(count, "active bet") if count < CAPPED_LIST else f"{count}+ active bets"
        if overdue:
            text += f", {_more(len(overdue))} overdue"
        if due_soon:
            text += f", {_more(len(due_soon))} due within a week"
        if signals:
            text += f", {_plural(len(signals), 'exit signal')} triggered"
        text += "."
    attention = bool(overdue or signals)
    return _section(
        "attention" if attention else "ok",
        as_of,
        STATUS_SOURCE,
        text,
        active_count=count,
        count_capped=count >= CAPPED_LIST,
        due_soon=len(due_soon),
        overdue=len(overdue),
        triggered_exit_signals=len(signals),
        items=items,
    )


def _exposure_section(status: dict[str, Any], as_of: str) -> dict[str, Any]:
    raw = _dict(_dict(status.get("money_path")).get("active_bets"))
    count = _int(raw.get("count"))
    if not raw:
        return _not_checked(STATUS_SOURCE, "Exposure not reported.")
    facts = {
        "active_count": count,
        "checked": bool(raw.get("checked")),
        "ledger_unavailable": bool(raw.get("ledger_unavailable")),
        "anchored": _int(raw.get("anchored")),
        "unanchored": _int(raw.get("unanchored")),
        "over_cap": len(_list(raw.get("over_cap"))),
    }
    if not count:
        return _section("not_applicable", as_of, STATUS_SOURCE, "No bets to check.", **facts)
    if facts["ledger_unavailable"]:
        return _section("not_checked", as_of, STATUS_SOURCE, "Books: can't check.", **facts)
    if not facts["checked"]:
        return _section("not_checked", as_of, STATUS_SOURCE, "Exposure not checked.", **facts)
    if facts["over_cap"]:
        text = f"{_plural(facts['over_cap'], 'bet')} over the exposure cap."
        return _section("attention", as_of, STATUS_SOURCE, text, **facts)
    text = "No bet over its exposure cap."
    if facts["unanchored"]:
        text += f" {_plural(facts['unanchored'], 'bet')} not tied to the books yet."
    return _section(
        "attention" if facts["unanchored"] else "ok", as_of, STATUS_SOURCE, text, **facts
    )


def _checkpoint_section(status: dict[str, Any], as_of: str) -> dict[str, Any]:
    git = _dict(status.get("git"))
    events = [_dict(e) for e in _list(_dict(status.get("journal")).get("events"))]
    last = next((e for e in events if e.get("recognized_as") != "unrecognized"), {})
    unsaved = _int(git.get("dirty_count"))
    ahead = git.get("ahead") if isinstance(git.get("ahead"), int) else None
    behind = git.get("behind") if isinstance(git.get("behind"), int) else None
    parts = []
    if last:
        parts.append(
            f"Last checkpoint {last.get('date') or ''}: {last.get('summary') or ''}".strip()
        )
    else:
        parts.append("No checkpoint in the last 14 days.")
    if unsaved:
        parts.append(f"{_plural(unsaved, 'unsaved file')}.")
    if ahead:
        parts.append(f"{_plural(ahead, 'commit')} not pushed.")
    if behind:
        parts.append(f"{_plural(behind, 'commit')} behind the remote.")
    return _section(
        "attention" if unsaved or ahead or behind else "ok",
        as_of,
        STATUS_SOURCE,
        " ".join(parts),
        last={
            "date": str(last.get("date") or ""),
            "summary": str(last.get("summary") or ""),
        }
        if last
        else None,
        unsaved_files=unsaved,
        ahead=ahead,
        behind=behind,
    )


def _github_section(status: dict[str, Any], as_of: str) -> dict[str, Any]:
    github = _dict(status.get("github"))
    if not github or github.get("degraded") or not github.get("available", True):
        return _section("not_checked", as_of, STATUS_SOURCE, "GitHub: not checked.")
    summary = _dict(github.get("summary"))
    counts = {
        key: _int(summary.get(key))
        for key in (
            "open_proposals",
            "attention_requests",
            "assigned_tasks",
            "blocked_or_stale_tasks",
        )
    }
    parts = []
    if counts["open_proposals"]:
        parts.append(f"{_plural(counts['open_proposals'], 'open proposal')}")
    if counts["attention_requests"]:
        parts.append(f"{_plural(counts['attention_requests'], 'review request')}")
    if counts["assigned_tasks"]:
        parts.append(f"{_plural(counts['assigned_tasks'], 'task')} assigned")
    if counts["blocked_or_stale_tasks"]:
        parts.append(f"{_plural(counts['blocked_or_stale_tasks'], 'task')} blocked or stale")
    needs = bool(
        counts["attention_requests"] or counts["assigned_tasks"] or counts["blocked_or_stale_tasks"]
    )
    text = (", ".join(parts) + ".") if parts else "Nothing waiting on GitHub."
    return _section("attention" if needs else "ok", as_of, STATUS_SOURCE, text, **counts)


def _connections_section(status: dict[str, Any], as_of: str) -> dict[str, Any]:
    integrations = _dict(status.get("integrations"))
    summary = _dict(integrations.get("summary"))
    if not integrations:
        return _not_checked(STATUS_SOURCE, "Connections: not checked.")
    facts = {
        "configured": _int(summary.get("configured")),
        "healthy": _int(summary.get("healthy")),
        "needs_repair": _int(summary.get("needs_repair")),
        "unverified": _int(summary.get("unverified")),
        "not_checked": _int(summary.get("not_checked")),
    }
    if not facts["configured"]:
        return _section("not_applicable", as_of, STATUS_SOURCE, "No connections set up.", **facts)
    text = f"{facts['healthy']} of {facts['configured']} connections ready."
    if facts["needs_repair"]:
        text += f" {_plural(facts['needs_repair'], 'needs', 'need')} repair."
    if facts["not_checked"]:
        text += f" {facts['not_checked']} not checked."
    state = (
        "attention" if facts["needs_repair"] else ("not_checked" if facts["not_checked"] else "ok")
    )
    return _section(state, as_of, STATUS_SOURCE, text, **facts)


# ---------------------------------------------------------------------------
# Sites and freshness from the cached fleet snapshot
# ---------------------------------------------------------------------------

_SITE_FLAG_WORDS = {
    "ci_failing": "checks failing",
    "deploy_behind_main": "live site behind main",
    "deploy_dirty": "live site has unsaved changes",
    "deploy_differs_from_main": "live site differs from main",
}


def _sites_section(hub: str, snapshot: dict[str, Any], snap_state: str) -> dict[str, Any]:
    if not snapshot:
        text = "Sites: not checked (no fleet snapshot yet)."
        return _section("not_checked", "", FLEET_SOURCE, text, snapshot=snap_state)
    as_of = str(snapshot.get("refreshed_at") or "")
    rows = [_dict(r) for r in _list(snapshot.get("sites")) if _dict(r).get("hub") == hub]
    repos = [_dict(r) for r in _list(snapshot.get("repos")) if _dict(r).get("hub") == hub]
    if not rows and not repos:
        return _section("not_applicable", as_of, FLEET_SOURCE, "No sites in the snapshot.")
    flags: dict[str, int] = {}
    for row in rows:
        for flag in _list(row.get("flags")):
            flags[str(flag)] = flags.get(str(flag), 0) + 1
    alerts = sum(
        _int(_dict(r.get("dependabot_alerts")).get("open"))
        for r in repos
        if _dict(r.get("dependabot_alerts")).get("state") == "ok"
    )
    words = [
        f"{_SITE_FLAG_WORDS[flag]} ({n})"
        for flag, n in sorted(flags.items())
        if flag in _SITE_FLAG_WORDS
    ]
    if alerts:
        words.append(f"{_plural(alerts, 'security alert')}")
    text = (
        f"{_plural(len(rows), 'site')}: " + ", ".join(words) + "."
        if words
        else f"{_plural(len(rows), 'site')}, nothing flagged."
    )
    return _section(
        "attention" if words else "ok",
        as_of,
        FLEET_SOURCE,
        text,
        sites=len(rows),
        flags=dict(sorted(flags.items())),
        security_alerts=alerts,
    )


def _freshness(
    status: dict[str, Any] | None, hub: dict[str, Any], snapshot: dict[str, Any]
) -> dict[str, Any]:
    git = _dict(_dict(status).get("git"))
    local = str(git.get("commit") or "")
    main_sha = ""
    for repo in _list(snapshot.get("repos")):
        row = _dict(repo)
        if row.get("repo") == hub["remote_full_name"]:
            main_sha = str(row.get("main_sha") or "")
    matches: bool | None = None
    on_default = bool(git.get("branch")) and git.get("branch") == git.get("default_branch")
    if local and main_sha and on_default:
        matches = main_sha.startswith(local)
    return {
        "status_generated_at": str(_dict(status).get("generated_at") or ""),
        "local_head": local,
        "main_sha": main_sha[:12],
        "local_matches_remote": matches,
    }


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------


def _card_base(hub: dict[str, Any], home: str) -> dict[str, Any]:
    checkout = hub["checkout"]
    return {
        "hub": hub["name"],
        "display_name": hub["name"],
        "remote": f"github:{hub['remote_full_name']}",
        "checkout": _tilde(checkout, home) if checkout else "",
    }


def _sections_unavailable(
    text: str, hub: str, snapshot: dict[str, Any], snap_state: str, state: str
) -> dict[str, Any]:
    sections = {name: _section(state, "", STATUS_SOURCE, text) for name in SECTION_NAMES}
    sections["sites"] = _sites_section(hub, snapshot, snap_state)
    return sections


def _make_card(
    hub: dict[str, Any],
    *,
    home: str,
    snapshot: dict[str, Any],
    snap_state: str,
    timeout: int,
    runner: StatusRunner,
) -> dict[str, Any]:
    card = _card_base(hub, home)
    checkout: Path | None = hub["checkout"]
    name = hub["name"]
    status: dict[str, Any] | None = None
    error = ""
    if checkout is None:
        state, checkout_state = "remote_only", "not_on_this_machine"
        text = "Lives on another machine; showing what GitHub last reported."
    elif not checkout.is_dir():
        state, checkout_state = "unavailable", "missing"
        text = "The local copy is missing on this machine."
    else:
        status, error = runner(checkout, timeout)
        if status is None:
            state, checkout_state = "unavailable", "ok"
            text = f"Could not read this business: {error}"
        elif not _dict(status.get("repo")).get("looks_like_mainbranch_repo"):
            state, checkout_state = "unavailable", "not_a_business_repo"
            text = "This folder is not a Main Branch business repo."
        else:
            state, checkout_state = "ok", "ok"
            text = ""
    card.update(state=state, checkout_state=checkout_state, reason=text if state != "ok" else "")
    card["freshness"] = _freshness(status, hub, snapshot)
    if state == "ok" and status is not None:
        as_of = str(status.get("generated_at") or "")
        sections = {
            "loop": _loop_section(status, as_of),
            "bets": _bets_section(status, as_of),
            "exposure": _exposure_section(status, as_of),
            "checkpoint": _checkpoint_section(status, as_of),
            "github": _github_section(status, as_of),
            "connections": _connections_section(status, as_of),
            "sites": _sites_section(name, snapshot, snap_state),
        }
        level = sections["loop"]["level"]
        card["verdict"] = "needs_you" if level in {"needs_attention", "not_ready"} else "on_track"
        if card["freshness"]["local_matches_remote"] is False:
            sections["loop"]["text"] += " May miss work saved elsewhere."
    else:
        sections = _sections_unavailable(
            text,
            name,
            snapshot,
            snap_state,
            "not_applicable" if state == "remote_only" else "unavailable",
        )
        site_state = sections["sites"]["state"]
        if state == "remote_only" and site_state == "attention":
            card["verdict"] = "needs_you"
        elif state == "remote_only" and site_state in {"ok", "not_applicable"}:
            card["verdict"] = "on_track"
        else:
            card["verdict"] = "cannot_see"
    card["sections"] = sections
    card["text"] = _card_text(card, text)
    return card


def _card_text(card: dict[str, Any], lead: str) -> str:
    verdict = {"needs_you": "Needs you", "on_track": "On track", "cannot_see": "Can't see"}[
        card["verdict"]
    ]
    lines = [f"{card['display_name']}: {verdict}."]
    if card["state"] == "ok":
        for name in SECTION_NAMES:
            section = card["sections"][name]
            if section["state"] in {"attention", "not_checked"} or name in {"loop", "bets"}:
                lines.append(f"  {section['text']}")
    else:
        lines.append(f"  {lead}")
        sites = card["sections"]["sites"]
        if sites["state"] in {"ok", "attention"}:
            lines.append(f"  {sites['text']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def checkin(
    *,
    config: Path | None = None,
    cache: Path | None = None,
    hub: str = "",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    status_runner: StatusRunner | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, Any], int]:
    """Build the check-in document and its exit code.

    Raises ``fleet.FleetConfigError`` for a missing or invalid hub list, an
    unknown ``hub`` or a bad ``timeout`` (exit 2, no cards).
    """
    if timeout < 1:
        raise fleet.FleetConfigError("--timeout must be at least 1 second")
    settings = fleet.load_config(config)
    hubs = settings["hubs"]
    if hub:
        hubs = [item for item in hubs if item["name"] == hub]
        if not hubs:
            raise fleet.FleetConfigError(f"no hub named {hub!r} in the hub list")
    current = now or datetime.now(timezone.utc)
    home = str(Path.home())
    snapshot, snap_state = read_snapshot(cache or fleet.cache_path())
    snapshot_block, snapshot_data = _snapshot_block(snapshot, snap_state, current)
    runner = status_runner or run_status_child
    cards = [
        _make_card(
            item,
            home=home,
            snapshot=snapshot_data,
            snap_state=snapshot_block["state"],
            timeout=timeout,
            runner=runner,
        )
        for item in hubs
    ]
    counts = {"needs_you": 0, "on_track": 0, "cannot_see": 0}
    for card in cards:
        counts[card["verdict"]] += 1
    unreadable = [card for card in cards if card["state"] == "unavailable"]
    overview_text = (
        f"{_plural(len(cards), 'business', 'businesses')}: {counts['needs_you']} need you, "
        f"{counts['on_track']} on track, {counts['cannot_see']} can't be seen."
    )
    exit_code = 1 if unreadable or snap_state == "unreadable" else 0
    warnings = []
    if snapshot_block["state"] in {"missing", "unreadable"}:
        warnings.append("no usable fleet snapshot; site facts are not checked")
    elif snapshot_block["stale"]:
        warnings.append("the fleet snapshot is over a day old")
    if snapshot_block["refresh_errors"]:
        warnings.append("the fleet snapshot has read failures; some site facts may be missing")
    errors = [f"{card['display_name']}: {card['reason']}" for card in unreadable]
    if snap_state == "unreadable":
        errors.append("the fleet snapshot could not be read")
    document: dict[str, Any] = {
        "ok": exit_code == 0,
        "schema": CHECKIN_SCHEMA,
        "schema_version": CHECKIN_SCHEMA_VERSION,
        "generated_at": current.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "safe_to_share": False,
        "hub_list": {"state": "ok", "hubs": len(settings["hubs"]), "shown": len(cards)},
        "fleet_snapshot": snapshot_block,
        "overview": {**counts, "text": overview_text},
        "cards": cards,
        "errors": errors,
        "warnings": warnings,
        "actions": [],
    }
    real_home = os.path.realpath(home)
    if real_home != home:
        document = _scrub(document, real_home)
    return _scrub(document, home), exit_code


def render_text(document: dict[str, Any]) -> None:
    """Print the overview and one short card per business, ready to paste."""
    lines = [document["overview"]["text"], ""]
    for card in document["cards"]:
        lines.extend([card["text"], ""])
    for warning in document.get("warnings") or []:
        lines.append(f"Note: {warning}.")
    print("\n".join(lines).rstrip())
