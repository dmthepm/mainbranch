"""``mb update`` install-mode contract tests."""

from __future__ import annotations

import errno
import json
import os
import shlex
import shutil
import subprocess
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import __version__, claude_guidance
from mb import codex as codex_mod
from mb import engine as engine_mod
from mb import freshness as freshness_mod
from mb import unreadable as unreadable_mod
from mb import update as update_mod
from mb.cli import app

runner = CliRunner()

# Captured before the autouse stub below replaces it, so the fixture-repo
# tests can run doctor's real Codex checks.
_REAL_CODEX_READINESS = codex_mod.readiness


@pytest.fixture(autouse=True)
def codex_adapter_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        codex_mod,
        "readiness",
        lambda repo: {
            "ok": True,
            "status": "ready",
            "static_ok": True,
            "runtime_ok": True,
            "plugin_ok": True,
            "command_surface_ok": True,
            "slash_commands_ready": True,
            "repair": "",
            "instructions": {
                "ok": True,
                "exists": True,
                "current": True,
                "repair_command": "",
            },
            "plugin_install": {
                "ok": True,
                "state": "ok",
                "plugin_installed": True,
                "plugin_enabled": True,
                "command_files_current": True,
                "command_surface_ok": True,
                "slash_commands_ready": True,
                "slash_commands_likely_loaded": False,
                "slash_commands_restart_required": False,
                "repair": "",
            },
        },
    )


@pytest.fixture(autouse=True)
def plugin_rail_wired(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default: repo is already on the plugin rail, so the #931 follow-up stays
    # quiet. Tests that exercise the symlink-era path override this.
    monkeypatch.setattr(
        update_mod,
        "plugin_wiring_status",
        lambda repo: {
            "wired": True,
            "marketplace_known": True,
            "plugin_enabled": True,
            "settings_path": str(Path(repo) / ".claude" / "settings.json"),
        },
    )
    monkeypatch.setattr(
        update_mod,
        "claude_mainbranch_plugin_status",
        lambda *, expected_version=None, timeout=5.0: {
            "checked": True,
            "ok": True,
            "state": "current",
            "expected_version": expected_version or __version__,
            "installed_version": expected_version or __version__,
            "installed_versions": [expected_version or __version__],
            "enabled_versions": [expected_version or __version__],
            "entries": [],
            "command": "claude plugin list --json",
            "repair": engine_mod.PLUGIN_INSTALL_COMMAND,
            "summary": "Main Branch Claude Code plugin is enabled.",
        },
    )


# Captured before the autouse stub below replaces it, so the probe itself can
# still be unit tested.
_REAL_UV_TOOL_DIR_HOLDS_THIS_INSTALL = update_mod._uv_tool_dir_holds_this_install


@pytest.fixture(autouse=True)
def uv_tool_dir_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    # `mb update` asks uv for its tool directory when path detection is
    # inconclusive. Tests must never read the developer's or CI runner's uv.
    monkeypatch.setattr(update_mod, "_uv_tool_dir_holds_this_install", lambda: False)


@pytest.fixture(autouse=True)
def pypi_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    # Every install mode now asks PyPI whether this build is ahead of the latest
    # release (#1022). Tests that care set their own answer; the rest stay off
    # the network and see a lookup that worked and matches this build. A failed
    # lookup (None) leaves the install alone, so tests of that path set it.
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: __version__)


def _completed(
    args: list[str],
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=args,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


INSTALLER_PREFIXES = (["uv", "tool", "install"], ["uv", "tool", "upgrade"], ["pipx", "upgrade"])


def _installer_calls(calls: list[list[str]]) -> list[list[str]]:
    """Every recorded call that would have replaced an install."""
    return [
        args
        for args in calls
        if any(args[: len(prefix)] == prefix for prefix in INSTALLER_PREFIXES)
    ]


def _surface_refresh_runner(
    calls: list[list[str]],
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Fake runner that satisfies the surface refresh and records everything."""

    def fake_run(
        args: list[str], *, cwd: Path | None = None, timeout: float = 0.0
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[:3] == ["mb", "skill", "link"]:
            return _completed(
                args, stdout=json.dumps({"ok": True, "linked": ["mb-start"], "tracked_changes": []})
            )
        if args[:3] == ["mb", "doctor", "repair"]:
            return _codex_repair_completed(args)
        if args[1:] == ["--version"]:
            return _completed(args, stdout="mb 9.9.9\n")
        return _completed(args)

    return fake_run


def _codex_repair_completed(args: list[str]) -> subprocess.CompletedProcess[str]:
    return _completed(
        args,
        stdout=json.dumps(
            {
                "ok": True,
                "warnings": [],
                "errors": [],
                "actions": [],
                "applied_actions": [],
            }
        ),
    )


def test_run_command_returns_124_on_timeout(monkeypatch: Any) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr("mb.update.subprocess.run", fake_run)

    result = update_mod._run_command(["git", "fetch"], timeout=0.01)

    assert result.returncode == 124
    assert "timed out after" in result.stderr


def test_version_from_mb_command_uses_running_entrypoint(monkeypatch: Any, tmp_path: Path) -> None:
    mb = tmp_path / "mb"
    mb.write_text("#!/bin/sh\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return _completed(args, stdout="mb 0.5.0\n")

    monkeypatch.setattr("mb.update.sys.argv", [str(mb), "update"])
    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    assert update_mod._version_from_mb_command() == "0.5.0"
    assert calls == [[str(mb), "--version"]]


def test_update_check_pipx_does_not_run_commands(monkeypatch: Any, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return _completed(args)

    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(
        update_mod,
        "_release_context",
        lambda version: {
            "version": version,
            "tag": f"oe-v{version}",
            "url": f"https://github.com/noontide-co/mainbranch/releases/tag/oe-v{version}",
            "name": f"Main Branch {version}",
            "published_at": "2026-05-15T00:00:00Z",
            "summary": "Test release summary.",
            "available": True,
            "source": "github_release",
        },
    )
    monkeypatch.setattr(update_mod, "bundled_skills", lambda: ["mb-start", "mb-update"])
    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    result = update_mod.run(repo=tmp_path / "biz", check=True)

    assert result["ok"] is True
    assert result["old_version"] == __version__
    assert result["new_version"] == "9.9.9"
    assert result["skills_relinked_count"] == 2
    assert result["planned_skills_relink_count"] == 2
    assert result["release"]["url"].endswith("/oe-v9.9.9")
    assert result["release"]["summary"] == "Test release summary."
    assert calls == []


def test_update_check_exposes_surface_refresh_plan(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(update_mod, "bundled_skills", lambda: ["mb-start", "mb-status"])

    result = update_mod.run(repo=tmp_path / "biz", check=True)

    assert result["refresh_surfaces"] is True
    assert result["surface_refresh"]["enabled"] is True
    assert result["surface_refresh"]["claude"]["skill_count"] == 2
    assert result["surface_refresh"]["claude"]["command"].startswith("mb skill link")
    assert "--only codex" in result["surface_refresh"]["codex"]["command"]
    assert any("would run `mb skill link" in action for action in result["actions"])
    assert any("would run `mb doctor repair" in action for action in result["actions"])


def test_update_can_skip_surface_refresh_explicitly(monkeypatch: Any, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args == ["pipx", "upgrade", "mainbranch"]:
            return _completed(args, stdout="upgraded package mainbranch")
        if args == ["mb", "--version"]:
            return _completed(args, stdout="mb 0.2.0\n")
        return _completed(args, returncode=1, stderr="unexpected")

    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(
        update_mod.shutil,  # type: ignore[attr-defined]
        "which",
        lambda name: "/opt/homebrew/bin/pipx",
    )
    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    result = update_mod.run(repo=tmp_path / "biz", refresh_surfaces=False)

    assert result["ok"] is True
    assert result["refresh_surfaces"] is False
    assert result["surface_refresh"]["skipped"] == ["claude", "codex"]
    assert "skipped agent surface refresh" in result["actions"]
    assert calls == [["pipx", "upgrade", "mainbranch"], ["mb", "--version"]]


def test_update_cli_accepts_no_refresh_surfaces(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(
        update_mod.shutil,  # type: ignore[attr-defined]
        "which",
        lambda name: "/opt/homebrew/bin/pipx",
    )
    monkeypatch.setattr(
        update_mod,
        "_run_command",
        lambda args, cwd=None: (
            _completed(args, stdout="mb 0.2.0\n")
            if args == ["mb", "--version"]
            else _completed(args, stdout="upgraded package mainbranch")
        ),
    )

    result = runner.invoke(
        app,
        ["update", "--repo", str(tmp_path / "biz"), "--no-refresh-surfaces", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["refresh_surfaces"] is False
    assert payload["surface_refresh"]["skipped"] == ["claude", "codex"]


def test_update_pipx_runs_upgrade_then_relinks(monkeypatch: Any, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args == ["pipx", "upgrade", "mainbranch"]:
            return _completed(args, stdout="upgraded package mainbranch")
        if args == ["mb", "--version"]:
            return _completed(args, stdout="mb 0.2.0\n")
        if args[:3] == ["mb", "skill", "link"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "linked": [".claude/skills/mb-start"],
                        "copied": [],
                        "skipped": [".claude/skills/mb-update"],
                        "errors": [],
                        "tracked_changes": [],
                    }
                ),
            )
        if args[:3] == ["mb", "doctor", "repair"]:
            return _codex_repair_completed(args)
        return _completed(args, returncode=1, stderr="unexpected")

    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(
        update_mod.shutil,  # type: ignore[attr-defined]
        "which",
        lambda name: "/opt/homebrew/bin/pipx",
    )
    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    repo = tmp_path / "biz"
    result = update_mod.run(repo=repo)

    assert result["ok"] is True
    assert result["new_version"] == "0.2.0"
    assert result["skills_relinked_count"] == 1
    assert result["warnings"] == [
        "could not refresh existing non-link skill path(s): .claude/skills/mb-update"
    ]
    assert calls == [
        ["pipx", "upgrade", "mainbranch"],
        ["mb", "--version"],
        ["mb", "skill", "link", "--repo", str(repo.resolve()), "--plan", "--json"],
        [
            "mb",
            "doctor",
            "repair",
            "--repo",
            str(repo.resolve()),
            "--plan",
            "--only",
            "codex",
            "--json",
        ],
        ["mb", "skill", "link", "--repo", str(repo.resolve()), "--json"],
        [
            "mb",
            "doctor",
            "repair",
            "--repo",
            str(repo.resolve()),
            "--apply",
            "--only",
            "codex",
            "--json",
        ],
    ]
    assert result["codex_repaired"] is True


def test_update_points_to_scoped_codex_repair_when_adapter_missing(
    monkeypatch: Any, tmp_path: Path
) -> None:
    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        if args == ["pipx", "upgrade", "mainbranch"]:
            return _completed(args, stdout="upgraded package mainbranch")
        if args == ["mb", "--version"]:
            return _completed(args, stdout="mb 0.3.29\n")
        if args[:3] == ["mb", "skill", "link"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "linked": [],
                        "copied": [],
                        "skipped": [],
                        "errors": [],
                        "tracked_changes": [],
                    }
                ),
            )
        if args[:3] == ["mb", "doctor", "repair"]:
            return _codex_repair_completed(args)
        return _completed(args, returncode=1, stderr="unexpected")

    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(
        update_mod.shutil,  # type: ignore[attr-defined]
        "which",
        lambda name: "/opt/homebrew/bin/pipx",
    )
    monkeypatch.setattr(update_mod, "_run_command", fake_run)
    monkeypatch.setattr(
        codex_mod,
        "readiness",
        lambda repo: {
            "ok": False,
            "status": "needs_setup",
            "static_ok": False,
            "runtime_ok": True,
            "plugin_ok": False,
            "repair": "mb doctor repair --apply --only codex",
            "instructions": {
                "ok": False,
                "exists": False,
                "current": False,
                "repair_command": "mb doctor repair --apply --only codex",
            },
            "plugin_install": {
                "ok": False,
                "state": "waiting_for_adapter_files",
                "plugin_installed": False,
                "plugin_enabled": False,
                "slash_commands_ready": False,
                "repair": "mb doctor repair --apply --only codex",
            },
        },
    )

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["ok"] is True
    assert result["codex_adapter"]["ok"] is False
    # #1053: every follow-up command names the repo, like the surface refresh.
    repo_flag = f"--repo {shlex.quote(str((tmp_path / 'biz').resolve()))}"
    assert f"mb doctor repair {repo_flag} --plan --only codex" in result["next_actions"]
    # #1049: the apply rewrites the tracked AGENTS.md, so a person runs it.
    assert not any("--apply" in action for action in result["next_actions"])
    codex_apply = [
        item
        for item in result["operator_actions"]
        if item["command"] == f"mb doctor repair {repo_flag} --apply --only codex"
    ]
    assert len(codex_apply) == 1
    assert "AGENTS.md" in codex_apply[0]["changes"]
    assert any(
        "Codex AGENTS.md guidance still needs repo repair" in item for item in result["warnings"]
    )


def test_update_points_to_scoped_codex_repair_when_global_skills_are_missing(
    monkeypatch: Any, tmp_path: Path
) -> None:
    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        if args == ["pipx", "upgrade", "mainbranch"]:
            return _completed(args, stdout="upgraded package mainbranch")
        if args == ["mb", "--version"]:
            return _completed(args, stdout="mb 0.3.32\n")
        if args[:3] == ["mb", "skill", "link"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "linked": [],
                        "copied": [],
                        "skipped": [],
                        "errors": [],
                        "tracked_changes": [],
                    }
                ),
            )
        if args[:3] == ["mb", "doctor", "repair"]:
            return _codex_repair_completed(args)
        return _completed(args, returncode=1, stderr="unexpected")

    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(
        update_mod.shutil,  # type: ignore[attr-defined]
        "which",
        lambda name: "/opt/homebrew/bin/pipx",
    )
    monkeypatch.setattr(update_mod, "_run_command", fake_run)
    monkeypatch.setattr(
        codex_mod,
        "readiness",
        lambda repo: {
            "ok": False,
            "status": "global_skill_missing_or_stale",
            "static_ok": True,
            "runtime_ok": True,
            "global_skill_ok": False,
            "plugin_ok": False,
            "repair": "mb doctor repair --apply --only codex",
            "instructions": {
                "ok": True,
                "exists": True,
                "current": True,
                "repair_command": "",
            },
            "global_skill": {
                "ok": False,
                "state": "global_skill_missing_or_stale",
                "repair": "mb doctor repair --apply --only codex",
            },
            "plugin_install": {
                "ok": False,
                "state": "plugin_not_installed",
                "plugin_installed": False,
                "plugin_enabled": False,
                "slash_commands_ready": False,
                "repair": f"Run `{codex_mod.CODEX_PLUGIN_INSTALL_COMMAND}`.",
            },
        },
    )

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["ok"] is True
    assert result["codex_adapter"]["status"] == "global_skill_missing_or_stale"
    assert result["codex_adapter"]["global_skill_ok"] is False
    repo_flag = f"--repo {shlex.quote(str((tmp_path / 'biz').resolve()))}"
    assert f"mb doctor repair {repo_flag} --plan --only codex" in result["next_actions"]
    # The global skill bundle is written under HOME, not the repo (#1049).
    assert f"mb doctor repair {repo_flag} --apply --only codex" in result["next_actions"]
    assert any(
        "global Main Branch Codex skills are not ready" in item for item in result["warnings"]
    )


def test_update_does_not_gate_ready_codex_on_slash_commands(
    monkeypatch: Any, tmp_path: Path
) -> None:
    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        if args == ["pipx", "upgrade", "mainbranch"]:
            return _completed(args, stdout="upgraded package mainbranch")
        if args == ["mb", "--version"]:
            return _completed(args, stdout="mb 0.3.34\n")
        if args[:3] == ["mb", "skill", "link"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "linked": [],
                        "copied": [],
                        "skipped": [],
                        "errors": [],
                        "tracked_changes": [],
                    }
                ),
            )
        if args[:3] == ["mb", "doctor", "repair"]:
            return _codex_repair_completed(args)
        return _completed(args, returncode=1, stderr="unexpected")

    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(
        update_mod.shutil,  # type: ignore[attr-defined]
        "which",
        lambda name: "/opt/homebrew/bin/pipx",
    )
    monkeypatch.setattr(update_mod, "_run_command", fake_run)
    monkeypatch.setattr(
        codex_mod,
        "readiness",
        lambda repo: {
            "ok": True,
            "status": "ready",
            "static_ok": True,
            "runtime_ok": True,
            "global_skill_ok": True,
            "plugin_ok": True,
            "generated_guidance_ready": True,
            "command_surface_ok": True,
            "slash_commands_ready": False,
            "repair": codex_mod.CODEX_REPAIR_TEXT,
            "instructions": {
                "ok": True,
                "exists": True,
                "current": True,
                "repair_command": "",
            },
            "global_skill": {
                "ok": True,
                "state": "ok",
                "repair": "",
            },
            "plugin_install": {
                "ok": True,
                "state": "ok",
                "plugin_installed": True,
                "plugin_enabled": True,
                "skill_ready": False,
                "command_files_current": False,
                "command_surface_ok": False,
                "slash_commands_ready": False,
                "repair": codex_mod.CODEX_REPAIR_TEXT,
            },
        },
    )

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["ok"] is True
    assert result["codex_adapter"]["plugin_ok"] is True
    assert result["codex_adapter"]["ok"] is True
    assert result["codex_adapter"]["slash_commands_ready"] is False
    assert "mb doctor repair --plan --only codex" not in result["next_actions"]
    assert not any("missing or stale" in item for item in result["warnings"])
    assert not any("Codex command API" in item for item in result["next_actions"])
    assert not any("Codex command API" in item for item in result["warnings"])


def test_update_surfaces_fresh_codex_thread_when_plugin_commands_were_refreshed(
    monkeypatch: Any, tmp_path: Path
) -> None:
    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        if args == ["pipx", "upgrade", "mainbranch"]:
            return _completed(args, stdout="upgraded package mainbranch")
        if args == ["mb", "--version"]:
            return _completed(args, stdout="mb 0.3.34\n")
        if args[:3] == ["mb", "skill", "link"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "linked": [],
                        "copied": [],
                        "skipped": [],
                        "errors": [],
                        "tracked_changes": [],
                    }
                ),
            )
        if args[:3] == ["mb", "doctor", "repair"]:
            return _codex_repair_completed(args)
        return _completed(args, returncode=1, stderr="unexpected")

    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(
        update_mod.shutil,  # type: ignore[attr-defined]
        "which",
        lambda name: "/opt/homebrew/bin/pipx",
    )
    monkeypatch.setattr(update_mod, "_run_command", fake_run)
    monkeypatch.setattr(
        codex_mod,
        "readiness",
        lambda repo: {
            "ok": True,
            "status": "ready",
            "static_ok": True,
            "runtime_ok": True,
            "plugin_ok": True,
            "generated_guidance_ready": True,
            "command_surface_ok": True,
            "slash_commands_ready": True,
            "repair": "",
            "instructions": {
                "ok": True,
                "exists": True,
                "current": True,
                "repair_command": "",
            },
            "plugin_install": {
                "ok": True,
                "state": "ok",
                "plugin_installed": True,
                "plugin_enabled": True,
                "skill_ready": False,
                "command_files_current": True,
                "command_surface_ok": True,
                "slash_commands_ready": True,
                "slash_commands_likely_loaded": False,
                "slash_commands_restart_required": True,
                "repair": "",
            },
        },
    )

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["ok"] is True
    assert result["codex_adapter"]["slash_commands_ready"] is True
    assert result["codex_adapter"]["slash_commands_likely_loaded"] is False
    assert result["codex_adapter"]["slash_commands_restart_required"] is True
    assert "Open a fresh Codex thread in the business repo." in result["next_actions"]
    assert any("global Main Branch skill bundle" in item for item in result["warnings"])


def test_update_check_clone_fetches_before_reading_origin(monkeypatch: Any, tmp_path: Path) -> None:
    root = tmp_path / "engine"
    (root / "mb" / "mb").mkdir(parents=True)
    (root / "mb" / "mb" / "__init__.py").write_text('__version__ = "0.1.2"\n')
    calls: list[tuple[list[str], Path | None]] = []

    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append((args, cwd))
        return _completed(args)

    monkeypatch.setattr(update_mod, "install_mode", lambda: "clone")
    monkeypatch.setattr(update_mod, "engine_root", lambda: root)
    monkeypatch.setattr(update_mod, "_run_command", fake_run)
    monkeypatch.setattr(update_mod, "_version_from_git_ref", lambda _root, _ref: "0.2.0")
    monkeypatch.setattr(update_mod, "bundled_skills", lambda: ["mb-start", "mb-status", "mb-think"])

    result = update_mod.run(repo=tmp_path / "biz", check=True)

    assert result["ok"] is True
    assert result["old_version"] == "0.1.2"
    assert result["new_version"] == "0.2.0"
    assert result["skills_relinked_count"] == 3
    assert calls == [(["git", "fetch", "origin", "main:refs/remotes/origin/main", "--quiet"], root)]
    assert "ran `git fetch origin main --quiet`" in result["actions"][0]
    assert "would run `git pull --ff-only origin main`" in result["actions"][1]
    assert result["actions"][2].endswith(" --json`")


def test_update_check_clone_reports_fetch_failure(monkeypatch: Any, tmp_path: Path) -> None:
    root = tmp_path / "engine"
    (root / "mb" / "mb").mkdir(parents=True)
    (root / "mb" / "mb" / "__init__.py").write_text('__version__ = "0.1.2"\n')

    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return _completed(args, returncode=128, stderr="no network")

    monkeypatch.setattr(update_mod, "install_mode", lambda: "clone")
    monkeypatch.setattr(update_mod, "engine_root", lambda: root)
    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    result = update_mod.run(repo=tmp_path / "biz", check=True)

    assert result["ok"] is False
    assert result["new_version"] == "0.1.2"
    assert "no network" in result["errors"][0]


def test_update_clone_pulls_engine_root_then_relinks(monkeypatch: Any, tmp_path: Path) -> None:
    root = tmp_path / "engine"
    (root / "mb" / "mb").mkdir(parents=True)
    init_file = root / "mb" / "mb" / "__init__.py"
    init_file.write_text('__version__ = "0.1.2"\n')
    calls: list[tuple[list[str], Path | None]] = []

    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append((args, cwd))
        if args == ["git", "pull", "--ff-only", "origin", "main"]:
            init_file.write_text('__version__ = "0.2.0"\n')
            return _completed(args, stdout="Already up to date.")
        if args[:3] == ["mb", "skill", "link"]:
            return _completed(
                args,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "linked": [],
                        "copied": [],
                        "skipped": [".claude/skills/mb-start"],
                        "errors": [],
                        "tracked_changes": [],
                    }
                ),
            )
        if args[:3] == ["mb", "doctor", "repair"]:
            return _codex_repair_completed(args)
        return _completed(args, returncode=1, stderr="unexpected")

    monkeypatch.setattr(update_mod, "install_mode", lambda: "clone")
    monkeypatch.setattr(update_mod, "engine_root", lambda: root)
    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["ok"] is True
    assert result["old_version"] == "0.1.2"
    assert result["new_version"] == "0.2.0"
    assert result["skills_relinked_count"] == 0
    assert result["warnings"] == [
        "could not refresh existing non-link skill path(s): .claude/skills/mb-start"
    ]
    assert calls[0] == (["git", "pull", "--ff-only", "origin", "main"], root)
    assert calls[-1][0] == [
        "mb",
        "doctor",
        "repair",
        "--repo",
        str((tmp_path / "biz").resolve()),
        "--apply",
        "--only",
        "codex",
        "--json",
    ]


def test_update_json_cli_envelope(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(
        update_mod,
        "_release_context",
        lambda version: {
            "version": version,
            "tag": f"oe-v{version}",
            "url": f"https://github.com/noontide-co/mainbranch/releases/tag/oe-v{version}",
            "name": "",
            "published_at": "",
            "summary": "Release notes from GitHub.",
            "available": True,
            "source": "github_release",
        },
    )
    monkeypatch.setattr(update_mod, "bundled_skills", lambda: ["mb-start"])

    result = runner.invoke(app, ["update", "--repo", str(tmp_path / "biz"), "--check", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["mode"] == "pipx"
    assert payload["old_version"] == __version__
    assert payload["new_version"] == "9.9.9"
    assert payload["skills_relinked_count"] == 1
    assert payload["planned_skills_relink_count"] == 1
    assert payload["release"]["summary"] == "Release notes from GitHub."
    assert payload["release"]["url"].endswith("/oe-v9.9.9")
    assert payload["errors"] == []


def test_update_check_current_release_still_exposes_notes_url(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: __version__)
    monkeypatch.setattr(update_mod, "bundled_skills", lambda: ["mb-start"])

    result = update_mod.run(repo=tmp_path / "biz", check=True)

    assert result["ok"] is True
    assert result["new_version"] == __version__
    assert result["release"]["source"] == "not_newer"
    assert result["release"]["url"].endswith(f"/oe-v{__version__}")


def test_update_rejects_unknown_install_mode(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(update_mod, "install_mode", lambda: "source")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["ok"] is False
    assert result["mode"] == "source"
    assert result["new_version"] == result["old_version"]
    assert "unsupported install mode" in result["errors"][0]


def test_update_wheel_install_gets_pip_guidance_instead_of_refusal(
    monkeypatch: Any, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(update_mod, "install_mode", lambda: "wheel")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["ok"] is True
    assert result["mode"] == "wheel"
    assert result["errors"] == []
    assert result["upgrade_performed"] is False
    assert result["manual_update_command"] == "pip install --upgrade mainbranch"
    assert "pip install --upgrade mainbranch" in result["next_actions"]
    assert _installer_calls(calls) == []


def test_update_wheel_install_still_refreshes_agent_surfaces(
    monkeypatch: Any, tmp_path: Path
) -> None:
    # Refreshing skill links needs no package upgrade. The guidance must not
    # promise a refresh that a later run would have to perform.
    calls: list[list[str]] = []

    monkeypatch.setattr(update_mod, "install_mode", lambda: "wheel")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["skills_relinked_count"] == 1
    assert result["codex_repaired"] is True
    assert any(args[:3] == ["mb", "skill", "link"] for args in calls)
    assert _installer_calls(calls) == []
    assert not any("run `mb update` again" in warning for warning in result["warnings"])


def test_update_manual_path_reports_the_version_pypi_offers(
    monkeypatch: Any, tmp_path: Path
) -> None:
    # `old == new` on a manual path would let `/mb-update` claim "already up to
    # date" on an install that is actually behind.
    monkeypatch.setattr(update_mod, "install_mode", lambda: "wheel")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner([]))

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["old_version"] == __version__
    assert result["new_version"] == "9.9.9"
    assert result["new_version"] != result["old_version"]


def test_update_manual_path_falls_back_when_pypi_is_unreachable(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.setattr(update_mod, "install_mode", lambda: "wheel")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: None)
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner([]))

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["ok"] is True
    assert result["new_version"] == result["old_version"]


def test_update_wheel_install_json_exits_zero_with_next_action(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.setattr(update_mod, "install_mode", lambda: "wheel")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner([]))

    invoked = runner.invoke(app, ["update", "--repo", str(tmp_path / "biz"), "--json"])

    assert invoked.exit_code == 0
    payload = json.loads(invoked.stdout)
    assert payload["errors"] == []
    assert "pip install --upgrade mainbranch" in payload["next_actions"]


def test_update_uv_check_names_command_without_running_installer(
    monkeypatch: Any, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return _completed(args)

    monkeypatch.setattr(update_mod, "install_mode", lambda: "uv")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(update_mod, "bundled_skills", lambda: ["mb-start"])
    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    result = update_mod.run(repo=tmp_path / "biz", check=True)

    assert result["ok"] is True
    assert result["mode"] == "uv"
    assert result["new_version"] == "9.9.9"
    assert (
        "uv tool install --refresh-package mainbranch mainbranch@latest" in result["next_actions"]
    )
    assert any(
        "would run `uv tool install --refresh-package mainbranch mainbranch@latest`" in a
        for a in result["actions"]
    )
    assert calls == []


def test_update_uv_check_json_exits_zero_with_next_action(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(update_mod, "install_mode", lambda: "uv")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")

    invoked = runner.invoke(app, ["update", "--repo", str(tmp_path / "biz"), "--check", "--json"])

    assert invoked.exit_code == 0
    payload = json.loads(invoked.stdout)
    assert payload["mode"] == "uv"
    assert payload["errors"] == []
    assert (
        "uv tool install --refresh-package mainbranch mainbranch@latest" in payload["next_actions"]
    )


def test_update_uv_non_interactive_prints_command_and_exits_zero(
    monkeypatch: Any, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def refuse_confirm(command: str, root: Path | None) -> bool:
        raise AssertionError("non-interactive update must never prompt")

    monkeypatch.setattr(update_mod, "install_mode", lambda: "uv")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr("mb.update.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    result = update_mod.run(repo=tmp_path / "biz", interactive=False, confirm=refuse_confirm)

    assert result["ok"] is True
    assert result["upgrade_performed"] is False
    assert result["new_version"] == "9.9.9"
    assert (
        "uv tool install --refresh-package mainbranch mainbranch@latest" in result["next_actions"]
    )
    assert _installer_calls(calls) == []
    assert result["skills_relinked_count"] == 1


def test_update_uv_json_never_prompts(monkeypatch: Any, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(update_mod, "install_mode", lambda: "uv")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr("mb.update.shutil.which", lambda name: f"/usr/bin/{name}")

    def explode(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("`--json` must never prompt")

    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))
    monkeypatch.setattr(update_mod, "_confirm_uv_update", explode)

    invoked = runner.invoke(app, ["update", "--repo", str(tmp_path / "biz"), "--json"])

    assert invoked.exit_code == 0
    payload = json.loads(invoked.stdout)
    assert payload["upgrade_performed"] is False
    assert (
        "uv tool install --refresh-package mainbranch mainbranch@latest" in payload["next_actions"]
    )
    assert _installer_calls(calls) == []


def test_update_uv_declined_prompt_leaves_install_alone(monkeypatch: Any, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    asked: list[str] = []

    def decline(command: str, root: Path | None) -> bool:
        asked.append(command)
        return False

    monkeypatch.setattr(update_mod, "install_mode", lambda: "uv")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr("mb.update.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    result = update_mod.run(repo=tmp_path / "biz", interactive=True, confirm=decline)

    assert asked == ["uv tool install --refresh-package mainbranch mainbranch@latest"]
    assert result["ok"] is True
    assert result["upgrade_performed"] is False
    assert (
        "uv tool install --refresh-package mainbranch mainbranch@latest" in result["next_actions"]
    )
    assert _installer_calls(calls) == []


def test_update_uv_accepted_prompt_runs_install_then_relinks(
    monkeypatch: Any, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[:3] == ["mb", "skill", "link"]:
            return _completed(
                args, stdout=json.dumps({"ok": True, "linked": ["mb-start"], "tracked_changes": []})
            )
        if args[:3] == ["mb", "doctor", "repair"]:
            return _codex_repair_completed(args)
        if args[1:] == ["--version"]:
            return _completed(args, stdout="mb 9.9.9\n")
        return _completed(args)

    monkeypatch.setattr(update_mod, "install_mode", lambda: "uv")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr("mb.update.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    result = update_mod.run(
        repo=tmp_path / "biz",
        interactive=True,
        confirm=lambda command, root: True,
    )

    assert result["ok"] is True
    assert result["upgrade_performed"] is True
    assert result["new_version"] == "9.9.9"
    assert [
        "uv",
        "tool",
        "install",
        "--refresh-package",
        "mainbranch",
        "mainbranch@latest",
    ] in calls
    assert result["skills_relinked_count"] == 1
    assert any(
        "ran `uv tool install --refresh-package mainbranch mainbranch@latest`" in a
        for a in result["actions"]
    )


def test_update_uv_install_failure_surfaces_command(monkeypatch: Any, tmp_path: Path) -> None:
    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return _completed(args, returncode=1, stderr="network unreachable")

    monkeypatch.setattr(update_mod, "install_mode", lambda: "uv")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr("mb.update.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    result = update_mod.run(
        repo=tmp_path / "biz",
        interactive=True,
        confirm=lambda command, root: True,
    )

    assert result["ok"] is False
    assert result["upgrade_performed"] is False
    assert "network unreachable" in result["errors"][0]
    assert (
        "uv tool install --refresh-package mainbranch mainbranch@latest" in result["next_actions"]
    )


def test_update_uv_missing_binary_returns_error(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(update_mod, "install_mode", lambda: "uv")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr("mb.update.shutil.which", lambda name: None)

    result = update_mod.run(
        repo=tmp_path / "biz",
        interactive=True,
        confirm=lambda command, root: True,
    )

    assert result["ok"] is False
    assert "`uv` is not on PATH" in result["errors"][0]
    assert (
        "uv tool install --refresh-package mainbranch mainbranch@latest" in result["next_actions"]
    )


def test_update_uses_uv_tool_dir_when_path_detection_is_inconclusive(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.setattr(update_mod, "install_mode", lambda: "wheel")
    monkeypatch.setattr(update_mod, "_uv_tool_dir_holds_this_install", lambda: True)
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")

    result = update_mod.run(repo=tmp_path / "biz", check=True)

    assert result["mode"] == "uv"
    assert (
        "uv tool install --refresh-package mainbranch mainbranch@latest" in result["next_actions"]
    )


def _uv_tool_dir_probe(
    monkeypatch: Any,
    tool_root: Path,
    engine: Path,
    interpreter: Path,
) -> bool:
    monkeypatch.setattr("mb.update.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        update_mod,
        "_run_command",
        lambda args, *, cwd=None, timeout=0.0: _completed(args, stdout=f"{tool_root}\n"),
    )
    monkeypatch.setattr(update_mod, "engine_root", lambda: engine)
    # The detector checks the running interpreter as well as the engine root,
    # so a test that models an install has to control both.
    monkeypatch.setattr("mb.engine.sys.executable", str(interpreter))
    return _REAL_UV_TOOL_DIR_HOLDS_THIS_INSTALL()


def test_uv_tool_dir_matches_an_install_under_the_reported_root(
    monkeypatch: Any, tmp_path: Path
) -> None:
    tool_root = tmp_path / "relocated" / "tools"
    engine = tool_root / "mainbranch" / "lib" / "site-packages" / "mb" / "_engine"
    interpreter = tmp_path / "uv" / "python" / "cpython-3.12" / "bin" / "python3.12"

    assert _uv_tool_dir_probe(monkeypatch, tool_root, engine, interpreter) is True


def test_uv_tool_dir_does_not_claim_an_unrelated_venv(monkeypatch: Any, tmp_path: Path) -> None:
    # The regression that `uv tool list` could not catch: this machine has a uv
    # tool install of Main Branch, but the running install is a plain
    # `pip install mainbranch` virtualenv somewhere else entirely.
    tool_root = tmp_path / "relocated" / "tools"
    (tool_root / "mainbranch").mkdir(parents=True)
    engine = tmp_path / "project" / ".venv" / "lib" / "site-packages" / "mb" / "_engine"
    interpreter = tmp_path / "project" / ".venv" / "bin" / "python3"

    assert _uv_tool_dir_probe(monkeypatch, tool_root, engine, interpreter) is False


def test_uv_tool_dir_probe_is_quiet_when_uv_is_absent(monkeypatch: Any) -> None:
    monkeypatch.setattr("mb.update.shutil.which", lambda name: None)

    assert _REAL_UV_TOOL_DIR_HOLDS_THIS_INSTALL() is False


def test_update_pipx_mode_still_upgrades_automatically(monkeypatch: Any, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[:3] == ["mb", "skill", "link"]:
            return _completed(
                args, stdout=json.dumps({"ok": True, "linked": ["mb-start"], "tracked_changes": []})
            )
        if args[:3] == ["mb", "doctor", "repair"]:
            return _codex_repair_completed(args)
        return _completed(args, stdout="mb 9.9.9\n")

    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr("mb.update.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["ok"] is True
    assert result["upgrade_performed"] is True
    assert result["manual_update_command"] == ""
    assert ["pipx", "upgrade", "mainbranch"] in calls
    assert not any(args[:2] == ["uv", "tool"] for args in calls)


def test_update_pipx_missing_binary_returns_error(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod.shutil, "which", lambda name: None)  # type: ignore[attr-defined]

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["ok"] is False
    assert result["new_version"] == result["old_version"]
    assert result["errors"] == ["pipx install mode detected, but `pipx` is not on PATH"]


def test_update_pipx_upgrade_failure_skips_relink(monkeypatch: Any, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return _completed(args, returncode=2, stderr="network down")

    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(
        update_mod.shutil,  # type: ignore[attr-defined]
        "which",
        lambda name: "/opt/homebrew/bin/pipx",
    )
    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["ok"] is False
    assert result["skills_relinked_count"] == 0
    assert calls == [["pipx", "upgrade", "mainbranch"]]
    assert "network down" in result["errors"][0]
    assert result["warnings"] == []
    assert result["next_actions"] == []


def test_update_pipx_local_wheel_parse_failure_surfaces_force_install(
    monkeypatch: Any, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return _completed(
            args,
            returncode=1,
            stderr=(
                "Unable to parse package spec: /tmp/Main Branch/dist/"
                "mainbranch-0.3.39-py3-none-any.whl"
            ),
        )

    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(
        update_mod.shutil,  # type: ignore[attr-defined]
        "which",
        lambda name: "/opt/homebrew/bin/pipx",
    )
    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["ok"] is False
    assert result["new_version"] == result["old_version"]
    assert result["skills_relinked_count"] == 0
    assert calls == [["pipx", "upgrade", "mainbranch"]]
    assert "Unable to parse package spec" in result["errors"][0]
    assert result["warnings"] == [
        "pipx could not parse the saved Main Branch install spec. This can happen "
        "after installing from a local wheel path. Approve a forced pipx reinstall "
        "to reset the saved install source."
    ]
    assert result["next_actions"] == ["pipx install --force mainbranch==9.9.9"]


def test_update_pipx_parse_failure_recovery_reuses_the_one_pypi_lookup(
    monkeypatch: Any, tmp_path: Path
) -> None:
    # One PyPI lookup per `mb update` run, including the pipx recovery path (#1028).
    lookups: list[str] = []

    def fake_latest() -> str:
        lookups.append("pypi")
        return "9.9.9"

    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return _completed(
            args,
            returncode=1,
            stderr="Unable to parse package spec: /tmp/dist/mainbranch-0.3.39-py3-none-any.whl",
        )

    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", fake_latest)
    monkeypatch.setattr("mb.update.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["next_actions"] == ["pipx install --force mainbranch==9.9.9"]
    assert lookups == ["pypi"]


def test_update_render_human_failure_prints_next_action(capsys: Any) -> None:
    update_mod.render_human(
        {
            "ok": False,
            "check": False,
            "old_version": "0.3.39",
            "new_version": "0.3.39",
            "mode": "pipx",
            "skills_relinked_count": 0,
            "errors": ["pipx upgrade mainbranch failed with exit code 1"],
            "warnings": ["Approve a forced pipx reinstall to reset the saved install source."],
            "next_actions": ["pipx install --force mainbranch==0.3.40"],
        }
    )

    output = capsys.readouterr().out

    assert "error: pipx upgrade mainbranch failed with exit code 1" in output
    assert "warning: Approve a forced pipx reinstall" in output
    assert "next: pipx install --force mainbranch==0.3.40" in output


def test_update_relink_invalid_json_is_reported(monkeypatch: Any, tmp_path: Path) -> None:
    root = tmp_path / "engine"
    (root / "mb" / "mb").mkdir(parents=True)
    (root / "mb" / "mb" / "__init__.py").write_text('__version__ = "0.1.2"\n')

    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        if args == ["git", "pull"]:
            return _completed(args)
        return _completed(args, stdout="not-json")

    monkeypatch.setattr(update_mod, "install_mode", lambda: "clone")
    monkeypatch.setattr(update_mod, "engine_root", lambda: root)
    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["ok"] is False
    assert result["skills_relinked_count"] == 0
    assert result["errors"] == ["mb skill link --plan returned invalid JSON"]


def test_update_relink_payload_errors_are_reported(monkeypatch: Any, tmp_path: Path) -> None:
    payload = {
        "ok": False,
        "linked": [],
        "copied": [".claude/skills/mb-start"],
        "skipped": [".claude/skills/mb-update"],
        "errors": ["could not locate bundled Main Branch engine root"],
    }

    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return _completed(args, stdout=json.dumps(payload))

    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    count, errors, warnings, parsed = update_mod._link_skills(tmp_path / "biz")

    assert count == 1
    assert errors == ["could not locate bundled Main Branch engine root"]
    assert warnings == [
        "could not refresh existing non-link skill path(s): .claude/skills/mb-update"
    ]
    assert parsed == payload


def test_update_render_human_check_and_error(capsys: Any) -> None:
    update_mod.render_human(
        {
            "check": True,
            "mode": "clone",
            "old_version": "0.1.2",
            "new_version": "0.2.0",
            "skills_relinked_count": 3,
            "release": {
                "url": "https://github.com/noontide-co/mainbranch/releases/tag/oe-v0.2.0",
                "summary": "Release context.",
                "available": True,
            },
            "actions": ["would run `git pull`"],
            "errors": ["boom"],
            "warnings": ["careful"],
        }
    )

    output = capsys.readouterr().out

    assert "install mode: clone" in output
    assert "version: 0.1.2 -> 0.2.0" in output
    assert (
        "release notes: https://github.com/noontide-co/mainbranch/releases/tag/oe-v0.2.0" in output
    )
    assert "release summary: Release context." in output
    assert "would refresh 3 skill link(s)" in output
    assert "error: boom" in output
    assert "warning: careful" in output


def test_update_render_human_check_labels_unavailable_release_url(capsys: Any) -> None:
    update_mod.render_human(
        {
            "check": True,
            "mode": "pipx",
            "old_version": "0.1.2",
            "new_version": "0.2.0",
            "skills_relinked_count": 0,
            "release": {
                "url": "https://github.com/noontide-co/mainbranch/releases/tag/oe-v0.2.0",
                "summary": "Fallback summary should not print.",
                "available": False,
                "source": "github_release_unavailable",
            },
            "actions": [],
            "errors": [],
            "warnings": [],
        }
    )

    output = capsys.readouterr().out

    assert "release notes:" not in output
    assert (
        "expected release notes URL: https://github.com/noontide-co/mainbranch/releases/tag/oe-v0.2.0"
        in output
    )
    assert "Fallback summary should not print." not in output


def test_update_render_human_check_skips_current_release_url(capsys: Any) -> None:
    update_mod.render_human(
        {
            "check": True,
            "mode": "pipx",
            "old_version": "0.2.0",
            "new_version": "0.2.0",
            "skills_relinked_count": 0,
            "release": {
                "url": "https://github.com/noontide-co/mainbranch/releases/tag/oe-v0.2.0",
                "available": False,
                "source": "not_newer",
            },
            "actions": [],
            "errors": [],
            "warnings": [],
        }
    )

    output = capsys.readouterr().out

    assert "release notes:" not in output
    assert "expected release notes URL:" not in output


def test_update_render_human_success(capsys: Any) -> None:
    update_mod.render_human(
        {
            "ok": True,
            "check": False,
            "old_version": "0.1.2",
            "new_version": "0.2.0",
            "skills_relinked_count": 4,
            "errors": [],
        }
    )

    output = capsys.readouterr().out

    assert "updated Main Branch (0.1.2 -> 0.2.0)" in output
    assert "refreshed 4 skill link(s)" in output


def test_update_render_human_same_version_says_already_current(capsys: Any) -> None:
    # #974: a successful run that lands the version already installed did not
    # update anything, so it must not say "updated".
    update_mod.render_human(
        {
            "ok": True,
            "check": False,
            "old_version": "0.5.3",
            "new_version": "0.5.3",
            "upgrade_performed": True,
            "skills_relinked_count": 4,
            "errors": [],
        }
    )

    output = capsys.readouterr().out

    assert "Main Branch is already current (0.5.3)." in output
    assert "updated" not in output
    assert "refreshed 4 skill link(s)" in output


def _ahead_of_pypi(monkeypatch: Any, tmp_path: Path, mode: str) -> None:
    """A release-candidate build installed while PyPI's latest is the prior release."""
    monkeypatch.setattr(update_mod, "install_mode", lambda: mode)
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_engine_version", lambda root=None: "0.6.3rc1")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "0.6.2")
    monkeypatch.setattr(update_mod, "bundled_skills", lambda: ["mb-start"])
    monkeypatch.setattr("mb.update.shutil.which", lambda name: f"/usr/bin/{name}")


def _assert_ahead_of_pypi(result: dict[str, Any]) -> None:
    assert result["ok"] is True
    assert result["old_version"] == "0.6.3rc1"
    assert result["new_version"] == "0.6.3rc1"
    assert result["latest_version"] == "0.6.2"
    assert result["installed_ahead_of_latest"] is True
    assert result["upgrade_performed"] is False
    assert result["manual_update_command"] == ""
    installers = ("uv tool install", "pipx upgrade", "pipx install", "pip install")
    assert not [a for a in result["next_actions"] if a.startswith(installers)]
    assert any("newer than PyPI's latest release (0.6.2)" in w for w in result["warnings"])


@pytest.mark.parametrize("mode", ["uv", "wheel", "pipx"])
def test_update_check_json_ahead_of_pypi_lists_no_install_command(
    monkeypatch: Any, tmp_path: Path, mode: str
) -> None:
    # #1022: a pre-release or local build newer than PyPI must not be offered
    # an install command that would downgrade it.
    calls: list[list[str]] = []
    _ahead_of_pypi(monkeypatch, tmp_path, mode)
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    cli = runner.invoke(app, ["update", "--repo", str(tmp_path / "biz"), "--check", "--json"])

    assert cli.exit_code == 0
    payload = json.loads(cli.stdout)
    _assert_ahead_of_pypi(payload)
    assert payload["release"]["source"] == "not_newer"
    assert _installer_calls(calls) == []


@pytest.mark.parametrize("mode", ["uv", "wheel", "pipx"])
def test_update_run_ahead_of_pypi_runs_no_installer(
    monkeypatch: Any, tmp_path: Path, mode: str, capsys: Any
) -> None:
    calls: list[list[str]] = []
    _ahead_of_pypi(monkeypatch, tmp_path, mode)
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    def never_prompt(command: str, root: Path | None) -> bool:
        raise AssertionError("must not offer to install an older release")

    result = update_mod.run(repo=tmp_path / "biz", interactive=True, confirm=never_prompt)

    _assert_ahead_of_pypi(result)
    assert _installer_calls(calls) == []
    assert result["skills_relinked_count"] == 1

    update_mod.render_human(result)
    output = capsys.readouterr().out
    assert "Main Branch 0.6.3rc1 is newer than PyPI's latest release (0.6.2)" in output
    assert "updated" not in output


def test_update_check_human_ahead_of_pypi(monkeypatch: Any, tmp_path: Path) -> None:
    _ahead_of_pypi(monkeypatch, tmp_path, "uv")
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner([]))

    cli = runner.invoke(app, ["update", "--repo", str(tmp_path / "biz"), "--check"])

    assert cli.exit_code == 0
    assert "version: 0.6.3rc1 (newer than PyPI's latest, 0.6.2)" in cli.stdout
    assert "next: uv tool install" not in cli.stdout


def test_update_dev_build_of_published_release_is_behind_pypi(
    monkeypatch: Any, tmp_path: Path
) -> None:
    # Versions compare by PEP 440, not by their numeric parts: 0.6.3.dev0
    # sorts before 0.6.3, so the published release is still an upgrade.
    _ahead_of_pypi(monkeypatch, tmp_path, "uv")
    monkeypatch.setattr(update_mod, "_engine_version", lambda root=None: "0.6.3.dev0")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "0.6.3")

    result = update_mod.run(repo=tmp_path / "biz", check=True)

    assert result["installed_ahead_of_latest"] is False
    assert result["new_version"] == "0.6.3"
    assert result["manual_update_command"] == update_mod.UV_UPDATE_COMMAND_TEXT
    assert update_mod.UV_UPDATE_COMMAND_TEXT in result["next_actions"]


# Installed and PyPI versions for each relation the #1036 matrix covers.
_RELATIONS = {
    "current": ("0.6.3", "0.6.3"),
    "behind": ("0.6.2", "0.6.3"),
    "ahead": ("0.6.4rc1", "0.6.3"),
}
_INSTALLER_TEXT = ("uv tool install", "pipx upgrade", "pipx install", "pip install")


def _installed_against_pypi(
    monkeypatch: Any, tmp_path: Path, mode: str, installed: str, latest: str
) -> None:
    monkeypatch.setattr(update_mod, "install_mode", lambda: mode)
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_engine_version", lambda root=None: installed)
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: latest)
    monkeypatch.setattr(update_mod, "_version_from_mb_command", lambda: latest)
    monkeypatch.setattr(update_mod, "bundled_skills", lambda: ["mb-start"])
    monkeypatch.setattr("mb.update.shutil.which", lambda name: f"/usr/bin/{name}")


def _install_commands(result: dict[str, Any]) -> list[str]:
    return [a for a in result["next_actions"] if a.startswith(_INSTALLER_TEXT)]


@pytest.mark.parametrize("mode", ["uv", "wheel"])
def test_update_check_already_current_names_no_install_command(
    monkeypatch: Any, tmp_path: Path, mode: str
) -> None:
    # #1036: a uv or wheel install that already runs PyPI's latest needs no
    # reinstall, so neither the JSON nor the human check offers one.
    calls: list[list[str]] = []
    _installed_against_pypi(monkeypatch, tmp_path, mode, "0.6.3", "0.6.3")
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    cli = runner.invoke(app, ["update", "--repo", str(tmp_path / "biz"), "--check", "--json"])
    human = runner.invoke(app, ["update", "--repo", str(tmp_path / "biz"), "--check"])

    assert cli.exit_code == 0
    payload = json.loads(cli.stdout)
    assert payload["ok"] is True
    assert payload["old_version"] == "0.6.3"
    assert payload["new_version"] == "0.6.3"
    assert payload["latest_version"] == "0.6.3"
    assert payload["installed_ahead_of_latest"] is False
    assert payload["latest_version_unknown"] is False
    assert payload["manual_update_command"] == ""
    assert _install_commands(payload) == []
    assert payload["warnings"] == []
    assert payload["release"]["source"] == "not_newer"
    assert human.exit_code == 0
    assert "Main Branch is already current (0.6.3)." in human.stdout
    assert "0.6.3 -> 0.6.3" not in human.stdout
    assert "uv tool install" not in human.stdout
    assert "pip install" not in human.stdout
    assert _installer_calls(calls) == []


@pytest.mark.parametrize("mode", ["uv", "wheel"])
def test_update_run_already_current_runs_and_asks_nothing(
    monkeypatch: Any, tmp_path: Path, mode: str, capsys: Any
) -> None:
    calls: list[list[str]] = []
    _installed_against_pypi(monkeypatch, tmp_path, mode, "0.6.3", "0.6.3")
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    def never_prompt(command: str, root: Path | None) -> bool:
        raise AssertionError("must not offer to reinstall the version already installed")

    result = update_mod.run(repo=tmp_path / "biz", interactive=True, confirm=never_prompt)

    assert result["ok"] is True
    assert result["new_version"] == "0.6.3"
    assert result["upgrade_performed"] is False
    assert result["manual_update_command"] == ""
    assert _install_commands(result) == []
    assert result["warnings"] == []
    assert result["skills_relinked_count"] == 1
    assert _installer_calls(calls) == []

    update_mod.render_human(result)
    output = capsys.readouterr().out
    assert "Main Branch is already current (0.6.3)." in output
    assert "did not upgrade" not in output
    assert "next: uv tool install" not in output
    assert "next: pip install" not in output


@pytest.mark.parametrize("mode", ["uv", "wheel"])
def test_update_cli_json_already_current_names_no_install_command(
    monkeypatch: Any, tmp_path: Path, mode: str
) -> None:
    calls: list[list[str]] = []
    _installed_against_pypi(monkeypatch, tmp_path, mode, "0.6.3", "0.6.3")
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    cli = runner.invoke(app, ["update", "--repo", str(tmp_path / "biz"), "--json"])

    assert cli.exit_code == 0
    payload = json.loads(cli.stdout)
    assert payload["new_version"] == "0.6.3"
    assert payload["manual_update_command"] == ""
    assert _install_commands(payload) == []
    assert payload["warnings"] == []
    assert _installer_calls(calls) == []


_EXPECTED_CHECK_COMMAND = {
    ("uv", "behind"): update_mod.UV_UPDATE_COMMAND_TEXT,
    ("wheel", "behind"): update_mod.PIP_UPDATE_COMMAND_TEXT,
}


@pytest.mark.parametrize("relation", ["current", "behind", "ahead"])
@pytest.mark.parametrize("mode", ["uv", "wheel", "pipx"])
def test_update_check_install_command_by_mode_and_relation(
    monkeypatch: Any, tmp_path: Path, mode: str, relation: str
) -> None:
    # Only a behind uv or wheel install is handed a command. pipx keeps its
    # "would run" action whenever it is not ahead, as before #1036.
    installed, latest = _RELATIONS[relation]
    _installed_against_pypi(monkeypatch, tmp_path, mode, installed, latest)
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner([]))

    result = update_mod.run(repo=tmp_path / "biz", check=True)

    command = _EXPECTED_CHECK_COMMAND.get((mode, relation), "")
    assert result["manual_update_command"] == command
    assert _install_commands(result) == ([command] if command else [])
    assert result["installed_ahead_of_latest"] is (relation == "ahead")
    assert result["new_version"] == (latest if relation == "behind" else installed)
    pipx_action = f"would run `{update_mod.PIPX_UPDATE_COMMAND_TEXT}`"
    assert (pipx_action in result["actions"]) is (mode == "pipx" and relation != "ahead")


@pytest.mark.parametrize("relation", ["current", "behind", "ahead"])
@pytest.mark.parametrize("mode", ["uv", "wheel", "pipx"])
def test_update_run_installer_by_mode_and_relation(
    monkeypatch: Any, tmp_path: Path, mode: str, relation: str
) -> None:
    # Interactive run: a behind uv install is asked once and installs on yes;
    # a current or ahead one is never asked. pipx upgrades unless ahead. A
    # wheel install never runs an installer.
    calls: list[list[str]] = []
    prompts: list[str] = []
    installed, latest = _RELATIONS[relation]
    _installed_against_pypi(monkeypatch, tmp_path, mode, installed, latest)
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    def confirm(command: str, root: Path | None) -> bool:
        prompts.append(command)
        return True

    result = update_mod.run(repo=tmp_path / "biz", interactive=True, confirm=confirm)

    expected_installs = {
        ("uv", "behind"): [update_mod.UV_UPDATE_COMMAND],
        ("pipx", "behind"): [["pipx", "upgrade", "mainbranch"]],
        ("pipx", "current"): [["pipx", "upgrade", "mainbranch"]],
    }.get((mode, relation), [])
    assert result["ok"] is True
    assert _installer_calls(calls) == expected_installs
    assert prompts == (
        [update_mod.UV_UPDATE_COMMAND_TEXT] if (mode, relation) == ("uv", "behind") else []
    )
    expected_manual = (
        update_mod.PIP_UPDATE_COMMAND_TEXT if (mode, relation) == ("wheel", "behind") else ""
    )
    assert result["manual_update_command"] == expected_manual


def _rc_sees_release(monkeypatch: Any, tmp_path: Path, installed: str, latest: str) -> list[str]:
    looked_up: list[str] = []

    def release_context(version: str) -> dict[str, Any]:
        looked_up.append(version)
        return {
            "version": version,
            "tag": f"oe-v{version}",
            "url": f"https://github.com/noontide-co/mainbranch/releases/tag/oe-v{version}",
            "name": f"Main Branch {version}",
            "published_at": "2026-10-01T00:00:00Z",
            "summary": "Test release summary.",
            "available": True,
            "source": "github_release",
        }

    _installed_against_pypi(monkeypatch, tmp_path, "uv", installed, latest)
    monkeypatch.setattr(update_mod, "_release_context", release_context)
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner([]))
    return looked_up


def test_update_check_rc_install_gets_final_release_context(
    monkeypatch: Any, tmp_path: Path
) -> None:
    # #1039: 0.6.3 is newer than 0.6.3rc1 under PEP 440, so the check reads the
    # final release's notes instead of reporting it as not newer.
    looked_up = _rc_sees_release(monkeypatch, tmp_path, "0.6.3rc1", "0.6.3")

    result = update_mod.run(repo=tmp_path / "biz", check=True)

    assert looked_up == ["0.6.3"]
    assert result["new_version"] == "0.6.3"
    assert result["release"]["source"] == "github_release"
    assert result["release"]["summary"] == "Test release summary."
    assert result["manual_update_command"] == update_mod.UV_UPDATE_COMMAND_TEXT


def test_update_check_final_install_gets_no_release_context_for_same_release(
    monkeypatch: Any, tmp_path: Path
) -> None:
    looked_up = _rc_sees_release(monkeypatch, tmp_path, "0.6.3", "0.6.3")

    result = update_mod.run(repo=tmp_path / "biz", check=True)

    assert looked_up == []
    assert result["release"]["source"] == "not_newer"


class _PyPIResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def __enter__(self) -> _PyPIResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


@pytest.mark.parametrize("body", ["[1, 2]", "null", "3", '"x"'])
@pytest.mark.parametrize("mode", ["uv", "pipx", "wheel"])
def test_update_with_non_object_pypi_json_reports_latest_unknown(
    monkeypatch: Any, tmp_path: Path, mode: str, body: str
) -> None:
    # #1039: valid JSON that is not an object must read as "latest unknown",
    # not stop `mb update` with a traceback.
    calls: list[list[str]] = []
    _installed_against_pypi(monkeypatch, tmp_path, mode, "0.6.3", "0.6.3")
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda url, timeout=0.0: _PyPIResponse(body),
    )
    monkeypatch.setattr(update_mod, "_latest_pypi_version", freshness_mod.latest_pypi_version)
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    cli = runner.invoke(app, ["update", "--repo", str(tmp_path / "biz"), "--json"])

    assert cli.exit_code == 0
    assert cli.exception is None
    payload = json.loads(cli.stdout)
    assert payload["latest_version_unknown"] is True
    assert payload["manual_update_command"] == ""
    assert _install_commands(payload) == []
    assert _installer_calls(calls) == []


def _latest_unknown(monkeypatch: Any, tmp_path: Path, mode: str, latest: str | None) -> None:
    """The 0.6.3 release-gate scenario: 0.6.3 installed, PyPI's answer unusable."""
    monkeypatch.setattr(update_mod, "install_mode", lambda: mode)
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_engine_version", lambda root=None: "0.6.3")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: latest)
    monkeypatch.setattr(update_mod, "_version_from_mb_command", lambda: "0.6.2")
    monkeypatch.setattr(update_mod, "bundled_skills", lambda: ["mb-start"])
    monkeypatch.setattr("mb.update.shutil.which", lambda name: f"/usr/bin/{name}")


def _assert_latest_unknown(result: dict[str, Any], *, retry: str) -> None:
    assert result["ok"] is True
    assert result["old_version"] == "0.6.3"
    assert result["new_version"] == "0.6.3"
    assert result["latest_version"] == ""
    assert result["latest_version_unknown"] is True
    assert result["installed_ahead_of_latest"] is False
    assert result["upgrade_performed"] is False
    assert result["manual_update_command"] == ""
    installers = ("uv tool install", "pipx upgrade", "pipx install", "pip install")
    assert not [a for a in result["next_actions"] if a.startswith(installers)]
    assert retry in result["next_actions"]
    assert any("could not check PyPI for the latest version" in w for w in result["warnings"])


@pytest.mark.parametrize("latest", [None, "", "not-a-version", "<html>"])
@pytest.mark.parametrize("mode", ["uv", "pipx", "wheel"])
def test_update_run_with_unknown_latest_runs_no_installer(
    monkeypatch: Any, tmp_path: Path, mode: str, latest: str | None, capsys: Any
) -> None:
    # A failed or unusable PyPI lookup is not permission to install: `@latest`
    # could be older than the installed build.
    calls: list[list[str]] = []
    _latest_unknown(monkeypatch, tmp_path, mode, latest)
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    def never_prompt(command: str, root: Path | None) -> bool:
        raise AssertionError("must not offer an install when freshness is unknown")

    result = update_mod.run(repo=tmp_path / "biz", interactive=True, confirm=never_prompt)

    _assert_latest_unknown(result, retry=update_mod._update_command(tmp_path / "biz"))
    assert _installer_calls(calls) == []
    assert result["skills_relinked_count"] == 1

    update_mod.render_human(result)
    output = capsys.readouterr().out
    assert (
        "Main Branch 0.6.3 was not changed; PyPI's latest version could not be checked." in output
    )
    assert "updated" not in output
    assert "already current" not in output


@pytest.mark.parametrize("mode", ["uv", "pipx", "wheel"])
def test_update_cli_json_with_unknown_latest_exits_zero(
    monkeypatch: Any, tmp_path: Path, mode: str
) -> None:
    calls: list[list[str]] = []
    _latest_unknown(monkeypatch, tmp_path, mode, None)
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    cli = runner.invoke(app, ["update", "--repo", str(tmp_path / "biz"), "--json"])

    assert cli.exit_code == 0
    _assert_latest_unknown(
        json.loads(cli.stdout), retry=update_mod._update_command(tmp_path / "biz")
    )
    assert _installer_calls(calls) == []


@pytest.mark.parametrize("mode", ["uv", "pipx", "wheel"])
def test_update_check_with_unknown_latest_lists_no_install_command(
    monkeypatch: Any, tmp_path: Path, mode: str
) -> None:
    calls: list[list[str]] = []
    _latest_unknown(monkeypatch, tmp_path, mode, None)
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    cli = runner.invoke(app, ["update", "--repo", str(tmp_path / "biz"), "--check", "--json"])
    human = runner.invoke(app, ["update", "--repo", str(tmp_path / "biz"), "--check"])

    assert cli.exit_code == 0
    payload = json.loads(cli.stdout)
    _assert_latest_unknown(payload, retry=update_mod._update_command(tmp_path / "biz", check=True))
    assert payload["release"]["source"] == "not_newer"
    assert human.exit_code == 0
    assert "version: 0.6.3 (PyPI's latest version could not be checked)" in human.stdout
    assert "next: uv tool install" not in human.stdout
    assert "next: pip install" not in human.stdout
    assert _installer_calls(calls) == []


@pytest.mark.parametrize(
    ("mode", "installer"),
    [
        ("uv", update_mod.UV_UPDATE_COMMAND),
        ("pipx", ["pipx", "upgrade", "mainbranch"]),
    ],
)
def test_update_older_install_with_known_latest_still_upgrades(
    monkeypatch: Any, tmp_path: Path, mode: str, installer: list[str]
) -> None:
    # The guard only fires on unknown freshness; a normal upgrade still runs.
    calls: list[list[str]] = []
    _latest_unknown(monkeypatch, tmp_path, mode, "0.6.4")
    monkeypatch.setattr(update_mod, "_version_from_mb_command", lambda: "0.6.4")
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    result = update_mod.run(repo=tmp_path / "biz", interactive=True, confirm=lambda *a: True)

    assert result["ok"] is True
    assert result["latest_version_unknown"] is False
    assert _installer_calls(calls) == [installer]
    assert result["upgrade_performed"] is True
    assert result["new_version"] == "0.6.4"


def test_update_reports_plugin_rail_wired_without_warning(monkeypatch: Any, tmp_path: Path) -> None:
    # Default fixture: repo already on the plugin rail -> no migration warning.
    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(update_mod, "bundled_skills", lambda: ["mb-start", "mb-status"])

    result = update_mod.run(repo=tmp_path / "biz", check=True)

    assert result["plugin_rail"]["wired"] is True
    assert not any("symlink-only skill wiring" in w for w in result["warnings"])
    assert not any("--plugin" in action for action in result["next_actions"])
    assert result["operator_actions"] == []


def test_update_surfaces_plugin_migration_for_symlink_era_repo(
    monkeypatch: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # #931: a repo that predates the plugin default stays on symlinks after
    # `mb update`; the post-update follow-up names the one-command migration.
    monkeypatch.setattr(
        update_mod,
        "plugin_wiring_status",
        lambda repo: {
            "wired": False,
            "marketplace_known": False,
            "plugin_enabled": False,
            "settings_path": str(tmp_path / "biz" / ".claude" / "settings.json"),
        },
    )
    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(update_mod, "bundled_skills", lambda: ["mb-start", "mb-status"])

    result = update_mod.run(repo=tmp_path / "biz", check=True)

    assert result["plugin_rail"]["wired"] is False
    warning = next(w for w in result["warnings"] if "symlink-only skill wiring" in w)
    # #1042: the warning points to `operator_actions` and names no command an
    # agent could read as its own step.
    assert "operator_actions" in warning
    assert "mb skill link" not in warning
    assert "mb doctor repair" not in warning
    # #1023: the switch writes a tracked file, so it is a step for a person,
    # never an unattended next action an agent might run.
    assert not any("--plugin" in action for action in result["next_actions"])
    quoted = shlex.quote(str((tmp_path / "biz").resolve()))
    assert [item["command"] for item in result["operator_actions"]] == [
        f"mb skill link --repo {quoted} --plugin"
    ]
    assert result["operator_actions"][0]["changes"] == [".claude/settings.json"]

    update_mod.render_human(result)
    out = capsys.readouterr().out
    assert f"for you to run: mb skill link --repo {quoted} --plugin" in out
    assert "not an agent" in out
    assert "next: mb skill link" not in out


def test_update_warns_when_installed_claude_plugin_is_stale(
    monkeypatch: Any, tmp_path: Path
) -> None:
    def fake_run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        if args == ["pipx", "upgrade", "mainbranch"]:
            return _completed(args)
        if args == ["mb", "--version"]:
            return _completed(args, stdout="mb 0.4.2\n")
        if args[:3] == ["mb", "skill", "link"]:
            return _completed(
                args, stdout=json.dumps({"ok": True, "linked": ["mb-start"], "tracked_changes": []})
            )
        if args[:4] == ["mb", "doctor", "repair", "--repo"]:
            return _codex_repair_completed(args)
        return _completed(args)

    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(shutil, "which", lambda name: "/opt/homebrew/bin/pipx")
    monkeypatch.setattr(update_mod, "_run_command", fake_run)
    monkeypatch.setattr(
        update_mod,
        "claude_mainbranch_plugin_status",
        lambda *, expected_version=None, timeout=5.0: {
            "checked": True,
            "ok": False,
            "state": "stale",
            "expected_version": expected_version,
            "installed_version": "0.4.1",
            "installed_versions": ["0.4.1"],
            "enabled_versions": ["0.4.1"],
            "entries": [],
            "command": "claude plugin list --json",
            "repair": engine_mod.PLUGIN_INSTALL_COMMAND,
            "summary": "Main Branch Claude Code plugin is enabled at 0.4.1, expected 0.4.2.",
        },
    )

    result = update_mod.run(repo=tmp_path / "biz")

    assert result["ok"] is True
    assert result["new_version"] == "0.4.2"
    assert result["plugin_rail"]["install"]["state"] == "stale"
    assert result["plugin_rail"]["install"]["expected_version"] == "0.4.2"
    assert engine_mod.PLUGIN_INSTALL_COMMAND in result["next_actions"]
    assert any("older Main Branch plugin" in warning for warning in result["warnings"])
    assert any("/reload-plugins" in warning for warning in result["warnings"])


def test_update_check_uses_planned_version_for_plugin_status(
    monkeypatch: Any, tmp_path: Path
) -> None:
    expected_versions: list[str | None] = []

    def fake_status(*, expected_version=None, timeout=5.0) -> dict[str, Any]:
        expected_versions.append(expected_version)
        return {
            "checked": True,
            "ok": False,
            "state": "stale",
            "expected_version": expected_version,
            "installed_version": "0.4.1",
            "installed_versions": ["0.4.1"],
            "enabled_versions": ["0.4.1"],
            "entries": [],
            "command": "claude plugin list --json",
            "repair": engine_mod.PLUGIN_INSTALL_COMMAND,
            "summary": (
                f"Main Branch Claude Code plugin is enabled at 0.4.1, expected {expected_version}."
            ),
        }

    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(update_mod, "bundled_skills", lambda: ["mb-start", "mb-status"])
    monkeypatch.setattr(update_mod, "claude_mainbranch_plugin_status", fake_status)

    result = update_mod.run(repo=tmp_path / "biz", check=True)

    assert expected_versions == ["9.9.9"]
    assert result["plugin_rail"]["install"]["expected_version"] == "9.9.9"
    assert any("expects 9.9.9" in warning for warning in result["warnings"])
    assert engine_mod.PLUGIN_INSTALL_COMMAND in result["next_actions"]


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("y", True), ("Y", True), ("yes", True), ("", False), ("n", False), ("sure", False)],
)
def test_confirm_uv_update_defaults_to_no(
    monkeypatch: Any, capsys: Any, tmp_path: Path, answer: str, expected: bool
) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt="": answer)

    approved = update_mod._confirm_uv_update(
        update_mod.UV_UPDATE_COMMAND_TEXT, tmp_path / "_engine"
    )

    assert approved is expected
    out = capsys.readouterr().out
    assert "uv tool install --refresh-package mainbranch mainbranch@latest" in out
    assert str(tmp_path / "_engine") in out


def test_confirm_uv_update_treats_interrupted_input_as_no(monkeypatch: Any) -> None:
    def interrupted(prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", interrupted)

    assert update_mod._confirm_uv_update(update_mod.UV_UPDATE_COMMAND_TEXT, None) is False


def test_update_render_human_manual_path_names_the_command(capsys: Any) -> None:
    update_mod.render_human(
        {
            "ok": True,
            "check": False,
            "mode": "uv",
            "old_version": "0.5.2",
            "new_version": "0.6.0",
            "upgrade_performed": False,
            "manual_update_command": update_mod.UV_UPDATE_COMMAND_TEXT,
            "skills_relinked_count": 15,
            "next_actions": [update_mod.UV_UPDATE_COMMAND_TEXT],
            "warnings": ["Main Branch was installed as a uv tool."],
            "errors": [],
        }
    )

    output = capsys.readouterr().out
    assert "install mode: uv" in output
    assert "version: 0.5.2 -> 0.6.0" in output
    assert "Main Branch did not upgrade this install." in output
    assert "refreshed 15 skill link(s)" in output
    assert "next: uv tool install --refresh-package mainbranch mainbranch@latest" in output


def test_update_check_uv_carries_the_manual_command_like_wheel_does(
    monkeypatch: Any, tmp_path: Path
) -> None:
    # The key must not appear and disappear by install mode.
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(update_mod, "bundled_skills", lambda: ["mb-start"])

    seen = {}
    for mode, command in (
        ("uv", "uv tool install --refresh-package mainbranch mainbranch@latest"),
        ("wheel", "pip install --upgrade mainbranch"),
    ):
        monkeypatch.setattr(update_mod, "install_mode", lambda mode=mode: mode)
        seen[mode] = update_mod.run(repo=tmp_path / "biz", check=True)
        assert seen[mode]["manual_update_command"] == command
        assert seen[mode]["new_version"] == "9.9.9"

    # And `--check` may only promise a relink the real run actually performs.
    assert seen["uv"]["planned_skills_relink_count"] == 1
    assert seen["wheel"]["planned_skills_relink_count"] == 1


def test_update_check_promise_matches_what_the_real_run_does(
    monkeypatch: Any, tmp_path: Path
) -> None:
    # Finding 1: `--check` planned 15 relinks that the real run never performed.
    calls: list[list[str]] = []

    monkeypatch.setattr(update_mod, "install_mode", lambda: "uv")
    monkeypatch.setattr(update_mod, "engine_root", lambda: tmp_path / "_engine")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "9.9.9")
    monkeypatch.setattr(update_mod, "bundled_skills", lambda: ["mb-start"])
    monkeypatch.setattr("mb.update.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(update_mod, "_run_command", _surface_refresh_runner(calls))

    planned = update_mod.run(repo=tmp_path / "biz", check=True)
    actual = update_mod.run(repo=tmp_path / "biz", interactive=False)

    assert planned["planned_skills_relink_count"] == actual["skills_relinked_count"]
    assert planned["surface_refresh"]["claude"]["command"] in actual["surface_refresh"]["commands"]
    assert _installer_calls(calls) == []


# --- #1012: no tracked-file writes without an interactive terminal ---------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def business_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A committed business repo with stale AGENTS.md and a bare .gitignore."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(home / ".codex"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("MAINBRANCH_CODEX_SKILLS_ROOT", str(home / ".codex" / "skills"))
    monkeypatch.setattr(codex_mod, "readiness", _REAL_CODEX_READINESS)
    monkeypatch.setattr(engine_mod, "_personal_skills_dir", lambda: home / ".claude" / "skills")
    repo = tmp_path / "biz"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text("# Business\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text("# Old guidance\n", encoding="utf-8")
    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-q",
        "-m",
        "Start",
    )
    return repo


def _in_process_mb(calls: list[list[str]]) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Run `mb ...` subcommands against this checkout's CLI, in process."""

    def fake_run(
        args: list[str], *, cwd: Path | None = None, timeout: float = 0.0
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args and args[0] == "mb":
            invoked = runner.invoke(app, args[1:])
            stderr = repr(invoked.exception) if invoked.exception else ""
            if isinstance(invoked.exception, SystemExit):
                stderr = ""
            return _completed(
                args, stdout=invoked.stdout, stderr=stderr, returncode=invoked.exit_code
            )
        return _completed(args, returncode=1, stderr="unexpected command in test")

    return fake_run


def _wheel_update_env(monkeypatch: pytest.MonkeyPatch, calls: list[list[str]]) -> None:
    monkeypatch.setattr(update_mod, "install_mode", lambda: "wheel")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: None)
    monkeypatch.setattr(update_mod, "_run_command", _in_process_mb(calls))


def _tracked_state(repo: Path) -> tuple[str, str, str]:
    return (
        _git(repo, "status", "--porcelain"),
        (repo / "AGENTS.md").read_text(encoding="utf-8"),
        (repo / ".gitignore").read_text(encoding="utf-8"),
    )


def test_update_without_terminal_leaves_tracked_files_and_reports_plan(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    monkeypatch.setattr(update_mod, "_is_interactive_terminal", lambda: False)

    def never_ask(repo: Path, files: list[str]) -> bool:
        raise AssertionError("must not prompt without a terminal")

    monkeypatch.setattr(update_mod, "_confirm_surface_writes", never_ask, raising=False)
    before = _tracked_state(business_repo)

    result = update_mod.run(repo=business_repo)

    assert _tracked_state(business_repo) == before
    assert before[0] == ""
    assert not any("--apply" in args for args in calls)
    assert ["mb", "skill", "link", "--repo", str(business_repo), "--json"] not in calls
    assert result["ok"] is True
    planned = result["surface_refresh"]["planned"]
    assert planned["consent"] == "no_terminal"
    assert planned["tracked_files"] == [".gitignore", "AGENTS.md"]
    apply_commands = [
        f"mb skill link --repo {business_repo}",
        f"mb doctor repair --repo {business_repo} --apply --only codex",
    ]
    assert planned["apply_commands"] == apply_commands
    # #1049: the apply commands write tracked files, so they are steps for a
    # person in `operator_actions`, never unattended `next_actions`.
    for command in apply_commands:
        assert command not in result["next_actions"]
    assert not any("--apply" in action for action in result["next_actions"])
    assert f"mb doctor repair --repo {business_repo} --plan --only codex" in result["next_actions"]
    surface_actions = [
        item for item in result["operator_actions"] if item["command"] in apply_commands
    ]
    assert [item["command"] for item in surface_actions] == apply_commands
    assert [item["changes"] for item in surface_actions] == [[".gitignore"], ["AGENTS.md"]]
    for item in surface_actions:
        assert set(item) == set(engine_mod.plugin_switch_operator_action())
        assert item["note"].startswith("For a person to run at a terminal, not an agent")
    assert result["surface_refresh"]["claude"]["applied"] is False
    assert result["surface_refresh"]["claude"]["tracked_writes"] == [".gitignore"]
    assert result["surface_refresh"]["codex"]["applied"] is False
    assert result["surface_refresh"]["codex"]["tracked_writes"] == ["AGENTS.md"]
    assert result["codex_repaired"] is False
    assert any("Left repo files unchanged" in w for w in result["warnings"])


def test_update_json_never_prompts_for_tracked_files_even_at_a_terminal(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    monkeypatch.setattr(update_mod, "_is_interactive_terminal", lambda: True)

    def never_ask(repo: Path, files: list[str]) -> bool:
        raise AssertionError("--json must not prompt")

    monkeypatch.setattr(update_mod, "_confirm_surface_writes", never_ask, raising=False)
    before = _tracked_state(business_repo)

    invoked = runner.invoke(app, ["update", "--repo", str(business_repo), "--json"])

    assert invoked.exit_code == 0, invoked.stdout
    payload = json.loads(invoked.stdout)
    assert _tracked_state(business_repo) == before
    assert payload["surface_refresh"]["planned"]["consent"] == "no_terminal"
    assert payload["surface_refresh"]["planned"]["tracked_files"] == [".gitignore", "AGENTS.md"]


def test_update_terminal_no_leaves_tracked_files(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    asked: list[list[str]] = []

    def say_no(repo: Path, files: list[str]) -> bool:
        asked.append(files)
        return False

    before = _tracked_state(business_repo)

    result = update_mod.run(repo=business_repo, interactive=True, confirm_surfaces=say_no)

    assert asked == [[".gitignore", "AGENTS.md"]], result["errors"]
    assert _tracked_state(business_repo) == before
    assert result["surface_refresh"]["planned"]["consent"] == "declined"
    codex_apply = f"mb doctor repair --repo {business_repo} --apply --only codex"
    link_apply = f"mb skill link --repo {business_repo}"
    assert codex_apply not in result["next_actions"]
    assert link_apply not in result["next_actions"]
    commands = [item["command"] for item in result["operator_actions"]]
    assert link_apply in commands
    assert codex_apply in commands


def test_update_leaves_an_old_claude_md_conventions_line_alone(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    # #1119: CLAUDE.md is written once by `mb init` and belongs to the
    # operator. `mb update` refreshes AGENTS.md, .gitignore and skill links,
    # even after a yes, and never rewrites the old one-set status line.
    old = (
        "# Business\n\n## Conventions\n\n"
        "- Status field: proposed | running | scaling | killed | graduated | died.\n"
    )
    (business_repo / "CLAUDE.md").write_text(old, encoding="utf-8")
    _commit_all(business_repo, "Old conventions line")
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    asked: list[list[str]] = []

    def say_yes(repo: Path, files: list[str]) -> bool:
        asked.append(files)
        return True

    result = update_mod.run(repo=business_repo, interactive=True, confirm_surfaces=say_yes)

    assert result["ok"] is True, result["errors"]
    assert asked == [[".gitignore", "AGENTS.md"]]
    assert (business_repo / "CLAUDE.md").read_text(encoding="utf-8") == old
    changed = sorted(line[3:] for line in _git(business_repo, "status", "--porcelain").splitlines())
    assert "CLAUDE.md" not in changed


def test_update_adds_entry_rules_to_069_claude_and_keeps_operator_notes(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    from mb.init import _read_template

    template = _read_template("CLAUDE.md.tmpl")
    start = template.index(claude_guidance.BEGIN)
    end = template.index(claude_guidance.END, start) + len(claude_guidance.END)
    old = template[:start] + template[end + 2 :]
    old = "Operator preface.\n\n" + old + "\n\n## Operator notes\n\nKeep this.\n"
    (business_repo / "CLAUDE.md").write_text(old, encoding="utf-8")
    _commit_all(business_repo, "0.6.9 Claude guidance with operator notes")
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)

    no_terminal = update_mod.run(repo=business_repo, interactive=False)
    assert "CLAUDE.md" in no_terminal["surface_refresh"]["planned"]["tracked_files"]
    assert (business_repo / "CLAUDE.md").read_text(encoding="utf-8") == old

    accepted = update_mod.run(
        repo=business_repo, interactive=True, confirm_surfaces=lambda _repo, _files: True
    )
    assert accepted["ok"] is True, accepted["errors"]
    text = (business_repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.startswith("Operator preface.\n\n")
    assert text.endswith("## Operator notes\n\nKeep this.\n")
    assert text.count(claude_guidance.BEGIN) == text.count(claude_guidance.END) == 1
    assert text.count("## Trials and readouts") == 1
    assert claude_guidance.plan(business_repo) == (None, None)


def test_claude_entry_rules_with_missing_end_marker_are_left_unchanged(
    tmp_path: Path,
) -> None:
    path = tmp_path / "CLAUDE.md"
    broken = "# Business\n\n" + claude_guidance.BEGIN + "\nOperator text.\n"
    path.write_text(broken, encoding="utf-8")
    content, refusal = claude_guidance.plan(tmp_path)
    assert content is None
    assert refusal is not None and "incomplete" in refusal
    assert path.read_text(encoding="utf-8") == broken


def test_update_terminal_yes_applies_once_then_unattended_runs_need_no_consent(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    asked: list[list[str]] = []

    def say_yes(repo: Path, files: list[str]) -> bool:
        asked.append(files)
        return True

    result = update_mod.run(repo=business_repo, interactive=True, confirm_surfaces=say_yes)

    assert asked == [[".gitignore", "AGENTS.md"]], result["errors"]
    assert result["ok"] is True, result["errors"]
    assert result["surface_refresh"]["planned"]["consent"] == "approved"
    assert result["surface_refresh"]["planned"]["apply_commands"] == []
    assert not [item for item in result["operator_actions"] if "--plugin" not in item["command"]]
    changed = sorted(line[3:] for line in _git(business_repo, "status", "--porcelain").splitlines())
    assert changed == [".gitignore", "AGENTS.md"]
    agents_md = (business_repo / "AGENTS.md").read_text(encoding="utf-8")
    assert agents_md != "# Old guidance\n"
    assert "<!-- mainbranch" in agents_md
    assert (business_repo / ".claude" / "skills" / "mb-start").is_symlink()
    assert result["codex_repaired"] is True

    # Once the tracked files are current, a run without a terminal still
    # refreshes the gitignored links, and asks nothing.
    _git(business_repo, "add", "-A")
    _git(
        business_repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-q",
        "-m",
        "Refresh",
    )
    (business_repo / ".claude" / "skills" / "mb-start").unlink()

    def never_ask(repo: Path, files: list[str]) -> bool:
        raise AssertionError("nothing tracked changes, so nothing to ask")

    again = update_mod.run(repo=business_repo, interactive=False, confirm_surfaces=never_ask)

    assert again["ok"] is True, again["errors"]
    assert again["surface_refresh"]["planned"]["consent"] == "not_needed"
    assert again["surface_refresh"]["claude"]["applied"] is True
    assert (business_repo / ".claude" / "skills" / "mb-start").is_symlink()
    assert _git(business_repo, "status", "--porcelain") == ""


def test_plan_link_skills_writes_nothing_and_names_gitignore(business_repo: Path) -> None:
    before = _tracked_state(business_repo)

    plan = engine_mod.plan_link_skills(business_repo)

    assert _tracked_state(business_repo) == before
    assert not (business_repo / ".claude").exists()
    assert plan["ok"] is True
    assert plan["tracked_writes"] == [".gitignore"]
    assert ".claude/skills/mb-start" in plan["linked"]
    assert ".claude/skills/mb-start" in plan["gitignore_add"]


# --- #1008 item 4: always fetch the new version after a release --------------


def test_uv_update_command_refreshes_the_package_index() -> None:
    assert update_mod.UV_UPDATE_COMMAND == [
        "uv",
        "tool",
        "install",
        "--refresh-package",
        "mainbranch",
        "mainbranch@latest",
    ]
    assert " ".join(update_mod.UV_UPDATE_COMMAND) == update_mod.UV_UPDATE_COMMAND_TEXT


def test_emitted_commands_quote_a_repo_path_with_spaces_and_parens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "My Business (old)"
    repo.mkdir()
    real = str(repo.resolve())

    def fake_run(
        args: list[str], *, cwd: Path | None = None, timeout: float = 0.0
    ) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["mb", "skill", "link"] and "--plan" in args:
            return _completed(
                args,
                stdout=json.dumps(
                    {"ok": True, "tracked_changes": [{"path": ".gitignore", "op": "write"}]}
                ),
            )
        if args[:3] == ["mb", "doctor", "repair"] and "--plan" in args:
            change = {"path": "AGENTS.md", "op": "write"}
            plan = {"ok": True, "actions": [{"id": "codex-agents-md", "tracked_changes": [change]}]}
            return _completed(args, stdout=json.dumps(plan))
        return _completed(args, returncode=1, stderr="must not apply without a terminal")

    monkeypatch.setattr(update_mod, "install_mode", lambda: "wheel")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: None)
    monkeypatch.setattr(update_mod, "_run_command", fake_run)

    result = update_mod.run(repo=repo, interactive=False)

    planned = result["surface_refresh"]["planned"]
    assert planned["consent"] == "no_terminal"
    emitted = [
        *planned["apply_commands"],
        *[a for a in result["next_actions"] if a.startswith("mb ") and "--repo" in a],
        *[item["command"] for item in result["operator_actions"] if "--repo" in item["command"]],
        result["surface_refresh"]["claude"]["command"],
        result["surface_refresh"]["codex"]["command"],
    ]
    assert len(planned["apply_commands"]) == 2
    assert any("--plan --only codex" in command for command in emitted)
    for command in emitted:
        argv = shlex.split(command)
        assert argv[argv.index("--repo") + 1] == real, command

    update_mod.render_human(result)
    out = capsys.readouterr().out.splitlines()
    printed = [
        line.removeprefix("next: ")
        for line in out
        if line.startswith("next: mb ") and "--repo" in line
    ]
    # The plan command, and the retry `mb update` hands out (#1072).
    assert len(printed) == 2
    for_you = [
        line.removeprefix("for you to run: ")
        for line in out
        if line.startswith("for you to run: mb ") and "--repo" in line
    ]
    assert len(for_you) == 2
    printed.extend(for_you)
    for command in printed:
        argv = shlex.split(command)
        assert argv[argv.index("--repo") + 1] == real, command


# --- #1015 review: deletions, aliases and transitional cleanup ---------------


def _commit_all(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-q",
        "-m",
        message,
    )


def _probe_repo(repo: Path, tmp_path: Path, kind: str) -> str:
    """Set up one review reproduction; return the tracked path it puts at risk."""
    entries, _ = engine_mod._link_gitignore_entries()
    (repo / ".gitignore").write_text("\n".join(entries) + "\n", encoding="utf-8")
    at_risk = ""
    if kind == "legacy_link":
        old = repo / ".claude" / "skills" / "start"
        old.parent.mkdir(parents=True)
        old.symlink_to(tmp_path / "missing-old-engine")
        _git(repo, "add", "-f", ".claude/skills/start")
        at_risk = ".claude/skills/start"
    elif kind == "claude_alias":
        shared = repo / "shared-claude"
        shared.mkdir()
        (shared / "settings.local.json").write_text("{}\n", encoding="utf-8")
        (repo / ".claude").symlink_to(shared, target_is_directory=True)
        at_risk = "shared-claude/settings.local.json"
    elif kind in {"codex_alias", "codex_skill_alias"}:
        codex_mod.write_agents_md(repo)
        shared = repo / "shared-codex" / "mb-start"
        shared.mkdir(parents=True)
        (shared / "SKILL.md").write_text("stale\n", encoding="utf-8")
        global_root = codex_mod.global_skill_source_root()
        if kind == "codex_alias":
            for name in codex_mod.CODEX_GLOBAL_SKILL_NAMES:
                current = shared.parent / name / "SKILL.md"
                current.parent.mkdir(parents=True, exist_ok=True)
                if name != "mb-start":
                    current.write_text(
                        codex_mod.render_codex_global_skill_md(name), encoding="utf-8"
                    )
            global_root.parent.mkdir(parents=True, exist_ok=True)
            global_root.symlink_to(shared.parent, target_is_directory=True)
        else:
            global_root.mkdir(parents=True, exist_ok=True)
            (global_root / "mb-start").symlink_to(shared, target_is_directory=True)
        at_risk = "shared-codex/mb-start/SKILL.md"
    elif kind == "codex_cleanup":
        legacy = repo / ".agents" / "skills" / "main-branch" / "SKILL.md"
        legacy.parent.mkdir(parents=True)
        # #1052: only a file `mb` wrote there is removed.
        legacy.write_text(codex_mod.render_codex_global_skill_md("main-branch"), encoding="utf-8")
        at_risk = ".agents/skills/main-branch"
    _commit_all(repo, "Probe setup")
    assert _git(repo, "status", "--porcelain") == ""
    return at_risk


def _changed_tracked(repo: Path) -> list[str]:
    status = _git(repo, "status", "--porcelain", "--untracked-files=no")
    return sorted(line[3:] for line in status.splitlines())


# A linked skills root still needs consent for writes into the tracked repo.
# A linked individual skill folder is kept instead (the separate test below).
REVIEW_PROBES = ["legacy_link", "claude_alias", "codex_alias", "codex_cleanup"]


@pytest.mark.parametrize("kind", REVIEW_PROBES)
def test_review_probe_unattended_changes_no_tracked_file_and_plans_it(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path, kind: str
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    at_risk = _probe_repo(business_repo, tmp_path, kind)

    result = update_mod.run(repo=business_repo, interactive=False)

    assert _changed_tracked(business_repo) == []
    assert _git(business_repo, "status", "--porcelain") == ""
    planned = result["surface_refresh"]["planned"]
    assert planned["consent"] == "no_terminal", planned
    assert at_risk in planned["tracked_files"], planned
    assert result["ok"] is True, result["errors"]


def test_a_linked_global_codex_skill_folder_is_left_alone_without_consent(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    at_risk = _probe_repo(business_repo, tmp_path, "codex_skill_alias")

    result = update_mod.run(repo=business_repo, interactive=False)

    assert (business_repo / at_risk).read_text(encoding="utf-8") == "stale\n"
    assert _git(business_repo, "status", "--porcelain") == ""
    assert result["surface_refresh"]["planned"]["consent"] == "not_needed"
    assert result["ok"] is True, result["errors"]


@pytest.mark.parametrize("kind", REVIEW_PROBES)
def test_review_probe_yes_changes_only_listed_files(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path, kind: str
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    at_risk = _probe_repo(business_repo, tmp_path, kind)
    asked: list[list[str]] = []

    def say_yes(repo: Path, files: list[str]) -> bool:
        asked.append(files)
        return True

    result = update_mod.run(repo=business_repo, interactive=True, confirm_surfaces=say_yes)

    assert len(asked) == 1
    listed = result["surface_refresh"]["planned"]["tracked_files"]
    assert at_risk in listed
    changed = _changed_tracked(business_repo)
    assert changed, "the approved plan should have changed something"
    if kind == "codex_alias":
        assert listed == changed == [at_risk]
        assert (business_repo / at_risk).read_text(encoding="utf-8") == (
            codex_mod.render_codex_global_skill_md("mb-start")
        )
    for path in changed:
        assert any(path == item or path.startswith(item.rstrip("/") + "/") for item in listed), (
            path,
            listed,
        )
    assert result["ok"] is True, result["errors"]


def _agents_md_missing_end_marker(repo: Path) -> str:
    codex_mod.write_agents_md(repo)
    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    # Guidance from an older template, so the repair is due.
    stale = text.replace(codex_mod.guidance_template_hash(), "0000000000000000")
    broken = stale.replace(codex_mod.AGENTS_MANAGED_END + "\n", "") + "\n## Our notes\n\nKeep.\n"
    (repo / "AGENTS.md").write_text(broken, encoding="utf-8")
    _commit_all(repo, "Notes under the guidance")
    return broken


@pytest.mark.parametrize("interactive", [False, True])
def test_update_reports_a_refused_codex_repair_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, interactive: bool
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _with_current_gitignore(business_repo)
    broken = _agents_md_missing_end_marker(business_repo)
    asked: list[list[str]] = []

    def say_yes(repo: Path, files: list[str]) -> bool:
        asked.append(files)
        return True

    result = update_mod.run(repo=business_repo, interactive=interactive, confirm_surfaces=say_yes)

    assert (business_repo / "AGENTS.md").read_text(encoding="utf-8") == broken
    assert _git(business_repo, "status", "--porcelain") == ""
    assert not any("--apply" in args and "codex" in args for args in calls)
    assert all("AGENTS.md" not in files for files in asked)
    codex_surface = result["surface_refresh"]["codex"]
    assert codex_surface["applied"] is False
    assert codex_surface["blocked"] is True
    assert "no end marker" in codex_surface["reason"]
    assert "AGENTS.md" not in result["surface_refresh"]["planned"]["tracked_files"]
    entries = [item for item in result["operator_actions"] if item.get("id") == "codex-agents-md"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["command"] == f"mb doctor repair --repo {business_repo} --apply --only codex"
    assert entry["changes"] == ["AGENTS.md"]
    assert codex_mod.AGENTS_MANAGED_END in entry["manual_step"]
    assert entry["manual_step"] in entry["note"]
    assert not any(
        item["note"] == update_mod.SURFACE_CODEX_APPLY_NOTE for item in result["operator_actions"]
    )
    assert f"mb doctor repair --repo {business_repo} --plan --only codex" in result["next_actions"]
    assert any(entry["reason"] in warning for warning in result["warnings"])
    assert result["ok"] is True, result["errors"]


def test_update_codex_follow_up_names_the_manual_step(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    _agents_md_missing_end_marker(business_repo)
    result: dict[str, Any] = {"operator_actions": [], "warnings": [], "next_actions": []}

    update_mod._add_codex_follow_up(result, business_repo)

    entries = [item for item in result["operator_actions"] if item.get("id") == "codex-agents-md"]
    assert len(entries) == 1
    assert codex_mod.AGENTS_MANAGED_END in entries[0]["manual_step"]
    # #1053: the entry names the repo, like every other `mb update` entry.
    assert entries[0]["command"] == (
        f"mb doctor repair --repo {shlex.quote(str(business_repo.resolve()))} --apply --only codex"
    )


def test_unattended_guard_reports_a_tracked_change_the_plan_missed(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    entries, _ = engine_mod._link_gitignore_entries()
    (business_repo / ".gitignore").write_text("\n".join(entries) + "\n", encoding="utf-8")
    _commit_all(business_repo, "Current gitignore")
    # A deliberately wrong plan: it misses the AGENTS.md write the apply makes.
    monkeypatch.setattr(
        update_mod,
        "_plan_codex_surface",
        lambda repo: ({"ok": True, "actions": []}, []),
    )

    result = update_mod.run(repo=business_repo, interactive=False)

    assert _changed_tracked(business_repo) == ["AGENTS.md"]
    assert result["ok"] is False
    assert result["surface_refresh"]["planned"]["unapproved_changes"] == ["AGENTS.md"]
    assert any("not approved: AGENTS.md" in error for error in result["errors"])


def _case_insensitive(directory: Path) -> bool:
    probe = directory / "case-probe"
    probe.write_text("", encoding="utf-8")
    try:
        return (directory / "CASE-PROBE").exists()
    finally:
        probe.unlink()


def _with_current_gitignore(repo: Path) -> None:
    entries, _ = engine_mod._link_gitignore_entries()
    (repo / ".gitignore").write_text("\n".join(entries) + "\n", encoding="utf-8")


def test_unattended_update_leaves_a_lowercase_agents_md_alone(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    if not _case_insensitive(business_repo):
        pytest.skip("needs a case-insensitive filesystem: agents.md and AGENTS.md differ here")
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _with_current_gitignore(business_repo)
    _git(business_repo, "mv", "AGENTS.md", "intermediate.md")
    _git(business_repo, "mv", "intermediate.md", "agents.md")
    _commit_all(business_repo, "Lowercase agents.md")

    result = update_mod.run(repo=business_repo, interactive=False)

    assert _git(business_repo, "status", "--porcelain") == ""
    assert (business_repo / "agents.md").read_text(encoding="utf-8") == "# Old guidance\n"
    planned = result["surface_refresh"]["planned"]
    assert planned["consent"] == "no_terminal", planned
    assert "agents.md" in planned["tracked_files"], planned
    assert result["ok"] is True, result["errors"]


@pytest.mark.parametrize("holder", ["business", "other"])
def test_unattended_update_never_writes_through_a_hard_link(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path, holder: str
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _with_current_gitignore(business_repo)
    codex_mod.write_agents_md(business_repo)
    holder_repo = business_repo
    if holder == "other":
        holder_repo = tmp_path / "other"
        holder_repo.mkdir()
        _git(holder_repo, "init", "-q", "-b", "main")
    shared = holder_repo / "shared-skill.md"
    shared.write_text("stale\n", encoding="utf-8")
    global_skill = codex_mod.global_skill_source_root() / "mb-start" / "SKILL.md"
    global_skill.parent.mkdir(parents=True, exist_ok=True)
    os.link(shared, global_skill)
    _commit_all(holder_repo, "Shared skill")
    if holder == "other":
        _commit_all(business_repo, "Current surfaces")

    result = update_mod.run(repo=business_repo, interactive=False)

    assert shared.read_text(encoding="utf-8") == "stale\n"
    assert _git(business_repo, "status", "--porcelain") == ""
    assert _git(holder_repo, "status", "--porcelain") == ""
    planned = result["surface_refresh"]["planned"]
    if holder == "business":
        assert "shared-skill.md" in planned["tracked_files"], planned
    else:
        # Outside the business repo the refresh still runs, into a new file.
        assert global_skill.read_text(encoding="utf-8") != "stale\n"
        assert not os.path.samefile(global_skill, shared)
    assert result["ok"] is True, result["errors"]


def test_planned_personal_backup_is_where_the_link_moves_it(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _with_current_gitignore(business_repo)
    codex_mod.write_agents_md(business_repo)
    _commit_all(business_repo, "Current surfaces")
    personal = engine_mod._personal_skills_dir()
    personal.mkdir(parents=True)
    (personal / "mb-start").symlink_to(tmp_path / "missing-engine")

    planned = [
        item["path"]
        for item in engine_mod.plan_link_skills(business_repo)["operations"]
        if item["op"] == "create" and ".mainbranch-backups" in item["path"]
    ]
    result = update_mod.run(repo=business_repo, interactive=False)

    applied = sorted(str(path) for path in (personal / ".mainbranch-backups").rglob("mb-start*"))
    assert planned and applied == planned, (planned, applied)
    assert result["ok"] is True, result["errors"]


@pytest.mark.parametrize("interactive", [False, True])
def test_update_never_deletes_a_persons_mb_command_in_an_old_codex_path(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, interactive: bool
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _with_current_gitignore(business_repo)
    codex_mod.write_agents_md(business_repo)
    mine = business_repo / codex_mod.CODEX_PLUGIN_COMMANDS_RELATIVE_PATH / "mb-team-policy.md"
    mine.parent.mkdir(parents=True)
    policy = "# Team policy\nOur Main Branch workflow requires two reviewers.\n"
    mine.write_text(policy, encoding="utf-8")
    _commit_all(business_repo, "A team command")

    result = update_mod.run(
        repo=business_repo, interactive=interactive, confirm_surfaces=lambda repo, files: True
    )

    assert mine.read_text(encoding="utf-8") == policy
    assert _git(business_repo, "status", "--porcelain") == ""
    assert not any("--apply" in args and "codex" in args for args in calls)
    assert result["surface_refresh"]["codex"]["blocked"] is True
    entries = [item for item in result["operator_actions"] if item.get("id") == "codex-agents-md"]
    assert len(entries) == 1
    assert "mb-team-policy.md" in entries[0]["reason"]
    assert result["ok"] is True, result["errors"]


# --- #1053: one plan command, `--repo` everywhere, no AGENTS.md unattended ---


def _codex_repair_commands(result: dict[str, Any]) -> list[str]:
    return [
        *[a for a in result["next_actions"] if a.startswith("mb doctor repair")],
        *[
            item["command"]
            for item in result["operator_actions"]
            if item["command"].startswith("mb doctor repair")
        ],
    ]


@pytest.mark.parametrize(
    ("check", "refresh"),
    [(False, True), (True, True), (False, False)],
    ids=["run", "check", "no-refresh"],
)
def test_update_lists_one_codex_plan_command_for_a_stale_agents_md(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, check: bool, refresh: bool
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)

    result = update_mod.run(
        repo=business_repo, check=check, refresh_surfaces=refresh, interactive=False
    )

    repo_flag = f"--repo {shlex.quote(str(business_repo.resolve()))}"
    plans = [a for a in result["next_actions"] if "--plan --only codex" in a]
    assert plans == [f"mb doctor repair {repo_flag} --plan --only codex"]
    applies = [
        item["command"]
        for item in result["operator_actions"]
        if "--apply --only codex" in item["command"]
    ]
    assert applies == [f"mb doctor repair {repo_flag} --apply --only codex"]
    for command in _codex_repair_commands(result):
        assert f" {repo_flag} " in command, command


def _without_agents_md(repo: Path) -> None:
    _with_current_gitignore(repo)
    (repo / "AGENTS.md").unlink()
    _commit_all(repo, "No AGENTS.md")


def test_unattended_update_does_not_create_a_missing_agents_md(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _without_agents_md(business_repo)

    result = update_mod.run(repo=business_repo, interactive=False)

    assert not (business_repo / "AGENTS.md").exists()
    assert _git(business_repo, "status", "--porcelain") == ""
    assert not any("--apply" in args for args in calls)
    assert result["ok"] is True, result["errors"]
    planned = result["surface_refresh"]["planned"]
    assert planned["consent"] == "no_terminal"
    assert planned["tracked_files"] == ["AGENTS.md"]
    assert {"path": "AGENTS.md", "op": "create"} in planned["tracked_changes"]
    codex_apply = f"mb doctor repair --repo {shlex.quote(str(business_repo))} --apply --only codex"
    entries = [item for item in result["operator_actions"] if item["command"] == codex_apply]
    assert len(entries) == 1
    assert entries[0]["changes"] == ["AGENTS.md"]
    assert result["surface_refresh"]["codex"]["applied"] is False
    assert any("Left repo files unchanged: AGENTS.md" in w for w in result["warnings"])


def test_terminal_yes_creates_a_missing_agents_md(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _without_agents_md(business_repo)
    asked: list[list[str]] = []

    def say_yes(repo: Path, files: list[str]) -> bool:
        asked.append(files)
        return True

    result = update_mod.run(repo=business_repo, interactive=True, confirm_surfaces=say_yes)

    assert asked == [["AGENTS.md (create)"]]
    assert result["ok"] is True, result["errors"]
    assert result["surface_refresh"]["planned"]["consent"] == "approved"
    assert result["surface_refresh"]["codex"]["applied"] is True
    assert (business_repo / "AGENTS.md").is_file()
    assert not [item for item in result["operator_actions"] if "--only codex" in item["command"]]


def test_operator_actions_doc_example_matches_real_entries(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    result = update_mod.run(repo=business_repo, interactive=False)
    real = {item["command"]: item for item in result["operator_actions"]}

    root = Path(__file__).resolve().parents[2]
    doc = (root / "docs" / "json-output-contract.md").read_text(encoding="utf-8")
    section = doc.split("### Operator Actions", 1)[1].split("\n### ", 1)[0]
    example = json.loads(section.split("```json\n", 1)[1].split("```", 1)[0])
    placeholder = "/Users/me/my-business"
    shown = {
        item["command"].replace(placeholder, shlex.quote(str(business_repo))): item
        for item in example["operator_actions"]
        if placeholder in item["command"]
    }
    plugin = f"mb skill link --repo {shlex.quote(str(business_repo))} --plugin"
    assert set(shown) == {
        f"mb skill link --repo {shlex.quote(str(business_repo))}",
        plugin,
        f"mb doctor repair --repo {shlex.quote(str(business_repo))} --apply --only codex",
    }
    assert set(shown[plugin]) == set(engine_mod.plugin_switch_operator_action(business_repo))
    for command, item in shown.items():
        if command == plugin:
            continue
        assert set(item) == set(real[command]), command
        assert item["changes"] == real[command]["changes"], command


def _dangling_agents_link(repo: Path, tmp_path: Path, where: str) -> str:
    """An untracked AGENTS.md link to a missing file; returns its target."""
    _without_agents_md(repo)
    target = "docs/nowhere.md" if where == "inside" else str(tmp_path / "elsewhere" / "x.md")
    (repo / "AGENTS.md").symlink_to(target)
    return target


@pytest.mark.parametrize("where", ["inside", "outside"])
def test_unattended_update_leaves_a_dangling_agents_md_link(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path, where: str
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    target = _dangling_agents_link(business_repo, tmp_path, where)

    result = update_mod.run(repo=business_repo, interactive=False)

    link = business_repo / "AGENTS.md"
    assert link.is_symlink()
    assert os.readlink(link) == target
    assert not any("--apply" in args for args in calls)
    assert result["ok"] is True, result["errors"]
    planned = result["surface_refresh"]["planned"]
    assert planned["consent"] == "no_terminal"
    assert planned["tracked_files"] == ["AGENTS.md"]
    assert {"path": "AGENTS.md", "op": "replace_link"} in planned["tracked_changes"]
    codex_apply = f"mb doctor repair --repo {shlex.quote(str(business_repo))} --apply --only codex"
    entries = [item for item in result["operator_actions"] if item["command"] == codex_apply]
    assert len(entries) == 1
    assert entries[0]["changes"] == ["AGENTS.md"]


def test_terminal_yes_replaces_a_dangling_agents_md_link(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _dangling_agents_link(business_repo, tmp_path, "outside")
    asked: list[list[str]] = []

    def say_yes(repo: Path, files: list[str]) -> bool:
        asked.append(files)
        return True

    result = update_mod.run(repo=business_repo, interactive=True, confirm_surfaces=say_yes)

    assert asked == [["AGENTS.md (replace link)"]]
    assert result["ok"] is True, result["errors"]
    link = business_repo / "AGENTS.md"
    assert not link.is_symlink()
    assert link.is_file()
    assert not (tmp_path / "elsewhere").exists()


# --- #1067: global files the Codex cleanup keeps, next to the AGENTS.md entry ---


def _without_kept(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in entries if item.get("id") != "codex-global-kept"]


@pytest.mark.parametrize("agents", ["missing", "refused"])
@pytest.mark.parametrize(
    ("check", "refresh"),
    [(False, True), (True, True), (False, False)],
    ids=["run", "check", "no-refresh"],
)
def test_update_lists_kept_global_files_without_hiding_the_agents_md_entry(
    monkeypatch: pytest.MonkeyPatch,
    business_repo: Path,
    tmp_path: Path,
    check: bool,
    refresh: bool,
    agents: str,
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    if agents == "missing":
        _git(business_repo, "rm", "-q", "AGENTS.md")
    else:
        (business_repo / "AGENTS.md").write_text(
            f"# Ours\n{codex_mod.AGENTS_MANAGED_BEGIN}\nOld guidance, end marker deleted.\n",
            encoding="utf-8",
        )
    _commit_all(business_repo, f"AGENTS.md {agents}")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    def update() -> dict[str, Any]:
        return update_mod.run(
            repo=business_repo, check=check, refresh_surfaces=refresh, interactive=False
        )

    without = update()
    mine = (
        codex_mod.global_plugin_source_root()
        / codex_mod.CODEX_PLUGIN_COMMANDS_RELATIVE_PATH
        / "mb-team-policy.md"
    )
    mine.parent.mkdir(parents=True, exist_ok=True)
    mine.write_text("# Team policy\nA person wrote this.\n", encoding="utf-8")
    result = update()

    kept = [item for item in result["operator_actions"] if item.get("id") == "codex-global-kept"]
    assert len(kept) == 1 and kept[0]["changes"] == [str(mine)]
    # Every entry `mb update` listed without the kept file is still there, unchanged.
    assert _without_kept(result["operator_actions"]) == without["operator_actions"]
    assert [w for w in result["warnings"] if w != kept[0]["note"]] == without["warnings"]
    agents_entries = [
        item
        for item in result["operator_actions"]
        if "--apply --only codex" in item["command"] and item.get("id") != "codex-global-kept"
    ]
    assert agents_entries, result["operator_actions"]
    if agents == "refused":
        assert [item.get("id") for item in agents_entries] == ["codex-agents-md"]
        assert "end marker" in agents_entries[0]["reason"]
    else:
        assert any("AGENTS.md" in item["changes"] for item in agents_entries)
    assert mine.read_text(encoding="utf-8") == "# Team policy\nA person wrote this.\n"


# --- #1072: every suggested command names the business repo -------------------


def _elsewhere(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    return other


def test_repo_flag_follows_one_rule_everywhere(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path
) -> None:
    quoted = shlex.quote(str(business_repo.resolve()))
    _elsewhere(monkeypatch, tmp_path)
    assert engine_mod.repo_flag(business_repo) == f" --repo {quoted}"
    assert update_mod._repo_flag(business_repo) == f" --repo {quoted}"
    assert codex_mod._repo_flag(business_repo) == f" --repo {quoted}"
    monkeypatch.chdir(business_repo)
    assert engine_mod.repo_flag(business_repo) == ""
    assert update_mod._repo_flag(business_repo) == ""
    assert codex_mod._repo_flag(business_repo) == ""


def test_update_next_actions_name_the_repo_from_another_folder(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    _elsewhere(monkeypatch, tmp_path)
    quoted = shlex.quote(str(business_repo.resolve()))

    checked = update_mod.run(repo=business_repo, check=True, interactive=False)
    live = update_mod.run(repo=business_repo, interactive=False, refresh_surfaces=False)

    assert f"mb update --repo {quoted} --check" in checked["next_actions"]
    assert f"mb update --repo {quoted}" in live["next_actions"]
    assert "mb update --check" not in checked["next_actions"]
    assert "mb update" not in live["next_actions"]
    assert any(f"`mb update --repo {quoted}` again" in w for w in live["warnings"])


def test_update_next_actions_stay_bare_inside_the_repo(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    monkeypatch.chdir(business_repo)

    live = update_mod.run(repo=business_repo, interactive=False, refresh_surfaces=False)

    assert "mb update" in live["next_actions"]


def test_update_manual_message_names_the_repo_command(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    monkeypatch.setattr(update_mod, "install_mode", lambda: "uv")
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: "99.0.0")
    monkeypatch.setattr("mb.update.shutil.which", lambda name: f"/usr/bin/{name}")
    _elsewhere(monkeypatch, tmp_path)
    quoted = shlex.quote(str(business_repo.resolve()))

    result = update_mod.run(repo=business_repo, interactive=False, refresh_surfaces=False)

    assert any(f"`mb update --repo {quoted}`" in w for w in result["warnings"])
    assert not any("`mb update` from a terminal" in w for w in result["warnings"])


def test_plugin_switch_operator_action_names_the_repo(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        update_mod,
        "plugin_wiring_status",
        lambda repo: {"wired": False, "marketplace_known": False, "plugin_enabled": False},
    )
    _elsewhere(monkeypatch, tmp_path)
    quoted = shlex.quote(str(business_repo.resolve()))
    result: dict[str, Any] = {"warnings": [], "next_actions": [], "operator_actions": []}

    update_mod._add_plugin_follow_up(result, business_repo.resolve())

    commands = [item["command"] for item in result["operator_actions"]]
    assert commands == [f"mb skill link --repo {quoted} --plugin"]
    monkeypatch.chdir(business_repo)
    result = {"warnings": [], "next_actions": [], "operator_actions": []}
    update_mod._add_plugin_follow_up(result, business_repo.resolve())
    assert [item["command"] for item in result["operator_actions"]] == ["mb skill link --plugin"]


def test_codex_runtime_follow_up_status_command_names_the_repo(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        codex_mod,
        "readiness",
        lambda repo=None, **_: {
            "ok": False,
            "status": "runtime",
            "instructions": {"ok": True},
            "global_skill_ok": True,
            "global_skill": {},
            "plugin_install": {},
        },
    )
    _elsewhere(monkeypatch, tmp_path)
    quoted = shlex.quote(str(business_repo.resolve()))
    result: dict[str, Any] = {"warnings": [], "next_actions": [], "operator_actions": []}

    update_mod._add_codex_follow_up(result, business_repo.resolve())

    assert result["next_actions"] == [f"mb status --json --peek {quoted}"]
    assert f"`mb status --json --peek {quoted}`" in result["warnings"][0]


def test_codex_follow_up_prose_names_the_repo(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        codex_mod,
        "readiness",
        lambda repo=None, **_: {
            "ok": False,
            "status": "global",
            "instructions": {"ok": True},
            "global_skill_ok": False,
            "global_skill": {},
            "plugin_install": {},
        },
    )
    _elsewhere(monkeypatch, tmp_path)
    flag = f"--repo {shlex.quote(str(business_repo.resolve()))}"
    result: dict[str, Any] = {"warnings": [], "next_actions": [], "operator_actions": []}

    update_mod._add_codex_follow_up(result, business_repo.resolve())

    assert f"mb doctor repair {flag} --plan --only codex" in result["warnings"][0]
    assert f"mb doctor repair {flag} --apply --only codex" in result["warnings"][0]


def test_a_suggested_command_runs_from_another_folder_on_the_repo(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    monkeypatch.setattr(update_mod, "install_mode", lambda: "pipx")
    other = _elsewhere(monkeypatch, tmp_path)
    live = update_mod.run(repo=business_repo, interactive=False, refresh_surfaces=False)
    retry = next(item for item in live["next_actions"] if item.startswith("mb update"))
    status = update_mod._status_command(business_repo)
    before = sorted(path.name for path in other.iterdir())

    args = [*shlex.split(retry)[1:], "--check", "--json"]
    out = runner.invoke(app, args)
    peek = runner.invoke(app, [*shlex.split(status)[1:]])

    assert out.exit_code == 0, out.output
    assert json.loads(out.stdout)["repo"] == str(business_repo.resolve())
    assert peek.exit_code == 0, peek.output
    assert json.loads(peek.stdout)["repo"]["path"] == str(business_repo.resolve())
    assert sorted(path.name for path in other.iterdir()) == before


# --- #1072: AGENTS.md as a folder or a link --------------------------------


def _agents_as_directory(repo: Path) -> None:
    (repo / "AGENTS.md").unlink()
    (repo / "AGENTS.md").mkdir()
    (repo / "AGENTS.md" / "notes.md").write_text("mine\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-qm", "dir")


@pytest.mark.parametrize("interactive", [False, True])
def test_update_reports_an_agents_md_folder_instead_of_crashing(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, interactive: bool
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _with_current_gitignore(business_repo)
    _agents_as_directory(business_repo)
    asked: list[list[str]] = []

    def say_yes(repo: Path, files: list[str]) -> bool:
        asked.append(files)
        return True

    result = update_mod.run(repo=business_repo, interactive=interactive, confirm_surfaces=say_yes)

    assert (business_repo / "AGENTS.md" / "notes.md").read_text(encoding="utf-8") == "mine\n"
    assert _git(business_repo, "status", "--porcelain") == ""
    assert all("AGENTS.md" not in files for files in asked)
    entries = [item for item in result["operator_actions"] if item.get("id") == "codex-agents-md"]
    assert len(entries) == 1
    assert "is a folder" in entries[0]["reason"]
    assert "Move or rename" in entries[0]["manual_step"]
    assert result["surface_refresh"]["codex"]["blocked"] is True
    assert result["ok"] is True, result["errors"]


def test_doctor_repair_codex_reports_an_agents_md_folder_instead_of_crashing(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    from mb import doctor as doctor_mod

    _agents_as_directory(business_repo)

    plan = doctor_mod.repair_plan(business_repo, only="codex")
    applied = doctor_mod.repair_apply(business_repo, only="codex")

    for report in (plan, applied):
        assert [item["id"] for item in report["operator_actions"]] == ["codex-agents-md"]
    assert (business_repo / "AGENTS.md" / "notes.md").is_file()


def _agents_as_link(repo: Path, kind: str, tmp_path: Path) -> Path:
    outside = tmp_path / "outside" / "AGENTS.md"
    outside.parent.mkdir()
    # The fixture tracks a regular AGENTS.md; only the "tracked" kind keeps a
    # tracked path, the others start from a repo that does not track one.
    _git(repo, "rm", "-q", "AGENTS.md")
    _git(repo, "-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-qm", "rm")
    if kind == "dangling":
        outside = tmp_path / "outside" / "missing.md"
    else:
        outside.write_text("# My own guidance\n", encoding="utf-8")
    (repo / "AGENTS.md").symlink_to(outside)
    if kind == "tracked":
        _git(repo, "add", "-A")
        _git(repo, "-c", "user.name=T", "-c", "user.email=t@example.invalid", "commit", "-qm", "l")
    return outside


@pytest.mark.parametrize("kind", ["untracked", "dangling", "tracked"])
def test_unattended_update_never_replaces_a_symlinked_agents_md(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path, kind: str
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _with_current_gitignore(business_repo)
    outside = _agents_as_link(business_repo, kind, tmp_path)
    target = os.readlink(business_repo / "AGENTS.md")

    result = update_mod.run(repo=business_repo, interactive=False)

    assert (business_repo / "AGENTS.md").is_symlink()
    assert os.readlink(business_repo / "AGENTS.md") == target
    assert not outside.exists() or outside.read_text(encoding="utf-8") == "# My own guidance\n"
    planned = result["surface_refresh"]["planned"]
    assert planned["consent"] == "no_terminal"
    assert "AGENTS.md" in planned["tracked_files"]
    assert result["surface_refresh"]["codex"]["applied"] is False
    entries = [
        item
        for item in result["operator_actions"]
        if item["command"].endswith("--apply --only codex")
    ]
    assert [item["changes"] for item in entries] == [["AGENTS.md"]]
    assert result["ok"] is True, result["errors"]


def test_an_interactive_yes_may_replace_a_symlinked_agents_md_it_listed(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _with_current_gitignore(business_repo)
    outside = _agents_as_link(business_repo, "untracked", tmp_path)
    asked: list[list[str]] = []

    def say_yes(repo: Path, files: list[str]) -> bool:
        asked.append(files)
        return True

    update_mod.run(repo=business_repo, interactive=True, confirm_surfaces=say_yes)

    assert len(asked) == 1
    assert any(item.startswith("AGENTS.md") for item in asked[0])
    assert not (business_repo / "AGENTS.md").is_symlink()
    assert outside.read_text(encoding="utf-8") == "# My own guidance\n"


@pytest.mark.parametrize("mode", ["run", "check", "no-refresh"])
@pytest.mark.parametrize("held", ["folder", "skill-link", "folder-link", "dangling-link"])
def test_update_does_not_suggest_an_apply_when_only_kept_global_entries_remain(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path, mode: str, held: str
) -> None:
    _wheel_update_env(monkeypatch, [])
    codex_mod.write_agents_md(business_repo)
    codex_mod.write_global_skill_source()
    skill = codex_mod.global_skill_file_path("main-branch")
    skill.unlink()
    if held == "folder":
        skill.mkdir()
    elif held == "skill-link":
        skill.parent.rmdir()
        outside = tmp_path / "my-skill"
        outside.mkdir()
        (outside / "SKILL.md").write_text("mine\n", encoding="utf-8")
        skill.parent.symlink_to(outside, target_is_directory=True)
    else:
        outside = tmp_path / "my-folder"
        if held == "folder-link":
            outside.mkdir()
        skill.symlink_to(outside, target_is_directory=True)
    _commit_all(business_repo, "Current guidance")

    result = update_mod.run(
        repo=business_repo,
        check=mode == "check",
        refresh_surfaces=mode != "no-refresh",
        interactive=False,
    )

    assert result["ok"] is True, result["errors"]
    assert not any("skills are not ready" in warning for warning in result["warnings"])
    assert not any("--apply --only codex" in command for command in result["next_actions"])
    entries = [a for a in result["operator_actions"] if a.get("id") == "codex-global-kept"]
    assert len(entries) == 1
    assert entries[0]["on_apply"]["writes"] == entries[0]["on_apply"]["removes"] == []
    assert entries[0]["on_apply"]["keeps"]


@pytest.mark.parametrize("work", ["write", "remove"])
def test_update_keeps_the_apply_suggestion_when_global_kept_entries_also_have_work(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, work: str
) -> None:
    _wheel_update_env(monkeypatch, [])
    codex_mod.write_agents_md(business_repo)
    codex_mod.write_global_skill_source()
    held = codex_mod.global_skill_file_path("main-branch")
    held.unlink()
    held.mkdir()
    if work == "write":
        codex_mod.global_skill_file_path("mb-start").unlink()
    else:
        codex_mod.write_global_plugin_source()

    result = update_mod.run(repo=business_repo, check=True, interactive=False)

    assert result["ok"] is True, result["errors"]
    assert any("--apply --only codex" in command for command in result["next_actions"])
    entry = next(a for a in result["operator_actions"] if a.get("id") == "codex-global-kept")
    assert entry["on_apply"]["writes" if work == "write" else "removes"]


# --- #1087 item 10: no new .gitignore without a yes ------------------------


def _without_gitignore(repo: Path) -> None:
    codex_mod.write_agents_md(repo)
    (repo / ".gitignore").unlink()
    _commit_all(repo, "No .gitignore")


def test_unattended_update_does_not_create_a_missing_gitignore(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _without_gitignore(business_repo)

    result = update_mod.run(repo=business_repo, interactive=False)

    assert not (business_repo / ".gitignore").exists()
    assert _git(business_repo, "status", "--porcelain") == ""
    assert ["mb", "skill", "link", "--repo", str(business_repo), "--json"] not in calls
    assert result["ok"] is True, result["errors"]
    planned = result["surface_refresh"]["planned"]
    assert planned["consent"] == "no_terminal"
    assert planned["tracked_files"] == [".gitignore"]
    assert {"path": ".gitignore", "op": "create"} in planned["tracked_changes"]
    link_apply = f"mb skill link --repo {shlex.quote(str(business_repo))}"
    entries = [item for item in result["operator_actions"] if item["command"] == link_apply]
    assert [item["changes"] for item in entries] == [[".gitignore"]]
    assert result["surface_refresh"]["claude"]["applied"] is False
    assert any("Left repo files unchanged: .gitignore" in w for w in result["warnings"])


def test_terminal_yes_creates_a_missing_gitignore(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _without_gitignore(business_repo)
    asked: list[list[str]] = []

    def say_yes(repo: Path, files: list[str]) -> bool:
        asked.append(files)
        return True

    result = update_mod.run(repo=business_repo, interactive=True, confirm_surfaces=say_yes)

    assert asked == [[".gitignore (create)"]]
    assert result["ok"] is True, result["errors"]
    assert result["surface_refresh"]["claude"]["applied"] is True
    entries, _ = engine_mod._link_gitignore_entries()
    lines = (business_repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert all(entry in lines for entry in entries)


# --- #1100: `--check` predicts the consent stop ------------------------------


def _tree_snapshot(*roots: Path) -> dict[str, str]:
    """Every entry under the roots (outside `.git`), with its bytes or link text."""
    snapshot: dict[str, str] = {}
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(name for name in dirnames if name != ".git")
            for name in [*dirnames, *filenames]:
                path = Path(dirpath) / name
                try:
                    path.lstat()
                except PermissionError:
                    # Listed in a folder that can be read but not entered.
                    snapshot[str(path)] = "unreachable"
                    continue
                if path.is_symlink():
                    snapshot[str(path)] = "link:" + os.readlink(path)
                elif path.is_dir():
                    snapshot[str(path)] = "dir"
                else:
                    try:
                        snapshot[str(path)] = path.read_bytes().hex()
                    except PermissionError:
                        snapshot[str(path)] = f"unreadable:{path.stat().st_mode:o}"
    return snapshot


def _gitignore_state(repo: Path, tmp_path: Path, state: str) -> None:
    """Put `.gitignore` (and `AGENTS.md`) in one of the #1100 consent states."""
    codex_mod.write_agents_md(repo)
    if state == "tracked_needs_lines":
        _commit_all(repo, "Current AGENTS.md")
        return
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (repo / ".gitignore").unlink()
    if state == "untracked_link":
        (elsewhere / "gitignore").write_text("node_modules/\n", encoding="utf-8")
        _commit_all(repo, "No .gitignore")
        (repo / ".gitignore").symlink_to(elsewhere / "gitignore")
    elif state == "dangling_link":
        _commit_all(repo, "No .gitignore")
        (repo / ".gitignore").symlink_to(elsewhere / "missing")
    elif state == "missing_with_agents_md":
        (repo / "AGENTS.md").unlink()
        _commit_all(repo, "No .gitignore, no AGENTS.md")
    else:
        assert state == "missing"
        _commit_all(repo, "No .gitignore")


@pytest.mark.parametrize(
    "state",
    ["missing", "untracked_link", "dangling_link", "tracked_needs_lines", "missing_with_agents_md"],
)
def test_check_predicts_the_consent_stop_of_an_unattended_run(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path, state: str
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _gitignore_state(business_repo, tmp_path, state)
    status_before = _git(business_repo, "status", "--porcelain", "--ignored")
    tree_before = _tree_snapshot(business_repo, tmp_path / "home", tmp_path / "elsewhere")

    checked = update_mod.run(repo=business_repo, check=True, interactive=False)

    assert _git(business_repo, "status", "--porcelain", "--ignored") == status_before
    assert _tree_snapshot(business_repo, tmp_path / "home", tmp_path / "elsewhere") == (tree_before)
    assert calls == []
    assert checked["ok"] is True, checked["errors"]

    ran = update_mod.run(repo=business_repo, interactive=False)

    predicted = checked["surface_refresh"]["planned"]
    actual = ran["surface_refresh"]["planned"]
    assert actual["consent"] == "no_terminal"
    for key in ("consent", "tracked_files", "tracked_changes", "apply_commands"):
        assert predicted[key] == actual[key], key
    assert ".gitignore" in predicted["tracked_files"]


def test_check_json_and_human_name_the_consent_stop(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _gitignore_state(business_repo, tmp_path, "dangling_link")
    monkeypatch.chdir(tmp_path)

    as_json = runner.invoke(app, ["update", "--check", "--json", "--repo", str(business_repo)])
    human = runner.invoke(app, ["update", "--check", "--repo", str(business_repo)])

    planned = json.loads(as_json.stdout)["surface_refresh"]["planned"]
    assert planned["consent"] == "no_terminal"
    assert planned["tracked_changes"] == [{"path": ".gitignore", "op": "replace_link"}]
    assert "would ask once before changing repo files: .gitignore (replace link)" in human.stdout
    assert f"  mb skill link --repo {shlex.quote(str(business_repo))}" in human.stdout
    assert os.path.islink(business_repo / ".gitignore")
    assert not (tmp_path / "elsewhere" / "missing").exists()


def test_check_output_is_unchanged_when_the_run_needs_no_consent(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    codex_mod.write_agents_md(business_repo)
    entries, _ = engine_mod._link_gitignore_entries()
    (business_repo / ".gitignore").write_text("\n".join(entries) + "\n", encoding="utf-8")
    _commit_all(business_repo, "Current")

    checked = update_mod.run(repo=business_repo, check=True, interactive=False)

    assert checked["surface_refresh"]["planned"] == {
        "consent": "not_needed",
        "tracked_files": [],
        "apply_commands": [],
    }
    assert update_mod.run(repo=business_repo, interactive=False)["surface_refresh"]["planned"][
        "consent"
    ] == ("not_needed")


def test_skill_link_apply_note_says_repo_files() -> None:
    # A new .gitignore is not tracked yet, so "tracked files" was not true for it.
    assert "repo files listed in `changes`" in update_mod.SURFACE_LINK_APPLY_NOTE
    assert "tracked files" not in update_mod.SURFACE_LINK_APPLY_NOTE


def test_check_matches_the_run_for_a_folder_that_is_not_a_business_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    monkeypatch.setattr(codex_mod, "readiness", _REAL_CODEX_READINESS)
    folder = tmp_path / "not-a-business"

    checked = update_mod.run(repo=folder, check=True, interactive=False)
    ran = update_mod.run(repo=folder, interactive=False)

    assert checked["surface_refresh"]["planned"] == ran["surface_refresh"]["planned"]
    assert not folder.exists()


def _unreadable_gitignore(repo: Path, kind: str) -> None:
    """A tracked `.gitignore` the skill-link plan cannot read (#1101 review)."""
    codex_mod.write_agents_md(repo)
    gitignore = repo / ".gitignore"
    if kind in {"skill_loop", "personal_skill_loop"}:
        # A bundled skill's link that points at itself (#1101 re-review).
        _commit_all(repo, "Current AGENTS.md")
        if kind == "skill_loop":
            skills = repo / ".claude" / "skills"
        else:
            skills = engine_mod._personal_skills_dir()
        skills.mkdir(parents=True, exist_ok=True)
        (skills / "mb-start").symlink_to("mb-start")
        return
    if kind in {"skills_closed", "personal_skills_closed"}:
        # #1106 item 3: a skills folder that cannot be entered is named itself.
        _commit_all(repo, "Current AGENTS.md")
        skills = _closed_folder(repo, kind)
        skills.mkdir(parents=True, exist_ok=True)
        (skills / "notes").write_text("x\n", encoding="utf-8")
        skills.chmod(0)
        return
    if kind == "both_not_utf8":
        # #1106 item 2: the plan reads settings first, so settings is named.
        settings = repo / ".claude" / "settings.local.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_bytes('{"note": "café"}\n'.encode("latin-1"))
        gitignore.write_bytes("node_modules/\n# café notes\n".encode("latin-1"))
        _commit_all(repo, "Neither file is UTF-8")
        return
    if kind == "folder":
        gitignore.unlink()
        _commit_all(repo, "No .gitignore")
        gitignore.mkdir()
        (gitignore / "keep").write_text("x\n", encoding="utf-8")
        return
    if kind == "latin1":
        gitignore.write_bytes("node_modules/\n# café notes\n".encode("latin-1"))
    elif kind == "utf16":
        gitignore.write_bytes("node_modules/\n".encode("utf-16"))
    else:
        assert kind == "unreadable"
    _commit_all(repo, f"{kind} .gitignore")
    if kind == "unreadable":
        gitignore.chmod(0)


def _closed_folder(repo: Path, kind: str) -> Path:
    if kind == "skills_closed":
        return repo / ".claude" / "skills"
    return engine_mod._personal_skills_dir()


MODE_000_KINDS = {"unreadable", "skills_closed", "personal_skills_closed"}


@pytest.mark.parametrize(
    ("kind", "named", "fix"),
    [
        ("latin1", "`.gitignore`", "Save `.gitignore` as UTF-8 text"),
        ("utf16", "`.gitignore`", "Save `.gitignore` as UTF-8 text"),
        ("unreadable", "`.gitignore`", "Give your user read access to `.gitignore`"),
        ("folder", "`.gitignore`", "Move the `.gitignore` folder aside"),
        (
            "skill_loop",
            "`.claude/skills/mb-start`",
            "Remove the link `.claude/skills/mb-start`",
        ),
        (
            "personal_skill_loop",
            "`~/.claude/skills/mb-start`",
            "Remove the link `~/.claude/skills/mb-start`",
        ),
        (
            "both_not_utf8",
            "`.claude/settings.local.json`",
            "Save `.claude/settings.local.json` as UTF-8 text",
        ),
        (
            "skills_closed",
            "`.claude/skills` (",
            "Let your user open the `.claude/skills` folder (give it read and execute permission),",
        ),
        (
            "personal_skills_closed",
            "`~/.claude/skills` (",
            "Let your user open the `~/.claude/skills` folder"
            " (give it read and execute permission),",
        ),
    ],
)
def test_check_does_not_crash_on_a_gitignore_it_cannot_read(
    monkeypatch: pytest.MonkeyPatch,
    business_repo: Path,
    tmp_path: Path,
    kind: str,
    named: str,
    fix: str,
) -> None:
    if kind in MODE_000_KINDS and hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root can read a mode 000 file")
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    _unreadable_gitignore(business_repo, kind)
    monkeypatch.chdir(tmp_path)
    status_before = _git(business_repo, "status", "--porcelain", "--ignored")
    tree_before = _tree_snapshot(business_repo, tmp_path / "home")
    try:
        as_json = runner.invoke(app, ["update", "--check", "--json", "--repo", str(business_repo)])
        human = runner.invoke(app, ["update", "--check", "--repo", str(business_repo)])
        assert _tree_snapshot(business_repo, tmp_path / "home") == tree_before
        assert _git(business_repo, "status", "--porcelain", "--ignored") == status_before
    finally:
        if kind == "unreadable":
            (business_repo / ".gitignore").chmod(0o644)
        if kind in {"skills_closed", "personal_skills_closed"}:
            _closed_folder(business_repo, kind).chmod(0o755)

    assert as_json.exception is None, as_json.exception
    assert as_json.exit_code == 0, as_json.stdout
    result = json.loads(as_json.stdout)
    assert result["ok"] is True
    assert result["surface_refresh"]["planned"] == {
        "consent": "not_needed",
        "tracked_files": [],
        "apply_commands": [],
    }
    warnings = [item for item in result["warnings"] if item.startswith("Could not read ")]
    assert len(warnings) == 1, result["warnings"]
    assert named in warnings[0]
    assert "cannot plan the skill link refresh" in warnings[0]
    assert "real `mb update` stops" in warnings[0]
    assert fix in warnings[0]
    assert str(tmp_path) not in warnings[0]
    assert human.exception is None, human.exception
    assert human.exit_code == 0
    assert f"warning: {warnings[0]}" in human.stdout
    assert calls == []


def test_check_reads_codex_readiness_once(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    reads: list[Path] = []

    def counted(repo: Path) -> dict[str, Any]:
        reads.append(Path(repo))
        return _REAL_CODEX_READINESS(repo)

    monkeypatch.setattr(codex_mod, "readiness", counted)

    result = update_mod.run(repo=business_repo, check=True, interactive=False)

    assert result["ok"] is True, result["errors"]
    assert result["surface_refresh"]["planned"]["consent"] == "no_terminal"
    assert len(reads) == 1


# --- #1106: name the file, never a traceback --------------------------------


def test_check_names_a_looping_link_whose_path_has_quotes_and_a_backslash(
    tmp_path: Path,
) -> None:
    # Item 1: the path is read back as written, not in its escaped form.
    repo = tmp_path / 'it\'s a "biz" \\ folder'
    link = repo / ".claude" / "skills" / "mb-start"
    exc = RuntimeError(f"Symlink loop from {str(link)!r}")

    warning = update_mod._unreadable_plan_warning(repo, "skill link", exc)

    assert warning.startswith("Could not read `.claude/skills/mb-start` (")
    assert str(tmp_path) not in warning


def test_a_decode_error_outside_read_text_names_no_guessed_file(
    business_repo: Path,
) -> None:
    # #1109 item 3: `.gitignore` does not decode either, but nothing shows it is
    # the file that failed, so it is not named.
    (business_repo / ".gitignore").write_bytes("# café\n".encode("latin-1"))
    try:
        b"\xff".decode("utf-8")
    except UnicodeDecodeError as caught:
        exc = caught

    warning = update_mod._unreadable_plan_warning(business_repo, "skill link", exc)

    assert warning.startswith("Could not read a file it needs (it is not UTF-8 text)")
    assert "`.gitignore`" not in warning
    assert "Save the files Main Branch reads in this repo as UTF-8 text" in warning


def test_a_loop_error_naming_a_closed_folder_is_not_called_a_loop(
    business_repo: Path,
) -> None:
    # #1117 item 1: the error is a symlink loop, but the walk names a closed
    # folder above it. That folder is no link, so it gets the permission fix.
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root can enter a mode 000 folder")
    closed = business_repo / ".claude"
    (closed / "skills").mkdir(parents=True)
    raw = str(closed / "skills" / "mb-start")
    for mode, fix in (
        (0o600, "Let your user enter the `.claude` folder (give it execute permission)"),
        (0, "Let your user open the `.claude` folder (give it read and execute permission)"),
    ):
        closed.chmod(mode)
        try:
            for exc in (
                RuntimeError(f"{unreadable_mod.SYMLINK_LOOP_PREFIX}{raw!r}"),
                OSError(errno.ELOOP, "Too many levels of symbolic links", raw),
            ):
                path, reason, named_fix = unreadable_mod.describe(exc, business_repo)
                warning = update_mod._unreadable_plan_warning(business_repo, "skill link", exc)
                assert (path, reason, named_fix) == (".claude", "permission denied", fix)
                assert "loop" not in warning
                assert "Remove the link" not in warning
        finally:
            closed.chmod(0o755)


def test_mode_000_names_read_and_execute_only_for_a_folder(business_repo: Path) -> None:
    # #1117 item 2: a mode 000 folder needs read and execute; a mode 000 file
    # needs read access only, as before.
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root can read a mode 000 file")
    folder = business_repo / ".claude"
    folder.mkdir()
    file = business_repo / ".gitignore"
    folder.chmod(0)
    file.chmod(0)
    try:
        for target, fix in (
            (
                folder,
                "Let your user open the `.claude` folder (give it read and execute permission)",
            ),
            (file, "Give your user read access to `.gitignore`"),
        ):
            exc = PermissionError(errno.EACCES, "Permission denied", str(target))
            assert unreadable_mod.describe(exc, business_repo) == (
                target.name,
                "permission denied",
                fix,
            )
    finally:
        folder.chmod(0o755)
        file.chmod(0o644)


def test_check_keeps_a_programming_error_loud(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path
) -> None:
    # Item 4: only pathlib's symlink loop is a file the plan cannot read.
    _wheel_update_env(monkeypatch, [])

    def broken(repo: Path) -> dict[str, Any]:
        raise NotImplementedError("not built yet")

    monkeypatch.setattr(update_mod, "plan_link_skills", broken)

    with pytest.raises(NotImplementedError):
        update_mod.run(repo=business_repo, check=True, interactive=False)


def _codex_unreadable(repo: Path, kind: str) -> Path:
    """Item 2: a state `codex.readiness` used to crash on; returns what to reopen."""
    codex_mod.write_agents_md(repo)
    if kind == "agents_latin1":
        (repo / "AGENTS.md").write_bytes("# Guidance\n\nCafé notes\n".encode("latin-1"))
        _commit_all(repo, "Latin-1 AGENTS.md")
        return repo / "AGENTS.md"
    _commit_all(repo, "Current AGENTS.md")
    if kind == "codex_home_loop":
        # #1109 item 1: the Codex folder itself is a link to itself.
        looped = Path(os.environ["CODEX_HOME"])
        looped.symlink_to(looped.name)
        return looped
    if kind in {"claude_closed", "claude_no_enter"}:
        closed = repo / ".claude"
        closed.mkdir()
        (closed / "settings.json").write_text("{}\n", encoding="utf-8")
    else:
        assert kind in {"codex_home_closed", "codex_home_no_enter"}
        closed = Path(os.environ["CODEX_HOME"])
        (closed / "skills").mkdir(parents=True)
    # #1109 item 5: mode 600 can be read but not entered.
    closed.chmod(0o600 if kind.endswith("_no_enter") else 0)
    return closed


CODEX_UNREADABLE = [
    ("agents_latin1", "`AGENTS.md`", "Save `AGENTS.md` as UTF-8 text"),
    (
        "claude_closed",
        "`.claude`",
        "Let your user open the `.claude` folder (give it read and execute permission)",
    ),
    (
        "codex_home_closed",
        "`~/.codex`",
        "Let your user open the `~/.codex` folder (give it read and execute permission)",
    ),
    ("codex_home_loop", "`~/.codex`", "Remove the link `~/.codex` or point it"),
    (
        "claude_no_enter",
        "`.claude`",
        "Let your user enter the `.claude` folder (give it execute permission)",
    ),
    (
        "codex_home_no_enter",
        "`~/.codex`",
        "Let your user enter the `~/.codex` folder (give it execute permission)",
    ),
]


@pytest.mark.parametrize(("kind", "named", "fix"), CODEX_UNREADABLE)
def test_update_and_doctor_name_a_codex_file_they_cannot_read(
    monkeypatch: pytest.MonkeyPatch,
    business_repo: Path,
    tmp_path: Path,
    kind: str,
    named: str,
    fix: str,
) -> None:
    root_skips = kind not in {"agents_latin1", "codex_home_loop"}
    if root_skips and hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root can read a mode 000 folder")
    calls: list[list[str]] = []
    _wheel_update_env(monkeypatch, calls)
    closed = _codex_unreadable(business_repo, kind)
    monkeypatch.chdir(tmp_path)
    repo = str(business_repo)
    tree_before = _tree_snapshot(business_repo, tmp_path / "home")
    # Git lists a folder it can read but not enter (mode 600) as untracked.
    status_before = _git(business_repo, "status", "--porcelain")
    try:
        check_json = runner.invoke(app, ["update", "--check", "--json", "--repo", repo])
        check_human = runner.invoke(app, ["update", "--check", "--repo", repo])
        run_json = runner.invoke(app, ["update", "--json", "--repo", repo])
        doctor_json = runner.invoke(app, ["doctor", "--json", repo])
        doctor_human = runner.invoke(app, ["doctor", repo])
        plan_json = runner.invoke(
            app, ["doctor", "repair", "--plan", "--only", "codex", "--json", "--repo", repo]
        )
        assert _tree_snapshot(business_repo, tmp_path / "home") == tree_before
        assert _git(business_repo, "status", "--porcelain") == status_before
    finally:
        if not closed.is_symlink():
            closed.chmod(0o755)

    invoked = [check_json, check_human, run_json, doctor_json, doctor_human, plan_json]
    for item in invoked:
        assert item.exception is None or isinstance(item.exception, SystemExit), item.exception

    checked = json.loads(check_json.stdout)
    assert check_json.exit_code == 0
    assert checked["ok"] is True
    warnings = [item for item in checked["warnings"] if item.startswith("Could not read ")]
    assert len(warnings) == 1, checked["warnings"]
    assert warnings[0].startswith(f"Could not read {named} (")
    assert fix in warnings[0]
    assert str(tmp_path) not in warnings[0]
    assert check_human.exit_code == 0
    assert f"warning: {warnings[0]}" in check_human.stdout

    ran = json.loads(run_json.stdout)
    assert run_json.exit_code == 1
    assert ran["ok"] is False
    named_errors = [item for item in ran["errors"] if named in item]
    assert len(named_errors) == 1, ran["errors"]
    assert fix in named_errors[0]
    # Nothing past the plan ran: no link refresh, no Codex apply.
    assert not any("--apply" in arg for args in calls for arg in args)
    assert ["mb", "skill", "link", "--repo", repo, "--json"] not in calls

    for invoked_json in (doctor_json, plan_json):
        envelope = json.loads(invoked_json.stdout)
        assert invoked_json.exit_code == 1
        assert envelope["ok"] is False
        assert [item["code"] for item in envelope["errors"]] == ["unreadable_file"]
        assert named in envelope["errors"][0]["message"]
        assert fix in envelope["errors"][0]["message"]
    assert doctor_human.exit_code == 1
    assert named in doctor_human.output


# --- #1106 item 3: one Codex action builder ---------------------------------


def _codex_plan_state(repo: Path, state: str) -> None:
    if state in {"baseline", "global_pending"}:
        codex_mod.write_agents_md(repo)
    if state == "missing_agents":
        (repo / "AGENTS.md").unlink()
    if state in {"baseline", "stale_agents", "missing_agents"}:
        codex_mod.write_global_skill_source()
    if _git(repo, "status", "--porcelain"):
        _commit_all(repo, state)


@pytest.mark.parametrize(
    "state", ["baseline", "stale_agents", "missing_agents", "global_pending", "both"]
)
def test_check_codex_plan_is_doctors_codex_plan(
    monkeypatch: pytest.MonkeyPatch, business_repo: Path, state: str
) -> None:
    from mb import doctor as doctor_mod

    _codex_plan_state(business_repo, state)
    monkeypatch.setattr(doctor_mod, "_net", lambda: (False, "offline in tests"))

    checked = update_mod._check_codex_plan(business_repo, codex_mod.readiness(business_repo))
    planned = doctor_mod.repair_plan(repo=business_repo, only="codex")

    codex_ids = {"codex-agents-md", "codex-global-skill"}
    doctor_actions = [item for item in planned["actions"] if item["id"] in codex_ids]
    keys = ("id", "operations", "tracked_changes", "safe_to_apply", "writes", "on_apply")
    assert [{key: item.get(key) for key in keys} for item in checked["actions"]] == [
        {key: item.get(key) for key in keys} for item in doctor_actions
    ]
    assert [item.get("id") for item in checked["operator_actions"]] == [
        item.get("id")
        for item in planned["operator_actions"]
        if item.get("id") in {"codex-agents-md", "codex-global-kept"}
    ]
    expected = {
        "baseline": [],
        "stale_agents": ["codex-agents-md"],
        "missing_agents": ["codex-agents-md"],
        "global_pending": ["codex-global-skill"],
        "both": ["codex-agents-md", "codex-global-skill"],
    }[state]
    assert [item["id"] for item in checked["actions"]] == expected
