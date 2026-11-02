"""``mb status`` — cheap daily briefing for a Main Branch repo."""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mb import __version__, github_activity, relationships, team, vocabulary
from mb import books as books_mod
from mb import codex as codex_mod
from mb import connect as connect_mod
from mb import content_strategy as content_strategy_mod
from mb import journal as journal_mod
from mb import onboard as onboard_mod
from mb import pushes as pushes_mod
from mb import ranker as ranker_mod
from mb import site as site_mod
from mb import topology as topology_mod
from mb import usage as usage_mod
from mb import validate as validate_mod
from mb.engine import install_mode, link_status, missing_bundled_links, repo_flag
from mb.freshness import (
    MODE_NEUTRAL_UPDATE_TEXT,
    REQUIRED_UPDATE_COMMANDS,
    format_update_alert,
    package_update_status,
)
from mb.gitignore import gitignore_problem
from mb.json_result import json_default as json_default  # noqa: F401

# isort: off
from mb.status_money_path import (
    AUDIENCE_SIGNAL_KEYWORDS as AUDIENCE_SIGNAL_KEYWORDS,
    CHANNEL_KEYWORDS as CHANNEL_KEYWORDS,
    CTA_KEYWORDS as CTA_KEYWORDS,
    CUSTOMER_PROGRESS_KEYWORDS as CUSTOMER_PROGRESS_KEYWORDS,
    MONEY_PATH_COMPONENTS as MONEY_PATH_COMPONENTS,
    MONEY_PATH_LEVEL_LABELS as MONEY_PATH_LEVEL_LABELS,
    MONEY_PATH_SCHEMA_VERSION as MONEY_PATH_SCHEMA_VERSION,
    OFFER_GUARDRAIL_KEYWORDS as OFFER_GUARDRAIL_KEYWORDS,
    PRODUCT_LADDER_REQUIREMENTS as PRODUCT_LADDER_REQUIREMENTS,
    PROOF_AVERAGE_CASE_KEYWORDS as PROOF_AVERAGE_CASE_KEYWORDS,
    PROOF_BEFORE_KEYWORDS as PROOF_BEFORE_KEYWORDS,
    PROOF_CAVEAT_KEYWORDS as PROOF_CAVEAT_KEYWORDS,
    PROOF_FAILURE_CONTEXT_KEYWORDS as PROOF_FAILURE_CONTEXT_KEYWORDS,
    PROOF_MECHANISM_KEYWORDS as PROOF_MECHANISM_KEYWORDS,
    PROOF_METRIC_KEYWORDS as PROOF_METRIC_KEYWORDS,
    PROOF_OBJECTION_KEYWORDS as PROOF_OBJECTION_KEYWORDS,
    PROOF_OUTCOME_KEYWORDS as PROOF_OUTCOME_KEYWORDS,
    PROOF_PERMISSION_KEYWORDS as PROOF_PERMISSION_KEYWORDS,
    PROOF_PERMISSION_NEGATIVE_RE as PROOF_PERMISSION_NEGATIVE_RE,
    PROOF_SOURCE_KEYWORDS as PROOF_SOURCE_KEYWORDS,
    PROOF_TIMEFRAME_KEYWORDS as PROOF_TIMEFRAME_KEYWORDS,
    TestimonialEntry as TestimonialEntry,
    _contains_any as _contains_any,
    _empty_proof_quality as _empty_proof_quality,
    _falsey_structured_value as _falsey_structured_value,
    _keyword_hits as _keyword_hits,
    _known_offer_refs as _known_offer_refs,
    _markdown_body_without_frontmatter as _markdown_body_without_frontmatter,
    _money_path as _money_path,
    _money_path_active_bet_exposure as _money_path_active_bet_exposure,
    _money_path_active_push as _money_path_active_push,
    _money_path_audience as _money_path_audience,
    _money_path_channel_strategy as _money_path_channel_strategy,
    _money_path_cta as _money_path_cta,
    _money_path_customer_progress as _money_path_customer_progress,
    _money_path_evidence as _money_path_evidence,
    _money_path_finance_actions as _money_path_finance_actions,
    _money_path_label as _money_path_label,
    _money_path_object as _money_path_object,
    _money_path_offer as _money_path_offer,
    _money_path_outcome_feedback as _money_path_outcome_feedback,
    _money_path_overall_level as _money_path_overall_level,
    _money_path_page_readiness as _money_path_page_readiness,
    _money_path_playbook as _money_path_playbook,
    _money_path_product_ladder as _money_path_product_ladder,
    _money_path_proof as _money_path_proof,
    _money_path_ranked_actions as _money_path_ranked_actions,
    _normalize_offer_ref as _normalize_offer_ref,
    _offer_slug_from_path as _offer_slug_from_path,
    _proof_linked_offer_refs as _proof_linked_offer_refs,
    _proof_public_marketing_readiness as _proof_public_marketing_readiness,
    _proof_quality as _proof_quality,
    _proof_text_has_metric as _proof_text_has_metric,
    _proof_text_has_timeframe as _proof_text_has_timeframe,
    _testimonial_entries as _testimonial_entries,
    _testimonial_explicit_offer_refs as _testimonial_explicit_offer_refs,
    _testimonial_signal_counts as _testimonial_signal_counts,
    _testimonial_structured_offer_refs as _testimonial_structured_offer_refs,
    _testimonial_structured_permission_signal as _testimonial_structured_permission_signal,
    _testimonial_text as _testimonial_text,
    _testimonial_text_permission_signal as _testimonial_text_permission_signal,
    _truthy_structured_value as _truthy_structured_value,
)
from mb.status_records import (
    ACTIVE_BET_STATUSES as ACTIVE_BET_STATUSES,
    ACTIVE_PUSH_STATUSES as ACTIVE_PUSH_STATUSES,
    BET_APPETITE_TIERS as BET_APPETITE_TIERS,
    BET_SIGNAL_COMPARATORS as BET_SIGNAL_COMPARATORS,
    COMPLETED_PUSH_STATUSES as COMPLETED_PUSH_STATUSES,
    IMPORTANT_DIRS as IMPORTANT_DIRS,
    LIVE_OFFER_STATUSES as LIVE_OFFER_STATUSES,
    PLAYBOOK_APPROVAL_STATUSES_NEEDING_ATTENTION as PLAYBOOK_APPROVAL_STATUSES_NEEDING_ATTENTION,
    PLAYBOOK_PROVIDER_BOUNDARIES_NEEDING_ATTENTION as PLAYBOOK_PROVIDER_BOUNDARIES_NEEDING_ATTENTION,  # noqa: E501
    PLAYBOOK_STATUSES_NEEDING_ATTENTION as PLAYBOOK_STATUSES_NEEDING_ATTENTION,
    PUSH_STATUSES_EXPECTING_PLAYBOOK as PUSH_STATUSES_EXPECTING_PLAYBOOK,
    STALE_DECISION_DAYS as STALE_DECISION_DAYS,
    STALE_RESEARCH_DAYS as STALE_RESEARCH_DAYS,
    UNCODIFIED_DECISION_DAYS as UNCODIFIED_DECISION_DAYS,
    _bet_appetite_tier as _bet_appetite_tier,
    _bet_commitment_summary as _bet_commitment_summary,
    _bet_exit_criteria as _bet_exit_criteria,
    _bet_metric_values as _bet_metric_values,
    _bet_money_path_summary as _bet_money_path_summary,
    _bet_sort_key as _bet_sort_key,
    _bet_summary as _bet_summary,
    _bets as _bets,
    _brain as _brain,
    _coerce_relationship_refs as _coerce_relationship_refs,
    _coerce_signal_number as _coerce_signal_number,
    _coerce_string_list as _coerce_string_list,
    _compare_signal as _compare_signal,
    _evaluate_bet_signal as _evaluate_bet_signal,
    _file_path_from_graph_id as _file_path_from_graph_id,
    _file_summary as _file_summary,
    _frontmatter_status as _frontmatter_status,
    _gap as _gap,
    _is_hidden_or_generated as _is_hidden_or_generated,
    _is_stub_content as _is_stub_content,
    _linked_paths as _linked_paths,
    _linked_push_paths_for_bet as _linked_push_paths_for_bet,
    _money_amount as _money_amount,
    _offer_summaries as _offer_summaries,
    _parse_date as _parse_date,
    _parse_explicit_date as _parse_explicit_date,
    _playbook_health as _playbook_health,
    _playbook_summaries as _playbook_summaries,
    _playbook_summary as _playbook_summary,
    _read_frontmatter as _read_frontmatter,
    _read_markdown_text as _read_markdown_text,
    _relationship_adjacency as _relationship_adjacency,
    _relationship_markdown_files as _relationship_markdown_files,
    _relationship_reference_edges as _relationship_reference_edges,
    _relationship_slug as _relationship_slug,
    _relative_existing_paths as _relative_existing_paths,
    _relative_markdown_files as _relative_markdown_files,
    _resolve_relationship_ref as _resolve_relationship_ref,
    _title_from_markdown as _title_from_markdown,
)
# isort: on

STATUS_SCHEMA_VERSION = "1.0"
LAST_STATUS_SEEN_RELATIVE_PATH = Path(".mb") / "last-status-seen.json"
LAST_STATUS_SEEN_GITIGNORE_ENTRY = ".mb/last-status-seen.json"
# Plain words for the Google Ads statuses mb site check reports.
GOOGLE_ADS_STATUS_WORDS = {
    "declared": "customer and conversion plan declared",
    "partly_declared": "customer declared, conversion plan missing",
    "placeholder": "customer ID is a placeholder",
    "not_checked": "account connection not checked",
    "no_evidence_recorded": "no conversion evidence recorded",
}
UNLINKED_RESEARCH_DAYS = 30
STALE_PUSH_DAYS = 14
STRANDED_RECORD_DAYS = 3
STRANDED_BRANCH_LIMIT = 50
STRANDED_COMMIT_LIMIT = 200
STRANDED_RECORD_ROOTS = ("bets", "pushes", "decisions", "research", "playbooks")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _which(name: str) -> str:
    return shutil.which(name) or ""


def _run_command(
    args: list[str], cwd: Path | None = None, timeout: float = 3.0, input: str | None = None
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input,
        )
    except FileNotFoundError:
        return {"ok": False, "returncode": 127, "stdout": "", "stderr": f"{args[0]} not found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": 124, "stdout": "", "stderr": "command timed out"}
    except subprocess.SubprocessError as exc:
        return {"ok": False, "returncode": 1, "stdout": "", "stderr": str(exc)}
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _looks_like_mainbranch_repo(repo: Path) -> dict[str, Any]:
    markers = {
        "agents_md": (repo / "AGENTS.md").is_file(),
        "claude_md": (repo / "CLAUDE.md").is_file(),
        "core": (repo / "core").is_dir() or (repo / "reference" / "core").exists(),
        "research": (repo / "research").is_dir(),
        "decisions": (repo / "decisions").is_dir(),
        "skill_wiring": (repo / ".claude" / "skills" / "mb-start" / "SKILL.md").is_file(),
    }
    required_shape_count = sum(bool(markers[name]) for name in ("core", "research", "decisions"))
    looks_like = bool(markers["claude_md"] and required_shape_count >= 2)
    missing = [name for name, present in markers.items() if not present and name != "skill_wiring"]
    return {
        "looks_like_mainbranch_repo": looks_like,
        "markers": markers,
        "missing_markers": missing,
    }


def _detect_default_branch(repo: Path) -> str:
    """Return the repo's default branch, falling back to common names."""
    symbolic = _run_command(
        ["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
        cwd=repo,
    )
    if symbolic["ok"]:
        raw = str(symbolic["stdout"]).strip()
        if raw.startswith("origin/"):
            return raw[len("origin/") :]
        if raw:
            return raw
    for candidate in ("main", "master"):
        exists = _run_command(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{candidate}"],
            cwd=repo,
        )
        if exists["ok"]:
            return candidate
    return ""


def _classify_workflow(
    *,
    branch: str,
    is_linked_worktree: bool,
    default_branch: str,
) -> str:
    """Classify an in-worktree checkout. Callers must ensure they are inside a
    git work tree before calling — `_git_info` short-circuits the non-worktree
    case before reaching this helper.
    """
    if not branch:
        return "detached"
    if is_linked_worktree:
        return "worktree"
    if default_branch and branch == default_branch:
        return "solo-on-main"
    return "branch"


def _build_git_summary(
    *,
    workflow_mode: str,
    branch: str,
    default_branch: str,
    dirty_count: int,
    ahead: int | None,
    behind: int | None,
) -> str:
    if workflow_mode == "detached":
        return "This workspace is detached. Switch back to a named workspace before saving."
    if not workflow_mode:
        return ""

    if workflow_mode == "solo-on-main":
        label = f"Working in the {branch or default_branch or 'main'} workspace"
    elif workflow_mode == "worktree":
        label = "Working in a linked workspace"
    else:
        label = "Working in a separate workspace"

    parts: list[str] = [label]
    if dirty_count:
        plural = "" if dirty_count == 1 else "s"
        parts.append(f"with {dirty_count} unsaved local file{plural}")
    else:
        parts.append("with no unsaved local changes")
    if ahead and behind:
        parts[-1] += "; local and shared saved work need reconciliation"
    elif ahead:
        plural = "" if ahead == 1 else "s"
        parts.append(f"with {ahead} saved checkpoint{plural} waiting to sync")
    elif behind:
        plural = "" if behind == 1 else "s"
        parts.append(f"with {behind} newer shared checkpoint{plural} to catch up")
    return " ".join(parts) + "."


def _git_info(repo: Path) -> dict[str, Any]:
    if not _which("git"):
        return {"available": False, "inside_work_tree": False, "error": "git not on PATH"}

    inside = _run_command(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo)
    if not inside["ok"] or inside["stdout"].strip() != "true":
        return {
            "available": True,
            "inside_work_tree": False,
            "error": "not a git work tree",
        }

    branch = _run_command(["git", "branch", "--show-current"], cwd=repo)
    commit = _run_command(["git", "rev-parse", "--short", "HEAD"], cwd=repo)
    status = _run_command(["git", "status", "--porcelain"], cwd=repo)
    remote = _run_command(["git", "config", "--get", "remote.origin.url"], cwd=repo)

    branch_name = branch["stdout"].strip() if branch["ok"] else ""
    dirty_lines = (
        [line for line in status["stdout"].splitlines() if line.strip()] if status["ok"] else []
    )

    git_dir = _run_command(["git", "rev-parse", "--git-dir"], cwd=repo)
    common_dir = _run_command(["git", "rev-parse", "--git-common-dir"], cwd=repo)
    # Linked worktrees report git-dir under .git/worktrees/<name>/ while
    # git-common-dir points at the shared .git directory. Git can emit either
    # path as relative or absolute depending on context, so resolve both
    # against `repo` before comparing instead of doing raw string inequality.
    is_linked_worktree = False
    if git_dir["ok"] and common_dir["ok"]:
        git_dir_path = (repo / git_dir["stdout"].strip()).resolve()
        common_dir_path = (repo / common_dir["stdout"].strip()).resolve()
        is_linked_worktree = git_dir_path != common_dir_path
    worktree_root = ""
    if is_linked_worktree:
        toplevel = _run_command(["git", "rev-parse", "--show-toplevel"], cwd=repo)
        if toplevel["ok"]:
            worktree_root = toplevel["stdout"].strip()

    default_branch = _detect_default_branch(repo)
    workflow_mode = _classify_workflow(
        branch=branch_name,
        is_linked_worktree=is_linked_worktree,
        default_branch=default_branch,
    )

    upstream_ref = ""
    ahead: int | None = None
    behind: int | None = None
    if branch_name:
        upstream = _run_command(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=repo,
        )
        if upstream["ok"]:
            upstream_ref = upstream["stdout"].strip()
            counts = _run_command(
                ["git", "rev-list", "--left-right", "--count", f"HEAD...{upstream_ref}"],
                cwd=repo,
            )
            if counts["ok"]:
                parts = counts["stdout"].split()
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    ahead = int(parts[0])
                    behind = int(parts[1])

    summary = _build_git_summary(
        workflow_mode=workflow_mode,
        branch=branch_name,
        default_branch=default_branch,
        dirty_count=len(dirty_lines),
        ahead=ahead,
        behind=behind,
    )

    return {
        "available": True,
        "inside_work_tree": True,
        "branch": branch_name,
        "commit": commit["stdout"].strip() if commit["ok"] else "",
        "dirty": bool(dirty_lines),
        "dirty_count": len(dirty_lines),
        "dirty_files": dirty_lines[:10],
        "remote": remote["stdout"].strip() if remote["ok"] else "",
        "workflow_mode": workflow_mode,
        "default_branch": default_branch,
        "upstream": upstream_ref,
        "ahead": ahead,
        "behind": behind,
        "worktree_root": worktree_root,
        "summary": summary,
        "error": "" if status["ok"] else status["stderr"].strip(),
    }


def _stranded_record_gap(
    repo: Path, git: dict[str, Any], *, now: datetime
) -> dict[str, Any] | None:
    """Find old record commits held on branches outside the default branch."""
    default = str(git.get("default_branch") or "")
    current = str(git.get("branch") or "")
    if not git.get("inside_work_tree") or not default or not current:
        return None
    shallow = _run_command(["git", "rev-parse", "--is-shallow-repository"], cwd=repo)
    if not shallow["ok"] or shallow["stdout"].strip() != "false":
        return None
    refs = _run_command(
        [
            "git",
            "for-each-ref",
            "--format=%(refname)%09%(upstream)%09%(objectname)%09%(symref)",
            "refs/heads",
            "refs/remotes",
        ],
        cwd=repo,
    )
    if not refs["ok"]:
        return None
    local: dict[str, str] = {}
    remotes: dict[str, str] = {}
    upstreams: dict[str, str] = {}
    tips: dict[str, str] = {}
    remote_default_refs: set[str] = set()
    for line in refs["stdout"].splitlines():
        ref, upstream, tip, symref = (line.split("\t") + ["", "", "", ""])[:4]
        tips[ref] = tip
        if ref.startswith("refs/heads/"):
            name = ref.removeprefix("refs/heads/")
            local[name] = ref
            upstreams[name] = upstream
        elif ref.startswith("refs/remotes/"):
            remote, _, branch = ref.removeprefix("refs/remotes/").partition("/")
            if branch == "HEAD":
                if symref:
                    remote_default_refs.add(symref)
            else:
                remotes[ref] = f"{remote}/{branch}"
                if branch == default:
                    remote_default_refs.add(ref)
    default_ref = local.get(default)
    if not default_ref:
        return None
    bases = [default_ref, *sorted(remote_default_refs & remotes.keys())]

    branches: list[tuple[str, list[str]]] = []
    consumed_remotes: set[str] = set()
    for name, ref in sorted(local.items()):
        if name == default:
            continue
        branch_refs = [ref]
        for remote_ref in remotes:
            remote_name = remotes[remote_ref].partition("/")[2]
            if remote_ref not in remote_default_refs and (
                remote_ref == upstreams.get(name) or remote_name == name
            ):
                consumed_remotes.add(remote_ref)
                branch_refs.append(remote_ref)
        branches.append((name, branch_refs))
    for ref, name in sorted(remotes.items()):
        if ref in consumed_remotes or ref in remote_default_refs:
            continue
        branches.append((name, [ref]))
    branches_capped = len(branches) > STRANDED_BRANCH_LIMIT
    records: list[dict[str, Any]] = []
    commits_capped = False
    for name, branch_refs in branches[:STRANDED_BRANCH_LIMIT]:
        log = _run_command(
            [
                "git",
                "log",
                f"--max-count={STRANDED_COMMIT_LIMIT + 1}",
                "--format=%ct%x09%H",
                "--name-only",
                *branch_refs,
                "--not",
                *bases,
                "--",
                *STRANDED_RECORD_ROOTS,
            ],
            cwd=repo,
            timeout=5.0,
        )
        if not log["ok"]:
            return None
        file_dates: dict[str, int] = {}
        commit_date: int | None = None
        commits = 0
        for line in log["stdout"].splitlines():
            if "\t" in line:
                timestamp, _, commit = line.partition("\t")
                if timestamp.isdigit() and re.fullmatch(r"[0-9a-f]{40,64}", commit):
                    commits += 1
                    commit_date = int(timestamp)
                    continue
            if commit_date is not None and line.startswith(
                tuple(f"{root}/" for root in STRANDED_RECORD_ROOTS)
            ):
                file_dates[line] = min(file_dates.get(line, commit_date), commit_date)
        if commits > STRANDED_COMMIT_LIMIT:
            commits_capped = True
        if not file_dates:
            continue
        branch_tips = list(dict.fromkeys(tips[ref] for ref in branch_refs))
        changed_by_tip = {tip: set(file_dates) for tip in branch_tips}
        for base in bases:
            diff = _run_command(
                [
                    "git",
                    "diff-tree",
                    "--stdin",
                    "-r",
                    "--name-only",
                    "--diff-filter=ACMRTUXB",
                    "--",
                    *STRANDED_RECORD_ROOTS,
                ],
                cwd=repo,
                timeout=5.0,
                input="".join(f"{tip} {tips[base]}\n" for tip in branch_tips),
            )
            if not diff["ok"]:
                return None
            different: dict[str, set[str]] = {tip: set() for tip in branch_tips}
            current_tip = ""
            for line in diff["stdout"].splitlines():
                if line in different:
                    current_tip = line
                elif current_tip:
                    different[current_tip].add(line)
            for tip in branch_tips:
                changed_by_tip[tip] &= different[tip]
        files = set().union(*changed_by_tip.values())
        if not files:
            continue
        oldest = min(file_dates[path] for path in files)
        age = now - datetime.fromtimestamp(oldest, timezone.utc)
        age_days = max(0, age.days)
        if age > timedelta(days=STRANDED_RECORD_DAYS):
            records.append(
                {
                    "branch": name,
                    "current": name == current,
                    "files": sorted(files)[:5],
                    "files_total": len(files),
                    "age_days": age_days,
                    "commits_capped": commits > STRANDED_COMMIT_LIMIT,
                }
            )
    if not records:
        return None
    current_text = " Your current branch is included." if any(r["current"] for r in records) else ""
    return {
        "id": "records_stranded_on_branches",
        "severity": "warn",
        "summary": (
            f"{len(records)} branch(es) hold older business records outside {default}."
            f"{current_text}"
        ),
        "count": len(records),
        "evidence": [str(item["branch"]) for item in records[:5]],
        "records": records[:5],
        "branches_total": len(records),
        "branches_capped": branches_capped,
        "commits_capped": commits_capped,
        "repair": (
            f"Check {default} for a duplicate record, then merge each branch into {default} "
            "or close it."
        ),
        "safe_to_share": True,
    }


def _git_recent_activity(repo: Path, git: dict[str, Any]) -> dict[str, Any]:
    if not git.get("inside_work_tree"):
        return {"available": False, "items": [], "error": git.get("error") or "git unavailable"}

    cmd = [
        "git",
        "log",
        "--since=14 days ago",
        "--date=short",
        "--pretty=format:%h%x09%ad%x09%s",
        "--name-only",
        "--",
        "core",
        "reference/core",
        "research",
        "decisions",
        "bets",
        "playbooks",
        "pushes",
        "campaigns",
        "log",
        "documents",
    ]
    result = _run_command(cmd, cwd=repo)
    if not result["ok"]:
        return {"available": False, "items": [], "error": result["stderr"].strip()}

    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in result["stdout"].splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("\t", 2)
        if len(parts) == 3 and re.fullmatch(r"[0-9a-f]{4,}", parts[0]):
            if current is not None:
                items.append(current)
            current = {"commit": parts[0], "date": parts[1], "subject": parts[2], "files": []}
            continue
        if current is not None:
            current["files"].append(line)
    if current is not None:
        items.append(current)

    return {"available": True, "items": items[:8], "error": ""}


def _parse_git_log_with_files(output: str, *, limit: int = 8) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("\t", 2)
        if len(parts) == 3 and re.fullmatch(r"[0-9a-f]{4,}", parts[0]):
            if current is not None:
                items.append(current)
            current = {"commit": parts[0], "date": parts[1], "subject": parts[2], "files": []}
            continue
        if current is not None:
            current["files"].append(line)
    if current is not None:
        items.append(current)
    return items[:limit]


def _git_since_last_seen(
    repo: Path,
    git: dict[str, Any],
    marker: dict[str, Any],
) -> dict[str, Any]:
    if not git.get("inside_work_tree"):
        return {
            "available": False,
            "commits": [],
            "changed_files": [],
            "error": git.get("error") or "git unavailable",
        }

    marker_git_raw = marker.get("git")
    marker_git: dict[str, Any] = marker_git_raw if isinstance(marker_git_raw, dict) else {}
    previous_commit = str(marker_git.get("commit") or "")
    current_commit = str(git.get("commit") or "")
    args = [
        "git",
        "log",
        "--date=short",
        "--pretty=format:%h%x09%ad%x09%s",
        "--name-only",
    ]
    if previous_commit and current_commit and previous_commit != current_commit:
        args.append(f"{previous_commit}..HEAD")
    else:
        previous_seen_at = _parse_timestamp(marker.get("seen_at"))
        if previous_seen_at is None:
            return {"available": True, "commits": [], "changed_files": [], "error": ""}
        args.append(f"--since={previous_seen_at.isoformat()}")
    result = _run_command(args, cwd=repo)
    if not result["ok"]:
        return {"available": False, "commits": [], "changed_files": [], "error": result["stderr"]}

    commits = _parse_git_log_with_files(result["stdout"])
    changed_files = sorted({file for item in commits for file in item["files"]})
    return {
        "available": True,
        "commits": commits,
        "changed_files": changed_files[:20],
        "error": "",
    }


def _empty_journal(repo: Path, *, available: bool) -> dict[str, Any]:
    return {
        "available": available,
        "ok": True,
        "repo": str(repo),
        "schema_version": journal_mod.JOURNAL_SCHEMA_VERSION,
        "events": [],
        "groups": [],
        "summary": {
            "events": 0,
            "groups": 0,
            "recognized_events": 0,
            "legacy_checkpoints": 0,
            "unrecognized_events": 0,
            "refs": 0,
        },
        "error": "",
        "safe_to_share": True,
    }


def _journal_since_last_seen(
    repo: Path,
    git: dict[str, Any],
    marker: dict[str, Any],
) -> dict[str, Any]:
    if not git.get("inside_work_tree"):
        return _empty_journal(repo, available=False)

    marker_git_raw = marker.get("git")
    marker_git: dict[str, Any] = marker_git_raw if isinstance(marker_git_raw, dict) else {}
    previous_commit = str(marker_git.get("commit") or "")
    current_commit = str(git.get("commit") or "")
    if previous_commit and current_commit and previous_commit != current_commit:
        return journal_mod.collect(repo, limit=20, since=None, rev_range=f"{previous_commit}..HEAD")

    previous_seen_at = _parse_timestamp(marker.get("seen_at"))
    if previous_seen_at is None:
        return _empty_journal(repo, available=True)
    return journal_mod.collect(repo, limit=20, since=previous_seen_at.isoformat(), rev_range=None)


def _is_push_stale(record: dict[str, Any], today: date) -> tuple[bool, int]:
    review_on = _parse_explicit_date(record.get("review_on"))
    if review_on is not None and review_on < today:
        return True, (today - review_on).days
    for key in ("started", "date"):
        item_date = _parse_explicit_date(record.get(key))
        if item_date is not None:
            age_days = (today - item_date).days
            if age_days > STALE_PUSH_DAYS:
                return True, age_days
            return False, age_days
    if any(record.get(key) not in (None, "") for key in ("review_on", "started", "date")):
        return False, 0
    slug = str(record.get("slug") or "")
    match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:-|$)", slug)
    if match:
        slug_date = _parse_explicit_date(match.group(1))
        if slug_date is not None:
            age_days = (today - slug_date).days
            return age_days > STALE_PUSH_DAYS, age_days
    return False, 0


def _relationship_health(
    repo: Path,
    *,
    brain: dict[str, Any],
    today: date,
) -> dict[str, Any]:
    edges = _relationship_reference_edges(repo)
    adjacency = _relationship_adjacency(edges)
    all_bets = [_bet_summary(repo, path) for path in _relative_markdown_files(repo, "bets")]
    active_bets = [
        item for item in all_bets if str(item.get("status", "")).lower() in ACTIVE_BET_STATUSES
    ]
    closed_bets = [item for item in all_bets if str(item.get("status", "")).lower() == "closed"]
    push_report = brain.get("pushes") or {}
    pushes = [item for item in push_report.get("records", []) if isinstance(item, dict)]
    push_frontmatter = {
        str(item.get("path") or ""): pushes_mod.read_frontmatter(repo / str(item.get("path") or ""))
        for item in pushes
    }
    offers = _offer_summaries(repo)
    decisions = [_file_summary(repo, path) for path in _relative_markdown_files(repo, "decisions")]
    research = [_file_summary(repo, path) for path in _relative_markdown_files(repo, "research")]
    bet_paths = {str(item.get("path") or "") for item in all_bets}
    push_paths = {str(item.get("path") or "") for item in pushes}
    current_push_paths = {
        str(item.get("path") or "")
        for item in pushes
        if str(item.get("status", "")).lower() in ACTIVE_PUSH_STATUSES
    }
    accepted_decisions_without_links = [
        item
        for item in decisions
        if str(item.get("status") or "").lower() in {"accepted", "codified"}
        and not adjacency.get(str(item["path"]))
    ]
    research_without_links = [
        {**item, "age_days": (today - research_date).days}
        for item in research
        if (research_date := _parse_explicit_date(item.get("date"))) is not None
        and (today - research_date).days > UNLINKED_RESEARCH_DAYS
        and not adjacency.get(str(item["path"]))
    ]

    active_bets_without_push = [
        item
        for item in active_bets
        if not _linked_push_paths_for_bet(adjacency, str(item["path"]), push_paths)
    ]
    closed_bets_without_outcome = [
        item for item in closed_bets if not _linked_paths(adjacency, str(item["path"]), "outcome")
    ]
    active_pushes_without_offer = [
        item
        for item in pushes
        if str(item.get("status", "")).lower() in ACTIVE_PUSH_STATUSES
        and not _linked_paths(adjacency, str(item.get("path") or ""), "offer")
    ]
    active_pushes_without_bet = [
        item
        for item in pushes
        if str(item.get("status", "")).lower() in ACTIVE_PUSH_STATUSES
        and not (
            (
                _linked_paths(adjacency, str(item.get("path") or ""), "bet")
                | _linked_paths(adjacency, str(item.get("path") or ""), "push")
            )
            & bet_paths
        )
        and not (
            push_frontmatter[str(item.get("path") or "")].get("linked_bets") == []
            and isinstance(push_frontmatter[str(item.get("path") or "")].get("no_bet_reason"), str)
            and push_frontmatter[str(item.get("path") or "")]["no_bet_reason"].strip()
        )
    ]
    completed_pushes_without_outcome = [
        item
        for item in pushes
        if str(item.get("status", "")).lower() in COMPLETED_PUSH_STATUSES
        and not _linked_paths(adjacency, str(item.get("path") or ""), "outcome")
    ]
    stale_pushes_without_outcome: list[dict[str, Any]] = []
    for item in pushes:
        if str(item.get("status", "")).lower() not in ACTIVE_PUSH_STATUSES:
            continue
        if _linked_paths(adjacency, str(item.get("path") or ""), "outcome"):
            continue
        source = push_frontmatter[str(item.get("path") or "")]
        stale, age_days = _is_push_stale(
            {
                **item,
                "date": source.get("date"),
                "slug": source.get("slug") or Path(str(item["path"])).parent.name,
            },
            today,
        )
        if stale:
            stale_item = dict(item)
            stale_item["age_days"] = age_days
            stale_pushes_without_outcome.append(stale_item)

    offers_without_current_push_or_playbook: list[dict[str, Any]] = []
    for item in offers:
        status = str(item.get("status") or "").lower()
        if status not in LIVE_OFFER_STATUSES:
            continue
        path = str(item.get("path") or "")
        offer_pushes = _linked_paths(adjacency, path, "offer")
        linked_pushes = _linked_paths(adjacency, path, "push")
        has_current_push = bool((offer_pushes | linked_pushes) & current_push_paths)
        has_playbook = bool(_linked_paths(adjacency, path, "playbook"))
        if not has_current_push and not has_playbook:
            offers_without_current_push_or_playbook.append(item)

    relationship_types = {
        relationship.canonical_type for relationship in relationships.RELATIONSHIPS
    }
    missing_relationship_targets: list[dict[str, Any]] = []
    for edge in edges:
        rel_type = str(edge.get("rel_type") or "")
        target = str(edge.get("target") or "")
        if rel_type not in relationship_types or not target.startswith("missing:"):
            continue
        raw_evidence = edge.get("evidence")
        evidence: dict[str, Any] = raw_evidence if isinstance(raw_evidence, dict) else {}
        missing_relationship_targets.append(
            {
                "source": str(evidence.get("path") or _file_path_from_graph_id(edge.get("source"))),
                "relationship": rel_type,
                "field": str(edge.get("original_field") or evidence.get("field") or ""),
                "target": str(edge.get("target_ref") or target.removeprefix("missing:")),
            }
        )

    outcome_edges = [edge for edge in edges if str(edge.get("rel_type") or "") == "outcome"]
    gaps = [
        _gap(
            gap_id="active_bets_without_push",
            severity="warn",
            summary=f"{len(active_bets_without_push)} active bet(s) need a linked push.",
            records=active_bets_without_push,
            repair=(
                "Link each active bet to the push that supports it, or add the reverse "
                "`linked_bets` field on that push."
            ),
        )
        if active_bets_without_push
        else None,
        _gap(
            gap_id="closed_bets_without_outcome",
            severity="warn",
            summary=(
                f"{len(closed_bets_without_outcome)} closed bet(s) need a result or outcome link."
            ),
            records=closed_bets_without_outcome,
            repair="Record the bet result and link the outcome artifact.",
        )
        if closed_bets_without_outcome
        else None,
        _gap(
            gap_id="active_pushes_without_offer",
            severity="warn",
            summary=(
                f"{len(active_pushes_without_offer)} active/planned push(es) need an offer link."
            ),
            records=active_pushes_without_offer,
            repair="Set the push `offer:` field to the repo-relative offer file.",
        )
        if active_pushes_without_offer
        else None,
        _gap(
            gap_id="active_pushes_without_bet",
            severity="warn",
            summary=(
                f"{len(active_pushes_without_bet)} live push(es) do not say which bet they serve."
            ),
            records=active_pushes_without_bet,
            repair=(
                "Link each push to its bet with `linked_bets`, write the bet with `/mb-bet`, "
                "or set `linked_bets: []` and a short `no_bet_reason` for a one-off."
            ),
        )
        if active_pushes_without_bet
        else None,
        _gap(
            gap_id="completed_pushes_without_outcome",
            severity="warn",
            summary=(
                f"{len(completed_pushes_without_outcome)} completed push(es) need review/outcome."
            ),
            records=completed_pushes_without_outcome,
            repair="Add `linked_outcomes` to the completed push after review.",
        )
        if completed_pushes_without_outcome
        else None,
        _gap(
            gap_id="stale_pushes_without_outcome",
            severity="warn",
            summary=f"{len(stale_pushes_without_outcome)} stale push(es) have not closed the loop.",
            records=stale_pushes_without_outcome,
            repair="Review stale pushes, capture the outcome, or update the review date.",
        )
        if stale_pushes_without_outcome
        else None,
        _gap(
            gap_id="offers_without_current_push_or_playbook",
            severity="info",
            summary=(
                f"{len(offers_without_current_push_or_playbook)} offer(s) have no current push "
                "or linked playbook."
            ),
            records=offers_without_current_push_or_playbook,
            repair=(
                "Connect each live offer to a current push or reusable playbook. Either set "
                "the push `offer:` to the repo-relative offer file or add `linked_pushes:` "
                "on the offer."
            ),
        )
        if offers_without_current_push_or_playbook
        else None,
        _gap(
            gap_id="accepted_decisions_without_links",
            severity="info",
            summary=(
                f"{len(accepted_decisions_without_links)} accepted decision(s) "
                "have no business links."
            ),
            records=accepted_decisions_without_links,
            repair="Link each decision to the bet or push it informs.",
        )
        if accepted_decisions_without_links
        else None,
        _gap(
            gap_id="research_without_links",
            severity="info",
            summary=f"{len(research_without_links)} older research note(s) have no business links.",
            records=research_without_links,
            repair="Link each research note to the bet or push it informs.",
        )
        if research_without_links
        else None,
        _gap(
            gap_id="missing_relationship_targets",
            severity="warn",
            summary=(
                f"{len(missing_relationship_targets)} relationship link(s) point at missing files."
            ),
            records=missing_relationship_targets,
            repair="Run `mb validate --cross-refs` for exact missing-link warnings.",
        )
        if missing_relationship_targets
        else None,
    ]
    active_gaps = [gap_item for gap_item in gaps if gap_item is not None]
    return {
        "ok": not active_gaps,
        "source": "mb status relationship scan",
        "registry_version": relationships.REGISTRY_VERSION,
        "summary": {
            "gaps": len(active_gaps),
            "warnings": len([item for item in active_gaps if item["severity"] == "warn"]),
            "info": len([item for item in active_gaps if item["severity"] == "info"]),
            "active_bets_without_push": len(active_bets_without_push),
            "closed_bets_without_outcome": len(closed_bets_without_outcome),
            "active_pushes_without_offer": len(active_pushes_without_offer),
            "active_pushes_without_bet": len(active_pushes_without_bet),
            "completed_pushes_without_outcome": len(completed_pushes_without_outcome),
            "stale_pushes_without_outcome": len(stale_pushes_without_outcome),
            "offers_without_current_push_or_playbook": len(offers_without_current_push_or_playbook),
            "accepted_decisions_without_links": len(accepted_decisions_without_links),
            "research_without_links": len(research_without_links),
            "missing_relationship_targets": len(missing_relationship_targets),
        },
        "gaps": active_gaps,
        "sections": {
            "bets": {
                "active": len(active_bets),
                "closed": len(
                    [item for item in all_bets if str(item.get("status") or "").lower() == "closed"]
                ),
                "active_without_push": active_bets_without_push[:5],
                "closed_without_outcome": closed_bets_without_outcome[:5],
            },
            "pushes": {
                "records": len(pushes),
                "active_without_offer": active_pushes_without_offer[:5],
                "active_without_bet": active_pushes_without_bet[:5],
                "completed_without_outcome": completed_pushes_without_outcome[:5],
                "stale_without_outcome": stale_pushes_without_outcome[:5],
            },
            "offers": {
                "records": len(offers),
                "without_current_push_or_playbook": offers_without_current_push_or_playbook[:5],
            },
            "decisions": {
                "without_links": accepted_decisions_without_links[:5],
                "without_links_total": len(accepted_decisions_without_links),
            },
            "research": {
                "without_links": research_without_links[:5],
                "without_links_total": len(research_without_links),
            },
            "outcomes": {
                "linked_count": len(outcome_edges),
                "missing_targets": missing_relationship_targets[:5],
            },
        },
        "safe_to_share": True,
    }


def _repo_full_name(remote: str) -> str:
    return github_activity.repo_full_name(remote)


def _gh_json(args: list[str], repo: Path) -> tuple[bool, Any, str]:
    result = _run_command(args, cwd=repo, timeout=5.0)
    if not result["ok"]:
        return False, None, result["stderr"].strip() or result["stdout"].strip()
    try:
        return True, json.loads(result["stdout"] or "[]"), ""
    except json.JSONDecodeError:
        return False, None, "gh returned invalid JSON"


def _github(
    repo: Path,
    git: dict[str, Any],
    *,
    team_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = connect_mod.github_context(repo, which_func=_which, command_runner=_run_command)
    if not context["ok"]:
        sections: dict[str, list[dict[str, Any]]] = {
            "assigned_tasks": [],
            "attention_requests": [],
            "open_proposals": [],
            "shipped_this_week": [],
            "recently_closed_tasks": [],
            "blocked_or_stale_tasks": [],
        }
        return {
            "available": context["state"] != "missing_cli",
            "authenticated": context["state"] not in {"missing_cli", "unauthenticated"},
            "degraded": True,
            "source": "gh",
            "repo": "",
            "summary": {
                "assigned_tasks": 0,
                "attention_requests": 0,
                "open_proposals": 0,
                "shipped_this_week": 0,
                "recently_closed_tasks": 0,
                "blocked_or_stale_tasks": 0,
            },
            "sections": sections,
            "errors": [str(context["summary"])],
            "assigned_issues": [],
            "review_requests": [],
            "recent_merged_prs": [],
            "context": context,
        }
    if team_facts is None:
        team_facts = team.facts(repo)
    report = github_activity.collect(
        repo,
        remote=str(git.get("remote", "")),
        team_facts=team_facts,
        which_func=_which,
        command_runner=_run_command,
        json_runner=_gh_json,
    )
    report["context"] = context
    return report


def _recent_merged_prs(prs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return github_activity.recent_merged_prs(prs)


def _summarize_pr(pr: dict[str, Any]) -> dict[str, Any]:
    return github_activity.summarize_pr(pr)


def _runtime(repo: Path) -> dict[str, Any]:
    claude_path = _which("claude")
    wiring = link_status(repo)
    codex = codex_mod.readiness(repo)
    wiring_repair = "Run `mb skill repair --repo .`, then `mb skill link --repo .`."
    wiring_summary = "Claude Code skill wiring is ready."
    if not wiring["ok"]:
        if wiring.get("stale_engine_paths"):
            current = wiring.get("current_mb") or {}
            wired = str(wiring.get("wired_engine_path") or wiring["stale_engine_paths"][0])
            wiring_summary = (
                "Claude Code wiring points at a different Main Branch engine. "
                f"Current mb: {current.get('path') or 'unknown'} "
                f"{current.get('version') or ''}; wired engine: {wired}."
            )
            if wiring.get("stale_from_other_install"):
                wiring_summary += " Multiple mb installs are active on PATH."
            wiring_repair = "Run `mb skill link --repo .`."
        else:
            wiring_summary = str(wiring.get("summary") or "Missing Main Branch start wiring.")
            wiring_repair = (
                "Run `mb doctor repair --plan`, review it, then run `mb doctor repair --apply`."
            )
    return {
        "claude_code": {
            "found": bool(claude_path),
            "path": claude_path,
            # Plugin-first repair (#924): the plugin is the cross-surface rail
            # (Claude Desktop + terminal). A missing `claude` CLI is fine for
            # Desktop users, so point them at the plugin first.
            "repair": ""
            if claude_path
            else (
                "The `claude` CLI is not on PATH — fine for the Claude Desktop app: "
                "install the Main Branch plugin from + -> Plugins -> "
                "`dmthepm/mainbranch`. For terminal use, install the CLI "
                "(https://claude.ai/install), then "
                "`claude plugin marketplace add dmthepm/mainbranch`."
            ),
        },
        "skill_wiring": {
            **wiring,
            "missing_bundled_links": missing_bundled_links(repo),
            "summary": wiring_summary,
            "repair": "" if wiring["ok"] else wiring_repair,
        },
        "codex_cli": codex,
    }


def _install() -> dict[str, Any]:
    mode = install_mode()
    return {
        "version": __version__,
        "mode": mode,
        "ok": mode != "unknown",
        "detail": f"mb {__version__} ({mode} mode)",
    }


def _schema() -> dict[str, Any]:
    return {
        "name": "mainbranch.status",
        "version": STATUS_SCHEMA_VERSION,
        "compatibility": "v1 additions are additive; existing v1 keys must not change meaning.",
    }


def push_facts(repo: str | Path) -> dict[str, Any]:
    """Return normalized push facts for JSON consumers."""
    return pushes_mod.facts(repo)


SITE_REPO_PATH_FIELDS = (
    "site_repo_path",
    "site_repo",
    "site_path",
    "site_repository_path",
)


def _site_repo_path_values(value: Any) -> list[Any]:
    if isinstance(value, dict):
        items: list[Any] = []
        for key in SITE_REPO_PATH_FIELDS:
            if key in value:
                items.append(value[key])
        return items
    if isinstance(value, list):
        return [item for entry in value for item in _site_repo_path_values(entry)]
    return [value]


def _resolve_site_repo_path(repo: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if re.match(r"^[a-z][a-z0-9+.-]*://", raw, flags=re.IGNORECASE):
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = repo / candidate
    return candidate.resolve()


def _candidate_site_repo_records(repo: Path) -> list[dict[str, Any]]:
    paths = _relative_markdown_files(repo, "pushes")
    paths.extend(_relative_markdown_files(repo, "campaigns"))
    paths.extend(path for path in _relative_markdown_files(repo, "core") if path.name == "offer.md")
    paths.extend(
        path for path in _relative_markdown_files(repo, "reference/core") if path.name == "offer.md"
    )

    records: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for path in paths:
        meta = _read_frontmatter(path)
        candidate_values: list[Any] = []
        for key in SITE_REPO_PATH_FIELDS:
            if key in meta:
                candidate_values.append(meta[key])
        for nested_key in ("site", "site_record", "measurement", "launch"):
            if nested_key in meta:
                candidate_values.extend(_site_repo_path_values(meta[nested_key]))

        for value in candidate_values:
            site_repo = _resolve_site_repo_path(repo, value)
            if site_repo is None or site_repo in seen:
                continue
            if not (site_repo / site_mod.CONVERSION_RELATIVE_PATH).exists():
                continue
            try:
                source = path.relative_to(repo).as_posix()
            except ValueError:
                source = str(path)
            records.append({"path": site_repo, "source": source})
            seen.add(site_repo)
    return records


def _google_ads_statuses(result: dict[str, Any]) -> dict[str, str]:
    """Map each Google Ads evidence kind to its status, so manual_count is explained."""

    return {
        str(item["kind"]): str(item["status"])
        for item in result.get("evidence") or []
        if str(item.get("kind") or "").startswith("google_ads_") and item.get("status")
    }


def _measurement_payload(result: dict[str, Any], *, repair_command: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "available": True,
        "state": result["state"],
        "ok": result["ok"],
        "summary": result["summary"],
        "repair": result["repair"],
        "repair_command": repair_command,
        "site_repo": result.get("site_repo", ""),
        "business_repo": result.get("business_repo", ""),
        "facts": {
            "conversion_kind": result["facts"].get("conversion_kind"),
            "expected_events": result["facts"].get("expected_events"),
            "gtm_container_id_present": bool(result["facts"].get("gtm_container_id")),
            "google_ads_customer_id_present": bool(result["facts"].get("google_ads_customer_id")),
            "primary_conversions": result["facts"].get("primary_conversions") or [],
            "instrumentation": result["facts"].get("instrumentation") or {},
        },
        "blocked_count": len(result.get("blocked") or []),
        "manual_count": len(result.get("manual") or []),
        "safe_to_share": True,
    }
    google_ads = _google_ads_statuses(result)
    if google_ads:
        payload["google_ads"] = google_ads
    return payload


def _shell_arg(path: Path) -> str:
    """A path as one shell word: double quotes when those are safe, else shell-quoted."""
    text = str(path)
    if any(char in text for char in '$`\\"!'):
        return shlex.quote(text)
    return f'"{text}"'


def _measurement(repo: Path) -> dict[str, Any]:
    """Return a compact paid-traffic measurement summary for status consumers."""

    conversion_path = repo / site_mod.CONVERSION_RELATIVE_PATH
    if conversion_path.exists():
        result = site_mod.check(repo, business_repo=repo)
        return _measurement_payload(result, repair_command="mb site check")

    site_records = _candidate_site_repo_records(repo)
    if site_records:
        site_repo = site_records[0]["path"]
        result = site_mod.check(site_repo, business_repo=repo)
        payload = _measurement_payload(
            result,
            repair_command=f"mb site check {_shell_arg(site_repo)} --business-repo .",
        )
        payload["source_record"] = site_records[0]["source"]
        return payload

    return {
        "available": False,
        "state": "missing",
        "summary": "No paid-traffic site conversion plan found.",
        "repair": "Run `/mb-site` for a paid-traffic minisite before checking launch readiness.",
        "repair_command": "mb site check",
        "safe_to_share": True,
    }


def _marker_path(repo: Path) -> Path:
    return repo / LAST_STATUS_SEEN_RELATIVE_PATH


def _marker_gitignore_state(repo: Path) -> dict[str, Any]:
    gitignore = repo / ".gitignore"
    entry = LAST_STATUS_SEEN_GITIGNORE_ENTRY
    if problem := gitignore_problem(repo):
        return {"ok": False, "path": ".gitignore", "entry": entry, "repair": problem}
    if _which("git"):
        check = _run_command(["git", "check-ignore", entry], cwd=repo)
        if check["ok"]:
            return {
                "ok": True,
                "path": ".gitignore",
                "entry": entry,
                "repair": "",
            }
    if not gitignore.exists():
        return {
            "ok": False,
            "path": ".gitignore",
            "entry": entry,
            "repair": f"Add `{entry}` to `.gitignore`.",
        }
    try:
        lines = gitignore.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    ignored = entry in {line.strip() for line in lines}
    return {
        "ok": ignored,
        "path": ".gitignore",
        "entry": entry,
        "repair": "" if ignored else f"Add `{entry}` to `.gitignore`.",
    }


def _read_last_seen_marker(repo: Path) -> dict[str, Any]:
    path = _marker_path(repo)
    if not path.exists():
        return {
            "exists": False,
            "path": LAST_STATUS_SEEN_RELATIVE_PATH.as_posix(),
            "error": "",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "exists": True,
            "path": LAST_STATUS_SEEN_RELATIVE_PATH.as_posix(),
            "error": f"could not read last status marker: {exc}",
        }
    return data if isinstance(data, dict) else {"exists": True, "error": "invalid marker shape"}


def _brain_count_changes(
    current_counts: dict[str, int],
    previous_counts: dict[str, Any],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for folder, current in sorted(current_counts.items()):
        try:
            previous = int(previous_counts.get(folder, 0))
        except (TypeError, ValueError):
            previous = 0
        delta = current - previous
        if delta:
            changes.append({"folder": folder, "before": previous, "after": current, "delta": delta})
    return changes


def _since_last_check(
    repo: Path,
    *,
    marker: dict[str, Any],
    git: dict[str, Any],
    brain: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    marker_exists = bool(marker.get("exists", True)) and not marker.get("error")
    previous_seen_at = str(marker.get("seen_at") or "") if marker_exists else ""
    previous_brain_raw = marker.get("brain")
    previous_brain: dict[str, Any] = (
        previous_brain_raw if isinstance(previous_brain_raw, dict) else {}
    )
    previous_counts_raw = previous_brain.get("counts")
    previous_counts: dict[str, Any] = (
        previous_counts_raw if isinstance(previous_counts_raw, dict) else {}
    )
    git_since: dict[str, Any] = (
        _git_since_last_seen(repo, git, marker)
        if marker_exists
        else {
            "available": bool(git.get("inside_work_tree")),
            "commits": [],
            "changed_files": [],
            "error": "",
        }
    )
    journal_since: dict[str, Any] = (
        _journal_since_last_seen(repo, git, marker)
        if marker_exists
        else _empty_journal(repo, available=bool(git.get("inside_work_tree")))
    )
    count_changes = _brain_count_changes(brain.get("counts") or {}, previous_counts)
    dirty_count = int(git.get("dirty_count") or 0)
    commits = git_since.get("commits") or []
    changed_files = git_since.get("changed_files") or []
    journal_summary = journal_since.get("summary") or {}
    summary = {
        "commits": len(commits) if isinstance(commits, list) else 0,
        "files_changed": len(changed_files) if isinstance(changed_files, list) else 0,
        "dirty_files": dirty_count,
        "brain_count_changes": len(count_changes),
        "journal_events": int(journal_summary.get("events") or 0),
        "journal_groups": int(journal_summary.get("groups") or 0),
    }
    first_run = not marker_exists
    return {
        "ok": not bool(marker.get("error")),
        "marker_path": LAST_STATUS_SEEN_RELATIVE_PATH.as_posix(),
        "marker_gitignore": _marker_gitignore_state(repo),
        "previous_seen_at": previous_seen_at,
        "current_seen_at": generated_at,
        "first_run": first_run,
        "summary": summary,
        "git": git_since,
        "journal": journal_since,
        "brain_count_changes": count_changes,
        "error": str(marker.get("error") or ""),
        "safe_to_share": True,
    }


def _write_last_seen_marker(repo: Path, report: dict[str, Any]) -> dict[str, Any]:
    if not report["repo"].get("looks_like_mainbranch_repo"):
        return {
            "attempted": False,
            "ok": False,
            "reason": "not a Main Branch repo",
            "path": LAST_STATUS_SEEN_RELATIVE_PATH.as_posix(),
        }
    marker = {
        "kind": "mainbranch.status.last_seen",
        "schema_version": STATUS_SCHEMA_VERSION,
        "seen_at": report["generated_at"],
        "repo": str(repo),
        "git": {
            "branch": str(report["git"].get("branch") or ""),
            "commit": str(report["git"].get("commit") or ""),
        },
        "brain": {"counts": report["brain"].get("counts") or {}},
        "readiness": {
            "level": str(report["readiness"].get("level") or ""),
            "score": int(report["readiness"].get("score") or 0),
        },
        "safe_to_share": True,
    }
    path = _marker_path(repo)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return {
            "attempted": True,
            "ok": False,
            "reason": str(exc),
            "path": LAST_STATUS_SEEN_RELATIVE_PATH.as_posix(),
        }
    return {
        "attempted": True,
        "ok": True,
        "reason": "",
        "path": LAST_STATUS_SEEN_RELATIVE_PATH.as_posix(),
    }


def _safe_exception_message(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    message = re.sub(
        r"(?<![A-Za-z0-9:])(?:"
        r"/(?:Users|home|private|tmp|var|Volumes|opt|usr/local)/[^\s\"'`<>),;]+"
        r"|[A-Za-z]:\\[^\s\"'`<>),;]+"
        r")",
        "<local-path>",
        message,
    )
    return message[:240] + ("..." if len(message) > 240 else "")


def _validation_status(repo: Path, *, cross_refs: bool = True) -> dict[str, Any]:
    try:
        report = validate_mod.run(str(repo), cross_refs=cross_refs)
    except Exception as exc:  # pragma: no cover - defensive status boundary
        message = _safe_exception_message(exc)
        return {
            "ok": False,
            "state": "error",
            "summary": {"errors": 1, "warnings": 0, "top_category": "validation_unavailable"},
            "validation_categories": {
                "schema_version": "1.0",
                "total_categories": 1,
                "top_category": "validation_unavailable",
                "top_repair": "Run `mb validate --cross-refs --json` for the exact failure.",
                "by_category": {
                    "validation_unavailable": {
                        "count": 1,
                        "errors": 1,
                        "warnings": 0,
                        "examples": [{"path": "", "message": message}],
                        "repair": "Run `mb validate --cross-refs --json` for the exact failure.",
                    }
                },
                "safe_to_share": True,
            },
            "safe_to_share": True,
        }
    summary = report.get("summary") or {}
    errors = int(summary.get("errors") or 0)
    warnings = int(summary.get("warnings") or 0)
    return {
        "ok": bool(report.get("ok")),
        "state": "error" if errors else ("warn" if warnings else "ok"),
        "summary": summary,
        "validation_categories": report.get("validation_categories") or {},
        "file_contracts": report.get("file_contracts") or {},
        "legacy_repair": report.get("legacy_repair"),
        "cross_refs": {
            "enabled": bool((report.get("cross_refs") or {}).get("enabled")),
            "warnings": len((report.get("cross_refs") or {}).get("warnings") or []),
            "orphan_offers": len((report.get("cross_refs") or {}).get("orphan_offers") or []),
        },
        "migration_drift": (report.get("migration_drift") or {}).get("summary", {}),
        "safe_to_share": True,
    }


def _file_commit_time(repo: Path, rel: str) -> int:
    """Last-commit unix time for a repo-relative path; 0 when unknown."""
    result = _run_command(["git", "log", "-1", "--format=%ct", "--", rel], cwd=repo)
    if not result["ok"]:
        return 0
    text = result["stdout"].strip()
    return int(text) if text.isdigit() else 0


def _core_propagation_drift(repo: Path, report: dict[str, Any]) -> dict[str, Any] | None:
    """Flag identity changes that never propagated to active push records.

    Field-proven failure: offer/audience/voice change lands, and the ad
    copy, pages, and emails derived from the OLD identity keep running.
    Within-repo detectable surface: active push records. Cross-repo
    surfaces (site repos) are out of scope here.
    """
    identity_paths = [
        rel
        for rel in ("core/offer.md", "core/audience.md", "core/voice.md")
        if (repo / rel).is_file()
    ]
    for pattern in ("core/offers/*/offer.md", "core/offers/*/audience.md"):
        identity_paths.extend(
            path.relative_to(repo).as_posix() for path in sorted(repo.glob(pattern))
        )
    if not identity_paths:
        return None
    push_report = (report.get("brain") or {}).get("pushes") or {}
    active = [
        record
        for record in push_report.get("records", [])
        if record.get("status") == "active" and not record.get("legacy")
    ]
    if not active:
        return None
    identity_times = {rel: _file_commit_time(repo, rel) for rel in identity_paths}
    newest_identity_rel = max(identity_times, key=lambda rel: identity_times[rel])
    newest_identity_ts = identity_times[newest_identity_rel]
    derived_paths = [str(record.get("path") or "") for record in active if record.get("path")]
    newest_derived_ts = max((_file_commit_time(repo, rel) for rel in derived_paths), default=0)
    if not newest_identity_ts or not newest_derived_ts:
        return None
    if newest_identity_ts <= newest_derived_ts:
        return None
    return {
        "id": "core_propagation",
        "severity": "warn",
        "summary": (
            "offer/audience/voice changed after your active push record(s) "
            "were last updated — derived copy (ads, pages, emails) may still "
            "carry the old identity."
        ),
        "evidence": [newest_identity_rel] + derived_paths[:4],
        "repair": (
            "Re-check the active pushes' copy against the updated core files "
            "and update the push records in the same pass."
        ),
        "safe_to_share": True,
    }


def _drift(report: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    validation = report.get("validation") or {}
    validation_state = str(validation.get("state") or "ok")
    if validation_state != "ok":
        categories = validation.get("validation_categories") or {}
        top_category = str(categories.get("top_category") or "")
        top_repair = str(categories.get("top_repair") or "Run `mb validate --cross-refs --json`.")
        summary = validation.get("summary") or {}
        items.append(
            {
                "id": "validation_debt",
                "severity": "error" if validation_state == "error" else "warn",
                "summary": (
                    f"{summary.get('errors', 0)} validation error(s), "
                    f"{summary.get('warnings', 0)} warning(s)"
                    + (f"; top category: {top_category}" if top_category else "")
                ),
                "evidence": list((categories.get("by_category") or {}).keys())[:5],
                "repair": top_repair,
                "safe_to_share": True,
            }
        )
    stale_decisions = report["brain"].get("stale_decisions") or []
    if stale_decisions:
        stale_decisions_total = report["brain"].get("stale_decisions_total", len(stale_decisions))
        shown = (
            f" ({len(stale_decisions)} shown)"
            if stale_decisions_total > len(stale_decisions)
            else ""
        )
        items.append(
            {
                "id": "stale_decisions",
                "severity": "warn",
                "summary": (
                    f"{stale_decisions_total} proposed/running decision(s) are stale{shown}."
                ),
                "evidence": [item["path"] for item in stale_decisions[:5]],
                "repair": "Review stale proposed/running decisions in `decisions/`.",
                "safe_to_share": True,
            }
        )
    uncodified_decisions = report["brain"].get("uncodified_decisions") or []
    if uncodified_decisions:
        uncodified_total = report["brain"].get(
            "uncodified_decisions_total", len(uncodified_decisions)
        )
        shown = (
            f" ({len(uncodified_decisions)} shown)"
            if uncodified_total > len(uncodified_decisions)
            else ""
        )
        items.append(
            {
                "id": "uncodified_decisions",
                "severity": "warn",
                "summary": (
                    f"{uncodified_total} accepted decision(s) were never "
                    f"codified into reference files{shown}."
                ),
                "evidence": [item["path"] for item in uncodified_decisions[:5]],
                "repair": "Run `/mb-think codify <decision-file>` to apply each, "
                "then flip its status to codified in the same pass.",
                "safe_to_share": True,
            }
        )
    stale_research = report["brain"].get("stale_research") or []
    if stale_research:
        stale_research_total = report["brain"].get("stale_research_total", len(stale_research))
        shown = (
            f" ({len(stale_research)} shown)" if stale_research_total > len(stale_research) else ""
        )
        items.append(
            {
                "id": "stale_research",
                "severity": "info",
                "summary": (
                    f"{stale_research_total} research note(s) are older than "
                    f"current freshness rules{shown}."
                ),
                "evidence": [item["path"] for item in stale_research[:5]],
                "repair": "Refresh or supersede stale research before using it for decisions.",
                "safe_to_share": True,
            }
        )
    propagation = _core_propagation_drift(Path(str(report.get("repo") or ".")), report)
    if propagation:
        items.append(propagation)
    relationship_health = report.get("relationship_health") or {}
    relationship_summary = relationship_health.get("summary") or {}
    if relationship_summary.get("gaps", 0):
        relationship_gaps = relationship_health.get("gaps") or []
        top_gap = next(
            (gap for gap in relationship_gaps if gap.get("severity") == "warn"),
            relationship_gaps[0] if relationship_gaps else {},
        )
        items.append(
            {
                "id": "relationship_health_gaps",
                "severity": "warn" if relationship_summary.get("warnings", 0) else "info",
                "summary": (
                    f"{relationship_summary.get('gaps', 0)} business relationship gap(s) "
                    "need review."
                ),
                "evidence": [
                    str(item.get("id") or "")
                    for item in (relationship_health.get("gaps") or [])[:5]
                ],
                "repair": str(
                    top_gap.get("repair")
                    or "Run `mb status --verbose --peek` to inspect relationship gaps."
                ),
                "safe_to_share": True,
            }
        )
    playbook_health = report.get("playbook_health") or {}
    playbook_summary = playbook_health.get("summary") or {}
    if playbook_summary.get("gaps", 0):
        top_gap = (playbook_health.get("gaps") or [{}])[0]
        items.append(
            {
                "id": "playbook_health_gaps",
                "severity": "warn" if playbook_summary.get("warnings", 0) else "info",
                "summary": (
                    f"{playbook_summary.get('gaps', 0)} push playbook health signal(s) need review."
                ),
                "evidence": [
                    str(item.get("id") or "") for item in (playbook_health.get("gaps") or [])[:5]
                ],
                "repair": str(
                    top_gap.get("repair")
                    or "Run `mb status --verbose --peek` to inspect playbook health."
                ),
                "safe_to_share": True,
            }
        )
    onboarding_summary = (report.get("onboarding") or {}).get("summary") or {}
    if onboarding_summary.get("status") == "in_progress":
        items.append(
            {
                "id": "incomplete_onboarding",
                "severity": "warn",
                "summary": (
                    f"{onboarding_summary.get('completed_required', 0)}/"
                    f"{onboarding_summary.get('total_required', 0)} required onboarding "
                    "steps complete."
                ),
                "evidence": list(onboarding_summary.get("missing_inputs") or [])[:5],
                "repair": str(
                    onboarding_summary.get("next_recommended_action")
                    or "Run `mb onboard status` to resume onboarding."
                ),
                "safe_to_share": True,
            }
        )
    skill_wiring = report["runtime"].get("skill_wiring") or {}
    if not skill_wiring.get("ok"):
        items.append(
            {
                "id": "broken_skill_wiring",
                "severity": "error",
                "summary": str(
                    skill_wiring.get("summary")
                    or "Claude Code skill wiring is missing or unhealthy."
                ),
                "evidence": list(skill_wiring.get("missing") or [])[:5],
                "repair": str(skill_wiring.get("repair") or "Run `mb skill link --repo .`."),
                "safe_to_share": True,
            }
        )
    codex_cli = report["runtime"].get("codex_cli") or {}
    codex_executable = codex_cli.get("executable") or {}
    codex_instructions = codex_cli.get("instructions") or {}
    codex_runtime = codex_cli.get("runtime") or {}
    codex_global_skill = codex_cli.get("global_skill") or {}
    if codex_executable.get("found") and not codex_instructions.get("ok"):
        items.append(
            {
                "id": "codex_instructions_not_ready",
                "severity": "warn",
                "summary": "Codex repo instructions are missing or stale.",
                "evidence": [
                    str(codex_instructions.get("path") or "AGENTS.md"),
                ],
                "repair": str(
                    codex_instructions.get("repair")
                    or "Run `mb doctor repair --plan`, then `mb doctor repair --apply`."
                ),
                "safe_to_share": True,
            }
        )
    if (
        codex_executable.get("found")
        and codex_instructions.get("ok")
        and codex_runtime.get("mismatch")
    ):
        items.append(
            {
                "id": "codex_runtime_mb_mismatch",
                "severity": "warn",
                "summary": str(
                    codex_runtime.get("summary")
                    or "Codex runtime may execute a different mb than this shell."
                ),
                "evidence": [
                    f"active: {codex_runtime.get('active_path') or 'unknown'} "
                    f"{codex_runtime.get('active_version') or ''}".strip(),
                    f"runtime: {codex_runtime.get('path') or 'unknown'} "
                    f"{codex_runtime.get('version') or ''}".strip(),
                ],
                "repair": str(
                    codex_runtime.get("repair")
                    or "Put the current Main Branch install earlier on the runtime PATH."
                ),
                "safe_to_share": True,
            }
        )
    if (
        codex_executable.get("found")
        and codex_instructions.get("ok")
        and codex_runtime.get("ok")
        and not codex_global_skill.get("ok")
    ):
        items.append(
            {
                "id": "codex_global_skills_not_ready",
                "severity": "warn",
                "summary": str(
                    codex_global_skill.get("summary")
                    or "Global Main Branch Codex skills are missing or stale."
                ),
                "evidence": [
                    f"skills root: {codex_global_skill.get('skills_root') or ''}".strip(),
                    f"state: {codex_global_skill.get('state') or 'unknown'}",
                    f"missing: {', '.join(codex_global_skill.get('missing') or [])}",
                ],
                "repair": str(codex_global_skill.get("repair") or codex_mod.CODEX_REPAIR_TEXT),
                "safe_to_share": True,
            }
        )
    connected_integrations = [
        item
        for item in (report.get("integrations") or {}).get("providers", [])
        if item.get("configured", item.get("connected"))
    ]
    unverified_integrations = [
        item for item in connected_integrations if item.get("state") == connect_mod.UNVERIFIED_STATE
    ]
    not_checked_integrations = [
        item
        for item in connected_integrations
        if item.get("state") == connect_mod.NOT_CHECKED_STATE
    ]
    broken_integrations = [
        item
        for item in connected_integrations
        if not item.get("ok")
        and item.get("state") not in {connect_mod.UNVERIFIED_STATE, connect_mod.NOT_CHECKED_STATE}
    ]
    if unverified_integrations:
        items.append(
            {
                "id": "unverified_integrations",
                "severity": "warn",
                "summary": (
                    f"{len(unverified_integrations)} declared integration(s) have a stored "
                    "credential that has never been confirmed with the provider."
                ),
                "evidence": [
                    f"{item['provider']}:{item['state']}" for item in unverified_integrations[:5]
                ],
                "repair": str(unverified_integrations[0].get("repair") or ""),
                "safe_to_share": True,
            }
        )
    if not_checked_integrations:
        items.append(
            {
                "id": "integrations_not_checked",
                "severity": "info",
                "summary": (
                    f"{len(not_checked_integrations)} declared integration(s) were not checked: "
                    "this command ran out of credential-read time. Nothing is known to be wrong."
                ),
                "evidence": [
                    f"{item['provider']}:{item['state']}" for item in not_checked_integrations[:5]
                ],
                "repair": str(not_checked_integrations[0].get("repair_command") or ""),
                "safe_to_share": True,
            }
        )
    if broken_integrations:
        items.append(
            {
                "id": "unhealthy_integrations",
                "severity": "warn",
                "summary": f"{len(broken_integrations)} declared integration(s) need repair.",
                "evidence": [
                    f"{item['provider']}:{item['state']}" for item in broken_integrations[:5]
                ],
                "repair": str(broken_integrations[0].get("repair_command") or "mb connect doctor"),
                "safe_to_share": True,
            }
        )
    if not report["since_last_check"]["marker_gitignore"]["ok"]:
        items.append(
            {
                "id": "status_marker_not_gitignored",
                "severity": "info",
                "summary": "The local status marker is not ignored by git yet.",
                "evidence": [LAST_STATUS_SEEN_GITIGNORE_ENTRY],
                "repair": report["since_last_check"]["marker_gitignore"]["repair"],
                "safe_to_share": True,
            }
        )
    return {
        "ok": not any(item["severity"] == "error" for item in items),
        "summary": {
            "total": len(items),
            "errors": len([item for item in items if item["severity"] == "error"]),
            "warnings": len([item for item in items if item["severity"] == "warn"]),
            "info": len([item for item in items if item["severity"] == "info"]),
        },
        "items": items,
    }


def _business_memory_readiness(report: dict[str, Any]) -> dict[str, Any]:
    repo = report.get("repo") or {}
    if not repo.get("looks_like_mainbranch_repo"):
        return {
            "state": "not_ready",
            "summary": (
                "Business memory is not available until this folder is a Main Branch business repo."
            ),
            "signals": ["repo.looks_like_mainbranch_repo=false"],
            "safe_to_share": True,
        }

    signals: list[str] = []
    validation = report.get("validation") or {}
    validation_summary = validation.get("summary") or {}
    if validation_summary.get("errors", 0):
        signals.append("validation.errors")
        return {
            "state": "blocked",
            "summary": (
                "Business memory has validation blockers; repo/runtime readiness does "
                "not mean the business context is complete."
            ),
            "signals": signals,
            "safe_to_share": True,
        }

    onboarding_summary = (report.get("onboarding") or {}).get("summary") or {}
    if onboarding_summary.get("status") == "in_progress":
        missing = list(onboarding_summary.get("missing_inputs") or [])[:5]
        signals.append("onboarding.summary.status=in_progress")
        return {
            "state": "needs_input",
            "summary": (
                f"{onboarding_summary.get('completed_required', 0)}/"
                f"{onboarding_summary.get('total_required', 0)} required onboarding "
                "inputs are complete; runtime can be ready while business memory still "
                "needs profile inputs."
            ),
            "signals": [*signals, *[str(item) for item in missing]],
            "next_action": str(
                onboarding_summary.get("next_recommended_action")
                or "Run `mb onboard status` to resume onboarding."
            ),
            "safe_to_share": True,
        }

    file_contracts = (validation.get("file_contracts") or {}).get("findings") or []
    if file_contracts:
        first = file_contracts[0]
        signals.append("validation.file_contracts.findings")
        return {
            "state": "needs_context",
            "summary": str(
                first.get("owner_message")
                or first.get("message")
                or "A business file is present but still needs clearer operating context."
            ),
            "signals": signals,
            "next_action": str(first.get("recommended_route") or "mb-think"),
            "safe_to_share": bool(first.get("safe_to_share", True)),
        }

    drift = report.get("drift") or {}
    drift_summary = drift.get("summary") or {}
    if drift_summary.get("warnings", 0) or drift_summary.get("info", 0):
        signals.append("drift.items")
        return {
            "state": "needs_attention",
            "summary": (
                "Repo/runtime checks are usable, but business memory still has drift or "
                "follow-up signals to review."
            ),
            "signals": signals,
            "safe_to_share": True,
        }

    return {
        "state": "ready",
        "summary": (
            "Business memory has no onboarding, validation, or drift blockers in the "
            "current status facts."
        ),
        "signals": [],
        "safe_to_share": True,
    }


def _install_repair(mode: str) -> str:
    """Install repair copy that names the detected install mode's command (#965, #1028)."""
    command = REQUIRED_UPDATE_COMMANDS.get(mode)
    return f"Run `{command}`." if command else MODE_NEUTRAL_UPDATE_TEXT


def _readiness(report: dict[str, Any]) -> dict[str, Any]:
    checks = [
        {
            "name": "mainbranch_repo",
            "ok": bool(report["repo"]["looks_like_mainbranch_repo"]),
            "weight": 25,
            "repair": "Run `mb init` in a new business repo or cd into an existing one.",
        },
        {
            "name": "git_repo",
            "ok": bool(report["git"].get("inside_work_tree")),
            "weight": 20,
            "repair": "Run `git init` if this should be a business repo.",
        },
        {
            "name": "install",
            "ok": bool(report["install"]["ok"]) and report["update"]["severity"] != "required",
            "weight": 15,
            "repair": (report["update"]["command"] or MODE_NEUTRAL_UPDATE_TEXT)
            if report["update"]["severity"] == "required"
            else _install_repair(str(report["install"].get("mode") or "")),
        },
        {
            "name": "skill_wiring",
            "ok": bool(report["runtime"]["skill_wiring"]["ok"]),
            "weight": 25,
            "repair": report["runtime"]["skill_wiring"]["repair"],
        },
        {
            "name": "claude_code",
            "ok": bool(report["runtime"]["claude_code"]["found"]),
            "weight": 15,
            "repair": report["runtime"]["claude_code"]["repair"],
        },
    ]
    possible = sum(int(check["weight"]) for check in checks)
    score = sum(int(check["weight"]) for check in checks if check["ok"])
    next_actions = [str(check["repair"]) for check in checks if not check["ok"] and check["repair"]]

    if report["git"].get("dirty"):
        next_actions.append(
            "Review or commit the current git changes before handing work to an agent."
        )
    if report["brain"]["stale_decisions"]:
        next_actions.append("Review stale proposed/running decisions in `decisions/`.")
    if report["brain"].get("stale_research"):
        next_actions.append("Refresh or supersede stale research before relying on it.")
    bets = report["brain"].get("bets") or {}
    if bets.get("overdue"):
        next_actions.append("Close or update overdue active bets in `bets/`.")
    elif bets.get("due_soon"):
        next_actions.append("Review active bets with deadlines in the next 7 days.")
    relationship_health = report.get("relationship_health") or {}
    relationship_gaps = [
        gap
        for gap in relationship_health.get("gaps") or []
        if gap.get("id") not in relationships.INFO_GAPS_WITHOUT_DAILY_ACTIONS
    ]
    if relationship_gaps:
        first_gap = relationship_gaps[0]
        next_actions.append(
            str(
                first_gap.get("repair")
                or "Review relationship gaps with `mb status --verbose --peek`."
            )
        )
    playbook_health = report.get("playbook_health") or {}
    playbook_gaps = playbook_health.get("gaps") or []
    if playbook_gaps:
        first_gap = playbook_gaps[0]
        next_actions.append(
            str(
                first_gap.get("repair")
                or "Review playbook health with `mb status --verbose --peek`."
            )
        )
    onboarding_summary = (report.get("onboarding") or {}).get("summary") or {}
    if onboarding_summary.get("status") == "in_progress":
        next_actions.append(
            str(
                onboarding_summary.get("next_recommended_action")
                or "Run `mb onboard status` to resume onboarding."
            )
        )
    integration_repairs = [
        item
        for item in (report.get("integrations") or {}).get("providers", [])
        if item.get("configured", item.get("connected"))
        and not item["ok"]
        and item.get("state") not in {connect_mod.UNVERIFIED_STATE, connect_mod.NOT_CHECKED_STATE}
    ]
    for item in integration_repairs[:3]:
        command = str(item.get("repair_command") or "mb connect doctor")
        next_actions.append(f"Repair {item['provider']} integration: `{command}`.")
    marker_gitignore = (report.get("since_last_check") or {}).get("marker_gitignore") or {}
    if marker_gitignore and not marker_gitignore.get("ok") and marker_gitignore.get("repair"):
        next_actions.append(str(marker_gitignore["repair"]))
    github_context = report["github"].get("context") or {}
    if github_context and not github_context.get("ok"):
        command = str(github_context.get("repair_command") or "gh auth login")
        next_actions.append(f"Repair GitHub context: `{command}`.")
    elif not report["github"]["authenticated"]:
        next_actions.append("Run `gh auth login` to include assigned issues and shipped PRs.")
    if not next_actions:
        next_actions.append("Run `claude` in this repo, then `/mb-start`.")

    percent = round((score / possible) * 100) if possible else 0
    if percent >= 85:
        level = "ready"
    elif percent >= 60:
        level = "needs_attention"
    else:
        level = "not_ready"
    business_memory = _business_memory_readiness(report)
    return {
        "score": percent,
        "level": level,
        "summary": (
            f"Repo/runtime readiness is {level} at {percent}/100. "
            f"Business memory is {business_memory['state']}."
        ),
        "dimensions": {
            "repo_runtime": {
                "score": percent,
                "level": level,
                "summary": "Repo shape, git, install, and runtime handoff checks.",
                "safe_to_share": True,
            },
            "business_memory": business_memory,
        },
        "checks": checks,
        "next_actions": next_actions[:5],
    }


def run(
    path: str = ".",
    *,
    update_marker: bool = True,
    validation_cross_refs: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic daily briefing report."""
    repo_path = Path(path).resolve()
    current_time = now or _utc_now()
    generated_at = _format_timestamp(current_time)
    repo_shape = _looks_like_mainbranch_repo(repo_path)
    git = _git_info(repo_path)
    update = package_update_status(repo_path)
    team_facts = team.facts(repo_path)
    github = _github(repo_path, git, team_facts=team_facts)
    brain = _brain(repo_path)
    topology_payload = topology_mod.collect(
        str(repo_path),
        git_remote=str(git.get("remote") or ""),
    )
    push_report = brain["pushes"]
    marker = _read_last_seen_marker(repo_path)
    report: dict[str, Any] = {
        "schema_version": STATUS_SCHEMA_VERSION,
        "schema": _schema(),
        "generated_at": generated_at,
        "ok": True,
        "repo": {"path": str(repo_path), **repo_shape},
        "install": _install(),
        "update": update,
        "runtime": _runtime(repo_path),
        "git": git,
        "git_activity": _git_recent_activity(repo_path, git),
        "journal": journal_mod.collect(repo_path, limit=12, since="14 days ago"),
        "brain": brain,
        "pushes": push_report["records"],
        "active_pushes": push_report["active"],
        "push_count": push_report["count"],
        "canonical_push_count": push_report["canonical_count"],
        "campaigns": push_report["legacy_campaigns"],
        "active_campaigns": push_report["active_legacy_campaigns"],
        "campaign_count": push_report["legacy_campaign_count"],
        "deprecated_campaign_keys": True,
        "push_compatibility": push_report["compatibility"],
        "vocabulary": vocabulary.facts(repo_path),
        "team": team_facts,
        "usage": usage_mod.status_view(repo=repo_path, now=current_time),
        "books": books_mod.readiness(repo_path),
        "onboarding": onboard_mod.onboarding_status(repo_path),
        "integrations": connect_mod.status_all(repo_path, github=github.get("context")),
        "measurement": _measurement(repo_path),
        "github": github,
    }
    report["content_strategy"] = content_strategy_mod.facts(
        repo_path,
        today=current_time.date(),
    )
    report["relationship_health"] = _relationship_health(
        repo_path,
        brain=brain,
        today=current_time.date(),
    )
    stranded_gap = _stranded_record_gap(repo_path, git, now=current_time)
    if stranded_gap is not None:
        health = report["relationship_health"]
        health["gaps"].insert(0, stranded_gap)
        health["summary"]["gaps"] += 1
        health["summary"]["warnings"] += 1
        health["summary"]["records_stranded_on_branches"] = stranded_gap["count"]
        health["ok"] = False
    report["playbook_health"] = _playbook_health(repo_path, brain=brain)
    report["money_path"] = _money_path(repo_path, report)
    report["since_last_check"] = _since_last_check(
        repo_path,
        marker=marker,
        git=git,
        brain=brain,
        generated_at=generated_at,
    )
    report["validation"] = _validation_status(repo_path, cross_refs=validation_cross_refs)
    report["drift"] = _drift(report)
    report["topology"] = {
        "schema": topology_payload["schema"],
        "safe_to_share": True,
        "summary": topology_payload["summary"],
        "registry": topology_payload["registry"],
        "descriptor": topology_payload["descriptor"],
        "current_repo": topology_payload["current_repo"],
        "repo_boundary": topology_payload["repo_boundary"],
        "child_counts": topology_payload["child_counts"],
        "restricted_repos": topology_payload["restricted_repos"],
        "findings": topology_payload["findings"],
        "local": {
            "repo_path": str(repo_path),
            "safe_to_share": False,
        },
    }
    report["readiness"] = _readiness(report)
    report["ranked_actions"] = ranker_mod.rank_status_report(report)
    report["ok"] = report["readiness"]["level"] != "not_ready"
    report["marker_update"] = (
        _write_last_seen_marker(repo_path, report)
        if update_marker
        else {
            "attempted": False,
            "ok": False,
            "reason": "disabled",
            "path": LAST_STATUS_SEEN_RELATIVE_PATH.as_posix(),
        }
    )
    return report


_QUALIFY_COMMAND_KEYS = {"command", "repair_command", "update_check_command", "next_command"}
_QUALIFY_PROSE_KEYS = {"repair", "operator_summary", "top_repair", "top_operator_summary"}
_QUALIFY_LIST_KEYS = {"next_steps"}
# Diagnostic copies, the command that was run, and Codex guidance keep their text.
_QUALIFY_SKIP_KEYS = {
    "raw",
    "result",
    "mb_command",
    "workflow_inventory",
    "fact_commands",
    "missing_markers",
    "smoke_command",
}


_BUSINESS_REPO_TAIL = " from the business repo."


def _qualify_text(value: str, repo: Path) -> str:
    """A command line or a sentence with backticked `mb` commands, naming the repo."""
    from mb import doctor  # doctor imports onboard and codex, which status also imports

    qualified = doctor._qualify_field(value, repo)
    if qualified == value:
        qualified = doctor._qualify_prose(value, repo)
    if qualified != value and qualified.endswith(_BUSINESS_REPO_TAIL):
        # The commands now name the repo, so "from the business repo" is redundant.
        qualified = qualified[: -len(_BUSINESS_REPO_TAIL)] + "."
    return qualified


def qualify_commands(report: dict[str, Any], repo: Path) -> dict[str, Any]:
    """Name the business repo in the suggested commands `mb status` prints (#1083).

    Run from another folder, a bare `mb skill link --repo .` would act on that
    folder. The same words `mb doctor` uses are rewritten here, at output time,
    so `mb start` and the dashboard keep reading the source text. Inside the
    repo nothing changes.
    """
    if not repo_flag(repo):
        return report

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _QUALIFY_SKIP_KEYS:
                    continue
                if key in _QUALIFY_COMMAND_KEYS | _QUALIFY_PROSE_KEYS and isinstance(value, str):
                    node[key] = _qualify_text(value, repo)
                elif key in _QUALIFY_LIST_KEYS and isinstance(value, list):
                    node[key] = [
                        _qualify_text(item, repo) if isinstance(item, str) else item
                        for item in value
                    ]
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(report)
    qualify_action_list(report.get("readiness"), repo)
    return report


def qualify_start_commands(report: dict[str, Any], repo: Path) -> dict[str, Any]:
    """The same rule for `mb start`: its command fields and its own `next_actions`.

    Applied after the report is built (and after any launch), so what ran is
    never rewritten.
    """
    qualify_commands(report, repo)
    qualify_action_list(report, repo)
    return report


def qualify_action_list(owner: Any, repo: Path, key: str = "next_actions") -> None:
    """Name the repo in one owned list of next actions, leaving other `next_actions` alone.

    `ads`, `launch`, `update` and Codex guidance carry their own `next_actions`
    (some with `<site-repo>` placeholders), so the list is named by its owner.
    """
    if not repo_flag(repo) or not isinstance(owner, dict) or not isinstance(owner.get(key), list):
        return
    owner[key] = [
        _qualify_text(item, repo) if isinstance(item, str) else item for item in owner[key]
    ]


def render_human(
    report: dict[str, Any],
    *,
    verbose: bool = False,
    no_color: bool = False,
) -> None:
    """Print a concise terminal briefing."""
    from rich.console import Console

    console = Console(no_color=no_color)
    repo = report["repo"]
    git = report["git"]
    runtime = report["runtime"]
    brain = report["brain"]
    onboarding = report.get("onboarding") or {}
    integrations = report.get(
        "integrations",
        {"summary": {"configured": 0, "healthy": 0, "needs_repair": 0}, "providers": []},
    )
    github = report["github"]
    readiness = report["readiness"]
    since = report.get("since_last_check") or {}
    drift = report.get("drift") or {"summary": {"total": 0}, "items": []}
    relationship_health = report.get("relationship_health") or {
        "summary": {"gaps": 0},
        "gaps": [],
    }
    playbook_health = report.get("playbook_health") or {
        "summary": {"gaps": 0},
        "gaps": [],
    }

    console.print(f"\n[bold]mb status[/bold]  {repo['path']}")
    usage = report.get("usage") or {}
    if usage.get("configured") or usage.get("errors"):
        console.print(usage_mod.status_line(usage), markup=False)
    alert = format_update_alert(report.get("update", {}))
    if alert:
        console.print(alert)
        console.print()
    console.print(
        f"[bold]{readiness['level'].replace('_', ' ')}[/bold]  {readiness['score']}/100\n"
    )
    business_memory = (readiness.get("dimensions") or {}).get("business_memory") or {}
    if business_memory:
        console.print(
            "[bold]Business memory[/bold] "
            f"{business_memory.get('state', 'unknown')}: "
            f"{business_memory.get('summary', '')}"
        )

    since_summary = since.get("summary") or {}
    if since.get("first_run"):
        console.print(
            f"[bold]Since last check[/bold] first run; recording {since.get('marker_path')}."
        )
    else:
        previous_seen = str(since.get("previous_seen_at") or "unknown")
        console.print(
            "[bold]Since last check[/bold] "
            f"{since_summary.get('commits', 0)} commit(s), "
            f"{since_summary.get('files_changed', 0)} tracked file change(s), "
            f"{since_summary.get('dirty_files', 0)} dirty file(s), "
            f"{since_summary.get('brain_count_changes', 0)} brain count change(s) "
            f"since {previous_seen}"
        )
    if since.get("error"):
        console.print(f"  [yellow]degraded:[/yellow] {since['error']}")
    since_journal = since.get("journal") or {}
    since_groups = since_journal.get("groups") or []
    if since_groups:
        console.print("  journal:")
        for group in since_groups[:3]:
            console.print(f"  - {group.get('label', 'Activity')}: {group.get('count', 0)} event(s)")
            if verbose:
                for summary in (group.get("summaries") or [])[:3]:
                    console.print(f"    - {summary}")
    elif not since.get("first_run") and since_journal.get("available") is False:
        console.print("  [yellow]journal unavailable[/yellow]")

    drift_summary = drift.get("summary") or {}
    if drift_summary.get("total", 0):
        console.print(
            "[bold]Drift[/bold] "
            f"{drift_summary.get('errors', 0)} error(s), "
            f"{drift_summary.get('warnings', 0)} warning(s), "
            f"{drift_summary.get('info', 0)} info"
        )
        for item in (drift.get("items") or [])[:5]:
            console.print(f"  - {item['severity']}: {item['summary']}")
            if verbose and item.get("repair"):
                console.print(f"    next: {item['repair']}")
    else:
        console.print("[bold]Drift[/bold] no stale or broken status signals detected")

    relationship_summary = relationship_health.get("summary") or {}
    if relationship_summary.get("gaps", 0):
        console.print(
            "[bold]Relationship health[/bold] "
            f"{relationship_summary.get('warnings', 0)} warning(s), "
            f"{relationship_summary.get('info', 0)} info"
        )
        for gap in (relationship_health.get("gaps") or [])[:3]:
            console.print(f"  - {gap['summary']}")
            if verbose and gap.get("repair"):
                console.print(f"    next: {gap['repair']}")
    else:
        console.print("[bold]Relationship health[/bold] no actionable business-link gaps detected")

    playbook_summary = playbook_health.get("summary") or {}
    if playbook_summary.get("gaps", 0):
        console.print(
            "[bold]Playbook health[/bold] "
            f"{playbook_summary.get('warnings', 0)} warning(s), "
            f"{playbook_summary.get('info', 0)} info"
        )
        for gap in (playbook_health.get("gaps") or [])[:3]:
            console.print(f"  - {gap['summary']}")
            if verbose and gap.get("repair"):
                console.print(f"    next: {gap['repair']}")

    repo_mark = (
        "[green]yes[/green]" if repo["looks_like_mainbranch_repo"] else "[yellow]no[/yellow]"
    )
    branch = git.get("branch") or "(unknown)"
    dirty = "dirty" if git.get("dirty") else "clean"
    if not git.get("inside_work_tree"):
        branch = "not a git repo"
        dirty = str(git.get("error") or "")
    console.print(
        f"[bold]Repo[/bold] {repo_mark} Main Branch repo  branch: {branch}  state: {dirty}"
    )
    console.print(f"[bold]Install[/bold] {report['install']['detail']}")

    topology = report.get("topology") or {}
    topology_summary = topology.get("summary") or {}
    topology_registry = topology.get("registry") or {}
    topology_current = topology.get("current_repo") or {}
    topology_counts = topology.get("child_counts") or {}
    if not topology_summary.get("registry_found"):
        console.print("[bold]Business map[/bold] no core/operations/repo-topology.md yet")
    elif not topology_summary.get("registry_ok"):
        console.print("[bold]Business map[/bold] [yellow]registry present but unparsable[/yellow]")
    else:
        display_name = topology_registry.get("business_display_name") or "(no display name)"
        total_children = topology_counts.get("total", 0)
        restricted = topology_summary.get("restricted_repo_count", 0)
        suffix = f", restricted {restricted}" if restricted else ""
        console.print(
            f"[bold]Business map[/bold] {display_name} — {total_children} child repo(s){suffix}"
        )
    role = topology_current.get("role") or ""
    role_suggestion = topology_current.get("role_suggestion") or ""
    if topology_current.get("matched"):
        identifier = topology_current.get("slug") or topology_current.get("remote_full_name") or "?"
        console.print(f"  this repo: {role or '?'} ({identifier})")
        if role and role != "business":
            console.print(
                "  [dim]child repo — strategy and operating memory "
                "(core/, bets/, pushes/) live in the parent hub[/dim]"
            )
    elif role:
        console.print(f"  this repo: {role}")
    elif not topology_current.get("is_hub"):
        hint = f" (looks like a {role_suggestion} repo)" if role_suggestion else ""
        console.print(f"  [yellow]this repo has no topology role declared{hint}[/yellow]")
        console.print(
            "  [dim]set role in .mainbranch/repo.json or the hub registry — "
            "see docs/child-repo-descriptors.md[/dim]"
        )
    if verbose:
        topology_findings = topology.get("findings") or []
        shown = 0
        for finding in topology_findings:
            severity = finding.get("severity", "")
            if severity not in {"warn", "error"}:
                continue
            console.print(f"  - {severity}: {finding.get('summary', '')}")
            shown += 1
            if shown >= 3:
                break

    claude = runtime["claude_code"]
    skills = runtime["skill_wiring"]
    codex = runtime.get("codex_cli") or {}
    claude_mark = "[green]found[/green]" if claude["found"] else "[yellow]missing[/yellow]"
    skill_mark = "[green]wired[/green]" if skills["ok"] else "[yellow]missing[/yellow]"
    codex_label = codex_mod.human_readiness_label(codex)
    codex_style = "green" if codex_label == "ready" else "yellow"
    codex_mark = f"[{codex_style}]{codex_label}[/{codex_style}] global skills"
    console.print(
        f"[bold]Runtime[/bold] Claude Code: {claude_mark}  skills: {skill_mark}  "
        f"Codex: {codex_mark}"
    )

    for warning in skills.get("plugin", {}).get("warnings", []):
        console.print("warning: " + warning, markup=False)

    integration_summary = integrations["summary"]
    if integration_summary["configured"]:
        integration_line = (
            "[bold]Integrations[/bold] "
            f"configured {integration_summary['configured']}  "
            f"healthy {integration_summary['healthy']}  "
            f"needs repair {integration_summary['needs_repair']}"
        )
        if integration_summary.get("unverified"):
            integration_line += f"  unverified {integration_summary['unverified']}"
        console.print(integration_line)
        for item in integrations.get("providers", []):
            if not item["ok"] and verbose:
                console.print(
                    f"  - {item['provider']}: {item['state']}  next: {item['repair_command']}"
                )

    measurement = report.get("measurement") or {}
    if measurement.get("available"):
        console.print(
            f"[bold]Measurement[/bold] {measurement.get('state')}  {measurement.get('summary')}"
        )
        google_ads = measurement.get("google_ads")
        if isinstance(google_ads, dict) and google_ads:
            words = [
                GOOGLE_ADS_STATUS_WORDS.get(str(value), str(value).replace("_", " "))
                for value in google_ads.values()
            ]
            facts = measurement.get("facts") or {}
            if google_ads.get("google_ads_plan") == "placeholder" and not facts.get(
                "primary_conversions"
            ):
                # A placeholder id hides the plan check; name the missing plan too.
                words.append("conversion plan missing")
            console.print(f"  Google Ads: {'; '.join(words)}")
        if verbose and measurement.get("repair"):
            console.print(f"  next: {measurement['repair']}")

    counts = brain["counts"]
    vocabulary_report = report.get("vocabulary") or {}
    vocabulary_terms = (
        vocabulary_report.get("terms", {}) if isinstance(vocabulary_report, dict) else {}
    )
    push_terms = vocabulary_terms.get("push", {}) if isinstance(vocabulary_terms, dict) else {}
    push_plural = str(push_terms.get("plural") or "pushes")
    pushes_count = counts.get("pushes", 0)
    campaigns_count = counts.get("campaigns", 0)
    pushes_segment = f"{push_plural} {pushes_count}"
    if campaigns_count:
        pushes_segment += f" (legacy campaigns {campaigns_count})"
    console.print(
        "[bold]Brain[/bold] "
        f"core {counts['core'] + counts['reference/core']}  "
        f"research {counts['research']}  decisions {counts['decisions']}  "
        f"bets {counts['bets']}  {pushes_segment}  "
        f"log {counts['log']}  documents {counts['documents']}"
    )

    if isinstance(vocabulary_report, dict):
        vocabulary_errors = vocabulary_report.get("errors") or []
        vocabulary_warnings = vocabulary_report.get("warnings") or []
        if vocabulary_report.get("ok") is False or vocabulary_errors:
            path = vocabulary_report.get("path") or "core/vocabulary.md"
            detail = vocabulary_errors[0] if vocabulary_errors else "malformed"
            console.print(
                f"[yellow]Vocabulary[/yellow] {path}: {detail} (using default push/pushes)"
            )
        elif vocabulary_warnings:
            path = vocabulary_report.get("path") or "core/vocabulary.md"
            console.print(f"[yellow]Vocabulary[/yellow] {path}: {vocabulary_warnings[0]}")

    if verbose and brain["recent_decisions"]:
        console.print("\n[bold]Recent decisions[/bold]")
        for item in brain["recent_decisions"][:3]:
            suffix = f" [{item['status']}]" if item["status"] else ""
            console.print(f"  - {item['date'] or item['updated_at'][:10]}  {item['title']}{suffix}")
    if verbose and brain["stale_decisions"]:
        console.print("[yellow]Stale proposed/running decisions[/yellow]")
        for item in brain["stale_decisions"][:3]:
            console.print(f"  - {item['path']} ({item['age_days']} days)")
    if verbose and brain.get("stale_research"):
        console.print("[yellow]Stale research[/yellow]")
        for item in brain["stale_research"][:3]:
            console.print(f"  - {item['path']} ({item['age_days']} days)")
    if verbose and brain["recent_research"]:
        console.print("\n[bold]Recent research[/bold]")
        for item in brain["recent_research"][:3]:
            console.print(f"  - {item['date'] or item['updated_at'][:10]}  {item['title']}")

    bets = brain.get("bets") or {}
    active_bets = bets.get("active") or []
    if active_bets:
        console.print("\n[bold]Active bets[/bold]")
        for item in active_bets[:3]:
            deadline = item.get("deadline") or "no deadline"
            stage = f", {item['stage']}" if item.get("stage") else ""
            console.print(f"  - {deadline}  {item['title']} [{item['status']}{stage}]")
    overdue_bets = bets.get("overdue") or []
    if overdue_bets:
        console.print("[yellow]Overdue active bets[/yellow]")
        for item in overdue_bets[:3]:
            console.print(f"  - {item['path']} ({item['days_overdue']} days overdue)")

    onboarding_summary = onboarding.get("summary") or {}
    if verbose and onboarding_summary.get("status") == "in_progress":
        console.print("\n[bold]Onboarding[/bold]")
        console.print(
            "  "
            f"{onboarding_summary.get('completed_required', 0)}/"
            f"{onboarding_summary.get('total_required', 0)} required steps complete"
        )
        missing = onboarding_summary.get("missing_inputs") or []
        if missing:
            console.print(f"  missing: {', '.join(missing[:5])}")
        console.print(f"  next: {onboarding_summary.get('next_recommended_action')}")

    journal = report.get("journal") or {}
    if verbose and journal.get("events"):
        console.print("\n[bold]Business journal[/bold]")
        for item in journal["events"][:5]:
            refs = item.get("refs") or []
            ref_label = f" refs {len(refs)}" if refs else ""
            console.print(
                f"  - {item.get('date')} {item.get('commit')}  {item.get('summary')}{ref_label}"
            )

    if verbose and report["git_activity"]["items"]:
        console.print("\n[bold]Recent git activity[/bold]")
        for item in report["git_activity"]["items"][:3]:
            files = ", ".join(item["files"][:2])
            if len(item["files"]) > 2:
                files += f" +{len(item['files']) - 2}"
            console.print(f"  - {item['date']} {item['commit']}  {item['subject']}  {files}")

    console.print("\n[bold]GitHub[/bold]")
    github_context = github.get("context") or {}
    if github_context and not github_context.get("ok"):
        console.print(f"  {github_context.get('summary')}")
        if github_context.get("repair_command"):
            console.print(f"  next: {github_context['repair_command']}")
    elif not github["available"]:
        console.print("  gh unavailable; skipping issues and PRs.")
    elif not github["authenticated"]:
        console.print("  gh not authenticated; run `gh auth login` to include business tasks.")
    else:
        summary = github.get("summary") or {}
        sections = github.get("sections") or {}
        assigned_count = summary.get("assigned_tasks", len(github.get("assigned_issues", [])))
        attention_count = summary.get(
            "attention_requests",
            len(github.get("review_requests", [])),
        )
        shipped_count = summary.get("shipped_this_week", len(github.get("recent_merged_prs", [])))
        console.print(
            f"  tasks assigned: {assigned_count}  "
            f"attention: {attention_count}  "
            f"open proposals: {summary.get('open_proposals', 0)}  "
            f"shipped this week: {shipped_count}"
        )
        assigned_tasks = sections.get("assigned_tasks") or github.get("assigned_issues", [])
        attention_requests = sections.get("attention_requests") or github.get("review_requests", [])
        open_proposals = sections.get("open_proposals") or []
        shipped = sections.get("shipped_this_week") or github.get("recent_merged_prs", [])
        blocked_or_stale = sections.get("blocked_or_stale_tasks") or []
        if verbose:
            for issue in assigned_tasks[:3]:
                console.print(f"  - task #{issue['number']}: {issue['title']}")
            for item in attention_requests[:3]:
                reason = item.get("reason", "Needs attention")
                console.print(f"  - attention #{item['number']}: {item['title']} ({reason})")
            for pr in open_proposals[:3]:
                console.print(f"  - proposal #{pr['number']}: {pr['title']}")
            for pr in shipped[:3]:
                console.print(f"  - shipped #{pr['number']}: {pr['what_shipped']}")
            for issue in blocked_or_stale[:3]:
                console.print(f"  - blocked/stale #{issue['number']}: {issue['title']}")
        for error in github["errors"][:2]:
            console.print(f"  [yellow]degraded:[/yellow] {error}")

    console.print("\n[bold]Next[/bold]")
    ranked_actions = report.get("ranked_actions") or []
    if ranked_actions:
        for index, action in enumerate(ranked_actions[:3], start=1):
            title = str(action.get("title") or action.get("id") or "Next action")
            reason = str(action.get("reason") or "")
            command = str(action.get("command") or "")
            console.print(f"  {index}. {title}")
            if reason:
                console.print(f"     why: {reason}")
            if command:
                console.print(f"     next: {command}")
    else:
        for action in readiness["next_actions"]:
            console.print(f"  - {action}")
    console.print()
