"""Agent role cards: one committed file per agent, selected by name at launch.

A card lives at ``core/roles/<name>.md`` in the business repo. Everything here
is read-only. The role is never guessed: the caller names it (``MB_ROLE`` for
the SessionStart hook, an argument for ``mb role show``/``check``).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

import yaml

ROLES_DIR = "core/roles"
ROLE_ENV = "MB_ROLE"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
# The card schema. A test pins this tuple: change it on purpose, not by accident.
REQUIRED_FIELDS: tuple[str, ...] = (
    "name",
    "role",
    "skills",
    "tools",
    "protocols",
    "first_action",
    "checkpoint",
)
LIST_FIELDS = ("skills", "tools", "protocols")
HOOK_SOURCES = ("startup", "resume", "clear", "compact")
MAX_CARD_BYTES = 65_536
MAX_CHECKPOINT_BYTES = 8_192
_CONTROL_RE = re.compile("[\\x00-\\x1f\\x7f-\\x9f\\u2028\\u2029]")
_NOT_TEXT_RE = re.compile("[\\x00-\\x08\\x0b-\\x1f\\x7f-\\x9f\\u2028\\u2029]")
CHECKPOINT_DIRS = ("state", "core/roles")
CHECKPOINT_RULE = (
    "checkpoint must be a regular .md file under state/ or core/roles/, with no hidden "
    "path segment, and not git-ignored unless under state/"
)
_MARKER_RE = re.compile(r"-{3}\s*(end\s+)?checkpoint(\s+contents)?\s*-{3}", re.IGNORECASE)


def strip_format(value: str) -> str:
    """Drop Unicode format controls (bidi overrides, zero-width, BOM) and line/paragraph breaks."""
    return "".join(ch for ch in value if unicodedata.category(ch) not in ("Cf", "Zl", "Zp"))


def emit(value: str) -> str:
    """Make a field or checkpoint text safe to put in model context.

    Format controls go first so they cannot split a marker; section markers
    inside the text are neutralized so it cannot forge the end of a section.
    """
    return _MARKER_RE.sub("[marker removed]", strip_format(value))


def has_control(value: str, *, multiline: bool = False) -> bool:
    """True when ``value`` has control characters; newline and tab pass if ``multiline``."""
    return bool((_NOT_TEXT_RE if multiline else _CONTROL_RE).search(value))


def printable(value: str, limit: int = 60) -> str:
    """Make untrusted text safe to echo: no control characters, bounded length."""
    cleaned = _CONTROL_RE.sub("?", strip_format(value).replace("\n", "?").replace("\r", "?"))
    return cleaned if len(cleaned) <= limit else cleaned[:limit] + "..."


def valid_name(name: object) -> bool:
    return isinstance(name, str) and NAME_RE.fullmatch(name) is not None


def _root(repo: str | Path) -> Path:
    return Path(repo).expanduser().resolve()


def card_paths(repo: str | Path) -> list[Path]:
    """Every ``*.md`` directly inside ``core/roles/``; empty when the folder is absent."""
    folder = _root(repo) / ROLES_DIR
    try:
        return sorted(
            p for p in folder.iterdir() if p.suffix == ".md" and not p.name.startswith(".")
        )
    except OSError:
        return []


def has_cards(repo: str | Path) -> bool:
    return bool(card_paths(repo))


def _safe_relative(value: str) -> bool:
    if not value or has_control(value) or value.startswith(("/", "~", "\\")):
        return False
    if re.match(r"^[A-Za-z]:", value):
        return False
    return ".." not in Path(value.replace("\\", "/")).parts


def _git_ignored(root: Path, relative: str) -> bool:
    """True if git ignores the path. Fails closed: an unanswered question counts as ignored."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-q", "--", relative],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    return result.returncode != 1


def checkpoint_problem(root: Path, relative: str) -> str | None:
    """Why a checkpoint may not be read automatically, or None when it may.

    The rule applies to the written path and to where it really points, so a
    link from an allowed name to ``.env`` fails.
    """
    if not _safe_relative(relative):
        return "checkpoint must be a relative path inside the repo"
    try:
        resolved = (root / relative).resolve().relative_to(root)
    except (OSError, ValueError):
        return "checkpoint must be a relative path inside the repo"
    for rel in (Path(relative.replace("\\", "/")), resolved):
        parts = rel.parts
        top = "core/roles" if parts[:2] == ("core", "roles") else (parts[:1] or ("",))[0]
        if (
            rel.suffix != ".md"
            or top not in CHECKPOINT_DIRS
            or len(parts) <= len(top.split("/"))
            or any(part.startswith(".") for part in parts)
        ):
            return CHECKPOINT_RULE
        if top != "state" and _git_ignored(root, rel.as_posix()):
            return CHECKPOINT_RULE
    return None


def _read_card(path: Path, root: Path) -> tuple[dict[str, Any] | None, str, list[str]]:
    """Return ``(frontmatter, body, errors)``. Never raises on bad content."""
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None, "", ["card resolves outside the repo"]
    try:
        if not resolved.is_file():
            return None, "", ["card is not a regular file"]
        if resolved.stat().st_size > MAX_CARD_BYTES:
            return None, "", [f"card is larger than {MAX_CARD_BYTES} bytes"]
        with resolved.open("rb") as handle:
            raw = handle.read(MAX_CARD_BYTES + 1)
        if len(raw) > MAX_CARD_BYTES:
            return None, "", [f"card is larger than {MAX_CARD_BYTES} bytes"]
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None, "", ["card could not be read as UTF-8 text"]
    if not text.startswith("---\n"):
        return None, text, ["card has no frontmatter"]
    end = text.find("\n---", 4)
    if end == -1:
        return None, text, ["card frontmatter is not closed"]
    try:
        parsed = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return None, text, ["card frontmatter is not valid YAML"]
    if not isinstance(parsed, dict):
        return None, text, ["card frontmatter must be a mapping"]
    return parsed, text[end + 4 :].lstrip("\n"), []


def _validate(fm: dict[str, Any], stem: str, root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in fm:
            errors.append(f"missing field: {field}")
    for field in REQUIRED_FIELDS:
        if field not in fm:
            continue
        value = fm[field]
        if field in LIST_FIELDS:
            if not isinstance(value, list) or not all(
                isinstance(v, str) and v.strip() and not has_control(v) for v in value
            ):
                errors.append(f"{field} must be a list of plain text items")
        elif not isinstance(value, str) or not value.strip():
            errors.append(f"{field} must be non-empty text")
        elif has_control(value, multiline=field == "first_action"):
            errors.append(f"{field} must not contain control characters")
    name = fm.get("name")
    if isinstance(name, str):
        if not valid_name(name):
            errors.append("name must be lowercase letters, digits, and hyphens (max 40)")
        elif name != stem:
            errors.append("name must match the file name")
    role = fm.get("role")
    if isinstance(role, str) and len(role) > 200:
        errors.append("role must be at most 200 characters")
    checkpoint = fm.get("checkpoint")
    if isinstance(checkpoint, str) and checkpoint.strip():
        problem = checkpoint_problem(root, checkpoint)
        if problem:
            errors.append(problem)
    for extra in sorted(set(fm) - set(REQUIRED_FIELDS), key=str):
        warnings.append(f"unknown field ignored: {printable(str(extra), 40)}")
    return errors, warnings


def load_card(repo: str | Path, name: str) -> dict[str, Any]:
    """Load one card by exact name. The name is checked before any path is built."""
    if not valid_name(name):
        return {
            "name": printable(str(name)),
            "valid": False,
            "found": False,
            "errors": ["role name must be lowercase letters, digits, and hyphens (max 40)"],
            "warnings": [],
        }
    root = _root(repo)
    path = root / ROLES_DIR / f"{name}.md"
    if not path.exists() and not path.is_symlink():
        return {
            "name": name,
            "valid": False,
            "found": False,
            "errors": [f"no role card at {ROLES_DIR}/{name}.md"],
            "warnings": [],
        }
    fm, body, errors = _read_card(path, root)
    warnings: list[str] = []
    if fm is not None:
        errors, warnings = _validate(fm, name, root)
    card: dict[str, Any] = {
        "name": name,
        "path": f"{ROLES_DIR}/{name}.md",
        "found": True,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }
    if not errors and fm is not None:
        card.update({field: fm[field] for field in REQUIRED_FIELDS})
        card["body"] = body
    return card


def list_cards(repo: str | Path) -> list[dict[str, Any]]:
    cards = []
    for path in card_paths(repo):
        card = load_card(repo, path.stem)
        cards.append(
            {
                "name": card["name"],
                "path": f"{ROLES_DIR}/{path.name}",
                "valid": card["valid"],
                "role": card.get("role"),
                "errors": card["errors"],
            }
        )
    return cards


def check(repo: str | Path, name: str | None = None) -> dict[str, Any]:
    """Validate every card, or one named card. ``ok`` is false on any invalid card."""
    if name is not None:
        card = load_card(repo, name)
        results = [{k: card[k] for k in ("name", "valid", "errors", "warnings")}]
    else:
        results = []
        for path in card_paths(repo):
            card = load_card(repo, path.stem)
            results.append({k: card[k] for k in ("name", "valid", "errors", "warnings")})
    errors = [f"{r['name']}: {e}" for r in results for e in r["errors"]]
    return {
        "ok": all(r["valid"] for r in results),
        "cards": results,
        "errors": errors,
        "warnings": [f"{r['name']}: {w}" for r in results for w in r["warnings"]],
    }


def _checkpoint_text(repo: Path, relative: str) -> str:
    if checkpoint_problem(repo, relative):
        return f"(Checkpoint {printable(relative)} was not read: {CHECKPOINT_RULE}.)"
    path = repo / relative
    try:
        resolved = path.resolve()
        resolved.relative_to(repo)
        if not resolved.is_file():
            raise OSError
        with resolved.open("rb") as handle:
            raw = handle.read(MAX_CHECKPOINT_BYTES + 1)
    except (OSError, ValueError):
        return f"(No checkpoint file at {relative} yet. State this and ask what to do next.)"
    text = raw[:MAX_CHECKPOINT_BYTES].decode("utf-8", errors="replace")
    cleaned = emit("".join(ch for ch in text if ch in "\n\t" or not _CONTROL_RE.match(ch)))
    if len(raw) > MAX_CHECKPOINT_BYTES:
        cleaned += "\n(checkpoint truncated)"
    return cleaned


def refusal(reason: str) -> str:
    """Loud, plain text for a session that has no usable role."""
    return (
        "!!! MAIN BRANCH ROLE CHECK FAILED !!!\n"
        f"{reason}\n"
        "STOP. Do not start work and do not pick a role yourself. "
        "Tell the owner exactly this message and ask which role to run as. "
        f"(Launch with {ROLE_ENV}=<role-name>; see `mb role list`.)\n"
        "!!! END ROLE CHECK !!!"
    )


def hook_text(repo: str | Path, source: str, env: dict[str, str] | None = None) -> str:
    """Text the SessionStart hook prints. Empty string means print nothing.

    No cards in the repo means nothing changes for that business, so the hook
    is silent there. With cards, the role must be named explicitly.
    """
    if not has_cards(repo):
        return ""
    selected = (env if env is not None else os.environ).get(ROLE_ENV, "")
    if not selected.strip():
        names = ", ".join(c["name"] for c in list_cards(repo))
        return refusal(f"No role was selected ({ROLE_ENV} is not set). Role cards here: {names}.")
    if not valid_name(selected):
        return refusal(f"The selected role name {printable(selected)!r} is not a valid role name.")
    card = load_card(repo, selected)
    if not card["found"]:
        return refusal(f"Selected role {selected!r} has no card at {ROLES_DIR}/{selected}.md.")
    if not card["valid"]:
        return refusal(
            f"Role card {selected!r} is invalid: "
            + "; ".join(printable(e, 120) for e in card["errors"])
        )
    root = _root(repo)
    lines = [
        f"MAIN BRANCH ROLE CARD (session {source}). You are running as role: {card['name']}.",
        "State this role in your first reply. Do not take another role.",
        f"Role: {emit(card['role'])}",
        "Skills: " + (emit(", ".join(card["skills"])) or "none"),
        "Tools: " + (emit(", ".join(card["tools"])) or "none"),
        "Protocols: " + (emit(", ".join(card["protocols"])) or "none"),
        f"First action: {emit(card['first_action'].strip())}",
        f"Checkpoint file: {emit(card['checkpoint'])}",
        "--- checkpoint contents ---",
        _checkpoint_text(root, card["checkpoint"]).rstrip(),
        "--- end checkpoint ---",
    ]
    return "\n".join(lines)


def _command_runs_role_hook(command: object) -> bool:
    """True only when the command starts with ``mb role hook``.

    Parsing arbitrary shell is a losing game, so any other form reads as not wired.
    That can miss a real hook. It can't report one that doesn't run.
    """
    if not isinstance(command, str):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    return (
        len(tokens) >= 3
        and Path(tokens[0]).name == "mb"
        and tokens[1:3] == ["role", "hook"]
        and not command.lstrip().startswith(("'", '"'))
    )


def _settings_has_hook(path: Path) -> bool:
    """True when the settings JSON has a SessionStart hook whose command runs ``mb role hook``."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    hooks_by_event = doc.get("hooks") if isinstance(doc, dict) else None
    groups = hooks_by_event.get("SessionStart") if isinstance(hooks_by_event, dict) else None
    if not isinstance(groups, list):
        return False
    for group in groups:
        hooks = group.get("hooks") if isinstance(group, dict) else None
        for hook in hooks if isinstance(hooks, list) else []:
            if isinstance(hook, dict) and _command_runs_role_hook(hook.get("command")):
                return True
    return False


def wiring(repo: str | Path, plugin_wired: bool) -> dict[str, Any]:
    """Facts for ``mb doctor``. Only meaningful when the repo has role cards.

    ``hook_wired`` means a real hook command was found in project settings. An
    enabled plugin is reported separately: its version is not visible here.
    """
    root = _root(repo)
    cards = list_cards(root)
    project_hook = any(
        _settings_has_hook(root / ".claude" / name)
        for name in ("settings.json", "settings.local.json")
    )
    return {
        "cards": len(cards),
        "invalid": [c["name"] for c in cards if not c["valid"]],
        "hook_wired": project_hook,
        "plugin_wired": plugin_wired,
        "project_hook": project_hook,
        "role_selected": bool(os.environ.get(ROLE_ENV, "").strip()),
    }
