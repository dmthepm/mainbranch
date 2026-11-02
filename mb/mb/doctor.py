"""``mb doctor`` — check the health of a Main Branch repo.

Checks Claude Code on PATH, gh auth status, network reachability,
``librsvg`` for ``tool-og-render``, and walks ``core/finance/`` looking
for cloud-backed paths. Cloud-backup detection triggers educational
triage per the master decision: prints a banner and offers
``mb educational anti-cloud-backup`` for the long-form rationale.
"""

from __future__ import annotations

import copy
import os
import re
import shutil
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mb import checkpoint as checkpoint_mod
from mb import codex as codex_mod
from mb import connect as connect_mod
from mb import engine as engine_mod
from mb import graph as graph_mod
from mb import migrate as migrate_mod
from mb import migration_lint
from mb import onboard as onboard_mod
from mb import related_links as related_links_mod
from mb import roles as roles_mod
from mb import spine as spine_mod
from mb import topology as topology_mod
from mb.doctor_checks import _FENCE_OPEN_RE as _FENCE_OPEN_RE
from mb.doctor_checks import _OLD_STATUS_LINE_RE as _OLD_STATUS_LINE_RE
from mb.doctor_checks import CLOUD_PREFIXES as CLOUD_PREFIXES
from mb.doctor_checks import DURABLE_MB_PATHS as DURABLE_MB_PATHS
from mb.doctor_checks import LEGACY_CLAUDE_LINK_DIRS as LEGACY_CLAUDE_LINK_DIRS
from mb.doctor_checks import LEGACY_VIP_AUDIT_PATHS as LEGACY_VIP_AUDIT_PATHS
from mb.doctor_checks import LEGACY_VIP_LOCAL_STATE_PATHS as LEGACY_VIP_LOCAL_STATE_PATHS
from mb.doctor_checks import LOCAL_GITIGNORE_ENTRIES as LOCAL_GITIGNORE_ENTRIES
from mb.doctor_checks import LOCAL_STATE_PATHS as LOCAL_STATE_PATHS
from mb.doctor_checks import REFERENCE_COMPAT_LINKS as REFERENCE_COMPAT_LINKS
from mb.doctor_checks import STATE_ORDER as STATE_ORDER
from mb.doctor_checks import _detect_cloud_paths as _detect_cloud_paths
from mb.doctor_checks import _flatten_yaml_keys as _flatten_yaml_keys
from mb.doctor_checks import _legacy_campaigns_check as _legacy_campaigns_check
from mb.doctor_checks import _legacy_claude_symlinks as _legacy_claude_symlinks
from mb.doctor_checks import _legacy_reference_state as _legacy_reference_state
from mb.doctor_checks import _legacy_vip_audit_state as _legacy_vip_audit_state
from mb.doctor_checks import _legacy_vip_key_classification as _legacy_vip_key_classification
from mb.doctor_checks import _local_state_summary as _local_state_summary
from mb.doctor_checks import _max_state as _max_state
from mb.doctor_checks import _migration_drift_from_checks as _migration_drift_from_checks
from mb.doctor_checks import _missing_gitignore_entries as _missing_gitignore_entries
from mb.doctor_checks import _offer_topology_state as _offer_topology_state
from mb.doctor_checks import _old_status_line_check as _old_status_line_check
from mb.doctor_checks import _outside_fences as _outside_fences
from mb.doctor_checks import _read_gitignore_entries as _read_gitignore_entries
from mb.doctor_checks import _read_markdown_frontmatter as _read_markdown_frontmatter
from mb.doctor_checks import _read_yaml_mapping as _read_yaml_mapping
from mb.doctor_checks import _rel as _rel
from mb.doctor_checks import _repair_legacy_claude_symlinks as _repair_legacy_claude_symlinks
from mb.doctor_checks import _repo_layout_check as _repo_layout_check
from mb.doctor_checks import _run_git as _run_git
from mb.doctor_checks import _schema_version_check as _schema_version_check
from mb.doctor_checks import _topology_drift_state as _topology_drift_state
from mb.doctor_checks import _tracked_local_state_paths as _tracked_local_state_paths
from mb.doctor_checks import _untrack_local_state_path as _untrack_local_state_path
from mb.doctor_checks import _utc_stamp as _utc_stamp
from mb.doctor_checks import _validation_summary as _validation_summary
from mb.doctor_commands import _BACKTICKED_MB as _BACKTICKED_MB
from mb.doctor_commands import _COMMAND_KEYS as _COMMAND_KEYS
from mb.doctor_commands import _COMMAND_LIST_KEYS as _COMMAND_LIST_KEYS
from mb.doctor_commands import _REDIRECT_WORD as _REDIRECT_WORD
from mb.doctor_commands import _REPO_FLAG_COMMANDS as _REPO_FLAG_COMMANDS
from mb.doctor_commands import _REPO_POSITIONAL_COMMANDS as _REPO_POSITIONAL_COMMANDS
from mb.doctor_commands import _RUN_TAIL as _RUN_TAIL
from mb.doctor_commands import _command_segments as _command_segments
from mb.doctor_commands import _qualify_command as _qualify_command
from mb.doctor_commands import _qualify_field as _qualify_field
from mb.doctor_commands import _qualify_prose as _qualify_prose
from mb.doctor_commands import _qualify_report as _qualify_report
from mb.doctor_commands import _qualify_run_commands as _qualify_run_commands
from mb.doctor_commands import _qualify_segment as _qualify_segment
from mb.doctor_commands import _qualify_validation_report as _qualify_validation_report
from mb.doctor_commands import _shell_words as _shell_words
from mb.doctor_commands import _unsupported_shell_syntax as _unsupported_shell_syntax
from mb.doctor_render import render_repair as render_repair
from mb.durable import atomic_write_text
from mb.engine import install_mode, link_status
from mb.freshness import (
    MODE_NEUTRAL_UPDATE_TEXT,
    checked_release_version,
    compare_versions,
    format_update_alert,
    package_update_status,
)
from mb.gitignore import gitignore_problem
from mb.skill_validate import run_all as validate_all_skills

REPAIR_SCHEMA = "mb.doctor.repair"
REPAIR_SCHEMA_VERSION = 1
AUDIENCE_VALUES = frozenset({"mechanical", "operator_decision", "informational"})
AGENT_REPAIR_SCOPES = frozenset({"claude", "codex"})
CLAUDE_ACTION_IDS = frozenset({"skill-link", "skill-shadow-repair", "legacy-claude-link-repair"})
CODEX_ACTION_IDS = frozenset({"codex-agents-md", "codex-global-skill"})
AGENT_ACTION_IDS = CLAUDE_ACTION_IDS | CODEX_ACTION_IDS
AGENT_SECTION_IDS = frozenset({"claude-wiring", "codex-wiring", "git"})


def _derive_audience(mode: str, safe_to_apply: bool) -> str:
    """Classify a repair action for operator-facing routing.

    See ``decisions/2026-05-11-operator-facing-gitops-and-migration-planning.md``
    for the contract. ``audience`` is a routing signal; ``safe_to_apply`` is the
    safety gate and stays authoritative.
    """
    if mode == "read":
        return "informational"
    if mode == "manual":
        return "operator_decision"
    if safe_to_apply:
        return "mechanical"
    return "operator_decision"


def _which(name: str) -> str:
    """Return path of binary or empty string."""
    return shutil.which(name) or ""


def _state_from_check(check: dict[str, Any]) -> str:
    if check.get("ok"):
        severity = str(check.get("severity") or "ok")
        return severity if severity in {"info"} else "ok"
    severity = str(check.get("severity") or "error")
    return severity if severity in {"info", "warn", "error"} else "error"


def _append_unique_lines(path: Path, entries: list[str]) -> bool:
    if gitignore_problem(path.parent):
        return False
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    existing_lines = set(existing.splitlines())
    missing = [entry for entry in entries if entry not in existing_lines]
    if not missing:
        return False
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    atomic_write_text(path, existing + prefix + "\n".join(missing) + "\n")
    return True


def _git_summary(repo: Path) -> dict[str, Any]:
    inside = _run_git(repo, ["rev-parse", "--is-inside-work-tree"])
    if not inside["ok"] or inside["stdout"] != "true":
        return {
            "inside_work_tree": False,
            "branch": "",
            "dirty": False,
            "changed_files": [],
            "state": "warn",
            "summary": "not a git work tree; initialize git before reviewable repairs",
        }
    branch = _run_git(repo, ["branch", "--show-current"])
    porcelain = _run_git(repo, ["status", "--short"])
    changed = [line for line in porcelain["stdout"].splitlines() if line]
    state = "warn" if changed else "ok"
    return {
        "inside_work_tree": True,
        "branch": branch["stdout"],
        "dirty": bool(changed),
        "changed_files": changed,
        "state": state,
        "summary": (
            f"{len(changed)} changed file(s); review before committing repair work"
            if changed
            else f"clean branch {branch['stdout'] or '(detached)'}"
        ),
    }


def _action(
    *,
    id: str,
    title: str,
    state: str,
    mode: str,
    command: str,
    safe_to_apply: bool,
    reason: str,
    writes: list[str] | None = None,
    applied: bool = False,
    result: dict[str, Any] | None = None,
    audience: str | None = None,
    operator_summary: str = "",
) -> dict[str, Any]:
    resolved_audience = (
        audience if audience in AUDIENCE_VALUES else _derive_audience(mode, safe_to_apply)
    )
    return {
        "id": id,
        "title": title,
        "state": state,
        "mode": mode,
        "command": command,
        "safe_to_apply": safe_to_apply,
        "reason": reason,
        "audience": resolved_audience,
        "operator_summary": operator_summary or reason or title,
        "writes": writes or [],
        "applied": applied,
        "result": result or {},
    }


def _attach_operations(
    action: dict[str, Any], target: Path, operations: list[dict[str, Any]]
) -> None:
    """Record every destination an apply touches and which ones git tracks (#1012)."""
    action["operations"] = engine_mod.public_operations(operations)
    action["tracked_changes"] = engine_mod.consent_destinations(target, operations)


def _section(
    id: str,
    title: str,
    state: str,
    summary: str,
    *,
    checks: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "title": title,
        "state": state,
        "summary": summary,
        "checks": checks or [],
        "actions": actions or [],
    }


DOSSIER_RELATIVE_PATH = Path("core") / "operations" / "agent-access-dossier.md"
_DOSSIER_VERIFY_RE = re.compile(r"^mb connect test ([a-z0-9][a-z0-9-]{1,30})$")
# Why `mb connect test` did not record its check, by `not_recorded_reason`.
# Any other reason gets a plain " (not recorded)", never a guessed cause.
_NOT_RECORDED_TAILS = {
    "connect_yaml_tracked": " (not recorded: .mb/connect.yaml is tracked by git)",
    "user_scope_read_only": " (not recorded: the user-scope connect file is read-only)",
    "user_scope_write_failed": " (not recorded: the user-scope connect file could not be written)",
}
# `user_scope_write_failed` also covers a user-scope file that cannot be read
# or parsed; `exit_follows_check` marks that case, so it is not called a write failure.
_USER_SCOPE_UNREADABLE_TAIL = (
    " (not recorded: the user-scope connect file is unreadable or invalid)"
)


def _dossier_provider_rows(path: Path) -> list[tuple[str, str]]:
    """Parse (provider, verify) pairs from the dossier's provider table."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[tuple[str, str]] = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("| provider |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not stripped.startswith("|"):
            in_table = False
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or set(cells[0]) <= {"-", ":", " "}:
            continue
        if len(cells) >= 2 and cells[0]:
            rows.append((cells[0], cells[-1]))
    return rows


def _dossier_verify_section(repo: Path) -> dict[str, Any]:
    """Verify the agent-access dossier's provider table.

    Only mb-owned verify commands run, and never through a shell: the
    provider id is parsed out of the row text and `mb connect test` is
    called in-process. Anything else in the verify column is surfaced for
    the operator to run — repo-listed commands are untrusted input.
    """
    path = repo / DOSSIER_RELATIVE_PATH
    if not path.is_file():
        return _section(
            "capability-dossier",
            "Agent Access Dossier",
            "info",
            (
                "no core/operations/agent-access-dossier.md — mb-setup scaffolds "
                "the capability map for new businesses"
            ),
        )
    rows = _dossier_provider_rows(path)
    checks: list[dict[str, Any]] = []
    if not rows:
        checks.append(
            {
                "name": "provider-table",
                "state": "warn",
                "summary": "dossier present but no rows found in the provider table",
            }
        )
    for provider_label, verify in rows:
        command = verify.strip().strip("`").strip()
        match = _DOSSIER_VERIFY_RE.fullmatch(command)
        if match:
            provider_id = match.group(1)
            try:
                result = connect_mod.test_provider(provider_id, repo)
            except ValueError as exc:
                checks.append(
                    {"name": provider_label, "state": "warn", "summary": f"verify failed: {exc}"}
                )
                continue
            ok = bool(result.get("ok"))
            raw_status = result.get("status")
            status: dict[str, Any] = raw_status if isinstance(raw_status, dict) else {}
            summary_tail = ""
            not_recorded_reason = str(result.get("not_recorded_reason") or "")
            if not_recorded_reason:
                # The check was not recorded, so the stored status is stale:
                # show what the check itself found, and why it was not recorded.
                raw_validation = result.get("validation")
                validation = raw_validation if isinstance(raw_validation, dict) else {}
                checked = str(result.get("state") or validation.get("state") or "")
                state_text = connect_mod.state_label(checked or ("ready" if ok else "failed"))
                summary_tail = _NOT_RECORDED_TAILS.get(not_recorded_reason, " (not recorded)")
                if not_recorded_reason == "user_scope_write_failed" and result.get(
                    "exit_follows_check"
                ):
                    summary_tail = _USER_SCOPE_UNREADABLE_TAIL
            else:
                state_text = connect_mod.state_label(
                    str(status.get("state") or ("ready" if ok else "failed"))
                )
            checks.append(
                {
                    "name": provider_label,
                    "state": "ok" if ok else "warn",
                    "summary": f"`mb connect test {provider_id}` → {state_text}{summary_tail}",
                }
            )
        else:
            checks.append(
                {
                    "name": provider_label,
                    "state": "info",
                    "summary": f"operator-run verify (not auto-executed): {command[:80]}",
                }
            )
    return _section(
        "capability-dossier",
        "Agent Access Dossier",
        _max_state([str(check["state"]) for check in checks]) if checks else "ok",
        "capability map verification — mb-owned verify commands only",
        checks=checks,
    )


def _spine_section(repo: Path) -> dict[str, Any]:
    """Grade the declared contact+event spine position.

    Honest grading per decisions/2026-06-12-spine-levels.md: report what
    the engine can verify (declaration present, store queryable through
    mb connect) and what the operator declared (timeline gaps, revisit
    trigger) — never infer a maturity score the facts can't support.
    """
    shown = spine_mod.show(repo)
    if not shown.get("declared"):
        return _section(
            "contact-event-spine",
            "Contact+Event Spine",
            "info",
            (
                "no spine declaration — run "
                f"`mb spine declare{engine_mod.repo_flag(repo)} --store <provider>` "
                "(or `--store none --intentional`) so agents read the position "
                "from facts instead of guessing"
            ),
        )
    declaration = shown.get("declaration") or {}
    store = str(declaration.get("store") or "")
    if store == "none":
        revisit = str(declaration.get("revisit_trigger") or "")
        return _section(
            "contact-event-spine",
            "Contact+Event Spine",
            "ok",
            "none, on purpose — a declared product stance"
            + (f"; revisit when: {revisit}" if revisit else ""),
        )
    checks: list[dict[str, Any]] = []
    lenses = declaration.get("lenses") or []
    checks.append(
        {
            "name": "declaration",
            "state": "ok",
            "summary": f"spine: {store}" + (f", {len(lenses)} fan-out lens(es)" if lenses else ""),
        }
    )
    try:
        status = connect_mod.status_provider(store, repo)
    except ValueError:
        checks.append(
            {
                "name": "agent-queryability",
                "state": "info",
                "summary": (
                    f"{store!r} is not an mb connect provider — queryability "
                    "unverified; connect it (or `mb connect <id> --custom`) so "
                    "the operator's agent can read the spine from the terminal"
                ),
            }
        )
    else:
        state_text = connect_mod.state_label(str(status.get("state") or ""))
        if status.get("ok") or str(status.get("state")) in {
            "unvalidated",
            "ready",
            connect_mod.UNVERIFIED_STATE,
            connect_mod.NOT_CHECKED_STATE,
        }:
            checks.append(
                {
                    "name": "agent-queryability",
                    "state": "ok",
                    "summary": f"{store} credentialed via mb connect (state: {state_text})",
                }
            )
        else:
            # Prefer the provider's own guidance. Falling straight to a generic
            # reconnect told operators to replace credentials that were fine.
            repair_hint = str(
                status.get("repair_command") or status.get("repair") or f"mb connect {store}"
            )
            checks.append(
                {
                    "name": "agent-queryability",
                    "state": "warn",
                    "summary": (
                        f"{store} declared as the spine but not agent-queryable "
                        f"(state: {state_text}); repair: {repair_hint}"
                    ),
                }
            )
    gaps = [str(gap) for gap in declaration.get("known_gaps") or []]
    if gaps:
        checks.append(
            {
                "name": "timeline-completeness",
                "state": "info",
                "summary": (
                    "declared gap(s) the spine does not hold: "
                    + "; ".join(gaps[:3])
                    + " — an owned event log alongside the store is the "
                    "augmented path (see decisions/2026-06-12-spine-levels.md)"
                ),
            }
        )
    else:
        checks.append(
            {
                "name": "timeline-completeness",
                "state": "ok",
                "summary": "no declared timeline gaps",
            }
        )
    revisit = str(declaration.get("revisit_trigger") or "")
    checks.append(
        {
            "name": "revisit-trigger",
            "state": "ok" if revisit else "info",
            "summary": f"revisit when: {revisit}"
            if revisit
            else "no revisit trigger declared — name the question that should reopen this",
        }
    )
    return _section(
        "contact-event-spine",
        "Contact+Event Spine",
        _max_state([str(check["state"]) for check in checks]),
        "declared contact+event spine position and what the engine can verify",
        checks=checks,
    )


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _action_ids_for_scope(only: str = "", *, all_agents: bool = False) -> set[str]:
    if all_agents:
        return set(AGENT_ACTION_IDS)
    if only == "claude":
        return set(CLAUDE_ACTION_IDS)
    if only == "codex":
        return set(CODEX_ACTION_IDS)
    return set()


def _agent_scope_label(only: str = "", *, all_agents: bool = False) -> str:
    if all_agents:
        return "all-agents"
    return only or "default"


def _agent_scope_filter(
    sections: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    *,
    only: str = "",
    all_agents: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    action_ids = _action_ids_for_scope(only, all_agents=all_agents)
    if not action_ids:
        return sections, actions
    section_ids = set(AGENT_SECTION_IDS)
    if only == "claude":
        section_ids = {"claude-wiring", "git"}
    elif only == "codex":
        section_ids = {"codex-wiring", "git"}
    filtered_sections = [section for section in sections if str(section.get("id")) in section_ids]
    filtered_actions = [action for action in actions if str(action.get("id")) in action_ids]
    return filtered_sections, filtered_actions


def _agent_surfaces(
    sections: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    *,
    only: str = "",
    all_agents: bool = False,
) -> dict[str, Any]:
    by_section = {str(section.get("id")): section for section in sections}
    by_action = {str(action.get("id")): action for action in actions}

    def surface(
        *,
        key: str,
        section_id: str,
        action_ids: frozenset[str],
        label: str,
        repair_command: str,
    ) -> dict[str, Any]:
        section = by_section.get(section_id, {})
        # Sorted: a frozenset's order follows the hash seed (#1100).
        surface_actions = [
            by_action[action_id] for action_id in sorted(action_ids) if action_id in by_action
        ]
        return {
            "id": key,
            "label": label,
            "state": str(section.get("state") or "info"),
            "detected": bool(section),
            "repair_command": repair_command,
            "checks": [
                {
                    "name": str(check.get("name") or ""),
                    "state": str(check.get("state") or "info"),
                    "summary": str(check.get("summary") or ""),
                }
                for check in section.get("checks", [])
            ],
            "planned_actions": [str(action.get("id")) for action in surface_actions],
            "touched_files": _unique(
                [str(path) for action in surface_actions for path in action.get("writes", [])]
            ),
        }

    return {
        "scope": _agent_scope_label(only, all_agents=all_agents),
        "scope_choices": [
            "mb doctor repair --plan --only claude",
            "mb doctor repair --plan --only codex",
            "mb doctor repair --plan --all-agents",
        ],
        "apply_choices": [
            "mb doctor repair --apply --only claude",
            "mb doctor repair --apply --only codex",
            "mb doctor repair --apply --all-agents",
        ],
        "surfaces": [
            surface(
                key="claude",
                section_id="claude-wiring",
                action_ids=CLAUDE_ACTION_IDS,
                label="Claude Code project-local skills",
                repair_command="mb doctor repair --apply --only claude",
            ),
            surface(
                key="codex",
                section_id="codex-wiring",
                action_ids=CODEX_ACTION_IDS,
                label="Codex global mb-* skills and repo AGENTS.md",
                repair_command="mb doctor repair --apply --only codex",
            ),
        ],
    }


def _repair_receipt(
    applied_actions: list[dict[str, Any]],
    *,
    only: str = "",
    all_agents: bool = False,
) -> dict[str, Any]:
    touched_files = _unique(
        [str(path) for action in applied_actions for path in action.get("writes", [])]
    )
    installed_skills: list[str] = []
    for action in applied_actions:
        if str(action.get("id")) != "codex-global-skill":
            continue
        result = action.get("result", {})
        if not isinstance(result, dict):
            continue
        status = result.get("status", {})
        if isinstance(status, dict):
            installed_skills.extend(str(name) for name in status.get("required_skills", []))
        source = result.get("source", {})
        if isinstance(source, dict) and not installed_skills:
            installed_skills.extend(
                str(path).removesuffix("/SKILL.md") for path in source.get("relative_paths", [])
            )
    scope = _agent_scope_label(only, all_agents=all_agents)
    skipped_surfaces: list[str] = []
    if scope == "default":
        skipped_surfaces = [
            "claude: run mb doctor repair --apply --only claude",
            "codex: run mb doctor repair --apply --only codex",
        ]
    elif scope == "claude":
        skipped_surfaces = ["codex"]
    elif scope == "codex":
        skipped_surfaces = ["claude"]

    return {
        "scope": scope,
        "installed_skills": _unique(installed_skills),
        "touched_files": touched_files,
        "skipped_surfaces": skipped_surfaces,
        "warnings": [
            str(action.get("reason") or "")
            for action in applied_actions
            if str(action.get("state")) in {"warn", "error"}
        ],
        "restart_notes": [
            "Open a fresh Codex thread after Codex global skills change.",
            "Restart Claude Code if it was already open while project-local skill links changed.",
        ],
        "rollback": [
            "Review touched files with git diff before committing.",
            "Use git restore for repo-local generated files you do not want to keep.",
            "Remove generated Codex skill folders from the Codex skills root if needed.",
        ],
        "uninstall": [
            "Claude: remove project-local .claude/skills links and settings entries after review.",
            "Codex: remove Main Branch folders under the Codex skills root after review.",
        ],
    }


def _net() -> tuple[bool, str]:
    """Best-effort: open a TCP connection to api.github.com:443."""
    try:
        with socket.create_connection(("api.github.com", 443), timeout=3):
            return True, "reachable"
    except OSError:
        return False, "no route to api.github.com"


def _rsvg() -> tuple[bool, str]:
    """Check rsvg-convert presence (tool-og-render primary path)."""
    if _which("rsvg-convert"):
        return True, "rsvg-convert on PATH"
    return False, "rsvg-convert missing (brew install librsvg)"


def _mainbranch_version_check(update: dict[str, Any]) -> dict[str, Any]:
    mode = install_mode()
    severity = str(update["severity"])
    latest = str(update["latest"])
    installed = str(update["installed"])

    if mode in {"clone", "source"} and severity not in {"required", "recommended"}:
        return {
            "name": "mainbranch-version",
            "ok": True,
            "detail": f"{update['installed']} ({mode} mode)",
            "severity": "info",
        }

    if severity == "unknown":
        return {
            "name": "mainbranch-version",
            "ok": True,
            "detail": f"{installed}; could not check PyPI for latest",
            "severity": "info",
        }

    if severity == "required":
        return {
            "name": "mainbranch-version",
            "ok": False,
            "detail": (
                f"installed {installed}; minimum supported is {update['minimum_supported']}. "
                + (f"Run `{update['command']}`." if update["command"] else MODE_NEUTRAL_UPDATE_TEXT)
            ),
            "severity": "error",
        }

    # #1043: version_key drops pre-release markers, so 0.6.3rc1 compared
    # equal to 0.6.3 here and the final release was missed. Compare with
    # the PEP 440 ordering used by `mb update`, guarded so an unparseable
    # latest never reads as an update.
    checked_latest = checked_release_version(latest)
    if severity == "recommended" or (
        checked_latest and compare_versions(checked_latest, installed) > 0
    ):
        return {
            "name": "mainbranch-version",
            "ok": False,
            "detail": (
                f"installed {installed}, latest is {latest}. "
                f"Run `{update['command']}` when you can."
            ),
            "severity": "warn",
        }
    return {
        "name": "mainbranch-version",
        "ok": True,
        "detail": f"{installed} is current" if latest else installed,
    }


def _graph_summary(repo: Path) -> dict[str, Any]:
    try:
        index = graph_mod.build_index(str(repo))
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        return {
            "ok": False,
            "state": "warn",
            "summary": f"graph summary failed to run: {exc}",
            "report": {},
        }
    unresolved = sum(1 for node in index.get("nodes", []) if node.get("type") == "wikilink")
    state = "warn" if unresolved else "ok"
    summary = index.get("summary", {})
    return {
        "ok": unresolved == 0,
        "state": state,
        "summary": (
            f"{summary.get('files', 0)} file(s), {summary.get('edges', 0)} edge(s), "
            f"{unresolved} unresolved wikilink(s)"
        ),
        "report": {"summary": summary, "unresolved_wikilinks": unresolved},
    }


def run(path: str, *, qualify: bool = True) -> dict[str, Any]:
    """Run all checks, return a structured report dict.

    With `qualify`, every suggested command names the repo when it is not the
    current folder (#1083). `repair_plan` passes False: its `raw` blocks stay
    verbatim copies and its own report pass qualifies the command fields.
    """
    repo = Path(path).resolve()
    checks: list[dict[str, Any]] = []
    update = package_update_status(repo)

    cc_path = _which("claude")
    checks.append(
        {
            "name": "claude-code",
            "ok": bool(cc_path),
            "detail": cc_path
            or (
                "claude CLI not on PATH. Main Branch runs as a Claude Code plugin "
                "in the Claude Desktop app too — install it (+ -> Plugins -> "
                "dmthepm/mainbranch), or for terminal use install the CLI "
                "(https://claude.ai/install) then "
                "`claude plugin marketplace add dmthepm/mainbranch`."
            ),
        }
    )

    codex_readiness = codex_mod.readiness(repo)
    codex_executable = codex_readiness["executable"]
    codex_instructions = codex_readiness["instructions"]
    codex_global_skill = codex_readiness["global_skill"]
    checks.append(
        {
            "name": "codex-cli",
            "ok": bool(codex_executable["found"]),
            "detail": codex_executable["path"] or "codex not on PATH",
            "severity": "info",
            "repair": codex_executable["repair"],
            "safe_to_share": True,
        }
    )
    checks.append(
        {
            "name": "codex-agents-md",
            "ok": bool(codex_instructions["ok"]),
            "detail": (
                "AGENTS.md and Main Branch Codex skills are current and point Codex "
                "to mb facts, lifecycle routes, and workflow inventory"
            )
            if codex_instructions["ok"]
            else (
                "Codex AGENTS.md or generated guidance is missing, stale, or missing "
                "required mb fact commands or lifecycle discovery guidance. "
                f"Run `mb doctor repair{engine_mod.repo_flag(repo)} --plan`, review, "
                f"then `mb doctor repair{engine_mod.repo_flag(repo)} --apply`."
            ),
            "severity": "ok" if codex_instructions["ok"] else "warn",
            "repair": codex_instructions["repair"],
            "safe_to_share": True,
            "status": codex_instructions,
        }
    )
    checks.append(
        {
            "name": "codex-global-skill",
            "ok": bool(codex_global_skill["ok"]),
            "detail": codex_global_skill["summary"],
            "severity": "ok"
            if codex_global_skill["ok"]
            else ("warn" if codex_executable["found"] and codex_instructions["ok"] else "info"),
            "repair": codex_global_skill["repair"],
            "repair_command": codex_global_skill["repair_command"],
            "safe_to_share": True,
            "status": codex_global_skill,
        }
    )

    gh_context = connect_mod.github_context(repo)
    integration_status = connect_mod.status_all(repo, github=gh_context)
    checks.append(
        {
            "name": "github-context",
            "ok": bool(gh_context["ok"]),
            "detail": gh_context["summary"],
            "severity": "warn",
            "state": gh_context["state"],
            "repair": gh_context["repair"],
            "repair_command": gh_context["repair_command"],
            "safe_to_share": True,
        }
    )

    net_ok, net_detail = _net()
    checks.append({"name": "network", "ok": net_ok, "detail": net_detail})

    rsvg_ok, rsvg_detail = _rsvg()
    checks.append(
        {
            "name": "librsvg",
            "ok": rsvg_ok,
            "detail": rsvg_detail,
            "severity": "warn" if not rsvg_ok else "ok",
        }
    )

    repo_ok = repo.exists() and os.access(repo, os.W_OK)
    checks.append(
        {
            "name": "repo-writable",
            "ok": repo_ok,
            "detail": str(repo),
        }
    )

    wiring = link_status(repo)
    plugin = wiring.get("plugin", {})
    source_warnings = plugin.get("warnings", [])
    checks.append(
        {
            "name": "plugin-source",
            "ok": not source_warnings,
            "severity": "warn" if source_warnings else "info",
            "detail": " ".join(source_warnings) or "No legacy Main Branch plugin source detected.",
            "plugin": plugin,
        }
    )
    if roles_mod.has_cards(repo):
        role_wiring = roles_mod.wiring(repo, bool(plugin.get("wired")))
        role_problem = bool(role_wiring["invalid"]) or not role_wiring["hook_wired"]
        if role_wiring["invalid"]:
            role_detail = (
                "Invalid role card(s): "
                + ", ".join(role_wiring["invalid"])
                + ". Run `mb role check`."
            )
        elif not role_wiring["hook_wired"] and role_wiring["plugin_wired"]:
            role_detail = (
                "Role hook not verified: the Main Branch plugin is enabled, but doctor cannot "
                "see whether its version has the role hook. Update the plugin, or add "
                "`mb role hook` as a SessionStart hook in .claude/settings.json."
            )
        elif not role_wiring["hook_wired"]:
            role_detail = (
                "Role cards exist but no SessionStart hook is wired, so sessions are "
                "not told their role. Enable the Main Branch plugin (version with role "
                "cards) or add `mb role hook` as a SessionStart hook."
            )
        else:
            role_detail = (
                f"{role_wiring['cards']} role card(s) valid; SessionStart hook wired. "
                + (
                    "A role is selected in this shell."
                    if role_wiring["role_selected"]
                    else "Launch agents with MB_ROLE=<name>; none is selected in this shell."
                )
            )
        checks.append(
            {
                "name": "role-cards",
                "ok": not role_problem,
                "severity": "warn" if role_problem else "info",
                "detail": role_detail,
                "roles": role_wiring,
            }
        )
    wiring_ok = bool(wiring["ok"])
    shadow_summary = wiring.get("shadow_report", {}).get("summary", {})
    active_shadows = int(shadow_summary.get("active_shadows", 0) or 0)
    legacy_globals = int(shadow_summary.get("legacy_globals", 0) or 0)
    checks.append(
        {
            "name": "skill-wiring",
            "ok": wiring_ok,
            "detail": (
                f"mb-start skill linked via {wiring['engine_root']}"
                if wiring_ok
                else (
                    "Missing Main Branch start wiring for Claude Code. Run "
                    f"`mb doctor repair{engine_mod.repo_flag(repo)} --plan`, then "
                    f"`mb doctor repair{engine_mod.repo_flag(repo)} --apply`."
                )
            ),
            "severity": "ok"
            if wiring_ok
            else ("warn" if not (repo / "CLAUDE.md").exists() else "error"),
        }
    )
    if wiring_ok:
        missing_links = engine_mod.missing_bundled_links(repo)
        checks.append(
            {
                "name": "skill-links-current",
                "ok": not missing_links,
                "detail": (
                    "All bundled skills are linked."
                    if not missing_links
                    else (
                        "Missing bundled skill links: " + ", ".join(missing_links) + ". "
                        f"Run `mb skill link{engine_mod.repo_flag(repo)}`."
                    )
                ),
                "severity": "warn" if missing_links else "ok",
            }
        )
    if active_shadows or legacy_globals:
        checks.append(
            {
                "name": "skill-shadowing",
                "ok": active_shadows == 0,
                "detail": (
                    f"{active_shadows} active personal skill shadow(s), "
                    f"{legacy_globals} legacy personal skill trap(s). "
                    f"Run `mb skill repair{engine_mod.repo_flag(repo)}` for details."
                ),
                "severity": "error" if active_shadows else "warn",
            }
        )

    checks.append(_mainbranch_version_check(update))
    skill_validation = validate_all_skills()
    skill_summary = skill_validation["summary"]
    checks.append(
        {
            "name": "bundled-skills",
            "ok": bool(skill_validation["ok"]),
            "detail": (
                f"{skill_summary['passed']}/{skill_summary['skills']} bundled skill(s) validate"
                if skill_validation["ok"]
                else (
                    f"{skill_summary['failed']} bundled skill(s) failed validation; "
                    "run `mb skill validate --all`."
                )
            ),
            "severity": "ok" if skill_validation["ok"] else "error",
        }
    )
    checks.append(_repo_layout_check(repo))
    checks.append(_schema_version_check(repo))
    checks.append(_legacy_campaigns_check(repo))
    drift = migration_lint.run(repo)
    checks.append(
        {
            "name": "migration-drift",
            "ok": bool(drift["ok"]),
            "detail": (
                "no migration-shape drift found"
                if drift["ok"]
                else (
                    f"{drift['summary']['warnings']} migration drift warning(s): "
                    + ", ".join(drift["summary"]["categories"])
                )
            ),
            "severity": "ok" if drift["ok"] else "warn",
            "findings": drift["findings"],
            "summary": drift["summary"],
            "safe_to_share": True,
        }
    )
    old_status_line = _old_status_line_check(repo)
    if old_status_line is not None:
        checks.append(old_status_line)
    checkpoint_hook = checkpoint_mod.hook_status(repo)
    hook_state = str(checkpoint_hook.get("state"))
    checks.append(
        {
            "name": "checkpoint-hook",
            "ok": bool(checkpoint_hook["ok"]),
            "detail": str(checkpoint_hook["summary"]),
            "severity": "ok"
            if checkpoint_hook["ok"]
            else "info"
            if hook_state == "engine_repo"
            else "warn",
            "state": hook_state,
            "repair": str(checkpoint_hook.get("summary") or ""),
            "repair_command": str(checkpoint_hook.get("repair_command") or ""),
            "safe_to_share": True,
        }
    )
    checks.append(connect_mod.doctor_check(repo, status=integration_status))
    onboarding = onboard_mod.onboarding_status(repo)
    onboarding_summary = onboarding["summary"]
    checks.append(
        {
            "name": "onboarding-progress",
            "ok": onboarding_summary["status"] == "ready",
            "detail": (
                "core onboarding complete"
                if onboarding_summary["status"] == "ready"
                else (
                    f"{onboarding_summary['completed_required']}/"
                    f"{onboarding_summary['total_required']} required steps complete; "
                    f"run `mb onboard status{engine_mod.repo_flag(repo)}`."
                )
            ),
            "severity": "warn",
        }
    )

    cloud_hits = _detect_cloud_paths(repo)
    cloud_ok = not cloud_hits
    checks.append(
        {
            "name": "anti-cloud-backup",
            "ok": cloud_ok,
            "detail": (
                "core/finance/ looks cloud-backed: "
                + ", ".join(cloud_hits)
                + ". Run `mb educational anti-cloud-backup` for context."
            )
            if cloud_hits
            else "core/finance/ not under iCloud / GDrive / Dropbox / OneDrive",
            "severity": "warn" if cloud_hits else "ok",
        }
    )

    skool_token = bool(os.environ.get("SKOOL_TOKEN"))
    checks.append(
        {
            "name": "skool-token",
            "ok": True,  # informational only
            "detail": "set" if skool_token else "unset (optional)",
            "severity": "info",
        }
    )

    # ``ok`` overall: every check must pass UNLESS its severity is warn/info.
    overall = all(c["ok"] or c.get("severity") in {"warn", "info"} for c in checks)
    hard_fail = any(not c["ok"] and c.get("severity") not in {"warn", "info"} for c in checks)

    if qualify:
        update = copy.deepcopy(update)  # the update object is shared with `mb update`
        _qualify_run_commands(checks, update, repo)

    return {
        "ok": overall and not hard_fail,
        "checks": checks,
        "repo": str(repo),
        "integrations": integration_status,
        "onboarding": onboarding,
        "update": update,
        "python": sys.version.split()[0],
    }


def _not_business_folder_guard(target: Path, *, mode: str = "plan") -> dict[str, Any] | None:
    """Refuse doctor writes (and noisy scans) outside a business folder.

    Field-proven failure (cold-eyes install test): pre-onboard doctor in an
    arbitrary cwd emitted seven folder-shaped warnings, validated stray
    markdown, and repair --apply would have scaffolded .claude/, AGENTS.md,
    and .gitignore into whatever directory the agent happened to be in.
    """
    markers = (
        "CLAUDE.md",
        "AGENTS.md",
        "core",
        "decisions",
        "research",
        "bets",
        "pushes",
        ".mb",
        ".mainbranch",
        # Legacy shapes are doctor's migration patients, not junk dirs.
        "reference",
        ".vip",
        "campaigns",
    )
    # Partially built or broken business folders are exactly what doctor
    # repairs — refuse only a directory with no business markers at all.
    # Hub or child: the descriptor docs promise doctor reports topology drift
    # inside child repos too, so the classifier accepts both.
    kind = topology_mod.classify_repo(target)["kind"]
    if kind in {"hub", "child"} or any((target / m).exists() for m in markers):
        return None
    message = (
        "this is not a Main Branch business folder — run `mb onboard` to "
        "create one (doctor checks and repairs run inside it)"
    )
    # Mirror the full repair payload contract so --json consumers and
    # render_repair never hit a guard-shaped hole.
    return {
        "schema": REPAIR_SCHEMA,
        "schema_version": REPAIR_SCHEMA_VERSION,
        "ok": True,
        "mode": mode,
        "only": "",
        "all_agents": False,
        # The guard refuses before any write, so even --apply stays read-only.
        "read_only": True,
        "repo": str(target),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "guard": "not_business_folder",
        "summary": {
            "ok": 0,
            "info": 1,
            "warn": 0,
            "error": 0,
            "actions": 0,
            "write_actions": 0,
            "safe_apply_actions": 0,
        },
        "plan_interpretation": {
            "state": "not_business_folder",
            "summary": message,
            "read_only_plan": True,
            "nonzero_exit_can_still_include_usable_plan": False,
            "safe_to_share": True,
        },
        "sections": [
            _section(
                "business-folder",
                "Business Folder",
                "info",
                message,
            )
        ],
        "actions": [],
        "operator_actions": [],
        "applied_actions": [],
        "post_apply": {
            "structural_verification": "mb onboard",
            "validation_frontmatter_debt": "mb onboard",
            "runtime_smoke_required": message,
            "git_review": [],
        },
        "safe_to_share": True,
    }


def codex_repair_actions(
    target: Path, codex_status: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The Codex repair actions and operator actions for `repair_plan`, in order.

    Shared with `mb update --check` (#1106), so the check plans exactly what
    `mb doctor repair --plan --only codex` would. `codex_status` is a
    `codex.readiness` report already read for `target`.
    """
    codex_instruction_status = codex_status.get("instructions") or {}
    codex_global_skill = codex_status.get("global_skill") or {}
    codex_actions: list[dict[str, Any]] = []
    codex_operator_actions: list[dict[str, Any]] = []
    if not codex_instruction_status.get("ok", False):
        agents_plan = codex_mod.agents_md_plan(target)
        agents_operations = agents_plan["operations"]
        # #1052: a repair that refuses, or leaves a person's files behind, is a
        # step for a person with a manual repair, never an agent repair.
        agents_operator_action = codex_mod.agents_md_operator_action(agents_plan, repo=target)
        reason = (
            "AGENTS.md is the repo-local Codex entrypoint; repair writes current "
            "fact grounding, lifecycle routing, and approval boundaries, and removes "
            "transitional repo-local plugin copies"
        )
        if agents_operator_action is not None:
            reason = f"{reason}. {agents_operator_action['reason']}"
        action = _action(
            id="codex-agents-md",
            title="Refresh Codex AGENTS.md instructions",
            state="warn",
            mode="write",
            command="mb doctor repair --apply --only codex",
            safe_to_apply=agents_operator_action is None,
            reason=reason,
            writes=(
                []
                if agents_plan["refused"]
                else [
                    "AGENTS.md",
                    *[str(item["rel"]) for item in agents_operations if item["op"] != "write"],
                ]
            ),
        )
        action["refused"] = agents_plan["refused"]
        action["kept"] = agents_plan["kept"]
        # #1056: an explicit apply does exactly this, even while safe_to_apply is false.
        action["on_apply"] = codex_mod.agents_md_apply_effect(agents_plan)
        _attach_operations(action, target, agents_operations)
        codex_actions.append(action)
        if agents_operator_action is not None:
            codex_operator_actions.append(agents_operator_action)
    # A file in an old global folder that is not proven to be Main Branch's
    # stays; a person decides what to do with it.
    global_operator_action = codex_mod.global_skill_operator_action(codex_global_skill, repo=target)
    if global_operator_action is not None:
        codex_operator_actions.append(global_operator_action)
    if not codex_global_skill.get("ok", True):
        action = _action(
            id="codex-global-skill",
            title="Install the global Main Branch Codex skill bundle",
            state="warn",
            mode="write",
            command="mb doctor repair --apply --only codex",
            safe_to_apply=global_operator_action is None,
            reason=(
                "Codex uses a global Main Branch skill bundle for supported and "
                "discoverable mb-* routes"
            ),
            writes=[
                str(codex_mod.global_skill_source_root()),
            ],
            result=codex_global_skill,
        )
        # #1056, #1062: files not proven to be Main Branch's in old global folders stay.
        action["kept"] = list(codex_global_skill.get("kept", []))
        action["on_apply"] = codex_mod.global_skill_apply_effect(codex_global_skill)
        _attach_operations(action, target, codex_mod.global_skill_operations())
        codex_actions.append(action)
    return codex_actions, codex_operator_actions


def repair_plan(
    repo: str | Path = ".",
    *,
    mode: str = "plan",
    applied_actions: list[dict[str, Any]] | None = None,
    only: str = "",
    all_agents: bool = False,
) -> dict[str, Any]:
    """Build the guided reconciliation plan without writing repo status markers."""
    if only and only not in AGENT_REPAIR_SCOPES:
        raise ValueError(f"unknown repair scope: {only}")
    if only and all_agents:
        raise ValueError("--only cannot be combined with --all-agents")
    target = Path(repo).expanduser().resolve()
    guard = _not_business_folder_guard(target, mode=mode)
    if guard is not None:
        return guard
    doctor_report = run(str(target), qualify=False)
    actions: list[dict[str, Any]] = []
    operator_actions: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []

    update = doctor_report.get("update", {})
    install_checks = [
        {
            "name": check["name"],
            "state": _state_from_check(check),
            "summary": _qualify_prose(check["detail"], target),
        }
        for check in doctor_report["checks"]
        if check["name"]
        in {"mainbranch-version", "claude-code", "github-context", "network", "librsvg"}
    ]
    if str(update.get("severity")) in {"required", "recommended"}:
        actions.append(
            _action(
                id="mainbranch-update",
                title="Update Main Branch install",
                state="error" if update.get("severity") == "required" else "warn",
                mode="write",
                command=str(update.get("command") or "mb update"),
                safe_to_apply=False,
                reason="package updates are explicit operator actions outside doctor repair",
            )
        )
    sections.append(
        _section(
            "install",
            "Install And Environment",
            _max_state([str(item["state"]) for item in install_checks]),
            "Main Branch install, runtime tools, GitHub, network, and optional render tooling",
            checks=install_checks,
        )
    )

    migration = migrate_mod.check(target, include_diff=False)
    migration_drift = _migration_drift_from_checks(
        doctor_report["checks"], target
    ) or migration_lint.run(target)
    reference_state = _legacy_reference_state(target)
    offer_topology = _offer_topology_state(target)
    legacy_vip = _legacy_vip_audit_state(target)
    legacy_campaigns_check = next(
        (check for check in doctor_report["checks"] if check["name"] == "legacy-campaigns"),
        None,
    )
    layout_checks = [
        {
            "name": check["name"],
            "state": _state_from_check(check),
            "summary": _qualify_prose(check["detail"], target),
        }
        for check in doctor_report["checks"]
        if check["name"] in {"repo-layout", "schema-version", "legacy-campaigns"}
    ]
    layout_checks.extend(
        {
            "name": item["path"],
            "state": item["state"],
            "summary": item["summary"],
            "kind": item["kind"],
        }
        for item in reference_state["checks"]
    )
    if migration.get("plan", {}).get("has_changes") or migration.get("pending"):
        actions.append(
            _action(
                id="migration-preview",
                title="Preview layout migration",
                state="warn",
                mode="read",
                command="mb migrate --repo . --check",
                safe_to_apply=True,
                reason="migration preview is read-only and should be reviewed before apply",
            )
        )
        actions.append(
            _action(
                id="migration-apply",
                title="Apply approved layout migration",
                state="warn",
                mode="write",
                command="mb migrate --repo . --apply",
                safe_to_apply=False,
                reason=(
                    "migration moves user-authored files; run doctor repair with "
                    "`--apply --include-migration` only after reviewing the preview"
                ),
                writes=["core/", "reference/core", "reference/offers", ".mb/schema_version"],
            )
        )
    if legacy_campaigns_check and not legacy_campaigns_check["ok"]:
        actions.append(
            _action(
                id="legacy_campaigns_to_pushes",
                title="Preview campaigns -> pushes migration",
                state="warn",
                mode="read",
                command="mb migrate campaigns --plan",
                safe_to_apply=True,
                reason=(
                    "campaigns/ is legacy compatibility; new coordinated work "
                    "writes to pushes/. Preview the move before applying."
                ),
            )
        )
    sections.append(
        _section(
            "repo-shape",
            "Repo Shape And Migration",
            _max_state([str(item["state"]) for item in layout_checks]),
            f"schema {migration.get('current_version')} -> {migration.get('latest_version')}",
            checks=layout_checks,
        )
    )

    drift_actions: list[dict[str, Any]] = []
    if migration_drift["findings"]:
        action = _action(
            id="migration-drift-review",
            title="Review business repo migration drift",
            state="warn",
            mode="manual",
            command="mb doctor repair --plan --json && mb validate --json",
            safe_to_apply=False,
            reason=(
                "migration drift warnings name stale paths and categories without "
                "copying private file contents; operators should approve moves or "
                "frontmatter repairs explicitly"
            ),
        )
        actions.append(action)
        drift_actions.append(action)
    sections.append(
        _section(
            "migration-drift",
            "Migration Drift Lint",
            "warn" if migration_drift["findings"] else "ok",
            (
                f"{migration_drift['summary']['warnings']} warning(s): "
                + ", ".join(migration_drift["summary"]["categories"])
                if migration_drift["findings"]
                else "no legacy active-write or stale runtime guidance drift found"
            ),
            checks=[
                {
                    "name": str(item["code"]),
                    "state": "warn",
                    "summary": str(item["message"]),
                    "path": str(item["path"]),
                    "category": str(item["category"]),
                    "repair_command": str(item["repair_command"]),
                    "content_included": False,
                }
                for item in migration_drift["findings"]
            ],
            actions=drift_actions,
        )
    )

    topology_drift = _topology_drift_state(target)
    topology_actions: list[dict[str, Any]] = []
    if topology_drift["state"] in {"warn", "error"}:
        action = _action(
            id="topology-drift-review",
            title="Review repo topology drift",
            state=topology_drift["state"],
            mode="manual",
            command="mb status --json --peek && mb validate --json",
            safe_to_apply=False,
            reason=(
                "topology drift names hub/child mismatches, unsafe metadata, "
                "or orphaned descriptors; doctor surfaces evidence but does "
                "not rename, delete, or rewrite repos or descriptors"
            ),
        )
        actions.append(action)
        topology_actions.append(action)
    sections.append(
        _section(
            "topology-drift",
            "Repo Topology Drift",
            topology_drift["state"],
            topology_drift["summary"],
            checks=topology_drift["checks"],
            actions=topology_actions,
        )
    )

    offer_actions: list[dict[str, Any]] = []
    if offer_topology["state"] != "ok":
        action = _action(
            id="offer-topology-review",
            title="Review active-offer and multi-offer migration guidance",
            state=offer_topology["state"],
            mode="manual",
            command="mb status --json --peek && mb validate --cross-refs",
            safe_to_apply=False,
            reason=(
                "active offer, brand offer, and per-offer topology are strategy "
                "choices; doctor surfaces evidence but does not rename or rewrite them"
            ),
        )
        actions.append(action)
        offer_actions.append(action)
    sections.append(
        _section(
            "offer-topology",
            "Offer Topology And Session State",
            offer_topology["state"],
            (
                "operator review needed for active-offer or multi-offer drift"
                if offer_topology["state"] != "ok"
                else "no offer topology migration guidance needed"
            ),
            checks=offer_topology["checks"],
            actions=offer_actions,
        )
    )

    legacy_vip_actions: list[dict[str, Any]] = []
    if legacy_vip["state"] != "ok":
        action = _action(
            id="legacy-vip-audit",
            title="Review legacy .vip YAML config/state",
            state=legacy_vip["state"],
            mode="manual",
            command="mb doctor repair --plan --json",
            safe_to_apply=False,
            reason=(
                ".vip YAML can contain private paths, provider notes, client context, "
                "or stale runtime snapshots; doctor classifies keys but does not copy "
                "raw values or migrate content automatically"
            ),
        )
        actions.append(action)
        legacy_vip_actions.append(action)
    sections.append(
        _section(
            "legacy-vip",
            "Legacy .vip Config And State",
            legacy_vip["state"],
            legacy_vip["summary"],
            checks=legacy_vip["checks"],
            actions=legacy_vip_actions,
        )
    )

    missing_gitignore = _missing_gitignore_entries(target)
    tracked_local_state = _tracked_local_state_paths(target)
    gitignore_problem_text = gitignore_problem(target)
    gitignore_actions: list[dict[str, Any]] = []
    if (missing_gitignore and not gitignore_problem_text) or tracked_local_state:
        action = _action(
            id="gitignore-local-state",
            title=(
                "Untrack Main Branch local state"
                if gitignore_problem_text
                else "Protect Main Branch local state in .gitignore"
            ),
            state="warn",
            mode="write",
            command="mb doctor repair --apply",
            safe_to_apply=True,
            reason=(
                "doctor repair untracks already-committed local state"
                if gitignore_problem_text
                else "these entries are local operational state; doctor repair adds "
                "gitignore coverage and untracks any already-committed local state"
            ),
            writes=([".gitignore"] if not gitignore_problem_text else []) + tracked_local_state,
        )
        actions.append(action)
        gitignore_actions.append(action)
    gitignore_state = (
        "warn" if gitignore_problem_text or missing_gitignore or tracked_local_state else "ok"
    )
    sections.append(
        _section(
            "gitignore",
            "Local State Gitignore",
            gitignore_state,
            gitignore_problem_text
            or (
                f"{len(missing_gitignore)} missing gitignore entrie(s), "
                f"{len(tracked_local_state)} tracked local-state file(s)"
                if missing_gitignore
                else f"{len(tracked_local_state)} tracked local-state file(s)"
                if tracked_local_state
                else "Main Branch local state is ignored"
            ),
            checks=[
                {
                    "name": entry,
                    "state": "warn"
                    if entry in missing_gitignore or entry in tracked_local_state
                    else "ok",
                    "summary": (
                        "tracked; repair will untrack"
                        if entry in tracked_local_state
                        else "missing"
                        if entry in missing_gitignore
                        else "covered"
                    ),
                }
                for entry in LOCAL_GITIGNORE_ENTRIES
            ],
            actions=gitignore_actions,
        )
    )

    checkpoint_hook = checkpoint_mod.hook_status(target)
    checkpoint_state = str(checkpoint_hook.get("state"))
    hook_check_state = (
        "ok"
        if checkpoint_hook.get("ok")
        else "info"
        if checkpoint_state == "engine_repo"
        else "warn"
        if checkpoint_state in {"missing", "broken", "blocked_existing_hook"}
        else "error"
    )
    hook_actions: list[dict[str, Any]] = []
    if checkpoint_state in {"missing", "broken"}:
        action = _action(
            id="checkpoint-hook-install",
            title="Install business checkpoint commit-message hook",
            state="warn",
            mode="write",
            command="mb checkpoint --install-hook",
            safe_to_apply=True,
            reason=(
                "the repo-local commit-msg hook validates manual git commits "
                "against the same business-readable checkpoint contract"
            ),
            writes=[".git/hooks/commit-msg"],
        )
        actions.append(action)
        hook_actions.append(action)
    elif checkpoint_state == "blocked_existing_hook":
        action = _action(
            id="checkpoint-hook-existing",
            title="Review existing commit-message hook before installing checkpoint validation",
            state="warn",
            mode="manual",
            command="review .git/hooks/commit-msg, then run mb checkpoint --install-hook",
            safe_to_apply=False,
            reason=(
                "Main Branch will not overwrite an existing user hook; preserve or "
                "compose it intentionally before installing checkpoint validation"
            ),
            writes=[".git/hooks/commit-msg"],
        )
        actions.append(action)
        hook_actions.append(action)
    sections.append(
        _section(
            "checkpoint-hook",
            "Checkpoint Commit Hook",
            hook_check_state,
            str(checkpoint_hook.get("summary") or "checkpoint hook status unavailable"),
            checks=[
                {
                    "name": "commit-msg",
                    "state": hook_check_state,
                    "summary": str(checkpoint_hook.get("summary") or ""),
                    "hook": str(checkpoint_hook.get("hook") or ""),
                    "repair_command": str(checkpoint_hook.get("repair_command") or ""),
                }
            ],
            actions=hook_actions,
        )
    )

    wiring = link_status(target)
    shadow_report = wiring.get("shadow_report", {})
    legacy_links = _legacy_claude_symlinks(target)
    wiring_checks = [
        {
            "name": "project-local-skills",
            "state": "ok" if wiring.get("ok") else "error",
            "summary": (
                "Claude Code can discover mb-start"
                if wiring.get("ok")
                else str(wiring.get("summary") or "missing Main Branch start wiring")
            ),
            "fallback_commands": wiring.get("fallback_commands", []),
        },
        {
            "name": "personal-skill-shadowing",
            "state": "ok"
            if not int(shadow_report.get("summary", {}).get("findings", 0) or 0)
            else (
                "warn"
                if int(shadow_report.get("summary", {}).get("repairable", 0) or 0)
                else "error"
            ),
            "summary": (
                f"{shadow_report.get('summary', {}).get('findings', 0)} finding(s), "
                f"{shadow_report.get('summary', {}).get('repairable', 0)} repairable"
            ),
        },
        {
            "name": "legacy-claude-reference-links",
            "state": legacy_links["state"],
            "summary": (
                f"{len(legacy_links['findings'])} symlink finding(s), "
                f"{legacy_links['repairable']} repairable"
            ),
        },
    ]
    if not wiring.get("ok"):
        actions.append(
            _action(
                id="skill-link",
                title="Restore Main Branch start wiring for Claude Code",
                state="error",
                mode="write",
                command="mb doctor repair --apply --only claude",
                safe_to_apply=True,
                reason=(
                    "restores project-local Main Branch start wiring so Claude Code "
                    "can discover /mb-start from this repo or worktree"
                ),
                writes=[
                    ".claude/settings.local.json",
                    ".claude/skills/",
                    ".gitignore",
                ],
            )
        )
    if not engine_mod.plugin_wiring_status(target).get("wired"):
        # #1042: the plugin-rail switch writes the tracked `.claude/settings.json`,
        # so it is a step for a person at a terminal, never a repair an agent
        # applies. Report it the way `mb update` does, in `operator_actions`.
        operator_actions.append(engine_mod.plugin_switch_operator_action(target))
    if int(shadow_report.get("summary", {}).get("repairable", 0) or 0):
        actions.append(
            _action(
                id="skill-shadow-repair",
                title="Move stale personal Main Branch skill symlinks to backup",
                state="warn",
                mode="write",
                command="mb doctor repair --apply --only claude",
                safe_to_apply=True,
                reason="only stale or broken Main Branch personal symlinks are moved",
                writes=[str(shadow_report.get("personal_skills_dir") or "~/.claude/skills")],
            )
        )
    if int(legacy_links["repairable"]):
        actions.append(
            _action(
                id="legacy-claude-link-repair",
                title="Move old clone-path lens/reference symlinks to backup",
                state="warn",
                mode="write",
                command="mb doctor repair --apply --only claude",
                safe_to_apply=True,
                reason="only stale Main Branch clone-path symlinks are moved; user files stay put",
                writes=[".claude/lenses/", ".claude/reference/", ".mb/backups/"],
            )
        )
    sections.append(
        _section(
            "claude-wiring",
            "Claude Code Wiring",
            _max_state([str(item["state"]) for item in wiring_checks]),
            "Project-local skills, personal shadowing, and old clone-path symlinks",
            checks=wiring_checks,
        )
    )

    codex_status = codex_mod.readiness(target)
    codex_instruction_status = codex_status["instructions"]
    codex_runtime_status = codex_status["runtime"]
    codex_global_skill = codex_status["global_skill"]
    codex_runtime_relevant = bool(
        codex_status["executable"]["found"] and codex_instruction_status["ok"]
    )
    codex_checks = [
        {
            "name": "codex-cli",
            "state": "ok" if codex_status["executable"]["found"] else "info",
            "summary": codex_status["executable"]["path"] or "codex not on PATH",
        },
        {
            "name": "AGENTS.md",
            "state": "ok" if codex_instruction_status["ok"] else "warn",
            "summary": (
                "Codex AGENTS.md guidance is current and includes mb fact grounding, "
                "lifecycle routes, and workflow inventory"
                if codex_instruction_status["ok"]
                else (
                    "Codex AGENTS.md guidance is missing, stale, or missing mb fact "
                    "grounding or lifecycle discovery guidance"
                )
            ),
            "missing_fact_commands": codex_instruction_status["missing_fact_commands"],
            "missing_lifecycle_guidance": codex_instruction_status["missing_lifecycle_guidance"],
            "lifecycle_discovery_ok": codex_instruction_status["lifecycle_discovery_ok"],
            "guidance_metadata_ok": codex_instruction_status["guidance_metadata_ok"],
            "guidance_schema_ok": codex_instruction_status["guidance_schema_ok"],
            "guidance_template_hash_ok": codex_instruction_status["guidance_template_hash_ok"],
            "guidance_min_mb_ok": codex_instruction_status["guidance_min_mb_ok"],
            "guidance_metadata": codex_instruction_status["guidance_metadata"],
            "expected_guidance_metadata": codex_instruction_status["expected_guidance_metadata"],
            "expected_template_hash": codex_instruction_status["expected_template_hash"],
            "guidance_min_mb": codex_instruction_status["guidance_min_mb"],
            "generated_version_ok": codex_instruction_status["generated_version_ok"],
            "expected_version_marker": codex_instruction_status["expected_version_marker"],
            "skill": codex_instruction_status["skill"],
            "approval_boundary_ok": codex_instruction_status["approval_boundary_ok"],
            "codex_native_ok": codex_instruction_status["codex_native_ok"],
        },
        {
            "name": "codex-runtime-mb",
            "state": (
                "ok"
                if codex_runtime_status["ok"]
                else ("warn" if codex_runtime_relevant else "info")
            ),
            "summary": (
                codex_runtime_status["summary"]
                if codex_runtime_relevant
                else (
                    "Codex runtime mb check waits until Codex CLI is installed "
                    "and adapter files are current."
                )
            ),
            "active_path": codex_runtime_status.get("active_path", ""),
            "active_version": codex_runtime_status.get("active_version", ""),
            "runtime_path": codex_runtime_status.get("path", ""),
            "runtime_version": codex_runtime_status.get("version", ""),
            "repair": codex_runtime_status.get("repair", "") if codex_runtime_relevant else "",
        },
        {
            "name": "codex-global-skill",
            "state": ("ok" if codex_global_skill["ok"] else "warn"),
            "summary": codex_global_skill["summary"],
            "skill_name": codex_global_skill["name"],
            "skill_path": codex_global_skill["path"],
            "skills_root": codex_global_skill["skills_root"],
            "routes": codex_global_skill["routes"],
            "required_skills": codex_global_skill.get("required_skills", []),
            "stale": codex_global_skill["stale"],
            "missing": codex_global_skill["missing"],
            "missing_markers": codex_global_skill["missing_markers"],
            "slash_commands_ready": codex_status.get("slash_commands_ready", False),
            "repair": codex_global_skill["repair"],
            # #1087 item 6: a linked folder that is already current; informational.
            **{
                key: codex_global_skill[key]
                for key in ("linked", "note")
                if key in codex_global_skill
            },
        },
    ]
    codex_actions, codex_operator_actions = codex_repair_actions(target, codex_status)
    actions.extend(codex_actions)
    operator_actions.extend(codex_operator_actions)
    sections.append(
        _section(
            "codex-wiring",
            "Codex Global Skill",
            _max_state([str(item["state"]) for item in codex_checks]),
            (
                "Main Branch global Codex skill, repo guidance, workflow inventory, "
                "and executable readiness"
            ),
            checks=codex_checks,
            actions=codex_actions,
        )
    )

    local_state = _local_state_summary(target)
    sections.append(
        _section(
            "mb-state",
            ".mb State",
            local_state["state"],
            local_state["summary"],
            checks=[
                {
                    "name": item["path"],
                    "state": "info" if item["exists"] else "ok",
                    "summary": "local operational state" if item["exists"] else "absent",
                }
                for item in local_state["local"]
            ]
            + [
                {
                    "name": item["path"],
                    "state": "info" if item["exists"] else "ok",
                    "summary": "durable repo marker" if item["exists"] else "absent",
                }
                for item in local_state["durable"]
            ],
        )
    )

    sections.append(_dossier_verify_section(target))
    sections.append(_spine_section(target))

    validation = _validation_summary(target, migration_drift_report=migration_drift)
    related_links = related_links_mod.plan(target)
    related_actions: list[dict[str, Any]] = []
    if related_links["summary"]["missing_links"]:
        action = _action(
            id="related-links-mirror",
            title="Mirror frontmatter links into Related links",
            state="warn",
            mode="write",
            command="mb doctor repair --apply",
            safe_to_apply=True,
            reason=(
                "frontmatter stays canonical; doctor only adds missing body-level "
                "Markdown links for GitHub, Obsidian, and human browsing"
            ),
            writes=[str(item["path"]) for item in related_links["files"]],
        )
        actions.append(action)
        related_actions.append(action)
    validation_categories = (
        validation.get("report", {}).get("validation_categories", {}).get("by_category", {})
    )
    only_related_link_warnings = set(validation_categories) == {
        related_links_mod.MISSING_RELATED_LINK_MIRROR_CATEGORY
    }
    if validation["state"] != "ok" and not only_related_link_warnings:
        actions.append(
            _action(
                id="validate-frontmatter",
                title="Repair validation and frontmatter debt",
                state=validation["state"],
                mode="manual",
                command="mb validate --json",
                safe_to_apply=False,
                reason="validation failures are user-authored content repairs",
            )
        )
    sections.append(
        _section(
            "validation",
            "Validation And Cross-Refs",
            validation["state"],
            validation["summary"],
            checks=[
                {
                    "name": "mb validate --cross-refs",
                    **validation,
                    "report": _qualify_validation_report(validation.get("report", {}), target),
                }
            ],
        )
    )

    status_line_check = next(
        (check for check in doctor_report["checks"] if check["name"] == "claude-status-line"),
        None,
    )
    if status_line_check is not None:
        status_line_action = _action(
            id="claude-status-line",
            title="Replace the old status line in CLAUDE.md",
            state="warn",
            mode="manual",
            command="mb doctor",
            safe_to_apply=False,
            reason=(
                "CLAUDE.md still gives one status set for every file type; `mb doctor` "
                "prints the replacement lines, and doctor never rewrites CLAUDE.md"
            ),
        )
        actions.append(status_line_action)
        sections.append(
            _section(
                "claude-status-line",
                "CLAUDE.md Status Line",
                "warn",
                "CLAUDE.md still teaches one status set for every file type",
                checks=[
                    {
                        "name": "claude-status-line",
                        "state": "warn",
                        "summary": (
                            "CLAUDE.md gives one status set for every file type; "
                            "`mb doctor` prints the replacement lines"
                        ),
                        "path": "CLAUDE.md",
                        "content_included": False,
                    }
                ],
                actions=[status_line_action],
            )
        )

    sections.append(
        _section(
            "related-links",
            "Related Links Mirrors",
            "warn" if related_links["summary"]["missing_links"] else "ok",
            (
                f"{related_links['summary']['missing_links']} frontmatter link(s) missing "
                f"from {related_links['summary']['files']} Related links section(s)"
                if related_links["summary"]["missing_links"]
                else "Related links mirrors match frontmatter"
            ),
            checks=[
                {
                    "name": str(item["path"]),
                    "state": "warn",
                    "summary": f"{len(item['missing'])} missing mirror link(s)",
                    "missing": item["missing"],
                    "content_included": False,
                }
                for item in related_links["files"]
            ],
            actions=related_actions,
        )
    )

    graph = _graph_summary(target)
    if graph["state"] != "ok":
        actions.append(
            _action(
                id="graph-links",
                title="Review graph and wikilink health",
                state=graph["state"],
                mode="manual",
                command="mb graph --json",
                safe_to_apply=False,
                reason="link meaning belongs to the operator or agent reviewing content",
            )
        )
    sections.append(
        _section(
            "graph",
            "Graph And Link Health",
            graph["state"],
            graph["summary"],
            checks=[{"name": "mb graph --json", **graph}],
        )
    )

    git = _git_summary(target)
    sections.append(
        _section(
            "git",
            "Git Review State",
            git["state"],
            git["summary"],
            checks=[
                {
                    "name": "branch",
                    "state": git["state"],
                    "summary": git["branch"] or "(none)",
                },
                {
                    "name": "dirty-state",
                    "state": git["state"],
                    "summary": f"{len(git['changed_files'])} changed file(s)",
                },
            ],
        )
    )

    agent_surfaces = _agent_surfaces(
        sections,
        actions,
        only=only,
        all_agents=all_agents,
    )
    sections, actions = _agent_scope_filter(
        sections,
        actions,
        only=only,
        all_agents=all_agents,
    )

    states = [str(section["state"]) for section in sections]
    summary = {
        "ok": sum(1 for state in states if state == "ok"),
        "info": sum(1 for state in states if state == "info"),
        "warn": sum(1 for state in states if state == "warn"),
        "error": sum(1 for state in states if state == "error"),
        "actions": len(actions),
        "write_actions": sum(1 for action in actions if action["mode"] == "write"),
        "safe_apply_actions": sum(
            1 for action in actions if action["mode"] == "write" and action["safe_to_apply"]
        ),
    }
    flag = engine_mod.repo_flag(target)
    if mode == "plan":
        if summary["error"]:
            plan_state = "plan_produced_with_blockers"
            plan_summary = (
                f"`mb doctor repair{flag} --plan` produced a read-only plan with blockers. "
                "Treat the nonzero exit as findings to review, not as an opaque command failure."
            )
        elif actions:
            plan_state = "plan_produced_with_findings"
            plan_summary = (
                f"`mb doctor repair{flag} --plan` produced a read-only plan with findings. "
                "Review the actions before approving any apply command."
            )
        else:
            plan_state = "clear"
            plan_summary = f"`mb doctor repair{flag} --plan` found no repair actions."
    else:
        plan_state = "apply_summary"
        plan_summary = f"`mb doctor repair{flag} --apply` returned an apply summary."
    report: dict[str, Any] = {
        "schema": REPAIR_SCHEMA,
        "schema_version": REPAIR_SCHEMA_VERSION,
        "ok": summary["error"] == 0,
        "mode": mode,
        "only": only,
        "all_agents": all_agents,
        "read_only": mode == "plan",
        "repo": str(target),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": summary,
        "plan_interpretation": {
            "state": plan_state,
            "summary": plan_summary,
            "read_only_plan": mode == "plan",
            "nonzero_exit_can_still_include_usable_plan": bool(mode == "plan" and actions),
            "safe_to_share": True,
        },
        "sections": sections,
        "actions": actions,
        # Steps for a person at a terminal, never run by an agent (#1042).
        "operator_actions": (
            codex_operator_actions
            if only == "codex"
            else [item for item in operator_actions if item not in codex_operator_actions]
            if only == "claude"
            else operator_actions
        ),
        "applied_actions": applied_actions or [],
        "agent_surfaces": agent_surfaces,
        "receipt": _repair_receipt(
            applied_actions or [],
            only=only,
            all_agents=all_agents,
        ),
        "post_apply": {
            "structural_verification": "mb doctor repair --plan --json",
            "validation_frontmatter_debt": "mb validate --cross-refs",
            "related_links_mirrors": "mb doctor repair --plan --json",
            "runtime_smoke_required": (
                "Static repair does not prove Claude Code runtime behavior. "
                "From the business repo, run `claude`, confirm `/mb-start` is discoverable, "
                "and verify it reads repo context without writing into the engine repo. "
                "For Codex, run read-only `codex exec --json --ephemeral --sandbox read-only "
                "-c 'approval_policy=\"never\"' -C <repo>` and verify the repo stays clean."
            ),
            "git_review": [
                "git status --short",
                "git diff",
                "git add <reviewed repair files>",
                "git commit -m '[fix] Reconcile Main Branch repo wiring'",
            ],
        },
        "raw": {
            "migration": migration,
            "legacy_reference": reference_state,
            "migration_drift": migration_drift,
            "offer_topology": offer_topology,
            "legacy_vip": legacy_vip,
            "legacy_claude_links": legacy_links,
            "validation": validation.get("report", {}),
            "related_links": related_links,
            "graph": graph.get("report", {}),
            "git": git,
        },
    }
    _qualify_report(report, target)
    post_apply = report["post_apply"]
    for key in ("structural_verification", "validation_frontmatter_debt", "related_links_mirrors"):
        post_apply[key] = _qualify_command(post_apply[key], target)
    return report


def repair_apply(
    repo: str | Path = ".",
    *,
    include_migration: bool = False,
    only: str = "",
    all_agents: bool = False,
) -> dict[str, Any]:
    """Apply safe doctor repairs and return a fresh reconciliation report."""
    if only and only not in AGENT_REPAIR_SCOPES:
        raise ValueError(f"unknown repair scope: {only}")
    if only and all_agents:
        raise ValueError("--only cannot be combined with --all-agents")
    target = Path(repo).expanduser().resolve()
    guard = _not_business_folder_guard(target, mode="apply")
    if guard is not None:
        return guard
    before = repair_plan(target, only=only, all_agents=all_agents)
    applied: list[dict[str, Any]] = []
    apply_non_agent = not only and not all_agents
    apply_claude = only == "claude" or all_agents
    apply_codex = only == "codex" or all_agents

    missing_gitignore = _missing_gitignore_entries(target)
    tracked_local_state = _tracked_local_state_paths(target)
    if missing_gitignore and apply_non_agent and not gitignore_problem(target):
        changed = _append_unique_lines(target / ".gitignore", missing_gitignore)
        applied.append(
            _action(
                id="gitignore-local-state",
                title="Protected Main Branch local state in .gitignore",
                state="ok",
                mode="write",
                command="mb doctor repair --apply",
                safe_to_apply=True,
                reason="added missing local-state gitignore entries",
                writes=[".gitignore"],
                applied=changed,
                result={"added": missing_gitignore},
            )
        )
    if tracked_local_state and apply_non_agent:
        results = [_untrack_local_state_path(target, rel) for rel in tracked_local_state]
        applied.append(
            _action(
                id="gitignore-local-state-untrack",
                title="Untracked Main Branch local state from git",
                state="ok" if all(item["ok"] for item in results) else "error",
                mode="write",
                command="mb doctor repair --apply",
                safe_to_apply=True,
                reason=(
                    "removed local operational state from the git index while "
                    "leaving the files on disk"
                ),
                writes=tracked_local_state,
                applied=any(item["ok"] for item in results),
                result={"untracked": results},
            )
        )

    checkpoint_hook = checkpoint_mod.hook_status(target)
    if checkpoint_hook.get("state") in {"missing", "broken"} and apply_non_agent:
        installed = checkpoint_mod.install_commit_hook(target)
        applied.append(
            _action(
                id="checkpoint-hook-install",
                title="Installed business checkpoint commit-message hook",
                state="ok" if installed["ok"] else "error",
                mode="write",
                command="mb checkpoint --install-hook",
                safe_to_apply=True,
                reason="installed repo-local validation for business-readable checkpoint subjects",
                writes=[".git/hooks/commit-msg"],
                applied=bool(installed.get("changed")),
                result=installed,
            )
        )

    shadow = engine_mod.inspect_personal_skill_conflicts(target, apply=apply_claude)
    if int(shadow.get("summary", {}).get("repaired", 0) or 0) and apply_claude:
        applied.append(
            _action(
                id="skill-shadow-repair",
                title="Moved stale personal Main Branch skill symlinks to backup",
                state="ok" if shadow["ok"] else "error",
                mode="write",
                command="mb skill repair --repo . --apply",
                safe_to_apply=True,
                reason="repaired stale or broken Main Branch personal symlinks",
                writes=[str(shadow.get("personal_skills_dir") or "~/.claude/skills")],
                applied=True,
                result=shadow,
            )
        )

    if not link_status(target).get("ok") and apply_claude:
        linked = engine_mod.link_skills(target)
        applied.append(
            _action(
                id="skill-link",
                title="Restored Main Branch start wiring for Claude Code",
                state="ok" if linked["ok"] else "error",
                mode="write",
                command="mb skill link --repo . --json",
                safe_to_apply=True,
                reason=(
                    "restored project-local Main Branch start wiring so Claude Code "
                    "can discover /mb-start"
                ),
                writes=[".claude/settings.local.json", ".claude/skills/", ".gitignore"],
                applied=True,
                result=linked,
            )
        )

    # #1042: never switch a repo to the plugin rail here. The switch writes the
    # tracked `.claude/settings.json`; the plan lists it in `operator_actions`.

    legacy_links = _legacy_claude_symlinks(target)
    repaired_links = (
        _repair_legacy_claude_symlinks(target, legacy_links["findings"])
        if apply_claude
        else {"moved": [], "errors": [], "ok": True}
    )
    if (repaired_links["moved"] or repaired_links["errors"]) and apply_claude:
        _append_unique_lines(target / ".gitignore", [".mb/backups/"])
        applied.append(
            _action(
                id="legacy-claude-link-repair",
                title="Moved old clone-path lens/reference symlinks to backup",
                state="ok" if repaired_links["ok"] else "error",
                mode="write",
                command=(
                    "mb doctor repair --apply --only claude"
                    if only == "claude"
                    else "mb doctor repair --apply --all-agents"
                    if all_agents
                    else "mb doctor repair --apply"
                ),
                safe_to_apply=True,
                reason="moved stale symlink entries, not user-authored files",
                writes=[".claude/lenses/", ".claude/reference/", ".mb/backups/"],
                applied=bool(repaired_links["moved"]),
                result=repaired_links,
            )
        )

    codex_instruction_status = codex_mod.instructions_status(target)
    if not codex_instruction_status["ok"] and apply_codex:
        agents = codex_mod.write_agents_md(target)
        applied.append(
            _action(
                id="codex-agents-md",
                title=(
                    "Left Codex AGENTS.md unchanged: it needs a manual repair first"
                    if agents["refused"]
                    else "Refreshed Codex repo instructions"
                ),
                state="warn" if agents["refused"] or agents["kept"] else "ok",
                mode="write",
                command=(
                    "mb doctor repair --apply --only codex"
                    if only == "codex"
                    else "mb doctor repair --apply --all-agents"
                    if all_agents
                    else "mb doctor repair --apply"
                ),
                safe_to_apply=not (agents["refused"] or agents["kept"]),
                reason=(
                    str(agents["refused"][0]["reason"])
                    if agents["refused"]
                    else "wrote current Codex AGENTS.md fact grounding, lifecycle routing, "
                    "and approval boundaries"
                    + (
                        "; kept files not proven to be Main Branch's: " + ", ".join(agents["kept"])
                        if agents["kept"]
                        else ""
                    )
                ),
                writes=list(agents.get("changed_paths", []))
                or ([] if agents["refused"] else ["AGENTS.md"]),
                applied=bool(agents["changed"]),
                result=agents,
            )
        )

    codex_status = codex_mod.readiness(target)
    codex_global_skill = codex_status["global_skill"]
    if not codex_global_skill["ok"] and apply_codex:
        installed = codex_mod.install_global_skill(target)
        applied.append(
            _action(
                id="codex-global-skill",
                title="Installed the global Main Branch Codex skill bundle",
                state="ok" if installed["ok"] else "error",
                mode="write",
                command=(
                    "mb doctor repair --apply --only codex"
                    if only == "codex"
                    else "mb doctor repair --apply --all-agents"
                ),
                safe_to_apply=True,
                reason=("installed global Codex skills for the supported Main Branch mb-* routes"),
                writes=[
                    str(codex_mod.global_skill_source_root()),
                ],
                applied=bool(installed.get("source", {}).get("changed")),
                result=installed,
            )
        )

    related_links_result: dict[str, Any] = {"changed": [], "errors": [], "ok": True}
    if apply_non_agent:
        related_links_result = related_links_mod.apply(target)
    if related_links_result["changed"] or related_links_result["errors"]:
        applied.append(
            _action(
                id="related-links-mirror",
                title="Mirrored frontmatter links into Related links",
                state="ok" if related_links_result["ok"] else "error",
                mode="write",
                command="mb doctor repair --apply",
                safe_to_apply=True,
                reason=(
                    "added missing Markdown body links from frontmatter; "
                    "frontmatter remains authoritative"
                ),
                writes=[str(item["path"]) for item in related_links_result["changed"]],
                applied=bool(related_links_result["changed"]),
                result=related_links_result,
            )
        )

    if include_migration and apply_non_agent:
        migrated = migrate_mod.apply(target)
        applied.append(
            _action(
                id="migration-apply",
                title="Applied approved layout migration",
                state="ok" if migrated["ok"] else "error",
                mode="write",
                command="mb migrate --repo . --apply",
                safe_to_apply=False,
                reason="operator explicitly opted into migration apply",
                writes=["core/", "reference/core", "reference/offers", ".mb/schema_version"],
                applied=bool(migrated.get("applied")),
                result=migrated,
            )
        )

    after = repair_plan(
        target,
        mode="apply",
        applied_actions=applied,
        only=only,
        all_agents=all_agents,
    )
    after["before_summary"] = before["summary"]
    return after


def render_human(report: dict[str, Any]) -> None:
    """Print a friendly summary to stdout."""
    from rich.console import Console

    console = Console()
    console.print(f"\n[bold]mb doctor[/bold]  {report['repo']}\n")
    alert = format_update_alert(report.get("update", {}))
    if alert:
        console.print(alert)
        console.print()
    for c in report["checks"]:
        sev = c.get("severity", "ok")
        if c["ok"]:
            mark = "[green]ok[/green]"
        elif sev == "warn":
            mark = "[yellow]warn[/yellow]"
        elif sev == "info":
            mark = "[blue]info[/blue]"
        else:
            mark = "[red]fail[/red]"
        console.print(f"  {mark}  {c['name']:<22} {c['detail']}")
    console.print()
    if report["ok"]:
        console.print("[green]all good — you're set to run `claude`.[/green]")
    else:
        console.print("[red]a few things to fix above — most are quick.[/red]")
