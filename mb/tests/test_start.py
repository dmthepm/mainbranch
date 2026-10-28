"""``mb start`` runtime handoff."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import codex as codex_mod
from mb import start as start_mod
from mb import status as status_mod
from mb.cli import app
from mb.init import run as init_run

runner = CliRunner()


def _install_mb_shim(tmp_path: Path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    shim = bin_dir / "mb"
    package_root = Path(__file__).resolve().parents[1]
    shim.write_text(
        f'#!/bin/sh\nPYTHONPATH="{package_root}" exec "{sys.executable}" -m mb "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")


def _with_claude(name: str) -> str:
    if name == "claude":
        return "/usr/local/bin/claude"
    return shutil.which(name) or ""


def _without_claude(name: str) -> str:
    if name == "claude":
        return ""
    return shutil.which(name) or ""


def _with_codex(name: str) -> str:
    if name == "codex":
        return "/usr/local/bin/codex"
    return shutil.which(name) or ""


def _without_codex(name: str) -> str:
    if name == "codex":
        return ""
    return shutil.which(name) or ""


def _prepare_codex_global_skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAINBRANCH_CODEX_SKILLS_ROOT", str(tmp_path / "codex-skills"))
    monkeypatch.setenv("MAINBRANCH_CODEX_PLUGIN_ROOT", str(tmp_path / "codex-plugin"))
    codex_mod.write_global_skill_source()


def _codex_runtime_ok() -> dict[str, Any]:
    return {
        "checked": True,
        "ok": True,
        "state": "ok",
        "shell": "/bin/zsh",
        "command": "command -v mb && mb --version",
        "path": "/usr/local/bin/mb",
        "version": "0.3.31",
        "active_path": "/usr/local/bin/mb",
        "active_version": "0.3.31",
        "path_mismatch": False,
        "version_mismatch": False,
        "mismatch": False,
        "error": "",
        "summary": "Login-shell runtime resolves the active mb.",
        "repair": "",
        "safe_to_share": True,
    }


def test_start_json_reports_codex_global_skill_handoff(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    monkeypatch.setattr(codex_mod, "_which", _with_codex)
    monkeypatch.setattr(codex_mod, "_login_shell_mb_diagnostics", _codex_runtime_ok)
    _prepare_codex_global_skills(tmp_path, monkeypatch)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "vocabulary.md").write_text(
        "---\n"
        "type: vocabulary\n"
        "status: active\n"
        "terms:\n"
        "  push:\n"
        "    singular: drop\n"
        "    plural: drops\n"
        "  statuses:\n"
        "    active: live\n"
        "---\n"
        "# Vocabulary\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["start", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["handoff_ready"] is True
    assert report["runtime"]["found"] is True
    assert report["runtime"]["skill_wiring"]["ok"] is True
    assert report["runtime"]["codex_cli"]["ok"] is True
    assert report["runtime"]["codex_cli"]["status"] == "ready"
    assert report["runtime"]["codex_cli"]["plugin_ok"] is False
    assert report["runtime"]["codex_cli"]["global_skill_ok"] is True
    assert report["runtime"]["codex_cli"]["generated_guidance_ready"] is True
    assert report["runtime"]["codex_cli"]["slash_commands_ready"] is False
    assert report["runtime"]["codex_cli"]["global_skill"]["skills"]["mb-start"]["ok"] is True
    assert report["runtime"]["codex_cli"]["instructions"]["ok"] is True
    assert report["experimental_runtimes"]["codex_cli"]["command"]["argv"] == [
        "codex",
        "-C",
        str(repo.resolve()),
    ]
    next_actions = "\n".join(report["next_actions"])
    assert f"codex -C {shlex.quote(str(repo.resolve()))}" not in next_actions
    assert report["ranked_actions"]
    assert report["daily_state"]["source_command"] == "mb status --json --peek"
    assert report["daily_state"]["runtime_handoff"]["ready"] is True
    assert report["daily_state"]["business_memory"]["state"] in {
        "needs_input",
        "needs_attention",
        "ready",
    }
    codex_next_actions = "\n".join(
        report["experimental_runtimes"]["codex_cli"]["command"]["next_actions"]
    )
    assert "global `mb-start`" in codex_next_actions
    assert "restart Codex" not in codex_next_actions
    assert "Run `claude" not in next_actions
    assert report["command"]["argv"] == ["claude"]
    assert report["command"]["display"].endswith(" && claude")
    assert report["command"]["follow_up"] == "/mb-start"
    codex_prompt = report["experimental_runtimes"]["codex_cli"]["command"]["startup_prompt"]
    assert "`mb-start`" in codex_prompt
    assert "/mb-start" not in codex_prompt
    assert report["launch"]["requested"] is False
    assert report["checkpoint"]["pending"]["status"] == "ready"
    assert report["books"]["schema_version"] == "1.0"
    assert report["books"]["safe_to_share"] is True
    assert report["topology"]["repo_boundary"]["schema"] == "mb.repo_boundary_helper.v0"
    assert report["topology"]["repo_boundary"]["recommended_choice"] == "same_business_repo"
    assert report["push_count"] == 0
    assert report["deprecated_campaign_keys"] is True
    assert report["push_compatibility"]["legacy_campaigns_read"] is True
    assert report["vocabulary"]["ok"] is True
    assert report["vocabulary"]["terms"]["push"] == {"singular": "drop", "plural": "drops"}
    assert report["vocabulary"]["terms"]["statuses"]["active"] == "live"
    assert "update" in report
    assert "ranked_actions" in report
    assert report["result_status"] == "ok"
    assert "status" not in report


def test_start_json_omits_codex_command_when_codex_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    monkeypatch.setattr(codex_mod, "_which", _without_codex)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    result = runner.invoke(app, ["start", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    codex = report["experimental_runtimes"]["codex_cli"]
    assert codex["executable"]["found"] is False
    assert "command" not in codex
    assert "Install Codex CLI" not in report["next_actions"]


def test_start_json_separates_codex_static_and_runtime_readiness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    monkeypatch.setattr(codex_mod, "_which", _with_codex)
    monkeypatch.setattr(codex_mod, "_login_shell_mb_diagnostics", _codex_runtime_ok)
    _prepare_codex_global_skills(tmp_path, monkeypatch)
    monkeypatch.setattr(
        codex_mod,
        "_login_shell_mb_diagnostics",
        lambda: {
            "checked": True,
            "ok": False,
            "state": "warn",
            "shell": "/bin/zsh",
            "command": "command -v mb && mb --version",
            "path": "/old/bin/mb",
            "version": "0.3.18",
            "active_path": "/new/bin/mb",
            "active_version": "0.3.29",
            "path_mismatch": True,
            "version_mismatch": True,
            "mismatch": True,
            "error": "",
            "summary": "Login-shell runtime resolves a different mb than this process.",
            "repair": "Put the current Main Branch install earlier on the login-shell PATH.",
            "safe_to_share": True,
        },
    )
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    result = runner.invoke(app, ["start", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    codex = report["runtime"]["codex_cli"]
    assert codex["static_ok"] is True
    assert codex["runtime_ok"] is False
    assert codex["status"] == "runtime_mismatch"
    check = next(item for item in report["checks"] if item["name"] == "codex_runtime_mb")
    assert check["ok"] is False
    assert "different mb" in check["detail"]
    codex_handoff = report["experimental_runtimes"]["codex_cli"]
    assert "Run `claude" not in "\n".join(codex_handoff["command"]["next_actions"])
    assert any("login-shell PATH" in action for action in codex_handoff["command"]["next_actions"])
    assert any(
        "mb status --json --peek" in action for action in codex_handoff["command"]["next_actions"]
    )
    top_level_actions = "\n".join(report["next_actions"])
    assert "Run `claude" not in top_level_actions
    assert "login-shell PATH" in top_level_actions
    assert "mb status --json --peek" in top_level_actions


def test_start_json_routes_to_codex_global_skill_repair_when_skills_are_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    monkeypatch.setattr(codex_mod, "_which", _with_codex)
    monkeypatch.setattr(codex_mod, "_login_shell_mb_diagnostics", _codex_runtime_ok)
    monkeypatch.setenv("MAINBRANCH_CODEX_SKILLS_ROOT", str(tmp_path / "codex-skills"))
    monkeypatch.setenv("MAINBRANCH_CODEX_PLUGIN_ROOT", str(tmp_path / "codex-plugin"))
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    result = runner.invoke(app, ["start", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    codex = report["runtime"]["codex_cli"]
    assert codex["status"] == "global_skill_missing_or_stale"
    assert codex["global_skill_ok"] is False
    assert codex["plugin_ok"] is False
    assert "mb-start/SKILL.md" in codex["global_skill"]["missing"]
    next_actions = "\n".join(report["next_actions"])
    repo_flag = f"--repo {shlex.quote(str(repo.resolve()))}"
    assert f"mb doctor repair {repo_flag} --plan --only codex" in next_actions
    assert f"codex -C {shlex.quote(str(repo.resolve()))}" not in next_actions
    assert "Run `claude" not in next_actions


def test_start_human_labels_missing_codex_without_experimental_copy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    monkeypatch.setattr(codex_mod, "_which", _without_codex)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    result = runner.invoke(app, ["start", "--repo", str(repo)])

    assert result.exit_code == 0
    assert "Codex" in result.stdout
    assert "missing" in result.stdout
    assert "global skills" in result.stdout
    assert "experimental" not in result.stdout


def test_start_json_names_doctor_repair_when_start_wiring_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    shutil.rmtree(repo / ".claude" / "skills")

    monkeypatch.chdir(repo)  # from another folder the commands name the repo (#1083)
    result = runner.invoke(app, ["start", "--repo", str(repo), "--json"])

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    wiring = report["runtime"]["skill_wiring"]
    assert report["handoff_ready"] is False
    assert "Missing Main Branch start wiring" in wiring["summary"]
    assert "project-local /mb-start bridge" in wiring["missing"]
    assert any("mb doctor repair --plan" in action for action in report["next_actions"])
    assert any("mb doctor repair --apply" in action for action in report["next_actions"])


def test_start_json_exposes_push_and_legacy_campaign_facts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    push = repo / "pushes" / "2026-05-06-workshop"
    push.mkdir(parents=True)
    (push / "push.md").write_text(
        "---\n"
        "type: push\n"
        "slug: workshop\n"
        "kind: launch\n"
        "status: active\n"
        "health: on-track\n"
        "goal:\n"
        "  metric: qualified calls\n"
        "  target: 10 qualified calls\n"
        "  by: 2026-05-20\n"
        "owner: Devon\n"
        "audience: founders\n"
        "offer: core/offers/workshop/offer.md\n"
        "promise: Own the launch memory in git.\n"
        "---\n"
        "# Workshop\n",
        encoding="utf-8",
    )
    campaign = repo / "campaigns" / "2026-05-legacy"
    campaign.mkdir(parents=True)
    (campaign / "campaign.md").write_text(
        "---\ntype: campaign\nslug: legacy\nstatus: active\n---\n# Legacy\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["start", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["push_count"] == 2
    assert report["canonical_push_count"] == 1
    assert report["campaign_count"] == 1
    assert {item["path"] for item in report["active_pushes"]} == {
        "pushes/2026-05-06-workshop/push.md",
        "campaigns/2026-05-legacy/campaign.md",
    }
    assert report["campaigns"][0]["deprecated"] is True


def test_start_json_preserves_books_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_which = shutil.which
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    monkeypatch.setattr(
        "mb.books.shutil.which",
        lambda name: "" if name == "hledger" else real_which(name),
    )
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "finance").mkdir(parents=True, exist_ok=True)
    (repo / "core" / "finance" / "books.md").write_text(
        (
            "---\n"
            "type: books\n"
            "ledger: hledger\n"
            "storage_mode: solo-local\n"
            'vault_location: ".mb/private/books/"\n'
            "---\n\n"
            "# Books\n"
        ),
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text("", encoding="utf-8")

    monkeypatch.chdir(repo)  # from another folder the commands name the repo (#1083)
    result = runner.invoke(app, ["start", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["books"]["state"] == "warn"
    assert report["books"]["configured"] is True
    assert report["books"]["mention"] is True
    assert report["books"]["hledger"]["available"] is False
    assert report["books"]["ignore"]["ok"] is False
    assert report["books"]["next_command"] == "mb books doctor --plan --json"
    assert report["books"]["recommended_route"] == {
        "tool": "mb books doctor --plan",
        "reason": "plan bookkeeping setup repairs",
    }


def test_start_degrades_when_claude_is_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(start_mod, "_which", _without_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    result = runner.invoke(app, ["start", "--repo", str(repo), "--json"])

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["handoff_ready"] is False
    claude_check = next(check for check in report["checks"] if check["name"] == "claude_code")
    assert claude_check["ok"] is False
    # Plugin-first repair (#924): names the cross-surface plugin (Desktop +
    # terminal). Still blocks the terminal handoff, but no longer claims a bare
    # "Install Claude Code" CLI step is the only path.
    repair = claude_check["repair"]
    assert "dmthepm/mainbranch" in repair
    assert "Claude Desktop" in repair
    assert "plugin" in repair.lower()


def test_start_required_update_blocks_handoff_and_surfaces_json(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    monkeypatch.setattr(
        start_mod,
        "package_update_status",
        lambda repo: {
            "installed": "0.1.0",
            "latest": "0.2.1",
            "minimum_supported": "0.2.0",
            "severity": "required",
            "command": "pipx upgrade mainbranch",
            "post_update_commands": ["mb skill link --repo .", "mb doctor"],
            "reason": (
                "Installed version predates mb update and the current skill-link repair flow."
            ),
        },
    )
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    result = runner.invoke(app, ["start", "--repo", str(repo), "--json"])

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["handoff_ready"] is False
    assert report["update"]["severity"] == "required"
    update_check = next(check for check in report["checks"] if check["name"] == "mainbranch_update")
    assert update_check["severity"] == "error"
    assert update_check["repair"] == "pipx upgrade mainbranch"

    human_result = runner.invoke(app, ["start", "--repo", str(repo)])
    assert human_result.exit_code == 1
    assert "Update required." in human_result.stdout
    assert "pipx upgrade mainbranch" in human_result.stdout


def test_start_recommended_update_keeps_handoff_ready(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    monkeypatch.setattr(
        start_mod,
        "package_update_status",
        lambda repo: {
            "installed": "0.2.0",
            "latest": "0.2.1",
            "minimum_supported": "0.2.0",
            "severity": "recommended",
            "command": "mb update",
            "post_update_commands": ["mb skill link --repo .", "mb doctor"],
            "reason": "A newer compatible Main Branch package is available.",
        },
    )
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    result = runner.invoke(app, ["start", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["handoff_ready"] is True
    assert report["update"]["severity"] == "recommended"
    update_check = next(check for check in report["checks"] if check["name"] == "mainbranch_update")
    assert update_check["severity"] == "warn"


def test_start_reads_status_ranked_actions_without_updating_marker(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    status_calls: list[dict[str, Any]] = []
    original_status_run = status_mod.run

    def capture_status_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        status_calls.append(dict(kwargs))
        return original_status_run(*args, **kwargs)

    monkeypatch.setattr(status_mod, "run", capture_status_run)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    marker = repo / ".mb" / "last-status-seen.json"
    assert not marker.exists()

    result = runner.invoke(app, ["start", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["ranked_actions"]
    assert report["daily_state"]["top_ranked_action"] == report["ranked_actions"][0]
    assert report["daily_state"]["source_command"] == "mb status --json --peek"
    assert status_calls == [
        {
            "path": str(repo.resolve()),
            "update_marker": False,
            "validation_cross_refs": False,
        }
    ]
    assert not marker.exists()


def test_start_surfaces_recent_checkpoint_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    _install_mb_shim(tmp_path, monkeypatch)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    subprocess_result = start_mod._run_command(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
    )
    assert subprocess_result["ok"] is True
    subprocess_result = start_mod._run_command(
        ["git", "config", "user.name", "Test User"], cwd=repo
    )
    assert subprocess_result["ok"] is True
    subprocess_result = start_mod._run_command(["git", "add", "."], cwd=repo)
    assert subprocess_result["ok"] is True
    subprocess_result = start_mod._run_command(
        ["git", "commit", "-m", "[added] business scaffold"],
        cwd=repo,
        timeout=15,
    )
    assert subprocess_result["ok"] is True
    (repo / "core" / "offer.md").write_text("# Offer\n", encoding="utf-8")
    commit = runner.invoke(
        app,
        [
            "checkpoint",
            "--repo",
            str(repo),
            "--message",
            "[updated] offer.md",
            "--yes",
            "--json",
        ],
    )
    assert commit.exit_code == 0
    (repo / "research" / "next.md").write_text("# Next\n", encoding="utf-8")

    result = runner.invoke(app, ["start", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["checkpoint"]["recent"][0]["subject"] == "[updated] offer.md"
    assert report["checkpoint"]["recent"][0]["verb"] == "updated"
    assert report["checkpoint"]["pending"]["status"] == "ready"
    assert report["journal"]["events"][0]["summary"] == "Updated offer.md"
    assert report["journal"]["events"][0]["loop"] == "sense"


def test_start_asks_for_repo_when_path_is_not_business_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(start_mod, "_which", _with_claude)

    result = runner.invoke(app, ["start", "--repo", str(tmp_path)])

    assert result.exit_code == 1
    assert "mb start" in result.stdout
    assert "--repo /path/to/business-repo" in result.stdout


def test_start_json_launch_is_rejected_without_launching(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    monkeypatch.setattr(start_mod, "_is_interactive_terminal", lambda: True)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    def fail_launch(path: Path) -> int:
        raise AssertionError(f"should not launch in JSON mode: {path}")

    monkeypatch.setattr(start_mod, "_launch_claude", fail_launch)

    result = runner.invoke(app, ["start", "--repo", str(repo), "--launch", "--json"])

    assert result.exit_code == 2
    report = json.loads(result.stdout)
    assert report["handoff_ready"] is True
    assert report["launch"]["requested"] is True
    assert report["launch"]["attempted"] is False
    assert "--json" in report["launch"]["blocked_reason"]
    assert "--launch" in report["errors"][0]


def test_start_launch_is_blocked_outside_interactive_terminal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    monkeypatch.setattr(start_mod, "_is_interactive_terminal", lambda: False)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    result = runner.invoke(app, ["start", "--repo", str(repo), "--launch"])

    assert result.exit_code == 1
    assert "Launch skipped" in result.stdout
    assert "interactive terminal" in result.stdout


def test_start_launches_when_explicit_and_interactive(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    monkeypatch.setattr(start_mod, "_is_interactive_terminal", lambda: True)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    launched: dict[str, Any] = {}

    def fake_launch(path: Path) -> int:
        launched["path"] = str(path)
        return 0

    monkeypatch.setattr(start_mod, "_launch_claude", fake_launch)

    result = runner.invoke(app, ["start", "--repo", str(repo), "--launch"])

    assert result.exit_code == 0
    assert launched["path"] == str(repo.resolve())
    assert "Launch" in result.stdout
    assert "claude exited 0" in result.stdout


def test_start_display_command_is_os_aware(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "path with spaces"

    monkeypatch.setattr(start_mod.os, "name", "posix")  # type: ignore[attr-defined]
    assert start_mod._display_command(repo) == f"cd {shlex.quote(str(repo))} && claude"

    monkeypatch.setattr(start_mod.os, "name", "nt")  # type: ignore[attr-defined]
    assert start_mod._display_command(repo).startswith("cd /d ")
    assert start_mod._display_command(repo).endswith(" && claude")


def test_start_runtime_guidance_is_plugin_first(tmp_path: Path, monkeypatch) -> None:
    # #924: the handoff payload carries an always-on plugin-first grounding fact
    # so an agent reading `mb start --json` knows both the user command and the
    # official plugin smoke command.
    monkeypatch.setattr(start_mod, "_which", _with_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    result = runner.invoke(app, ["start", "--repo", str(repo), "--json"])

    report = json.loads(result.stdout)
    guidance = report["runtime"]["guidance"]
    assert "normal Claude Code command remains /mb-start" in guidance
    assert "/mainbranch:mb-start" in guidance
    assert "claude plugin marketplace add dmthepm/mainbranch" in guidance
    assert "cloud" in guidance.lower()
