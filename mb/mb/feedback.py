"""Local friction log for ``mb feedback`` (#986).

Agents and operators hit friction in ``mb``: a refused command, a confusing
message, a missing probe. ``mb feedback "<text>"`` appends one JSON line to a
local file in the user state directory so the friction survives the session,
and ``mb feedback rollup`` turns the file into a Markdown draft a maintainer
can turn into issues. Credential and safety refusals log themselves through
``record_refusal``.

Nothing here sends anything anywhere. Every line is scrubbed before it is
written (``mb.feedback_scrub``): secret-shaped values are redacted, home
directory paths become ``~`` and other absolute paths ``<local-path>``. A
refusal line carries the rule that fired and the command, never the refused
value.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mb import __version__, feedback_scrub
from mb.durable import UnconfirmedWriteError, atomic_write_text, state_lock

SCHEMA_VERSION = 1
FEEDBACK_FILENAME = "feedback.jsonl"
LOG_ENV_VAR = "MB_FEEDBACK_LOG"
SUBCOMMANDS = ("rollup", "list", "clear")
KINDS = ("feedback", "refusal")
MAX_TEXT_CHARS = 4000
DEFAULT_SINCE = "7d"
MAX_SINCE = timedelta(days=36500)

_SINCE_RE = re.compile(r"^\s*(\d+)\s*([hdw])\s*$", re.IGNORECASE)


def state_dir() -> Path:
    """Return the Main Branch user state directory (honours ``XDG_STATE_HOME``)."""
    base = os.environ.get("XDG_STATE_HOME", "").strip()
    root = Path(base).expanduser() if base else Path.home() / ".local" / "state"
    return root / "mainbranch"


def feedback_path() -> Path:
    return state_dir() / FEEDBACK_FILENAME


def display_path(path: Path) -> str:
    """Render a path for output without an absolute path in it.

    Paths under the state directory read as ``$XDG_STATE_HOME/...`` when that
    variable is set, else the home directory reads as ``~``.
    """
    base = os.environ.get("XDG_STATE_HOME", "").strip()
    if base:
        try:
            return "$XDG_STATE_HOME/" + path.relative_to(Path(base).expanduser()).as_posix()
        except ValueError:
            pass
    return scrub(str(path))


def refusal_logging_enabled() -> bool:
    return os.environ.get(LOG_ENV_VAR, "").strip().lower() not in {"0", "false", "no", "off"}


def scrub(text: str) -> str:
    """Cap ``text`` at ``MAX_TEXT_CHARS``, then redact secrets and absolute paths.

    The cap comes first so a huge input is never scanned in full. A quote cut
    open by the cap redacts to the end, like any unterminated quote. See
    ``mb.feedback_scrub`` for the rules: the default is to redact.
    """
    if len(text) <= MAX_TEXT_CHARS:
        return feedback_scrub.scrub(text)
    return feedback_scrub.scrub(text[:MAX_TEXT_CHARS]) + " [truncated]"


_COMMAND_WORD_RE = re.compile(r"[a-z][a-z0-9-]*")
_RULE_RE = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,63}")
MAX_COMMAND_WORDS = 3


def command_path(value: str | None) -> str | None:
    """Keep only the ``mb`` command path: ``mb`` plus up to three plain words.

    Stops at the first token that is not a lowercase command word (a flag, a
    value, a path, a quote), and drops everything after it, so arguments are
    never stored. ``None`` when no command word remains.
    """
    words: list[str] = []
    tokens = (value or "").split()
    if tokens[:1] == ["mb"]:
        tokens = tokens[1:]
    for token in tokens[:MAX_COMMAND_WORDS]:
        if not _COMMAND_WORD_RE.fullmatch(token):
            break
        words.append(token)
    return f"mb {' '.join(words)}" if words else None


def rule_slug(value: str | None) -> str:
    """A refusal rule id such as ``connect.config_boundary``, else ``other``."""
    rule = value or ""
    return rule if _RULE_RE.fullmatch(rule) else "other"


def repo_kind(repo: str | Path = ".") -> str:
    """Classify the repo a line was written from: hub, child, engine or none.

    Uses the shared classifier, so feedback agrees with the launch screen,
    ``mb doctor`` and ``mb checkpoint``. ``unknown`` only when the classifier
    itself fails; logging never fails on it.
    """
    from mb.topology import classify_repo

    try:
        return str(classify_repo(Path(repo).resolve())["kind"])
    except Exception:  # noqa: BLE001 - a log line must not fail on classification
        return "unknown"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _storage_error(code: str, action: str, exc: OSError, target: Path) -> dict[str, Any]:
    """A structured error for a failed read or write, with no path in it."""
    if isinstance(exc, UnconfirmedWriteError):
        return {
            "ok": False,
            "errors": [
                {
                    "code": code,
                    "message": "the feedback file was rewritten, but the write could not be "
                    "confirmed on disk; check the disk, then rerun the command",
                }
            ],
            "path": display_path(target),
            "safe_to_share": True,
        }
    if isinstance(exc, TimeoutError):
        reason = "timed out waiting for the feedback file lock"
    else:
        reason = exc.strerror or type(exc).__name__
    return {
        "ok": False,
        "errors": [
            {"code": code, "message": scrub(f"could not {action} the feedback file: {reason}")}
        ],
        "path": display_path(target),
        "safe_to_share": True,
    }


def _append(entry: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
    with state_lock(path, timeout=2.0):
        fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "r+b") as handle:
            # A crash mid-write can leave an unterminated fragment; start on a
            # fresh line so this record does not merge into it.
            size = handle.seek(0, os.SEEK_END)
            if size:
                handle.seek(size - 1)
                if handle.read(1) != b"\n":
                    line = "\n" + line
            handle.write(line.encode("utf-8"))


def record(
    text: str,
    *,
    command: str | None = None,
    repo: str | Path = ".",
    path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append one scrubbed ``kind: feedback`` line."""
    target = path or feedback_path()
    body = scrub(text.strip())
    if not body:
        return {
            "ok": False,
            "errors": [{"code": "empty_feedback", "message": "feedback text is empty"}],
            "path": display_path(target),
            "safe_to_share": True,
        }
    entry = {
        "schema": SCHEMA_VERSION,
        "kind": "feedback",
        "time": _iso(now or _now()),
        "mb_version": __version__,
        "command": command_path(command),
        "repo_kind": repo_kind(repo),
        "text": body,
    }
    try:
        _append(entry, target)
    except OSError as exc:
        return _storage_error("feedback_write_failed", "write", exc, target)
    return {
        "ok": True,
        "entry": entry,
        "path": display_path(target),
        "sent": False,
        "safe_to_share": True,
    }


def record_refusal(
    rule: str,
    command: str,
    *,
    repo: str | Path = ".",
    path: Path | None = None,
) -> bool:
    """Append a ``kind: refusal`` line for a credential or safety boundary.

    Callers pass the rule that fired and the command, never the refused value.
    Only the rule slug (else ``other``) and the command path are stored.
    Logging is best effort: it never raises and never changes the refusal.
    ``MB_FEEDBACK_LOG=0`` turns it off. Returns whether a line was written.
    """
    if not refusal_logging_enabled():
        return False
    try:
        entry = {
            "schema": SCHEMA_VERSION,
            "kind": "refusal",
            "time": _iso(_now()),
            "mb_version": __version__,
            "command": command_path(command),
            "rule": rule_slug(rule),
            "repo_kind": repo_kind(repo),
        }
        _append(entry, path or feedback_path())
    except Exception:  # noqa: BLE001 - logging must never break the refusal itself
        return False
    return True


_OPTIONAL_TEXT_FIELDS = ("command", "rule", "text", "repo_kind", "mb_version")


def _decode_line(raw: bytes) -> dict[str, Any] | None:
    """Decode and validate one line; ``None`` when it is not a usable record."""
    try:
        item = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return None
    if not isinstance(item, dict):
        return None
    time = item.get("time")
    if not isinstance(time, str) or _parse_time(time) is None:
        return None
    if item.get("kind", "feedback") not in KINDS:
        return None
    for field in _OPTIONAL_TEXT_FIELDS:
        if item.get(field) is not None and not isinstance(item[field], str):
            return None
    return item


def _iter_lines(path: Path) -> Iterator[dict[str, Any] | None]:
    try:
        handle = path.open("rb")
    except FileNotFoundError:
        return
    with handle:
        for raw in handle:
            if raw.strip():
                yield _decode_line(raw)


def _parse_time(value: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def read_entries(path: Path | None = None) -> tuple[list[dict[str, Any]], int]:
    """Return parsed entries oldest first and the count of unreadable lines."""
    entries: list[dict[str, Any]] = []
    skipped = 0
    for item in _iter_lines(path or feedback_path()):
        if item is None:
            skipped += 1
            continue
        entries.append(item)
    entries.sort(key=lambda item: item["time"])
    return entries, skipped


def parse_since(value: str, *, now: datetime | None = None) -> datetime:
    """Parse ``7d`` / ``12h`` / ``2w`` or an ISO date into a UTC cutoff."""
    current = now or _now()
    match = _SINCE_RE.match(value or "")
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        hours = amount * {"h": 1, "d": 24, "w": 168}[unit]
        if hours > MAX_SINCE.total_seconds() / 3600:
            raise ValueError(f"--since {value.strip()} is longer than 100 years")
        return current - timedelta(hours=hours)
    return _parse_date(value)


def _parse_date(value: str) -> datetime:
    text = (value or "").strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        moment = _parse_time(text)
        if moment is None:
            raise ValueError(
                "expected a duration such as 7d, 12h or 2w, or a date such as "
                f"2026-10-01; got {text!r}"
            ) from None
        return moment
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)


def _since_filter(entries: list[dict[str, Any]], cutoff: datetime | None) -> list[dict[str, Any]]:
    if cutoff is None:
        return entries
    return [item for item in entries if (_parse_time(item["time"]) or cutoff) >= cutoff]


def list_entries(
    *,
    since: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the newest ``limit`` entries, optionally filtered by window and kind."""
    target = path or feedback_path()
    cutoff = parse_since(since, now=now) if since else None
    try:
        entries, skipped = read_entries(target)
    except OSError as exc:
        return _storage_error("feedback_read_failed", "read", exc, target)
    selected = _since_filter(entries, cutoff)
    if kind:
        selected = [item for item in selected if item.get("kind") == kind]
    total = len(selected)
    if limit > 0:
        selected = selected[-limit:]
    return {
        "ok": True,
        "path": display_path(target),
        "since": _iso(cutoff) if cutoff else None,
        "total": total,
        "shown": len(selected),
        "skipped_lines": skipped,
        "entries": selected,
        "safe_to_share": True,
    }


def rollup(
    *,
    since: str = DEFAULT_SINCE,
    path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Group entries in the window by kind, command and rule, with counts."""
    target = path or feedback_path()
    cutoff = parse_since(since, now=now)
    try:
        entries, skipped = read_entries(target)
    except OSError as exc:
        return _storage_error("feedback_read_failed", "read", exc, target)
    selected = _since_filter(entries, cutoff)
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in selected:
        kind = str(item.get("kind") or "feedback")
        command = str(item.get("command") or "")
        rule = str(item.get("rule") or "")
        key = (kind, command, rule)
        group = groups.setdefault(
            key,
            {
                "kind": kind,
                "command": command or None,
                "rule": rule or None,
                "count": 0,
                "oldest": item["time"],
                "newest": item["time"],
                "repo_kinds": [],
                "mb_versions": [],
                "texts": [],
            },
        )
        group["count"] += 1
        group["oldest"] = min(group["oldest"], item["time"])
        group["newest"] = max(group["newest"], item["time"])
        for field, value in (
            ("repo_kinds", item.get("repo_kind")),
            ("mb_versions", item.get("mb_version")),
        ):
            if value and value not in group[field]:
                group[field].append(value)
        text = item.get("text")
        if text:
            group["texts"].append(text)
    ordered = sorted(
        groups.values(),
        key=lambda group: (
            group["kind"] != "refusal",
            -group["count"],
            group["command"] or "",
            group["rule"] or "",
        ),
    )
    result = {
        "ok": True,
        "path": display_path(target),
        "since": _iso(cutoff),
        "window": since,
        "total": len(selected),
        "skipped_lines": skipped,
        "groups": ordered,
        "safe_to_share": True,
    }
    result["markdown"] = render_rollup_markdown(result)
    return result


def render_rollup_markdown(result: dict[str, Any]) -> str:
    """Render a rollup as a Markdown draft a maintainer can turn into issues."""
    lines = [
        "# mb feedback rollup",
        "",
        f"Window: since {result['since']} ({result['window']}). "
        f"Entries: {result['total']}. Local file: `{result['path']}`. Nothing was sent.",
    ]
    if result.get("skipped_lines"):
        lines.append(f"Unreadable lines skipped: {result['skipped_lines']}.")
    refusals = [group for group in result["groups"] if group["kind"] == "refusal"]
    notes = [group for group in result["groups"] if group["kind"] != "refusal"]
    if not result["groups"]:
        lines += ["", "No feedback or refusals in this window."]
        return "\n".join(lines) + "\n"
    if refusals:
        lines += [
            "",
            "## Refusals",
            "",
            "| Rule | Command | Count | Oldest | Newest |",
            "| --- | --- | ---: | --- | --- |",
        ]
        for group in refusals:
            lines.append(
                f"| `{group['rule'] or 'unknown'}` | `{group['command'] or '-'}` | "
                f"{group['count']} | {group['oldest']} | {group['newest']} |"
            )
    if notes:
        lines += ["", "## Feedback"]
        for group in notes:
            command = f"`{group['command']}`" if group["command"] else "No command given"
            lines += [
                "",
                f"### {command}: {group['count']} {'entry' if group['count'] == 1 else 'entries'}",
                "",
                f"Oldest {group['oldest']}, newest {group['newest']}. "
                f"Repo kinds: {', '.join(group['repo_kinds']) or 'unknown'}. "
                f"mb versions: {', '.join(group['mb_versions']) or 'unknown'}.",
                "",
            ]
            lines += [f"- {' '.join(text.split())}" for text in group["texts"]]
    return "\n".join(lines) + "\n"


def clear(*, before: str, path: Path | None = None) -> dict[str, Any]:
    """Drop entries older than ``before`` (a date or timestamp) and unreadable lines."""
    target = path or feedback_path()
    cutoff = _parse_date(before)
    if not target.exists():
        return {
            "ok": True,
            "path": display_path(target),
            "before": _iso(cutoff),
            "removed": 0,
            "kept": 0,
            "safe_to_share": True,
        }
    try:
        with state_lock(target):
            entries, skipped = read_entries(target)
            kept = [item for item in entries if (_parse_time(item["time"]) or cutoff) >= cutoff]
            removed = len(entries) - len(kept)
            text = "".join(
                json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in kept
            )
            atomic_write_text(target, text)
    except OSError as exc:
        return _storage_error("feedback_clear_failed", "rewrite", exc, target)
    return {
        "ok": True,
        "path": display_path(target),
        "before": _iso(cutoff),
        "removed": removed,
        "removed_unreadable": skipped,
        "kept": len(kept),
        "safe_to_share": True,
    }


def render_record(result: dict[str, Any]) -> None:
    print(f"Saved to {result['path']} (local only; nothing was sent).")
    print("Run `mb feedback rollup` to see this week's friction grouped by command.")


def render_list(result: dict[str, Any]) -> None:
    if not result["entries"]:
        print(f"No feedback in {result['path']}.")
        return
    for item in result["entries"]:
        kind = item.get("kind", "feedback")
        command = item.get("command") or "-"
        if kind == "refusal":
            print(f"{item['time']}  refusal  {command}  rule={item.get('rule') or 'unknown'}")
        else:
            print(f"{item['time']}  feedback  {command}  {item.get('text', '')}")
    if result["shown"] < result["total"]:
        print(f"Showing the newest {result['shown']} of {result['total']}; use --limit 0 for all.")


def render_clear(result: dict[str, Any]) -> None:
    print(
        f"Removed {result['removed']} entries before {result['before']}; "
        f"kept {result['kept']} in {result['path']}."
    )
