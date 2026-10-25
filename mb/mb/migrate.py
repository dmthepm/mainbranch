"""Schema-versioned repo migrations for ``mb migrate``."""

from __future__ import annotations

import difflib
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from mb import migrations
from mb.durable import atomic_write_text
from mb.engine import repo_flag
from mb.gitignore import gitignore_problem
from mb.migrations.base import MigrationInfo, MigrationPlan, PlannedChange

ENVELOPE_SCHEMA = "mb.migrate"
ENVELOPE_SCHEMA_VERSION = 2
LATEST_SCHEMA_VERSION = "0.2"
SCHEMA_MARKER = ".mb/schema_version"
BACKUPS_GITIGNORE_ENTRY = ".mb/backups/"
IGNORED_OS_METADATA_FILES = {".DS_Store", "Thumbs.db", "Desktop.ini"}


class MigrationApplyError(RuntimeError):
    """Raised when the filesystem changes after a successful dry-run plan."""


def _marker_path(repo: Path) -> Path:
    return repo / SCHEMA_MARKER


def read_schema_version(repo: str | Path) -> str:
    """Read or infer the business-repo schema version."""
    target = Path(repo).resolve()
    marker = _marker_path(target)
    if marker.exists():
        value = marker.read_text(encoding="utf-8").strip()
        return value or "unknown"
    legacy_reference_paths = (
        "core",
        "offers",
        "proof",
        "brand",
        "strategy",
        "visual-identity",
        "domain",
    )
    if any(
        (target / "reference" / path).exists() and not (target / "reference" / path).is_symlink()
        for path in legacy_reference_paths
    ):
        return "0.1"
    if (target / "core").is_dir():
        return LATEST_SCHEMA_VERSION
    return "unknown"


def _schema_key(version: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(part) for part in version.strip().split("."))
    except ValueError:
        return None


def is_future_schema_version(version: str) -> bool:
    current = _schema_key(version)
    latest = _schema_key(LATEST_SCHEMA_VERSION)
    if current is None or latest is None:
        return False
    return current > latest


def schema_write_blocker(repo: str | Path) -> str:
    version = read_schema_version(repo)
    if not is_future_schema_version(version):
        return ""
    return (
        f"schema {version} is newer than this engine supports "
        f"(latest {LATEST_SCHEMA_VERSION}); upgrade Main Branch before writing."
    )


def _migration_dict(info: MigrationInfo) -> dict[str, str]:
    return {
        "id": info.id,
        "name": info.name,
        "from_version": info.from_version,
        "to_version": info.to_version,
        "description": info.description,
    }


def pending_migrations(repo: str | Path) -> list[tuple[MigrationInfo, Any]]:
    """Return registered migrations pending for ``repo``."""
    version = read_schema_version(repo)
    if is_future_schema_version(version):
        return []
    pending: list[tuple[MigrationInfo, Any]] = []
    version_map = migrations.version_map()
    for info, module in migrations.registered():
        registered_module = version_map.get(version)
        if version == info.from_version and registered_module == module.__name__:
            pending.append((info, module))
            version = info.to_version
    return pending


def _read_text_for_diff(path: Path) -> list[str]:
    if not path.exists() or not path.is_file():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)


def _diff_for_change(repo: Path, change: PlannedChange) -> list[str]:
    if change.kind == "move_file":
        source = repo / change.source
        old_lines = _read_text_for_diff(source)
        new_lines = old_lines
        delete_diff = list(
            difflib.unified_diff(
                old_lines,
                [],
                fromfile=f"a/{change.source}",
                tofile="/dev/null",
                lineterm="",
            )
        )
        add_diff = list(
            difflib.unified_diff(
                [],
                new_lines,
                fromfile="/dev/null",
                tofile=f"b/{change.target}",
                lineterm="",
            )
        )
        return delete_diff + add_diff
    if change.kind == "delete_file":
        old_lines = _read_text_for_diff(repo / change.path)
        return list(
            difflib.unified_diff(
                old_lines,
                [],
                fromfile=f"a/{change.path}",
                tofile="/dev/null",
                lineterm="",
            )
        )
    if change.kind == "write_file":
        old_lines = _read_text_for_diff(repo / change.path)
        new_lines = change.content.splitlines(keepends=True)
        return list(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{change.path}" if old_lines else "/dev/null",
                tofile=f"b/{change.path}",
                lineterm="",
            )
        )
    if change.kind == "symlink":
        new_lines = [f"symlink -> {change.target}\n"]
        return list(
            difflib.unified_diff(
                [],
                new_lines,
                fromfile="/dev/null",
                tofile=f"b/{change.path}",
                lineterm="",
            )
        )
    return []


def _unified_diff(repo: Path, plans: list[MigrationPlan], include_marker: bool) -> str:
    lines: list[str] = []
    for plan in plans:
        for change in plan.changes:
            lines.extend(_diff_for_change(repo, change))
    if include_marker:
        marker_change = PlannedChange(
            kind="write_file",
            path=SCHEMA_MARKER,
            content=LATEST_SCHEMA_VERSION + "\n",
        )
        lines.extend(_diff_for_change(repo, marker_change))
    return "\n".join(lines) + ("\n" if lines else "")


def _plan_dict(plan: MigrationPlan) -> dict[str, Any]:
    return {
        "migration": _migration_dict(plan.migration),
        "has_changes": plan.has_changes,
        "changes": [
            {
                "kind": change.kind,
                "path": change.path,
                "source": change.source,
                "target": change.target,
            }
            for change in plan.changes
        ],
        "errors": plan.errors,
    }


def _plan_has_changes(plans: list[MigrationPlan]) -> bool:
    return any(plan.has_changes for plan in plans)


def _backup_hint(plans: list[MigrationPlan]) -> dict[str, Any]:
    return {
        "will_create": bool(plans and _plan_has_changes(plans)),
        "directory": ".mb/backups/",
        "note": (
            "`mb migrate --apply` creates a timestamped repo-local backup before changing files."
        ),
    }


def _next_after_status(result: dict[str, Any]) -> str:
    if result.get("errors"):
        return "Upgrade Main Branch before running migrations or repair writes in this repo."
    if result.get("pending"):
        return "Run `mb migrate --check` to preview the migration before applying it."
    return "No layout migration is pending."


def _next_after_check(result: dict[str, Any]) -> str:
    if result.get("errors"):
        return (
            "Do not apply yet. Reconcile the reported conflicts, then rerun `mb migrate --check`."
        )
    plan = result.get("plan") or {}
    if plan.get("has_changes"):
        return "Review this dry-run. If it matches the move you want, run `mb migrate --apply`."
    return "No layout migration is pending."


_APPLIED_NEXT = "Run `mb doctor`, `mb validate`, and `mb start --json` from the migrated repo."


def name_repo(text: str, repo: str | Path) -> str:
    """The suggested commands in `next`, naming the business repo from another folder (#1083).

    Unchanged from inside the repo. The apply sentence is built by hand because
    `mb doctor` takes the repo as an argument and `mb start` as `--repo`.
    """
    flag = repo_flag(repo)
    if not flag:
        return text
    if text == _APPLIED_NEXT:
        quoted = flag.removeprefix(" --repo ")
        return f"Run `mb doctor {quoted}`, `mb validate{flag}`, and `mb start --json{flag}`."
    from mb import doctor  # doctor imports modules that import migrate

    return doctor._qualify_prose(text, Path(repo))


def _next_after_apply(result: dict[str, Any]) -> str:
    if result.get("errors"):
        return (
            "No further migration writes are safe yet. Review the backup path if "
            "one was created, reconcile the error, then rerun `mb migrate --check`."
        )
    if result.get("applied"):
        return _APPLIED_NEXT
    return "No layout migration was applied."


def _base_envelope(repo: Path, action: str) -> dict[str, Any]:
    pending = pending_migrations(repo)
    blocker = schema_write_blocker(repo)
    result = {
        "schema": ENVELOPE_SCHEMA,
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "ok": not blocker,
        "action": action,
        "repo": str(repo),
        "current_version": read_schema_version(repo),
        "latest_version": LATEST_SCHEMA_VERSION,
        "pending": [_migration_dict(info) for info, _module in pending],
        "plan": None,
        "applied": [],
        "backup": None,
        "errors": [blocker] if blocker else [],
        "next": "",
    }
    result["next"] = _next_after_status(result)
    return result


def status(repo: str | Path = ".") -> dict[str, Any]:
    """Return current schema version and pending migrations."""
    target = Path(repo).resolve()
    return _base_envelope(target, "status")


def check(repo: str | Path = ".", *, include_diff: bool = False) -> dict[str, Any]:
    """Plan pending migrations without writing files."""
    target = Path(repo).resolve()
    result = _base_envelope(target, "check")
    if result["errors"]:
        result["plan"] = {
            "has_changes": False,
            "migrations": [],
            "diff_included": include_diff,
            "diff": "",
            "privacy_note": "",
            "errors": list(result["errors"]),
        }
        result["backup"] = _backup_hint([])
        result["next"] = _next_after_check(result)
        return result
    pending = pending_migrations(target)
    plans = [migrations.plan_for(info, module, target) for info, module in pending]
    _ensure_gitignore_plan(target, plans)
    errors = [error for plan in plans for error in plan.errors]
    result["ok"] = not errors
    result["plan"] = {
        "has_changes": any(plan.has_changes for plan in plans),
        "migrations": [_plan_dict(plan) for plan in plans],
        "diff_included": include_diff,
        "diff": _unified_diff(target, plans, include_marker=bool(pending)) if include_diff else "",
        "privacy_note": (
            "Full file diffs are hidden by default because legacy business repos "
            "can contain private strategy, proof, and offer details. Re-run with "
            "`--diff` only when the output will stay local."
        ),
        "errors": errors,
    }
    result["backup"] = _backup_hint(plans)
    result["errors"] = errors
    result["next"] = _next_after_check(result)
    return result


def _backup_path(repo: Path, migration_ids: list[str]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = "-".join(migration_ids) if migration_ids else "noop"
    return repo / ".mb" / "backups" / f"{stamp}-{suffix}"


def _gitignore_content_with_backups(text: str) -> str:
    lines = text.splitlines()
    if BACKUPS_GITIGNORE_ENTRY in {line.strip() for line in lines}:
        return text
    prefix = text if text.endswith("\n") or not text else text + "\n"
    return prefix + BACKUPS_GITIGNORE_ENTRY + "\n"


def _is_os_metadata_file(path: Path) -> bool:
    return path.name in IGNORED_OS_METADATA_FILES or path.name.startswith("._")


def _remove_ignored_metadata_tree(path: Path) -> None:
    if not path.is_dir():
        return
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink() and _is_os_metadata_file(child):
            child.unlink()
    for child in sorted(
        (item for item in path.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        if not any(child.iterdir()):
            child.rmdir()


def _ensure_gitignore_plan(repo: Path, plans: list[MigrationPlan]) -> None:
    if not plans or gitignore_problem(repo):
        return
    gitignore = repo / ".gitignore"
    text = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    updated = _gitignore_content_with_backups(text)
    if updated == text:
        return
    plans[0].changes.append(PlannedChange(kind="write_file", path=".gitignore", content=updated))


def _backup_existing_paths(repo: Path, backup_dir: Path, plans: list[MigrationPlan]) -> list[str]:
    copied: list[str] = []
    paths: set[str] = {SCHEMA_MARKER}
    for plan in plans:
        for change in plan.changes:
            if change.kind in {"move_file", "delete_file"} and change.source:
                paths.add(change.source)
            elif change.kind in {"write_file", "symlink"}:
                paths.add(change.path)

    for rel in sorted(paths):
        source = repo / rel
        if not source.exists() and not source.is_symlink():
            continue
        dest = backup_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            dest.write_text(f"symlink -> {source.readlink().as_posix()}\n", encoding="utf-8")
        elif source.is_dir():
            shutil.copytree(source, dest, symlinks=True, dirs_exist_ok=True)
        else:
            shutil.copy2(source, dest)
        copied.append(rel)
    return copied


def _apply_change(repo: Path, change: PlannedChange) -> None:
    path = repo / change.path
    if change.kind == "mkdir":
        path.mkdir(parents=True, exist_ok=True)
        return
    if change.kind == "move_file":
        source = repo / change.source
        target = repo / change.target
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and source.exists() and source.read_bytes() == target.read_bytes():
            source.unlink()
            return
        source.rename(target)
        return
    if change.kind == "delete_file":
        if path.exists():
            path.unlink()
        return
    if change.kind == "write_file":
        atomic_write_text(path, change.content)
        return
    if change.kind == "remove_empty_dir":
        if path.is_dir():
            _remove_ignored_metadata_tree(path)
            if not any(path.iterdir()):
                path.rmdir()
                return
            raise MigrationApplyError(f"{change.path} is not empty; aborting before replacement")
        if path.exists():
            raise MigrationApplyError(f"{change.path} is not empty; aborting before replacement")
        return
    if change.kind == "symlink":
        if path.is_symlink() and path.readlink().as_posix() == change.target:
            return
        if path.exists() or path.is_symlink():
            raise MigrationApplyError(f"{change.path} already exists; cannot create symlink")
        path.symlink_to(change.target, target_is_directory=True)


def apply(repo: str | Path = ".") -> dict[str, Any]:
    """Apply pending migrations after creating a repo-local backup."""
    target = Path(repo).resolve()
    result = check(target, include_diff=False)
    result["action"] = "apply"
    plans = [
        migrations.plan_for(info, module, target) for info, module in pending_migrations(target)
    ]
    _ensure_gitignore_plan(target, plans)
    if result["errors"]:
        result["ok"] = False
        result["next"] = _next_after_apply(result)
        return result
    if not plans:
        result["ok"] = True
        result["next"] = _next_after_apply(result)
        return result

    backup_dir = _backup_path(target, [plan.migration.id for plan in plans])
    backup_dir.mkdir(parents=True, exist_ok=False)
    copied = _backup_existing_paths(target, backup_dir, plans)
    atomic_write_text(
        backup_dir / "manifest.json",
        json.dumps({"schema_version": 1, "copied": copied}, indent=2) + "\n",
    )

    for plan in plans:
        for change in plan.changes:
            try:
                _apply_change(target, change)
            except (OSError, MigrationApplyError) as exc:
                result["ok"] = False
                result["errors"].append(str(exc))
                result["backup"] = {"path": str(backup_dir), "copied": copied}
                result["next"] = _next_after_apply(result)
                return result

    marker = _marker_path(target)
    atomic_write_text(marker, LATEST_SCHEMA_VERSION + "\n")

    result["ok"] = True
    result["current_version"] = LATEST_SCHEMA_VERSION
    result["pending"] = []
    result["applied"] = [_migration_dict(plan.migration) for plan in plans]
    result["backup"] = {"path": str(backup_dir), "copied": copied}
    result["next"] = _next_after_apply(result)
    return result


def render_status(result: dict[str, Any]) -> None:
    print(f"schema version: {result['current_version']}")
    pending = result.get("pending", [])
    if pending:
        print("pending migrations:")
        for item in pending:
            print(f"  {item['id']} {item['name']} ({item['from_version']} -> {item['to_version']})")
    else:
        print("pending migrations: none")
    if result.get("next"):
        print(f"next: {result['next']}")


def _render_plan_summary(plan: dict[str, Any]) -> None:
    print("pending migration changes:")
    for migration in plan.get("migrations", []):
        info = migration["migration"]
        print(f"  {info['id']} {info['name']} ({info['from_version']} -> {info['to_version']})")
        for change in migration.get("changes", []):
            detail = change.get("path") or change.get("target") or change.get("source")
            if change.get("kind") == "move_file":
                detail = f"{change.get('source')} -> {change.get('target')}"
            print(f"    - {change.get('kind')}: {detail}")


def render_check(result: dict[str, Any]) -> None:
    plan = result.get("plan") or {}
    errors = result.get("errors", [])
    if errors:
        print("migration blocked; no files changed.")
        for error in errors:
            print(f"error: {error}")
        if plan.get("has_changes"):
            print()
            _render_plan_summary(plan)
        if result.get("next"):
            print()
            print(f"next: {result['next']}")
        return
    diff = str(plan.get("diff", ""))
    if diff:
        print(diff, end="")
    elif plan.get("has_changes"):
        _render_plan_summary(plan)
        print()
        print(plan.get("privacy_note", "Full diffs are hidden by default."))
        diff_command = f"mb migrate{repo_flag(result['repo'])} --check --diff"
        print(f"Run `{diff_command}` to print the full unified diff locally.")
        backup = result.get("backup") or {}
        if backup.get("will_create"):
            print(f"Backup on apply: {backup['directory']}")
        if result.get("next"):
            print(f"next: {result['next']}")
    else:
        print("no migrations pending")
        if result.get("next"):
            print(f"next: {result['next']}")


def render_apply(result: dict[str, Any]) -> None:
    if result.get("errors"):
        for error in result["errors"]:
            print(f"error: {error}")
        if result.get("next"):
            print(f"next: {result['next']}")
        return
    applied = result.get("applied", [])
    if not applied:
        print("no migrations pending")
        return
    print(f"applied {len(applied)} migration(s)")
    backup = result.get("backup") or {}
    if backup.get("path"):
        print(f"backup: {backup['path']}")
    print(f"schema version: {result['current_version']}")
    if result.get("next"):
        print(f"next: {result['next']}")


# ---------------------------------------------------------------------------
# campaigns -> pushes migration planner (preview-only)
#
# Per the MAIN-251 push primitive decision, the canonical engine primitive is
# `pushes/`. This planner walks legacy `campaigns/<slug>/campaign.md` records
# and proposes per-record moves to `pushes/<YYYY-MM-DD-slug>/push.md`.
#
# Plan-only in this release: the planner classifies records but does not move
# files. Apply lands in a follow-up PR with explicit operator approval and
# backup. Per the issue's Migration Rubric, no silent migration; ambiguous
# generated folders surface for operator review.
# ---------------------------------------------------------------------------

CAMPAIGNS_PLAN_SCHEMA = "mb.migrate.campaigns"
CAMPAIGNS_PLAN_SCHEMA_VERSION = 1

_DATED_DAY_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})-")
_DATED_MONTH_PREFIX = re.compile(r"^(\d{4}-\d{2})-")
_PUSH_FOLDER_NAMES = {"ads", "emails", "posts", "reviews", "assets", "source"}
_PUSH_FILE_NAMES = {
    "ads.md",
    "emails.md",
    "posts.md",
    "site.md",
    "review-log.md",
}


def _read_campaign_frontmatter(path: Path) -> dict[str, Any]:
    """Best-effort YAML frontmatter read; returns {} on failure."""
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
    block = text[3:end].lstrip("\n")
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _infer_push_date(folder_name: str, frontmatter: dict[str, Any]) -> tuple[str, str] | None:
    """Return (YYYY-MM-DD date string, source-label) or None when ambiguous."""
    day_match = _DATED_DAY_PREFIX.match(folder_name)
    if day_match:
        return day_match.group(1), "folder.day-prefix"
    month_match = _DATED_MONTH_PREFIX.match(folder_name)
    if month_match:
        return f"{month_match.group(1)}-01", "folder.month-prefix"
    for field in ("started", "review_on"):
        value = frontmatter.get(field)
        if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return value, f"frontmatter.{field}"
        iso_method = getattr(value, "isoformat", None)
        if callable(iso_method):
            iso = iso_method()
            if isinstance(iso, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso):
                return iso, f"frontmatter.{field}"
    return None


def _slug_without_date_prefix(folder_name: str) -> str:
    day_match = _DATED_DAY_PREFIX.match(folder_name)
    if day_match:
        return folder_name[len(day_match.group(0)) :]
    month_match = _DATED_MONTH_PREFIX.match(folder_name)
    if month_match:
        return folder_name[len(month_match.group(0)) :]
    return folder_name


def _enumerate_folder_contents(folder: Path, repo: Path) -> tuple[list[str], list[str]]:
    """Split a campaign folder's children into (recognized, unrecognized) artifacts.

    Recognized = listed in the Migration Rubric (ads/, emails/, posts/, site.md,
    review-log.md, assets/, source/, etc.). These are auto-moved with the push.
    Unrecognized = anything else inside the folder; these are flagged as
    ambiguous within the move and surfaced for operator review rather than
    silently moved.
    """
    recognized: list[str] = []
    unrecognized: list[str] = []
    for child in sorted(folder.iterdir()):
        if child.name == "campaign.md":
            continue
        if child.name == ".gitkeep":
            continue
        rel = child.relative_to(repo).as_posix()
        is_recognized_dir = child.is_dir() and child.name in _PUSH_FOLDER_NAMES
        is_recognized_file = child.is_file() and child.name in _PUSH_FILE_NAMES
        if is_recognized_dir or is_recognized_file:
            recognized.append(rel)
        else:
            unrecognized.append(rel)
    return recognized, unrecognized


def _git_first_added_date(repo: Path, path: Path) -> str | None:
    """Best-effort git first-added date (YYYY-MM-DD) for a file.

    Returns None when not in a git repo, when the file has never been committed,
    or when git is unavailable. Never raises.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "log",
                "--diff-filter=A",
                "--follow",
                "--format=%ad",
                "--date=short",
                "--",
                str(path.relative_to(repo)),
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    candidate = lines[-1]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
        return candidate
    return None


def _infer_push_date_with_git(
    folder_name: str,
    frontmatter: dict[str, Any],
    record_path: Path,
    repo: Path,
) -> tuple[str, str] | None:
    """Apply the full Migration Rubric date inference, including git fallback."""
    primary = _infer_push_date(folder_name, frontmatter)
    if primary is not None:
        return primary
    git_date = _git_first_added_date(repo, record_path)
    if git_date is not None:
        return git_date, "git.first-added"
    return None


def _classify_loose_top_level_file(child: Path, repo: Path) -> dict[str, Any]:
    """A file at the top of campaigns/ has no folder context and no record. Ambiguous."""
    rel = child.relative_to(repo).as_posix()
    return {
        "kind": "ambiguous",
        "from": rel,
        "reason": (
            "loose file at the top of campaigns/ (not inside a campaign folder). "
            "No campaign.md context; cannot infer a coordinated push."
        ),
        "suggestion": (
            "review with the operator. If it is generated content, consider "
            "documents/prototypes/ or documents/archive/. If it belongs to a "
            "specific push, move it inside the push folder by hand and re-run "
            "the plan. If unsure, leave in place."
        ),
    }


def _classify_campaign_folder(folder: Path, repo: Path) -> dict[str, Any]:
    """Classify one direct child of campaigns/ as a move, ambiguous, or blocker."""
    rel = folder.relative_to(repo).as_posix()
    record = folder / "campaign.md"
    if not record.is_file():
        # No campaign.md -- this is generated material, not a coordinated push.
        # Per the rubric, do not auto-promote into pushes/.
        recognized, unrecognized = _enumerate_folder_contents(folder, repo)
        contents = recognized + unrecognized
        return {
            "kind": "ambiguous",
            "from": rel,
            "reason": "no campaign.md inside this folder; cannot infer a coordinated push",
            "suggestion": (
                "review with the operator. Likely homes: documents/archive/, "
                "documents/prototypes/, or leave in place with a warning."
            ),
            "contents": contents,
        }

    frontmatter = _read_campaign_frontmatter(record)
    inferred = _infer_push_date_with_git(folder.name, frontmatter, record, repo)
    slug = _slug_without_date_prefix(folder.name)
    if inferred is None:
        return {
            "kind": "blocker",
            "from": rel,
            "reason": (
                "cannot infer a date for the push folder name. Folder has no "
                "YYYY-MM-DD or YYYY-MM prefix, frontmatter has no `started` or "
                "`review_on` date, and the file has no git history."
            ),
            "suggestion": (
                "add `started: YYYY-MM-DD` to the campaign.md frontmatter or "
                "rename the folder with a dated prefix, then re-run the plan."
            ),
        }
    date_str, date_source = inferred
    push_folder = f"pushes/{date_str}-{slug}"
    push_record_rel = f"{push_folder}/push.md"
    move_with_push, review_inside_folder = _enumerate_folder_contents(folder, repo)
    frontmatter_changes: list[str] = []
    if frontmatter.get("type") == "campaign":
        frontmatter_changes.append("type: campaign -> type: push")
    if "linked_campaigns" in frontmatter:
        frontmatter_changes.append("linked_campaigns -> linked_pushes (rename)")
    has_provider_meta_ads = (
        isinstance(frontmatter.get("provider_refs"), dict)
        and "meta_ads" in frontmatter["provider_refs"]
    )
    notes: list[str] = []
    if has_provider_meta_ads:
        notes.append(
            "provider_refs.meta_ads.campaign_id preserved (Meta's term for its object, "
            "not the engine primitive)"
        )
    if review_inside_folder:
        notes.append(
            "unrecognized files inside this folder will NOT auto-move with the push; "
            "see review_inside_folder for the operator-review list"
        )
    return {
        "kind": "move",
        "from": rel,
        "to": push_record_rel,
        "date": date_str,
        "date_source": date_source,
        "slug": slug,
        "frontmatter_changes": frontmatter_changes,
        "move_with_push": move_with_push,
        "review_inside_folder": review_inside_folder,
        "notes": notes,
    }


def plan_campaigns_to_pushes(repo: str | Path = ".") -> dict[str, Any]:
    """Read-only plan classifying every campaigns/ child as a move, ambiguous, or blocker.

    Returns a structured dict that ``mb migrate campaigns --plan`` renders or
    serializes to JSON. Does not write any files. Apply lands in a follow-up
    PR with backups and explicit operator approval.
    """
    target = Path(repo).expanduser().resolve()
    envelope: dict[str, Any] = {
        "schema": CAMPAIGNS_PLAN_SCHEMA,
        "schema_version": CAMPAIGNS_PLAN_SCHEMA_VERSION,
        "repo": str(target),
        "ok": True,
        "moves": [],
        "ambiguous": [],
        "blockers": [],
        "summary": {"moves": 0, "ambiguous": 0, "blockers": 0},
        "next": (
            "Plan-only in this release. `mb migrate campaigns --apply` is not yet "
            "implemented; the apply path lands in a follow-up PR with backups and "
            "explicit operator approval."
        ),
    }

    campaigns_dir = target / "campaigns"
    if not campaigns_dir.is_dir():
        envelope["next"] = "no legacy campaigns/ folder; nothing to migrate"
        return envelope

    direct_children = [
        child for child in sorted(campaigns_dir.iterdir()) if child.name != ".gitkeep"
    ]
    if not direct_children:
        envelope["next"] = "campaigns/ folder is empty; nothing to migrate"
        return envelope

    for child in direct_children:
        if child.is_file():
            classification = _classify_loose_top_level_file(child, target)
        elif child.is_dir():
            classification = _classify_campaign_folder(child, target)
        else:
            # Symlink or other; skip with a conservative ambiguous entry.
            classification = {
                "kind": "ambiguous",
                "from": child.relative_to(target).as_posix(),
                "reason": "non-file, non-directory entry under campaigns/",
                "suggestion": (
                    "review with the operator; the migrate planner does not touch symlinks."
                ),
            }
        kind = classification.pop("kind")
        if kind == "move":
            envelope["moves"].append(classification)
        elif kind == "ambiguous":
            envelope["ambiguous"].append(classification)
        else:
            envelope["blockers"].append(classification)

    envelope["summary"]["moves"] = len(envelope["moves"])
    envelope["summary"]["ambiguous"] = len(envelope["ambiguous"])
    envelope["summary"]["blockers"] = len(envelope["blockers"])
    envelope["ok"] = len(envelope["blockers"]) == 0
    return envelope


def render_campaigns_plan(result: dict[str, Any]) -> None:
    """Operator-facing rendering of `mb migrate campaigns --plan`."""
    summary = result["summary"]
    print(f"campaigns -> pushes plan for {result['repo']}")
    print(
        f"  moves: {summary['moves']}  "
        f"ambiguous: {summary['ambiguous']}  "
        f"blockers: {summary['blockers']}"
    )
    for move in result["moves"]:
        print(f"\nmove: {move['from']}")
        print(f"  -> {move['to']}")
        print(f"  date: {move['date']}  (source: {move['date_source']})")
        for change in move.get("frontmatter_changes", []):
            print(f"  frontmatter: {change}")
        for note in move.get("notes", []):
            print(f"  note: {note}")
        if move.get("move_with_push"):
            print(f"  move with push: {len(move['move_with_push'])} item(s)")
            for path in move["move_with_push"]:
                print(f"    - {path}")
        if move.get("review_inside_folder"):
            print(f"  review before apply: {len(move['review_inside_folder'])} item(s)")
            for path in move["review_inside_folder"]:
                print(f"    - {path}")
    for ambiguous in result["ambiguous"]:
        print(f"\nambiguous: {ambiguous['from']}")
        print(f"  reason: {ambiguous['reason']}")
        print(f"  suggestion: {ambiguous['suggestion']}")
    for blocker in result["blockers"]:
        print(f"\nblocker: {blocker['from']}")
        print(f"  reason: {blocker['reason']}")
        print(f"  suggestion: {blocker['suggestion']}")
    print(f"\n{result['next']}")
