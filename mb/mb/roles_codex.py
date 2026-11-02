"""Codex wiring for role cards: one user-level SessionStart hook, installed by the owner.

The card and ``mb role hook`` are shared with Claude Code. Codex only needs a thin
trigger in ``$CODEX_HOME/hooks.json`` (default ``~/.codex``). Everything here is a
plan unless the caller applies it. It never edits trust state or ``config.toml``.
"""

from __future__ import annotations

import copy
import difflib
import json
import os
from pathlib import Path
from typing import Any

from mb.codex import _symlinked_ancestor
from mb.durable import atomic_write_text

CODEX_HOME_ENV = "CODEX_HOME"
HOOKS_FILE = "hooks.json"
# Codex runs this for every source it can start a session from.
CODEX_MATCHER = "startup|resume|clear|compact|fork"
# A role card plus its 8 KB checkpoint is near Codex's default 2,500-token cap.
CONTEXT_LIMIT = 4000
HOOK_TIMEOUT_SECONDS = 20
_MARK = "mb role hook --runtime codex"

# POSIX sh, wrapped so a zsh or fish login shell cannot abort it. It walks up from the
# session folder to a git root looking for core/roles, so a session with no cards
# never starts Python. If mb cannot run it prints a plain refusal, but only when a
# card file exists. It always exits 0.
_REFUSAL = (
    "MAIN BRANCH ROLE CHECK FAILED: this repo has role cards (core/roles) but the role "
    "could not be loaded. STOP. Do not start work and do not pick a role yourself. "
    "Tell the owner this message and ask them to fix the role setup. This session has no role."
)
CODEX_HOOK_COMMAND = (
    "sh -c '"
    'd=$PWD; while :; do [ -d "$d/core/roles" ] && break; '
    '{ [ -e "$d/.git" ] || [ "$d" = / ]; } && exit 0; p=${d%/*}; d=${p:-/}; done; '
    f"if command -v mb >/dev/null 2>&1 && out=$({_MARK} 2>/dev/null); "
    'then [ -z "$out" ] || printf "%s\\n" "$out"; '
    'else set -- "$d"/core/roles/*.md; '
    f'if [ -e "$1" ] || [ -L "$1" ]; then printf "%s\\n" "{_REFUSAL}"; fi; fi; exit 0\''
)


def codex_home() -> Path:
    override = os.environ.get(CODEX_HOME_ENV, "").strip()
    return Path(override).expanduser() if override else Path.home() / ".codex"


def hooks_path() -> Path:
    return codex_home() / HOOKS_FILE


def hook_group() -> dict[str, Any]:
    return {
        "matcher": CODEX_MATCHER,
        "hooks": [
            {
                "type": "command",
                "command": CODEX_HOOK_COMMAND,
                "timeout": HOOK_TIMEOUT_SECONDS,
                "additionalContextLimit": CONTEXT_LIMIT,
            }
        ],
    }


def _is_ours(hook: object) -> bool:
    command = hook.get("command") if isinstance(hook, dict) else None
    return isinstance(command, str) and _MARK in command


def _current(hook: object) -> bool:
    return isinstance(hook, dict) and hook == hook_group()["hooks"][0]


def _session_groups(doc: Any) -> tuple[list[Any] | None, str | None]:
    """The SessionStart group list, [] when absent, or a reason the file is not safe to merge."""
    if not isinstance(doc, dict):
        return None, "hooks.json must be a JSON object"
    hooks = doc.get("hooks")
    if hooks is None:
        return [], None
    if not isinstance(hooks, dict):
        return None, '"hooks" must be an object'
    groups = hooks.get("SessionStart")
    if groups is None:
        return [], None
    if not isinstance(groups, list):
        return None, '"hooks.SessionStart" must be a list'
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks", []), list):
            return None, "a SessionStart entry is not a hook group"
    return groups, None


def _read(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """The parsed file ({} when absent), or None plus the reason it must not be touched."""
    home = codex_home()
    if not home.is_dir():
        return None, f"no Codex home at {home}; run Codex once or set {CODEX_HOME_ENV}"
    if path.is_symlink() or _symlinked_ancestor(home, path) is not None:
        return None, f"{path} is a link; a link leads somewhere you chose, so it is left alone"
    if not path.exists():
        return {}, None
    if not path.is_file():
        return None, f"{path} is not a regular file"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None, f"{path} is not valid JSON; fix or move it, nothing was changed"
    _, problem = _session_groups(doc)
    return (None, f"{path}: {problem}; nothing was changed") if problem else (doc, None)


def _prune(doc: dict[str, Any]) -> None:
    hooks = doc.get("hooks")
    if isinstance(hooks, dict):
        if hooks.get("SessionStart") == []:
            del hooks["SessionStart"]
        if not hooks:
            del doc["hooks"]


def _merged(doc: dict[str, Any], *, remove: bool) -> dict[str, Any]:
    out = copy.deepcopy(doc)
    hooks = out.setdefault("hooks", {})
    groups = hooks.setdefault("SessionStart", [])
    kept: list[Any] = []
    for group in groups:
        inner = group.get("hooks", [])
        theirs = [h for h in inner if not _is_ours(h)]
        if len(theirs) == len(inner):
            kept.append(group)
        elif theirs:
            kept.append({**group, "hooks": theirs})
    if not remove:
        kept.append(hook_group())
    hooks["SessionStart"] = kept
    _prune(out)
    return out


def _render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def plan(*, remove: bool = False) -> dict[str, Any]:
    """What install (or uninstall) would do. Nothing is written."""
    path = hooks_path()
    doc, problem = _read(path)
    report: dict[str, Any] = {
        "path": str(path),
        "remove": remove,
        "action": "refused",
        "problem": problem,
        "diff": "",
        "after": None,
    }
    if doc is None:
        return report
    groups, _ = _session_groups(doc)
    ours = [h for g in groups or [] for h in g.get("hooks", []) if _is_ours(h)]
    installed = any(_current(h) for h in ours) and any(
        g.get("matcher") == CODEX_MATCHER and any(_current(h) for h in g.get("hooks", []))
        for g in groups or []
    )
    if remove and not ours:
        report["action"] = "unchanged"
        return report
    if not remove and installed and len(ours) == 1:
        report["action"] = "unchanged"
        return report
    after = _merged(doc, remove=remove)
    before = _render(doc) if path.exists() else ""
    text = _render(after) if after else ""
    report["action"] = "remove" if remove else ("replace" if ours else "add")
    report["after"] = after
    report["diff"] = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            text.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        )
    )
    return report


def apply(*, remove: bool = False) -> dict[str, Any]:
    """Write the planned change atomically. Refused or unchanged plans write nothing."""
    report = plan(remove=remove)
    if report["action"] in {"refused", "unchanged"}:
        return {**report, "written": False}
    path = Path(report["path"])
    after = report["after"]
    if not after:
        path.unlink()
    else:
        atomic_write_text(path, _render(after), mode=0o644 if not path.exists() else None)
    return {**report, "written": True}


def wiring() -> dict[str, Any]:
    """Facts for ``mb doctor``. ``wired`` needs the exact hook we generate in user hooks.json.

    Trust is never read: Codex keeps a hash of each hook and skips new or changed
    ones until the owner reviews them in ``/hooks``. Doctor cannot see that.
    """
    path = hooks_path()
    doc, problem = _read(path)
    groups, _ = _session_groups(doc) if doc is not None else (None, None)
    wired = any(
        g.get("matcher") == CODEX_MATCHER and any(_current(h) for h in g.get("hooks", []))
        for g in groups or []
    )
    return {
        "path": str(path),
        "wired": wired,
        "readable": doc is not None,
        "problem": problem,
        "trust": "not verified",
    }
