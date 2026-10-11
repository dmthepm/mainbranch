"""Plan git-backed agent checkpoints for business repos."""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from mb import checkpoint_verbs, topology

SURFACE_ORDER = [
    "core",
    "pushes",
    "campaigns",
    "decisions",
    "research",
    "bets",
    "outputs",
    "log",
    "documents",
    "site",
    "config",
    "unknown",
]

REVIEW_REQUIRED_GUIDANCE = (
    "Remove it from the business folder, move it to local scratch space, or rerun "
    "with --include-review-required if it intentionally belongs in this checkpoint."
)

SECRET_RE = re.compile(
    r"(?i)("
    r"(api[_-]?key|access[_-]?token|secret|client[_-]?secret)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{8,}"
    r"|authorization:\s*bearer\s+\S+"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r")"
)

HOOK_NAME = "commit-msg"
HOOK_BEGIN = "# >>> mainbranch checkpoint hook >>>"
HOOK_END = "# <<< mainbranch checkpoint hook <<<"


def _resolved_mb_path() -> str:
    current_command = Path(sys.argv[0])
    if current_command.name == "mb":
        if current_command.is_absolute() and current_command.exists():
            return str(current_command.resolve())
        resolved_command = shutil.which(str(current_command))
        if resolved_command:
            return resolved_command
    return shutil.which("mb") or ""


def _hook_body(mb_path: str = "") -> str:
    quoted_mb = shlex.quote(mb_path)
    return f"""\
#!/bin/sh
{HOOK_BEGIN}
# Main Branch business repos use readable checkpoint subjects.
# This hook validates only the commit subject through the installed mb CLI.
MB_BIN={quoted_mb}

if [ "$#" -lt 1 ]; then
  exit 0
fi

subject=$(sed -n '1p' "$1")
case "$subject" in
  Merge\\ *|Revert\\ *|fixup!\\ *|squash!\\ *|amend!\\ *)
    exit 0
    ;;
esac

git_dir=$(git rev-parse --git-dir 2>/dev/null || true)
if [ -n "$git_dir" ]; then
  case "$1" in
    "$git_dir/MERGE_MSG"|"$git_dir/SQUASH_MSG")
      exit 0
      ;;
  esac
  if [ -e "$git_dir/CHERRY_PICK_HEAD" ]; then
    exit 0
  fi
fi

if [ -n "$MB_BIN" ] && [ -x "$MB_BIN" ]; then
  MB_CHECKPOINT="$MB_BIN"
elif command -v mb >/dev/null 2>&1; then
  MB_CHECKPOINT=$(command -v mb)
else
  echo "Main Branch checkpoint hook could not find the mb CLI." >&2
  echo "Repair: install or update Main Branch, then run: mb doctor repair --apply" >&2
  exit 1
fi

if ! "$MB_CHECKPOINT" checkpoint --validate - < "$1"; then
  echo "" >&2
  echo "Main Branch rejected this checkpoint because the message is not business-readable." >&2
  echo "Use a subject like: [updated] offer.md -- clarified guarantee" >&2
  echo "For a suggested checkpoint, run: mb checkpoint --plan --json" >&2
  echo "If the hook itself is damaged, run: mb doctor repair --apply" >&2
  exit 1
fi
{HOOK_END}
"""


def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(repo),
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(
            ["git", *args],
            127,
            "",
            str(exc),
        )


def _git_error(label: str, result: subprocess.CompletedProcess[str]) -> str:
    details = (result.stderr or result.stdout).strip()
    return f"{label} failed with exit code {result.returncode}: {details or 'no output'}"


def _git_root(repo: Path) -> tuple[Path | None, str | None]:
    result = _run_git(repo, ["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        return None, _git_error("git rev-parse --show-toplevel", result)
    return Path(result.stdout.strip()).resolve(), None


def _git_dir(repo: Path) -> Path | None:
    result = _run_git(repo, ["rev-parse", "--git-dir"])
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    path = Path(raw)
    if not path.is_absolute():
        path = repo / path
    return path.resolve()


def _hook_path(repo: Path) -> tuple[Path | None, str | None, Path | None]:
    root, root_error = _git_root(repo)
    if root is None:
        return None, root_error or "not a git repo", None
    git_dir = _git_dir(root)
    if git_dir is None:
        return root, "could not resolve .git directory", None
    return root, None, git_dir / "hooks" / HOOK_NAME


def _is_engine_repo(repo: Path) -> bool:
    return topology.is_engine_repo(repo)


def _is_managed_hook(text: str) -> bool:
    return HOOK_BEGIN in text and HOOK_END in text


def _normalize_hook_for_compare(text: str) -> str:
    """Blank the baked MB_BIN path so the comparison ignores it.

    The hook bakes ``MB_BIN=<absolute mb path>`` as a fast path, but that path
    legitimately varies by how mb was invoked (a venv bin, a pipx shim, a
    `python -m mb` shim). The hook already falls back to `command -v mb` when
    MB_BIN is not executable, so the path is an optimization, not correctness.
    Comparing it caused a fresh, healthy hook to read as "differs from the
    current template" whenever onboard installed it from one entrypoint and a
    later `mb status` checked it from another (cold-eyes finding, #880).
    """
    return re.sub(r"(?m)^MB_BIN=.*$", "MB_BIN=", text)


def _hook_state_from_text(text: str, expected: str) -> str:
    if not _is_managed_hook(text):
        return "blocked_existing_hook"
    if _normalize_hook_for_compare(text) == _normalize_hook_for_compare(expected):
        return "installed"
    return "broken"


def hook_status(repo: str | Path = ".") -> dict[str, Any]:
    """Inspect the repo-local checkpoint commit-message hook."""
    target = Path(repo).expanduser().resolve()
    root, root_error, hook = _hook_path(target)
    if root is None or hook is None:
        return {
            "ok": False,
            "state": "error",
            "repo": str(target),
            "installed": False,
            "hook": "",
            "managed": False,
            "safe_to_install": False,
            "safe_to_uninstall": False,
            "summary": root_error or "could not inspect git hook",
            "repair_command": "git init",
            "errors": [root_error or "could not inspect git hook"],
        }
    if _is_engine_repo(root):
        return {
            "ok": True,
            "state": "engine_repo",
            "repo": str(root),
            "installed": False,
            "hook": str(hook),
            "managed": False,
            "safe_to_install": False,
            "safe_to_uninstall": False,
            "summary": "engine repo is not governed by business checkpoint hook rules",
            "repair_command": "",
            "errors": [],
        }
    if not hook.exists():
        return {
            "ok": False,
            "state": "missing",
            "repo": str(root),
            "installed": False,
            "hook": str(hook),
            "managed": False,
            "safe_to_install": True,
            "safe_to_uninstall": False,
            "summary": "Main Branch checkpoint commit-message hook is not installed",
            "repair_command": "mb checkpoint --install-hook",
            "errors": [],
        }
    try:
        text = hook.read_text(encoding="utf-8")
    except OSError as exc:
        return {
            "ok": False,
            "state": "error",
            "repo": str(root),
            "installed": False,
            "hook": str(hook),
            "managed": False,
            "safe_to_install": False,
            "safe_to_uninstall": False,
            "summary": f"could not read checkpoint hook: {exc}",
            "repair_command": "mb doctor repair --plan",
            "errors": [str(exc)],
        }
    state = _hook_state_from_text(text, _hook_body(_resolved_mb_path()))
    managed = _is_managed_hook(text)
    installed = state == "installed"
    safe = state in {"installed", "broken"}
    summary = {
        "installed": "Main Branch checkpoint commit-message hook is installed",
        "broken": "Main Branch checkpoint hook is present but differs from the current template",
        "blocked_existing_hook": (
            "an existing commit-msg hook is present; Main Branch will not overwrite it"
        ),
    }[state]
    return {
        "ok": installed,
        "state": state,
        "repo": str(root),
        "installed": installed,
        "hook": str(hook),
        "managed": managed,
        "safe_to_install": safe,
        "safe_to_uninstall": safe,
        "summary": summary,
        "repair_command": "mb checkpoint --install-hook"
        if safe
        else "review .git/hooks/commit-msg, then run mb checkpoint --install-hook",
        "errors": [],
    }


def install_commit_hook(repo: str | Path = ".") -> dict[str, Any]:
    """Install or repair the repo-local Main Branch checkpoint hook."""
    status_report = hook_status(repo)
    state = str(status_report["state"])
    if state == "engine_repo":
        return {
            **status_report,
            "ok": True,
            "installed": False,
            "changed": False,
            "summary": "skipped engine repo; business checkpoint hook not installed",
        }
    if state == "blocked_existing_hook":
        return {
            **status_report,
            "ok": False,
            "changed": False,
            "errors": [
                (
                    "existing .git/hooks/commit-msg is not managed by Main Branch; "
                    "review or move it before installing the checkpoint hook"
                )
            ],
        }
    if state == "error":
        return {**status_report, "changed": False}
    hook = Path(str(status_report["hook"]))
    try:
        hook.parent.mkdir(parents=True, exist_ok=True)
        previous = hook.read_text(encoding="utf-8") if hook.exists() else ""
        hook_body = _hook_body(_resolved_mb_path())
        hook.write_text(hook_body, encoding="utf-8")
        hook.chmod(0o755)
    except OSError as exc:
        return {
            **status_report,
            "ok": False,
            "state": "error",
            "changed": False,
            "summary": f"could not install checkpoint hook: {exc}",
            "errors": [str(exc)],
        }
    changed = previous != hook_body
    return {
        **hook_status(status_report["repo"]),
        "ok": True,
        "changed": changed,
        "summary": (
            "installed Main Branch checkpoint commit-message hook (newly installed or repaired)"
            if changed
            else "verified Main Branch checkpoint commit-message hook (already installed)"
        ),
        "errors": [],
    }


def uninstall_commit_hook(repo: str | Path = ".") -> dict[str, Any]:
    """Remove only the Main Branch-managed checkpoint hook."""
    status_report = hook_status(repo)
    state = str(status_report["state"])
    if state == "missing":
        return {
            **status_report,
            "ok": True,
            "changed": False,
            "summary": "Main Branch checkpoint commit-message hook is already absent",
            "errors": [],
        }
    if state == "engine_repo":
        return {**status_report, "ok": True, "changed": False, "errors": []}
    if state == "blocked_existing_hook":
        return {
            **status_report,
            "ok": False,
            "changed": False,
            "errors": [
                "existing commit-msg hook is not managed by Main Branch; leaving it in place"
            ],
        }
    if state == "error":
        return {**status_report, "changed": False}
    hook = Path(str(status_report["hook"]))
    try:
        hook.unlink()
    except OSError as exc:
        return {
            **status_report,
            "ok": False,
            "state": "error",
            "changed": False,
            "summary": f"could not uninstall checkpoint hook: {exc}",
            "errors": [str(exc)],
        }
    return {
        **hook_status(status_report["repo"]),
        "ok": True,
        "changed": True,
        "summary": "removed Main Branch checkpoint commit-message hook",
        "errors": [],
    }


def _status_records(repo: Path) -> tuple[list[dict[str, Any]], str | None]:
    result = _run_git(repo, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    if result.returncode != 0:
        return [], _git_error("git status --porcelain", result)

    records: list[dict[str, Any]] = []
    parts = result.stdout.split("\0")
    index = 0
    while index < len(parts):
        item = parts[index]
        index += 1
        if not item:
            continue
        raw = item[:2]
        path = item[3:] if len(item) > 3 else ""
        old_path = ""
        if (raw[0] in {"R", "C"} or raw[1] in {"R", "C"}) and index < len(parts):
            old_path = parts[index]
            index += 1
        records.append(
            {
                "path": path,
                "old_path": old_path,
                "git_status": raw,
                "staged": raw[0] not in {" ", "?"},
                "unstaged": raw[1] not in {" ", "?"},
                "untracked": raw == "??",
                "deleted": "D" in raw,
                "conflict": _is_conflict_status(raw),
            }
        )
    return records, None


def _is_conflict_status(raw: str) -> bool:
    return raw in {"DD", "AU", "UD", "UA", "DU", "AA", "UU"} or "U" in raw


def _surface(path: str) -> str:
    if path.startswith("core/") or path == "core":
        return "core"
    if path.startswith("pushes/") or path == "pushes":
        return "pushes"
    if path.startswith("campaigns/") or path == "campaigns":
        return "campaigns"
    if path.startswith("decisions/") or path == "decisions":
        return "decisions"
    if path.startswith("research/") or path == "research":
        return "research"
    if path.startswith("bets/") or path == "bets":
        return "bets"
    if path.startswith("outputs/") or path == "outputs":
        return "outputs"
    if path.startswith("log/") or path == "log":
        return "log"
    if path.startswith("documents/") or path == "documents":
        return "documents"
    if path.startswith(("src/", "app/", "pages/", "components/", "public/", "dist/")):
        return "site"
    if path in {"package.json", "astro.config.mjs", "vite.config.ts", "vite.config.js"}:
        return "site"
    if path.startswith((".github/", ".agents/", ".claude/", ".mainbranch/", ".mb/")):
        return "config"
    if path in {"AGENTS.md", "CLAUDE.md", ".gitignore", "README.md"}:
        return "config"
    return "unknown"


def _safe_read(path: Path, limit: int = 262_144) -> str:
    try:
        data = path.read_bytes()[:limit]
    except OSError:
        return ""
    if b"\x00" in data:
        return ""
    return data.decode("utf-8", errors="ignore")


def _is_env_file(path: str) -> bool:
    name = Path(path).name
    return name == ".env" or name.startswith(".env.")


def _is_local_bridge(path: str) -> bool:
    return (
        path == ".claude/settings.local.json"
        or path.startswith(".claude/skills/")
        or path.startswith(".claude/worktrees/")
        or path.startswith(".mb/backups/")
        or path.startswith(".mb/issue-drafts/")
    )


def _service_account_json(path: str, text: str) -> bool:
    if not path.endswith(".json"):
        return False
    lowered = text.lower()
    return '"type"' in lowered and "service_account" in lowered and "private_key" in lowered


def _review_required(repo: Path, changes: list[dict[str, Any]]) -> list[dict[str, str]]:
    review: list[dict[str, str]] = []
    for change in changes:
        path = str(change["path"])
        name = Path(path).name
        lowered_name = name.lower()
        abs_path = repo / path
        surface = str(change.get("surface", "unknown"))
        if change.get("deleted"):
            continue

        if re.match(r"^untitled(?:[\s._-]*\d*)?(?:\.[^.]+)?$", lowered_name):
            review.append(
                {
                    "code": "generic_untitled_file",
                    "path": path,
                    "message": (
                        "generic Untitled files look like accidental editor scratch, "
                        "not durable business memory"
                    ),
                    "guidance": REVIEW_REQUIRED_GUIDANCE,
                }
            )
            continue

        scratch_suffixes = (
            ".bak",
            ".orig",
            ".rej",
            ".swp",
            ".swo",
            ".tmp",
        )
        scratch_markers = (
            "conflicted copy",
            "merge conflict",
            "merge-conflict",
            ".backup.",
            ".base.",
            ".local.",
            ".remote.",
        )
        if (
            lowered_name.endswith("~")
            or lowered_name.endswith(scratch_suffixes)
            or any(marker in lowered_name for marker in scratch_markers)
        ):
            review.append(
                {
                    "code": "editor_or_conflict_scratch",
                    "path": path,
                    "message": "file looks like editor, backup, or conflict scratch",
                    "guidance": REVIEW_REQUIRED_GUIDANCE,
                }
            )
            continue

        if name != ".gitkeep" and abs_path.is_file() and abs_path.stat().st_size == 0:
            review.append(
                {
                    "code": "zero_byte_file",
                    "path": path,
                    "message": "empty files are often accidental notes or setup leftovers",
                    "guidance": REVIEW_REQUIRED_GUIDANCE,
                }
            )
            continue

        if "prompt" in lowered_name and surface in {"unknown", "config"}:
            review.append(
                {
                    "code": "prompt_draft",
                    "path": path,
                    "message": "prompt drafts should be reviewed before becoming business memory",
                    "guidance": REVIEW_REQUIRED_GUIDANCE,
                }
            )
            continue

        if change.get("untracked") and surface == "unknown":
            review.append(
                {
                    "code": "unexpected_repo_file",
                    "path": path,
                    "message": "file is outside the expected business folders for a checkpoint",
                    "guidance": REVIEW_REQUIRED_GUIDANCE,
                }
            )
    return review


def _safety_blocks(repo: Path, changes: list[dict[str, Any]]) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    if _is_engine_repo(repo):
        blocks.append(
            {
                "code": "engine_repo",
                "path": ".",
                "message": "checkpoint planning is for business repos, not the engine repo",
            }
        )

    git_dir = _git_dir(repo)
    if git_dir is not None:
        for marker in ("MERGE_HEAD", "rebase-merge", "rebase-apply"):
            if (git_dir / marker).exists():
                blocks.append(
                    {
                        "code": "git_operation_in_progress",
                        "path": ".git",
                        "message": f"git operation in progress: {marker}",
                    }
                )

    for change in changes:
        path = str(change["path"])
        abs_path = repo / path
        if change.get("conflict"):
            blocks.append(
                {
                    "code": "merge_conflict",
                    "path": path,
                    "message": "file has an unresolved merge conflict status",
                }
            )
        if _is_local_bridge(path):
            blocks.append(
                {
                    "code": "local_bridge_file",
                    "path": path,
                    "message": "local Claude/Main Branch bridge files must not be checkpointed",
                }
            )
        if _is_env_file(path):
            blocks.append(
                {
                    "code": "env_file",
                    "path": path,
                    "message": "environment files may contain secrets",
                }
            )
        if abs_path.is_symlink() and path.startswith(".claude/"):
            blocks.append(
                {
                    "code": "local_symlink",
                    "path": path,
                    "message": "local Claude symlinks are machine-specific",
                }
            )
        if change.get("deleted") or not abs_path.is_file() or abs_path.is_symlink():
            continue
        text = _safe_read(abs_path)
        if _service_account_json(path, text):
            blocks.append(
                {
                    "code": "service_account_json",
                    "path": path,
                    "message": "service-account JSON contains private credentials",
                }
            )
        elif SECRET_RE.search(text):
            blocks.append(
                {
                    "code": "secret_like_content",
                    "path": path,
                    "message": "file content looks like it may contain a secret",
                }
            )
    return blocks


def _surface_counts(changes: list[dict[str, Any]]) -> dict[str, int]:
    counts = {surface: 0 for surface in SURFACE_ORDER}
    for change in changes:
        counts[str(change["surface"])] += 1
    return {surface: count for surface, count in counts.items() if count}


def _surface_phrase(surfaces: list[str]) -> str:
    if not surfaces:
        return "work"
    labels = {
        "core": "core",
        "pushes": "pushes",
        "campaigns": "campaigns",
        "decisions": "decisions",
        "research": "research",
        "bets": "bets",
        "outputs": "outputs",
        "log": "log",
        "documents": "documents",
        "site": "site",
        "config": "setup",
        "unknown": "repo files",
    }
    named = [labels.get(surface, surface) for surface in surfaces]
    if len(named) == 1:
        return named[0]
    if len(named) == 2:
        return f"{named[0]} and {named[1]}"
    return ", ".join(named[:-1]) + f", and {named[-1]}"


def _slug_words(value: str) -> str:
    slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", value)
    slug = re.sub(r"^(?:unsaved|draft|approved|sanitized)-", "", slug)
    return slug.replace("_", "-").replace("-", " ").strip()


def _core_object_label(path: Path) -> str:
    parts = path.parts
    if len(parts) >= 4 and parts[0] == "core" and parts[1] == "offers":
        offer = _slug_words(parts[2])
        stem = _slug_words(path.stem)
        if path.name == "offer.md":
            return f"{offer} offer"
        if path.name == "audience.md":
            return f"{offer} audience"
        return f"{offer} {stem}"
    if path.name == "offer.md":
        return "offer"
    if path.name == "audience.md":
        return "audience"
    if path.name == "soul.md":
        return "soul"
    if path.name == "voice.md":
        return "voice"
    if path.name == "content-strategy.md":
        return "content strategy"
    if path.name == "product-ladder.md":
        return "product ladder"
    if len(parts) > 1 and parts[1] == "proof":
        return "proof"
    return _slug_words(path.stem)


def _research_object_label(path: Path) -> str:
    slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem)
    slug = re.sub(r"^(?:unsaved|draft|approved|sanitized)-", "", slug)
    if "founder-calls" in slug:
        return "founder-call research"
    label = _slug_words(slug)
    return f"{label} research" if label else "research"


def _object_from_single_change(change: dict[str, Any]) -> str:
    path = str(change["path"])
    surface = str(change["surface"])
    path_obj = Path(path)
    if surface == "bets":
        stem = path_obj.stem if path_obj.suffix else path_obj.name
        return f"bet {stem}"
    if surface == "pushes":
        return (
            f"{_slug_words(path_obj.parent.name)} push"
            if path_obj.name == "push.md"
            else f"{_slug_words(path_obj.stem)} push"
        )
    if surface == "campaigns":
        return (
            f"{_slug_words(path_obj.parent.name)} campaign"
            if path_obj.name == "campaign.md"
            else f"{_slug_words(path_obj.stem)} campaign"
        )
    if surface == "decisions":
        stem = path_obj.stem
        label = stem[11:] if re.match(r"^\d{4}-\d{2}-\d{2}-", stem) else stem
        return f"{_slug_words(label)} decision"
    if surface == "core":
        return _core_object_label(path_obj)
    if surface == "research":
        return _research_object_label(path_obj)
    if surface == "log":
        return f"{_slug_words(path_obj.stem)} log"
    if surface == "documents":
        return f"{_slug_words(path_obj.stem)} document"
    if surface == "config":
        return "setup"
    return path_obj.stem or path_obj.name or path


def _object_phrase(changes: list[dict[str, Any]]) -> str | None:
    if not 1 <= len(changes) <= 3:
        return None
    labels = [_object_from_single_change(change) for change in changes]
    if any(not label or label in {"setup", "repo files"} for label in labels):
        return None
    if len(set(labels)) != len(labels):
        return None
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _proposal_verb(changes: list[dict[str, Any]], surfaces: list[str]) -> tuple[str, str]:
    if not changes:
        return "updated", "default checkpoint action"
    if "bets" in surfaces and all(change.get("untracked") for change in changes):
        return "opened", "new bet files are being saved"
    if surfaces == ["decisions"]:
        return "decided", "decision files changed"
    if surfaces and set(surfaces).issubset({"pushes", "campaigns", "outputs", "site"}):
        if all(change.get("untracked") for change in changes):
            return "drafted", "new reviewable artifact files were created"
        return "updated", "existing shipped-work files changed"
    if surfaces and set(surfaces).issubset({"config"}):
        return "fixed", "setup or wiring files changed"
    if all(change.get("untracked") for change in changes):
        return "added", "new durable business context was created"
    return "updated", "existing durable business context changed"


def _proposal(changes: list[dict[str, Any]], blocks: list[dict[str, str]]) -> dict[str, Any] | None:
    if not changes or blocks:
        return None
    counts = _surface_counts(changes)
    surfaces = [surface for surface in SURFACE_ORDER if surface in counts]
    verb, reason = _proposal_verb(changes, surfaces)
    phrase = _object_phrase(changes)
    if phrase is None:
        phrase = _surface_phrase(surfaces)
    changed_paths = [str(change["path"]) for change in changes]
    message = f"[{verb}] {phrase}"
    parsed = checkpoint_verbs.parse_subject(message)
    validation = checkpoint_verbs.validate_subject(message)
    return {
        "mode": "beginner",
        "message": message,
        "verb": verb,
        "loop": parsed.get("loop"),
        "loops": parsed.get("loops", []),
        "channel_hint": parsed.get("channel_hint"),
        "reason": f"Chosen because {reason}.",
        "validation": validation,
        "body": {
            "changed": changed_paths,
            "why": "Save meaningful business progress before moving on.",
            "next": "Run mb status or /mb-start to continue from repo truth.",
        },
    }


def _commit_body(proposal: dict[str, Any]) -> str:
    body = proposal.get("body", {})
    changed = body.get("changed", []) if isinstance(body, dict) else []
    why = str(body.get("why", "") if isinstance(body, dict) else "")
    next_step = str(body.get("next", "") if isinstance(body, dict) else "")
    lines = ["Changed:"]
    if isinstance(changed, list) and changed:
        lines.extend(f"- {path}" for path in changed)
    else:
        lines.append("- repo files")
    if why:
        lines.extend(["", "Why:", f"- {why}"])
    if next_step:
        lines.extend(["", "Next:", f"- {next_step}"])
    return "\n".join(lines)


def _head_sha(repo: Path) -> str:
    result = _run_git(repo, ["rev-parse", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else ""


def recent(repo: str | Path = ".", *, limit: int = 5) -> dict[str, Any]:
    """Return recent checkpoint commits for resume surfaces."""
    target = Path(repo).resolve()
    root, root_error = _git_root(target)
    if root is None:
        return {
            "ok": False,
            "repo": str(target),
            "commits": [],
            "errors": [root_error or "not a git repo"],
        }
    result = _run_git(
        root,
        [
            "log",
            f"--max-count={limit}",
            f"--grep={checkpoint_verbs.accepted_prefix_pattern()}",
            "--extended-regexp",
            "--format=%H%x1f%ct%x1f%s",
        ],
    )
    if result.returncode != 0:
        return {
            "ok": False,
            "repo": str(root),
            "commits": [],
            "errors": [_git_error("git log checkpoint history", result)],
        }
    commits = []
    for line in result.stdout.splitlines():
        parts = line.split("\x1f", 2)
        if len(parts) != 3:
            continue
        sha, timestamp, subject = parts
        parsed = checkpoint_verbs.parse_subject(subject)
        legacy_checkpoint = subject.startswith("[checkpoint]")
        commits.append(
            {
                "sha": sha,
                "timestamp": int(timestamp) if timestamp.isdigit() else 0,
                "subject": subject,
                "recognized_as": "legacy_checkpoint"
                if legacy_checkpoint
                else "business_verb"
                if parsed.get("recognized")
                else "unknown",
                "verb": parsed.get("verb"),
                "loop": parsed.get("loop"),
                "loops": parsed.get("loops", []),
                "channel_hint": parsed.get("channel_hint"),
                "parsed": parsed,
            }
        )
    return {"ok": True, "repo": str(root), "commits": commits, "errors": []}


def status(repo: str | Path = ".", *, mode: str = "beginner") -> dict[str, Any]:
    """Return checkpoint resume facts: recent checkpoints plus pending plan."""
    planned = plan(repo=repo, mode=mode)
    history = recent(repo=planned.get("repo", repo))
    pending = {
        "status": planned.get("status"),
        "has_changes": planned.get("has_changes", False),
        "summary": planned.get("summary", {}),
        "proposal": planned.get("proposal"),
        "safety": planned.get("safety", {}),
        "errors": planned.get("errors", []),
    }
    return {
        "ok": bool(planned.get("status") != "error" and history.get("ok")),
        "repo": planned.get("repo") or history.get("repo") or str(Path(repo).resolve()),
        "recent": history.get("commits", []),
        "pending": pending,
        "errors": [*planned.get("errors", []), *history.get("errors", [])],
    }


def plan(repo: str | Path = ".", *, mode: str = "beginner") -> dict[str, Any]:
    """Plan a checkpoint without staging or committing changes."""
    target = Path(repo).resolve()
    if mode not in {"beginner", "concern"}:
        return {
            "ok": False,
            "status": "error",
            "repo": str(target),
            "mode": mode,
            "errors": ["mode must be beginner or concern"],
        }
    if not target.exists():
        return {
            "ok": False,
            "status": "error",
            "repo": str(target),
            "mode": mode,
            "errors": ["repo not found"],
        }

    root, root_error = _git_root(target)
    if root is None:
        return {
            "ok": False,
            "status": "error",
            "repo": str(target),
            "mode": mode,
            "errors": [root_error or "not a git repo"],
        }

    records, status_error = _status_records(root)
    if status_error is not None:
        return {
            "ok": False,
            "status": "error",
            "repo": str(root),
            "mode": mode,
            "errors": [status_error],
        }

    changes = [
        {
            **record,
            "surface": _surface(str(record["path"])),
        }
        for record in records
    ]
    blocks = _safety_blocks(root, changes)
    review_required = _review_required(root, changes)
    warnings: list[dict[str, str]] = []
    if topology.classify_repo(root)["kind"] == "none":
        warnings.append(
            {
                "code": "not_business_repo",
                "path": ".",
                "message": "repo does not look like a Main Branch business repo",
            }
        )

    status = "clean"
    if changes:
        if blocks:
            status = "blocked"
        elif review_required:
            status = "review_required"
        else:
            status = "ready"
    proposal = _proposal(changes, blocks)
    counts = _surface_counts(changes)
    return {
        "ok": not blocks and not review_required,
        "status": status,
        "repo": str(root),
        "mode": mode,
        "has_changes": bool(changes),
        "summary": {
            "changed_files": len(changes),
            "staged_files": sum(1 for change in changes if change["staged"]),
            "unstaged_files": sum(1 for change in changes if change["unstaged"]),
            "untracked_files": sum(1 for change in changes if change["untracked"]),
            "surfaces": counts,
        },
        "changes": changes,
        "safety": {
            "ok": not blocks and not review_required,
            "blocks": blocks,
            "review_required": review_required,
            "warnings": warnings,
        },
        "proposal": proposal,
        "errors": [],
    }


def commit(
    repo: str | Path = ".",
    *,
    message: str = "",
    mode: str = "beginner",
    yes: bool = False,
    include_review_required: bool = False,
) -> dict[str, Any]:
    """Commit an approved checkpoint plan."""
    planned = plan(repo=repo, mode=mode)
    if planned.get("status") == "clean":
        return {
            "ok": True,
            "status": "clean",
            "repo": planned.get("repo"),
            "committed": False,
            "plan": planned,
            "errors": [],
        }
    safety = planned.get("safety", {})
    blocks = safety.get("blocks", []) if isinstance(safety, dict) else []
    review_required = safety.get("review_required", []) if isinstance(safety, dict) else []
    if blocks:
        return {
            "ok": False,
            "status": "blocked",
            "repo": planned.get("repo"),
            "committed": False,
            "plan": planned,
            "errors": ["checkpoint plan is blocked"],
        }
    if review_required and not include_review_required:
        return {
            "ok": False,
            "status": "review_required",
            "repo": planned.get("repo"),
            "committed": False,
            "plan": planned,
            "errors": [
                (
                    "checkpoint includes files that need review; remove them or pass "
                    "--include-review-required after confirming they belong in business memory"
                )
            ],
        }
    if not yes:
        return {
            "ok": False,
            "status": "approval_required",
            "repo": planned.get("repo"),
            "committed": False,
            "plan": planned,
            "errors": ["pass --yes after reviewing the checkpoint plan"],
        }

    proposal = planned.get("proposal")
    if not isinstance(proposal, dict):
        return {
            "ok": False,
            "status": "error",
            "repo": planned.get("repo"),
            "committed": False,
            "plan": planned,
            "errors": ["checkpoint plan did not include a proposal"],
        }

    repo_path = Path(str(planned["repo"]))
    commit_message = message.strip() or str(proposal["message"])
    validation = checkpoint_verbs.validate_subject(commit_message)
    if not validation["ok"]:
        return {
            "ok": False,
            "status": "invalid_message",
            "repo": str(repo_path),
            "committed": False,
            "validation": validation,
            "plan": planned,
            "errors": ["checkpoint message is not business-readable"],
        }
    paths = [str(change["path"]) for change in planned.get("changes", [])]
    if not paths:
        return {
            "ok": True,
            "status": "clean",
            "repo": str(repo_path),
            "committed": False,
            "plan": planned,
            "errors": [],
        }

    add = _run_git(repo_path, ["add", "--", *paths])
    if add.returncode != 0:
        return {
            "ok": False,
            "status": "error",
            "repo": str(repo_path),
            "committed": False,
            "plan": planned,
            "errors": [_git_error("git add", add)],
        }
    body = _commit_body({**proposal, "message": commit_message})
    commit_result = _run_git(repo_path, ["commit", "-m", commit_message, "-m", body])
    if commit_result.returncode != 0:
        return {
            "ok": False,
            "status": "error",
            "repo": str(repo_path),
            "committed": False,
            "plan": planned,
            "errors": [_git_error("git commit", commit_result)],
        }

    return {
        "ok": True,
        "status": "committed",
        "repo": str(repo_path),
        "committed": True,
        "commit": {
            "sha": _head_sha(repo_path),
            "message": commit_message,
            "body": body,
        },
        "plan": planned,
        "errors": [],
    }


def validate_message(message: str) -> dict[str, Any]:
    """Validate a proposed checkpoint message."""
    validation = checkpoint_verbs.validate_subject(message)
    return {
        "ok": validation["ok"],
        "status": "valid" if validation["ok"] else "invalid",
        "validation": validation,
        "contract": checkpoint_verbs.contract(),
        "verbs": {
            verb: {
                "prefix": entry.prefix,
                "loops": list(entry.loops),
                "loop": entry.default_loop,
                "channel_hint": entry.channel_hint,
                "use_when": entry.use_when,
            }
            for verb, entry in checkpoint_verbs.registry().items()
        },
        "errors": [problem["message"] for problem in validation.get("errors", [])],
    }


def render_human(result: dict[str, Any]) -> None:
    """Render a checkpoint plan for operators."""
    status = result.get("status")
    print("mb checkpoint")
    if result.get("repo"):
        print(f"repo: {result.get('repo')}")
    if "hook" in result and status not in {"valid", "invalid"}:
        hook_state = result.get("state", status)
        print(f"hook: {result.get('hook')}")
        print(f"state: {hook_state}")
        if result.get("summary"):
            print(str(result["summary"]))
        if result.get("repair_command"):
            print(f"repair: {result['repair_command']}")
        for error in result.get("errors", []):
            print(f"error: {error}")
        return
    if "validation" in result and status in {"valid", "invalid"}:
        validation = result.get("validation", {})
        subject = validation.get("subject", "") if isinstance(validation, dict) else ""
        print(f"message: {subject}")
        if status == "valid":
            parsed = validation.get("parsed", {}) if isinstance(validation, dict) else {}
            loop = parsed.get("loop") if isinstance(parsed, dict) else None
            print("valid business checkpoint message.")
            if loop:
                print(f"loop: {loop}")
            return
        print("invalid checkpoint message.")
        for error in validation.get("errors", []) if isinstance(validation, dict) else []:
            print(f"  - {error['message']}")
            print(f"    fix: {error['guidance']}")
        return
    if status == "committed":
        commit_info = result.get("commit", {})
        sha = commit_info.get("sha", "") if isinstance(commit_info, dict) else ""
        message = commit_info.get("message", "") if isinstance(commit_info, dict) else ""
        print(f"saved checkpoint: {message}")
        if sha:
            print(f"commit: {sha[:12]}")
        return
    if status == "approval_required":
        print("approval required.")
        print("review the plan, then rerun with --yes to save the checkpoint.")
        return
    if status == "review_required":
        print("checkpoint needs review before saving.")
        plan_result = result.get("plan")
        safety_source = plan_result if isinstance(plan_result, dict) else result
        safety = safety_source.get("safety", {}) if isinstance(safety_source, dict) else {}
        review = safety.get("review_required", []) if isinstance(safety, dict) else []
        if review:
            print(
                "These files look like scratch, setup junk, or prompt drafts, "
                "not durable business memory:"
            )
            for item in review:
                print(f"  - {item['path']}: {item['message']}")
            print(
                "Remove them, or rerun with --include-review-required "
                "if they intentionally belong here."
            )
        for error in result.get("errors", []):
            print(f"error: {error}")
        return
    if status == "clean":
        print("nothing to checkpoint.")
        return
    if status == "error":
        for error in result.get("errors", []):
            print(f"error: {error}")
        return
    if status == "invalid_message":
        print("checkpoint message is not business-readable.")
        validation = result.get("validation", {})
        for error in validation.get("errors", []) if isinstance(validation, dict) else []:
            print(f"  - {error['message']}")
            print(f"    fix: {error['guidance']}")
        return

    summary = result.get("summary", {})
    changed_files = summary.get("changed_files", 0)
    print(f"changed files: {changed_files}")
    surfaces = summary.get("surfaces", {})
    if isinstance(surfaces, dict) and surfaces:
        rendered = ", ".join(f"{key}={value}" for key, value in surfaces.items())
        print(f"surfaces: {rendered}")

    safety = result.get("safety", {})
    blocks = safety.get("blocks", []) if isinstance(safety, dict) else []
    if blocks:
        print("")
        print("checkpoint blocked:")
        for block in blocks:
            print(f"  - {block['path']}: {block['message']}")
        return
    review = safety.get("review_required", []) if isinstance(safety, dict) else []
    if review:
        print("")
        print("checkpoint needs review before saving:")
        for item in review:
            print(f"  - {item['path']}: {item['message']}")
        print(
            "Remove them, or rerun with --include-review-required "
            "if they intentionally belong here."
        )
        return

    proposal = result.get("proposal")
    if isinstance(proposal, dict):
        print("")
        print("suggested checkpoint:")
        print(f"  {proposal['message']}")
        if proposal.get("reason"):
            print(f"  {proposal['reason']}")
        print("")
        print("This is a plan only. Rerun with --message and --yes to save it.")
