"""Public-safe team member facts for business repos."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from mb import usage

TEAM_SCHEMA_VERSION = "1.0"
TEAM_DIR = Path("core") / "team"
RELATIONSHIPS = {"owner", "member", "contractor", "advisor", "external_collaborator"}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
GITHUB_HANDLE_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?$")


def normalize_github_handle(value: Any) -> str:
    """Return a canonical GitHub handle, without leading @, or empty on invalid input."""
    if not isinstance(value, str):
        return ""
    raw = value.strip()
    if not raw:
        return ""
    if raw.startswith("https://github.com/"):
        raw = raw.removeprefix("https://github.com/").split("/", maxsplit=1)[0]
    if raw.startswith("http://github.com/"):
        raw = raw.removeprefix("http://github.com/").split("/", maxsplit=1)[0]
    normalized = raw.removeprefix("@").strip().lower()
    return normalized if GITHUB_HANDLE_RE.fullmatch(normalized) else ""


def display_name(member: dict[str, Any]) -> str:
    preferred = str(member.get("preferred_name") or "").strip()
    if preferred:
        return preferred
    name = str(member.get("name") or "").strip()
    if name:
        return name
    return str(member.get("slug") or "").strip()


def _read_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    try:
        text = usage.read_bounded(path, usage.ROLE_LIMIT).decode("utf-8")
    except (OSError, UnicodeError, usage.Refused) as exc:
        return {}, f"unreadable: {exc}"
    if not text.startswith("---"):
        return {}, "no frontmatter"
    try:
        end = text.index("\n---", 3)
    except ValueError:
        return {}, "unterminated frontmatter"
    raw = text[3:end].lstrip("\n")
    try:
        parsed = yaml.safe_load(raw) or {}
    except (yaml.YAMLError, RecursionError) as exc:
        return {}, f"yaml error: {exc}"
    if not isinstance(parsed, dict):
        return {}, "frontmatter not a mapping"
    return parsed, ""


def _github_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _member_from_file(repo: Path, path: Path) -> dict[str, Any]:
    frontmatter, error = _read_frontmatter(path)
    rel = path.relative_to(repo).as_posix()
    slug = path.stem
    handles = [
        normalize_github_handle(value) for value in _github_values(frontmatter.get("github"))
    ]
    handles = [handle for handle in handles if handle]
    member = {
        "slug": slug,
        "path": rel,
        "name": str(frontmatter.get("name") or "").strip(),
        "preferred_name": str(frontmatter.get("preferred_name") or "").strip(),
        "display_name": "",
        "role": str(frontmatter.get("role") or "").strip(),
        "relationship": str(frontmatter.get("relationship") or "").strip(),
        "github": handles,
        "areas": [item for item in frontmatter.get("areas", []) if isinstance(item, str)]
        if isinstance(frontmatter.get("areas"), list)
        else [],
        "external": frontmatter.get("relationship") == "external_collaborator",
        "ok": not error,
        "error": error,
    }
    member["display_name"] = display_name(member)
    return member


def facts(repo: str | Path = ".") -> dict[str, Any]:
    target = Path(repo).resolve()
    team_root = target / TEAM_DIR
    members: list[dict[str, Any]] = []
    if team_root.exists():
        for path in sorted(team_root.glob("*.md")):
            if path.name == "README.md":
                continue
            members.append(_member_from_file(target, path))

    known_handles: dict[str, dict[str, str]] = {}
    duplicate_handles: dict[str, list[str]] = {}
    for member in members:
        for handle in member.get("github", []):
            if handle in known_handles:
                duplicate_handles.setdefault(handle, [known_handles[handle]["path"]]).append(
                    str(member["path"])
                )
                continue
            known_handles[handle] = {
                "slug": str(member["slug"]),
                "path": str(member["path"]),
                "display_name": str(member["display_name"]),
                "relationship": str(member["relationship"]),
            }

    owner_count = sum(1 for member in members if member.get("relationship") == "owner")
    return {
        "schema_version": TEAM_SCHEMA_VERSION,
        "ok": all(bool(member.get("ok")) for member in members) and not duplicate_handles,
        "path": TEAM_DIR.as_posix(),
        "members": members,
        "github": {
            "known_handles": known_handles,
            "duplicate_handles": duplicate_handles,
            "unknown_contributor_guidance": (
                "Keep unknown GitHub handles as handles and add core/team/<slug>.md "
                "when the contributor is part of the business context."
            ),
        },
        "summary": {
            "members": len(members),
            "owners": owner_count,
            "external_collaborators": sum(
                1 for member in members if member.get("relationship") == "external_collaborator"
            ),
            "github_handles": len(known_handles),
        },
        "safe_to_share": True,
    }


def resolve_github_handle(handle: str, team_facts: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_github_handle(handle)
    if not normalized:
        return {
            "handle": handle,
            "known": False,
            "display_name": "",
            "slug": "",
            "path": "",
            "label": f"unknown contributor ({handle})" if handle else "unknown contributor",
        }
    known = (
        ((team_facts or {}).get("github") or {}).get("known_handles") or {}
        if isinstance(team_facts, dict)
        else {}
    )
    member = known.get(normalized)
    if isinstance(member, dict):
        display = str(member.get("display_name") or normalized)
        return {
            "handle": normalized,
            "known": True,
            "display_name": display,
            "slug": str(member.get("slug") or ""),
            "path": str(member.get("path") or ""),
            "label": display,
        }
    return {
        "handle": normalized,
        "known": False,
        "display_name": "",
        "slug": "",
        "path": "",
        "label": f"unknown contributor (@{normalized})",
    }
