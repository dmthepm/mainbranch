"""Locate and link the bundled Main Branch engine payload.

The public wheel carries a synthetic engine root at ``mb/_engine`` whose
shape mirrors the source checkout enough for Claude Code skills:

```
mb/_engine/.claude/skills/...
mb/_engine/.claude/reference/...
mb/_engine/.claude/lenses/...
mb/_engine/workflows/...
mb/_engine/playbooks/...
```

Source checkouts use the repository root directly. Keeping both install
modes behind this module lets ``mb init`` and ``mb skill link`` wire the
same Claude Code discovery surface for pipx users and clone-based users.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from mb import __version__
from mb.durable import CorruptStateError, atomic_write_json, atomic_write_text, read_json_object

SKILL_PREFIX = "mb-"
PRIMARY_SKILL = "mb-start"
LEGACY_SKILL_NAMES = (
    "ads",
    "end",
    "help",
    "organic",
    "pull",
    "setup",
    "site",
    "skill-brief-draft",
    "skill-concept",
    "skill-review",
    "start",
    "think",
    "wiki",
)
RETIRED_PROJECT_SKILL_LINK_NAMES = (
    "mb-pull",
    "mb-vsl",
    "vsl",
)
ENGINE_MARKER = Path(".claude") / "skills" / PRIMARY_SKILL / "SKILL.md"
GITIGNORE_HEADER = "# Main Branch local Claude wiring"


def _is_engine_root(path: Path) -> bool:
    return (path / ENGINE_MARKER).is_file()


def source_engine_root() -> Path | None:
    """Return the repo root when running from a source checkout."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if _is_engine_root(parent):
            return parent
    return None


def packaged_engine_root() -> Path | None:
    """Return the installed wheel's synthetic engine root, if present."""
    try:
        ref = resources.files("mb").joinpath("_engine")
        root = Path(str(ref))
        if _is_engine_root(root):
            return root
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        pass
    return None


def engine_root() -> Path | None:
    """Return the best engine root for this install.

    Prefer the packaged payload when it exists so pipx installs win over
    stale clone paths. Source checkouts fall back to the repository root.
    """
    return packaged_engine_root() or source_engine_root()


def skills_dir(root: Path | None = None) -> Path | None:
    root = root or engine_root()
    if root is None:
        return None
    candidate = root / ".claude" / "skills"
    return candidate if candidate.is_dir() else None


def bundled_skills() -> list[str]:
    """Names of bundled skills, alphabetically.

    Only directories carrying a ``SKILL.md`` count. A source checkout's engine
    root is a live working tree, so leftover renamed or scratch directories
    under ``.claude/skills/`` (for example a pre-rename ``start/`` holding only
    ``.DS_Store``) must not be linked into business repos as skills.
    """
    root = skills_dir()
    if root is None:
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir() and (d / "SKILL.md").is_file())


def missing_bundled_links(repo: str | Path) -> list[str]:
    """Bundled skills without a discoverable project-local skill link."""
    links = Path(repo).resolve() / ".claude" / "skills"
    return [name for name in bundled_skills() if not (links / name / "SKILL.md").is_file()]


def legacy_skill_name(name: str) -> str:
    """Return the pre-prefix skill name for a bundled skill name."""
    return name[len(SKILL_PREFIX) :] if name.startswith(SKILL_PREFIX) else name


def skill_path(name: str) -> Path | None:
    """Return on-disk path to a bundled skill's directory."""
    root = skills_dir()
    if root is None:
        return None
    candidate = root / name
    return candidate if candidate.is_dir() else None


def _read_settings(path: Path, *, strict: bool = False) -> dict[str, Any]:
    if not path.exists():
        return {}
    if strict:
        return read_json_object(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _iter_mb_binaries(path_value: str | None = None) -> list[str]:
    """Return executable `mb` binaries on PATH, preserving PATH order."""
    path_text = path_value if path_value is not None else os.environ.get("PATH", "")
    binaries: list[str] = []
    seen: set[str] = set()
    for raw_dir in path_text.split(os.pathsep):
        if not raw_dir:
            continue
        candidate = Path(raw_dir).expanduser() / "mb"
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            continue
        try:
            key = str(candidate.resolve())
        except OSError:
            key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        binaries.append(str(candidate))
    return binaries


def _mb_binary_version(path: str, *, timeout: float = 3.0) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "version": "", "output": "", "error": str(exc)}
    output = (result.stdout or result.stderr).strip()
    version = output.removeprefix("mb ").strip() if output.startswith("mb ") else output
    return {
        "ok": result.returncode == 0,
        "version": version if result.returncode == 0 else "",
        "output": output,
        "error": "" if result.returncode == 0 else output,
    }


def mb_install_diagnostics(path_value: str | None = None) -> dict[str, Any]:
    """Describe active `mb` binaries on PATH for runtime wiring diagnostics."""
    active = shutil.which("mb") or ""
    installs: list[dict[str, Any]] = []
    for binary in _iter_mb_binaries(path_value):
        version = _mb_binary_version(binary)
        installs.append(
            {
                "path": binary,
                "version": version["version"],
                "ok": version["ok"],
                "error": version["error"],
                "active": bool(active and Path(binary) == Path(active)),
            }
        )
    versions = {str(item["version"]) for item in installs if item.get("version")}
    return {
        "active_path": active,
        "current_version": __version__,
        "installs": installs,
        "multiple_installs": len(installs) > 1,
        "multiple_versions": len(versions) > 1,
        "repair_command": "mb skill link --repo .",
    }


def _same_path(left: str, right: str) -> bool:
    if not left or not right:
        return False
    try:
        return Path(left).resolve() == Path(right).resolve()
    except OSError:
        return Path(left) == Path(right)


def _running_mb_path() -> str:
    """Console script of the running install, never found through PATH.

    pip, pipx and uv put the `mb` script next to the interpreter that runs it, so
    `sys.argv[0]` is the script that started this process when it is an `mb`
    file (it also covers installers that copy the script out of the venv). Else
    the bin dir of `sys.executable`, where pip, pipx and uv put the script;
    `sys.executable` is not resolved because a venv's `python` links to the base
    interpreter, which has no `mb`. Returns "" (for example under `python -m mb`
    from a bare checkout).
    """

    candidates: list[Path] = []
    if sys.argv and sys.argv[0] and Path(sys.argv[0]).name == "mb":
        candidates.append(Path(sys.argv[0]).expanduser().absolute())
    if sys.executable:
        candidates.append(Path(sys.executable).parent / "mb")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return ""


def login_shell_mb_diagnostics(shell: str | None = None, *, timeout: float = 5.0) -> dict[str, Any]:
    """Check which `mb` a login shell is likely to execute.

    Claude Code and Codex command execution can enter through a login shell even
    when the operator's current process has the right pipx or venv PATH. The login
    shell is asked only where `mb` is (`command -v`); that `mb` is never run. The
    running install is this package, so its version is `__version__`. The other
    install's version is not known without running it, so it is reported empty.
    """

    shell_path = shell or os.environ.get("SHELL") or "/bin/sh"
    command = (
        "mb_path=$(command -v mb 2>/dev/null || true); printf '__MB_PATH__=%s\\n' \"$mb_path\""
    )
    active_path = _running_mb_path()
    result: subprocess.CompletedProcess[str] | None = None
    try:
        result = subprocess.run(
            [shell_path, "-lc", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "checked": True,
            "ok": False,
            "state": "error",
            "shell": shell_path,
            "command": command,
            "path": "",
            "version": "",
            "active_path": active_path,
            "active_version": __version__,
            "path_mismatch": False,
            "version_mismatch": False,
            "mismatch": False,
            "error": str(exc),
            "summary": "Could not check the login-shell mb runtime path.",
            "repair": "Run `command -v mb` in the runtime shell.",
            "safe_to_share": True,
        }

    output_lines = (result.stdout or "").splitlines() + (result.stderr or "").splitlines()
    runtime_path = ""
    for raw_line in output_lines:
        line = raw_line.strip()
        if line.startswith("__MB_PATH__="):
            runtime_path = line.removeprefix("__MB_PATH__=").strip()
    command_ok = result.returncode == 0 and bool(runtime_path)
    same_install = bool(command_ok and _same_path(runtime_path, active_path))
    path_mismatch = bool(command_ok and active_path and not same_install)
    # The other mb is never run, so its version is unknown and never claimed.
    runtime_version = __version__ if same_install else ""
    version_mismatch = False
    mismatch = path_mismatch
    if not command_ok:
        state = "error"
        summary = "Login-shell runtime could not resolve a usable mb command."
    elif mismatch:
        state = "warn"
        summary = (
            "Login-shell runtime resolves a different mb than this process. "
            f"Active mb: {active_path} {__version__}; "
            f"login shell mb: {runtime_path} (version not checked)."
        )
    elif not active_path:
        state = "ok"
        summary = (
            f"Login shell resolves mb at {runtime_path}; this process's own mb "
            "script was not found, so they were not compared."
        )
    else:
        state = "ok"
        summary = "Login-shell runtime resolves the current mb command."
    return {
        "checked": True,
        "ok": bool(command_ok and not mismatch),
        "state": state,
        "shell": shell_path,
        "command": command,
        "path": runtime_path,
        "version": runtime_version,
        "active_path": active_path,
        "active_version": __version__,
        "path_mismatch": path_mismatch,
        "version_mismatch": version_mismatch,
        "mismatch": mismatch,
        "returncode": result.returncode,
        "error": "" if command_ok else "\n".join(output_lines),
        "summary": summary,
        "repair": (
            "Put the current Main Branch install earlier on the login-shell PATH, "
            "then rerun `mb status --json --peek`."
        )
        if mismatch
        else ("Install or expose `mb` on the runtime shell PATH." if not command_ok else ""),
        "safe_to_share": True,
    }


def _looks_like_engine_root_path(path: Path) -> bool:
    has_skill_marker = any(
        (path / ".claude" / "skills" / name / "SKILL.md").is_file()
        for name in (PRIMARY_SKILL, "start")
    )
    if not has_skill_marker:
        return False
    source_markers = [
        path / "mb" / "mb" / "__init__.py",
        path / "mb" / "pyproject.toml",
        path / "AGENTS.md",
        path / "CHANGELOG.md",
    ]
    packaged_markers = [
        path.parent / "__init__.py",
        path.parent / "py.typed",
    ]
    return any(marker.exists() for marker in source_markers) or (
        path.name == "_engine" and any(marker.exists() for marker in packaged_markers)
    )


def _looks_like_missing_legacy_engine_path(value: str) -> bool:
    parts = {part.lower() for part in Path(value).parts}
    return bool(parts & {"mb-vip", "mainbranch"})


def looks_like_missing_legacy_engine_path(value: str) -> bool:
    """Return whether a missing path looks like an old Main Branch engine clone."""
    return _looks_like_missing_legacy_engine_path(value)


def _is_stale_engine_path(value: str, active_root: Path) -> bool:
    candidate = Path(value).expanduser()
    try:
        if candidate.exists() and candidate.resolve() == active_root.resolve():
            return False
    except OSError:
        return False
    if candidate.exists():
        return _looks_like_engine_root_path(candidate)
    return _looks_like_missing_legacy_engine_path(value)


def is_stale_engine_path(value: str, active_root: Path) -> bool:
    """Return whether ``value`` points at a stale Main Branch engine root."""
    return _is_stale_engine_path(value, active_root)


def _render_settings(settings_path: Path, root: Path) -> tuple[str | None, list[str], str]:
    """The refreshed `.claude/settings.local.json` text, or None when unchanged."""
    try:
        data = _read_settings(settings_path, strict=True)
    except CorruptStateError as exc:
        return (
            None,
            [],
            (
                f"{settings_path} is not valid JSON ({exc.detail}); refused to "
                "refresh local Claude wiring to avoid clobbering your settings."
            ),
        )
    permissions = data.setdefault("permissions", {})
    if not isinstance(permissions, dict):
        permissions = {}
        data["permissions"] = permissions

    existing = permissions.get("additionalDirectories", [])
    if not isinstance(existing, list):
        existing = []

    root_str = str(root)
    removed_stale = [
        str(p)
        for p in existing
        if isinstance(p, str) and p != root_str and _is_stale_engine_path(p, root)
    ]
    cleaned = [
        str(p) for p in existing if isinstance(p, str) and p != root_str and p not in removed_stale
    ]
    permissions["additionalDirectories"] = [root_str, *cleaned]

    rendered = json.dumps(data, indent=2, sort_keys=True) + "\n"
    changed = not settings_path.exists() or settings_path.read_text(encoding="utf-8") != rendered
    return (rendered if changed else None), removed_stale, ""


def _link_or_copy(source: Path, dest: Path) -> str:
    if dest.is_symlink():
        try:
            if dest.resolve(strict=True) == source.resolve(strict=True):
                return "unchanged"
        except FileNotFoundError:
            pass
        dest.unlink()
    elif dest.exists():
        return "skipped"

    try:
        dest.symlink_to(source, target_is_directory=True)
        return "linked"
    except OSError:
        shutil.copytree(
            source,
            dest,
            ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"),
        )
        return "copied"


def _personal_skills_dir() -> Path:
    return Path.home() / ".claude" / "skills"


def _frontmatter_name(skill_file: Path) -> str:
    try:
        text = skill_file.read_text(encoding="utf-8")
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end == -1:
        return ""
    for line in text[3:end].splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def _infer_skill_root(skill_path: Path, name: str) -> Path | None:
    try:
        resolved = skill_path.resolve(strict=True)
    except FileNotFoundError:
        return None
    if resolved.name != name:
        return None
    if resolved.parent.name != "skills" or resolved.parent.parent.name != ".claude":
        return None
    return resolved.parent.parent.parent


def _looks_like_mainbranch_engine(root: Path | None, skill_path: Path, name: str) -> bool:
    if root is None:
        return False
    skill_file = skill_path / "SKILL.md"
    if not skill_file.is_file():
        return False
    frontmatter_name = _frontmatter_name(skill_file)
    if frontmatter_name and frontmatter_name != name:
        return False
    source_markers = [
        root / "mb" / "mb" / "__init__.py",
        root / "mb" / "pyproject.toml",
        root / "AGENTS.md",
        root / "CHANGELOG.md",
    ]
    packaged_markers = [
        root.parent / "__init__.py",
        root.parent / "py.typed",
    ]
    return any(marker.exists() for marker in source_markers) or (
        root.name == "_engine" and any(marker.exists() for marker in packaged_markers)
    )


def _classify_personal_skill(entry: Path, name: str) -> tuple[str, str]:
    if not entry.exists() and not entry.is_symlink():
        return "missing", ""
    if entry.is_symlink():
        try:
            resolved = entry.resolve(strict=True)
        except FileNotFoundError:
            return "broken-symlink", ""
        root = _infer_skill_root(entry, name)
        if _looks_like_mainbranch_engine(root, resolved, name):
            return "stale-mainbranch-link", str(resolved)
        return "not-mainbranch-link", str(resolved)
    return "not-mainbranch-link", str(entry)


# `mb skill link` moves personal links here, at a path it can plan exactly.
LINK_BACKUP_FOLDER = "skill-link"


def _backup_destination(global_dir: Path, name: str, folder: str) -> Path:
    base = global_dir / ".mainbranch-backups" / folder
    candidate = base / name
    if not candidate.exists() and not candidate.is_symlink():
        return candidate
    suffix = 1
    while True:
        candidate = base / f"{name}-{suffix}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        suffix += 1


def _conflict_finding(
    *,
    name: str,
    kind: str,
    global_dir: Path,
    repo: Path,
    apply: bool,
    timestamp: str,
    backup_to: Path | None = None,
) -> dict[str, Any]:
    entry = global_dir / name
    classification, target = _classify_personal_skill(entry, name)
    safe_to_repair = classification in {"stale-mainbranch-link", "broken-symlink"}
    backup_path = ""
    repaired = False
    error = ""
    if apply and safe_to_repair:
        backup = backup_to or _backup_destination(global_dir, name, timestamp)
        try:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(entry), str(backup))
            repaired = True
            backup_path = str(backup)
        except OSError as exc:
            error = str(exc)

    current_name = f"{SKILL_PREFIX}{name}" if kind == "legacy-global" else name
    return {
        "name": name,
        "current_name": current_name,
        "kind": kind,
        "global_path": str(entry),
        "global_target": target,
        "project_path": str(repo / ".claude" / "skills" / current_name),
        "classification": classification,
        "safe_to_repair": safe_to_repair,
        "repaired": repaired,
        "backup_path": backup_path,
        "error": error,
        "message": (
            "personal skill shadows the project-local Main Branch skill"
            if kind == "active-shadow"
            else "legacy personal skill can still catch the old slash command"
        ),
    }


def inspect_personal_skill_conflicts(
    repo: str | Path,
    *,
    apply: bool = False,
    personal_skills_dir: Path | None = None,
    backup_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Inspect or repair personal Claude Code skills that can shadow Main Branch.

    ``apply`` only moves stale Main Branch symlinks and broken symlinks matching
    Main Branch's current or legacy skill names. User-authored or third-party
    skills are reported but never changed. ``backup_paths`` limits the repair
    to the names a plan listed and moves each to its planned path.
    """
    target = Path(repo).expanduser().resolve()
    global_dir = personal_skills_dir or _personal_skills_dir()
    current_names = bundled_skills()
    findings: list[dict[str, Any]] = []
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for name in current_names:
        project_skill = target / ".claude" / "skills" / name / "SKILL.md"
        global_entry = global_dir / name
        if project_skill.is_file() and (global_entry.exists() or global_entry.is_symlink()):
            findings.append(
                _conflict_finding(
                    name=name,
                    kind="active-shadow",
                    global_dir=global_dir,
                    repo=target,
                    apply=apply and (backup_paths is None or name in backup_paths),
                    timestamp=timestamp,
                    backup_to=(backup_paths or {}).get(name),
                )
            )

    current_legacy_names = {legacy_skill_name(name) for name in current_names}
    for name in LEGACY_SKILL_NAMES:
        global_entry = global_dir / name
        if name in current_legacy_names and (global_entry.exists() or global_entry.is_symlink()):
            findings.append(
                _conflict_finding(
                    name=name,
                    kind="legacy-global",
                    global_dir=global_dir,
                    repo=target,
                    apply=apply and (backup_paths is None or name in backup_paths),
                    timestamp=timestamp,
                    backup_to=(backup_paths or {}).get(name),
                )
            )

    blocking = [
        item
        for item in findings
        if item["kind"] == "active-shadow" and not item.get("repaired", False)
    ]
    repairable = [
        item for item in findings if item["safe_to_repair"] and not item.get("repaired", False)
    ]
    errors = [item for item in findings if item["error"]]
    return {
        "ok": not blocking and not errors,
        "repo": str(target),
        "personal_skills_dir": str(global_dir),
        "checked_current_skills": current_names,
        "checked_legacy_skills": list(LEGACY_SKILL_NAMES),
        "apply": apply,
        "findings": findings,
        "summary": {
            "findings": len(findings),
            "active_shadows": sum(1 for item in findings if item["kind"] == "active-shadow"),
            "legacy_globals": sum(1 for item in findings if item["kind"] == "legacy-global"),
            "repairable": len(repairable),
            "repaired": sum(1 for item in findings if item["repaired"]),
            "blocked": len(blocking),
            "errors": len(errors),
        },
        "repair_command": "mb skill repair --repo . --apply",
    }


def _link_gitignore_entries() -> tuple[list[str], list[str]]:
    """The `.gitignore` lines `link_skills` keeps, and the retired ones it drops."""
    entries = [
        ".claude/settings.local.json",
        ".claude/worktrees/",
        *[f".claude/skills/{name}" for name in bundled_skills()],
    ]
    retired = [
        f".claude/skills/{name}"
        for name in sorted(set(LEGACY_SKILL_NAMES) | set(RETIRED_PROJECT_SKILL_LINK_NAMES))
        if name not in bundled_skills()
    ]
    return entries, retired


class _TrackedIndex:
    """Answers "does git track this real path?" in whichever repo holds it.

    An alias (a symlinked `.claude/`, a global skill folder linked into a repo)
    can land a write in any git work tree, so the lookup starts from the real
    destination, not from the business repo. Unknowns count as tracked.
    """

    def __init__(self) -> None:
        self._toplevels: dict[str, str | None] = {}
        self._tracked: dict[str, set[str] | None] = {}

    def _git(self, cwd: str, *args: str) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                ["git", "-C", cwd, *args],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            return None

    def _toplevel(self, real: str) -> str | None:
        probe = real
        while not os.path.isdir(probe):
            parent = os.path.dirname(probe)
            if parent == probe:
                return None
            probe = parent
        if probe not in self._toplevels:
            proc = self._git(probe, "rev-parse", "--show-toplevel")
            top = proc.stdout.strip() if proc is not None and proc.returncode == 0 else ""
            self._toplevels[probe] = os.path.realpath(top) if top else None
        return self._toplevels[probe]

    def _tracked_set(self, top: str) -> set[str] | None:
        if top not in self._tracked:
            proc = self._git(top, "ls-files", "-z")
            self._tracked[top] = (
                {item for item in proc.stdout.split("\0") if item}
                if proc is not None and proc.returncode == 0
                else None
            )
        return self._tracked[top]

    def is_tracked(self, real: str) -> bool:
        top = self._toplevel(real)
        if top is None:
            return False
        rel = os.path.relpath(real, top)
        if rel == "." or rel.startswith(".."):
            return True
        rel = rel.replace(os.sep, "/")
        if rel == ".git" or rel.startswith(".git/"):
            return True
        tracked = self._tracked_set(top)
        if tracked is None:
            return True
        prefix = rel + "/"
        return rel in tracked or any(item.startswith(prefix) for item in tracked)


class _TrackedIdentities:
    """The business repo's tracked files and their folders, by (device, inode).

    A case variant (`agents.md` for `AGENTS.md` on a case-insensitive disk), a
    symlink or a hard link reaches the same inode under another spelling, so
    matching identities catches every alias a string comparison misses.
    """

    def __init__(self, repo_real: str) -> None:
        self.repo = repo_real
        self.files: dict[tuple[int, int], str] = {}
        self.dirs: dict[tuple[int, int], str] = {}
        self.names: set[str] = set()
        self.known = False
        inside = self._git("rev-parse", "--is-inside-work-tree")
        if inside is not None and inside.returncode != 0:
            self.known = True  # not a git work tree: nothing here is tracked
            return
        proc = self._git("ls-files", "-z")
        if inside is None or proc is None or proc.returncode != 0:
            return
        self.known = True
        folders: set[str] = {"."}
        for rel in (item for item in proc.stdout.split("\0") if item):
            self.names.add(rel.casefold())
            try:
                st = os.lstat(os.path.join(repo_real, rel))
            except OSError:
                continue  # tracked but missing from the work tree
            self.files.setdefault((st.st_dev, st.st_ino), rel)
            parent = os.path.dirname(rel)
            while parent and parent not in folders:
                folders.add(parent)
                parent = os.path.dirname(parent)
        for rel in folders:
            try:
                st = os.stat(os.path.join(repo_real, rel))
            except OSError:
                continue
            self.dirs.setdefault((st.st_dev, st.st_ino), rel)

    def _git(self, *args: str) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                ["git", "-C", self.repo, *args],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            return None

    def match(self, path: str, op: str) -> str | None:
        """The tracked path ``op`` on ``path`` would change, or None.

        Raises OSError when the destination cannot be checked.
        """
        if not self.known:
            raise OSError(f"cannot list the files git tracks in {self.repo}")
        lexical = os.path.abspath(path)
        try:
            st = os.lstat(lexical)
        except FileNotFoundError:
            return self._match_new(lexical)
        hit = self._match_stat(st, op)
        if hit is None and op in _FOLLOWING_OPS and os.path.islink(lexical):
            try:
                hit = self._match_stat(os.stat(lexical), op)
            except FileNotFoundError:
                return None
        return hit

    def _match_stat(self, st: os.stat_result, op: str) -> str | None:
        key = (st.st_dev, st.st_ino)
        if key in self.files:
            return self.files[key]
        if op == "delete_tree" and key in self.dirs:
            return self.dirs[key]
        return None

    def _match_new(self, lexical: str) -> str | None:
        """A path that does not exist yet: is a tracked file missing there?"""
        parent, rest = lexical, ""
        while True:
            head, tail = os.path.split(parent)
            if head == parent:
                return None
            parent, rest = head, os.path.join(tail, rest) if rest else tail
            try:
                st = os.stat(parent)
            except FileNotFoundError:
                continue
            folder = self.dirs.get((st.st_dev, st.st_ino))
            if folder is None:
                return None
            rel = rest if folder == "." else f"{folder}/{rest}"
            rel = rel.replace(os.sep, "/")
            folded = rel.casefold()
            if folded in self.names or any(name.startswith(folded + "/") for name in self.names):
                return rel
            return None


# Operations whose last path component is followed when written or removed.
_FOLLOWING_OPS = frozenset({"write", "delete_tree"})


def _real_destinations(path: str, op: str) -> list[str]:
    lexical = os.path.abspath(path)
    nofollow = os.path.join(os.path.realpath(os.path.dirname(lexical)), os.path.basename(lexical))
    destinations = [nofollow]
    if op in _FOLLOWING_OPS and os.path.islink(nofollow):
        destinations.append(os.path.realpath(nofollow))
    return destinations


def consent_destinations(
    repo: str | Path, operations: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """The planned operations that would change a file git tracks.

    Two checks, and either one is enough. By identity: a destination that
    exists (or, for a new path, its nearest existing parent) is compared by
    device and inode with the business repo's tracked files and the folders
    that hold them, so case variants, symlinks and hard links all match. By
    real path: the destination is resolved through every symlinked parent
    (and a followed last component) and looked up in the git work tree that
    really holds it, whichever repo that is. Anything that cannot be checked
    needs consent. Paths inside ``repo`` are reported relative to it; anything
    else is reported as its real absolute path.
    """
    repo_real = os.path.realpath(Path(repo).expanduser())
    index = _TrackedIndex()
    identities = _TrackedIdentities(repo_real)
    needed: list[dict[str, str]] = []
    for operation in operations:
        op = str(operation.get("op") or "")
        raw = str(operation.get("path") or "")
        try:
            by_identity = identities.match(raw, op)
            destinations = _real_destinations(str(operation["path"]), op)
        except (KeyError, OSError, ValueError):
            needed.append({"path": raw, "op": op})
            continue
        if by_identity is not None:
            needed.append({"path": by_identity, "op": op})
            continue
        for real in destinations:
            if not index.is_tracked(real):
                continue
            inside = real == repo_real or real.startswith(repo_real + os.sep)
            shown = os.path.relpath(real, repo_real).replace(os.sep, "/") if inside else real
            needed.append({"path": shown, "op": op})
            break
    unique: dict[tuple[str, str], dict[str, str]] = {}
    for item in needed:
        unique.setdefault((item["path"], item["op"]), item)
    return list(unique.values())


def public_operations(operations: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Operations without their file contents, for plans and JSON."""
    return [{"op": str(item["op"]), "path": str(item["path"])} for item in operations]


def _gitignore_text_after(existing: str, add: list[str], remove: list[str]) -> str:
    """The `.gitignore` text `link_skills` leaves behind."""
    text = existing
    lines = text.splitlines()
    kept = [line for line in lines if line not in set(remove)]
    if kept != lines:
        text = "\n".join(kept)
        if text:
            text += "\n"
    existing_lines = set(text.splitlines())
    to_add = [entry for entry in add if entry not in existing_lines]
    if not to_add:
        return text
    prefix = "" if not text or text.endswith("\n") else "\n"
    block = to_add if GITIGNORE_HEADER in existing_lines else [GITIGNORE_HEADER, *to_add]
    return text + prefix + "\n".join(block) + "\n"


def _planned_personal_repairs(global_dir: Path) -> list[str]:
    """Personal skill names whose stale or broken link `link_skills` may move.

    Planned as if every project skill were present, because the link creates
    them before the repair runs; the repair is then limited to these names.
    """
    current_names = bundled_skills()
    current_legacy_names = {legacy_skill_name(name) for name in current_names}
    candidates = [
        *current_names,
        *[name for name in LEGACY_SKILL_NAMES if name in current_legacy_names],
    ]
    planned: list[str] = []
    for name in candidates:
        entry = global_dir / name
        if not entry.exists() and not entry.is_symlink():
            continue
        classification, _ = _classify_personal_skill(entry, name)
        if classification in {"stale-mainbranch-link", "broken-symlink"}:
            planned.append(name)
    return list(dict.fromkeys(planned))


def _link_operations(target: Path, root: Path) -> dict[str, Any]:
    """Every destination `link_skills` will touch, in the order it touches them.

    `link_skills` executes this list and nothing else, so `mb skill link
    --plan` and `mb update` see exactly what the link will change (#1012).
    """
    skill_link_dir = target / ".claude" / "skills"
    operations: list[dict[str, Any]] = []
    settings_path = target / ".claude" / "settings.local.json"
    rendered, removed_stale, error = _render_settings(settings_path, root)
    if error:
        return {"error": error, "removed_stale_engine_paths": removed_stale}
    if rendered is not None:
        operations.append(
            {
                "op": "write",
                "path": str(settings_path),
                "rel": ".claude/settings.local.json",
                "content": rendered,
            }
        )

    removable_names = sorted(set(LEGACY_SKILL_NAMES) | set(RETIRED_PROJECT_SKILL_LINK_NAMES))
    for name in removable_names:
        dest = skill_link_dir / name
        if dest.is_symlink():
            operations.append({"op": "delete", "path": str(dest), "rel": f".claude/skills/{name}"})

    skipped: list[str] = []
    for name in bundled_skills():
        source = root / ".claude" / "skills" / name
        dest = skill_link_dir / name
        rel = f".claude/skills/{name}"
        if dest.is_symlink():
            try:
                if dest.resolve(strict=True) == source.resolve(strict=True):
                    continue
            except FileNotFoundError:
                pass
            op = "replace_link"
        elif dest.exists():
            skipped.append(rel)
            continue
        else:
            op = "create_link"
        operations.append({"op": op, "path": str(dest), "rel": rel, "source": str(source)})

    entries, retired = _link_gitignore_entries()
    gitignore = target / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    existing_lines = set(existing.splitlines())
    gitignore_add = [entry for entry in entries if entry not in existing_lines]
    gitignore_remove = [entry for entry in retired if entry in existing_lines]
    updated = _gitignore_text_after(existing, entries, retired)
    if updated != existing:
        operations.append(
            {"op": "write", "path": str(gitignore), "rel": ".gitignore", "content": updated}
        )

    global_dir = _personal_skills_dir()
    personal = _planned_personal_repairs(global_dir)
    backup_paths: dict[str, Path] = {}
    for name in personal:
        backup = _backup_destination(global_dir, name, LINK_BACKUP_FOLDER)
        backup_paths[name] = backup
        operations.append({"op": "delete", "path": str(global_dir / name), "rel": ""})
        operations.append({"op": "create", "path": str(backup), "rel": ""})

    return {
        "error": "",
        "operations": operations,
        "skipped": skipped,
        "gitignore_add": gitignore_add,
        "gitignore_remove": gitignore_remove,
        "personal_repairs": personal,
        "backup_paths": backup_paths,
        "removed_stale_engine_paths": removed_stale,
    }


def plan_link_skills(repo: str | Path) -> dict[str, Any]:
    """What `link_skills` would change, without writing anything.

    ``operations`` lists every destination the link touches (write, delete,
    create or replace a link). ``tracked_changes`` lists the ones that would
    change a file git tracks, after resolving symlinked parents, and
    ``tracked_writes`` their paths. `mb update` links unattended only when
    ``tracked_changes`` is empty (#1012).
    """
    target = Path(repo).expanduser().resolve()
    root = engine_root()
    empty: dict[str, Any] = {
        "ok": False,
        "plan": True,
        "repo": str(target),
        "engine_root": str(root) if root is not None else None,
        "linked": [],
        "skipped": [],
        "removed_legacy": [],
        "gitignore_add": [],
        "gitignore_remove": [],
        "operations": [],
        "tracked_changes": [],
        "tracked_writes": [],
    }
    if root is None:
        return {**empty, "errors": ["could not locate bundled Main Branch engine root"]}
    planned = _link_operations(target, root)
    if planned["error"]:
        return {**empty, "errors": [planned["error"]]}
    operations = planned["operations"]
    tracked = consent_destinations(target, operations)
    return {
        **empty,
        "ok": True,
        "linked": [
            item["rel"] for item in operations if item["op"] in {"create_link", "replace_link"}
        ],
        "skipped": planned["skipped"],
        "removed_legacy": [
            item["rel"] for item in operations if item["op"] == "delete" and item["rel"]
        ],
        "gitignore_add": planned["gitignore_add"],
        "gitignore_remove": planned["gitignore_remove"],
        "operations": public_operations(operations),
        "tracked_changes": tracked,
        "tracked_writes": list(dict.fromkeys(item["path"] for item in tracked)),
        "errors": [],
    }


def link_skills(repo: str | Path) -> dict[str, Any]:
    """Wire bundled skills into a business repo for Claude Code discovery."""
    target = Path(repo).resolve()
    target.mkdir(parents=True, exist_ok=True)

    root = engine_root()
    if root is None:
        return {
            "ok": False,
            "repo": str(target),
            "engine_root": None,
            "created": [],
            "linked": [],
            "copied": [],
            "skipped": [],
            "errors": ["could not locate bundled Main Branch engine root"],
        }

    planned = _link_operations(target, root)
    if planned["error"]:
        return {
            "ok": False,
            "repo": str(target),
            "engine_root": str(root),
            "created": [],
            "linked": [],
            "copied": [],
            "skipped": [],
            "removed_legacy": [],
            "removed_stale_engine_paths": planned["removed_stale_engine_paths"],
            "errors": [planned["error"]],
        }

    (target / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    linked: list[str] = []
    copied: list[str] = []
    skipped: list[str] = list(planned["skipped"])
    removed_legacy: list[str] = []
    for item in planned["operations"]:
        op = item["op"]
        path = Path(item["path"])
        rel = item["rel"]
        if not rel:
            continue  # personal skill repairs run below, limited to the plan
        if op == "write":
            atomic_write_text(path, item["content"])
            created.append(rel)
        elif op == "delete":
            if path.is_symlink():
                path.unlink()
                removed_legacy.append(rel)
        else:
            mode = _link_or_copy(Path(item["source"]), path)
            if mode == "linked":
                linked.append(rel)
                created.append(rel)
            elif mode == "copied":
                copied.append(rel)
                created.append(rel)
            elif mode == "skipped":
                skipped.append(rel)

    return {
        "ok": True,
        "repo": str(target),
        "engine_root": str(root),
        "created": list(dict.fromkeys(created)),
        "linked": linked,
        "copied": copied,
        "skipped": skipped,
        "removed_legacy": removed_legacy,
        "removed_stale_engine_paths": planned["removed_stale_engine_paths"],
        "errors": [],
        "shadow_report": inspect_personal_skill_conflicts(
            target, apply=True, backup_paths=planned["backup_paths"]
        ),
    }


def _is_linked_worktree(target: Path) -> bool:
    """True when ``target`` is a linked git worktree (not the primary checkout)."""

    def _rev_parse(arg: str) -> str:
        try:
            proc = subprocess.run(
                ["git", "rev-parse", arg],
                cwd=target,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return proc.stdout.strip() if proc.returncode == 0 else ""

    git_dir = _rev_parse("--git-dir")
    common_dir = _rev_parse("--git-common-dir")
    if not git_dir or not common_dir:
        return False
    git_dir_path = (
        (target / git_dir).resolve() if not Path(git_dir).is_absolute() else Path(git_dir).resolve()
    )
    common_dir_path = (
        (target / common_dir).resolve()
        if not Path(common_dir).is_absolute()
        else Path(common_dir).resolve()
    )
    return git_dir_path != common_dir_path


def link_status(repo: str | Path) -> dict[str, Any]:
    """Return whether ``repo`` can discover Main Branch skills."""
    target = Path(repo).resolve()
    flag = repo_flag(target)
    root = engine_root()
    settings_path = target / ".claude" / "settings.local.json"
    settings = _read_settings(settings_path)
    dirs = settings.get("permissions", {}).get("additionalDirectories", [])
    if not isinstance(dirs, list):
        dirs = []

    root_str = str(root) if root is not None else ""
    settings_has_engine = bool(root_str and root_str in dirs)
    stale_engine_paths = [
        value
        for value in dirs
        if isinstance(value, str) and root is not None and _is_stale_engine_path(value, root)
    ]
    configured_engine_paths = [
        value
        for value in dirs
        if isinstance(value, str) and _looks_like_engine_root_path(Path(value).expanduser())
    ]
    wired_engine_path = (
        root_str
        if settings_has_engine
        else (
            stale_engine_paths[0]
            if stale_engine_paths
            else (configured_engine_paths[0] if configured_engine_paths else "")
        )
    )
    start_link = target / ".claude" / "skills" / PRIMARY_SKILL
    start_skill = start_link / "SKILL.md"
    start_link_ok = start_skill.is_file()
    shadow_report = inspect_personal_skill_conflicts(target, apply=False)
    install_diagnostics = mb_install_diagnostics()
    stale_from_other_install = bool(stale_engine_paths and install_diagnostics["multiple_installs"])
    missing: list[str] = []
    if not settings_has_engine:
        missing.append("Main Branch engine access")
    if not start_link_ok:
        missing.append("project-local /mb-start bridge")
    if not shadow_report["ok"]:
        missing.append("personal Claude skill shadow")
    is_linked_worktree = _is_linked_worktree(target)
    if not missing:
        summary = "Main Branch start wiring is ready."
    elif is_linked_worktree:
        # The wiring is gitignored, so a fresh worktree never carries it.
        # Name that explicitly: operators read this as "skills disappeared".
        summary = (
            "This is a git worktree, and Main Branch wiring is machine-local "
            "state that worktrees do not inherit — every fresh worktree starts "
            "without it. Missing: " + ", ".join(missing) + ". "
            "Run `mb skill link --repo .` here, then reload skills."
        )
    else:
        summary = "Missing Main Branch start wiring: " + ", ".join(missing) + "."

    plugin = plugin_wiring_status(target)
    if missing and plugin["wired"]:
        summary += (
            " Tracked plugin wiring is present — once the plugin is active, "
            "skill discovery survives fresh worktrees without relinking."
        )
    return {
        "ok": settings_has_engine and start_link_ok and shadow_report["ok"],
        "plugin": plugin,
        "is_linked_worktree": is_linked_worktree,
        "repo": str(target),
        "engine_root": root_str or None,
        "settings_path": str(settings_path),
        "settings_has_engine": settings_has_engine,
        "settings_additional_directories": [str(item) for item in dirs if isinstance(item, str)],
        "wired_engine_path": wired_engine_path,
        "stale_engine_paths": stale_engine_paths,
        "stale_from_other_install": stale_from_other_install,
        "current_mb": {
            "path": install_diagnostics["active_path"],
            "version": install_diagnostics["current_version"],
            "engine_root": root_str or "",
        },
        "mb_installs": install_diagnostics,
        "primary_skill": PRIMARY_SKILL,
        "primary_link_ok": start_link_ok,
        "primary_link": str(start_link),
        "start_link_ok": start_link_ok,
        "start_link": str(start_link),
        "shadow_report": shadow_report,
        "missing": missing,
        "summary": summary,
        "fallback_commands": [
            f"mb start{flag} --json",
            f"mb doctor repair{flag} --plan",
            f"mb doctor repair{flag} --apply",
        ],
        "repair_command": "mb skill link --repo .",
    }


PACKAGE_NAME = "mainbranch"


def uv_tool_roots() -> list[Path]:
    """Directories uv keeps tool virtualenvs in, most specific first.

    uv resolves its tool directory from ``UV_TOOL_DIR``, then
    ``$XDG_DATA_HOME/uv/tools``, then ``~/.local/share/uv/tools``. Checking all
    three keeps detection correct for operators who relocate the tool root
    without paying for a ``uv tool dir`` subprocess on every diagnostic call.
    """
    roots: list[Path] = []
    tool_dir = os.environ.get("UV_TOOL_DIR", "").strip()
    if tool_dir:
        roots.append(Path(tool_dir).expanduser())
    data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    if data_home:
        roots.append(Path(data_home).expanduser() / "uv" / "tools")
    roots.append(Path.home() / ".local" / "share" / "uv" / "tools")
    return roots


def _under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except (OSError, ValueError):
        return False
    return True


def looks_like_uv_tool_install(
    root: Path | None = None,
    *,
    tool_roots: list[Path] | None = None,
) -> bool:
    """True when this install lives inside a ``uv tool install`` environment.

    The engine payload under ``<uv tool dir>/<package>/`` is the signal that
    carries detection (#963).

    ``sys.executable`` is checked too, but it only fires on Windows, where venv
    interpreters are copies. On macOS and Linux a uv tool venv's ``bin/python``
    is a symlink out to the uv-managed base interpreter under ``uv/python/``,
    and containment is checked after ``.resolve()``, so that candidate cannot
    match there — and cannot produce a false positive either.

    Pass ``tool_roots`` to test against a tool directory reported by uv itself
    instead of the documented defaults.
    """
    candidates = [root if root is not None else engine_root(), Path(sys.executable)]
    paths = [candidate for candidate in candidates if candidate is not None]
    for tool_root in uv_tool_roots() if tool_roots is None else tool_roots:
        package_root = tool_root / PACKAGE_NAME
        if any(_under(path, package_root) for path in paths):
            return True
    return False


def install_mode() -> str:
    """Best-effort install mode label for diagnostics and skill prose."""
    root = engine_root()
    if root is None:
        return "unknown"
    if packaged_engine_root() is not None:
        root_text = str(root)
        pipx_home = os.environ.get("PIPX_HOME", "").strip()
        prefix = Path(pipx_home).expanduser() if pipx_home else None
        if "pipx" in root_text or (prefix is not None and str(prefix) in root_text):
            return "pipx"
        if looks_like_uv_tool_install(root):
            return "uv"
        return "wheel"
    if (root / ".git").exists():
        return "clone"
    return "source"


PLUGIN_MARKETPLACE_NAME = "mainbranch"
PLUGIN_REPO = "noontide-co/mainbranch"
PLUGIN_ENABLE_KEY = "mainbranch@mainbranch"
PLUGIN_INSTALL_COMMAND = (
    "claude plugin marketplace update mainbranch && "
    "claude plugin install mainbranch@mainbranch --scope user"
)


def _tracked_settings_path(repo: Path) -> Path:
    return repo / ".claude" / "settings.json"


def plugin_wiring_status(repo: str | Path) -> dict[str, Any]:
    """Report the worktree-durable plugin wiring in tracked settings.

    Stage 2 of the plugin migration (decisions/2026-06-10): plugin
    enablement written to TRACKED `.claude/settings.json` survives
    worktrees, unlike the gitignored symlink wiring. Shape verified live
    against `claude plugin marketplace add` output.
    """
    target = Path(repo).resolve()
    settings = _read_settings(_tracked_settings_path(target))
    marketplaces = settings.get("extraKnownMarketplaces")
    marketplace = (
        marketplaces.get(PLUGIN_MARKETPLACE_NAME) if isinstance(marketplaces, dict) else None
    )
    source = (marketplace or {}).get("source") if isinstance(marketplace, dict) else None
    marketplace_known = bool(
        isinstance(source, dict)
        and source.get("source") == "github"
        and source.get("repo") == PLUGIN_REPO
    )
    enabled_plugins = settings.get("enabledPlugins")
    plugin_enabled = bool(
        isinstance(enabled_plugins, dict) and enabled_plugins.get(PLUGIN_ENABLE_KEY) is True
    )
    return {
        "marketplace_known": marketplace_known,
        "plugin_enabled": plugin_enabled,
        "wired": marketplace_known and plugin_enabled,
        "settings_path": str(_tracked_settings_path(target)),
    }


def _plugin_entry_summary(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(entry.get("id") or ""),
        "version": str(entry.get("version") or ""),
        "scope": str(entry.get("scope") or ""),
        "enabled": entry.get("enabled") is True,
        "install_path": str(entry.get("installPath") or entry.get("install_path") or ""),
    }


def _run_claude_plugin_list(*, timeout: float = 5.0) -> subprocess.CompletedProcess[str] | None:
    claude = shutil.which("claude")
    if not claude:
        return None
    try:
        return subprocess.run(
            [claude, "plugin", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return subprocess.CompletedProcess(
            args=[claude, "plugin", "list", "--json"],
            returncode=1,
            stdout="",
            stderr="could not run `claude plugin list --json`",
        )


def claude_mainbranch_plugin_status(
    *, expected_version: str | None = None, timeout: float = 5.0
) -> dict[str, Any]:
    """Report the installed Claude Code Main Branch plugin version.

    `mb update` can refresh packaged project-local bridge links, but Claude
    Code plugin installs are loaded by the runtime and do not self-update just
    because the `mainbranch` package changed. This probe is best-effort: if
    Claude Code is not installed or does not support JSON plugin listing, the
    caller gets an unchecked status instead of a hard failure.
    """
    expected = (expected_version or __version__).strip()
    base: dict[str, Any] = {
        "checked": False,
        "ok": False,
        "state": "unchecked",
        "expected_version": expected,
        "installed_version": "",
        "installed_versions": [],
        "enabled_versions": [],
        "entries": [],
        "command": "claude plugin list --json",
        "repair": PLUGIN_INSTALL_COMMAND,
        "summary": "Claude Code plugin version was not checked.",
    }
    result = _run_claude_plugin_list(timeout=timeout)
    if result is None:
        base.update(
            {
                "state": "claude_missing",
                "summary": "Claude Code CLI is not on PATH; plugin version was not checked.",
            }
        )
        return base
    base["checked"] = True
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        base.update(
            {
                "state": "error",
                "summary": detail or "`claude plugin list --json` failed.",
            }
        )
        return base
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        base.update(
            {"state": "invalid_json", "summary": "Claude plugin list returned invalid JSON."}
        )
        return base
    if not isinstance(payload, list):
        base.update(
            {
                "state": "invalid_json",
                "summary": "Claude plugin list returned an unexpected JSON shape.",
            }
        )
        return base

    entries = [
        _plugin_entry_summary(entry)
        for entry in payload
        if isinstance(entry, dict) and str(entry.get("id") or "") == PLUGIN_ENABLE_KEY
    ]
    installed_versions = sorted({entry["version"] for entry in entries if entry["version"]})
    enabled_entries = [entry for entry in entries if entry["enabled"]]
    enabled_versions = sorted({entry["version"] for entry in enabled_entries if entry["version"]})
    preferred = next(
        (entry for entry in enabled_entries if expected and entry["version"] == expected),
        enabled_entries[0] if enabled_entries else (entries[0] if entries else {}),
    )
    installed_version = str(preferred.get("version") or "")
    base.update(
        {
            "installed_version": installed_version,
            "installed_versions": installed_versions,
            "enabled_versions": enabled_versions,
            "entries": entries,
        }
    )
    if not entries:
        base.update(
            {
                "state": "not_installed",
                "summary": "The Main Branch Claude Code plugin is not installed.",
            }
        )
        return base
    if expected and expected in enabled_versions:
        base.update(
            {
                "ok": True,
                "state": "current",
                "summary": f"Main Branch Claude Code plugin is enabled at {expected}.",
            }
        )
        return base
    if expected and expected in installed_versions:
        base.update(
            {
                "state": "installed_not_enabled",
                "summary": (
                    f"Main Branch Claude Code plugin {expected} is installed but not enabled."
                ),
            }
        )
        return base
    if enabled_versions:
        base.update(
            {
                "state": "stale",
                "summary": (
                    "Main Branch Claude Code plugin is enabled at "
                    f"{', '.join(enabled_versions)}, expected {expected or 'the current package'}."
                ),
            }
        )
        return base
    base.update(
        {
            "state": "disabled",
            "summary": "The Main Branch Claude Code plugin is installed but disabled.",
        }
    )
    return base


# The plugin-rail switch writes a tracked file, so `mb update` and
# `mb doctor repair` list it in `operator_actions` for a person, never as a
# step an agent runs (#1023, #1042).
PLUGIN_SWITCH_COMMAND = "mb skill link --repo . --plugin"  # the in-repo form
PLUGIN_SWITCH_NOTE = (
    "For a person to run at a terminal, not an agent: switches this repo to the "
    "Main Branch plugin rail by writing the tracked `.claude/settings.json`. "
    "Restart Claude Code afterwards."
)


def repo_flag(repo: str | Path | None) -> str:
    """` --repo <path>` for a command a person may paste, shell-quoted (#1072).

    The one rule every suggested command follows: the absolute repo path,
    omitted only when the repo is the current directory (or none is known).
    """
    if repo is None:
        return ""
    target = Path(repo).expanduser().resolve()
    try:
        here: Path | None = Path.cwd().resolve()
    except OSError:
        here = None
    return "" if target == here else f" --repo {shlex.quote(str(target))}"


def operator_action(command: str, changes: list[str], note: str) -> dict[str, Any]:
    """One `operator_actions` entry: a tracked-file write for a person to run."""
    return {"command": command, "changes": list(changes), "note": note}


def plugin_switch_operator_action(repo: str | Path | None = None) -> dict[str, Any]:
    """The `operator_actions` entry for a repo still on symlink-only wiring.

    The command names the business repo (#1072), so it acts on that repo from
    any folder; it keeps `--repo .` only when no repo is known.
    """
    command = PLUGIN_SWITCH_COMMAND if repo is None else f"mb skill link{repo_flag(repo)} --plugin"
    return operator_action(command, [".claude/settings.json"], PLUGIN_SWITCH_NOTE)


def write_plugin_wiring(repo: str | Path) -> dict[str, Any]:
    """Write the worktree-durable plugin wiring into tracked settings.

    Merges two keys into `.claude/settings.json` (created if absent),
    preserving everything else in the file. Idempotent.
    """
    target = Path(repo).resolve()
    path = _tracked_settings_path(target)
    # Never clobber a hand-edited-but-broken settings file. `_read_settings`
    # returns {} for BOTH "absent" and "unparseable"; writing from {} on the
    # unparseable case would silently destroy the operator's other keys
    # (permissions, hooks, ...). Refuse and report instead.
    if path.exists():
        raw = path.read_text(encoding="utf-8")
        if raw.strip():
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                return {
                    "ok": False,
                    "changed": False,
                    "settings_path": str(path),
                    "wiring": plugin_wiring_status(target),
                    "summary": (
                        f".claude/settings.json is not valid JSON ({exc.msg}); refused "
                        "to write plugin wiring to avoid clobbering your settings — fix "
                        "the JSON, then re-run."
                    ),
                }
            if not isinstance(parsed, dict):
                return {
                    "ok": False,
                    "changed": False,
                    "settings_path": str(path),
                    "wiring": plugin_wiring_status(target),
                    "summary": (
                        ".claude/settings.json must be a JSON object; refused to write "
                        "plugin wiring to avoid clobbering your settings."
                    ),
                }
    settings = _read_settings(path, strict=True)
    before = plugin_wiring_status(target)
    marketplaces = settings.setdefault("extraKnownMarketplaces", {})
    if not isinstance(marketplaces, dict):
        marketplaces = {}
        settings["extraKnownMarketplaces"] = marketplaces
    marketplaces[PLUGIN_MARKETPLACE_NAME] = {"source": {"source": "github", "repo": PLUGIN_REPO}}
    enabled = settings.setdefault("enabledPlugins", {})
    if not isinstance(enabled, dict):
        enabled = {}
        settings["enabledPlugins"] = enabled
    enabled[PLUGIN_ENABLE_KEY] = True
    atomic_write_json(path, settings)
    after = plugin_wiring_status(target)
    return {
        "ok": after["wired"],
        "changed": before != after,
        "settings_path": str(path),
        "wiring": after,
        "summary": (
            "plugin wiring written to tracked settings — skill discovery now "
            "survives fresh worktrees (restart or /reload-plugins to pick up)"
            if after["wired"]
            else "plugin wiring write did not verify; inspect .claude/settings.json"
        ),
    }
