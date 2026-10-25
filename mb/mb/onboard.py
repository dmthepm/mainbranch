"""``mb onboard`` — adaptive human setup flow for Main Branch."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from mb import books as books_mod
from mb import checkpoint as checkpoint_mod
from mb import codex as codex_mod
from mb import connect as connect_mod
from mb import init as init_mod
from mb import topology as topology_mod
from mb.engine import link_skills, link_status, repo_flag, write_plugin_wiring
from mb.gitignore import gitignore_problem

LEVELS = {"beginner", "intermediate", "power"}
MODES = {"new", "connect", "auto"}
ONBOARDING_STATE_RELATIVE_PATH = Path(".mb") / "onboarding.json"
ONBOARDING_STATE_VERSION = 1
TEAM_SIZES = {"unknown", "solo", "small_team", "larger_team"}
SUCCESS_STAGES = {"unknown", "prelaunch", "working", "successful", "scaling"}
BOOKS_STORAGE_MODES = {"", "solo-local", "team-private-repo", "advanced-vault"}
BUDGET_BANDS = {"", "under-500", "500-2k", "2k-10k", "over-10k", "private"}
THRESHOLD_PRIVACY = {"", "declared", "private", "unknown"}
AMOUNT_FIELDS = (
    "trivial_max_amount",
    "small_max_amount",
    "material_max_amount",
    "strategic_min_amount",
)

BOUNDARIES = {
    "collect_now": [
        "business type and team size",
        "current success stage and desired direction",
        "primary offer, audience, voice, proof, and operating constraints",
        "GitHub/team workflow needs for this business size",
    ],
    "defer_until_needed": [
        "full finances or ledgers",
        "raw customer/member exports",
        "credentials, tokens, and private account secrets",
        "exhaustive operations documentation outside the core files",
    ],
}

ONBOARDING_GITIGNORE_ENTRY = ".mb/onboarding.json"
LOCAL_SETUP_PATH_PREFIXES = (
    ".git/",
    ".mb/",
    ".claude/settings.local.json",
    ".claude/worktrees/",
    ".claude/skills/",
)
TRACKED_LOCAL_SETUP_PATHS = {
    ".mb/schema_version",
}


def _which(name: str) -> str:
    return shutil.which(name) or ""


def _run_command(args: list[str], cwd: Path | None = None, timeout: float = 5.0) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "stderr": f"{args[0]} not found", "returncode": 127}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "command timed out", "returncode": 124}
    except subprocess.SubprocessError as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc), "returncode": 1}
    return {
        "ok": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


def _git_output(repo: Path, args: list[str], timeout: float = 5.0) -> dict[str, Any]:
    return _run_command(["git", *args], cwd=repo, timeout=timeout)


def _has_git_commit(repo: Path) -> bool:
    head = _git_output(repo, ["rev-parse", "--verify", "HEAD"])
    return bool(head["ok"])


def _git_remote(repo: Path) -> str:
    remote = _git_output(repo, ["config", "--get", "remote.origin.url"])
    return remote["stdout"].strip() if remote["ok"] else ""


def _git_branch(repo: Path) -> str:
    branch = _git_output(repo, ["branch", "--show-current"])
    return branch["stdout"].strip() if branch["ok"] else ""


def _tracking_branch(repo: Path) -> str:
    tracking = _git_output(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    return tracking["stdout"].strip() if tracking["ok"] else ""


def _working_tree_dirty(repo: Path) -> bool:
    status = _git_output(repo, ["status", "--porcelain"])
    return bool(status["ok"] and status["stdout"].strip())


def _durable_generated_paths(paths: list[str]) -> list[str]:
    durable: list[str] = []
    for raw in paths:
        rel = raw.strip().replace("\\", "/").strip("/")
        if not rel or rel == ".git":
            continue
        path = Path(rel)
        if path.is_absolute() or ".." in path.parts:
            continue
        if rel not in TRACKED_LOCAL_SETUP_PATHS and any(
            rel == prefix.rstrip("/") or rel.startswith(prefix)
            for prefix in LOCAL_SETUP_PATH_PREFIXES
        ):
            continue
        if rel not in durable:
            durable.append(rel)
    return durable


def _commit_generated_scaffold(
    repo: Path,
    *,
    business_name: str,
    generated_paths: list[str],
) -> dict[str, Any]:
    commit_message = f"[opened] Main Branch scaffold for {business_name or repo.name}"
    result: dict[str, Any] = {
        "ok": False,
        "committed": False,
        "commands": [],
        "errors": [],
        "repair": "",
    }
    durable_paths = _durable_generated_paths(generated_paths)
    if durable_paths:
        add = _git_output(repo, ["add", "--", *durable_paths])
        result["commands"].append("git add -- " + " ".join(durable_paths))
        if not add["ok"]:
            result["errors"].append(add["stderr"].strip() or "git add failed")
            result["repair"] = (
                "Rerun `mb onboard --yes --path <repo> --github <owner/repo> --push` "
                "after the folder is writable."
            )
            return result

    staged = _git_output(repo, ["diff", "--cached", "--quiet", "--"])
    staged_changes = staged["returncode"] == 1
    if staged["returncode"] not in {0, 1}:
        result["errors"].append(staged["stderr"].strip() or "git staged diff failed")
        result["repair"] = (
            "Rerun `mb onboard --yes --path <repo> --github <owner/repo> --push` "
            "after the folder is writable."
        )
        return result
    if staged_changes:
        commit = _git_output(repo, ["commit", "-m", commit_message], timeout=15.0)
        result["commands"].append(f"git commit -m {commit_message!r}")
        if not commit["ok"]:
            result["errors"].append(commit["stderr"].strip() or commit["stdout"].strip())
            result["repair"] = (
                "Configure git author identity if needed, then run "
                f'`git commit -m "{commit_message}"`.'
            )
            return result
        result["committed"] = True
    elif not _has_git_commit(repo):
        result["errors"].append("No durable scaffold files were staged for the first commit.")
        result["repair"] = (
            "Rerun `mb onboard --yes --path <repo> --github <owner/repo> --push` "
            "after the folder is writable."
        )
        return result

    if _working_tree_dirty(repo):
        result["errors"].append("This folder has files Main Branch did not create.")
        result["repair"] = (
            "Move private or scratch files out of the business folder, then rerun "
            "`mb onboard --yes --path <repo> --github <owner/repo> --push`."
        )
        return result

    result["ok"] = True
    return result


def _github_owner(github_repo: str) -> str:
    parts = github_repo.strip().split("/", maxsplit=1)
    return parts[0].strip() if len(parts) == 2 else ""


def _github_preflight(github_repo: str) -> dict[str, Any]:
    owner = _github_owner(github_repo)
    result: dict[str, Any] = {
        "ok": False,
        "authenticated": False,
        "authenticated_account": "",
        "expected_owner": owner,
        "owner_matches_authenticated_account": False,
        "commands": [],
        "errors": [],
        "repair": "",
    }
    auth = _run_command(["gh", "auth", "status"], timeout=5.0)
    result["commands"].append("gh auth status")
    user = _run_command(["gh", "api", "user", "--jq", ".login"], timeout=5.0)
    result["commands"].append("gh api user --jq .login")
    account = user["stdout"].strip() if user["ok"] else ""
    result["authenticated_account"] = account
    result["authenticated"] = bool(auth["ok"] or account)
    result["owner_matches_authenticated_account"] = bool(owner and account and owner == account)
    if not result["authenticated"]:
        result["errors"].append("GitHub CLI is installed but not authenticated.")
        result["repair"] = "Run `gh auth login`, then rerun onboarding."
        return result
    result["ok"] = True
    return result


def _github_create_push(
    repo: Path,
    *,
    business_name: str,
    github_repo: str,
    visibility: str,
    push: bool,
    generated_paths: list[str] | None = None,
) -> dict[str, Any]:
    requested = bool(github_repo.strip())
    result: dict[str, Any] = {
        "requested": requested,
        "ok": not requested,
        "repo": github_repo.strip(),
        "visibility": visibility,
        "committed": False,
        "clean_tree": not _working_tree_dirty(repo),
        "remote_set": bool(_git_remote(repo)),
        "pushed": False,
        "tracking": _tracking_branch(repo),
        "preflight": {},
        "commands": [],
        "errors": [],
        "repair": "",
    }
    if not requested:
        return result
    if visibility not in {"private", "public"}:
        result["errors"].append("github visibility must be private or public")
        result["repair"] = "Use `--github-visibility private` or `--github-visibility public`."
        return result
    if not _which("gh"):
        result["errors"].append("GitHub CLI is not installed.")
        result["repair"] = "Install GitHub CLI, then run `gh auth login`."
        return result
    if not _which("git"):
        result["errors"].append("git is not installed.")
        result["repair"] = "Install git before creating the GitHub repo."
        return result

    preflight = _github_preflight(github_repo.strip())
    result["preflight"] = preflight
    result["commands"].extend(preflight["commands"])
    if not preflight["ok"]:
        result["errors"].extend(str(item) for item in preflight["errors"])
        result["repair"] = str(preflight["repair"])
        return result

    commit_result = _commit_generated_scaffold(
        repo,
        business_name=business_name,
        generated_paths=generated_paths or [],
    )
    result["commands"].extend(commit_result["commands"])
    result["committed"] = bool(commit_result["committed"])
    result["clean_tree"] = commit_result["ok"]
    if not commit_result["ok"]:
        result["errors"].extend(str(item) for item in commit_result["errors"])
        result["repair"] = str(commit_result["repair"])
        return result

    args = ["gh", "repo", "create", github_repo.strip(), f"--{visibility}", "--source", "."]
    if not _git_remote(repo):
        args.extend(["--remote", "origin"])
    if push:
        args.append("--push")
    create = _run_command(args, cwd=repo, timeout=30.0)
    result["commands"].append(" ".join(args))
    if not create["ok"]:
        result["errors"].append(create["stderr"].strip() or create["stdout"].strip())
        result["repair"] = (
            "Run `gh auth login`, then rerun onboarding or create the GitHub repo manually."
        )
        return result
    result["remote_set"] = bool(_git_remote(repo))
    result["tracking"] = _tracking_branch(repo)
    result["pushed"] = bool(push and result["tracking"])
    result["clean_tree"] = not _working_tree_dirty(repo)
    result["ok"] = True
    return result


def _setup_complete(repo: Path, *, github_requested: bool = False) -> dict[str, Any]:
    markers = _repo_markers(repo)
    git_repo = _git_output(repo, ["rev-parse", "--is-inside-work-tree"])
    branch = _git_branch(repo)
    remote = _git_remote(repo)
    tracking = _tracking_branch(repo)
    checkpoint_hook = checkpoint_mod.hook_status(repo)
    wiring = link_status(repo)
    committed = _has_git_commit(repo)
    dirty = _working_tree_dirty(repo)
    return {
        "scaffolded": _looks_initialized(markers),
        "initialized_on_main": bool(git_repo["ok"] and branch == "main"),
        "checkpoint_hook_ready": bool(checkpoint_hook.get("ok")),
        "checkpoint_hook_repair": ""
        if checkpoint_hook.get("ok")
        else f"mb checkpoint{repo_flag(repo)} --install-hook",
        "committed_with_durable_files": bool(committed and not dirty),
        "github_remote_connected": bool(remote),
        "github_remote": remote,
        "pushed_tracking_remote": bool(tracking),
        "tracking_branch": tracking,
        "github_requested": github_requested,
        "claude_code_handoff_ready": bool(wiring.get("ok")),
        "codex_instructions_present": (repo / "AGENTS.md").is_file(),
        "codex_plugin_present": bool(codex_mod.plugin_install_status(repo).get("ok")),
        "owner_outcome": (
            "This business folder is created, saved, synced to GitHub, and ready to open "
            "in Claude Code."
            if github_requested
            and remote
            and tracking
            and wiring.get("ok")
            and committed
            and not dirty
            else "This business folder is created and ready for the next setup step."
        ),
    }


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "my-business"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _state_path(repo: Path) -> Path:
    return repo / ONBOARDING_STATE_RELATIVE_PATH


def _ensure_onboarding_gitignore(repo: Path) -> bool:
    if gitignore_problem(repo):
        return False
    gitignore = repo / ".gitignore"
    existing_text = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    entries = {line.strip() for line in existing_text.splitlines()}
    if ONBOARDING_GITIGNORE_ENTRY in entries or ".mb/" in entries:
        return False
    prefix = "" if not existing_text or existing_text.endswith("\n") else "\n"
    gitignore.write_text(
        existing_text + prefix + ONBOARDING_GITIGNORE_ENTRY + "\n",
        encoding="utf-8",
    )
    return True


def _normalize_team_size(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "": "unknown",
        "one": "solo",
        "one_person": "solo",
        "1": "solo",
        "solo_operator": "solo",
        "small": "small_team",
        "team": "small_team",
        "2_5": "small_team",
        "2_to_5": "small_team",
        "larger": "larger_team",
        "large": "larger_team",
        "6_plus": "larger_team",
        "20_person": "larger_team",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in TEAM_SIZES:
        raise ValueError("team-size must be solo, small-team, larger-team, or unknown")
    return normalized


def _normalize_success_stage(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "": "unknown",
        "not_started": "prelaunch",
        "already_successful": "successful",
        "success": "successful",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in SUCCESS_STAGES:
        raise ValueError(
            "success-stage must be prelaunch, working, successful, scaling, or unknown"
        )
    return normalized


def _load_state(repo: Path) -> dict[str, Any] | None:
    path = _state_path(repo)
    if not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _initial_state(
    *,
    repo: Path,
    business_name: str = "",
    team_size: str = "unknown",
    business_type: str = "",
    success_stage: str = "unknown",
    desired_outcome: str = "",
    money_path: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now()
    return {
        "schema_version": ONBOARDING_STATE_VERSION,
        "kind": "mainbranch.onboarding",
        "created_at": now,
        "updated_at": now,
        "profile": {
            "business_name": business_name.strip(),
            "business_type": business_type.strip(),
            "team_size": _normalize_team_size(team_size),
            "success_stage": _normalize_success_stage(success_stage),
            "desired_outcome": desired_outcome.strip(),
        },
        "money_path": money_path or {},
        "contract": {
            "state_path": str(ONBOARDING_STATE_RELATIVE_PATH),
            "canonical_business_truth": [
                "accepted offer, audience, voice, proof, decisions, and durable summaries",
                (
                    "files under core/, research/, decisions/, bets/, "
                    "pushes/ (legacy campaigns/), log/, and documents/"
                ),
            ],
            "operational_progress": [
                "checklist state, missing input labels, persona/team-size routing, and next action",
                "safe setup metadata that lets a later agent resume without a transcript",
            ],
            "never_store_here": [
                "credentials, secrets, raw customer/member exports, or full finances",
                "chat transcripts or large pasted source dumps",
            ],
        },
        "boundaries": BOUNDARIES,
        "notes": [],
        "source": "mb onboard",
    }


def _merge_state(existing: dict[str, Any] | None, updates: dict[str, Any]) -> dict[str, Any]:
    state = existing.copy() if existing else {}
    if not state:
        state = updates
    else:
        state["schema_version"] = ONBOARDING_STATE_VERSION
        state["kind"] = "mainbranch.onboarding"
        state.setdefault("created_at", updates.get("created_at", _now()))
        state["updated_at"] = _now()
        state.setdefault("contract", updates["contract"])
        state.setdefault("boundaries", BOUNDARIES)
        state.setdefault("notes", [])
        profile = dict(state.get("profile") or {})
        for key, value in updates["profile"].items():
            if value not in {"", "unknown"}:
                profile[key] = value
            else:
                profile.setdefault(key, value)
        state["profile"] = profile
        money_path = dict(state.get("money_path") or {})
        for key, value in (updates.get("money_path") or {}).items():
            if value not in {"", None}:
                money_path[key] = value
            else:
                money_path.setdefault(key, value)
        state["money_path"] = money_path
        state["source"] = updates.get("source", "mb onboard")
    return state


def write_plan(
    repo: str | Path = ".",
    *,
    business_name: str = "",
    team_size: str = "unknown",
    business_type: str = "",
    success_stage: str = "unknown",
    desired_outcome: str = "",
    operating_currency: str = "",
    books_storage_mode: str = "",
    monthly_experiment_budget_band: str = "",
    threshold_privacy: str = "",
    trivial_max_amount: float | int | str | None = None,
    small_max_amount: float | int | str | None = None,
    material_max_amount: float | int | str | None = None,
    strategic_min_amount: float | int | str | None = None,
    approval_required_for_material: bool | str | None = None,
    ledger_anchor_default: bool | str | None = None,
) -> dict[str, Any]:
    """Create or update the lightweight onboarding progress plan."""
    target = Path(repo).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    existing = _load_state(target)
    updates = _initial_state(
        repo=target,
        business_name=business_name,
        team_size=team_size,
        business_type=business_type,
        success_stage=success_stage,
        desired_outcome=desired_outcome,
        money_path=_money_path_inputs(
            operating_currency=operating_currency,
            books_storage_mode=books_storage_mode,
            monthly_experiment_budget_band=monthly_experiment_budget_band,
            threshold_privacy=threshold_privacy,
            trivial_max_amount=trivial_max_amount,
            small_max_amount=small_max_amount,
            material_max_amount=material_max_amount,
            strategic_min_amount=strategic_min_amount,
            approval_required_for_material=approval_required_for_material,
            ledger_anchor_default=ledger_anchor_default,
        ),
    )
    state = _merge_state(existing, updates)
    path = _state_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _ensure_onboarding_gitignore(target)
    return onboarding_status(target)


def _repo_markers(repo: Path) -> dict[str, bool]:
    return {
        "exists": repo.exists(),
        "git": (repo / ".git").exists(),
        "claude_md": (repo / "CLAUDE.md").is_file(),
        "core": (repo / "core").is_dir() or (repo / "reference" / "core").exists(),
        "research": (repo / "research").is_dir(),
        "decisions": (repo / "decisions").is_dir(),
        "skill_start": (repo / ".claude" / "skills" / "mb-start" / "SKILL.md").is_file(),
    }


def _looks_initialized(markers: dict[str, bool]) -> bool:
    shaped_dirs = sum(1 for key in ("core", "research", "decisions") if markers[key])
    return markers["claude_md"] and shaped_dirs >= 2


def _tool_readiness(
    repo: Path,
    *,
    github_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    git_path = _which("git")
    gh_path = _which("gh")
    claude_path = _which("claude")
    gh_auth = False
    gh_repair = ""
    gh_state = "missing_cli"
    git_repo = False

    if git_path:
        git_probe = _run_command(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo)
        git_repo = git_probe["ok"] and git_probe["stdout"].strip() == "true"
    if github_context is not None:
        gh_auth = bool(github_context.get("ok"))
        gh_state = str(github_context.get("state") or ("ready" if gh_auth else "unknown"))
        gh_repair = str(github_context.get("repair") or github_context.get("repair_command") or "")
    elif gh_path:
        gh_probe = _run_command(["gh", "auth", "status"], cwd=repo)
        gh_auth = gh_probe["ok"]
        gh_state = "ready" if gh_auth else "unauthenticated"
        gh_repair = "" if gh_auth else "Run `gh auth login` to connect GitHub tasks and proposals."

    return {
        "git": {
            "found": bool(git_path),
            "path": git_path,
            "repo": git_repo,
            "repair": "" if git_path else "Install git, then run `mb doctor`.",
        },
        "github_cli": {
            "found": bool(gh_path),
            "authenticated": gh_auth,
            "state": gh_state,
            "path": gh_path,
            "repair": ""
            if gh_path and gh_auth
            else gh_repair
            or (
                "Install GitHub CLI: https://cli.github.com/ and run `gh auth login`."
                if not gh_path
                else "Run `gh auth login` to connect GitHub tasks and proposals."
            ),
        },
        "claude_code": {
            "found": bool(claude_path),
            "path": claude_path,
            "repair": "" if claude_path else "Install Claude Code: https://claude.ai/install",
        },
    }


def _infer_level(tool_readiness: dict[str, Any]) -> str:
    git = bool(tool_readiness["git"]["found"])
    gh = bool(
        tool_readiness["github_cli"]["found"] and tool_readiness["github_cli"]["authenticated"]
    )
    claude = bool(tool_readiness["claude_code"]["found"])
    if git and gh and claude:
        return "power"
    if git and (gh or claude):
        return "intermediate"
    return "beginner"


def _normalize_level(level: str) -> str:
    normalized = level.strip().lower().replace("_", "-")
    if normalized == "power-user":
        normalized = "power"
    if normalized and normalized not in LEVELS and normalized != "auto":
        raise ValueError("level must be beginner, intermediate, power, or auto")
    return normalized or "auto"


def _normalize_currency(value: str) -> str:
    currency = (value or "").strip().upper()
    if not currency:
        return ""
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("operating-currency must be a 3-letter currency code such as USD")
    return currency


def _normalize_budget_band(value: str) -> str:
    normalized = (value or "").strip().lower().replace("$", "").replace(",", "")
    normalized = normalized.replace(" ", "-").replace("_", "-")
    aliases = {
        "under-500": "under-500",
        "<500": "under-500",
        "500-2000": "500-2k",
        "500-to-2k": "500-2k",
        "2k-10k": "2k-10k",
        "2000-10000": "2k-10k",
        "over-10000": "over-10k",
        "over-10k": "over-10k",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in BUDGET_BANDS:
        raise ValueError(
            "monthly-experiment-budget-band must be under-500, 500-2k, "
            "2k-10k, over-10k, private, or blank"
        )
    return normalized


def _normalize_threshold_privacy(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in THRESHOLD_PRIVACY:
        raise ValueError("threshold-privacy must be declared, private, unknown, or blank")
    return normalized


def _parse_optional_amount(value: float | int | str | None, *, field: str) -> float | None:
    if value in {None, ""}:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive number")
    try:
        amount = float(str(value).replace(",", "").strip())
    except ValueError as exc:
        raise ValueError(f"{field} must be a positive number") from exc
    if amount <= 0:
        raise ValueError(f"{field} must be a positive number")
    return int(amount) if amount.is_integer() else amount


def _parse_optional_bool(value: bool | str | None, *, field: str) -> bool | None:
    if value in {None, ""}:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{field} must be yes, no, true, false, or blank")


def _money_path_inputs(
    *,
    operating_currency: str = "",
    books_storage_mode: str = "",
    monthly_experiment_budget_band: str = "",
    threshold_privacy: str = "",
    trivial_max_amount: float | int | str | None = None,
    small_max_amount: float | int | str | None = None,
    material_max_amount: float | int | str | None = None,
    strategic_min_amount: float | int | str | None = None,
    approval_required_for_material: bool | str | None = None,
    ledger_anchor_default: bool | str | None = None,
) -> dict[str, Any]:
    storage_mode = (books_storage_mode or "").strip()
    if storage_mode not in BOOKS_STORAGE_MODES:
        raise ValueError(
            "books-storage-mode must be solo-local, team-private-repo, advanced-vault, or blank"
        )
    amounts = {
        "trivial_max_amount": _parse_optional_amount(
            trivial_max_amount, field="trivial-max-amount"
        ),
        "small_max_amount": _parse_optional_amount(small_max_amount, field="small-max-amount"),
        "material_max_amount": _parse_optional_amount(
            material_max_amount, field="material-max-amount"
        ),
        "strategic_min_amount": _parse_optional_amount(
            strategic_min_amount, field="strategic-min-amount"
        ),
    }
    approval_required = _parse_optional_bool(
        approval_required_for_material,
        field="approval-required-for-material",
    )
    ledger_default = _parse_optional_bool(ledger_anchor_default, field="ledger-anchor-default")
    money_path = {
        "operating_currency": _normalize_currency(operating_currency),
        "books_storage_mode": storage_mode,
        "monthly_experiment_budget_band": _normalize_budget_band(monthly_experiment_budget_band),
        "threshold_privacy": _normalize_threshold_privacy(threshold_privacy),
        "approval_required_for_material": approval_required,
        "ledger_anchor_default": ledger_default,
        **amounts,
    }
    return {key: value for key, value in money_path.items() if value not in {"", None}}


def _has_threshold_amounts(money_path: dict[str, Any]) -> bool:
    return any(money_path.get(field) not in {"", None} for field in AMOUNT_FIELDS)


def _threshold_tiers_from_inputs(money_path: dict[str, Any]) -> dict[str, dict[str, Any]]:
    ledger_default = bool(money_path.get("ledger_anchor_default", True))
    approval_required = bool(money_path.get("approval_required_for_material", True))
    tiers: dict[str, dict[str, Any]] = {}
    if money_path.get("trivial_max_amount") is not None:
        tiers["trivial"] = {
            "max_amount": money_path["trivial_max_amount"],
            "approval": "operator",
            "ledger_required": False,
        }
    if money_path.get("small_max_amount") is not None:
        tiers["small"] = {
            "max_amount": money_path["small_max_amount"],
            "approval": "operator",
            "ledger_required": ledger_default,
        }
    if money_path.get("material_max_amount") is not None:
        tiers["material"] = {
            "max_amount": money_path["material_max_amount"],
            "approval": "accepted_decision" if approval_required else "operator",
            "ledger_required": ledger_default,
        }
    if money_path.get("strategic_min_amount") is not None:
        tiers["strategic"] = {
            "min_amount": money_path["strategic_min_amount"],
            "approval": "accepted_decision",
            "ledger_required": ledger_default,
            "requires_exit_rubric": True,
        }
    return tiers


def _books_policy_has_thresholds(repo: Path) -> bool:
    fm, err = books_mod._read_frontmatter(repo / "core" / "finance" / "books.md")
    if err or not fm:
        return False
    policy = books_mod._money_path_policy_from_frontmatter(fm)
    return bool(policy.get("thresholds_declared"))


def _frontmatter_and_body(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "# Bookkeeping\n\nThis file declares public-safe MoneyPath policy only.\n"
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    parsed = yaml.safe_load(text[3:end].strip()) or {}
    body = text[end + 4 :].lstrip("\n")
    return parsed if isinstance(parsed, dict) else {}, body


def _write_books_policy_from_onboarding(repo: Path, money_path: dict[str, Any]) -> bool:
    if money_path.get("threshold_privacy") == "private":
        return False
    tiers = _threshold_tiers_from_inputs(money_path)
    if not tiers:
        return False
    path = repo / "core" / "finance" / "books.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm, body = _frontmatter_and_body(path)
    fm.setdefault("type", "books")
    fm.setdefault("ledger", "hledger")
    fm["operating_currency"] = (
        money_path.get("operating_currency") or fm.get("operating_currency") or "USD"
    )
    fm.setdefault("fiscal_year_start", "01-01")
    fm.setdefault("reporting_cadence", "monthly")
    fm["storage_mode"] = (
        money_path.get("books_storage_mode") or fm.get("storage_mode") or "solo-local"
    )
    if fm["storage_mode"] in books_mod.NON_LOCAL_STORAGE_MODES:
        if str(fm.get("vault_location") or "").strip() == ".mb/private/books/":
            fm["vault_location"] = ""
        else:
            fm.setdefault("vault_location", "")
    else:
        fm.setdefault("vault_location", ".mb/private/books/")
    fm.setdefault("github_backup", False)
    fm.setdefault("encrypted_backup", False)
    fm.setdefault("class_b_data", True)
    raw_money = fm.get("money_path")
    money: dict[str, Any] = raw_money if isinstance(raw_money, dict) else {}
    money.setdefault("scale_basis", "rolling_30_day_gross_outflow")
    money.setdefault("exposure_window_days", 7)
    raw_existing_tiers = money.get("appetite_thresholds")
    existing_tiers = raw_existing_tiers if isinstance(raw_existing_tiers, dict) else {}
    money["appetite_thresholds"] = {**existing_tiers, **tiers}
    fm["money_path"] = money
    path.write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n" + body.lstrip("\n"),
        encoding="utf-8",
    )
    return True


def _normalize_mode(mode: str, existing: bool) -> str:
    normalized = mode.strip().lower()
    if normalized not in MODES:
        raise ValueError("mode must be new, connect, or auto")
    if normalized == "auto":
        return "connect" if existing else "new"
    return normalized


def _next_steps(repo: Path) -> list[str]:
    steps = [
        f"cd {repo}",
        "claude",
        "/mb-start",
    ]
    if _which("codex"):
        steps.extend(
            [
                "mb doctor repair --plan --only codex",
                "mb doctor repair --apply --only codex",
                f"codex -C {repo}",
                "Ask Codex to start this Main Branch business day from read-only mb facts.",
            ]
        )
    # First checkpoint is the operator's first durable memory; name it
    # explicitly so a fresh repo's empty-baseline state self-explains (#880).
    steps.append("Save your first checkpoint once you've made changes: mb checkpoint --plan")
    return steps


def _has_any_file(paths: list[Path]) -> bool:
    for path in paths:
        if path.is_file() and path.name != ".gitkeep" and path.stat().st_size > 0:
            return True
        if path.is_dir():
            for child in path.rglob("*.md"):
                if child.is_file() and child.stat().st_size > 0:
                    return True
    return False


def _core_inputs(repo: Path) -> dict[str, bool]:
    core = repo / "core"
    reference_core = repo / "reference" / "core"
    return {
        "offer": _has_any_file(
            [
                core / "offer.md",
                core / "offers",
                reference_core / "offer.md",
                repo / "reference" / "offers",
            ]
        ),
        "audience": _has_any_file([core / "audience.md", reference_core / "audience.md"]),
        "voice": _has_any_file([core / "voice.md", reference_core / "voice.md"]),
        "soul": _has_any_file([core / "soul.md", reference_core / "soul.md"]),
        "proof": _has_any_file(
            [
                core / "proof",
                core / "proof.md",
                core / "testimonials.md",
                repo / "reference" / "proof",
            ]
        ),
    }


def _profile_missing(profile: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in ("business_type", "success_stage", "desired_outcome"):
        if not str(profile.get(key) or "").strip() or profile.get(key) == "unknown":
            missing.append(key)
    if profile.get("team_size") in {"", "unknown", None}:
        missing.append("team_size")
    return missing


def _team_step(profile: dict[str, Any], repo: Path) -> dict[str, Any]:
    team_size = str(profile.get("team_size") or "unknown")
    team_files = [
        path
        for path in (repo / "core" / "team").glob("*.md")
        if path.is_file() and path.name != "README.md"
    ]
    if team_size == "unknown":
        return {
            "id": "team_layer",
            "title": "Team operating loop",
            "status": "pending",
            "owner": "agent",
            "missing_inputs": ["team_size"],
            "next_action": "Ask whether this is a solo operator, small team, or larger team.",
            "required": False,
        }
    if team_size == "solo":
        missing = [] if team_files else ["core/team/<owner>.md"]
        return {
            "id": "team_layer",
            "title": "Solo operating loop",
            "status": "complete" if not missing else "pending",
            "owner": "agent",
            "missing_inputs": missing,
            "next_action": (
                "Keep the owner file in core/team/ so GitHub activity can use a business name."
            ),
            "required": False,
        }

    missing = []
    if len(team_files) < 2:
        missing.append("core/team/<member>.md for each teammate")
    if not (repo / ".github" / "CODEOWNERS").exists():
        missing.append(".github/CODEOWNERS")
    if not _has_any_file([repo / "decisions", repo / "documents" / "team-workflow.md"]):
        missing.append("team workflow or decision note")
    label = "Small-team GitHub loop" if team_size == "small_team" else "Larger-team GitHub loop"
    return {
        "id": "team_layer",
        "title": label,
        "status": "complete" if not missing else "pending",
        "owner": "agent",
        "missing_inputs": missing,
        "next_action": (
            "Document owners, review expectations, and where team tasks/proposals live."
        ),
        "required": team_size in {"small_team", "larger_team"},
    }


def _step(
    *,
    step_id: str,
    title: str,
    complete: bool,
    missing_inputs: list[str],
    next_action: str,
    owner: str = "agent",
    required: bool = True,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "title": title,
        "status": "complete" if complete else "pending",
        "owner": owner,
        "required": required,
        "missing_inputs": missing_inputs,
        "next_action": next_action,
    }


def _checklist(repo: Path, state: dict[str, Any], markers: dict[str, bool]) -> list[dict[str, Any]]:
    flag = repo_flag(repo)
    profile = dict(state.get("profile") or {})
    money_path = dict(state.get("money_path") or {})
    core_inputs = _core_inputs(repo)
    missing_core = [key for key, ok in core_inputs.items() if not ok]
    wiring = link_status(repo)
    checkpoint_hook = checkpoint_mod.hook_status(repo)
    threshold_status = (
        money_path.get("threshold_privacy") == "private"
        or _has_threshold_amounts(money_path)
        or _books_policy_has_thresholds(repo)
    )
    return [
        _step(
            step_id="repo_scaffold",
            title="Business repo scaffold",
            complete=_looks_initialized(markers),
            missing_inputs=[]
            if _looks_initialized(markers)
            else ["CLAUDE.md", "core/", "research/", "decisions/"],
            next_action="Run `mb onboard --mode new --path <repo> --name <business>`.",
            owner="mb",
        ),
        _step(
            step_id="business_profile",
            title="Business profile and success direction",
            complete=not _profile_missing(profile),
            missing_inputs=_profile_missing(profile),
            next_action=(
                "Ask only for business type, team size, current success stage, "
                "and desired outcome; do not collect full operations detail yet."
            ),
        ),
        _step(
            step_id="core_reference",
            title="Core files",
            complete=not missing_core,
            missing_inputs=missing_core,
            next_action=(
                "Collect just enough to draft core offer, audience, voice, soul, and proof files."
            ),
        ),
        _team_step(profile, repo),
        _step(
            step_id="money_path_thresholds",
            title="MoneyPath appetite thresholds",
            complete=threshold_status,
            missing_inputs=[]
            if threshold_status
            else ["money_path.appetite_thresholds or private threshold choice"],
            next_action=(
                "Optionally collect safe appetite thresholds; never collect revenue, "
                "balances, payees, payroll, raw ledger rows, or customer payments."
            ),
            owner="agent",
            required=False,
        ),
        _step(
            step_id="runtime_handoff",
            title="Runtime handoff",
            complete=bool(wiring["ok"]),
            missing_inputs=[] if wiring["ok"] else ["Claude Code skill wiring"],
            next_action=(
                f"Run `mb skill link{flag or ' --repo .'}`, then `mb start{flag} --json`."
            ),
            owner="mb",
        ),
        _step(
            step_id="checkpoint_hook",
            title="Checkpoint save hook",
            complete=bool(checkpoint_hook["ok"]),
            missing_inputs=[]
            if checkpoint_hook["ok"]
            else ["business-readable checkpoint commit hook"],
            next_action=(
                f"Run `mb doctor repair{flag} --plan`, then `mb doctor repair{flag} --apply`."
            ),
            owner="mb",
            required=False,
        ),
    ]


def onboarding_status(repo: str | Path = ".") -> dict[str, Any]:
    """Return the deterministic onboarding progress envelope for a business repo."""
    target = Path(repo).expanduser().resolve()
    loaded = _load_state(target)
    state = loaded or _initial_state(repo=target)
    markers = _repo_markers(target)
    checklist = _checklist(target, state, markers)
    topology = topology_mod.collect(target)
    required = [step for step in checklist if step.get("required", True)]
    complete = [step for step in required if step["status"] == "complete"]
    next_step = next((step for step in checklist if step["status"] != "complete"), None)
    return {
        "ok": _looks_initialized(markers),
        "repo": str(target),
        "state_path": str(_state_path(target)),
        "state_exists": loaded is not None,
        "state_valid": loaded is not None or not _state_path(target).exists(),
        "profile": state.get("profile") or {},
        "money_path": state.get("money_path") or {},
        "contract": state.get("contract") or {},
        "boundaries": state.get("boundaries") or BOUNDARIES,
        "repo_boundary": topology["repo_boundary"],
        "checklist": checklist,
        "summary": {
            "status": "ready" if len(complete) == len(required) else "in_progress",
            "completed_required": len(complete),
            "total_required": len(required),
            "missing_inputs": [
                item for step in required for item in step.get("missing_inputs", [])
            ],
            "next_step": next_step["id"] if next_step else "",
            "next_recommended_action": next_step["next_action"] if next_step else "Run `mb start`.",
        },
    }


def run(
    *,
    path: str,
    name: str = "",
    owner_name: str = "",
    owner_github: str = "",
    mode: str = "auto",
    level: str = "auto",
    team_size: str = "unknown",
    business_type: str = "",
    success_stage: str = "unknown",
    desired_outcome: str = "",
    operating_currency: str = "",
    books_storage_mode: str = "",
    monthly_experiment_budget_band: str = "",
    threshold_privacy: str = "",
    trivial_max_amount: float | int | str | None = None,
    small_max_amount: float | int | str | None = None,
    material_max_amount: float | int | str | None = None,
    strategic_min_amount: float | int | str | None = None,
    approval_required_for_material: bool | str | None = None,
    ledger_anchor_default: bool | str | None = None,
    github_repo: str = "",
    github_visibility: str = "private",
    github_push: bool = False,
) -> dict[str, Any]:
    """Create or connect a business repo and verify the Claude Code handoff."""
    target = Path(path).expanduser().resolve()
    money_path_inputs = _money_path_inputs(
        operating_currency=operating_currency,
        books_storage_mode=books_storage_mode,
        monthly_experiment_budget_band=monthly_experiment_budget_band,
        threshold_privacy=threshold_privacy,
        trivial_max_amount=trivial_max_amount,
        small_max_amount=small_max_amount,
        material_max_amount=material_max_amount,
        strategic_min_amount=strategic_min_amount,
        approval_required_for_material=approval_required_for_material,
        ledger_anchor_default=ledger_anchor_default,
    )
    before = _repo_markers(target)
    normalized_mode = _normalize_mode(mode, _looks_initialized(before))

    errors: list[str] = []
    warnings: list[str] = []
    created: list[str] = []
    action = normalized_mode
    result_business_name = name.strip() if normalized_mode == "connect" else ""
    init_result: dict[str, Any] | None = None
    link_result: dict[str, Any] | None = None
    github_result: dict[str, Any] | None = None

    if normalized_mode == "connect" and not target.exists():
        errors.append(f"cannot connect missing repo: {target}")
    elif normalized_mode == "connect" and not _looks_initialized(before):
        errors.append(
            "Existing repo does not look like a Main Branch repo. "
            "Run `mb onboard --mode new --path <repo> --name <business>` to scaffold it."
        )
    elif normalized_mode == "connect":
        link_result = link_skills(target)
        created.extend(str(item) for item in link_result.get("created", []))
        if not link_result.get("ok"):
            errors.extend(str(item) for item in link_result.get("errors", []))
        # Wire the plugin (primary cross-surface rail) by default on connect
        # too (decision 2026-06-10, Stage 3). Idempotent.
        plugin_wiring = write_plugin_wiring(target)
        if plugin_wiring.get("changed") and ".claude/settings.json" not in created:
            created.append(".claude/settings.json")
        action = "repaired" if before["claude_md"] else "connected"
    else:
        business_name = name.strip() or target.name.replace("-", " ").title()
        result_business_name = business_name
        init_result = init_mod.run(
            path=str(target),
            name=business_name,
            owner_name=owner_name,
            owner_github=owner_github,
            # Declining GitHub must not scrape the machine's gh login into
            # the scaffold (cold-eyes finding, #880) — infer only when the
            # operator actually chose a GitHub path.
            infer_github_identity=bool(github_repo.strip()),
        )
        created.extend(str(item) for item in init_result.get("created", []))
        warnings.extend(str(item) for item in init_result.get("warnings", []))
        if init_result["status"] == "error":
            errors.append(str(init_result.get("error") or "mb init failed"))
        elif init_result["status"] == "already-initialized":
            action = "repaired"
        else:
            action = "created"

    if (
        target.exists()
        and not errors
        and _write_books_policy_from_onboarding(target, money_path_inputs)
    ):
        created.append("core/finance/books.md")

    after = _repo_markers(target)
    wiring = link_status(target)
    tools = _tool_readiness(target)
    selected_level = _normalize_level(level)

    if not after["git"]:
        warnings.append("Repo is not a git work tree. Run `git init` or `mb doctor` for repair.")
    # A recorded budget band with no thresholds and no private choice leaves the
    # MoneyPath checklist silently todo — say what's still missing (#880).
    if (
        money_path_inputs.get("monthly_experiment_budget_band")
        and not _has_threshold_amounts(money_path_inputs)
        and money_path_inputs.get("threshold_privacy") != "private"
    ):
        warnings.append(
            "Recorded the monthly budget band, but MoneyPath thresholds are still "
            "open — add trivial/small/material amounts (or pass "
            "--threshold-privacy private to record that you're keeping them private)."
        )
    checkpoint_hook = (
        init_result.get("checkpoint_hook")
        if init_result
        else checkpoint_mod.hook_status(target)
        if target.exists()
        else None
    )
    if isinstance(checkpoint_hook, dict) and not checkpoint_hook.get("ok"):
        warnings.append(str(checkpoint_hook.get("summary") or "Checkpoint hook needs repair."))

    if github_repo.strip() and target.exists() and not errors:
        github_result = _github_create_push(
            target,
            business_name=result_business_name,
            github_repo=github_repo,
            visibility=github_visibility.strip().lower(),
            push=github_push,
            generated_paths=created,
        )
        if not github_result.get("ok"):
            errors.extend(str(item) for item in github_result.get("errors", []))
            if github_result.get("repair"):
                warnings.append(str(github_result["repair"]))
        else:
            github_context = connect_mod.github_context(
                target,
                which_func=_which,
                command_runner=_run_command,
            )
            tools = _tool_readiness(target, github_context=github_context)

    if selected_level == "auto":
        selected_level = _infer_level(tools)

    if not tools["github_cli"]["found"] or not tools["github_cli"]["authenticated"]:
        warnings.append(str(tools["github_cli"]["repair"]))
    if not tools["claude_code"]["found"]:
        warnings.append(str(tools["claude_code"]["repair"]))
    if not wiring["ok"]:
        warnings.append("Claude Code skill discovery is not wired. Run `mb doctor` for details.")

    ok = not errors and wiring["ok"] and after["claude_md"]
    progress = (
        write_plan(
            target,
            business_name=result_business_name,
            team_size=team_size,
            business_type=business_type,
            success_stage=success_stage,
            desired_outcome=desired_outcome,
            operating_currency=operating_currency,
            books_storage_mode=books_storage_mode,
            monthly_experiment_budget_band=monthly_experiment_budget_band,
            threshold_privacy=threshold_privacy,
            trivial_max_amount=trivial_max_amount,
            small_max_amount=small_max_amount,
            material_max_amount=material_max_amount,
            strategic_min_amount=strategic_min_amount,
            approval_required_for_material=approval_required_for_material,
            ledger_anchor_default=ledger_anchor_default,
        )
        if target.exists() and not errors
        else onboarding_status(target)
    )
    return {
        "ok": ok,
        "status": "ok" if ok else "error",
        "action": action,
        "path": str(target),
        "mode": normalized_mode,
        "level": selected_level,
        "business_name": result_business_name,
        "created": created,
        "repo": {
            "before": before,
            "after": after,
            "looks_initialized": _looks_initialized(after),
        },
        "tools": tools,
        "skill_wiring": wiring,
        "warnings": [warning for warning in warnings if warning],
        "errors": errors,
        "doctor_command": f"mb doctor {target}",
        "checkpoint_hook": checkpoint_hook,
        "github": github_result
        or _github_create_push(
            target,
            business_name=result_business_name,
            github_repo="",
            visibility=github_visibility.strip().lower(),
            push=False,
        ),
        "setup_complete": _setup_complete(target, github_requested=bool(github_repo.strip()))
        if target.exists()
        else {},
        "onboarding": progress,
        "next_steps": _next_steps(target),
        "init": init_result,
        "link": link_result,
    }


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()
