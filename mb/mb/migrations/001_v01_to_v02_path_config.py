"""001: migrate v0.1 reference paths to the v0.2 repo layout."""

from __future__ import annotations

from pathlib import Path

from mb.migrations.base import MigrationInfo, MigrationPlan, PlannedChange

INFO = MigrationInfo(
    id="001",
    name="001_v01_to_v02_path_config",
    from_version="0.1",
    to_version="0.2",
    description="Move legacy reference paths into current core paths.",
)

CURRENT_DIRS = (
    "core",
    "core/offers",
    "core/proof",
    "core/brand",
    "core/strategy",
    "core/operations",
    "core/finance",
    "research",
    "decisions",
    "bets",
    "log",
    "pushes",
    "documents",
)
LEGACY_TREE_MOVES = (
    ("reference/core", "core"),
    ("reference/offers", "core/offers"),
    ("reference/proof", "core/proof"),
    ("reference/brand", "core/brand"),
    ("reference/strategy", "core/strategy"),
    ("reference/visual-identity", "core/brand"),
    ("reference/domain", "core/operations"),
)
LEGACY_FILE_MOVES = (
    ("reference/domain/content-strategy.md", "core/content-strategy.md"),
    ("reference/domain/product-ladder.md", "core/product-ladder.md"),
)
IGNORED_METADATA_FILES = {
    ".DS_Store",
    "Thumbs.db",
    "Desktop.ini",
}
DECISION_PATH = "decisions/2026-05-02-mainbranch-v02-path-migration.md"
DECISION_CONTENT = """\
---
type: decision
date: 2026-05-02
status: accepted
topic: Main Branch v0.2 path migration
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/175
---

# Main Branch v0.2 Path Migration

This repo was migrated by `mb migrate` from the legacy v0.1 reference layout to
the current v0.2 layout.

## Changes

- Moved `reference/core/*` into `core/`.
- Moved `reference/offers/*` into `core/offers/` when present.
- Moved `reference/proof/*` into `core/proof/`.
- Moved `reference/brand/*` and `reference/visual-identity/*` into `core/brand/`.
- Moved `reference/strategy/*` into `core/strategy/`.
- Moved brand-level `reference/domain/content-strategy.md` and
  `reference/domain/product-ladder.md` into `core/`.
- Moved remaining `reference/domain/*` operating context into `core/operations/`.
- Kept `reference/core` and `reference/offers` as compatibility links.
- Added current Main Branch working folders.
- Wrote `.mb/schema_version`.
"""


def _is_correct_symlink(path: Path, target: str) -> bool:
    return path.is_symlink() and path.readlink().as_posix() == target


def _is_empty_dir(path: Path) -> bool:
    return path.is_dir() and not any(path.iterdir())


def _bytes_equal(left: Path, right: Path) -> bool:
    try:
        return left.read_bytes() == right.read_bytes()
    except OSError:
        return False


def _relative_files(root: Path, *, exclude: set[Path] | None = None) -> list[Path]:
    if not root.exists() or root.is_symlink():
        return []
    excluded = exclude or set()
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not _is_metadata_file(path)
        and path.relative_to(root) not in excluded
    )


def _is_metadata_file(path: Path) -> bool:
    return path.name in IGNORED_METADATA_FILES or path.name.startswith("._")


def _plan_move_tree(
    repo: Path,
    plan: MigrationPlan,
    source_rel: str,
    target_rel: str,
    *,
    exclude: set[Path] | None = None,
) -> None:
    source_root = repo / source_rel
    target_root = repo / target_rel
    if not source_root.exists() or source_root.is_symlink():
        return
    if not source_root.is_dir():
        plan.errors.append(f"{source_rel} exists but is not a directory")
        return

    files = _relative_files(source_root, exclude=exclude)
    for source in files:
        rel = source.relative_to(source_root)
        target = target_root / rel
        source_path = source.relative_to(repo).as_posix()
        target_path = target.relative_to(repo).as_posix()
        if target.exists():
            if _bytes_equal(source, target):
                plan.changes.append(
                    PlannedChange(kind="delete_file", path=source_path, source=source_path)
                )
                continue
            plan.errors.append(
                f"{target_path} already exists with different contents "
                f"(from {source_path}); manual reconciliation required"
            )
            continue
        plan.changes.append(
            PlannedChange(
                kind="move_file",
                path=target_path,
                source=source_path,
                target=target_path,
            )
        )

    # These remove operations are applied after file moves, deepest first.
    for directory in sorted(
        (path for path in source_root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        plan.changes.append(
            PlannedChange(
                kind="remove_empty_dir",
                path=directory.relative_to(repo).as_posix(),
            )
        )
    plan.changes.append(PlannedChange(kind="remove_empty_dir", path=source_rel))


def _plan_move_file(repo: Path, plan: MigrationPlan, source_rel: str, target_rel: str) -> None:
    source = repo / source_rel
    target = repo / target_rel
    if not source.exists() or source.is_symlink():
        return
    if not source.is_file():
        plan.errors.append(f"{source_rel} exists but is not a file")
        return
    if target.exists():
        if _bytes_equal(source, target):
            plan.changes.append(
                PlannedChange(kind="delete_file", path=source_rel, source=source_rel)
            )
            return
        plan.errors.append(
            f"{target_rel} already exists with different contents "
            f"(from {source_rel}); manual reconciliation required"
        )
        return
    plan.changes.append(
        PlannedChange(kind="move_file", path=target_rel, source=source_rel, target=target_rel)
    )


def _plan_compat_link(repo: Path, plan: MigrationPlan, path_rel: str, target: str) -> None:
    path = repo / path_rel
    if _is_correct_symlink(path, target):
        return
    if any(path_rel == source for source, _target in LEGACY_TREE_MOVES) and path.is_dir():
        plan.changes.append(PlannedChange(kind="symlink", path=path_rel, target=target))
        return
    if path.exists() or path.is_symlink():
        if _is_empty_dir(path):
            plan.changes.append(PlannedChange(kind="remove_empty_dir", path=path_rel))
        else:
            plan.errors.append(f"{path_rel} must be empty before creating compatibility link")
            return
    plan.changes.append(PlannedChange(kind="symlink", path=path_rel, target=target))


def _updated_claude_text(text: str) -> str:
    replacements = (
        ("reference/core/*.md", "core/*.md"),
        ("reference/domain/content-strategy.md", "core/content-strategy.md"),
        ("reference/domain/product-ladder.md", "core/product-ladder.md"),
        ("reference/proof/angles/", "core/proof/angles/"),
        ("reference/proof/", "core/proof/"),
        ("reference/visual-identity/", "core/brand/"),
        ("reference/brand/", "core/brand/"),
        ("reference/strategy/", "core/strategy/"),
        ("reference/domain/", "core/operations/"),
        ("reference/core/", "core/"),
        ("reference/offers/", "core/offers/"),
        ("reference/core", "core"),
        ("reference/offers", "core/offers"),
    )
    updated = text
    for old, new in replacements:
        updated = updated.replace(old, new)
    return updated


def _plan_claude_update(repo: Path, plan: MigrationPlan) -> None:
    path = repo / "CLAUDE.md"
    if not path.exists() or not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        plan.errors.append(f"could not read CLAUDE.md: {exc}")
        return
    updated = _updated_claude_text(text)
    if updated != text:
        plan.changes.append(PlannedChange(kind="write_file", path="CLAUDE.md", content=updated))


def _plan_decision(repo: Path, plan: MigrationPlan) -> None:
    path = repo / DECISION_PATH
    if path.exists():
        return
    plan.changes.append(
        PlannedChange(kind="write_file", path=DECISION_PATH, content=DECISION_CONTENT)
    )


def plan(repo: Path) -> MigrationPlan:
    """Return the deterministic v0.1 -> v0.2 migration plan."""
    result = MigrationPlan(migration=INFO)

    for directory in CURRENT_DIRS:
        path = repo / directory
        if not path.exists():
            result.changes.append(PlannedChange(kind="mkdir", path=directory))
            result.changes.append(
                PlannedChange(kind="write_file", path=f"{directory}/.gitkeep", content="")
            )

    for source, target in LEGACY_FILE_MOVES:
        _plan_move_file(repo, result, source, target)

    for source, target in LEGACY_TREE_MOVES:
        exclude = (
            {Path("content-strategy.md"), Path("product-ladder.md")}
            if source == "reference/domain"
            else None
        )
        _plan_move_tree(repo, result, source, target, exclude=exclude)

    _plan_compat_link(repo, result, "reference/core", "../core")
    _plan_compat_link(repo, result, "reference/offers", "../core/offers")
    _plan_claude_update(repo, result)
    _plan_decision(repo, result)

    return result
