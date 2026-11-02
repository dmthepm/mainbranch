"""Repository layout, legacy state, migration, and validation checks for doctor."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from mb import engine as engine_mod
from mb import migrate as migrate_mod
from mb import topology as topology_mod
from mb import validate as validate_mod
from mb.gitignore import gitignore_problem
from mb.migrate import (
    LATEST_SCHEMA_VERSION,
    pending_migrations,
    read_schema_version,
    schema_write_blocker,
)

CLOUD_PREFIXES = (
    "Library/Mobile Documents",  # iCloud Drive
    "Library/CloudStorage",  # macOS unified cloud
    "Google Drive",
    "GoogleDrive",
    "Dropbox",
    "OneDrive",
)
LOCAL_GITIGNORE_ENTRIES = (
    ".claude/settings.local.json",
    ".claude/worktrees/",
    ".mb/private/",
    ".mb/backups/",
    ".mb/connect.yaml",
    ".mb/onboarding.json",
    ".mb/last-status-seen.json",
    ".mb/issue-drafts/",
    ".vip/local.yaml",
)
LOCAL_STATE_PATHS = (
    ".mb/private",
    ".mb/backups",
    ".mb/connect.yaml",
    ".mb/onboarding.json",
    ".mb/last-status-seen.json",
    ".mb/issue-drafts",
    ".vip/local.yaml",
)
DURABLE_MB_PATHS = (".mb/schema_version",)
LEGACY_VIP_LOCAL_STATE_PATHS = (".vip/local.yaml",)
LEGACY_VIP_AUDIT_PATHS = (".vip/local.yaml", ".vip/config.yaml")
LEGACY_CLAUDE_LINK_DIRS = (".claude/lenses", ".claude/reference")
REFERENCE_COMPAT_LINKS = {
    "reference/core": "../core",
    "reference/offers": "../core/offers",
}
STATE_ORDER = {"ok": 0, "info": 1, "warn": 2, "error": 3}


def _detect_cloud_paths(repo: Path) -> list[str]:
    """Return list of cloud-prefixed paths inside the repo's finance dir.

    The check matches against the *resolved real path* of ``core/finance/``
    so a symlink into iCloud is caught.
    """
    finance = repo / "core" / "finance"
    if not finance.exists():
        return []
    real = finance.resolve()
    home = str(Path.home())
    rel = str(real)
    if rel.startswith(home):
        rel = rel[len(home) + 1 :]
    hits = [p for p in CLOUD_PREFIXES if p in rel]
    return hits


def _repo_layout_check(repo: Path) -> dict[str, Any]:
    has_core = (repo / "core").is_dir()
    has_reference_core = (repo / "reference" / "core").exists()
    has_reference = (repo / "reference").is_dir()

    if has_core:
        return {
            "name": "repo-layout",
            "ok": True,
            "detail": "current core/ layout present",
        }

    if has_reference_core:
        return {
            "name": "repo-layout",
            "ok": False,
            "detail": (
                "legacy reference/core layout detected. This still works, but "
                f"run `mb skill link{engine_mod.repo_flag(repo)}` after upgrading and read "
                "`docs/migrating.md` before moving files."
            ),
            "severity": "warn",
        }

    if has_reference:
        return {
            "name": "repo-layout",
            "ok": False,
            "detail": (
                "legacy reference/ layout detected without core/. Main Branch can "
                "brief this repo, but current schema features may be limited. "
                "Read `docs/migrating.md` before moving files."
            ),
            "severity": "warn",
        }

    return {
        "name": "repo-layout",
        "ok": False,
        "detail": "no core/ or reference/ layout found",
        "severity": "warn",
    }


# The one-set status line `mb init` wrote into CLAUDE.md before #1121, in each
# shipped form: "Status enum:" (0.1.x, backticked template and plain embedded
# fallback) and "Status field:" (later 0.x). Anchored to a list item, as every
# shipped form is, so a CLAUDE.md that quotes the line inside a sentence, or in a
# fenced code block (see `_outside_fences`), is not flagged.
_OLD_STATUS_LINE_RE = re.compile(
    r"^[ \t]*[-*][ \t]+(Status (?:field|enum)):[ \t]*"
    r"`?proposed \| running \| scaling \| killed \| graduated \| died`?",
    re.MULTILINE,
)


_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}(?=[^`]*$)|~{3,})")


def _outside_fences(text: str) -> str:
    """Return ``text`` with lines inside fenced code blocks blanked (CommonMark).

    A fence opens with three or more backticks or tildes (up to three spaces of
    indent, optional info string) and closes on the same character at least as
    long; an unclosed fence runs to the end of the file.
    """
    kept: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        if fence is None:
            opened = _FENCE_OPEN_RE.match(line)
            if opened:
                fence = opened.group(1)
                kept.append("")
            else:
                kept.append(line)
            continue
        kept.append("")
        stripped = line.strip()
        if (
            len(line) - len(line.lstrip(" ")) <= 3
            and len(stripped) >= len(fence)
            and set(stripped) == {fence[0]}
        ):
            fence = None
    return "\n".join(kept)


def _old_status_line_check(repo: Path) -> dict[str, Any] | None:
    """Warn when CLAUDE.md still teaches one status set for every file type (#1122).

    Returns None when the line is absent, so repos without it see no new check.
    The check only suggests the replacement; it never rewrites CLAUDE.md.
    """
    path = repo / "CLAUDE.md"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    match = _OLD_STATUS_LINE_RE.search(_outside_fences(text))
    if match is None:
        return None
    from mb import init as init_mod

    suggested = init_mod.status_conventions()
    repair = (
        "CLAUDE.md still says every file type uses `proposed | running | scaling | killed | "
        "graduated | died`; `mb validate` rejects `running` on a bet. Replace the "
        f"`{match.group(1)}:` line (and any lines continuing it) with:\n" + suggested
    )
    return {
        "name": "claude-status-line",
        "ok": False,
        "detail": repair,
        "severity": "warn",
        "path": "CLAUDE.md",
        "repair": repair,
        "suggested_text": suggested,
        "safe_to_share": True,
    }


def _legacy_campaigns_check(repo: Path) -> dict[str, Any]:
    """Detect legacy `campaigns/` records as drift from the canonical `pushes/` shape.

    Per the push primitive decision, ``pushes/`` is the canonical engine
    primitive. ``campaigns/`` records remain as compatibility reads but new
    coordinated work should land in ``pushes/``. This check warns when a repo
    has any legacy campaign records so the operator can preview the migration.
    """
    campaigns_dir = repo / "campaigns"
    if not campaigns_dir.is_dir():
        return {
            "name": "legacy-campaigns",
            "ok": True,
            "detail": "no legacy campaigns/ records",
            "severity": "ok",
        }

    plan = migrate_mod.plan_campaigns_to_pushes(repo)
    legacy_records: list[str] = []
    ambiguous_files: list[str] = []
    blocker_paths: list[str] = []

    for move in plan.get("moves", []):
        from_path = str(move["from"])
        legacy_records.append(f"{from_path}/campaign.md")
        ambiguous_files.extend(str(path) for path in move.get("review_inside_folder", []))

    for ambiguous in plan.get("ambiguous", []):
        ambiguous_files.append(str(ambiguous["from"]))

    for blocker in plan.get("blockers", []):
        from_path = str(blocker["from"])
        blocker_paths.append(from_path)
        record = repo / from_path / "campaign.md"
        if record.is_file():
            legacy_records.append(f"{from_path}/campaign.md")

    legacy_records = sorted(set(legacy_records))
    ambiguous_files = sorted(set(ambiguous_files))
    blocker_paths = sorted(set(blocker_paths))

    total = len(legacy_records) + len(ambiguous_files) + len(blocker_paths)
    if total == 0:
        # Empty campaigns/ folder (e.g. just a .gitkeep). No drift to warn.
        return {
            "name": "legacy-campaigns",
            "ok": True,
            "detail": "campaigns/ folder is empty",
            "severity": "ok",
        }

    parts: list[str] = []
    if legacy_records:
        parts.append(
            f"{len(legacy_records)} legacy campaign record(s) found. "
            "Main Branch now writes pushes/. Run "
            "`mb migrate campaigns --plan` to preview a safe move."
        )
    if ambiguous_files:
        parts.append(
            f"{len(ambiguous_files)} ambiguous path(s) under campaigns/ that may "
            "belong in pushes/, documents/, or stay in place; "
            "review with `mb migrate campaigns --plan`."
        )
    if blocker_paths:
        parts.append(
            f"{len(blocker_paths)} blocker(s) under campaigns/ require operator input "
            "before migration can be planned."
        )

    return {
        "name": "legacy-campaigns",
        "ok": False,
        "detail": " ".join(parts),
        "severity": "warn",
        "legacy_records": legacy_records,
        "ambiguous_files": ambiguous_files,
        "blockers": blocker_paths,
    }


def _schema_version_check(repo: Path) -> dict[str, Any]:
    current = read_schema_version(repo)
    future_blocker = schema_write_blocker(repo)
    if future_blocker:
        return {
            "name": "schema-version",
            "ok": False,
            "detail": future_blocker,
            "severity": "error",
        }
    pending = pending_migrations(repo)
    if pending:
        names = ", ".join(info.name for info, _module in pending)
        return {
            "name": "schema-version",
            "ok": False,
            "detail": (
                f"schema {current}; pending migration(s): {names}. "
                "Run `mb migrate --check` before `mb migrate --apply`."
            ),
            "severity": "warn",
        }
    if current == "unknown":
        return {
            "name": "schema-version",
            "ok": False,
            "detail": "schema version unknown; run `mb migrate status` from the repo root.",
            "severity": "warn",
        }
    return {
        "name": "schema-version",
        "ok": True,
        "detail": f"schema {current} (latest {LATEST_SCHEMA_VERSION})",
    }


def _missing_gitignore_entries(repo: Path) -> list[str]:
    entries = _read_gitignore_entries(repo)

    def covered(entry: str) -> bool:
        if entry in entries:
            return True
        return any(parent.endswith("/") and entry.startswith(parent) for parent in entries)

    return [entry for entry in LOCAL_GITIGNORE_ENTRIES if not covered(entry)]


def _tracked_local_state_paths(repo: Path) -> list[str]:
    tracked: list[str] = []
    for rel in LOCAL_STATE_PATHS:
        result = _run_git(repo, ["ls-files", "--error-unmatch", rel])
        if result["ok"]:
            tracked.append(rel)
    return tracked


def _untrack_local_state_path(repo: Path, rel: str) -> dict[str, Any]:
    path = repo / rel
    result = _run_git(repo, ["rm", "--cached", "--", rel])
    return {
        "path": rel,
        "ok": bool(result["ok"]),
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exists_on_disk": path.exists() or path.is_symlink(),
    }


def _local_state_summary(repo: Path) -> dict[str, Any]:
    local = [
        {"path": rel, "exists": (repo / rel).exists() or (repo / rel).is_symlink()}
        for rel in LOCAL_STATE_PATHS
    ]
    durable = [
        {"path": rel, "exists": (repo / rel).exists() or (repo / rel).is_symlink()}
        for rel in DURABLE_MB_PATHS
    ]
    missing_gitignore = [
        item["path"]
        for item in local
        if item["exists"] and item["path"] in _missing_gitignore_entries(repo)
    ]
    tracked = _tracked_local_state_paths(repo)
    problem = gitignore_problem(repo)
    return {
        "state": "warn" if problem or missing_gitignore or tracked else "ok",
        "summary": problem
        or (
            f"{len(missing_gitignore)} local state path(s) need gitignore coverage"
            if missing_gitignore
            else f"{len(tracked)} local state path(s) are still tracked"
            if tracked
            else "local operational state is separated from durable markers"
        ),
        "local": local,
        "durable": durable,
        "missing_gitignore": missing_gitignore,
        "tracked": tracked,
    }


def _legacy_reference_state(repo: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for rel, expected_target in REFERENCE_COMPAT_LINKS.items():
        path = repo / rel
        if not path.exists() and not path.is_symlink():
            checks.append(
                {
                    "path": rel,
                    "state": "ok",
                    "summary": "absent",
                    "kind": "absent",
                }
            )
            continue
        if path.is_symlink():
            target = path.readlink().as_posix()
            exists = path.exists()
            if target == expected_target and exists:
                state = "info"
                summary = f"compatibility link -> {target}"
                kind = "compat-link"
            elif not exists:
                state = "warn"
                summary = f"broken symlink -> {target}"
                kind = "broken-link"
            else:
                state = "warn"
                summary = f"unexpected symlink -> {target}"
                kind = "unexpected-link"
            checks.append({"path": rel, "state": state, "summary": summary, "kind": kind})
            continue
        if path.is_dir():
            files = [
                child.relative_to(repo).as_posix()
                for child in path.rglob("*")
                if child.is_file() and not child.is_symlink()
            ]
            canonical_rel = expected_target.removeprefix("../")
            canonical = repo / canonical_rel
            state = "warn"
            kind = "legacy-content"
            if canonical.exists():
                summary = (
                    f"{len(files)} legacy file(s) remain alongside {canonical_rel}; "
                    "check for split truth before migrating"
                )
                kind = "split-truth"
            else:
                summary = f"{len(files)} legacy file(s) can be reviewed by `mb migrate --check`"
            checks.append(
                {
                    "path": rel,
                    "state": state,
                    "summary": summary,
                    "kind": kind,
                    "files": files,
                }
            )
            continue
        checks.append(
            {
                "path": rel,
                "state": "error",
                "summary": "exists but is neither a directory nor a symlink",
                "kind": "unexpected-file",
            }
        )
    return {
        "state": _max_state([str(item["state"]) for item in checks]),
        "checks": checks,
    }


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _read_markdown_frontmatter(path: Path) -> dict[str, Any]:
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


def _flatten_yaml_keys(data: dict[str, Any], *, prefix: str = "") -> list[str]:
    keys: list[str] = []
    for key, value in data.items():
        key_text = str(key)
        path = f"{prefix}.{key_text}" if prefix else key_text
        if isinstance(value, dict) and value:
            keys.extend(_flatten_yaml_keys(value, prefix=path))
        else:
            keys.append(path)
    return keys


def _legacy_vip_key_classification(key: str) -> dict[str, str]:
    parts = key.split(".")
    root = parts[0] if parts else key

    if key == "current_offer":
        return {
            "family": "current_offer",
            "classification": "local-session-state",
            "destination": (
                "Use an explicit per-run offer choice, status/start routing, or a future "
                "Main Branch session-state contract; do not treat `.vip/local.yaml` as canonical."
            ),
            "action": "manual_review",
        }
    if root in {"default_repo", "recent_repos", "user", "media", "last_seen_version", "vip_path"}:
        return {
            "family": f"{root}.*" if len(parts) > 1 else root,
            "classification": "machine-local-preference",
            "destination": (
                "Keep only in machine-local runtime config if still useful; never move into "
                "tracked business files."
            ),
            "action": "keep_local_or_delete",
        }
    if root == "session":
        return {
            "family": "session.*",
            "classification": "machine-local-session-state",
            "destination": "Keep as runtime-local preference/session state if retained.",
            "action": "keep_local_or_delete",
        }
    if root in {"business_type", "business_name", "offer_structure", "skool_url"} or root.endswith(
        "_url"
    ):
        return {
            "family": root,
            "classification": "durable-business-truth",
            "destination": (
                "Review manually and move still-current, non-private facts into `core/`, "
                "`core/operations/`, or onboarding state."
            ),
            "action": "manual_move_if_current",
        }
    if root == "tools":
        return {
            "family": "tools.*",
            "classification": "stale-runtime-snapshot",
            "destination": "Prefer current `mb connect`, `mb status`, and runtime facts.",
            "action": "delete_after_review",
        }
    if root == "mcps":
        return {
            "family": "mcps.*",
            "classification": "provider-readiness-hint",
            "destination": (
                "Move only durable, non-secret requirements to generated `CLAUDE.md`, "
                "`core/operations/`, or provider docs; keep credentials local."
            ),
            "action": "manual_review",
        }
    if root == "infrastructure":
        return {
            "family": "infrastructure.*",
            "classification": "provider-or-infra-hint",
            "destination": (
                "Classify manually. Non-secret provider identifiers may belong in operation "
                "or provider notes; secrets and account-private details stay local."
            ),
            "action": "manual_review",
        }
    if root in {"content", "skills"}:
        return {
            "family": f"{root}.*",
            "classification": "legacy-skill-default",
            "destination": "Use explicit skill inputs or documented workflow defaults, not `.vip`.",
            "action": "manual_review",
        }
    if root in {"clients", "client_repos", "child_repos", "repos"}:
        return {
            "family": f"{root}.*",
            "classification": "repo-topology-hint",
            "destination": (
                "Review manually before moving to topology docs, graph links, or provider-safe "
                "notes; sanitize client/private paths."
            ),
            "action": "manual_review",
        }
    if root == "reference_structure":
        return {
            "family": "reference_structure.*",
            "classification": "stale-legacy-layout",
            "destination": (
                "Use `mb doctor`, `mb migrate --check`, and current `core/` layout facts."
            ),
            "action": "delete_after_review",
        }
    if root in {"paths", "path_config"}:
        return {
            "family": f"{root}.*",
            "classification": "legacy-compatibility-fallback",
            "destination": "Prefer current repo layout and `mb` path resolution.",
            "action": "manual_review",
        }
    return {
        "family": f"{root}.*" if len(parts) > 1 else root,
        "classification": "manual-review",
        "destination": (
            "Inspect manually. Do not move raw values into durable files until privacy and "
            "current relevance are clear."
        ),
        "action": "manual_review",
    }


def _legacy_vip_audit_state(repo: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for rel in LEGACY_VIP_AUDIT_PATHS:
        path = repo / rel
        if not path.exists() and not path.is_symlink():
            checks.append(
                {
                    "name": rel,
                    "state": "ok",
                    "summary": "absent",
                    "kind": "absent",
                    "entries": [],
                    "deletion": {
                        "safe": False,
                        "reason": "file is absent",
                    },
                }
            )
            continue
        if path.is_symlink():
            checks.append(
                {
                    "name": rel,
                    "state": "warn",
                    "summary": "legacy `.vip` YAML is a symlink; manual review required",
                    "kind": "legacy-vip-yaml",
                    "entries": [],
                    "deletion": {
                        "safe": False,
                        "reason": "symlink target may be machine-local or private",
                    },
                }
            )
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            checks.append(
                {
                    "name": rel,
                    "state": "warn",
                    "summary": "legacy `.vip` YAML exists but could not be parsed",
                    "kind": "legacy-vip-yaml",
                    "parse_error": type(exc).__name__,
                    "entries": [],
                    "deletion": {
                        "safe": False,
                        "reason": "parse before deleting or migrating",
                    },
                }
            )
            continue
        if not isinstance(raw, dict):
            checks.append(
                {
                    "name": rel,
                    "state": "warn",
                    "summary": "legacy `.vip` YAML is not a mapping; manual review required",
                    "kind": "legacy-vip-yaml",
                    "entries": [],
                    "deletion": {
                        "safe": False,
                        "reason": "unexpected YAML shape",
                    },
                }
            )
            continue

        entries = [
            {
                "key": key,
                **_legacy_vip_key_classification(key),
                "value_included": False,
            }
            for key in sorted(_flatten_yaml_keys(raw))
        ]
        actions = {str(entry["action"]) for entry in entries}
        manual_count = sum(1 for entry in entries if str(entry["action"]).startswith("manual"))
        local_count = sum(
            1 for entry in entries if str(entry["classification"]).startswith("machine-local")
        )
        stale_count = sum(1 for entry in entries if entry["action"] == "delete_after_review")
        safe_to_delete = bool(entries) and not any(
            action in actions for action in {"manual_review", "manual_move_if_current"}
        )
        if not entries:
            deletion = {
                "safe": True,
                "reason": "file has no keys; delete after confirming no runtime still expects it",
            }
        elif safe_to_delete:
            deletion = {
                "safe": True,
                "reason": (
                    "only local/session/stale fallback keys were found; delete after reviewing "
                    "that no active runtime depends on them"
                ),
            }
        else:
            deletion = {
                "safe": False,
                "reason": (
                    "manual-review or durable-business keys remain; classify and move only "
                    "still-current, non-private facts first"
                ),
            }
        checks.append(
            {
                "name": rel,
                "state": "warn",
                "summary": (
                    f"{len(entries)} legacy key(s): {manual_count} manual review, "
                    f"{local_count} local/session, {stale_count} stale/delete"
                ),
                "kind": "legacy-vip-yaml",
                "entries": entries,
                "deletion": deletion,
            }
        )
    return {
        "state": _max_state([str(item["state"]) for item in checks]),
        "summary": (
            "legacy `.vip` config/state needs review"
            if any(item["state"] != "ok" for item in checks)
            else "no legacy `.vip` config/state files found"
        ),
        "checks": checks,
    }


def _offer_topology_state(repo: Path) -> dict[str, Any]:
    """Return migration guidance for active-offer state and multi-offer drift."""
    checks: list[dict[str, Any]] = []
    offer_records: list[dict[str, Any]] = []
    active_offers: list[str] = []

    for rel in LEGACY_VIP_LOCAL_STATE_PATHS:
        path = repo / rel
        if not path.exists() and not path.is_symlink():
            checks.append(
                {
                    "name": rel,
                    "state": "ok",
                    "summary": "absent",
                    "kind": "absent",
                }
            )
            continue
        data = _read_yaml_mapping(path)
        current_offer = str(data.get("current_offer") or "").strip()
        current_offer_present = bool(current_offer and current_offer != "null")
        if current_offer_present:
            active_offers.append(current_offer)
        checks.append(
            {
                "name": rel,
                "state": "warn",
                "summary": (
                    "legacy repo-local session offer state; read as fallback, "
                    "but do not let skills write it silently"
                ),
                "kind": "legacy-vip-local-state",
                "current_offer_present": current_offer_present,
                "value_included": False,
            }
        )

    offers_dir = repo / "core" / "offers"
    if offers_dir.is_dir():
        for offer_file in sorted(offers_dir.glob("*/offer.md")):
            folder_slug = offer_file.parent.name
            meta = _read_markdown_frontmatter(offer_file)
            declared_slug = str(meta.get("slug") or "").strip()
            record = {
                "path": _rel(repo, offer_file),
                "folder_slug": folder_slug,
                "declared_slug": declared_slug,
                "status": str(meta.get("status") or "").strip(),
            }
            offer_records.append(record)
            if declared_slug and declared_slug != folder_slug:
                checks.append(
                    {
                        "name": _rel(repo, offer_file),
                        "state": "warn",
                        "summary": (
                            f"folder slug `{folder_slug}` differs from frontmatter "
                            f"slug `{declared_slug}`; review before renaming or routing"
                        ),
                        "kind": "offer-slug-drift",
                        **record,
                    }
                )

    existing_folders = {str(record["folder_slug"]) for record in offer_records}
    for active_offer in active_offers:
        if active_offer not in existing_folders:
            checks.append(
                {
                    "name": "active-offer-target",
                    "state": "warn",
                    "summary": (
                        "legacy active-offer state has no matching per-offer file "
                        "under core/offers/"
                    ),
                    "kind": "missing-active-offer",
                    "value_included": False,
                }
            )

    brand_offer = repo / "core" / "offer.md"
    brand_meta = _read_markdown_frontmatter(brand_offer) if brand_offer.is_file() else {}
    brand_slug = str(brand_meta.get("slug") or "").strip()
    if active_offers and len(offer_records) > 1 and brand_offer.is_file():
        checks.append(
            {
                "name": "multi-offer-context",
                "state": "warn",
                "summary": (
                    f"legacy active offer `{active_offers[0]}` exists alongside "
                    f"brand-level core/offer.md and {len(offer_records)} per-offer "
                    "files; confirm brand-level vs offer-specific scope before writing"
                ),
                "kind": "multi-offer-review",
                "current_offer_present": True,
                "value_included": False,
                "brand_offer": "core/offer.md",
                "offers": [record["path"] for record in offer_records],
            }
        )
    if brand_slug and brand_slug in existing_folders:
        checks.append(
            {
                "name": "core/offer.md",
                "state": "warn",
                "summary": (
                    f"brand-level core/offer.md declares slug `{brand_slug}`, which "
                    "also exists as a per-offer folder; review split truth"
                ),
                "kind": "brand-offer-slug-overlap",
                "brand_slug": brand_slug,
            }
        )

    if not checks:
        checks.append(
            {
                "name": "core/offers",
                "state": "ok",
                "summary": "no multi-offer topology guidance needed",
                "kind": "absent",
            }
        )

    return {
        "state": _max_state([str(item["state"]) for item in checks]),
        "checks": checks,
        "offers": offer_records,
    }


def _legacy_claude_symlinks(repo: Path) -> dict[str, Any]:
    root = engine_mod.engine_root()
    active_root = root or Path("/")
    findings: list[dict[str, Any]] = []
    for rel_dir in LEGACY_CLAUDE_LINK_DIRS:
        directory = repo / rel_dir
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            if not entry.is_symlink():
                continue
            raw_target = entry.readlink()
            target = raw_target
            if not target.is_absolute():
                target = entry.parent / target
            target_text = str(target)
            target_parts = {part.lower() for part in Path(target_text).parts}
            raw_parts = {part.lower() for part in Path(str(raw_target)).parts}
            clone_named = bool((target_parts | raw_parts) & {"mb-vip", "mainbranch"})
            try:
                inside_active_root = target.resolve(strict=True).is_relative_to(
                    active_root.resolve(strict=True)
                )
            except (FileNotFoundError, OSError):
                inside_active_root = False
            stale = (
                False
                if inside_active_root
                else engine_mod.is_stale_engine_path(target_text, active_root)
                or (
                    engine_mod.looks_like_missing_legacy_engine_path(str(raw_target))
                    or engine_mod.looks_like_missing_legacy_engine_path(target_text)
                    or clone_named
                )
            )
            if stale:
                state = "warn"
                safe = True
                summary = "stale Main Branch clone-path symlink can be moved to backup"
            else:
                state = "info"
                safe = False
                summary = "third-party or user-authored symlink; inspect manually"
            findings.append(
                {
                    "path": _rel(repo, entry),
                    "target": str(raw_target),
                    "resolved_target": target_text,
                    "state": state,
                    "safe_to_repair": safe,
                    "summary": summary,
                }
            )
    return {
        "state": _max_state([str(item["state"]) for item in findings]),
        "findings": findings,
        "repairable": sum(1 for item in findings if item["safe_to_repair"]),
    }


def _repair_legacy_claude_symlinks(repo: Path, findings: list[dict[str, Any]]) -> dict[str, Any]:
    repairable = [item for item in findings if item.get("safe_to_repair")]
    if not repairable:
        return {"ok": True, "moved": [], "backup_dir": "", "errors": []}
    backup_dir = repo / ".mb" / "backups" / f"doctor-repair-{_utc_stamp()}" / "claude-links"
    moved: list[dict[str, str]] = []
    errors: list[str] = []
    for item in repairable:
        source = repo / str(item["path"])
        dest = backup_dir / str(item["path"])
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(dest))
            moved.append(
                {
                    "path": str(item["path"]),
                    "target": str(item["target"]),
                    "backup_path": _rel(repo, dest),
                }
            )
        except OSError as exc:
            errors.append(f"{item['path']}: {exc}")
    if moved:
        manifest = backup_dir / "manifest.json"
        manifest.write_text(json.dumps({"moved": moved}, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": not errors,
        "moved": moved,
        "backup_dir": _rel(repo, backup_dir) if moved else "",
        "errors": errors,
    }


def _migration_drift_from_checks(
    checks: list[dict[str, Any]],
    repo: Path,
) -> dict[str, Any] | None:
    check = next((item for item in checks if item.get("name") == "migration-drift"), None)
    if check is None:
        return None
    findings = check.get("findings", [])
    if not isinstance(findings, list):
        findings = []
    summary = check.get("summary")
    if not isinstance(summary, dict):
        summary = {
            "warnings": len(findings),
            "categories": sorted({str(item.get("category")) for item in findings}),
        }
    return {
        "ok": not findings,
        "repo": str(repo),
        "findings": findings,
        "summary": summary,
    }


def _topology_drift_state(repo: Path) -> dict[str, Any]:
    """Surface repo topology drift evidence for ``mb doctor repair --plan``.

    Reads the topology view via :func:`mb.topology.collect` and maps its
    findings into the doctor section vocabulary (``ok``/``info``/``warn``/
    ``error``). Preview-only: this helper never renames, deletes, or rewrites
    topology files or descriptors.
    """
    payload = topology_mod.collect(str(repo))
    findings = payload.get("findings") or []
    summary = payload.get("summary") or {}

    severity_to_state = {"info": "info", "warn": "warn", "error": "error"}
    checks: list[dict[str, Any]] = []
    for finding in findings:
        severity = str(finding.get("severity") or "info")
        checks.append(
            {
                "name": str(finding.get("code") or ""),
                "state": severity_to_state.get(severity, "info"),
                "summary": str(finding.get("summary") or ""),
                "path": str(finding.get("path") or ""),
                "detail": str(finding.get("detail") or ""),
                "repair_command": str(finding.get("repair_command") or ""),
                "safe_to_share": True,
            }
        )

    registry_found = bool(summary.get("registry_found"))
    registry_ok = bool(summary.get("registry_ok"))
    descriptor_found = bool(summary.get("descriptor_found"))
    warnings = int(summary.get("warnings", 0) or 0)
    errors = int(summary.get("errors", 0) or 0)

    codes_by_severity: dict[str, list[str]] = {}
    for finding in findings:
        severity = str(finding.get("severity") or "info")
        code = str(finding.get("code") or "")
        if not code:
            continue
        codes_by_severity.setdefault(severity, []).append(code)
    warn_codes = sorted(set(codes_by_severity.get("warn", [])))
    error_codes = sorted(set(codes_by_severity.get("error", [])))

    if errors:
        state = "error"
        section_summary = (
            f"{errors} topology drift error(s): {', '.join(error_codes)}"
            if error_codes
            else f"{errors} topology drift error(s)"
        )
    elif warnings:
        state = "warn"
        section_summary = (
            f"{warnings} topology drift warning(s): {', '.join(warn_codes)}"
            if warn_codes
            else f"{warnings} topology drift warning(s)"
        )
    elif not registry_found and not descriptor_found:
        state = "info"
        section_summary = "no topology registry yet (optional)"
    elif registry_found and registry_ok:
        state = "ok"
        section_summary = "topology registry parses; no drift detected"
    else:
        state = "info"
        section_summary = "no topology registry yet (optional)"

    return {
        "state": state,
        "summary": section_summary,
        "checks": checks,
        "findings": findings,
        "child_repo_count": int(summary.get("child_repo_count", 0) or 0),
        "restricted_repo_count": int(summary.get("restricted_repo_count", 0) or 0),
        "summary_payload": {
            "registry_found": registry_found,
            "registry_ok": registry_ok,
            "descriptor_found": descriptor_found,
            "child_repo_count": int(summary.get("child_repo_count", 0) or 0),
            "restricted_repo_count": int(summary.get("restricted_repo_count", 0) or 0),
            "warnings": warnings,
            "errors": errors,
        },
    }


def _validation_summary(
    repo: Path,
    *,
    migration_drift_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        report = validate_mod.run(
            str(repo),
            cross_refs=True,
            migration_drift_report=migration_drift_report,
        )
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        return {
            "ok": False,
            "state": "error",
            "summary": f"validation failed to run: {exc}",
            "report": {},
        }
    summary = report.get("summary", {})
    errors = int(summary.get("errors", 0) or 0)
    warnings = int(summary.get("warnings", 0) or 0)
    categories = report.get("validation_categories") or {}
    top_category = categories.get("top_category")
    state = "error" if errors else ("warn" if warnings else "ok")
    return {
        "ok": report["ok"],
        "state": state,
        "summary": (
            f"{errors} error(s), {warnings} warning(s)"
            + (f"; top category: {top_category}" if top_category else "")
        ),
        "report": {
            "summary": summary,
            "validation_categories": report.get("validation_categories", {}),
            "files": len(report.get("files", [])),
            "legacy_repair": report.get("legacy_repair"),
            "cross_refs": {
                "enabled": report.get("cross_refs", {}).get("enabled", False),
                "warnings": len(report.get("cross_refs", {}).get("warnings", [])),
                "orphan_offers": len(report.get("cross_refs", {}).get("orphan_offers", [])),
            },
            "migration_drift": report.get("migration_drift", {}).get("summary", {}),
        },
    }


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _rel(repo: Path, path: Path) -> str:
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return str(path)


def _max_state(states: list[str]) -> str:
    if not states:
        return "ok"
    return max(states, key=lambda state: STATE_ORDER.get(state, 3))


def _read_gitignore_entries(repo: Path) -> set[str]:
    gitignore = repo / ".gitignore"
    if gitignore_problem(repo) or not gitignore.exists():
        return set()
    try:
        return {line.strip() for line in gitignore.read_text(encoding="utf-8").splitlines()}
    except OSError:
        return set()


def _run_git(repo: Path, args: list[str]) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return {"ok": False, "stdout": "", "stderr": "git unavailable"}
    return {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "returncode": proc.returncode,
    }
