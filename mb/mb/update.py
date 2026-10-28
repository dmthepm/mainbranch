"""Install-mode-aware Main Branch engine updates."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mb import __version__, claude_guidance
from mb import codex as codex_mod
from mb import unreadable as unreadable_mod
from mb.doctor import _not_business_folder_guard, codex_repair_actions
from mb.engine import (
    PLUGIN_INSTALL_COMMAND,
    bundled_skills,
    claude_mainbranch_plugin_status,
    engine_root,
    install_mode,
    looks_like_uv_tool_install,
    operator_action,
    plan_link_skills,
    plugin_switch_operator_action,
    plugin_wiring_status,
    repo_flag,
)

# Re-exported: callers and tests read these from `mb.update`.
from mb.freshness import (
    PIP_UPDATE_COMMAND_TEXT as PIP_UPDATE_COMMAND_TEXT,
)
from mb.freshness import (
    PIPX_UPDATE_COMMAND_TEXT as PIPX_UPDATE_COMMAND_TEXT,
)
from mb.freshness import (
    UV_UPDATE_COMMAND_TEXT as UV_UPDATE_COMMAND_TEXT,
)
from mb.freshness import (
    checked_release_version,
    compare_versions,
    release_notes_url,
)
from mb.freshness import (
    latest_pypi_version as _latest_pypi_version,
)
from mb.freshness import (
    uv_update_command_text as uv_update_command_text,
)

VERSION_RE = re.compile(r'__version__\s*=\s*["\']([^"\']+)["\']')
CLONE_UPDATE_COMMAND = ["git", "pull", "--ff-only", "origin", "main"]
# Fallback when the latest version is unknown; a known PyPI version is pinned.
UV_UPDATE_COMMAND = UV_UPDATE_COMMAND_TEXT.split()


def _uv_update_command(latest: str | None) -> list[str]:
    return uv_update_command_text(latest).split()


UV_MANUAL_MESSAGE = (
    "Main Branch was installed as a uv tool. Upgrading replaces the installed "
    "command, so it only runs after an explicit yes at an interactive prompt. "
    "The command below is yours to run, or run `{update}` from a terminal to "
    "be asked."
)
UV_DECLINED_MESSAGE = (
    "Left the installed Main Branch alone. The command below is yours to run "
    "whenever you want the upgrade."
)
WHEEL_MANUAL_MESSAGE = (
    "Main Branch does not upgrade a plain wheel install for you. The command "
    "below is yours to run from the environment that owns this install."
)
UV_TOOL_DIR_COMMAND = ["uv", "tool", "dir"]
UV_TOOL_DIR_TIMEOUT_SECONDS = 10.0
SURFACE_PLAN_NO_TERMINAL_MESSAGE = (
    "Left repo files unchanged: {files}. Without an interactive terminal, "
    "`mb update` does not change tracked files in the business repo or create "
    "new ones. Applying these changes is the operator's step: review them, "
    "then run the commands below from a terminal."
)
SURFACE_PLAN_DECLINED_MESSAGE = (
    "Left repo files unchanged: {files}. Run the commands below whenever you want these changes."
)
SURFACE_LINK_APPLY_NOTE = (
    "For a person to run at a terminal, not an agent: refreshes this repo's "
    "Claude Code skill links, which writes the repo files listed in `changes`."
)
CHECK_PLAN_UNREADABLE_MESSAGE = (
    "Could not read {target} ({error}), so this check cannot plan the {part} "
    "refresh or say which repo files it would change. A real `mb update` stops "
    "there too, with an error. {fix}, then run the check again."
)
SURFACE_CODEX_APPLY_NOTE = (
    "For a person to run at a terminal, not an agent: refreshes this repo's "
    "Codex guidance, which writes or deletes the tracked files listed in "
    "`changes`. Review the read-only plan in `next_actions` first."
)
AHEAD_OF_PYPI_MESSAGE = (
    "Installed Main Branch {installed} is newer than PyPI's latest release "
    "({latest}), so there is nothing to install. Installing the latest release "
    "would replace this build with an older version."
)
LATEST_UNKNOWN_MESSAGE = (
    "Main Branch could not check PyPI for the latest version, so it left this "
    "install ({installed}) alone. Installing without that check could replace it "
    "with an older version. Check your connection, then run `{retry}` again."
)
GITHUB_RELEASE_API_URL_TEMPLATE = (
    "https://api.github.com/repos/dmthepm/mainbranch/releases/tags/oe-v{version}"
)
COMMAND_TIMEOUT_SECONDS = 120.0
UV_RELEASE_NOT_READY_MESSAGE = (
    "Main Branch {version} is a new release and uv cannot find it yet. "
    "Your current install is unchanged. Retry `mb update` in a few minutes."
)


def _uv_release_not_ready(result: subprocess.CompletedProcess[str], latest: str | None) -> bool:
    """Recognize uv's missing pinned version after PyPI supplied that version."""
    if latest is None:
        return False
    output = _command_output(result)
    pattern = (
        rf"\bno (?:matching )?version(?: found)? for[ \t]+mainbranch=={re.escape(latest)}"
        r"(?![\w.+-])"
    )
    # PyPI package names are case-insensitive, so accept MainBranch too.
    return re.search(pattern, output, flags=re.IGNORECASE) is not None


def _run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: float = COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=str(cwd) if cwd is not None else None,
            # Children never read the operator's typing meant for our prompts.
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            args=args,
            returncode=124,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=f"timed out after {timeout:g}s",
        )


def _engine_version(root: Path | None = None) -> str:
    root = root or engine_root()
    if root is None:
        return __version__

    candidates = [
        root / "mb" / "mb" / "__init__.py",
        root / "mb" / "__init__.py",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        match = VERSION_RE.search(candidate.read_text(encoding="utf-8"))
        if match:
            return match.group(1)
    return __version__


def _version_from_git_ref(root: Path, ref: str) -> str | None:
    result = _run_command(["git", "show", f"{ref}:mb/mb/__init__.py"], cwd=root)
    if result.returncode != 0:
        return None
    match = VERSION_RE.search(result.stdout)
    return match.group(1) if match else None


def _fetch_origin_main(root: Path) -> tuple[bool, str | None]:
    result = _run_command(
        ["git", "fetch", "origin", "main:refs/remotes/origin/main", "--quiet"],
        cwd=root,
    )
    if result.returncode == 0:
        return True, None
    return False, _command_error("git fetch origin main", result)


def _current_mb_entrypoint() -> str:
    candidate = Path(sys.argv[0])
    if candidate.name == "mb" and candidate.exists():
        return str(candidate)
    return "mb"


def _version_from_mb_command(command: str | None = None) -> str | None:
    result = _run_command([command or _current_mb_entrypoint(), "--version"])
    if result.returncode != 0:
        return None
    match = re.search(r"\bmb\s+(.+)\s*$", result.stdout.strip())
    return match.group(1) if match else None


def _command_error(label: str, result: subprocess.CompletedProcess[str]) -> str:
    named = _unreadable_command_error(result)
    if named:
        return named
    details = (result.stderr or result.stdout).strip()
    return f"{label} failed with exit code {result.returncode}: {details or 'no output'}"


def _unreadable_command_error(result: subprocess.CompletedProcess[str]) -> str:
    """The sentence an `mb ... --json` step printed for a file it could not read (#1106)."""
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        return ""
    errors = payload.get("errors") if isinstance(payload, dict) else None
    for item in errors if isinstance(errors, list) else []:
        if isinstance(item, dict) and item.get("code") == unreadable_mod.JSON_ERROR_CODE:
            return str(item.get("message") or "")
    return ""


def _command_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part.strip() for part in (result.stderr, result.stdout) if part.strip())


def _is_interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _uv_tool_dir_holds_this_install() -> bool:
    """True when uv's own tool directory contains the running install.

    `install_mode()` checks the documented uv tool roots by path. An operator
    can move that root, so ask uv where it actually is — but still require that
    *this* engine root or interpreter lives under it.

    `uv tool list` cannot answer that question. It names installed tools without
    paths, so on a machine that has a uv tool install of Main Branch it also
    matches an unrelated `pip install mainbranch` virtualenv, and would hand
    that operator a command that upgrades a different install (#963).

    Runs only on the `mb update` path, so diagnostics stay subprocess-free.
    """
    if shutil.which("uv") is None:
        return False
    located = _run_command(UV_TOOL_DIR_COMMAND, timeout=UV_TOOL_DIR_TIMEOUT_SECONDS)
    if located.returncode != 0:
        return False
    tool_root = located.stdout.strip()
    if not tool_root:
        return False
    return looks_like_uv_tool_install(engine_root(), tool_roots=[Path(tool_root)])


def _resolve_install_mode() -> str:
    """Install mode for update decisions, asking uv for its real tool root."""
    mode = install_mode()
    if mode == "wheel" and _uv_tool_dir_holds_this_install():
        return "uv"
    return mode


def _confirm_uv_update(command: str, root: Path | None) -> bool:
    """Ask before running a real installer. Default is no."""
    print("Main Branch was installed as a uv tool.")
    if root is not None:
        print(f"engine root: {root}")
    print(f"This will run: {command}")
    try:
        answer = input("Run it now? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in {"y", "yes"}


def _confirm_surface_writes(repo: Path, files: list[str]) -> bool:
    """Ask once before refreshing agent surfaces changes repo files. Default is no."""
    print(f"Refreshing agent surfaces would change these files in {repo}:")
    for path in files:
        print(f"  - {path}")
    try:
        answer = input("Apply these changes now? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in {"y", "yes"}


def _checked_latest_version() -> str | None:
    """PyPI's latest Main Branch version, or None when it could not be established.

    None covers a failed or timed-out lookup and an answer that is not a
    release version. Callers treat None as "freshness unknown", never as
    permission to install.
    """
    return checked_release_version(_latest_pypi_version())


def _note_latest_unknown(result: dict[str, Any], *, retry: str) -> None:
    """Record that PyPI's latest version could not be checked, so nothing installs.

    Without a known latest version no installer may run: a timed-out JSON
    lookup says nothing about what an installer's own index would resolve, and
    `@latest` could be older than the installed build. `ok` stays true and the
    installed version is kept; the only next action is the retry.
    """
    old = str(result.get("old_version") or "")
    result["latest_version_unknown"] = True
    result["new_version"] = result["old_version"]
    result["warnings"].append(
        LATEST_UNKNOWN_MESSAGE.format(installed=old or "unknown", retry=retry)
    )
    if retry not in result["next_actions"]:
        result["next_actions"].append(retry)


def _note_manual_update(
    result: dict[str, Any],
    *,
    command: str,
    message: str,
    latest: str | None,
) -> None:
    """Hand the operator the command that works instead of dead-ending (#963).

    `ok` stays true: nothing failed. `upgrade_performed` stays false so no
    caller reads this as an applied update. `new_version` reports what PyPI
    actually offers rather than echoing the installed version, so `mb update
    --json` and the `/mb-update` skill cannot read this as "already current".

    This records the outcome; it does not end the run. Refreshing agent
    surfaces needs no package upgrade, so the manual paths continue into the
    same surface refresh every other mode gets.
    """
    if _note_ahead_of_pypi(result, latest):
        return
    result["new_version"] = latest or result["old_version"]
    result["manual_update_command"] = command
    result["warnings"].append(
        message.replace("{update}", _update_command(str(result.get("repo") or ".")))
    )
    if command not in result["next_actions"]:
        result["next_actions"].append(command)


def _note_ahead_of_pypi(result: dict[str, Any], latest: str | None) -> bool:
    """Record a pre-release or local build that is newer than PyPI's latest (#1022).

    Returns True when the installed version is ahead. The result then keeps
    `new_version` at the installed version and lists no install command, because
    every installer's `latest` would be a downgrade.
    """
    if latest:
        result["latest_version"] = latest
    old = str(result.get("old_version") or "")
    if not latest or not old or compare_versions(old, latest) <= 0:
        return False
    result["installed_ahead_of_latest"] = True
    result["new_version"] = old
    result["warnings"].append(AHEAD_OF_PYPI_MESSAGE.format(installed=old, latest=latest))
    return True


def _note_already_current(result: dict[str, Any], latest: str | None) -> bool:
    """Record a uv or wheel install that already runs PyPI's latest release (#1036).

    Returns True when the installed version equals ``latest``. The result then
    keeps `new_version` at the installed version, leaves `manual_update_command`
    empty and lists no install command: reinstalling the same release changes
    nothing, so there is nothing for the operator to confirm or run.
    """
    old = str(result.get("old_version") or "")
    if not latest or not old or compare_versions(old, latest) != 0:
        return False
    result["latest_version"] = latest
    result["new_version"] = old
    return True


def _looks_like_pipx_package_spec_parse_failure(
    result: subprocess.CompletedProcess[str],
) -> bool:
    output = _command_output(result).lower()
    if "package spec" not in output:
        return False
    parse_phrases = ("unable to parse", "could not parse", "cannot parse")
    if not any(phrase in output for phrase in parse_phrases):
        return False
    return ".whl" in output or "/" in output or "\\" in output


def _pipx_force_install_recovery_command(latest: str | None) -> str:
    if latest:
        return f"pipx install --force mainbranch=={latest}"
    return "pipx install --force mainbranch"


def _add_pipx_package_spec_recovery(
    result: dict[str, Any],
    upgrade: subprocess.CompletedProcess[str],
    latest: str | None,
) -> None:
    if not _looks_like_pipx_package_spec_parse_failure(upgrade):
        return
    # Reuses the run's one PyPI lookup rather than asking again (#1028).
    command = _pipx_force_install_recovery_command(latest)
    result["warnings"].append(
        "pipx could not parse the saved Main Branch install spec. This can happen "
        "after installing from a local wheel path. Approve a forced pipx reinstall "
        "to reset the saved install source."
    )
    result["next_actions"].append(command)


def _list_field(result: dict[str, Any], key: str) -> list[str]:
    value = result.get(key, [])
    return [str(item) for item in value] if isinstance(value, list) else []


def _skill_count_from_link_result(result: dict[str, Any]) -> int:
    total = 0
    for key in ("linked", "copied"):
        total += len(_list_field(result, key))
    return total


def _release_summary(body: str) -> str:
    lines: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            if lines:
                break
            continue
        if line.startswith("#"):
            continue
        lines.append(line)
    return " ".join(lines)


def _release_context(version: str, *, timeout: float = 3.0) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    version = version.strip()
    context: dict[str, Any] = {
        "version": version,
        "tag": f"oe-v{version}" if version else "",
        "url": release_notes_url(version),
        "name": "",
        "published_at": "",
        "summary": "",
        "available": False,
        "source": "github_release",
    }
    if not version:
        return context
    url = GITHUB_RELEASE_API_URL_TEMPLATE.format(version=version)
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        context["source"] = "github_release_unavailable"
        return context
    if not isinstance(data, dict):
        context["source"] = "github_release_unavailable"
        return context
    body = str(data.get("body") or "")
    context.update(
        {
            "url": str(data.get("html_url") or context["url"]),
            "name": str(data.get("name") or ""),
            "published_at": str(data.get("published_at") or ""),
            "summary": _release_summary(body),
            "available": True,
        }
    )
    return context


def _link_warnings(payload: dict[str, Any]) -> list[str]:
    skipped = _list_field(payload, "skipped")
    if not skipped:
        return []
    return [
        "could not refresh existing non-link skill path(s): " + ", ".join(skipped),
    ]


def _link_skills(repo: Path) -> tuple[int, list[str], list[str], dict[str, Any] | None]:
    result = _run_command(["mb", "skill", "link", "--repo", str(repo), "--json"])
    if result.returncode != 0:
        return 0, [_command_error("mb skill link", result)], [], None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return 0, ["mb skill link returned invalid JSON"], [], None
    if not isinstance(payload, dict):
        return 0, ["mb skill link returned an unexpected JSON payload"], [], None
    errors = payload.get("errors", [])
    parsed_errors = [str(error) for error in errors] if isinstance(errors, list) else []
    warnings = _link_warnings(payload)
    if payload.get("ok") is not True:
        return (
            _skill_count_from_link_result(payload),
            parsed_errors or ["mb skill link failed"],
            warnings,
            payload,
        )
    return _skill_count_from_link_result(payload), [], warnings, payload


def _repair_codex_surface(repo: Path) -> tuple[bool, list[str], list[str], dict[str, Any] | None]:
    result = _run_command(
        [
            "mb",
            "doctor",
            "repair",
            "--repo",
            str(repo),
            "--apply",
            "--only",
            "codex",
            "--json",
        ]
    )
    if result.returncode != 0:
        return False, [_command_error("mb doctor repair --only codex", result)], [], None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False, ["mb doctor repair --only codex returned invalid JSON"], [], None
    if not isinstance(payload, dict):
        return (
            False,
            ["mb doctor repair --only codex returned an unexpected JSON payload"],
            [],
            None,
        )

    raw_warnings = payload.get("warnings", [])
    warnings = [str(item) for item in raw_warnings] if isinstance(raw_warnings, list) else []
    raw_errors = payload.get("errors", [])
    errors = [str(item) for item in raw_errors] if isinstance(raw_errors, list) else []
    if payload.get("ok") is not True:
        return False, errors or ["mb doctor repair --only codex failed"], warnings, payload
    return True, [], warnings, payload


def _json_command(args: list[str], label: str) -> tuple[dict[str, Any] | None, list[str]]:
    result = _run_command(args)
    if result.returncode != 0:
        return None, [_command_error(label, result)]
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, [f"{label} returned invalid JSON"]
    if not isinstance(payload, dict):
        return None, [f"{label} returned an unexpected JSON payload"]
    if payload.get("ok") is not True:
        raw_errors = payload.get("errors", [])
        errors = [str(item) for item in raw_errors] if isinstance(raw_errors, list) else []
        return payload, errors or [f"{label} failed"]
    return payload, []


def _plan_skill_link(repo: Path) -> tuple[dict[str, Any] | None, list[str]]:
    return _json_command(
        ["mb", "skill", "link", "--repo", str(repo), "--plan", "--json"],
        "mb skill link --plan",
    )


def _plan_codex_surface(repo: Path) -> tuple[dict[str, Any] | None, list[str]]:
    return _json_command(
        ["mb", "doctor", "repair", "--repo", str(repo), "--plan", "--only", "codex", "--json"],
        "mb doctor repair --plan --only codex",
    )


CODEX_SURFACE_ACTION_IDS = ("codex-agents-md", "codex-global-skill")
CHANGE_LABELS = {
    "delete": "delete",
    "delete_tree": "delete",
    "replace_link": "replace link",
    "create_link": "new link",
    "create": "create",
}


def _changes_from(items: Any) -> list[dict[str, str]] | None:
    if not isinstance(items, list):
        return None
    return [
        {"path": str(item.get("path") or ""), "op": str(item.get("op") or "")}
        for item in items
        if isinstance(item, dict)
    ]


def _codex_tracked_changes(plan: dict[str, Any]) -> list[dict[str, str]] | None:
    """Tracked files the planned Codex repair would change, or None if unknown.

    `mb doctor repair --plan` resolves every destination (AGENTS.md, the
    transitional repo files it removes, each global skill file) through
    symlinks and asks git whether it is tracked (#1012).
    """
    changes: list[dict[str, str]] = []
    for action in plan.get("actions", []):
        if not isinstance(action, dict) or action.get("id") not in CODEX_SURFACE_ACTION_IDS:
            continue
        found = _changes_from(action.get("tracked_changes"))
        if found is None:
            return None
        changes.extend(found)
    return changes


def _new_repo_files(
    operations: list[Any], repo: Path, known: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Planned writes that would create a file in the business repo.

    `tracked_changes` names only files git already tracks, so a missing file
    is not in it. A new file still shows in `git status`, so it needs the same
    yes as a tracked write. An untracked link counts too, dangling or not
    (#1072): the apply replaces the link itself (`replace_link`), so the
    inside-repo check resolves the parent folder, never the link.
    """
    repo_real = os.path.realpath(repo)
    seen = {item["path"] for item in known}
    found: list[dict[str, str]] = []
    for operation in operations:
        if not isinstance(operation, dict) or operation.get("op") != "write":
            continue
        path = str(operation.get("path") or "")
        # #1072: a link the person made is held like a tracked file, whether
        # or not it points anywhere; only a regular file is refreshed freely.
        if not path or (os.path.exists(path) and not os.path.islink(path)):
            continue
        real = os.path.join(os.path.realpath(os.path.dirname(path)), os.path.basename(path))
        if not real.startswith(repo_real + os.sep):
            continue
        rel = os.path.relpath(real, repo_real).replace(os.sep, "/")
        if rel not in seen:
            seen.add(rel)
            op = "replace_link" if os.path.islink(path) else "create"
            found.append({"path": rel, "op": op})
    return found


def _codex_new_repo_files(
    plan: dict[str, Any], repo: Path, known: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Files the Codex AGENTS.md repair would create in the business repo (#1053)."""
    operations = [
        operation
        for action in plan.get("actions", [])
        if isinstance(action, dict) and action.get("id") == "codex-agents-md"
        for operation in action.get("operations") or []
    ]
    return _new_repo_files(operations, repo, known)


def _link_new_repo_files(
    plan: dict[str, Any], repo: Path, known: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Files the skill link would create in the business repo (#1087 item 10).

    A missing `.gitignore` is created by the link, so it needs a yes like a
    new AGENTS.md. Everything else the link creates (the skill links,
    `.claude/settings.local.json`) is one of the lines that `.gitignore` holds.
    """
    found = _new_repo_files(list(plan.get("operations") or []), repo, known)
    return [item for item in found if item["path"] == ".gitignore"]


def _surface_consent(
    link_plan: dict[str, Any],
    codex_plan: dict[str, Any],
    repo: Path,
    claude_content: str | None = None,
) -> dict[str, Any] | None:
    """The repo files the surface refresh would change, or None if unknown.

    Shared by the run and `--check` (#1100), so the check names the same
    files, and the same consent stop, that an unattended run hits.
    """
    link_changes = _changes_from(link_plan.get("tracked_changes"))
    codex_changes = _codex_tracked_changes(codex_plan)
    if link_changes is None or codex_changes is None:
        return None
    # #1087 item 10: creating a missing .gitignore needs the same yes.
    link_changes.extend(_link_new_repo_files(link_plan, repo, link_changes))
    # #1052: a Codex AGENTS.md repair that would refuse, or leave a person's
    # files behind, needs a manual step first. No consent prompt, no write.
    codex_blocked = _codex_blocked_actions(codex_plan)
    if codex_blocked:
        codex_changes = []
    else:
        # #1053: creating a missing AGENTS.md needs the same yes.
        codex_changes.extend(_codex_new_repo_files(codex_plan, repo, codex_changes))
    link_writes = list(dict.fromkeys(item["path"] for item in link_changes))
    codex_writes = list(dict.fromkeys(item["path"] for item in codex_changes))
    claude_changes = [{"path": "CLAUDE.md", "op": "modify"}] if claude_content is not None else []
    return {
        "codex_blocked": codex_blocked,
        "link_writes": link_writes,
        "codex_writes": codex_writes,
        "claude_writes": ["CLAUDE.md"] if claude_changes else [],
        "tracked_changes": list(
            {
                (c["path"], c["op"]): c for c in [*link_changes, *codex_changes, *claude_changes]
            }.values()
        ),
        "tracked_files": list(
            dict.fromkeys([*link_writes, *codex_writes, *[c["path"] for c in claude_changes]])
        ),
    }


def _check_codex_plan(repo: Path, codex: dict[str, Any]) -> dict[str, Any]:
    """The Codex part of `mb doctor repair --plan --only codex`, read-only.

    Built by doctor's own `codex_repair_actions` (#1106), so the two cannot
    drift, without doctor's network and version checks. `codex` is the
    readiness `--check` already read, so it is read once.
    """
    if _not_business_folder_guard(repo) is not None:
        # Doctor plans nothing outside a business folder.
        return {"actions": [], "operator_actions": []}
    actions, operator_actions = codex_repair_actions(repo, codex)
    return {"actions": actions, "operator_actions": operator_actions}


def _unreadable_plan_warning(repo: Path, part: str, exc: BaseException) -> str:
    path, reason, fix = unreadable_mod.describe(exc, repo)
    return CHECK_PLAN_UNREADABLE_MESSAGE.format(
        target=f"`{path}`" if path else "a file it needs",
        part=part,
        error=reason,
        fix=fix,
    )


def _guard_unreadable(
    result: dict[str, Any], repo: Path, part: str, read: Callable[[], Any], *, check: bool
) -> bool:
    """Run one read step; a file it cannot read is named instead of a traceback (#1106).

    `--check` names it in a warning, as for the skill-link plan (#1101); a run
    names it in `errors`, once, and fails. False when the step could not read.
    """
    try:
        read()
    except (OSError, ValueError, RuntimeError) as exc:
        if not unreadable_mod.is_unreadable_error(exc):
            raise
        if check:
            # One warning per path: two steps that trip on the same folder
            # name it once.
            path = unreadable_mod.describe(exc, repo)[0]
            named = f"Could not read `{path}` ("
            if not path or not any(str(item).startswith(named) for item in result["warnings"]):
                result["warnings"].append(_unreadable_plan_warning(repo, part, exc))
        else:
            note = unreadable_mod.message(exc, repo)
            result["ok"] = False
            if note not in result["errors"]:
                result["errors"].append(note)
        return False
    return True


def _predict_surface_consent(result: dict[str, Any], repo: Path, codex: dict[str, Any]) -> None:
    """`--check`: report the consent stop an unattended run would hit (#1100).

    Read-only: the same plans the run makes, in this process, with this
    install's templates. Only a repo whose refresh would change repo files
    gains the planned fields, so every other check result stays as it was. A
    plan that cannot be made predicts nothing; a file it cannot read (not
    UTF-8, no permission, a folder, a looping link) is named in a warning,
    because the run stops with an error at the same place.
    """
    # RuntimeError: pathlib's symlink loop on Python 3.10 to 3.12; any other
    # RuntimeError is a programming error and stays loud (#1106 item 4).
    try:
        link_plan = plan_link_skills(repo)
    except (OSError, ValueError, RuntimeError) as exc:
        if isinstance(exc, RuntimeError) and not unreadable_mod.is_unreadable_error(exc):
            raise
        result["warnings"].append(_unreadable_plan_warning(repo, "skill link", exc))
        return
    if link_plan.get("ok") is not True:
        return
    try:
        codex_plan = _check_codex_plan(repo, codex)
    except (OSError, ValueError, RuntimeError) as exc:
        if isinstance(exc, RuntimeError) and not unreadable_mod.is_unreadable_error(exc):
            raise
        result["warnings"].append(_unreadable_plan_warning(repo, "Codex guidance", exc))
        return
    try:
        claude_content, claude_refusal = claude_guidance.plan(repo)
    except (OSError, UnicodeError, ValueError) as exc:
        result["warnings"].append(_unreadable_plan_warning(repo, "Claude guidance", exc))
        return
    if claude_refusal:
        result["warnings"].append(claude_refusal)
    consent = _surface_consent(link_plan, codex_plan, repo, claude_content)
    if consent is None or not consent["tracked_files"]:
        return
    planned = result["surface_refresh"]["planned"]
    planned["consent"] = "no_terminal"
    planned["tracked_files"] = consent["tracked_files"]
    planned["tracked_changes"] = consent["tracked_changes"]
    if consent["link_writes"]:
        planned["apply_commands"].append(f"mb skill link{_repo_flag(repo)}")
    if consent["codex_writes"]:
        planned["apply_commands"].append(f"mb doctor repair{_repo_flag(repo)} --apply --only codex")
    if consent["claude_writes"]:
        planned["apply_commands"].append(_update_command(repo))
        result["operator_actions"].append(
            operator_action(
                _update_command(repo),
                consent["claude_writes"],
                "Run interactively and approve the CLAUDE.md entry guidance refresh.",
            )
        )


def _codex_blocked_actions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """The plan's Codex AGENTS.md steps that need a person first (#1052)."""

    return [
        item
        for item in plan.get("operator_actions", [])
        if isinstance(item, dict) and item.get("id") == "codex-agents-md"
    ]


def _change_label(change: dict[str, str]) -> str:
    label = CHANGE_LABELS.get(change["op"])
    return f"{change['path']} ({label})" if label else change["path"]


def _tracked_snapshot(repo: Path) -> dict[str, str] | None:
    """Status and content hash of every changed tracked file, or None outside git."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain=v1", "-z", "--untracked-files=no"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    fields = proc.stdout.split("\0")
    snapshot: dict[str, str] = {}
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        if status[0] in "RC":
            index += 1  # the original path of a rename or copy
        snapshot[path] = f"{status}:{_content_hash(repo / path)}"
    return snapshot


def _content_hash(path: Path) -> str:
    try:
        if path.is_symlink():
            return "link:" + os.readlink(path)
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "-"


def _unapproved_tracked_changes(
    before: dict[str, str], after: dict[str, str], allowed: list[str]
) -> list[str]:
    changed = sorted(path for path in {*before, *after} if before.get(path) != after.get(path))
    prefixes = [item.rstrip("/") for item in allowed]
    return [
        path
        for path in changed
        if not any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes)
    ]


def _repo_flag(repo: Path) -> str:
    """` --repo <path>` for a command the operator may paste (#1072)."""
    return repo_flag(repo)


def _update_command(repo: Path | str, *, check: bool = False) -> str:
    """The `mb update` command that acts on this business repo from any folder."""
    return f"mb update{repo_flag(Path(repo))}{' --check' if check else ''}"


def _status_command(repo: Path | str) -> str:
    """The read-only status command for this repo; `mb status` takes the path."""
    target = Path(repo).resolve()
    flag = repo_flag(target)
    path = f" {shlex.quote(str(target))}" if flag else ""
    return f"mb status --json --peek{path}"


def _base_result(
    repo: Path,
    *,
    check: bool,
    mode: str,
    root: Path | None,
    refresh_surfaces: bool,
) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": mode,
        "check": check,
        "refresh_surfaces": refresh_surfaces,
        "repo": str(repo),
        "engine_root": str(root) if root is not None else None,
        "old_version": _engine_version(root),
        "new_version": None,
        "latest_version": "",
        "installed_ahead_of_latest": False,
        "latest_version_unknown": False,
        "upgrade_performed": False,
        "manual_update_command": "",
        "skills_relinked_count": 0,
        "planned_skills_relink_count": 0,
        "codex_repaired": False,
        "codex_repair_result": {},
        "release": {},
        "actions": [],
        "warnings": [],
        "errors": [],
        "next_actions": [],
        "operator_actions": [],
        "codex_adapter": {},
        "surface_refresh": {
            "enabled": refresh_surfaces,
            "claude": {},
            "codex": {},
            "commands": [],
            "skipped": [] if refresh_surfaces else ["claude", "codex"],
            "planned": {
                "consent": "not_needed",
                "tracked_files": [],
                "apply_commands": [],
            },
        },
    }


def _add_codex_follow_up(
    result: dict[str, Any], repo: Path, codex: dict[str, Any] | None = None
) -> None:
    if codex is None:
        codex = codex_mod.readiness(repo)
    instructions = codex.get("instructions", {})
    global_skill = codex.get("global_skill", {})
    plugin_install = codex.get("plugin_install", {})
    result["codex_adapter"] = {
        "ok": codex["ok"],
        "status": codex.get("status", ""),
        "static_ok": codex.get("static_ok", False),
        "runtime_ok": codex.get("runtime_ok", False),
        "global_skill_ok": codex.get("global_skill_ok", False),
        "plugin_ok": codex.get("plugin_ok", False),
        "command_surface_ok": codex.get("command_surface_ok", False),
        "slash_commands_ready": codex.get("slash_commands_ready", False),
        "global_skill": global_skill,
        "slash_commands_likely_loaded": plugin_install.get("slash_commands_likely_loaded", False),
        "slash_commands_restart_required": plugin_install.get(
            "slash_commands_restart_required", False
        ),
        "exists": instructions.get("exists", False),
        "current": instructions.get("current", False),
        "repair_command": codex.get("repair", "") or instructions.get("repair_command", ""),
        "plugin_install": plugin_install,
    }
    if not codex["ok"]:
        # #1053: the same `--repo` form the surface refresh emits, so the two
        # follow-ups collapse to one plan command and every entry names the repo.
        plan_command = f"mb doctor repair{_repo_flag(repo)} --plan --only codex"
        apply_command = f"mb doctor repair{_repo_flag(repo)} --apply --only codex"
        next_actions: list[str]
        if not instructions.get("ok", False):
            message = (
                "Codex AGENTS.md guidance still needs repo repair. Run "
                f"`{plan_command}`, review it, then approve `{apply_command}`."
            )
            next_actions = [plan_command]
            # #1049: the apply rewrites the tracked AGENTS.md, so it is a step
            # for a person; the surface refresh may already have listed it.
            if not any(
                "--apply --only codex" in str(item.get("command", ""))
                for item in result["operator_actions"]
            ):
                agents_plan = codex_mod.agents_md_plan(repo)
                # #1052: a repair that needs a manual step first says which.
                blocked = codex_mod.agents_md_operator_action(agents_plan, repo=repo)
                changes = [str(op["rel"]) for op in agents_plan["operations"]]
                if blocked:
                    blocked["command"] = apply_command
                result["operator_actions"].append(
                    blocked
                    or operator_action(
                        apply_command,
                        changes or ["AGENTS.md"],
                        SURFACE_CODEX_APPLY_NOTE,
                    )
                )
        elif not codex.get("global_skill_ok", False):
            message = (
                "The global Main Branch Codex skills are not ready, so `mb-*` "
                "routes may be missing or stale. "
                f"Run `{plan_command}`, review it, then approve `{apply_command}`."
            )
            next_actions = [plan_command, apply_command]
            if global_skill.get("kept") and not codex_mod.global_skill_operations():
                # Only the manual kept-files step can help; an apply would do nothing.
                message = ""
                next_actions = []
        else:
            message = (
                "Codex runtime readiness still needs attention. Run "
                f"`{_status_command(repo)}` and repair the reported runtime issue."
            )
            next_actions = [_status_command(repo)]
        if message:
            result["warnings"].append(message)
        result["next_actions"].extend(next_actions)
    elif plugin_install.get("slash_commands_restart_required"):
        result["warnings"].append(
            "Codex may need a fresh thread before it sees the refreshed global "
            "Main Branch skill bundle."
        )
        result["next_actions"].append("Open a fresh Codex thread in the business repo.")
    # #1067: files doctor keeps in global Codex folders are reported here too,
    # last, so the AGENTS.md entries above stay exactly as they were. Listed
    # first, its apply command would satisfy the guard above and hide them.
    # Same shape as the blocked AGENTS.md repair: `mb update` alone tells
    # the operator. Nothing is deleted on their account.
    kept_action = codex_mod.global_skill_operator_action(global_skill, repo=repo)
    if kept_action is not None and not any(
        item.get("id") == "codex-global-kept" for item in result["operator_actions"]
    ):
        result["warnings"].append(str(kept_action.get("note") or ""))
        result["operator_actions"].append(kept_action)


def _add_plugin_follow_up(result: dict[str, Any], repo: Path) -> None:
    """Surface plugin-rail migration guidance for symlink-era repos (#931).

    `mb update` refreshes the symlink wiring but does not write the tracked
    plugin wiring, so a repo created before the plugin default stays on
    symlinks even though the plugin is the default cross-surface rail. Name the
    one-command migration as post-update guidance — never an automatic write.
    """
    status = plugin_wiring_status(repo)
    expected_version = str(result.get("new_version") or result.get("old_version") or __version__)
    install = claude_mainbranch_plugin_status(expected_version=expected_version)
    result["plugin_rail"] = {
        "wired": status.get("wired", False),
        "marketplace_known": status.get("marketplace_known", False),
        "plugin_enabled": status.get("plugin_enabled", False),
        "settings_path": status.get("settings_path", ""),
        "install": install,
    }
    if not status.get("wired", False):
        result["warnings"].append(
            "This repo is on symlink-only skill wiring. The Main Branch plugin is "
            "the default cross-surface rail (Claude Desktop and the terminal, and "
            "it survives git worktrees). The switch writes a tracked file, so it "
            "is listed under `operator_actions` for a person to run at a terminal."
        )
        # #1023: the switch writes tracked `.claude/settings.json`, so it is a
        # step for a person at a terminal, never an unattended next action.
        result["operator_actions"].append(plugin_switch_operator_action(repo))

    install_state = str(install.get("state") or "")
    if install_state in {"stale", "installed_not_enabled", "disabled", "not_installed"}:
        expected = str(install.get("expected_version") or expected_version)
        installed = str(install.get("installed_version") or "")
        if install_state == "stale":
            message = (
                "Claude Code is still loading an older Main Branch plugin "
                f"({installed or 'unknown'}), while this package expects {expected}. "
                "Update/reinstall the plugin, then restart Claude Code or run "
                "`/reload-plugins` before relying on slash-skill changes."
            )
        elif install_state == "installed_not_enabled":
            message = (
                f"Main Branch plugin {expected} is installed in Claude Code but not enabled. "
                "Enable it, then restart Claude Code or run `/reload-plugins`."
            )
        elif install_state == "disabled":
            message = (
                "The Main Branch Claude Code plugin is installed but disabled. Enable it, "
                "then restart Claude Code or run `/reload-plugins`."
            )
        else:
            message = (
                "The Main Branch Claude Code plugin is not installed. Install it so Claude "
                "Desktop and the terminal load the updated slash skills."
            )
        result["warnings"].append(message)
        result["next_actions"].append(PLUGIN_INSTALL_COMMAND)


def _refresh_surfaces(
    result: dict[str, Any],
    target_repo: Path,
    *,
    wants_prompt: bool,
    confirm: Callable[[Path, list[str]], bool],
) -> None:
    """Refresh Claude links and Codex guidance; tracked-file writes need a yes.

    Each surface is planned first. A surface whose plan changes no tracked repo
    file (gitignored skill links, the global Codex skill bundle) refreshes as
    before. A surface that would change one (`.gitignore`, `AGENTS.md`) is
    applied only after one yes at an interactive prompt; otherwise its plan and
    apply command are reported and the repo is left as it was (#1012).
    """
    surface = result["surface_refresh"]
    planned = surface["planned"]

    link_plan, link_plan_errors = _plan_skill_link(target_repo)
    result["actions"].append(f"ran `mb skill link --repo {target_repo} --plan --json`")
    if link_plan_errors:
        result["ok"] = False
        result["errors"].extend(link_plan_errors)
        return
    codex_plan, codex_plan_errors = _plan_codex_surface(target_repo)
    result["actions"].append(
        f"ran `mb doctor repair --repo {target_repo} --plan --only codex --json`"
    )
    if codex_plan_errors:
        result["ok"] = False
        result["errors"].extend(codex_plan_errors)
        return
    link_plan = link_plan or {}
    codex_plan = codex_plan or {}

    try:
        claude_content, claude_refusal = claude_guidance.plan(target_repo)
    except (OSError, UnicodeError, ValueError) as exc:
        result["ok"] = False
        result["errors"].append(f"Could not read CLAUDE.md for guidance refresh: {exc}")
        return
    if claude_refusal:
        result["warnings"].append(claude_refusal)
    consent = _surface_consent(link_plan, codex_plan, target_repo, claude_content)
    if consent is None:
        result["ok"] = False
        result["errors"].append(
            "the installed `mb` did not report which tracked files the surface refresh "
            "would change, so nothing was refreshed. Upgrade Main Branch, then run "
            f"`{_update_command(target_repo)}` again."
        )
        return
    codex_blocked = consent["codex_blocked"]
    link_writes = consent["link_writes"]
    codex_writes = consent["codex_writes"]
    claude_writes = consent["claude_writes"]
    tracked_changes = consent["tracked_changes"]
    tracked_files = consent["tracked_files"]
    planned["tracked_files"] = tracked_files
    planned["tracked_changes"] = tracked_changes

    approved = False
    if tracked_files:
        if wants_prompt:
            approved = confirm(target_repo, [_change_label(item) for item in tracked_changes])
            planned["consent"] = "approved" if approved else "declined"
        else:
            planned["consent"] = "no_terminal"
    apply_link = approved or not link_writes
    apply_codex = (approved or not codex_writes) and not codex_blocked

    link_apply_command = f"mb skill link{_repo_flag(target_repo)}"
    codex_apply_command = f"mb doctor repair{_repo_flag(target_repo)} --apply --only codex"

    before = _tracked_snapshot(target_repo) if (apply_link or apply_codex or approved) else None

    if not apply_link:
        surface["claude"] = {
            "ok": True,
            "applied": False,
            "skill_count": 0,
            "tracked_writes": link_writes,
            "command": link_apply_command,
            "plan": link_plan,
        }
        planned["apply_commands"].append(link_apply_command)
    else:
        linked_count, link_errors, link_warnings, link_payload = _link_skills(target_repo)
        claude_command = f"mb skill link --repo {shlex.quote(str(target_repo))} --json"
        result["actions"].append(f"ran `{claude_command}`")
        surface["commands"].append(claude_command)
        surface["claude"] = {
            "ok": not link_errors,
            "applied": True,
            "skill_count": linked_count,
            "command": claude_command,
            "result": link_payload or {},
        }
        result["skills_relinked_count"] = linked_count
        result["warnings"].extend(link_warnings)
        if link_errors:
            result["ok"] = False
            result["errors"].extend(link_errors)
            return

    if codex_blocked:
        surface["codex"] = {
            "ok": True,
            "applied": False,
            "blocked": True,
            "reason": " ".join(str(item.get("reason") or "") for item in codex_blocked),
            "tracked_writes": [],
            "command": codex_apply_command,
        }
        result["warnings"].extend(str(item.get("note") or "") for item in codex_blocked)
        result["next_actions"].append(
            f"mb doctor repair{_repo_flag(target_repo)} --plan --only codex"
        )
        for item in codex_blocked:
            entry = operator_action(
                codex_apply_command,
                [str(path) for path in item.get("changes", [])],
                str(item.get("note") or ""),
            )
            for key in ("id", "reason", "manual_step", "on_apply"):
                if key in item:
                    entry[key] = item[key]
            result["operator_actions"].append(entry)
    elif not apply_codex:
        surface["codex"] = {
            "ok": True,
            "applied": False,
            "tracked_writes": codex_writes,
            "command": codex_apply_command,
            "plan": {
                "actions": [
                    {
                        "id": str(action.get("id") or ""),
                        "title": str(action.get("title") or ""),
                        "writes": [str(path) for path in action.get("writes", [])],
                    }
                    for action in codex_plan.get("actions", [])
                    if isinstance(action, dict)
                ],
            },
        }
        planned["apply_commands"].append(codex_apply_command)
    else:
        codex_ok, codex_errors, codex_warnings, codex_payload = _repair_codex_surface(target_repo)
        codex_command = (
            f"mb doctor repair --repo {shlex.quote(str(target_repo))} --apply --only codex --json"
        )
        result["actions"].append(f"ran `{codex_command}`")
        surface["commands"].append(codex_command)
        surface["codex"] = {
            "ok": codex_ok,
            "applied": True,
            "command": codex_command,
            "result": codex_payload or {},
        }
        result["codex_repaired"] = codex_ok
        if codex_payload is not None:
            result["codex_repair_result"] = codex_payload
        result["warnings"].extend(codex_warnings)
        if codex_errors:
            result["ok"] = False
            result["errors"].extend(codex_errors)

    if claude_content is not None and approved:
        claude_guidance.apply(target_repo, claude_content)
        surface["claude_guidance"] = {"applied": True, "tracked_writes": claude_writes}
    elif claude_writes:
        surface["claude_guidance"] = {"applied": False, "tracked_writes": claude_writes}
        planned["apply_commands"].append(_update_command(target_repo))

    if before is not None:
        after = _tracked_snapshot(target_repo)
        unapproved = (
            _unapproved_tracked_changes(before, after, tracked_files if approved else [])
            if after is not None
            else []
        )
        if unapproved:
            result["ok"] = False
            result["errors"].append(
                "mb update changed tracked file(s) that were not approved: "
                + ", ".join(unapproved)
                + ". Nothing was reverted; review them with `git status` and `git diff`."
            )
            planned["unapproved_changes"] = unapproved

    if planned["apply_commands"]:
        template = (
            SURFACE_PLAN_DECLINED_MESSAGE
            if planned["consent"] == "declined"
            else SURFACE_PLAN_NO_TERMINAL_MESSAGE
        )
        result["warnings"].append(template.format(files=", ".join(tracked_files)))
        if not apply_codex and not codex_blocked:
            # Review before apply: the plan names every file the repair writes.
            result["next_actions"].append(
                f"mb doctor repair{_repo_flag(target_repo)} --plan --only codex"
            )
        # #1049: each apply command writes tracked files `mb update` declined
        # to change without a person, so it is a step for a person, not an
        # unattended next action. `apply_commands` keeps them for readers.
        if not apply_link:
            result["operator_actions"].append(
                operator_action(link_apply_command, link_writes, SURFACE_LINK_APPLY_NOTE)
            )
        if not apply_codex and not codex_blocked:
            result["operator_actions"].append(
                operator_action(codex_apply_command, codex_writes, SURFACE_CODEX_APPLY_NOTE)
            )
        if claude_writes and not approved:
            result["operator_actions"].append(
                operator_action(
                    _update_command(target_repo),
                    claude_writes,
                    "Run interactively and approve the CLAUDE.md entry guidance refresh.",
                )
            )


def run(
    repo: str | Path = ".",
    *,
    check: bool = False,
    refresh_surfaces: bool = True,
    interactive: bool | None = None,
    confirm: Callable[[str, Path | None], bool] | None = None,
    confirm_surfaces: Callable[[Path, list[str]], bool] | None = None,
) -> dict[str, Any]:
    """Update the active Main Branch install and refresh business-repo skills.

    `pipx` and `clone` installs upgrade automatically. A `uv` tool install
    upgrades only after an explicit yes at an interactive prompt; every other
    path prints the working command instead of refusing (#963).

    The surface refresh changes tracked files in the business repo (`AGENTS.md`,
    `.gitignore`) only after one explicit yes at an interactive prompt. Without
    one, it plans those changes into `surface_refresh.planned` and lists the
    apply commands in `operator_actions` for a person (#1012, #1049).
    """
    target_repo = Path(repo).resolve()
    wants_prompt = _is_interactive_terminal() if interactive is None else interactive
    mode = _resolve_install_mode()
    root = engine_root()
    result = _base_result(
        target_repo,
        check=check,
        mode=mode,
        root=root,
        refresh_surfaces=refresh_surfaces,
    )

    if mode not in {"pipx", "clone", "uv", "wheel"}:
        result["ok"] = False
        result["new_version"] = result["old_version"]
        result["errors"].append(
            f"unsupported install mode: {mode}. Expected a pipx install, a uv tool "
            "install, another wheel install, or a git clone."
        )
        return result

    # One PyPI lookup per run for the package modes. None means freshness is
    # unknown: nothing installs and no install command is handed out.
    latest = _checked_latest_version() if mode in {"pipx", "uv", "wheel"} else None

    uv_command = uv_update_command_text(latest)

    if check:
        if mode in {"pipx", "uv", "wheel"} and latest is None:
            result["actions"] = [
                "would leave this install alone; PyPI's latest version could not be checked",
            ]
            _note_latest_unknown(result, retry=_update_command(target_repo, check=True))
        elif mode in {"uv", "wheel"} and _note_already_current(result, latest):
            result["actions"] = [
                "would leave this install alone; it already runs PyPI's latest release",
            ]
        elif mode == "uv":
            result["actions"] = [
                f"would run `{uv_command}` after an explicit yes",
            ]
            _note_manual_update(
                result,
                command=uv_command,
                message=UV_MANUAL_MESSAGE,
                latest=latest,
            )
        elif mode == "wheel":
            result["actions"] = [
                f"would leave this install alone; `{PIP_UPDATE_COMMAND_TEXT}` is yours to run",
            ]
            _note_manual_update(
                result,
                command=PIP_UPDATE_COMMAND_TEXT,
                message=WHEEL_MANUAL_MESSAGE,
                latest=latest,
            )
        elif mode == "pipx":
            if not _note_ahead_of_pypi(result, latest):
                result["new_version"] = latest or result["old_version"]
                result["actions"] = [
                    f"would run `{PIPX_UPDATE_COMMAND_TEXT}`",
                ]
        else:
            if root is None:
                result["ok"] = False
                result["errors"].append("could not locate Main Branch engine root")
                result["new_version"] = result["old_version"]
                return result
            fetched, fetch_error = _fetch_origin_main(root)
            result["actions"].append(f"ran `git fetch origin main --quiet` in {root}")
            if not fetched:
                result["ok"] = False
                result["errors"].append(fetch_error or "git fetch origin main failed")
                result["new_version"] = result["old_version"]
                return result
            result["new_version"] = (
                _version_from_git_ref(root, "origin/main") or result["old_version"]
            )
            result["actions"].extend(
                [
                    f"would run `git pull --ff-only origin main` in {root}",
                ]
            )
        if result["installed_ahead_of_latest"]:
            result["actions"] = ["would leave this install alone; it is newer than PyPI's latest"]
        codex_status: dict[str, Any] | None = None
        codex_readable = True
        if refresh_surfaces:
            surface_commands = [
                f"mb skill link --repo {shlex.quote(str(target_repo))} --json",
                f"mb doctor repair --repo {shlex.quote(str(target_repo))} "
                "--apply --only codex --json",
            ]
            result["surface_refresh"]["commands"] = surface_commands
            result["actions"].extend(f"would run `{command}`" for command in surface_commands)
            result["actions"].append(
                "would ask once before changing tracked files (AGENTS.md, .gitignore); "
                "without a terminal, would report the plan and leave them unchanged"
            )
            planned_count = len(bundled_skills())
            result["skills_relinked_count"] = planned_count
            result["planned_skills_relink_count"] = planned_count
            result["surface_refresh"]["claude"] = {
                "planned": True,
                "skill_count": planned_count,
                "command": surface_commands[0],
            }
            result["surface_refresh"]["codex"] = {
                "planned": True,
                "command": surface_commands[1],
            }
            status: dict[str, Any] = {}
            codex_readable = _guard_unreadable(
                result,
                target_repo,
                "Codex guidance",
                lambda: status.update(codex_mod.readiness(target_repo)),
                check=True,
            )
            if codex_readable:
                codex_status = status
                _predict_surface_consent(result, target_repo, codex_status)
        else:
            result["actions"].append("would skip agent surface refresh")
        new_version = str(result.get("new_version") or "")
        old_version = str(result.get("old_version") or "")
        if new_version and old_version and compare_versions(new_version, old_version) > 0:
            result["release"] = _release_context(new_version)
        elif new_version:
            result["release"] = {
                "version": new_version,
                "tag": f"oe-v{new_version}",
                "url": release_notes_url(new_version),
                "name": "",
                "published_at": "",
                "summary": "",
                "available": False,
                "source": "not_newer",
            }
        if codex_readable:
            _guard_unreadable(
                result,
                target_repo,
                "Codex guidance",
                lambda: _add_codex_follow_up(result, target_repo, codex_status),
                check=True,
            )
        _guard_unreadable(
            result,
            target_repo,
            "Claude Code plugin",
            lambda: _add_plugin_follow_up(result, target_repo),
            check=True,
        )
        return result

    if mode in {"pipx", "uv", "wheel"} and latest is None:
        result["actions"].append(
            "left this install alone; PyPI's latest version could not be checked"
        )
        _note_latest_unknown(result, retry=_update_command(target_repo))
    elif mode in {"pipx", "uv"} and _note_ahead_of_pypi(result, latest):
        result["actions"].append("left this install alone; it is newer than PyPI's latest")
    elif mode in {"uv", "wheel"} and _note_already_current(result, latest):
        result["actions"].append("left this install alone; it already runs PyPI's latest release")
    elif mode == "pipx":
        if shutil.which("pipx") is None:
            result["ok"] = False
            result["new_version"] = result["old_version"]
            result["errors"].append("pipx install mode detected, but `pipx` is not on PATH")
            return result
        upgrade = _run_command(["pipx", "upgrade", "mainbranch"])
        result["actions"].append("ran `pipx upgrade mainbranch`")
        if upgrade.returncode != 0:
            result["ok"] = False
            result["new_version"] = result["old_version"]
            result["errors"].append(_command_error("pipx upgrade mainbranch", upgrade))
            _add_pipx_package_spec_recovery(result, upgrade, latest)
            return result
        result["new_version"] = _version_from_mb_command() or result["old_version"]
        result["upgrade_performed"] = True
    elif mode == "uv":
        if shutil.which("uv") is None:
            result["ok"] = False
            result["new_version"] = result["old_version"]
            result["errors"].append("uv install mode detected, but `uv` is not on PATH")
            result["next_actions"].append(uv_command)
            return result
        approved = False
        if wants_prompt:
            approved = (confirm or _confirm_uv_update)(uv_command, root)
            if not approved:
                result["actions"].append(f"declined `{uv_command}`")
        if not approved:
            _note_manual_update(
                result,
                command=uv_command,
                message=UV_DECLINED_MESSAGE if wants_prompt else UV_MANUAL_MESSAGE,
                latest=latest,
            )
        else:
            upgrade = _run_command(_uv_update_command(latest))
            result["actions"].append(f"ran `{uv_command}`")
            if upgrade.returncode != 0:
                result["ok"] = False
                result["new_version"] = result["old_version"]
                if _uv_release_not_ready(upgrade, latest):
                    result["errors"].append(UV_RELEASE_NOT_READY_MESSAGE.format(version=latest))
                else:
                    result["errors"].append(_command_error(uv_command, upgrade))
                    result["next_actions"].append(uv_command)
                return result
            result["new_version"] = _version_from_mb_command() or result["old_version"]
            result["upgrade_performed"] = True
    elif mode == "wheel":
        _note_manual_update(
            result,
            command=PIP_UPDATE_COMMAND_TEXT,
            message=WHEEL_MANUAL_MESSAGE,
            latest=latest,
        )
    else:
        if root is None:
            result["ok"] = False
            result["new_version"] = result["old_version"]
            result["errors"].append("could not locate Main Branch engine root")
            return result
        pull = _run_command(CLONE_UPDATE_COMMAND, cwd=root)
        result["actions"].append(f"ran `git pull --ff-only origin main` in {root}")
        if pull.returncode != 0:
            result["ok"] = False
            result["new_version"] = result["old_version"]
            result["errors"].append(_command_error("git pull", pull))
            return result
        result["new_version"] = _engine_version(root)
        result["upgrade_performed"] = True

    if refresh_surfaces:
        _refresh_surfaces(
            result,
            target_repo,
            wants_prompt=wants_prompt,
            confirm=confirm_surfaces or _confirm_surface_writes,
        )
    else:
        result["actions"].append("skipped agent surface refresh")
    _guard_unreadable(
        result,
        target_repo,
        "Codex guidance",
        lambda: _add_codex_follow_up(result, target_repo),
        check=False,
    )
    _guard_unreadable(
        result,
        target_repo,
        "Claude Code plugin",
        lambda: _add_plugin_follow_up(result, target_repo),
        check=False,
    )
    result["next_actions"] = list(dict.fromkeys(result["next_actions"]))
    return result


def _render_surface_plan(result: dict[str, Any]) -> None:
    surface = result.get("surface_refresh")
    planned = surface.get("planned") if isinstance(surface, dict) else None
    if not isinstance(planned, dict) or not planned.get("apply_commands"):
        return
    files = ", ".join(str(path) for path in planned.get("tracked_files", []))
    print(f"left repo files unchanged: {files}")


def _render_predicted_consent(result: dict[str, Any]) -> None:
    surface = result.get("surface_refresh")
    planned = surface.get("planned") if isinstance(surface, dict) else None
    if not isinstance(planned, dict) or planned.get("consent") != "no_terminal":
        return
    changes = planned.get("tracked_changes") or []
    labels = [
        _change_label(item)
        for item in changes
        if isinstance(item, dict) and "path" in item and "op" in item
    ]
    files = ", ".join(labels or [str(path) for path in planned.get("tracked_files", [])])
    print(f"would ask once before changing repo files: {files}")
    print("without a terminal, would leave them unchanged and list the commands for you:")
    for command in planned.get("apply_commands", []):
        print(f"  {command}")


def _render_operator_actions(result: dict[str, Any]) -> None:
    for item in result.get("operator_actions", []):
        if isinstance(item, dict) and item.get("command"):
            print(f"for you to run: {item['command']}")
            if item.get("note"):
                print(f"  {item['note']}")


def render_human(result: dict[str, Any]) -> None:
    """Print a concise human-readable update result."""
    old = result.get("old_version") or "unknown"
    new = result.get("new_version") or "unknown"
    mode = result.get("mode") or "unknown"
    count = result.get("skills_relinked_count", 0)
    refresh_surfaces = result.get("refresh_surfaces", True)

    ahead = result.get("installed_ahead_of_latest") is True
    latest = result.get("latest_version") or "unknown"
    latest_unknown = result.get("latest_version_unknown") is True
    # uv and wheel installs that already run PyPI's latest carry no install
    # command (#1036); pipx and clone checks keep their "would run" line.
    already_current = (
        mode in {"uv", "wheel"}
        and not ahead
        and not latest_unknown
        and not result.get("manual_update_command")
        and bool(result.get("latest_version"))
        and old == new
    )

    if result.get("check"):
        print(f"install mode: {mode}")
        if ahead:
            print(f"version: {old} (newer than PyPI's latest, {latest})")
        elif latest_unknown:
            print(f"version: {old} (PyPI's latest version could not be checked)")
        elif already_current:
            print(f"version: {old}")
            print(f"Main Branch is already current ({old}).")
        else:
            print(f"version: {old} -> {new}")
        raw_release = result.get("release")
        release = raw_release if isinstance(raw_release, dict) else {}
        release_url = str(release.get("url") or "")
        release_summary = str(release.get("summary") or "")
        release_available = release.get("available") is True
        if release_url and release_available:
            print(f"release notes: {release_url}")
        elif release_url and release.get("source") != "not_newer":
            print(f"expected release notes URL: {release_url}")
        if release_summary and release_available:
            print(f"release summary: {release_summary}")
        for action in result.get("actions", []):
            print(action)
        for action in result.get("next_actions", []):
            print(f"next: {action}")
        if count:
            print(f"would refresh {count} skill link(s)")
        _render_predicted_consent(result)
        if not refresh_surfaces:
            print("would skip agent surface refresh")
    elif result.get("ok") and result.get("manual_update_command"):
        print(f"install mode: {mode}")
        print(f"version: {old} -> {new}")
        print("Main Branch did not upgrade this install.")
        if refresh_surfaces:
            print(f"refreshed {count} skill link(s)")
            if result.get("codex_repaired"):
                print("refreshed Codex global skills")
            _render_surface_plan(result)
        else:
            print("skipped agent surface refresh")
        for action in result.get("next_actions", []):
            print(f"next: {action}")
    elif result.get("ok"):
        if ahead:
            print(f"Main Branch {old} is newer than PyPI's latest release ({latest}); not changed.")
        elif latest_unknown:
            print(f"Main Branch {old} was not changed; PyPI's latest version could not be checked.")
        elif old == new:
            print(f"Main Branch is already current ({new}).")
        else:
            print(f"updated Main Branch ({old} -> {new})")
        if refresh_surfaces:
            print(f"refreshed {count} skill link(s)")
            if result.get("codex_repaired"):
                print("refreshed Codex global skills")
            _render_surface_plan(result)
        else:
            print("skipped agent surface refresh")
        for action in result.get("next_actions", []):
            print(f"next: {action}")

    adapter = result.get("codex_adapter")
    global_skill = adapter.get("global_skill") if isinstance(adapter, dict) else None
    if isinstance(global_skill, dict) and global_skill.get("note"):
        # #1087 item 6: informational, not a warning or a step to run.
        print(f"note: {global_skill['note']}")
    if result.get("errors"):
        for error in result["errors"]:
            print(f"error: {error}")
    if result.get("warnings"):
        # #1078: a note printed under "for you to run" is not printed again here.
        printed_notes = {
            str(item["note"])
            for item in result.get("operator_actions", [])
            if isinstance(item, dict) and item.get("command") and item.get("note")
        }
        for warning in result["warnings"]:
            if warning not in printed_notes:
                print(f"warning: {warning}")
    if not result.get("check") and not result.get("ok"):
        for action in result.get("next_actions", []):
            print(f"next: {action}")
    _render_operator_actions(result)
