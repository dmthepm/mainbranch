"""``mb status`` — cheap daily briefing for a Main Branch repo."""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

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
from mb import validate as validate_mod
from mb.engine import install_mode, link_status, repo_flag
from mb.freshness import (
    MODE_NEUTRAL_UPDATE_TEXT,
    REQUIRED_UPDATE_COMMANDS,
    format_update_alert,
    package_update_status,
)
from mb.json_result import json_default

IMPORTANT_DIRS = (
    "core",
    "reference/core",
    "research",
    "decisions",
    "bets",
    "pushes",
    "campaigns",
    "log",
    "documents",
)
STATUS_SCHEMA_VERSION = "1.0"
LAST_STATUS_SEEN_RELATIVE_PATH = Path(".mb") / "last-status-seen.json"
LAST_STATUS_SEEN_GITIGNORE_ENTRY = ".mb/last-status-seen.json"
STALE_DECISION_DAYS = 14
UNCODIFIED_DECISION_DAYS = 7
# Plain words for the Google Ads statuses mb site check reports.
GOOGLE_ADS_STATUS_WORDS = {
    "declared": "customer and conversion plan declared",
    "partly_declared": "customer declared, conversion plan missing",
    "placeholder": "customer ID is a placeholder",
    "not_checked": "account connection not checked",
    "no_evidence_recorded": "no conversion evidence recorded",
}
STALE_RESEARCH_DAYS = 45
UNLINKED_RESEARCH_DAYS = 30
ACTIVE_BET_STATUSES = {"open", "paused"}
BET_APPETITE_TIERS = {"trivial", "small", "material", "strategic"}
BET_SIGNAL_COMPARATORS = {"<", "<=", "==", ">=", ">", "!="}
ACTIVE_PUSH_STATUSES = {"planned", "active", "paused"}
COMPLETED_PUSH_STATUSES = {"completed"}
LIVE_OFFER_STATUSES = {"accepted", "graduated", "running", "scaling"}
STALE_PUSH_DAYS = 14
PUSH_STATUSES_EXPECTING_PLAYBOOK = {"planned", "active"}
PLAYBOOK_STATUSES_NEEDING_ATTENTION = {"draft", "planned"}
PLAYBOOK_APPROVAL_STATUSES_NEEDING_ATTENTION = {"needed", "rejected", ""}
PLAYBOOK_PROVIDER_BOUNDARIES_NEEDING_ATTENTION = {
    "plan-only",
    "external-manual",
    "manual-provider",
}
MONEY_PATH_SCHEMA_VERSION = "1.0"
MONEY_PATH_LEVEL_LABELS = {
    0: "missing",
    1: "stated",
    2: "structured",
    3: "evidence_backed",
    4: "field_tested",
    5: "instrumented",
}
MONEY_PATH_COMPONENTS = (
    "customer_progress",
    "offer",
    "audience",
    "proof",
    "product_ladder",
    "cta_path",
    "channel_strategy",
    "active_push",
    "playbook",
    "page_readiness",
    "outcome_feedback_loop",
)
OFFER_GUARDRAIL_KEYWORDS = {
    "audience": ("audience", "who this is for", "who they are", "buyer", "customer"),
    "transformation": ("transformation", "outcome", "before", "after", "result"),
    "mechanism": ("mechanism", "method", "how it works", "process"),
    "price_value": ("pricing", "price", "value", "$", "investment"),
    "proof": ("proof", "testimonial", "case study", "typicality", "evidence"),
    "risk_reversal": ("risk reversal", "guarantee", "refund", "trial", "pilot"),
    "objections": ("objection", "concern", "blocker", "why not"),
    "reason_to_act": ("urgency", "reason to act", "timing", "capacity", "deadline"),
    "next_step": ("next step", "cta", "call", "apply", "buy", "checkout", "join", "book"),
}
AUDIENCE_SIGNAL_KEYWORDS = {
    "customer_progress": ("progress", "job", "trying to", "desired outcome", "what they want"),
    "buyer_language": ("what they say", "language", "phrases", "interviews", "reviews", "dms"),
    "pain_or_gain": ("pain", "gain", "escaping", "status quo", "problem"),
    "objections": ("objection", "concern", "trust", "time", "price", "fit"),
}
CUSTOMER_PROGRESS_KEYWORDS = {
    "job_to_be_done": ("job", "trying to", "progress", "switching", "hire"),
    "pain": ("pain", "problem", "stuck", "struggle", "escaping", "status quo"),
    "gain": ("gain", "desired outcome", "result", "better", "wants"),
    "language": ("what they say", "language", "phrases", "interviews", "reviews", "dms"),
}
CTA_KEYWORDS = (
    "next step",
    "cta",
    "call to action",
    "book",
    "apply",
    "buy",
    "checkout",
    "join",
    "subscribe",
    "download",
    "waitlist",
    "sign up",
    "schedule",
)
PRODUCT_LADDER_REQUIREMENTS = {
    "entry_step": ("entry", "first step", "front end", "lead magnet"),
    "ascension_path": ("ascension", "cross-sell", "upgrade", "feeds from", "feeds into"),
    "retention_offer": ("retention", "renewal", "continuity", "membership", "community"),
}
CHANNEL_KEYWORDS = (
    "paid",
    "organic",
    "email",
    "site",
    "community",
    "partner",
    "outreach",
    "content",
    "ads",
    "search",
)
PROOF_BEFORE_KEYWORDS = (
    "before",
    "previously",
    "used to",
    "started with",
    "came in",
    "stuck",
)
PROOF_OUTCOME_KEYWORDS = (
    "after",
    "outcome",
    "result",
    "shipped",
    "booked",
    "won",
    "increased",
    "reduced",
    "saved",
)
PROOF_TIMEFRAME_KEYWORDS = (
    "time to outcome",
    "within",
    "deadline",
    "review period",
)
PROOF_METRIC_KEYWORDS = (
    "%",
    "$",
    "revenue",
    "calls",
    "signups",
    "leads",
    "conversion",
    "sales",
    "hours",
)
PROOF_MECHANISM_KEYWORDS = (
    "mechanism",
    "method",
    "process",
    "because",
    "using",
    "through",
    "workflow",
)
PROOF_OBJECTION_KEYWORDS = (
    "objection",
    "concern",
    "skeptical",
    "worried",
    "hesitated",
    "trust",
    "time",
    "price",
)
PROOF_PERMISSION_KEYWORDS = (
    "permissioned",
    "approved for public",
    "public: true",
    "safe to share",
)
PROOF_PERMISSION_NEGATIVE_RE = re.compile(
    r"\b(?:not|no|without|pending|needs?|awaiting|unapproved)\b.{0,40}"
    r"\b(?:permission|permissioned|approved|public|share|sharing)\b"
    r"|\b(?:permission|permissioned|approved|public|share|sharing)\b.{0,40}"
    r"\b(?:not|no|without|pending|needed|awaiting|unapproved|false)\b"
)
PROOF_AVERAGE_CASE_KEYWORDS = (
    "average",
    "median",
    "typical",
    "most users",
    "usual",
    "common case",
)
PROOF_CAVEAT_KEYWORDS = ("caveat", "constraint", "not guaranteed", "depends", "varies")
PROOF_FAILURE_CONTEXT_KEYWORDS = (
    "failure",
    "fails",
    "does not work",
    "doesn't work",
    "when this breaks",
    "poor fit",
)
PROOF_SOURCE_KEYWORDS = (
    "source",
    "customer language",
    "sales call",
    "interview",
    "conversion",
    "outcome log",
    "recorded",
)


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


def _run_command(args: list[str], cwd: Path | None = None, timeout: float = 3.0) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
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


def _read_frontmatter(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            first = handle.readline()
            if first.strip() != "---":
                return {}
            lines: list[str] = []
            for line in handle:
                if line.strip() == "---":
                    break
                lines.append(line)
            else:
                return {}
    except OSError:
        return {}
    raw = "".join(lines).strip()
    try:
        parsed = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _read_markdown_text(path: Path, *, limit: int = 80_000) -> str:
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except OSError:
        return ""


def _relative_existing_paths(repo: Path, candidates: list[str]) -> list[str]:
    return [rel for rel in candidates if (repo / rel).is_file()]


def _money_path_label(level: int) -> str:
    return MONEY_PATH_LEVEL_LABELS.get(level, "missing")


def _money_path_evidence(
    *,
    kind: str,
    path: str,
    summary: str,
    field: str = "",
) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": path,
        "field": field,
        "summary": summary,
    }


def _money_path_object(
    *,
    level: int,
    status: str,
    summary: str,
    paths: list[str],
    missing: list[str],
    evidence: list[dict[str, Any]] | None = None,
    references: list[str] | None = None,
    recommended_route: str = "/mb-think",
    confidence: str = "high",
) -> dict[str, Any]:
    resolved_level = max(0, min(5, int(level)))
    return {
        "level": resolved_level,
        "label": _money_path_label(resolved_level),
        "status": status,
        "summary": summary,
        "paths": paths[:10],
        "missing": missing[:10],
        "evidence": (evidence or [])[:10],
        "references": references or [],
        "recommended_route": recommended_route,
        "confidence": confidence,
        "safe_to_share": True,
    }


def _keyword_hits(text: str, groups: dict[str, tuple[str, ...]]) -> list[str]:
    lowered = text.lower()
    return [
        group
        for group, keywords in groups.items()
        if any(keyword in lowered for keyword in keywords)
    ]


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _markdown_body_without_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return "\n".join(lines[index + 1 :]).strip()
    return text.strip()


def _offer_slug_from_path(path: str) -> str:
    match = re.match(r"core/offers/([^/]+)/offer\.md$", path)
    return match.group(1) if match else ""


TestimonialEntry = str | dict[str, Any]


def _known_offer_refs(offer_paths: list[str]) -> dict[str, str]:
    refs: dict[str, str] = {}
    for path in offer_paths:
        refs[path] = path
        slug = _offer_slug_from_path(path)
        if slug:
            refs[slug] = path
            refs[f"core/offers/{slug}"] = path
            refs[f"core/offers/{slug}/"] = path
            refs[f"core/offers/{slug}/offer.md"] = path
    return refs


def _normalize_offer_ref(value: Any, offer_paths: list[str]) -> str:
    if not isinstance(value, str):
        return ""
    clean = value.strip().strip("\"'")
    if not clean:
        return ""
    clean = clean.removeprefix("./")
    return _known_offer_refs(offer_paths).get(clean, "")


def _proof_linked_offer_refs(repo: Path, proof_path: str, offer_paths: list[str]) -> set[str]:
    meta = _read_frontmatter(repo / proof_path)
    raw_refs = set(_coerce_string_list(meta.get("offer")))
    raw_refs.update(_coerce_string_list(meta.get("linked_offers")))
    refs = {
        normalized for ref in raw_refs if (normalized := _normalize_offer_ref(ref, offer_paths))
    }
    match = re.match(r"core/offers/([^/]+)/proof/", proof_path)
    if match and (
        normalized := _normalize_offer_ref(f"core/offers/{match.group(1)}/offer.md", offer_paths)
    ):
        refs.add(normalized)
    return {ref for ref in refs if ref}


def _testimonial_entries(text: str, meta: dict[str, Any]) -> list[TestimonialEntry]:
    entries: list[TestimonialEntry] = []
    frontmatter_entries = meta.get("testimonials")
    if isinstance(frontmatter_entries, list):
        for item in frontmatter_entries:
            if isinstance(item, dict):
                entries.append(item)
            elif isinstance(item, str) and item.strip():
                entries.append(item.strip())
    body = _markdown_body_without_frontmatter(text)
    sections = [
        section.strip()
        for section in re.split(r"(?m)^#{2,6}\s+", body)
        if section.strip() and len(section.strip()) >= 20
    ]
    if len(sections) > 1:
        entries.extend(sections)
    else:
        list_entries = [
            line.strip(" >-*")
            for line in body.splitlines()
            if re.match(r"^\s*(?:[-*]\s+|>\s*)", line) and len(line.strip(" >-*")) >= 20
        ]
        if list_entries:
            entries.extend(list_entries)
        else:
            cleaned = "\n".join(
                line for line in body.splitlines() if not line.strip().startswith("#")
            ).strip()
            if len(cleaned) >= 20:
                entries.append(cleaned)
    deduped: list[TestimonialEntry] = []
    seen: set[str] = set()
    for entry in entries:
        key = (
            json.dumps(entry, sort_keys=True, default=json_default)
            if isinstance(entry, dict)
            else entry.strip()
        )
        if key and key not in seen:
            deduped.append(entry)
            seen.add(key)
    return deduped


def _testimonial_text(entry: TestimonialEntry) -> str:
    if isinstance(entry, str):
        return entry
    values: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, str):
            values.append(value)
        elif isinstance(value, (int, float)):
            values.append(str(value))

    collect(entry)
    return " ".join(values)


def _truthy_structured_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "approved", "public", "permissioned"}
    return False


def _falsey_structured_value(value: Any) -> bool:
    if isinstance(value, bool):
        return not value
    if isinstance(value, str):
        return value.strip().lower() in {
            "false",
            "no",
            "not approved",
            "not permissioned",
            "pending",
            "private",
            "internal",
        }
    return False


def _testimonial_structured_permission_signal(entry: TestimonialEntry) -> bool | None:
    if not isinstance(entry, dict):
        return None
    permission_fields = {
        "public",
        "permissioned_public",
        "approved_for_public",
        "safe_to_share",
        "public_approved",
    }
    explicit_false = False
    for key, value in entry.items():
        normalized = str(key).strip().lower().replace("-", "_")
        if normalized not in permission_fields:
            continue
        if _truthy_structured_value(value):
            return True
        explicit_false = explicit_false or _falsey_structured_value(value)
    if explicit_false:
        return False
    return None


def _testimonial_text_permission_signal(text: str) -> bool:
    lowered = text.lower()
    if PROOF_PERMISSION_NEGATIVE_RE.search(lowered):
        return False
    return _contains_any(lowered, PROOF_PERMISSION_KEYWORDS)


def _testimonial_structured_offer_refs(entry: TestimonialEntry) -> list[str]:
    if not isinstance(entry, dict):
        return []
    refs: list[str] = []
    for key in ("offer", "linked_offer", "linked_offers"):
        refs.extend(_coerce_string_list(entry.get(key)))
    return refs


def _testimonial_explicit_offer_refs(text: str) -> list[str]:
    refs: list[str] = []
    for match in re.finditer(
        r"(?im)(?:^|\b)(?:offer|linked_offer|linked_offers)\s*:\s*(?:-\s*)?([^\n,;#]+)",
        text,
    ):
        refs.append(match.group(1).strip().strip("\"'`"))
    return refs


def _proof_text_has_timeframe(text: str) -> bool:
    lowered = text.lower()
    return bool(re.search(r"\b\d+\s+(?:day|days|week|weeks|month|months)\b", lowered)) or any(
        keyword in lowered for keyword in PROOF_TIMEFRAME_KEYWORDS
    )


def _proof_text_has_metric(text: str) -> bool:
    lowered = text.lower()
    return bool(
        re.search(r"(?:\d+%|\$\d+|\b\d+\s+(?:calls|signups|leads|sales|hours)\b)", lowered)
    ) or any(keyword in lowered for keyword in PROOF_METRIC_KEYWORDS)


def _testimonial_signal_counts(
    entries: list[TestimonialEntry],
    *,
    linked_offer_refs: set[str],
    offer_paths: list[str],
) -> dict[str, int]:
    counts = {
        "total": len(entries),
        "generic": 0,
        "specific": 0,
        "permissioned_public": 0,
        "specific_permissioned_public": 0,
        "linked_to_offer": 0,
        "with_before_state": 0,
        "with_outcome": 0,
        "with_timeframe": 0,
        "with_metric": 0,
        "with_mechanism": 0,
        "with_objection": 0,
    }
    has_path_offer_link = bool(linked_offer_refs & set(offer_paths))
    for entry in entries:
        entry_text = _testimonial_text(entry)
        lowered = entry_text.lower()
        has_before = _contains_any(lowered, PROOF_BEFORE_KEYWORDS)
        has_outcome = _contains_any(lowered, PROOF_OUTCOME_KEYWORDS)
        has_timeframe = _proof_text_has_timeframe(lowered)
        has_metric = _proof_text_has_metric(lowered)
        has_mechanism = _contains_any(lowered, PROOF_MECHANISM_KEYWORDS)
        has_objection = _contains_any(lowered, PROOF_OBJECTION_KEYWORDS)
        structured_permission = _testimonial_structured_permission_signal(entry)
        has_permission = (
            structured_permission
            if structured_permission is not None
            else _testimonial_text_permission_signal(entry_text)
        )
        explicit_offer_refs = _testimonial_structured_offer_refs(entry)
        explicit_offer_refs.extend(_testimonial_explicit_offer_refs(entry_text))
        has_entry_offer_link = any(
            _normalize_offer_ref(ref, offer_paths) for ref in explicit_offer_refs
        )
        has_offer_link = has_path_offer_link or has_entry_offer_link
        signals = [
            has_before,
            has_outcome,
            has_timeframe,
            has_metric,
            has_mechanism,
            has_objection,
        ]
        counts["with_before_state"] += int(has_before)
        counts["with_outcome"] += int(has_outcome)
        counts["with_timeframe"] += int(has_timeframe)
        counts["with_metric"] += int(has_metric)
        counts["with_mechanism"] += int(has_mechanism)
        counts["with_objection"] += int(has_objection)
        counts["permissioned_public"] += int(has_permission)
        counts["specific_permissioned_public"] += int(has_permission and any(signals))
        counts["linked_to_offer"] += int(has_offer_link)
        if any(signals):
            counts["specific"] += 1
        else:
            counts["generic"] += 1
    return counts


def _empty_proof_quality() -> dict[str, Any]:
    return {
        "testimonials": {
            "total": 0,
            "generic": 0,
            "specific": 0,
            "permissioned_public": 0,
            "specific_permissioned_public": 0,
            "linked_to_offer": 0,
            "with_before_state": 0,
            "with_outcome": 0,
            "with_timeframe": 0,
            "with_metric": 0,
            "with_mechanism": 0,
            "with_objection": 0,
        },
        "typicality": {
            "exists": False,
            "has_average_case": False,
            "has_caveats": False,
            "has_common_failure_context": False,
            "has_time_to_outcome": False,
        },
        "claim_links": {
            "linked_offers": [],
            "unsupported_offer_claims": [],
        },
        "public_marketing": {
            "ready": False,
            "status": "missing",
            "summary": "No testimonial proof is available for public marketing.",
            "missing": ["testimonials"],
            "next_action": "collect_testimonials",
        },
    }


def _proof_public_marketing_readiness(quality: dict[str, Any]) -> dict[str, Any]:
    testimonial_quality = quality.get("testimonials") or {}
    total = int(testimonial_quality.get("total") or 0)
    specific = int(testimonial_quality.get("specific") or 0)
    permissioned = int(testimonial_quality.get("permissioned_public") or 0)
    specific_permissioned = int(testimonial_quality.get("specific_permissioned_public") or 0)
    if total == 0:
        return {
            "ready": False,
            "status": "missing",
            "summary": "No testimonial proof is available for public marketing.",
            "missing": ["testimonials"],
            "next_action": "collect_testimonials",
        }
    if specific > 0 and specific_permissioned == 0:
        return {
            "ready": False,
            "status": "blocked",
            "summary": (
                "Specific proof exists for internal strategy, but no specific "
                "testimonial is permissioned for public marketing."
            ),
            "missing": ["permissioned_public_testimonials"],
            "next_action": "collect_public_permission",
        }
    if specific == 0:
        missing = ["specific_testimonials"]
        if permissioned == 0:
            missing.append("permissioned_public_testimonials")
        return {
            "ready": False,
            "status": "incomplete",
            "summary": (
                "Testimonials exist, but public marketing proof needs "
                "specific permissioned evidence."
            ),
            "missing": missing,
            "next_action": "strengthen_testimonials",
        }
    return {
        "ready": True,
        "status": "ready",
        "summary": "At least one specific testimonial is permissioned for public marketing.",
        "missing": [],
        "next_action": None,
    }


def _frontmatter_status(repo: Path, rel_path: str) -> str:
    return str(_read_frontmatter(repo / rel_path).get("status") or "").lower()


def _is_stub_content(repo: Path, rel_path: str) -> bool:
    status = _frontmatter_status(repo, rel_path)
    text = _read_markdown_text(repo / rel_path).lower()
    return status == "stub" or "public stub" in text or "[from state]" in text


def _parse_date(value: Any, fallback_path: Path) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            pass
    match = re.match(r"(\d{4}-\d{2}-\d{2})", fallback_path.name)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            return None
    return None


def _parse_explicit_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _relative_markdown_files(repo: Path, folder: str) -> list[Path]:
    root = repo / folder
    if not root.exists():
        return []
    return sorted(
        (path for path in root.rglob("*.md") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _file_summary(
    repo: Path, path: Path, frontmatter: dict[str, Any] | None = None
) -> dict[str, Any]:
    meta = frontmatter if frontmatter is not None else _read_frontmatter(path)
    item_date = _parse_date(meta.get("date"), path)
    try:
        rel = path.relative_to(repo).as_posix()
    except ValueError:
        rel = str(path)
    return {
        "path": rel,
        "title": _title_from_markdown(path),
        "date": item_date.isoformat() if item_date else "",
        "status": str(meta.get("status", "") or ""),
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
    }


def _title_from_markdown(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped.startswith("# "):
                    return stripped[2:].strip()
    except OSError:
        pass
    return path.stem.replace("-", " ")


def _brain(repo: Path) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for folder in IMPORTANT_DIRS:
        root = repo / folder
        counts[folder] = (
            sum(1 for path in root.rglob("*.md") if path.is_file()) if root.exists() else 0
        )

    decision_files = _relative_markdown_files(repo, "decisions")
    decisions: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    uncodified: list[dict[str, Any]] = []
    today = date.today()

    for path in decision_files:
        meta = _read_frontmatter(path)
        item = _file_summary(repo, path, meta)
        decisions.append(item)
        status = item["status"].lower()
        decision_date = _parse_date(meta.get("date"), path)
        if status in {"proposed", "running"} and decision_date is not None:
            age_days = (today - decision_date).days
            if age_days > STALE_DECISION_DAYS:
                stale_item = dict(item)
                stale_item["age_days"] = age_days
                stale.append(stale_item)
        # Accepted but never codified: the decision happened, the reference
        # files it should change did not — decision-vs-implementation drift.
        if status == "accepted" and decision_date is not None:
            age_days = (today - decision_date).days
            if age_days > UNCODIFIED_DECISION_DAYS:
                uncodified_item = dict(item)
                uncodified_item["age_days"] = age_days
                uncodified.append(uncodified_item)

    research_files = _relative_markdown_files(repo, "research")
    research: list[dict[str, Any]] = []
    stale_research: list[dict[str, Any]] = []
    for path in research_files:
        meta = _read_frontmatter(path)
        item = _file_summary(repo, path, meta)
        research.append(item)
        research_date = _parse_date(meta.get("date"), path)
        if research_date is not None:
            age_days = (today - research_date).days
            if age_days > STALE_RESEARCH_DAYS:
                stale_item = dict(item)
                stale_item["age_days"] = age_days
                stale_research.append(stale_item)
    bets = _bets(repo)
    push_facts = pushes_mod.facts(repo)

    return {
        "counts": counts,
        "recent_decisions": decisions[:5],
        "recent_decisions_total": len(decisions),
        "stale_decisions": stale[:5],
        "stale_decisions_total": len(stale),
        "uncodified_decisions": uncodified[:5],
        "uncodified_decisions_total": len(uncodified),
        "recent_research": research[:5],
        "recent_research_total": len(research),
        "stale_research": stale_research[:5],
        "stale_research_total": len(stale_research),
        "bets": bets,
        "pushes": push_facts,
    }


def _bet_summary(repo: Path, path: Path) -> dict[str, Any]:
    meta = _read_frontmatter(path)
    opened = _parse_date(meta.get("opened"), path)
    deadline = _parse_explicit_date(meta.get("deadline"))
    try:
        rel = path.relative_to(repo).as_posix()
    except ValueError:
        rel = str(path)
    channels = meta.get("channels")
    if not isinstance(channels, list):
        channels = []
    money_path = _bet_money_path_summary(meta, path)
    exit_criteria = _bet_exit_criteria(meta, today=date.today())
    return {
        "path": rel,
        "title": _title_from_markdown(path),
        "status": str(meta.get("status", "") or ""),
        "stage": str(meta.get("stage", "") or ""),
        "commitment": _bet_commitment_summary(meta),
        "opened": opened.isoformat() if opened else "",
        "deadline": deadline.isoformat() if deadline else "",
        "appetite": str(meta.get("appetite", "") or ""),
        "appetite_tier": _bet_appetite_tier(meta),
        "hypothesis": str(meta.get("hypothesis", "") or ""),
        "metric": str(meta.get("metric", "") or ""),
        "target": str(meta.get("target", "") or ""),
        "result": str(meta.get("result", "") or ""),
        "money_path": money_path,
        "exit_criteria": exit_criteria,
        "public": bool(meta.get("public", False)),
        "channels": [str(channel) for channel in channels if isinstance(channel, str)],
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
    }


def _bet_commitment_summary(meta: dict[str, Any]) -> dict[str, str] | None:
    raw = meta.get("commitment")
    if not isinstance(raw, dict):
        return None
    return {
        key: str(raw.get(key) or "").strip() for key in ("action", "cadence", "owner", "evidence")
    }


def _bet_appetite_tier(meta: dict[str, Any]) -> str:
    tier = meta.get("appetite_tier")
    if isinstance(tier, str) and tier.strip().lower() in BET_APPETITE_TIERS:
        return tier.strip().lower()
    appetite = meta.get("appetite")
    if isinstance(appetite, str) and appetite.strip().lower() in BET_APPETITE_TIERS:
        return appetite.strip().lower()
    return ""


def _bet_money_path_summary(meta: dict[str, Any], path: Path) -> dict[str, Any]:
    raw = meta.get("money_path")
    if not isinstance(raw, dict):
        return {
            "declared": False,
            "required": False,
            "bet_id": "",
            "expected_bet_id": path.stem,
            "anchor_required_before": "",
            "exposure_cap": None,
        }
    exposure_cap = raw.get("exposure_cap")
    cap: dict[str, Any] | None = None
    if isinstance(exposure_cap, dict):
        amount = exposure_cap.get("amount")
        currency = exposure_cap.get("currency")
        cap = {
            "amount": amount
            if isinstance(amount, int | float) and not isinstance(amount, bool)
            else None,
            "currency": str(currency or "").strip(),
        }
    return {
        "declared": True,
        "required": bool(raw.get("required")),
        "bet_id": str(raw.get("bet_id") or "").strip(),
        "expected_bet_id": path.stem,
        "anchor_required_before": str(raw.get("anchor_required_before") or "").strip(),
        "exposure_cap": cap,
    }


def _bet_metric_values(meta: dict[str, Any]) -> dict[str, Any]:
    for key in ("metrics", "metric_values"):
        value = meta.get(key)
        if isinstance(value, dict):
            return {str(metric): current for metric, current in value.items()}
    return {}


def _coerce_signal_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _compare_signal(current: Any, comparator: str, threshold: Any) -> bool | None:
    current_number = _coerce_signal_number(current)
    threshold_number = _coerce_signal_number(threshold)
    if current_number is not None and threshold_number is not None:
        if comparator == "<":
            return current_number < threshold_number
        if comparator == "<=":
            return current_number <= threshold_number
        if comparator == "==":
            return current_number == threshold_number
        if comparator == ">=":
            return current_number >= threshold_number
        if comparator == ">":
            return current_number > threshold_number
        if comparator == "!=":
            return current_number != threshold_number
    if comparator == "==":
        return str(current) == str(threshold)
    if comparator == "!=":
        return str(current) != str(threshold)
    return None


def _evaluate_bet_signal(
    signal: dict[str, Any],
    *,
    metrics: dict[str, Any],
    today: date,
) -> dict[str, Any]:
    metric = str(signal.get("metric") or "").strip()
    comparator = str(signal.get("comparator") or "").strip()
    threshold = signal.get("threshold")
    by_date = _parse_explicit_date(signal.get("by"))
    current_value = metrics.get(metric) if metric else None
    base = {
        "id": str(signal.get("id") or metric or "unnamed-signal"),
        "metric": metric,
        "comparator": comparator,
        "threshold": threshold,
        "current_value": current_value,
        "by": by_date.isoformat() if by_date else str(signal.get("by") or ""),
        "action": str(signal.get("action") or ""),
        "triggered": False,
        "status": "not_triggered",
    }
    if not metric or comparator not in BET_SIGNAL_COMPARATORS:
        base["status"] = "invalid"
        return base
    if metric not in metrics:
        base["status"] = "missing_metric"
        return base
    matched = _compare_signal(current_value, comparator, threshold)
    if matched is None:
        base["status"] = "invalid"
        return base
    if by_date is not None and by_date > today:
        base["status"] = "pending"
        return base
    base["triggered"] = bool(matched)
    base["status"] = "triggered" if matched else "not_triggered"
    return base


def _bet_exit_criteria(meta: dict[str, Any], *, today: date) -> dict[str, Any]:
    rubric = meta.get("kill_rubric")
    if not isinstance(rubric, dict):
        return {
            "declared": False,
            "missing": True,
            "failure_signals": [],
            "double_down_signals": [],
            "triggered_failure_signals": [],
            "triggered_double_down_signals": [],
            "metrics_source": "",
        }
    metrics = _bet_metric_values(meta)
    failure_signals = [
        _evaluate_bet_signal(signal, metrics=metrics, today=today)
        for signal in rubric.get("failure_signals") or []
        if isinstance(signal, dict)
    ]
    double_down_signals = [
        _evaluate_bet_signal(signal, metrics=metrics, today=today)
        for signal in rubric.get("double_down_signals") or []
        if isinstance(signal, dict)
    ]
    return {
        "declared": True,
        "missing": False,
        "failure_signals": failure_signals,
        "double_down_signals": double_down_signals,
        "triggered_failure_signals": [
            signal for signal in failure_signals if signal.get("triggered")
        ],
        "triggered_double_down_signals": [
            signal for signal in double_down_signals if signal.get("triggered")
        ],
        "metrics_source": "frontmatter.metrics"
        if "metrics" in meta
        else "frontmatter.metric_values"
        if "metric_values" in meta
        else "",
    }


def _bet_sort_key(item: dict[str, Any]) -> tuple[str, str]:
    deadline = str(item.get("deadline") or "9999-12-31")
    return (deadline, str(item.get("path") or ""))


def _bets(repo: Path) -> dict[str, Any]:
    bet_items = [_bet_summary(repo, path) for path in _relative_markdown_files(repo, "bets")]
    active = [
        item for item in bet_items if str(item.get("status", "")).lower() in ACTIVE_BET_STATUSES
    ]
    active.sort(key=_bet_sort_key)
    today = date.today()
    due_soon: list[dict[str, Any]] = []
    overdue: list[dict[str, Any]] = []
    for item in active:
        deadline = _parse_explicit_date(item.get("deadline"))
        if deadline is None:
            continue
        days_until = (deadline - today).days
        if days_until < 0:
            overdue_item = dict(item)
            overdue_item["days_overdue"] = abs(days_until)
            overdue.append(overdue_item)
        elif days_until <= 7:
            due_item = dict(item)
            due_item["days_until_deadline"] = days_until
            due_soon.append(due_item)
    missing_exit_criteria = [
        item for item in active if (item.get("exit_criteria") or {}).get("missing")
    ]
    triggered_failure_signals = [
        {
            "path": item.get("path"),
            "title": item.get("title"),
            "signal": signal,
        }
        for item in active
        for signal in (item.get("exit_criteria") or {}).get("triggered_failure_signals", [])
    ]
    triggered_double_down_signals = [
        {
            "path": item.get("path"),
            "title": item.get("title"),
            "signal": signal,
        }
        for item in active
        for signal in (item.get("exit_criteria") or {}).get("triggered_double_down_signals", [])
    ]
    return {
        "active": active[:5],
        "due_soon": due_soon[:5],
        "overdue": overdue[:5],
        "recent": bet_items[:5],
        "exit_criteria": {
            "missing": missing_exit_criteria[:5],
            "triggered_failure_signals": triggered_failure_signals[:10],
            "triggered_double_down_signals": triggered_double_down_signals[:10],
        },
    }


def _file_path_from_graph_id(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("file:"):
        return ""
    return value[len("file:") :]


def _relationship_adjacency(edges: list[dict[str, Any]]) -> dict[str, dict[str, set[str]]]:
    adjacency: dict[str, dict[str, set[str]]] = {}
    for edge in edges:
        rel_type = str(edge.get("rel_type") or edge.get("type") or "")
        source = _file_path_from_graph_id(edge.get("source"))
        target = _file_path_from_graph_id(edge.get("target"))
        if not rel_type or not source or not target:
            continue
        adjacency.setdefault(source, {}).setdefault(rel_type, set()).add(target)
        adjacency.setdefault(target, {}).setdefault(rel_type, set()).add(source)
    return adjacency


def _linked_push_paths_for_bet(
    adjacency: dict[str, dict[str, set[str]]],
    bet_path: str,
    push_paths: set[str],
) -> set[str]:
    direct_pushes = _linked_paths(adjacency, bet_path, "push")
    reverse_bet_links = _linked_paths(adjacency, bet_path, "bet") & push_paths
    return direct_pushes | reverse_bet_links


def _relationship_slug(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "unknown"


def _coerce_relationship_refs(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _is_hidden_or_generated(path: Path, repo: Path) -> bool:
    try:
        rel_parts = path.relative_to(repo).parts
    except ValueError:
        return True
    is_bundled_data = rel_parts[:2] == ("mb", "_data") or rel_parts[:1] == ("_data",)
    return (
        any(
            part.startswith(".") or part in {"__pycache__", "node_modules", ".venv", "venv"}
            for part in rel_parts
        )
        or is_bundled_data
    )


def _relationship_markdown_files(repo: Path) -> list[Path]:
    return [
        path
        for path in sorted(repo.rglob("*.md"))
        if path.is_file() and not _is_hidden_or_generated(path, repo)
    ]


def _resolve_relationship_ref(repo: Path, ref: str) -> Path | None:
    clean_ref = relationships.clean_ref(ref)
    if not clean_ref:
        return None
    target = (repo / clean_ref).resolve()
    try:
        target.relative_to(repo)
    except ValueError:
        return None
    return target


def _relationship_reference_edges(repo: Path) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str, tuple[tuple[str, str], ...]]] = set()
    if not repo.exists():
        return edges

    for file_path in _relationship_markdown_files(repo):
        frontmatter = _read_frontmatter(file_path)
        if not frontmatter:
            continue
        source_rel = file_path.relative_to(repo).as_posix()
        source_id = f"file:{source_rel}"
        for field in relationships.relationship_fields_for_source(source_rel):
            rel_type = relationships.normalize_relationship(
                field,
                source_path=source_rel,
                fallback=field,
            )
            for ref in _coerce_relationship_refs(frontmatter.get(field)):
                clean_ref = relationships.clean_ref(ref)
                if not clean_ref and not relationships.is_external_ref(ref):
                    continue
                target = _resolve_relationship_ref(repo, ref)
                if target is not None and target.exists():
                    target_id = f"file:{target.relative_to(repo).as_posix()}"
                elif relationships.is_external_ref(ref):
                    target_id = f"external:{_relationship_slug(ref)}"
                else:
                    target_id = f"missing:{_relationship_slug(ref)}"
                evidence = {"kind": "frontmatter", "field": field, "path": source_rel}
                key = (source_id, target_id, rel_type, tuple(sorted(evidence.items())))
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edges.append(
                    {
                        "source": source_id,
                        "target": target_id,
                        "type": field,
                        "rel_type": rel_type,
                        "original_field": field,
                        "evidence": evidence,
                        "target_ref": ref,
                    }
                )
    return edges


def _linked_paths(
    adjacency: dict[str, dict[str, set[str]]],
    path: str,
    rel_type: str,
) -> set[str]:
    return adjacency.get(path, {}).get(rel_type, set())


def _offer_summaries(repo: Path) -> list[dict[str, Any]]:
    paths: list[Path] = []
    for folder in ("core/offers", "reference/core/offers"):
        paths.extend(
            path for path in _relative_markdown_files(repo, folder) if path.name == "offer.md"
        )
    for rel in ("core/offer.md", "reference/core/offer.md"):
        path = repo / rel
        if path.is_file():
            paths.append(path)
    unique_paths = sorted(set(paths), key=lambda path: path.stat().st_mtime, reverse=True)
    return [_file_summary(repo, path, _read_frontmatter(path)) for path in unique_paths]


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item.strip()]
    return []


def _playbook_summary(repo: Path, path: Path) -> dict[str, Any]:
    meta = _read_frontmatter(path)
    try:
        rel = path.relative_to(repo).as_posix()
    except ValueError:
        rel = str(path)
    push_path = ""
    if path.parent.name == "playbooks" and path.parent.parent.name:
        push_path = f"pushes/{path.parent.parent.name}/push.md"
    approval_raw = meta.get("approval")
    approval: dict[str, Any] = approval_raw if isinstance(approval_raw, dict) else {}
    state_raw = meta.get("state")
    state: dict[str, Any] = state_raw if isinstance(state_raw, dict) else {}
    return {
        "path": rel,
        "title": _title_from_markdown(path),
        "status": str(meta.get("status", "") or ""),
        "push": str(meta.get("push", "") or ""),
        "resolved_push": push_path,
        "platform": str(meta.get("platform", "") or ""),
        "provider": str(meta.get("provider", "") or ""),
        "provider_boundary": str(meta.get("provider_boundary", "") or ""),
        "approval": {
            "required": bool(approval.get("required")),
            "status": str(approval.get("status", "") or ""),
            "approved_by": str(approval.get("approved_by", "") or ""),
            "approved_at": str(approval.get("approved_at", "") or ""),
        },
        "linked_outcomes": _coerce_string_list(meta.get("linked_outcomes")),
        "provider_refs_recorded": bool(state.get("provider_refs")),
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
    }


def _playbook_summaries(repo: Path) -> list[dict[str, Any]]:
    return [
        _playbook_summary(repo, path)
        for path in sorted(repo.glob("pushes/*/playbooks/*.md"))
        if path.is_file()
    ]


def _gap(
    *,
    gap_id: str,
    severity: str,
    summary: str,
    records: list[dict[str, Any]],
    repair: str,
) -> dict[str, Any]:
    return {
        "id": gap_id,
        "severity": severity,
        "summary": summary,
        "count": len(records),
        "evidence": [str(item.get("path") or item.get("source") or "") for item in records[:5]],
        "records": records[:5],
        "repair": repair,
        "safe_to_share": True,
    }


def _playbook_health(
    repo: Path,
    *,
    brain: dict[str, Any],
) -> dict[str, Any]:
    push_report = brain.get("pushes") or {}
    pushes = [
        item
        for item in push_report.get("records", [])
        if isinstance(item, dict) and item.get("source") == "canonical"
    ]
    playbooks = _playbook_summaries(repo)
    playbooks_by_push: dict[str, list[dict[str, Any]]] = {}
    for playbook in playbooks:
        push_path = str(playbook.get("resolved_push") or "")
        if push_path:
            playbooks_by_push.setdefault(push_path, []).append(playbook)

    pushes_without_playbook = [
        item
        for item in pushes
        if str(item.get("status") or "").lower() in PUSH_STATUSES_EXPECTING_PLAYBOOK
        and not playbooks_by_push.get(str(item.get("path") or ""))
    ]
    pending_status = [
        item
        for item in playbooks
        if str(item.get("status") or "").lower() in PLAYBOOK_STATUSES_NEEDING_ATTENTION
    ]
    approval_needed = [
        item
        for item in playbooks
        if bool((item.get("approval") or {}).get("required"))
        and str(item.get("status") or "").lower() not in {"canceled", "retired"}
        and str((item.get("approval") or {}).get("status") or "").lower()
        in PLAYBOOK_APPROVAL_STATUSES_NEEDING_ATTENTION
    ]
    completed_without_outcome: list[dict[str, Any]] = []
    for push in pushes:
        if str(push.get("status") or "").lower() not in COMPLETED_PUSH_STATUSES:
            continue
        for playbook in playbooks_by_push.get(str(push.get("path") or ""), []):
            if not playbook.get("linked_outcomes"):
                item = dict(playbook)
                item["push_status"] = str(push.get("status") or "")
                completed_without_outcome.append(item)
    provider_boundary_attention = [
        item
        for item in playbooks
        if str(item.get("provider_boundary") or "").lower()
        in PLAYBOOK_PROVIDER_BOUNDARIES_NEEDING_ATTENTION
        and str(item.get("status") or "").lower() not in {"canceled", "retired"}
    ]

    gaps = [
        _gap(
            gap_id="pushes_without_playbook",
            severity="warn",
            summary=(
                f"{len(pushes_without_playbook)} active/planned push(es) need a playbook run."
            ),
            records=pushes_without_playbook,
            repair="Add a run record under `pushes/<push>/playbooks/` for each active push.",
        )
        if pushes_without_playbook
        else None,
        _gap(
            gap_id="pending_playbook_statuses",
            severity="warn",
            summary=f"{len(pending_status)} playbook run(s) are still draft/planned.",
            records=pending_status,
            repair="Review each playbook run and move it toward approved, active, or completed.",
        )
        if pending_status
        else None,
        _gap(
            gap_id="playbook_approval_needed",
            severity="warn",
            summary=f"{len(approval_needed)} playbook run(s) still need approval.",
            records=approval_needed,
            repair="Record approval status before publishing, spending, or mutating providers.",
        )
        if approval_needed
        else None,
        _gap(
            gap_id="completed_playbooks_without_outcome",
            severity="warn",
            summary=(
                f"{len(completed_without_outcome)} completed-push playbook run(s) "
                "need an outcome link."
            ),
            records=completed_without_outcome,
            repair="Add `linked_outcomes` to the playbook after the push is reviewed.",
        )
        if completed_without_outcome
        else None,
        _gap(
            gap_id="manual_provider_boundaries",
            severity="info",
            summary=(
                f"{len(provider_boundary_attention)} playbook run(s) are still "
                "plan/manual provider work."
            ),
            records=provider_boundary_attention,
            repair=(
                "Confirm the operator expects manual provider steps before treating this "
                "as automation."
            ),
        )
        if provider_boundary_attention
        else None,
    ]
    active_gaps = [gap_item for gap_item in gaps if gap_item is not None]
    return {
        "ok": not active_gaps,
        "source": "mb status playbook scan",
        "summary": {
            "gaps": len(active_gaps),
            "warnings": len([item for item in active_gaps if item["severity"] == "warn"]),
            "info": len([item for item in active_gaps if item["severity"] == "info"]),
            "playbooks": len(playbooks),
            "pushes_without_playbook": len(pushes_without_playbook),
            "pending_playbook_statuses": len(pending_status),
            "playbook_approval_needed": len(approval_needed),
            "completed_playbooks_without_outcome": len(completed_without_outcome),
            "manual_provider_boundaries": len(provider_boundary_attention),
        },
        "gaps": active_gaps,
        "sections": {
            "pushes": {
                "records": len(pushes),
                "expecting_playbook": len(
                    [
                        item
                        for item in pushes
                        if str(item.get("status") or "").lower() in PUSH_STATUSES_EXPECTING_PLAYBOOK
                    ]
                ),
                "without_playbook": pushes_without_playbook[:5],
            },
            "playbooks": {
                "records": playbooks[:5],
                "pending_status": pending_status[:5],
                "approval_needed": approval_needed[:5],
                "completed_without_outcome": completed_without_outcome[:5],
                "provider_boundary_attention": provider_boundary_attention[:5],
            },
        },
        "safe_to_share": True,
    }


def _money_path_offer(
    repo: Path,
    *,
    proof_paths: list[str],
    proof_quality: dict[str, Any],
) -> dict[str, Any]:
    per_offer_paths = sorted(
        path.relative_to(repo).as_posix()
        for path in repo.glob("core/offers/*/offer.md")
        if path.is_file()
    )
    paths = per_offer_paths + _relative_existing_paths(
        repo,
        ["core/offer.md", "reference/core/offer.md"],
    )
    if not paths:
        return _money_path_object(
            level=0,
            status="missing",
            summary="No offer file was found.",
            paths=["core/offer.md"],
            missing=["offer"],
            references=["docs/offer-sharpening.md"],
        )

    texts_by_path = {path: _read_markdown_text(repo / path) for path in paths}
    texts = list(texts_by_path.values())
    combined = "\n".join(texts)
    guardrails = _keyword_hits(combined, OFFER_GUARDRAIL_KEYWORDS)
    missing = [key for key in OFFER_GUARDRAIL_KEYWORDS if key not in guardrails]
    guardrail_checks: dict[str, dict[str, Any]] = {}
    for field, keywords in OFFER_GUARDRAIL_KEYWORDS.items():
        hit_paths = [path for path, text in texts_by_path.items() if _contains_any(text, keywords)]
        guardrail_checks[field] = {
            "present": bool(hit_paths),
            "paths": hit_paths[:5],
            "keywords": [keyword for keyword in keywords if keyword in combined.lower()][:5],
        }
    stubs = [path for path in paths if _is_stub_content(repo, path)]
    evidence = [
        _money_path_evidence(
            kind="file",
            path=path,
            field="offer",
            summary="Offer file exists.",
        )
        for path in paths[:5]
    ]
    evidence.extend(
        _money_path_evidence(
            kind="section",
            path=paths[0],
            field=field,
            summary=f"{field.replace('_', ' ')} signal appears in offer text.",
        )
        for field in guardrails[:5]
    )
    live_offer_paths = [
        path for path in per_offer_paths if _frontmatter_status(repo, path) in LIVE_OFFER_STATUSES
    ]
    testimonial_quality = proof_quality.get("testimonials") or {}
    claim_links = proof_quality.get("claim_links") or {}
    proof_boundary_warnings: list[str] = []
    if "proof" in guardrails and not proof_paths:
        proof_boundary_warnings.append("proof_claim_without_proof_file")
    if (
        int(testimonial_quality.get("total") or 0) > 0
        and int(testimonial_quality.get("permissioned_public") or 0) == 0
    ):
        proof_boundary_warnings.append("testimonials_without_permissioned_public_signal")
    if claim_links.get("unsupported_offer_claims"):
        proof_boundary_warnings.append("offer_claims_without_offer_linked_proof")

    level = 1
    status = "stated"
    summary = "Offer exists as durable repo text."
    if len(guardrails) >= 4 and not stubs:
        level = 2
        status = "structured"
        summary = "Offer has several expected guardrail signals."
    if proof_paths and level >= 2:
        level = 3
        status = "evidence_backed"
        summary = "Offer is structured and proof files exist."
    if stubs:
        missing = sorted(set(missing + ["replace_stub_offer"]))
        summary = "Offer file is still a public stub."
    if len(live_offer_paths) > 1:
        level = min(level, 1)
        status = "ambiguous_multi_offer"
        missing = sorted(set(missing + ["active_offer_selection"]))
        summary = (
            "Multiple live offer files exist and no active offer selection is "
            "available in status facts."
        )

    item = _money_path_object(
        level=level,
        status=status,
        summary=summary,
        paths=paths,
        missing=missing,
        evidence=evidence,
        references=["docs/offer-sharpening.md"],
        recommended_route="/mb-think",
    )
    item["guardrails"] = {
        "answered": guardrails,
        "missing": missing,
        "checks": guardrail_checks,
        "proof_boundary_warnings": proof_boundary_warnings,
        "reference": "docs/offer-sharpening.md",
    }
    return item


def _money_path_audience(repo: Path) -> dict[str, Any]:
    paths = sorted(
        path.relative_to(repo).as_posix()
        for path in repo.glob("core/offers/*/audience.md")
        if path.is_file()
    )
    paths.extend(_relative_existing_paths(repo, ["core/audience.md", "reference/core/audience.md"]))
    if not paths:
        return _money_path_object(
            level=0,
            status="missing",
            summary="No audience file was found.",
            paths=["core/audience.md"],
            missing=["audience", "customer_progress", "buyer_language"],
            references=["docs/offer-sharpening.md"],
        )

    combined = "\n".join(_read_markdown_text(repo / path) for path in paths)
    hits = _keyword_hits(combined, AUDIENCE_SIGNAL_KEYWORDS)
    missing = [key for key in AUDIENCE_SIGNAL_KEYWORDS if key not in hits]
    stubs = [path for path in paths if _is_stub_content(repo, path)]
    level = 1
    status = "stated"
    summary = "Audience exists as durable repo text."
    if len(hits) >= 2 and not stubs:
        level = 2
        status = "structured"
        summary = "Audience includes buyer language, progress, pain, or objection signals."
    if "buyer_language" in hits and "objections" in hits and not stubs:
        level = 3
        status = "evidence_backed"
        summary = "Audience includes source-language and objection signals."
    if stubs:
        missing = sorted(set(missing + ["replace_stub_audience"]))
        summary = "Audience file is still a public stub."

    return _money_path_object(
        level=level,
        status=status,
        summary=summary,
        paths=paths,
        missing=missing,
        evidence=[
            _money_path_evidence(
                kind="file", path=path, field="audience", summary="Audience file exists."
            )
            for path in paths[:5]
        ]
        + [
            _money_path_evidence(
                kind="section",
                path=paths[0],
                field=field,
                summary=f"{field.replace('_', ' ')} signal appears in audience text.",
            )
            for field in hits[:5]
        ],
        references=["docs/offer-sharpening.md"],
        recommended_route="/mb-think",
        confidence="medium" if level >= 2 else "high",
    )


def _money_path_customer_progress(repo: Path) -> dict[str, Any]:
    paths = _relative_existing_paths(repo, ["core/audience.md", "reference/core/audience.md"])
    paths.extend(
        sorted(
            path.relative_to(repo).as_posix()
            for path in repo.glob("core/offers/*/audience.md")
            if path.is_file()
        )
    )
    research_paths = [
        path.relative_to(repo).as_posix()
        for path in _relative_markdown_files(repo, "research")[:8]
        if _contains_any(
            _read_markdown_text(path), tuple(sum(CUSTOMER_PROGRESS_KEYWORDS.values(), ()))
        )
    ]
    paths.extend(research_paths[:5])
    if not paths:
        return _money_path_object(
            level=0,
            status="missing",
            summary="No customer-progress, job, pain, gain, or buyer-language source was found.",
            paths=["core/audience.md", "research/"],
            missing=["customer_progress", "buyer_language"],
            references=["docs/offer-sharpening.md"],
            recommended_route="/mb-think",
        )

    combined = "\n".join(
        _read_markdown_text(repo / path) for path in paths if (repo / path).is_file()
    )
    hits = _keyword_hits(combined, CUSTOMER_PROGRESS_KEYWORDS)
    missing = [key for key in CUSTOMER_PROGRESS_KEYWORDS if key not in hits]
    stubs = [path for path in paths if (repo / path).is_file() and _is_stub_content(repo, path)]
    level = 1
    status = "stated"
    summary = "Customer progress exists as loose audience or research text."
    if len(hits) >= 2 and not stubs:
        level = 2
        status = "structured"
        summary = "Customer progress includes job, pain, gain, or language signals."
    if "language" in hits and ("job_to_be_done" in hits or "pain" in hits) and not stubs:
        level = 3
        status = "evidence_backed"
        summary = "Customer progress includes buyer language tied to a job, pain, or gain."
    if stubs:
        missing = sorted(set(missing + ["replace_stub_customer_progress"]))
        summary = "Customer-progress source is still a public audience stub."

    return _money_path_object(
        level=level,
        status=status,
        summary=summary,
        paths=sorted(set(paths)),
        missing=missing,
        evidence=[
            _money_path_evidence(
                kind="text",
                path=paths[0],
                field=field,
                summary=f"{field.replace('_', ' ')} signal appears in repo text.",
            )
            for field in hits[:5]
        ],
        references=["docs/offer-sharpening.md"],
        recommended_route="/mb-think",
        confidence="medium" if level >= 2 else "high",
    )


def _proof_quality(
    repo: Path,
    *,
    paths: list[str],
    offer_paths: list[str],
    pushes: list[dict[str, Any]],
    playbooks: list[dict[str, Any]],
    measurement: dict[str, Any],
    relationship_health: dict[str, Any],
) -> dict[str, Any]:
    quality = _empty_proof_quality()
    testimonial_counts = quality["testimonials"]
    linked_offers: set[str] = set()
    any_structured_entry = False
    proof_texts: list[str] = []
    for path in paths:
        text = _read_markdown_text(repo / path)
        proof_texts.append(text)
        linked_refs = _proof_linked_offer_refs(repo, path, offer_paths)
        linked_offers.update(linked_refs)
        if path.endswith("testimonials.md"):
            meta = _read_frontmatter(repo / path)
            entries = _testimonial_entries(text, meta)
            any_structured_entry = any_structured_entry or len(entries) > 1 or bool(meta)
            counts = _testimonial_signal_counts(
                entries,
                linked_offer_refs=linked_refs,
                offer_paths=offer_paths,
            )
            for key, value in counts.items():
                testimonial_counts[key] += value
        if path.endswith("typicality.md"):
            lowered = text.lower()
            typicality = quality["typicality"]
            typicality["exists"] = True
            typicality["has_average_case"] = _contains_any(lowered, PROOF_AVERAGE_CASE_KEYWORDS)
            typicality["has_caveats"] = _contains_any(lowered, PROOF_CAVEAT_KEYWORDS)
            typicality["has_common_failure_context"] = _contains_any(
                lowered,
                PROOF_FAILURE_CONTEXT_KEYWORDS,
            )
            typicality["has_time_to_outcome"] = _proof_text_has_timeframe(lowered)
    quality["claim_links"]["linked_offers"] = sorted(linked_offers)
    unsupported_claims: list[str] = []
    if offer_paths and paths and not (linked_offers & set(offer_paths)):
        unsupported_claims.extend(
            f"{path}: no offer-linked proof detected" for path in offer_paths[:5]
        )
    quality["claim_links"]["unsupported_offer_claims"] = unsupported_claims
    quality["structured_entries"] = any_structured_entry
    quality["source_backed"] = _contains_any("\n".join(proof_texts), PROOF_SOURCE_KEYWORDS)
    quality["instrumentation"] = {
        "active_push": bool(
            [
                push
                for push in pushes
                if str(push.get("status") or "").lower() in ACTIVE_PUSH_STATUSES
            ]
        ),
        "playbook": bool(playbooks),
        "page_readiness": bool(measurement.get("available")),
        "outcome_feedback": bool(
            (relationship_health.get("sections") or {}).get("outcomes", {}).get("linked_count")
        )
        or any(playbook.get("linked_outcomes") for playbook in playbooks),
    }
    quality["public_marketing"] = _proof_public_marketing_readiness(quality)
    return quality


def _money_path_proof(
    repo: Path,
    *,
    offer_paths: list[str],
    pushes: list[dict[str, Any]],
    playbooks: list[dict[str, Any]],
    measurement: dict[str, Any],
    relationship_health: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    proof_files = [
        path
        for root in [repo / "core" / "proof", *repo.glob("core/offers/*/proof")]
        if root.exists()
        for path in sorted(root.rglob("*.md"))
        if path.is_file()
    ]
    legacy_proof = [
        path
        for path in repo.glob("core/offers/*/*.md")
        if path.name in {"testimonials.md", "typicality.md"}
    ]
    proof_files.extend(legacy_proof)
    paths = sorted({path.relative_to(repo).as_posix() for path in proof_files})
    if not paths:
        quality = _empty_proof_quality()
        return (
            _money_path_object(
                level=0,
                status="missing",
                summary="No reusable proof files were found.",
                paths=["core/proof/"],
                missing=["testimonials", "typicality", "proof_angles"],
                references=["docs/offer-sharpening.md"],
                recommended_route="/mb-think",
            )
            | {"quality": quality},
            [],
        )

    quality = _proof_quality(
        repo,
        paths=paths,
        offer_paths=offer_paths,
        pushes=pushes,
        playbooks=playbooks,
        measurement=measurement,
        relationship_health=relationship_health,
    )
    has_testimonials = any(path.endswith("testimonials.md") for path in paths)
    has_typicality = any(path.endswith("typicality.md") for path in paths)
    has_angles = any("/angles/" in path for path in paths)
    missing = [
        name
        for name, present in {
            "testimonials": has_testimonials,
            "typicality": has_typicality,
            "proof_angles": has_angles,
        }.items()
        if not present
    ]
    level = 1
    status = "stated"
    summary = "Proof files exist."
    testimonial_quality = quality["testimonials"]
    typicality_quality = quality["typicality"]
    instrumentation = quality["instrumentation"]
    if has_testimonials or has_typicality or quality["structured_entries"]:
        level = 2
        status = "structured"
        summary = "Proof includes standard files, entries, or frontmatter."
    if int(testimonial_quality["specific"]) > 0 and (
        has_typicality or int(testimonial_quality["linked_to_offer"]) > 0
    ):
        level = 3
        status = "evidence_backed"
        summary = "Proof includes specific outcomes tied to typicality or an offer."
    if (
        level >= 3
        and int(testimonial_quality["specific"]) >= 2
        and (
            quality["source_backed"]
            or int(testimonial_quality["permissioned_public"]) > 0
            or int(testimonial_quality["with_metric"]) > 0
            or int(testimonial_quality["with_timeframe"]) > 0
        )
    ):
        level = 4
        status = "field_tested"
        summary = "Proof includes multiple specific, source or outcome-backed entries."
    has_active_path = bool(instrumentation["active_push"]) or bool(instrumentation["playbook"])
    if (
        level >= 3
        and int(testimonial_quality["linked_to_offer"]) > 0
        and bool(typicality_quality["exists"])
        and has_active_path
        and bool(instrumentation["outcome_feedback"])
    ):
        level = 5
        status = "instrumented"
        summary = "Proof is linked to an offer and connected to outcome feedback."
    return (
        _money_path_object(
            level=level,
            status=status,
            summary=summary,
            paths=paths,
            missing=missing,
            evidence=[
                _money_path_evidence(
                    kind="file", path=path, field="proof", summary="Proof file exists."
                )
                for path in paths[:5]
            ],
            references=["docs/offer-sharpening.md"],
            recommended_route="/mb-think",
        )
        | {"quality": quality},
        paths,
    )


def _money_path_product_ladder(repo: Path, *, multi_offer: bool) -> dict[str, Any]:
    paths = _relative_existing_paths(
        repo, ["core/product-ladder.md", "reference/core/product-ladder.md"]
    )
    if not paths and not multi_offer:
        return _money_path_object(
            level=1,
            status="single_offer_mode",
            summary=(
                "Single-offer repo; product ladder is optional until offers need "
                "relationship logic."
            ),
            paths=["core/product-ladder.md"],
            missing=[],
            evidence=[],
            references=[".claude/reference/business-primitives/setup-patterns.md"],
            recommended_route="/mb-think",
        )
    if not paths:
        return _money_path_object(
            level=0,
            status="missing",
            summary="Multiple offer files exist, but no product ladder explains how they relate.",
            paths=["core/product-ladder.md"],
            missing=["entry_step", "ascension_path", "retention_offer"],
            references=[".claude/reference/business-primitives/setup-patterns.md"],
            recommended_route="/mb-think",
        )
    text = "\n".join(_read_markdown_text(repo / path) for path in paths)
    hits = _keyword_hits(text, PRODUCT_LADDER_REQUIREMENTS)
    level = 2 if len(hits) >= 3 else 1
    return _money_path_object(
        level=level,
        status="structured" if level >= 2 else "stated",
        summary="Product ladder explains offer relationships."
        if level >= 2
        else "Product ladder exists as loose text.",
        paths=paths,
        missing=[
            item for item in ("entry_step", "ascension_path", "retention_offer") if item not in hits
        ],
        evidence=[
            _money_path_evidence(
                kind="file",
                path=paths[0],
                field="product_ladder",
                summary="Product ladder file exists.",
            )
        ],
        references=[".claude/reference/business-primitives/setup-patterns.md"],
        recommended_route="/mb-think",
    )


def _money_path_cta(
    repo: Path,
    *,
    offer_paths: list[str],
    playbooks: list[dict[str, Any]],
    pushes: list[dict[str, Any]],
    measurement: dict[str, Any],
) -> dict[str, Any]:
    paths: list[str] = []
    evidence: list[dict[str, Any]] = []
    text_only_paths: list[str] = []
    for rel in offer_paths:
        if _contains_any(_read_markdown_text(repo / rel), CTA_KEYWORDS):
            paths.append(rel)
            text_only_paths.append(rel)
            evidence.append(
                _money_path_evidence(
                    kind="text",
                    path=rel,
                    field="cta",
                    summary="CTA or next-step language appears in offer text.",
                )
            )
    push_goal_paths = [
        str(push.get("path") or "") for push in pushes if push.get("path") and push.get("goal")
    ]
    if push_goal_paths:
        paths.extend(push_goal_paths[:5])
        evidence.append(
            _money_path_evidence(
                kind="frontmatter",
                path=push_goal_paths[0],
                field="goal",
                summary="Push goal can anchor the entry or conversion step.",
            )
        )
    playbook_paths = [str(item.get("path") or "") for item in playbooks if item.get("path")]
    if playbook_paths:
        paths.extend(playbook_paths[:5])
        evidence.append(
            _money_path_evidence(
                kind="frontmatter",
                path=playbook_paths[0],
                field="resource",
                summary="A playbook resource or trigger can carry the next step.",
            )
        )
    if measurement.get("available"):
        source = str(
            measurement.get("source_record")
            or measurement.get("site_repo")
            or ".mainbranch/conversion.json"
        )
        paths.append(source)
        evidence.append(
            _money_path_evidence(
                kind="measurement",
                path=source,
                field="conversion",
                summary=str(measurement.get("summary") or "Conversion plan found."),
            )
        )

    if not paths:
        return _money_path_object(
            level=0,
            status="missing",
            summary="No CTA path, resource handoff, or conversion endpoint was found.",
            paths=["core/offer.md"],
            missing=["next_step", "conversion_endpoint"],
            references=["docs/offer-sharpening.md"],
            recommended_route="/mb-think",
        )
    level = 2 if measurement.get("available") or playbook_paths or push_goal_paths else 1
    return _money_path_object(
        level=level,
        status="structured" if level >= 2 else "stated",
        summary=(
            "CTA path is connected to a playbook, push goal, or conversion plan."
            if level >= 2
            else "CTA language exists, but no connected page, push goal, or playbook was found."
        ),
        paths=sorted(set(paths)),
        missing=[] if level >= 2 else ["conversion_endpoint"],
        evidence=evidence,
        references=["docs/offer-sharpening.md"],
        recommended_route="/mb-site" if level >= 1 else "/mb-think",
        confidence="high" if level >= 2 else ("medium" if text_only_paths else "high"),
    )


def _money_path_channel_strategy(repo: Path, *, pushes: list[dict[str, Any]]) -> dict[str, Any]:
    paths = _relative_existing_paths(
        repo,
        [
            "core/content-strategy.md",
            "core/marketing/distribution-strategy.md",
            "reference/core/content-strategy.md",
        ],
    )
    paths.extend(
        sorted(
            path.relative_to(repo).as_posix()
            for root in [
                repo / "core" / "marketing" / "channels",
                repo / "core" / "marketing" / "accounts",
            ]
            if root.exists()
            for path in root.glob("*.md")
            if path.is_file()
        )
    )
    active_channels = sorted(
        {
            str(channel)
            for push in pushes
            if str(push.get("status") or "").lower()
            in ACTIVE_PUSH_STATUSES | COMPLETED_PUSH_STATUSES
            for channel in (push.get("channels") or [])
            if isinstance(channel, str) and channel.strip()
        }
    )
    evidence = [
        _money_path_evidence(
            kind="file",
            path=path,
            field="channel_strategy",
            summary="Content strategy file exists.",
        )
        for path in paths
    ]
    if active_channels and pushes:
        evidence.append(
            _money_path_evidence(
                kind="frontmatter",
                path=str(pushes[0].get("path") or "pushes/"),
                field="channels",
                summary=f"Push channel(s) recorded: {', '.join(active_channels[:5])}.",
            )
        )
    if not paths and not active_channels:
        return _money_path_object(
            level=0,
            status="missing",
            summary="No channel strategy or push channels were found.",
            paths=["core/content-strategy.md"],
            missing=["active_channel", "distribution_strategy"],
            references=["docs/content-strategy.md", "docs/operator-loops.md"],
            recommended_route="/mb-think",
        )
    level = 2 if active_channels else 1
    return _money_path_object(
        level=level,
        status="structured" if level >= 2 else "stated",
        summary="Channel strategy has active channel facts."
        if active_channels
        else "Channel strategy exists as durable text.",
        paths=paths + [str(push.get("path")) for push in pushes[:5] if push.get("path")],
        missing=[] if active_channels else ["active_channel"],
        evidence=evidence,
        references=["docs/content-strategy.md", "docs/operator-loops.md"],
        recommended_route="/mb-think",
    )


def _money_path_active_push(pushes: list[dict[str, Any]]) -> dict[str, Any]:
    active = [
        push for push in pushes if str(push.get("status") or "").lower() in ACTIVE_PUSH_STATUSES
    ]
    if not active:
        return _money_path_object(
            level=0,
            status="missing",
            summary="No active or planned push is moving the money path forward.",
            paths=["pushes/"],
            missing=["active_push"],
            references=["docs/system-architecture.md"],
            recommended_route="/mb-start",
        )
    first = active[0]
    required = ("goal", "audience", "offer", "promise", "channels")
    missing = [key for key in required if not first.get(key)]
    level = 2 if not missing else 1
    return _money_path_object(
        level=level,
        status="structured" if level >= 2 else "stated",
        summary="Active push has goal, audience, offer, promise, and channels."
        if level >= 2
        else "Active push exists but is missing route fields.",
        paths=[str(push.get("path") or "") for push in active[:5] if push.get("path")],
        missing=missing,
        evidence=[
            _money_path_evidence(
                kind="frontmatter",
                path=str(first.get("path") or "pushes/"),
                field="status",
                summary=f"Push status is {first.get('status')}.",
            )
        ],
        references=["docs/system-architecture.md"],
        recommended_route="/mb-start",
    )


def _money_path_playbook(
    playbooks: list[dict[str, Any]], playbook_health: dict[str, Any]
) -> dict[str, Any]:
    if not playbooks:
        return _money_path_object(
            level=0,
            status="missing",
            summary="No push playbook run record was found.",
            paths=["pushes/<push>/playbooks/"],
            missing=["playbook_run"],
            references=["docs/playbooks.md"],
            recommended_route="/mb-start",
        )
    approved = [
        item
        for item in playbooks
        if str((item.get("approval") or {}).get("status") or "").lower() == "approved"
    ]
    active_or_completed = [
        item
        for item in playbooks
        if str(item.get("status") or "").lower() in {"active", "completed"}
    ]
    missing = []
    if not approved:
        missing.append("approval")
    if not active_or_completed:
        missing.append("active_or_completed_run")
    level = 1
    if active_or_completed:
        level = 2
    if approved and active_or_completed and not (playbook_health.get("gaps") or []):
        level = 3
    first = playbooks[0]
    return _money_path_object(
        level=level,
        status="evidence_backed" if level >= 3 else ("structured" if level >= 2 else "stated"),
        summary="Push playbook is approved, active/completed, and has no status health gaps."
        if level >= 3
        else "Push playbook exists but still needs approval, activation, or review.",
        paths=[str(item.get("path") or "") for item in playbooks[:5] if item.get("path")],
        missing=missing,
        evidence=[
            _money_path_evidence(
                kind="frontmatter",
                path=str(first.get("path") or ""),
                field="provider_boundary",
                summary=f"Provider boundary is {first.get('provider_boundary') or 'unspecified'}.",
            )
        ],
        references=["docs/playbooks.md"],
        recommended_route="/mb-start",
    )


def _money_path_page_readiness(measurement: dict[str, Any]) -> dict[str, Any]:
    if not measurement.get("available"):
        return _money_path_object(
            level=0,
            status="missing",
            summary="No paid-traffic site conversion plan was found.",
            paths=[".mainbranch/conversion.json"],
            missing=["page_or_lander", "conversion_plan"],
            references=["docs/google-ads-gtm-conversion-rubric.md"],
            recommended_route="/mb-site",
        )
    state = str(measurement.get("state") or "missing")
    state_levels = {
        "missing": 0,
        "blocked": 1,
        "ready_for_preview": 2,
        "ready_for_operator_review": 3,
        "ready": 5,
    }
    level = state_levels.get(state, 1)
    source = str(
        measurement.get("source_record")
        or measurement.get("site_repo")
        or ".mainbranch/conversion.json"
    )
    return _money_path_object(
        level=level,
        status=state,
        summary=str(measurement.get("summary") or f"Site measurement state is {state}."),
        paths=[source],
        missing=[] if level >= 2 else ["conversion_plan_ready"],
        evidence=[
            _money_path_evidence(
                kind="measurement",
                path=source,
                field="state",
                summary=f"Site readiness state is {state}.",
            )
        ],
        references=["docs/google-ads-gtm-conversion-rubric.md"],
        recommended_route="/mb-site",
    )


def _money_path_outcome_feedback(
    relationship_health: dict[str, Any],
    playbook_health: dict[str, Any],
    playbooks: list[dict[str, Any]],
) -> dict[str, Any]:
    relationship_outcomes = (relationship_health.get("sections") or {}).get("outcomes") or {}
    linked_count = int(relationship_outcomes.get("linked_count") or 0)
    playbooks_with_outcomes = [item for item in playbooks if item.get("linked_outcomes")]
    playbook_summary = playbook_health.get("summary") or {}
    missing_count = int(playbook_summary.get("completed_playbooks_without_outcome") or 0) + int(
        (relationship_health.get("summary") or {}).get("completed_pushes_without_outcome") or 0
    )
    if linked_count or playbooks_with_outcomes:
        evidence = (
            [
                _money_path_evidence(
                    kind="relationship",
                    path="",
                    field="linked_outcomes",
                    summary=f"{linked_count} linked outcome relationship(s) found.",
                )
            ]
            if linked_count
            else []
        )
        if playbooks_with_outcomes:
            evidence.append(
                _money_path_evidence(
                    kind="frontmatter",
                    path=str(playbooks_with_outcomes[0].get("path") or ""),
                    field="linked_outcomes",
                    summary=f"{len(playbooks_with_outcomes)} playbook(s) link outcomes.",
                )
            )
        return _money_path_object(
            level=3,
            status="evidence_backed",
            summary=("Outcome links feed learning back into the repo."),
            paths=[
                str(item.get("path") or "")
                for item in playbooks_with_outcomes[:5]
                if item.get("path")
            ],
            missing=[] if not missing_count else ["some_completed_runs_missing_outcomes"],
            evidence=evidence,
            references=["docs/business-connections.md"],
            recommended_route="/mb-end",
        )
    return _money_path_object(
        level=0,
        status="missing",
        summary="No outcome feedback link was found.",
        paths=["pushes/", "bets/", "log/"],
        missing=["linked_outcomes", "review_or_outcome_note"],
        evidence=[],
        references=["docs/business-connections.md"],
        recommended_route="/mb-end",
    )


def _money_path_ranked_actions(
    objects: dict[str, dict[str, Any]], overall_level: int
) -> list[dict[str, Any]]:
    candidates = [
        (
            "define-customer-progress",
            "Define the customer progress",
            "customer_progress",
            (
                "The money path needs the buyer's job, pain, gain, or language before "
                "offer routing can be trusted."
            ),
            "/mb-think",
        ),
        (
            "clarify-offer",
            "Clarify the offer",
            "offer",
            "The money path needs a legible offer before downstream routing can help.",
            "/mb-think",
        ),
        (
            "define-audience-progress",
            "Define the buyer progress",
            "audience",
            "The money path needs a clear audience and customer-progress signal.",
            "/mb-think",
        ),
        (
            "attach-proof",
            "Attach proof to the promise",
            "proof",
            "The path needs proof, typicality, or evidence before scaling traffic.",
            "/mb-think",
        ),
        (
            "define-cta-path",
            "Define the CTA path",
            "cta_path",
            "Offer and audience facts need a next step or conversion endpoint.",
            "/mb-think",
        ),
        (
            "connect-channel-strategy",
            "Connect an active channel",
            "channel_strategy",
            "The path needs a demand source or distribution channel.",
            "/mb-think",
        ),
        (
            "open-or-select-push",
            "Open or select the active push",
            "active_push",
            "The path needs coordinated work moving it forward.",
            "/mb-start",
        ),
        (
            "record-playbook-run",
            "Record the push playbook",
            "playbook",
            "The path needs a run record for approval, provider boundary, and outcome hooks.",
            "/mb-start",
        ),
        (
            "prepare-page-readiness",
            "Prepare page readiness",
            "page_readiness",
            "Demand needs somewhere measurable to land before launch advice is useful.",
            "/mb-site",
        ),
        (
            "close-outcome-loop",
            "Close the outcome feedback loop",
            "outcome_feedback_loop",
            "Completed or active work needs outcome evidence feeding back into durable memory.",
            "/mb-end",
        ),
    ]
    actions: list[dict[str, Any]] = []
    # Strong proof (level >= 4) with only quality nits should not outrank
    # packaging/channel/push moves. Hold its strengthen action and re-insert it
    # below those moves, just above the page-readiness/outcome tail.
    deferred_strong_proof: dict[str, Any] | None = None
    for action_id, title, key, fallback_reason, route in candidates:
        component = objects.get(key) or {}
        level = int(component.get("level") or 0)
        missing = component.get("missing") or []
        if key == "outcome_feedback_loop":
            if level != 0:
                continue
        elif key == "proof" and level >= 2:
            quality = component.get("quality") or {}
            testimonial_quality = quality.get("testimonials") or {}
            typicality_quality = quality.get("typicality") or {}
            claim_links = quality.get("claim_links") or {}
            instrumentation = quality.get("instrumentation") or {}
            public_marketing = quality.get("public_marketing") or {}
            if public_marketing.get("status") == "blocked":
                actions.append(
                    {
                        "id": "collect-proof-permission",
                        "title": "Collect proof permission",
                        "reason": str(
                            public_marketing.get("summary")
                            or "Specific proof exists, but public marketing permission is missing."
                        ),
                        "route": "/mb-think",
                        "source": "money_path.objects.proof.quality.public_marketing",
                        "component": "proof",
                        "confidence": "high",
                        "effort_hint": "low",
                        "missing": [
                            str(item) for item in (public_marketing.get("missing") or [])[:5]
                        ],
                        "safe_to_share": True,
                    }
                )
                continue
            proof_quality_gaps: list[str] = []
            if int(testimonial_quality.get("generic") or 0) > 0:
                proof_quality_gaps.append("specific_testimonials")
            if int(testimonial_quality.get("linked_to_offer") or 0) == 0:
                proof_quality_gaps.append("offer_linked_proof")
            if not bool(typicality_quality.get("exists")):
                proof_quality_gaps.append("typicality")
            if claim_links.get("unsupported_offer_claims"):
                proof_quality_gaps.append("supported_offer_claims")
            if not bool(instrumentation.get("outcome_feedback")):
                proof_quality_gaps.append("outcome_feedback")
            if not proof_quality_gaps:
                continue
            strengthen_proof = {
                "id": "strengthen-proof-quality",
                "title": "Strengthen proof quality",
                "reason": (
                    "Proof exists, but testimonials are generic or not linked to an "
                    "offer, outcome, typicality, or claim."
                ),
                "route": "/mb-think",
                "source": "money_path.objects.proof.quality",
                "component": "proof",
                "confidence": "medium",
                "effort_hint": "medium",
                "missing": proof_quality_gaps[:5],
                "safe_to_share": True,
            }
            if level >= 4:
                # Proof is already field-tested. Polishing it ranks below
                # packaging/channel/push moves; hold it for the tail.
                deferred_strong_proof = strengthen_proof
            else:
                actions.append(strengthen_proof)
            continue
        elif level >= 2:
            continue
        actions.append(
            {
                "id": action_id,
                "title": title,
                "reason": str(component.get("summary") or fallback_reason),
                "route": route,
                "source": f"money_path.objects.{key}",
                "component": key,
                "confidence": "high" if level == 0 else "medium",
                "effort_hint": "medium",
                "missing": [str(item) for item in missing[:5]],
                "safe_to_share": True,
            }
        )
    if deferred_strong_proof is not None:
        # Re-insert just above the page-readiness/outcome tail. With 5+ higher
        # priority moves ahead of it (and no tail action to anchor against), the
        # final [:5] cut can drop strong-proof polish entirely -- by design, it is
        # the lowest-urgency move once proof is already field-tested.
        tail_components = {"page_readiness", "outcome_feedback_loop"}
        insert_at = next(
            (
                index
                for index, action in enumerate(actions)
                if action.get("component") in tail_components
            ),
            len(actions),
        )
        actions.insert(insert_at, deferred_strong_proof)
    return actions[:5]


def _money_path_overall_level(objects: dict[str, dict[str, Any]]) -> int:
    customer_progress = int((objects.get("customer_progress") or {}).get("level") or 0)
    offer = int((objects.get("offer") or {}).get("level") or 0)
    audience = int((objects.get("audience") or {}).get("level") or 0)
    proof = int((objects.get("proof") or {}).get("level") or 0)
    cta = int((objects.get("cta_path") or {}).get("level") or 0)
    channel = int((objects.get("channel_strategy") or {}).get("level") or 0)
    active_push = int((objects.get("active_push") or {}).get("level") or 0)
    playbook = int((objects.get("playbook") or {}).get("level") or 0)
    page = int((objects.get("page_readiness") or {}).get("level") or 0)
    outcome = int((objects.get("outcome_feedback_loop") or {}).get("level") or 0)
    if offer == 0:
        return 0
    if customer_progress == 0 or audience == 0 or offer < 2 or audience < 2:
        return 1
    if proof == 0 or cta == 0:
        return 2
    if min(channel, active_push, playbook) == 0:
        return 3
    if outcome == 0:
        return 4
    if page >= 5 and outcome >= 3 and min(proof, cta, channel, active_push, playbook) >= 2:
        return 5
    return 4


def _money_amount(
    *, commodity: str = "USD", decimal_mantissa: int = 0, decimal_places: int = 2
) -> dict[str, Any]:
    scale = 10**decimal_places
    whole = abs(decimal_mantissa) // scale
    fraction = abs(decimal_mantissa) % scale
    sign = "-" if decimal_mantissa < 0 else ""
    if commodity == "USD" and decimal_places == 2:
        display = f"{sign}${whole:,}.{fraction:02d}"
    elif decimal_places > 0:
        display = f"{sign}{whole:,}.{fraction:0{decimal_places}d} {commodity}".strip()
    else:
        display = f"{sign}{whole:,} {commodity}".strip()
    return {
        "commodity": commodity,
        "decimal_mantissa": decimal_mantissa,
        "decimal_places": decimal_places,
        "display": display,
    }


def _money_path_active_bet_exposure(repo: Path, report: dict[str, Any]) -> dict[str, Any]:
    raw_brain = report.get("brain")
    brain = raw_brain if isinstance(raw_brain, dict) else {}
    raw_bets = brain.get("bets")
    bets = raw_bets if isinstance(raw_bets, dict) else {}
    active = [item for item in bets.get("active", []) if isinstance(item, dict)]
    books = report.get("books") if isinstance(report.get("books"), dict) else {}
    policy = (
        ((books.get("policy") or {}).get("money_path") or {}) if isinstance(books, dict) else {}
    )
    currency = str(policy.get("currency") or "USD")
    exposure_window_days = int(policy.get("exposure_window_days") or 7)
    # A bet that declares MoneyPath anchoring as required has committed (or is
    # about to commit) execution spend. Exploratory pricing/product bets that
    # have not done so should not trigger eager ledger-repair nudges.
    requires_anchor = any(
        isinstance(item.get("money_path"), dict) and bool(item["money_path"].get("required"))
        for item in active
    )
    summary: dict[str, Any] = {
        "count": len(active),
        "anchored": 0,
        "unanchored": 0,
        "requires_anchor": requires_anchor,
        "gross_exposure": _money_amount(commodity=currency),
        "this_week_at_risk": _money_amount(commodity=currency),
        "over_cap": [],
        "ledger_unavailable": False,
        "checked": False,
    }
    if not active:
        return summary
    try:
        exposure_report = books_mod.exposure(repo=repo, active=True)
    except Exception:
        return {**summary, "ledger_unavailable": True}
    if not exposure_report.get("ok") and not exposure_report.get("exposures"):
        return {**summary, "ledger_unavailable": True}
    exposures = [item for item in exposure_report.get("exposures", []) if isinstance(item, dict)]
    total_mantissa = 0
    total_places = 2
    week_mantissa = 0
    today = date.today()
    for item in exposures:
        raw_anchor = item.get("anchor")
        anchor = raw_anchor if isinstance(raw_anchor, dict) else {}
        if anchor.get("present"):
            summary["anchored"] += 1
        raw_money_path = item.get("money_path")
        money_path = raw_money_path if isinstance(raw_money_path, dict) else {}
        if not anchor.get("present") and money_path.get("required"):
            summary["unanchored"] += 1
        raw_totals = item.get("totals")
        totals = raw_totals if isinstance(raw_totals, dict) else {}
        raw_gross = totals.get("gross_outflow")
        gross = raw_gross if isinstance(raw_gross, dict) else {}
        if gross.get("commodity") == currency:
            total_places = int(gross.get("decimal_places") or total_places)
            total_mantissa += int(gross.get("decimal_mantissa") or 0)
            deadline = str(
                next(
                    (bet.get("deadline") for bet in active if bet.get("path") == item.get("path")),
                    "",
                )
            )
            try:
                deadline_date = date.fromisoformat(deadline)
            except ValueError:
                deadline_date = None
            if (
                deadline_date is not None
                and 0 <= (deadline_date - today).days <= exposure_window_days
            ):
                week_mantissa += int(gross.get("decimal_mantissa") or 0)
        raw_scale_gate = item.get("scale_gate")
        scale_gate = raw_scale_gate if isinstance(raw_scale_gate, dict) else {}
        if scale_gate.get("over_cap"):
            summary["over_cap"].append(
                {
                    "path": str(item.get("path") or ""),
                    "title": str(item.get("title") or ""),
                    "appetite_tier": str(scale_gate.get("appetite_tier") or ""),
                    "gross_exposure": gross,
                    "threshold": scale_gate.get("threshold_amount"),
                    "safe_to_share": True,
                }
            )
    summary["checked"] = True
    summary["gross_exposure"] = _money_amount(
        commodity=currency, decimal_mantissa=total_mantissa, decimal_places=total_places
    )
    summary["this_week_at_risk"] = _money_amount(
        commodity=currency, decimal_mantissa=week_mantissa, decimal_places=total_places
    )
    return summary


def _money_path_finance_actions(
    *, policy: dict[str, Any], active_bets: dict[str, Any], policy_present: bool
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    active_count = int(active_bets.get("count") or 0)
    if (policy_present or active_count) and not policy.get("thresholds_declared"):
        actions.append(
            {
                "id": "declare-appetite-thresholds",
                "title": "Declare MoneyPath appetite thresholds",
                "reason": (
                    "MoneyPath cannot compare active bet exposure to your appetite until "
                    "core/finance/books.md declares thresholds."
                ),
                "route": "/mb-think",
                "component": "financial_exposure",
                "source": "money_path.policy.thresholds_declared",
                "confidence": "medium",
                "missing": ["core/finance/books.md money_path.appetite_thresholds"],
                "safe_to_share": True,
            }
        )
    if (
        active_bets.get("ledger_unavailable")
        and active_count
        and active_bets.get("requires_anchor")
    ):
        actions.append(
            {
                "id": "repair-books-exposure",
                "title": "Repair books exposure checks",
                "reason": (
                    "An active bet requires MoneyPath anchoring, but Main Branch "
                    "cannot check private ledger anchors."
                ),
                "route": "mb books doctor --plan --json",
                "component": "financial_exposure",
                "source": "money_path.active_bets.ledger_unavailable",
                "confidence": "medium",
                "missing": ["hledger exposure check"],
                "safe_to_share": True,
            }
        )
    if int(active_bets.get("unanchored") or 0):
        actions.append(
            {
                "id": "anchor-active-bet-exposure",
                "title": "Anchor active bet exposure",
                "reason": (
                    "One or more active bets require MoneyPath anchors before execution spend."
                ),
                "route": "/mb-bet",
                "component": "financial_exposure",
                "source": "money_path.active_bets.unanchored",
                "confidence": "high",
                "missing": ["ledger bet anchors"],
                "safe_to_share": True,
            }
        )
    if active_bets.get("over_cap"):
        actions.append(
            {
                "id": "review-over-cap-bets",
                "title": "Review bets over appetite",
                "reason": "One or more active bets are over the configured MoneyPath appetite cap.",
                "route": "/mb-bet",
                "component": "financial_exposure",
                "source": "money_path.active_bets.over_cap",
                "confidence": "high",
                "missing": [
                    str(item.get("path") or "") for item in active_bets.get("over_cap", [])
                ],
                "safe_to_share": True,
            }
        )
    return actions


def _money_path(repo: Path, report: dict[str, Any]) -> dict[str, Any]:
    brain = report.get("brain") or {}
    push_report = brain.get("pushes") or {}
    pushes = [item for item in push_report.get("records", []) if isinstance(item, dict)]
    playbook_health = report.get("playbook_health") or {}
    relationship_health = report.get("relationship_health") or {}
    measurement = report.get("measurement") or {}
    playbooks = _playbook_summaries(repo)
    candidate_offer_paths = sorted(
        path.relative_to(repo).as_posix()
        for path in repo.glob("core/offers/*/offer.md")
        if path.is_file()
    )
    candidate_offer_paths.extend(
        _relative_existing_paths(repo, ["core/offer.md", "reference/core/offer.md"])
    )
    proof, proof_paths = _money_path_proof(
        repo,
        offer_paths=candidate_offer_paths,
        pushes=pushes,
        playbooks=playbooks,
        measurement=measurement,
        relationship_health=relationship_health,
    )
    offer = _money_path_offer(
        repo,
        proof_paths=proof_paths,
        proof_quality=proof.get("quality") or _empty_proof_quality(),
    )
    offer_paths = [str(path) for path in offer.get("paths") or [] if (repo / str(path)).is_file()]
    multi_offer = bool(list(repo.glob("core/offers/*/offer.md")))
    collected_objects = {
        "customer_progress": _money_path_customer_progress(repo),
        "offer": offer,
        "audience": _money_path_audience(repo),
        "proof": proof,
        "product_ladder": _money_path_product_ladder(repo, multi_offer=multi_offer),
        "cta_path": _money_path_cta(
            repo,
            offer_paths=offer_paths,
            playbooks=playbooks,
            pushes=pushes,
            measurement=measurement,
        ),
        "channel_strategy": _money_path_channel_strategy(repo, pushes=pushes),
        "active_push": _money_path_active_push(pushes),
        "playbook": _money_path_playbook(playbooks, playbook_health),
        "page_readiness": _money_path_page_readiness(measurement),
        "outcome_feedback_loop": _money_path_outcome_feedback(
            relationship_health,
            playbook_health,
            playbooks,
        ),
    }
    objects = {component: collected_objects[component] for component in MONEY_PATH_COMPONENTS}
    overall_level = _money_path_overall_level(objects)
    books = report.get("books") if isinstance(report.get("books"), dict) else {}
    policy = (
        ((books.get("policy") or {}).get("money_path") or {}) if isinstance(books, dict) else {}
    )
    policy_present = (
        bool((books.get("policy") or {}).get("present")) if isinstance(books, dict) else False
    )
    active_bets = _money_path_active_bet_exposure(repo, report)
    finance_actions = _money_path_finance_actions(
        policy=policy,
        active_bets=active_bets,
        policy_present=policy_present,
    )
    return {
        "schema_version": MONEY_PATH_SCHEMA_VERSION,
        "overall_level": overall_level,
        "overall_label": _money_path_label(overall_level),
        "summary": (
            "MoneyPath reports legibility, support, connection, and instrumentation "
            "from repo facts."
        ),
        "policy": policy,
        "active_bets": active_bets,
        "objects": objects,
        "ranked_actions": [*finance_actions, *_money_path_ranked_actions(objects, overall_level)],
        "safe_to_share": True,
    }


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
                "`noontide-co/mainbranch`. For terminal use, install the CLI "
                "(https://claude.ai/install), then "
                "`claude plugin marketplace add noontide-co/mainbranch`."
            ),
        },
        "skill_wiring": {
            **wiring,
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
        gap for gap in relationship_health.get("gaps") or [] if gap.get("severity") == "warn"
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
