"""Privacy-safe business repo migration drift lint.

The lint surface warns about old active-looking repo shapes without reading or
printing private file bodies. It is intentionally advisory: compatibility paths
remain readable, while current agents get deterministic guidance about where
new work belongs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from mb import engine as engine_mod
from mb import pushes as pushes_mod

STALE_TOP_LEVEL_FOLDERS = {
    "ops": "Use `core/operations/` for durable operations context.",
    "skills": (
        "Use packaged `.claude/skills/mb-*` wiring; do not treat top-level `skills/` "
        "as part of the current business record."
    ),
    "briefs": (
        "Use `research/`, `decisions/`, `pushes/`, `log/`, or `documents/` based on the artifact."
    ),
    "content": (
        "Use `pushes/`, `documents/`, or channel-specific push/playbook records "
        "for shipped content."
    ),
    "staging": (
        "Use `pushes/<YYYY-MM-DD-slug>/` for coordinated work and `.mb/` or OS "
        "temp for local scratch."
    ),
    "outputs": (
        "`outputs/` is legacy generated-work language. Move historical content to "
        "`documents/archive/<name>/` or classify it by hand; do not bulk-promote old "
        "generated work into `pushes/` or legacy `campaigns/`."
    ),
}

STALE_CLAUDE_PATTERNS = (
    (
        "stale-claude-reference-guidance",
        "reference/",
        re.compile(r"(?im)^\s*[-*]\s*`?reference/`?\s+(?:-|--|\u2014)"),
        "`reference/` is legacy compatibility. New durable business truth belongs in `core/`.",
    ),
    (
        "stale-claude-reference-core-guidance",
        "reference/core",
        re.compile(
            r"(?i)(?:write|add|create|new work|new truth)[^\n.]{0,80}reference/(?:core|offers)"
        ),
        (
            "`reference/core` and `reference/offers` are compatibility paths. "
            "New writes belong in `core/` and `core/offers/`."
        ),
    ),
    (
        "stale-claude-campaigns-guidance",
        "campaigns/",
        re.compile(r"(?im)^\s*[-*]\s*`?campaigns/`?\s+(?:-|--|\u2014)"),
        "`campaigns/` is compatibility read. New coordinated work belongs in `pushes/`.",
    ),
    (
        "stale-claude-campaign-write-guidance",
        "campaigns/",
        re.compile(r"(?i)(?:write|add|create|new work|new coordinated work)[^\n.]{0,80}campaigns/"),
        "`campaigns/` is compatibility read. New coordinated work belongs in `pushes/`.",
    ),
)


def _finding(
    *,
    code: str,
    path: str,
    category: str,
    message: str,
    repair_command: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "path": path,
        "category": category,
        "message": message,
        "repair_command": repair_command,
        "safe_to_share": True,
        "content_included": False,
    }


def _has_non_ignored_content(path: Path) -> bool:
    if path.is_symlink():
        return False
    if path.is_file():
        return path.name not in {".gitkeep", ".DS_Store"}
    if not path.is_dir():
        return False
    for child in path.rglob("*"):
        if (
            child.is_file()
            and not child.is_symlink()
            and child.name not in {".gitkeep", ".DS_Store"}
        ):
            return True
    return False


def _read_frontmatter(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    try:
        end = text.index("\n---", 3)
    except ValueError:
        return {}
    try:
        parsed = yaml.safe_load(text[3:end].lstrip("\n")) or {}
    except yaml.YAMLError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _cached_frontmatter(path: Path, cache: dict[Path, dict[str, Any]]) -> dict[str, Any]:
    if path not in cache:
        cache[path] = _read_frontmatter(path)
    return cache[path]


def _iter_markdown_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(path for path in root.rglob("*.md") if path.is_file() and not path.is_symlink())


def _lint_reference(repo: Path, findings: list[dict[str, Any]]) -> None:
    reference = repo / "reference"
    if not reference.exists() or reference.is_symlink():
        return
    for rel in ("reference/core", "reference/offers"):
        path = repo / rel
        if path.exists() and not path.is_symlink() and _has_non_ignored_content(path):
            findings.append(
                _finding(
                    code="legacy-reference-active-content",
                    path=rel,
                    category="legacy-folder",
                    message=(
                        f"{rel} contains real files. Main Branch can read legacy `reference/`, "
                        "but new durable business truth belongs in `core/`."
                    ),
                    repair_command="mb migrate --check",
                )
            )
    other_files = [
        child.relative_to(repo).as_posix()
        for child in reference.rglob("*")
        if child.is_file()
        and not child.is_symlink()
        and child.name not in {".gitkeep", ".DS_Store"}
        and not child.relative_to(repo)
        .as_posix()
        .startswith(("reference/core/", "reference/offers/"))
    ]
    if other_files:
        findings.append(
            _finding(
                code="legacy-reference-extra-content",
                path="reference/",
                category="legacy-folder",
                message=(
                    f"reference/ contains {len(other_files)} file(s) outside compatibility links. "
                    "Classify them before writing new work; current homes are usually `core/`, "
                    "`research/`, `decisions/`, `pushes/`, `log/`, or `documents/`."
                ),
                repair_command="mb doctor repair --plan --json",
            )
        )


def _lint_campaigns(repo: Path, findings: list[dict[str, Any]]) -> None:
    campaigns = repo / "campaigns"
    if campaigns.is_dir() and _has_non_ignored_content(campaigns):
        findings.append(
            _finding(
                code="legacy-campaigns-active-content",
                path="campaigns/",
                category="legacy-folder",
                message=(
                    "`campaigns/` contains legacy content. It remains readable for "
                    "compatibility; new coordinated work belongs in `pushes/`."
                ),
                repair_command="mb migrate campaigns --plan",
            )
        )


def _lint_top_level_folders(repo: Path, findings: list[dict[str, Any]]) -> None:
    for name, destination in STALE_TOP_LEVEL_FOLDERS.items():
        path = repo / name
        if path.is_dir() and _has_non_ignored_content(path):
            findings.append(
                _finding(
                    code=f"legacy-top-level-{name}",
                    path=f"{name}/",
                    category="legacy-folder",
                    message=(
                        f"Top-level `{name}/` looks like an old active-write folder. {destination}"
                    ),
                    repair_command="mb doctor repair --plan --json",
                )
            )


def _lint_vip(repo: Path, findings: list[dict[str, Any]]) -> None:
    vip = repo / ".vip"
    if not vip.is_dir() or not _has_non_ignored_content(vip):
        return
    findings.append(
        _finding(
            code="legacy-vip-config",
            path=".vip/",
            category="legacy-settings",
            message=(
                "`.vip/` contains pre-current Main Branch config or state. Treat it as "
                "legacy audit material, not active product truth; doctor classifies keys "
                "without printing raw values."
            ),
            repair_command="mb doctor repair --plan --json",
        )
    )


def _lint_push_shapes(
    repo: Path,
    findings: list[dict[str, Any]],
    frontmatter_cache: dict[Path, dict[str, Any]],
) -> None:
    pushes = repo / "pushes"
    if not pushes.is_dir():
        return
    for md in _iter_markdown_files(pushes):
        rel = md.relative_to(repo).as_posix()
        parts = md.relative_to(repo).parts
        fm = _cached_frontmatter(md, frontmatter_cache)
        if parts[-1] == "push.md":
            if len(parts) != 3 or not pushes_mod.PUSH_FOLDER_RE.fullmatch(parts[1]):
                findings.append(
                    _finding(
                        code="push-record-wrong-shape",
                        path=rel,
                        category="filename",
                        message="Push records should live at `pushes/<YYYY-MM-DD-slug>/push.md`.",
                        repair_command="mb doctor repair --plan --json",
                    )
                )
            continue
        if fm.get("type") == "push":
            findings.append(
                _finding(
                    code="push-frontmatter-wrong-path",
                    path=rel,
                    category="filename",
                    message=(
                        "A `type: push` record should be named `pushes/<YYYY-MM-DD-slug>/push.md`."
                    ),
                    repair_command="mb doctor repair --plan --json",
                )
            )
        if fm.get("type") == "playbook" and (len(parts) < 4 or parts[2] != "playbooks"):
            findings.append(
                _finding(
                    code="playbook-run-wrong-path",
                    path=rel,
                    category="filename",
                    message="Playbook run records should live under `pushes/<push>/playbooks/`.",
                    repair_command="mb doctor repair --plan --json",
                )
            )


def _lint_frontmatter(
    repo: Path,
    findings: list[dict[str, Any]],
    frontmatter_cache: dict[Path, dict[str, Any]],
) -> None:
    for bet in _iter_markdown_files(repo / "bets"):
        fm = _read_frontmatter(bet)
        if not fm:
            continue
        rel = bet.relative_to(repo).as_posix()
        if "linked_campaigns" in fm and "linked_pushes" not in fm:
            findings.append(
                _finding(
                    code="bet-legacy-campaign-links-only",
                    path=rel,
                    category="frontmatter",
                    message=(
                        "`linked_campaigns` remains readable, but current bets should also "
                        "use `linked_pushes` for canonical push links."
                    ),
                    repair_command="mb validate --json",
                )
            )
    for push in _iter_markdown_files(repo / "pushes"):
        fm = _cached_frontmatter(push, frontmatter_cache)
        if fm and push.name == "push.md" and fm.get("type") not in {None, "push"}:
            findings.append(
                _finding(
                    code="push-record-type-mismatch",
                    path=push.relative_to(repo).as_posix(),
                    category="frontmatter",
                    message="Files named `push.md` should use `type: push` frontmatter.",
                    repair_command="mb validate --json",
                )
            )


def _lint_claude_guidance(repo: Path, findings: list[dict[str, Any]]) -> None:
    path = repo / "CLAUDE.md"
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for code, concept, pattern, message in STALE_CLAUDE_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        context = text[max(0, match.start() - 24) : match.end() + 24].lower()
        if (code.endswith("write-guidance") or code.endswith("core-guidance")) and any(
            phrase in context
            for phrase in (
                "do not write",
                "don't write",
                "never write",
                "not write",
                "compatibility fallback",
                "compatibility path",
            )
        ):
            continue
        findings.append(
            _finding(
                code=code,
                path="CLAUDE.md",
                category="runtime-guidance",
                message=(
                    f"Generated repo guidance still teaches `{concept}` as an active path. "
                    f"{message}"
                ),
                repair_command="mb doctor repair --plan --json",
            )
        )


def _lint_settings(repo: Path, findings: list[dict[str, Any]]) -> None:
    path = repo / ".claude" / "settings.local.json"
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    dirs = data.get("permissions", {}).get("additionalDirectories", [])
    if not isinstance(dirs, list):
        return
    root = engine_mod.engine_root()
    if root is None:
        return
    install = engine_mod.mb_install_diagnostics()
    stale = [
        value
        for value in dirs
        if isinstance(value, str) and engine_mod.is_stale_engine_path(value, root)
    ]
    if stale:
        other_install = (
            " This often happens when multiple `mb` installs are active on PATH."
            if install.get("multiple_installs")
            else ""
        )
        findings.append(
            {
                **_finding(
                    code="stale-claude-settings-engine-path",
                    path=".claude/settings.local.json",
                    category="runtime-settings",
                    message=(
                        f".claude/settings.local.json has {len(stale)} stale Main Branch "
                        "engine path(s). Refresh project-local skill wiring before trusting "
                        f"runtime discovery. Current mb: {install.get('active_path') or 'unknown'} "
                        f"{install.get('current_version') or ''}; wired engine: {stale[0]}."
                        f"{other_install}"
                    ),
                    repair_command="mb skill link --repo . --json",
                ),
                "current_mb_path": install.get("active_path") or "",
                "current_mb_version": install.get("current_version") or "",
                "current_engine_path": str(root),
                "wired_engine_paths": stale,
                "multiple_mb_installs": bool(install.get("multiple_installs")),
                "mb_installs": install.get("installs") or [],
            }
        )


def run(repo: str | Path) -> dict[str, Any]:
    target = Path(repo).expanduser().resolve()
    findings: list[dict[str, Any]] = []
    frontmatter_cache: dict[Path, dict[str, Any]] = {}
    _lint_reference(target, findings)
    _lint_campaigns(target, findings)
    _lint_top_level_folders(target, findings)
    _lint_vip(target, findings)
    _lint_push_shapes(target, findings, frontmatter_cache)
    _lint_frontmatter(target, findings, frontmatter_cache)
    _lint_claude_guidance(target, findings)
    _lint_settings(target, findings)
    categories = sorted({str(item["category"]) for item in findings})
    return {
        "ok": not findings,
        "repo": str(target),
        "findings": findings,
        "summary": {
            "warnings": len(findings),
            "categories": categories,
        },
    }
