"""``mb doctor`` smoke + cloud-backup detection."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import codex as codex_mod
from mb import doctor as doctor_mod
from mb import engine as engine_mod
from mb import migration_lint
from mb.cli import app
from mb.doctor import _detect_cloud_paths, _repo_layout_check, run
from mb.init import run as init_run

runner = CliRunner()


@pytest.fixture(autouse=True)
def codex_missing_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codex_mod, "_which", lambda name: "" if name == "codex" else None)


def _with_codex(name: str) -> str:
    if name == "codex":
        return "/usr/local/bin/codex"
    return ""


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


def _codex_runtime_path_mismatch_same_version() -> dict[str, Any]:
    return {
        "checked": True,
        "ok": False,
        "state": "warn",
        "shell": "/bin/zsh",
        "command": "command -v mb && mb --version",
        "path": "/tmp/smoke/bin/mb",
        "version": "0.3.34",
        "active_path": "/Users/example/.local/bin/mb",
        "active_version": "0.3.34",
        "path_mismatch": True,
        "version_mismatch": False,
        "mismatch": True,
        "error": "",
        "summary": "Login-shell runtime resolves a different mb than this process.",
        "repair": "Put the current Main Branch install earlier on the login-shell PATH.",
        "safe_to_share": True,
    }


def _codex_plugin_list_result(repo: Path, *, installed: bool = True) -> dict[str, Any]:
    marketplace = codex_mod.marketplace_path(repo)
    plugin = codex_mod.plugin_manifest_path(repo).parent
    status = "installed, enabled" if installed else "not installed"
    return {
        "ok": True,
        "returncode": 0,
        "stdout": (
            f"Marketplace `{codex_mod.CODEX_MARKETPLACE_NAME}`\n"
            f"{marketplace}\n\n"
            "PLUGIN                                    STATUS              VERSION  PATH\n"
            f"{codex_mod.CODEX_PLUGIN_SELECTOR}  {status}  0.1.0  {plugin}\n"
        ),
        "stderr": "",
        "command": f"codex plugin list --marketplace {codex_mod.CODEX_MARKETPLACE_NAME}",
    }


def _prepare_codex_global_plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAINBRANCH_CODEX_PLUGIN_ROOT", str(tmp_path / "codex-global"))
    codex_mod.write_global_plugin_source()


def _setup_git(repo: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def _prepare_codex_global_skill_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAINBRANCH_CODEX_PLUGIN_ROOT", str(tmp_path / "codex-global"))
    monkeypatch.setenv("MAINBRANCH_CODEX_SKILLS_ROOT", str(tmp_path / "codex-skills"))


def _write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_doctor_runs_on_empty_dir(tmp_path: Path) -> None:
    report = run(path=str(tmp_path))
    assert "checks" in report
    names = {c["name"] for c in report["checks"]}
    assert {"claude-code", "github-context", "network", "anti-cloud-backup"}.issubset(names)
    assert "skill-wiring" in names
    assert "mainbranch-version" in names
    assert "repo-layout" in names
    assert "schema-version" in names
    assert "update" in report


def test_doctor_reuses_github_context_for_integrations(tmp_path: Path, monkeypatch) -> None:
    calls = 0

    def fake_context(repo: Path) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "ok": False,
            "state": "missing_github_remote",
            "summary": "This repo does not have a GitHub origin remote.",
            "repair": "Add a GitHub origin remote before relying on GitHub tasks or proposals.",
            "repair_command": "gh repo create --source . --remote origin --push",
            "safe_to_share": True,
        }

    monkeypatch.setattr(
        doctor_mod.connect_mod,  # type: ignore[attr-defined]
        "github_context",
        fake_context,
    )

    report = run(path=str(tmp_path))

    assert calls == 1
    assert report["integrations"]["github"]["state"] == "missing_github_remote"


def test_cloud_path_detection_via_symlink(tmp_path: Path, monkeypatch) -> None:
    # Build a fake repo whose core/finance/ is a symlink pointing at a path
    # whose realpath includes "Dropbox".
    fake_home = tmp_path / "home"
    cloud = fake_home / "Dropbox" / "Stuff"
    cloud.mkdir(parents=True)
    repo = tmp_path / "biz"
    (repo / "core").mkdir(parents=True)
    (repo / "core" / "finance").symlink_to(cloud)

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    hits = _detect_cloud_paths(repo)
    assert "Dropbox" in hits


def test_doctor_clean_finance_passes(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    (repo / "core" / "finance").mkdir(parents=True)
    report = run(path=str(repo))
    cloud = next(c for c in report["checks"] if c["name"] == "anti-cloud-backup")
    assert cloud["ok"] is True


def test_doctor_skill_wiring_passes_after_init(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    report = run(path=str(repo))
    wiring = next(c for c in report["checks"] if c["name"] == "skill-wiring")
    assert wiring["ok"] is True
    codex_agents = next(c for c in report["checks"] if c["name"] == "codex-agents-md")
    assert codex_agents["ok"] is True
    checkpoint_hook = next(c for c in report["checks"] if c["name"] == "checkpoint-hook")
    assert checkpoint_hook["ok"] is True


def test_repo_layout_warns_on_legacy_reference_core(tmp_path: Path) -> None:
    repo = tmp_path / "legacy"
    (repo / "reference" / "core").mkdir(parents=True)

    check = _repo_layout_check(repo)

    assert check["ok"] is False
    assert check["severity"] == "warn"
    assert "legacy reference/core" in check["detail"]


def test_repo_layout_accepts_current_core(tmp_path: Path) -> None:
    repo = tmp_path / "current"
    (repo / "core").mkdir(parents=True)

    check = _repo_layout_check(repo)

    assert check["ok"] is True
    assert "current core/" in check["detail"]


def test_doctor_warns_on_schema_drift(tmp_path: Path) -> None:
    repo = tmp_path / "legacy"
    (repo / "reference" / "core").mkdir(parents=True)

    report = run(path=str(repo))

    check = next(c for c in report["checks"] if c["name"] == "schema-version")
    assert check["ok"] is False
    assert check["severity"] == "warn"
    assert "mb migrate --check" in check["detail"]


def test_doctor_blocks_future_schema(tmp_path: Path) -> None:
    repo = tmp_path / "future"
    (repo / ".mb").mkdir(parents=True)
    (repo / ".mb" / "schema_version").write_text("9.0\n", encoding="utf-8")

    report = run(path=str(repo))

    check = next(c for c in report["checks"] if c["name"] == "schema-version")
    assert check["ok"] is False
    assert check["severity"] == "error"
    assert "newer than this engine supports" in check["detail"]


def test_doctor_json_and_human_output_include_required_update(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        doctor_mod,
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

    report = doctor_mod.run(path=str(tmp_path))

    assert report["ok"] is False
    assert report["update"]["severity"] == "required"
    version_check = next(
        check for check in report["checks"] if check["name"] == "mainbranch-version"
    )
    assert version_check["severity"] == "error"
    assert "minimum supported" in version_check["detail"]

    doctor_mod.render_human(report)
    output = capsys.readouterr().out
    assert "Update required." in output
    assert "pipx upgrade mainbranch" in output


def test_doctor_required_update_unknown_install_is_mode_neutral(
    tmp_path: Path, monkeypatch
) -> None:
    # #965: with no known install mode there is no command to name, and the
    # check must not render an empty one.
    from mb.freshness import package_update_status

    monkeypatch.setattr(
        doctor_mod,
        "package_update_status",
        lambda repo: package_update_status(
            repo, installed_version="0.1.0", latest_version="0.6.2", mode="unknown"
        ),
    )

    report = doctor_mod.run(path=str(tmp_path))

    version_check = next(
        check for check in report["checks"] if check["name"] == "mainbranch-version"
    )
    assert "Run ``" not in version_check["detail"]
    assert "with the tool that installed it" in version_check["detail"]


def test_doctor_flags_final_release_for_rc_install(tmp_path: Path, monkeypatch) -> None:
    # #1043: version_key dropped the pre-release marker, so an rc install
    # treated the final release as equal and never saw the update. The
    # mocked dict uses severity "current" so the fallback comparison in
    # _mainbranch_version_check (not the severity branch) is exercised.
    monkeypatch.setattr(doctor_mod, "install_mode", lambda: "wheel")
    monkeypatch.setattr(
        doctor_mod,
        "package_update_status",
        lambda repo: {
            "installed": "0.6.3rc1",
            "latest": "0.6.3",
            "minimum_supported": "0.5.0",
            "severity": "current",
            "command": "mb update",
            "post_update_commands": [],
            "reason": "Installed version is current.",
        },
    )

    report = doctor_mod.run(path=str(tmp_path))

    version_check = next(
        check for check in report["checks"] if check["name"] == "mainbranch-version"
    )
    assert version_check["ok"] is False
    assert version_check["severity"] == "warn"
    assert "installed 0.6.3rc1, latest is 0.6.3" in version_check["detail"]


def test_doctor_does_not_flag_rc_for_final_install(tmp_path: Path, monkeypatch) -> None:
    # #1043: the reverse must hold too: a final install is never told that
    # an rc of the same release is an update.
    monkeypatch.setattr(doctor_mod, "install_mode", lambda: "wheel")
    monkeypatch.setattr(
        doctor_mod,
        "package_update_status",
        lambda repo: {
            "installed": "0.6.3",
            "latest": "0.6.3rc1",
            "minimum_supported": "0.5.0",
            "severity": "current",
            "command": "mb update",
            "post_update_commands": [],
            "reason": "Installed version is current.",
        },
    )

    report = doctor_mod.run(path=str(tmp_path))

    version_check = next(
        check for check in report["checks"] if check["name"] == "mainbranch-version"
    )
    assert version_check["ok"] is True


def test_doctor_command_still_runs_after_repair_subcommand_added(tmp_path: Path) -> None:
    result = runner.invoke(app, ["doctor", str(tmp_path), "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    assert payload["repo"] == str(tmp_path.resolve())
    assert "checks" in payload


def test_doctor_repair_plan_is_read_only_for_status_marker(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    marker = repo / ".mb" / "last-status-seen.json"
    assert not marker.exists()

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    assert payload["schema"] == "mb.doctor.repair"
    assert payload["read_only"] is True
    assert payload["plan_interpretation"]["state"] in {
        "clear",
        "plan_produced_with_findings",
        "plan_produced_with_blockers",
    }
    assert not marker.exists()


def test_doctor_repair_adds_connect_yaml_to_gitignore(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    gitignore = repo / ".gitignore"
    gitignore.write_text(
        gitignore.read_text(encoding="utf-8").replace(".mb/connect.yaml\n", ""),
        encoding="utf-8",
    )

    plan = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert plan.exit_code in {0, 1}
    plan_payload = json.loads(plan.stdout)
    checks = {
        check["name"]: check
        for section in plan_payload["sections"]
        if section["id"] == "gitignore"
        for check in section["checks"]
    }
    assert checks[".mb/connect.yaml"]["state"] == "warn"

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--apply", "--json"])

    assert result.exit_code in {0, 1}
    assert ".mb/connect.yaml" in gitignore.read_text(encoding="utf-8")


def test_doctor_repair_protects_legacy_vip_local_state(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    gitignore = repo / ".gitignore"
    gitignore.write_text(
        gitignore.read_text(encoding="utf-8").replace(".vip/local.yaml\n", ""),
        encoding="utf-8",
    )
    vip_local = repo / ".vip" / "local.yaml"
    vip_local.parent.mkdir()
    vip_local.write_text("current_offer: community\n", encoding="utf-8")
    doctor_mod._run_git(repo, ["add", "-f", ".vip/local.yaml"])

    plan = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert plan.exit_code in {0, 1}
    plan_payload = json.loads(plan.stdout)
    checks = {
        check["name"]: check
        for section in plan_payload["sections"]
        if section["id"] == "gitignore"
        for check in section["checks"]
    }
    assert checks[".vip/local.yaml"]["summary"] == "tracked; repair will untrack"

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--apply", "--json"])

    assert result.exit_code in {0, 1}
    assert ".vip/local.yaml" in gitignore.read_text(encoding="utf-8")
    assert vip_local.exists()
    assert not doctor_mod._run_git(repo, ["ls-files", "--error-unmatch", ".vip/local.yaml"])["ok"]


def test_doctor_repair_plan_reports_missing_checkpoint_hook(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    (repo / ".git" / "hooks" / "commit-msg").unlink()

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "checkpoint-hook")
    assert section["state"] == "warn"
    actions = {action["id"]: action for action in payload["actions"]}
    assert actions["checkpoint-hook-install"]["safe_to_apply"] is True


def test_doctor_repair_apply_restores_missing_claude_worktree_start_wiring(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    # Plain git for setup: the product helper has a short timeout and its
    # commit runs the checkpoint hook, which needs `mb` on PATH.
    _setup_git(repo, "config", "user.email", "test@example.com")
    _setup_git(repo, "config", "user.name", "Test User")
    _setup_git(repo, "add", "AGENTS.md", "CLAUDE.md", "README.md", "core")
    _setup_git(repo, "commit", "--no-verify", "-m", "[updated] setup -- baseline")
    worktree = repo / ".claude" / "worktrees" / "repair-start"
    _setup_git(repo, "worktree", "add", "-b", "repair-start", str(worktree))

    assert not (worktree / ".claude" / "skills" / "mb-start" / "SKILL.md").exists()

    plan = doctor_mod.repair_plan(repo=worktree)
    section = next(section for section in plan["sections"] if section["id"] == "claude-wiring")
    start_check = next(
        check for check in section["checks"] if check["name"] == "project-local-skills"
    )
    actions = {action["id"]: action for action in plan["actions"]}

    assert section["state"] == "error"
    assert "git worktree" in start_check["summary"]
    assert "worktrees do not inherit" in start_check["summary"]
    assert "mb skill link --repo ." in start_check["summary"]
    assert "project-local /mb-start bridge" in start_check["summary"]
    assert start_check["fallback_commands"] == [
        f"mb start{_flag(worktree)} --json",
        f"mb doctor repair{_flag(worktree)} --plan",
        f"mb doctor repair{_flag(worktree)} --apply",
    ]
    assert actions["skill-link"]["command"] == (
        f"mb doctor repair{_flag(worktree)} --apply --only claude"
    )
    assert "/mb-start" in actions["skill-link"]["reason"]

    applied = doctor_mod.repair_apply(repo=worktree, only="claude")
    applied_actions = {action["id"]: action for action in applied["applied_actions"]}

    assert "skill-link" in applied_actions
    assert (worktree / ".claude" / "skills" / "mb-start" / "SKILL.md").is_file()
    assert engine_mod.link_status(worktree)["ok"] is True


def test_doctor_repair_plan_reports_missing_codex_agents_md(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    (repo / "AGENTS.md").unlink()

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "codex-wiring")
    assert section["state"] == "warn"
    agents_check = next(check for check in section["checks"] if check["name"] == "AGENTS.md")
    assert agents_check["state"] == "warn"
    actions = {action["id"]: action for action in payload["actions"]}
    assert actions["codex-agents-md"]["safe_to_apply"] is True
    assert actions["codex-agents-md"]["command"] == (
        f"mb doctor repair{_flag(repo)} --apply --only codex"
    )
    assert "AGENTS.md" in actions["codex-agents-md"]["writes"]


def test_doctor_repair_only_codex_filters_unrelated_related_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_codex_global_skill_roots(tmp_path, monkeypatch)
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    (repo / "AGENTS.md").write_text("# stale\n\nNo facts here.\n", encoding="utf-8")
    decision = repo / "decisions" / "2026-05-22-choice.md"
    _write_md(
        decision,
        "---\n"
        "type: decision\n"
        "date: 2026-05-22\n"
        "status: proposed\n"
        "linked_offers:\n"
        "  - ../core/offer.md\n"
        "---\n\n"
        "# Choice\n",
    )

    plan_result = runner.invoke(
        app,
        ["doctor", "repair", "--repo", str(repo), "--plan", "--only", "codex", "--json"],
    )

    assert plan_result.exit_code in {0, 1}
    plan = json.loads(plan_result.stdout)
    assert plan["only"] == "codex"
    assert [section["id"] for section in plan["sections"]] == ["codex-wiring", "git"]
    assert [action["id"] for action in plan["actions"]] == [
        "codex-agents-md",
        "codex-global-skill",
    ]

    apply_result = runner.invoke(
        app,
        ["doctor", "repair", "--repo", str(repo), "--apply", "--only", "codex", "--json"],
    )

    assert apply_result.exit_code in {0, 1}
    payload = json.loads(apply_result.stdout)
    applied = {action["id"]: action for action in payload["applied_actions"]}
    assert set(applied) == {"codex-agents-md", "codex-global-skill"}
    assert applied["codex-agents-md"]["command"] == (
        f"mb doctor repair{_flag(repo)} --apply --only codex"
    )
    assert "## Related links" not in decision.read_text(encoding="utf-8")


def test_doctor_repair_plan_lists_agent_surfaces_and_scope_choices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_codex_global_skill_roots(tmp_path, monkeypatch)
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    (repo / "AGENTS.md").write_text("# stale\n\nNo facts here.\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    surfaces = {surface["id"]: surface for surface in payload["agent_surfaces"]["surfaces"]}
    assert payload["agent_surfaces"]["scope_choices"] == [
        f"mb doctor repair{_flag(repo)} --plan --only claude",
        f"mb doctor repair{_flag(repo)} --plan --only codex",
        f"mb doctor repair{_flag(repo)} --plan --all-agents",
    ]
    assert surfaces["claude"]["label"] == "Claude Code project-local skills"
    assert surfaces["codex"]["label"] == "Codex global mb-* skills and repo AGENTS.md"
    assert "codex-agents-md" in surfaces["codex"]["planned_actions"]
    assert "codex-global-skill" in surfaces["codex"]["planned_actions"]
    assert "AGENTS.md" in surfaces["codex"]["touched_files"]
    assert str(tmp_path / "codex-skills") in surfaces["codex"]["touched_files"]


def test_doctor_repair_only_claude_filters_codex_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_codex_global_skill_roots(tmp_path, monkeypatch)
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    (repo / "AGENTS.md").write_text("# stale\n\nNo facts here.\n", encoding="utf-8")

    result = runner.invoke(
        app, ["doctor", "repair", "--repo", str(repo), "--plan", "--only", "claude", "--json"]
    )

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    assert payload["only"] == "claude"
    assert [section["id"] for section in payload["sections"]] == ["claude-wiring", "git"]
    assert all(not action["id"].startswith("codex-") for action in payload["actions"])


def _agents_md_without_end_marker(repo: Path) -> str:
    """Current guidance whose end marker a person deleted, plus their notes (#1052)."""
    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    # Guidance from an older template, so the repair is due.
    stale = text.replace(codex_mod.guidance_template_hash(), "0000000000000000")
    broken = stale.replace(codex_mod.AGENTS_MANAGED_END + "\n", "") + "\n## Our notes\n\nKeep.\n"
    (repo / "AGENTS.md").write_text(broken, encoding="utf-8")
    return broken


def _codex_repair(repo: Path, mode: str) -> dict[str, Any]:
    result = runner.invoke(
        app, ["doctor", "repair", "--repo", str(repo), mode, "--only", "codex", "--json"]
    )
    assert result.exit_code in {0, 1}, result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    return payload


def test_doctor_codex_repair_that_would_refuse_is_an_operator_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_codex_global_skill_roots(tmp_path, monkeypatch)
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    broken = _agents_md_without_end_marker(repo)

    plan = _codex_repair(repo, "--plan")

    actions = {action["id"]: action for action in plan["actions"]}
    agents_action = actions["codex-agents-md"]
    assert agents_action["safe_to_apply"] is False
    assert agents_action["audience"] == "operator_decision"
    assert agents_action["writes"] == []
    assert agents_action["operations"] == []
    assert [item["code"] for item in agents_action["refused"]] == ["missing_end_marker"]
    entries = [item for item in plan["operator_actions"] if item.get("id") == "codex-agents-md"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["command"] == codex_mod.repair_command(repo)
    assert "no end marker" in entry["reason"]
    assert codex_mod.AGENTS_MANAGED_END in entry["manual_step"]
    assert entry["manual_step"] in entry["note"]

    applied = _codex_repair(repo, "--apply")

    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == broken
    agents_applied = next(
        item for item in applied["applied_actions"] if item["id"] == "codex-agents-md"
    )
    assert agents_applied["applied"] is False
    assert agents_applied["safe_to_apply"] is False
    assert agents_applied["result"]["refused"][0]["code"] == "missing_end_marker"
    assert any(item.get("id") == "codex-agents-md" for item in applied["operator_actions"])


def test_doctor_codex_repair_keeping_a_persons_file_is_an_operator_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_codex_global_skill_roots(tmp_path, monkeypatch)
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    folder = repo / ".agents" / "skills" / "main-branch"
    folder.mkdir(parents=True)
    (folder / "my-notes.md").write_text("Mine.\n", encoding="utf-8")
    (folder / "SKILL.md").write_text(
        codex_mod.render_codex_global_skill_md("main-branch"), encoding="utf-8"
    )

    plan = _codex_repair(repo, "--plan")

    agents_action = next(item for item in plan["actions"] if item["id"] == "codex-agents-md")
    assert agents_action["safe_to_apply"] is False
    assert agents_action["kept"] == [".agents/skills/main-branch/my-notes.md"]
    assert agents_action["operations"] == [
        {"op": "delete", "path": str((folder / "SKILL.md").resolve())}
    ]
    entry = next(item for item in plan["operator_actions"] if item.get("id") == "codex-agents-md")
    assert entry["changes"] == [".agents/skills/main-branch/SKILL.md"]
    assert ".agents/skills/main-branch/my-notes.md" in entry["reason"]

    _codex_repair(repo, "--apply")

    assert (folder / "my-notes.md").read_text(encoding="utf-8") == "Mine.\n"
    assert not (folder / "SKILL.md").exists()


def test_doctor_codex_repair_of_a_plain_agents_md_stays_an_agent_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_codex_global_skill_roots(tmp_path, monkeypatch)
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    (repo / "AGENTS.md").write_text("# Our notes\n\nKeep.\n", encoding="utf-8")

    plan = _codex_repair(repo, "--plan")

    agents_action = next(item for item in plan["actions"] if item["id"] == "codex-agents-md")
    assert agents_action["safe_to_apply"] is True
    assert agents_action["refused"] == []
    assert agents_action["kept"] == []
    assert plan["operator_actions"] == []

    _codex_repair(repo, "--apply")

    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert text.startswith(codex_mod.AGENTS_MANAGED_BEGIN)
    assert text.endswith("# Our notes\n\nKeep.\n")


def test_doctor_repair_rejects_mixed_agent_scope(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "doctor",
            "repair",
            "--repo",
            str(tmp_path),
            "--plan",
            "--only",
            "codex",
            "--all-agents",
        ],
    )

    assert result.exit_code == 2
    assert "--only cannot be combined with --all-agents" in result.stderr


def test_doctor_repair_apply_all_agents_installs_codex_without_codex_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_codex_global_skill_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(codex_mod, "_which", lambda name: "" if name == "codex" else None)
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    (repo / "AGENTS.md").write_text("# stale\n\nNo facts here.\n", encoding="utf-8")
    old_playbook_skill = tmp_path / "codex-skills" / "weekly-review" / "SKILL.md"
    old_playbook_skill.parent.mkdir(parents=True, exist_ok=True)
    old_playbook_skill.write_bytes(
        (
            Path(__file__).parent / "fixtures/codex_released/0.3.36/skills/weekly-review/SKILL.md"
        ).read_bytes()
    )

    result = runner.invoke(
        app, ["doctor", "repair", "--repo", str(repo), "--apply", "--all-agents", "--json"]
    )

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    applied = {action["id"]: action for action in payload["applied_actions"]}
    assert "codex-agents-md" in applied
    assert "codex-global-skill" in applied
    receipt = payload["receipt"]
    assert "mb-start" in receipt["installed_skills"]
    assert "weekly-review" not in receipt["installed_skills"]
    assert "main-branch-owner-loop" not in receipt["installed_skills"]
    assert str(tmp_path / "codex-skills") in receipt["touched_files"]
    assert (tmp_path / "codex-skills" / "mb-start" / "SKILL.md").is_file()
    assert not old_playbook_skill.exists()


def test_doctor_repair_apply_default_does_not_silently_write_agent_surfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_codex_global_skill_roots(tmp_path, monkeypatch)
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    (repo / "AGENTS.md").write_text("# stale\n\nNo facts here.\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--apply", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    applied_ids = {action["id"] for action in payload["applied_actions"]}
    assert "codex-agents-md" not in applied_ids
    assert "codex-global-skill" not in applied_ids
    assert not (tmp_path / "codex-skills" / "mb-start" / "SKILL.md").exists()
    assert payload["receipt"]["skipped_surfaces"] == [
        f"claude: run mb doctor repair{_flag(repo)} --apply --only claude",
        f"codex: run mb doctor repair{_flag(repo)} --apply --only codex",
    ]


def test_doctor_repair_plan_marks_codex_runtime_info_when_codex_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(codex_mod, "_which", lambda name: "" if name == "codex" else None)
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
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "codex-wiring")
    runtime_check = next(
        check for check in section["checks"] if check["name"] == "codex-runtime-mb"
    )
    assert runtime_check["state"] == "info"
    assert "waits until Codex CLI is installed" in runtime_check["summary"]
    assert runtime_check["repair"] == ""


def test_doctor_repair_plan_installs_missing_codex_global_skills(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(codex_mod, "_which", _with_codex)
    monkeypatch.setattr(codex_mod, "_login_shell_mb_diagnostics", _codex_runtime_ok)
    _prepare_codex_global_skill_roots(tmp_path, monkeypatch)
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")

    result = runner.invoke(
        app, ["doctor", "repair", "--repo", str(repo), "--plan", "--only", "codex", "--json"]
    )

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    actions = {action["id"]: action for action in payload["actions"]}
    assert "codex-global-skill" in actions
    assert actions["codex-global-skill"]["safe_to_apply"] is True
    assert actions["codex-global-skill"]["command"] == (
        f"mb doctor repair{_flag(repo)} --apply --only codex"
    )
    section = next(section for section in payload["sections"] if section["id"] == "codex-wiring")
    skill_check = next(
        check for check in section["checks"] if check["name"] == "codex-global-skill"
    )
    assert skill_check["state"] == "warn"
    assert "mb-start/SKILL.md" in skill_check["missing"]


def test_doctor_repair_plan_installs_missing_codex_global_skills_with_runtime_path_warning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(codex_mod, "_which", _with_codex)
    monkeypatch.setattr(
        codex_mod,
        "_login_shell_mb_diagnostics",
        _codex_runtime_path_mismatch_same_version,
    )
    _prepare_codex_global_skill_roots(tmp_path, monkeypatch)
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")

    result = runner.invoke(
        app, ["doctor", "repair", "--repo", str(repo), "--plan", "--only", "codex", "--json"]
    )

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    actions = {action["id"]: action for action in payload["actions"]}
    assert "codex-global-skill" in actions
    section = next(section for section in payload["sections"] if section["id"] == "codex-wiring")
    runtime_check = next(
        check for check in section["checks"] if check["name"] == "codex-runtime-mb"
    )
    skill_check = next(
        check for check in section["checks"] if check["name"] == "codex-global-skill"
    )
    assert runtime_check["state"] == "warn"
    assert skill_check["state"] == "warn"


def test_doctor_repair_apply_installs_missing_codex_global_skills(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(codex_mod, "_which", _with_codex)
    monkeypatch.setattr(codex_mod, "_login_shell_mb_diagnostics", _codex_runtime_ok)
    _prepare_codex_global_skill_roots(tmp_path, monkeypatch)
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")

    result = runner.invoke(
        app, ["doctor", "repair", "--repo", str(repo), "--apply", "--only", "codex", "--json"]
    )

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    applied = {action["id"]: action for action in payload["applied_actions"]}
    assert "codex-global-skill" in applied
    assert applied["codex-global-skill"]["state"] == "ok"
    assert applied["codex-global-skill"]["command"] == (
        f"mb doctor repair{_flag(repo)} --apply --only codex"
    )
    status = applied["codex-global-skill"]["result"]["status"]
    assert status["skills"]["mb-start"]["ok"] is True
    assert status["skills"]["mb-ads"]["ok"] is True


def test_doctor_repair_apply_installs_missing_codex_global_skills_with_runtime_path_warning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(codex_mod, "_which", _with_codex)
    monkeypatch.setattr(
        codex_mod,
        "_login_shell_mb_diagnostics",
        _codex_runtime_path_mismatch_same_version,
    )
    _prepare_codex_global_skill_roots(tmp_path, monkeypatch)
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")

    result = runner.invoke(
        app, ["doctor", "repair", "--repo", str(repo), "--apply", "--only", "codex", "--json"]
    )

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    applied = {action["id"]: action for action in payload["applied_actions"]}
    assert "codex-global-skill" in applied
    assert applied["codex-global-skill"]["state"] == "ok"


def test_doctor_repair_plan_reports_stale_codex_lifecycle_guidance(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    agents = repo / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8").replace(
            "## Codex Lifecycle Workflow Index",
            "## Old Codex Notes",
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "codex-wiring")
    agents_check = next(check for check in section["checks"] if check["name"] == "AGENTS.md")
    assert agents_check["state"] == "warn"
    assert agents_check["lifecycle_discovery_ok"] is False
    assert "## Codex Lifecycle Workflow Index" in agents_check["missing_lifecycle_guidance"]
    actions = {action["id"]: action for action in payload["actions"]}
    assert "codex-agents-md" in actions


def test_doctor_repair_plan_reports_stale_codex_guidance_metadata(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    agents = repo / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8").replace(
            "template_hash=" + codex_mod.guidance_template_hash(),
            "template_hash=stale0000000000",
            1,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "codex-wiring")
    agents_check = next(check for check in section["checks"] if check["name"] == "AGENTS.md")
    assert agents_check["state"] == "warn"
    assert agents_check["guidance_metadata_ok"] is False
    assert agents_check["guidance_template_hash_ok"] is False
    assert agents_check["generated_version_ok"] is False
    assert agents_check["expected_template_hash"] == codex_mod.guidance_template_hash()
    assert "mainbranch:codex-guidance" in agents_check["expected_guidance_metadata"]
    actions = {action["id"]: action for action in payload["actions"]}
    assert "codex-agents-md" in actions


def test_codex_guidance_currentness_does_not_depend_on_package_patch_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")

    monkeypatch.setattr(codex_mod, "__version__", "99.99.99")

    status = codex_mod.instructions_status(repo)

    assert status["ok"] is True
    assert status["guidance_metadata_ok"] is True
    assert status["expected_version_marker"] == ""


def test_doctor_repair_plan_reports_pre_engine_source_boundary_codex_guidance(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    agents = repo / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8").replace(
            "does not need to contain that engine source file. ",
            "",
            1,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "codex-wiring")
    agents_check = next(check for check in section["checks"] if check["name"] == "AGENTS.md")
    assert agents_check["state"] == "warn"
    assert agents_check["lifecycle_discovery_ok"] is False
    assert (
        "does not need to contain that engine source file"
        in agents_check["missing_lifecycle_guidance"]
    )
    actions = {action["id"]: action for action in payload["actions"]}
    assert actions["codex-agents-md"]["safe_to_apply"] is True
    assert "AGENTS.md" in actions["codex-agents-md"]["writes"]


def test_doctor_repair_plan_reports_custom_codex_agents_missing_source_item(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    agents = repo / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8").replace("- `runtime.codex_cli`\n", "", 1)
        + "\n## Local Notes\n\nKeep this operator-specific note.\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "codex-wiring")
    agents_check = next(check for check in section["checks"] if check["name"] == "AGENTS.md")
    assert agents_check["state"] == "warn"
    assert agents_check["lifecycle_discovery_ok"] is False
    assert "- `runtime.codex_cli`" in agents_check["missing_lifecycle_guidance"]
    actions = {action["id"]: action for action in payload["actions"]}
    assert "codex-agents-md" in actions


def test_doctor_repair_apply_refreshes_codex_agents_md(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    (repo / "AGENTS.md").write_text("# stale\n\nNo facts here.\n", encoding="utf-8")

    result = runner.invoke(
        app, ["doctor", "repair", "--repo", str(repo), "--apply", "--only", "codex", "--json"]
    )

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    applied = {action["id"]: action for action in payload["applied_actions"]}
    assert "codex-agents-md" in applied
    agents_text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Codex Start Workflow" in agents_text
    assert "## Codex Lifecycle Workflow Index" in agents_text
    assert "## Codex Status Workflow" in agents_text
    assert "## Codex Think Route" in agents_text
    assert "mb status --json --peek" in agents_text
    assert not (repo / ".agents" / "plugins").exists()
    assert not (repo / ".agents" / "skills" / "main-branch-owner-loop").exists()


def test_doctor_repair_removes_stale_repo_local_codex_plugin(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    command = repo / ".agents" / "plugins" / "main-branch-owner-loop" / "commands" / "mb-start.md"
    command.parent.mkdir(parents=True, exist_ok=True)
    # The shim exactly as 0.3.30 wrote it; only proven files are removed.
    command.write_bytes(
        (
            Path(__file__).parent / "fixtures/codex_released/0.3.30/repo/.agents/plugins"
            "/main-branch-owner-loop/commands/mb-start.md"
        ).read_bytes()
    )

    plan_result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])
    assert plan_result.exit_code in {0, 1}
    plan = json.loads(plan_result.stdout)
    actions = {action["id"]: action for action in plan["actions"]}
    assert "codex-agents-md" in actions

    apply_result = runner.invoke(
        app, ["doctor", "repair", "--repo", str(repo), "--apply", "--only", "codex", "--json"]
    )
    assert apply_result.exit_code in {0, 1}
    assert not command.exists()


def test_doctor_repair_preserves_custom_codex_agents_md_when_contract_is_current(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    agents = repo / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8")
        + "\n## Local Notes\n\nKeep this operator-specific note.\n",
        encoding="utf-8",
    )

    plan_result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])
    assert plan_result.exit_code in {0, 1}
    plan = json.loads(plan_result.stdout)
    actions = {action["id"]: action for action in plan["actions"]}
    assert "codex-agents-md" not in actions

    apply_result = runner.invoke(
        app, ["doctor", "repair", "--repo", str(repo), "--apply", "--json"]
    )
    assert apply_result.exit_code in {0, 1}
    applied = {
        action["id"]: action for action in json.loads(apply_result.stdout)["applied_actions"]
    }
    assert "codex-agents-md" not in applied
    assert "Keep this operator-specific note." in agents.read_text(encoding="utf-8")


def test_doctor_repair_apply_installs_checkpoint_hook(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    hook = repo / ".git" / "hooks" / "commit-msg"
    hook.unlink()

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--apply", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    applied = {action["id"]: action for action in payload["applied_actions"]}
    assert "checkpoint-hook-install" in applied
    assert hook.exists()
    hook_text = hook.read_text(encoding="utf-8")
    assert "MB_BIN=" in hook_text
    assert '"$MB_CHECKPOINT" checkpoint --validate -' in hook_text


def test_doctor_repair_preserves_existing_checkpoint_hook(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    hook = repo / ".git" / "hooks" / "commit-msg"
    hook.write_text("#!/bin/sh\necho user hook\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--apply", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    actions = {action["id"]: action for action in payload["actions"]}
    assert actions["checkpoint-hook-existing"]["safe_to_apply"] is False
    assert hook.read_text(encoding="utf-8") == "#!/bin/sh\necho user hook\n"


def test_doctor_repair_untracks_existing_connect_yaml(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    connect_path = repo / ".mb" / "connect.yaml"
    connect_path.write_text("version: 1\nrepo_id: legacy\nproviders: {}\n", encoding="utf-8")
    doctor_mod._run_git(repo, ["add", "-f", ".mb/connect.yaml"])

    plan = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert plan.exit_code in {0, 1}
    plan_payload = json.loads(plan.stdout)
    checks = {
        check["name"]: check
        for section in plan_payload["sections"]
        if section["id"] == "gitignore"
        for check in section["checks"]
    }
    assert checks[".mb/connect.yaml"]["summary"] == "tracked; repair will untrack"

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--apply", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    applied = {action["id"]: action for action in payload["applied_actions"]}
    assert "gitignore-local-state-untrack" in applied
    assert connect_path.exists()
    assert not doctor_mod._run_git(repo, ["ls-files", "--error-unmatch", ".mb/connect.yaml"])["ok"]


def test_doctor_warns_on_legacy_campaigns_records(tmp_path: Path) -> None:
    repo = tmp_path / "legacy-pushes"
    init_run(path=str(repo), name="Acme")
    legacy = repo / "campaigns" / "2026-04-spring-launch"
    legacy.mkdir(parents=True)
    (legacy / "campaign.md").write_text(
        "---\nslug: spring-launch\nstatus: active\n---\n# spring launch\n",
        encoding="utf-8",
    )

    report = doctor_mod.run(path=str(repo))

    legacy_check = next(c for c in report["checks"] if c["name"] == "legacy-campaigns")
    assert legacy_check["ok"] is False
    assert legacy_check["severity"] == "warn"
    assert "1 legacy campaign record" in legacy_check["detail"]
    assert f"mb migrate{_flag(repo)} campaigns --plan" in legacy_check["detail"]
    assert legacy_check["legacy_records"] == ["campaigns/2026-04-spring-launch/campaign.md"]


def test_doctor_uses_campaigns_migration_plan_for_ambiguous_artifacts(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "legacy-pushes-with-artifacts"
    init_run(path=str(repo), name="Acme")
    legacy = repo / "campaigns" / "2026-04-15-spring-launch"
    legacy.mkdir(parents=True)
    (legacy / "campaign.md").write_text(
        "---\nslug: spring-launch\nstatus: active\n---\n# spring launch\n",
        encoding="utf-8",
    )
    (legacy / "ads.md").write_text("# ads\n", encoding="utf-8")
    (legacy / "random-notes.md").write_text("# random\n", encoding="utf-8")

    report = doctor_mod.run(path=str(repo))

    legacy_check = next(c for c in report["checks"] if c["name"] == "legacy-campaigns")
    assert legacy_check["ok"] is False
    assert legacy_check["legacy_records"] == ["campaigns/2026-04-15-spring-launch/campaign.md"]
    assert "campaigns/2026-04-15-spring-launch/ads.md" not in legacy_check["ambiguous_files"]
    assert "campaigns/2026-04-15-spring-launch/random-notes.md" in legacy_check["ambiguous_files"]


def test_doctor_clean_repo_has_no_legacy_campaigns_warning(tmp_path: Path) -> None:
    repo = tmp_path / "fresh"
    init_run(path=str(repo), name="Acme")

    report = doctor_mod.run(path=str(repo))

    legacy_check = next(c for c in report["checks"] if c["name"] == "legacy-campaigns")
    # `mb init` no longer scaffolds campaigns/, so there is nothing to warn on.
    assert legacy_check["ok"] is True
    assert legacy_check.get("severity") in {"ok", None}


def test_doctor_repair_plan_exposes_legacy_campaigns_to_pushes_action(tmp_path: Path) -> None:
    repo = tmp_path / "legacy-pushes-repair"
    init_run(path=str(repo), name="Acme")
    legacy = repo / "campaigns" / "2026-04-spring-launch"
    legacy.mkdir(parents=True)
    (legacy / "campaign.md").write_text(
        "---\nslug: spring-launch\nstatus: active\n---\n# spring launch\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    actions = {action["id"]: action for action in payload["actions"]}
    assert "legacy_campaigns_to_pushes" in actions
    item = actions["legacy_campaigns_to_pushes"]
    assert item["mode"] == "read"
    assert item["safe_to_apply"] is True
    assert item["command"] == f"mb migrate{_flag(repo)} campaigns --plan"
    repo_shape = next(section for section in payload["sections"] if section["id"] == "repo-shape")
    legacy_check = next(
        check for check in repo_shape["checks"] if check["name"] == "legacy-campaigns"
    )
    assert legacy_check["state"] == "warn"


def test_doctor_repair_plan_reports_stale_generated_guidance_privately(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "stale-guidance"
    init_run(path=str(repo), name="Acme")
    (repo / "CLAUDE.md").write_text(
        "\n".join(
            [
                "# Acme",
                "",
                "## Folders",
                "",
                "- `reference/` - current business memory and active write target",
                "- `campaigns/` - current coordinated work",
                "",
                "Private customer note that should never appear in lint output.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "migration-drift")
    assert section["state"] == "warn"
    checks = {check["name"]: check for check in section["checks"]}
    assert "stale-claude-reference-guidance" in checks
    assert "stale-claude-campaigns-guidance" in checks
    assert checks["stale-claude-reference-guidance"]["content_included"] is False
    assert "Private customer note" not in result.stdout
    actions = {action["id"]: action for action in payload["actions"]}
    assert actions["migration-drift-review"]["mode"] == "manual"
    assert actions["migration-drift-review"]["safe_to_apply"] is False


def test_doctor_repair_plan_reports_migration_shape_drift(tmp_path: Path) -> None:
    repo = tmp_path / "shape-drift"
    init_run(path=str(repo), name="Acme")
    (repo / "reference" / "core").mkdir(parents=True)
    (repo / "reference" / "core" / "offer.md").write_text("# Legacy offer\n", encoding="utf-8")
    (repo / ".vip").mkdir()
    (repo / ".vip" / "config.yaml").write_text(
        "reference_structure:\n  core: reference/core\n",
        encoding="utf-8",
    )
    legacy = repo / "campaigns" / "2026-04-launch"
    legacy.mkdir(parents=True)
    (legacy / "campaign.md").write_text(
        "---\nslug: launch\nstatus: active\n---\n# Launch\n",
        encoding="utf-8",
    )
    wrong_push = repo / "pushes" / "launch" / "push.md"
    wrong_push.parent.mkdir(parents=True)
    wrong_push.write_text(
        (
            "---\n"
            "type: push\n"
            "slug: launch\n"
            "kind: launch\n"
            "status: active\n"
            "health: unknown\n"
            "goal: {}\n"
            "owner: Devon\n"
            "audience: buyers\n"
            "offer: offer\n"
            "promise: promise\n"
            "---\n"
            "# Push\n"
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "migration-drift")
    codes = {check["name"] for check in section["checks"]}
    assert "legacy-reference-active-content" in codes
    assert "legacy-campaigns-active-content" in codes
    assert "legacy-vip-config" in codes
    assert "push-record-wrong-shape" in codes


def test_doctor_repair_plan_exposes_validation_top_category(tmp_path: Path) -> None:
    repo = tmp_path / "validation-categories"
    init_run(path=str(repo), name="Acme")
    for slug in ("one", "two"):
        offer = repo / "core" / "offers" / slug / "offer.md"
        offer.parent.mkdir(parents=True)
        offer.write_text("---\nstatus: running\n---\n# Offer\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "validation")
    check = section["checks"][0]
    assert "top category: missing_slug" in check["summary"]
    assert check["report"]["validation_categories"]["by_category"]["missing_slug"]["count"] == 2


def test_doctor_repair_plan_reports_related_links_mirror_action(tmp_path: Path) -> None:
    repo = tmp_path / "related-links-plan"
    init_run(path=str(repo), name="Acme")
    _write_md(
        repo / "research" / "2026-05-10-audience.md",
        "---\ndate: 2026-05-10\ntopic: audience\nsource: manual\n---\n# Audience\n",
    )
    _write_md(
        repo / "decisions" / "2026-05-10-audience.md",
        (
            "---\n"
            "date: 2026-05-10\n"
            "status: accepted\n"
            "linked_research:\n"
            "  - research/2026-05-10-audience.md\n"
            "---\n"
            "# Audience decision\n"
        ),
    )

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "related-links")
    assert section["state"] == "warn"
    assert section["checks"][0]["name"] == "decisions/2026-05-10-audience.md"
    actions = {action["id"]: action for action in payload["actions"]}
    action = actions["related-links-mirror"]
    assert action["safe_to_apply"] is True
    assert action["writes"] == ["decisions/2026-05-10-audience.md"]
    assert "validate-frontmatter" not in actions


def test_doctor_repair_apply_adds_related_links_without_deleting_human_links(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "related-links-apply"
    init_run(path=str(repo), name="Acme")
    _write_md(
        repo / "research" / "2026-05-10-audience.md",
        "---\ndate: 2026-05-10\ntopic: audience\nsource: manual\n---\n# Audience Notes\n",
    )
    decision = repo / "decisions" / "2026-05-10-audience.md"
    _write_md(
        decision,
        (
            "---\n"
            "date: 2026-05-10\n"
            "status: accepted\n"
            "linked_research:\n"
            "  - research/2026-05-10-audience.md\n"
            "---\n"
            "# Audience decision\n"
            "\n"
            "## Related links\n"
            "\n"
            "- [Existing manual note](../documents/manual.md) - keep this prose.\n"
            "\n"
            "## Consequences\n"
            "\n"
            "Keep the rest of the file.\n"
        ),
    )

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--apply", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    applied = {action["id"]: action for action in payload["applied_actions"]}
    assert "related-links-mirror" in applied
    text = decision.read_text(encoding="utf-8")
    assert "- [Existing manual note](../documents/manual.md) - keep this prose." in text
    assert "- [audience](../research/2026-05-10-audience.md)" in text
    assert "## Consequences\n\nKeep the rest of the file." in text


def test_doctor_repair_include_migration_requires_apply_guidance(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["doctor", "repair", "--repo", str(tmp_path), "--include-migration", "--plan"],
    )

    assert result.exit_code == 2
    assert "--apply --include-migration" in result.stderr


def test_doctor_repair_plan_reuses_migration_drift_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "reuse-drift"
    init_run(path=str(repo), name="Acme")
    calls = 0

    def fake_lint(path: Path) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "ok": True,
            "repo": str(path),
            "findings": [],
            "summary": {"warnings": 0, "categories": []},
        }

    monkeypatch.setattr(migration_lint, "run", fake_lint)

    doctor_mod.repair_plan(repo)

    assert calls == 1


def test_doctor_repair_plan_exposes_reference_split_truth(tmp_path: Path) -> None:
    repo = tmp_path / "split-truth"
    (repo / "core").mkdir(parents=True)
    (repo / "reference" / "core").mkdir(parents=True)
    (repo / "core" / "offer.md").write_text("# Current offer\n", encoding="utf-8")
    (repo / "reference" / "core" / "offer.md").write_text("# Legacy offer\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "repo-shape")
    reference_check = next(
        check for check in section["checks"] if check["name"] == "reference/core"
    )
    assert reference_check["state"] == "warn"
    assert reference_check["kind"] == "split-truth"
    assert "split truth" in reference_check["summary"]


def test_doctor_repair_plan_reports_stale_vip_local_state(tmp_path: Path) -> None:
    repo = tmp_path / "legacy-vip"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "offers" / "community").mkdir(parents=True)
    (repo / "core" / "offers" / "community" / "offer.md").write_text(
        "---\nslug: community\nstatus: running\n---\n# Community\n",
        encoding="utf-8",
    )
    (repo / ".vip").mkdir()
    (repo / ".vip" / "local.yaml").write_text("current_offer: community\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "offer-topology")
    vip_check = next(check for check in section["checks"] if check["name"] == ".vip/local.yaml")
    assert vip_check["state"] == "warn"
    assert vip_check["kind"] == "legacy-vip-local-state"
    assert vip_check["current_offer_present"] is True
    assert vip_check["value_included"] is False
    assert "community" not in json.dumps(vip_check)
    actions = {action["id"]: action for action in payload["actions"]}
    assert actions["offer-topology-review"]["mode"] == "manual"
    assert actions["offer-topology-review"]["safe_to_apply"] is False


def test_doctor_repair_plan_flags_offer_slug_folder_drift(tmp_path: Path) -> None:
    repo = tmp_path / "offer-drift"
    init_run(path=str(repo), name="Acme")
    offer = repo / "core" / "offers" / "community" / "offer.md"
    offer.parent.mkdir(parents=True)
    offer.write_text(
        "---\nslug: noontide-community\nstatus: running\n---\n# Community\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "offer-topology")
    drift = next(check for check in section["checks"] if check["kind"] == "offer-slug-drift")
    assert drift["state"] == "warn"
    assert drift["folder_slug"] == "community"
    assert drift["declared_slug"] == "noontide-community"


def test_doctor_repair_plan_keeps_normal_multi_offer_repo_quiet(tmp_path: Path) -> None:
    repo = tmp_path / "normal-multi-offer"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "offer.md").write_text("# Brand offer thesis\n", encoding="utf-8")
    for slug in ("community", "agency"):
        offer = repo / "core" / "offers" / slug / "offer.md"
        offer.parent.mkdir(parents=True)
        offer.write_text(f"---\nslug: {slug}\nstatus: running\n---\n# {slug}\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "offer-topology")
    kinds = {check["kind"] for check in section["checks"]}
    assert section["state"] == "ok"
    assert "offer-slug-drift" not in kinds
    assert "multi-offer-review" not in kinds
    assert "brand-offer-slug-overlap" not in kinds


def test_doctor_repair_plan_flags_multi_offer_session_disagreement(tmp_path: Path) -> None:
    repo = tmp_path / "multi-offer"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "offer.md").write_text(
        "---\nslug: community\nstatus: running\n---\n# Brand thesis\n",
        encoding="utf-8",
    )
    for slug in ("community", "agency"):
        offer = repo / "core" / "offers" / slug / "offer.md"
        offer.parent.mkdir(parents=True)
        offer.write_text(f"---\nslug: {slug}\nstatus: running\n---\n# {slug}\n", encoding="utf-8")
    (repo / ".vip").mkdir()
    (repo / ".vip" / "local.yaml").write_text("current_offer: community\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "offer-topology")
    kinds = {check["kind"] for check in section["checks"]}
    assert "multi-offer-review" in kinds
    assert "brand-offer-slug-overlap" in kinds
    assert section["state"] == "warn"


def test_doctor_repair_plan_audits_mixed_vip_yaml_without_values(tmp_path: Path) -> None:
    repo = tmp_path / "legacy-vip-audit"
    init_run(path=str(repo), name="Acme")
    (repo / ".vip").mkdir()
    (repo / ".vip" / "local.yaml").write_text(
        "\n".join(
            [
                "current_offer: community",
                "user:",
                "  name: Example Operator",
                "session:",
                "  show_context_tips: true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / ".vip" / "config.yaml").write_text(
        "\n".join(
            [
                "business_name: Example Business",
                "business_type: community",
                "offer_structure: multi",
                "tools:",
                "  apify:",
                "    status: installed",
                "mcps:",
                "  google_drive:",
                "    required_for: docs",
                "infrastructure:",
                "  site:",
                "    provider: cloudflare",
                "content:",
                "  default_channel: newsletter",
                "skills:",
                "  ads:",
                "    default_count: 5",
                "client_repos:",
                "  example_client: /private/path/redacted",
                "reference_structure:",
                "  core: reference/core",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    before_local = (repo / ".vip" / "local.yaml").read_text(encoding="utf-8")
    before_config = (repo / ".vip" / "config.yaml").read_text(encoding="utf-8")
    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    assert (repo / ".vip" / "local.yaml").read_text(encoding="utf-8") == before_local
    assert (repo / ".vip" / "config.yaml").read_text(encoding="utf-8") == before_config
    payload = json.loads(result.stdout)
    assert payload["read_only"] is True
    section = next(section for section in payload["sections"] if section["id"] == "legacy-vip")
    assert section["state"] == "warn"
    by_name = {check["name"]: check for check in section["checks"]}
    local_entries = {entry["key"]: entry for entry in by_name[".vip/local.yaml"]["entries"]}
    config_entries = {entry["key"]: entry for entry in by_name[".vip/config.yaml"]["entries"]}

    assert local_entries["current_offer"]["classification"] == "local-session-state"
    assert local_entries["user.name"]["classification"] == "machine-local-preference"
    assert local_entries["session.show_context_tips"]["classification"] == (
        "machine-local-session-state"
    )
    assert config_entries["business_name"]["classification"] == "durable-business-truth"
    assert config_entries["tools.apify.status"]["classification"] == "stale-runtime-snapshot"
    assert config_entries["mcps.google_drive.required_for"]["classification"] == (
        "provider-readiness-hint"
    )
    assert config_entries["infrastructure.site.provider"]["classification"] == (
        "provider-or-infra-hint"
    )
    assert config_entries["content.default_channel"]["classification"] == "legacy-skill-default"
    assert config_entries["skills.ads.default_count"]["classification"] == "legacy-skill-default"
    assert config_entries["client_repos.example_client"]["classification"] == "repo-topology-hint"
    assert config_entries["reference_structure.core"]["classification"] == "stale-legacy-layout"
    assert all(entry["value_included"] is False for entry in local_entries.values())
    assert all(entry["value_included"] is False for entry in config_entries.values())
    assert "Example Operator" not in result.stdout
    assert "/private/path" not in result.stdout
    actions = {action["id"]: action for action in payload["actions"]}
    assert actions["legacy-vip-audit"]["mode"] == "manual"
    assert actions["legacy-vip-audit"]["safe_to_apply"] is False


def test_doctor_repair_plan_handles_malformed_vip_yaml(tmp_path: Path) -> None:
    repo = tmp_path / "bad-vip"
    init_run(path=str(repo), name="Acme")
    (repo / ".vip").mkdir()
    (repo / ".vip" / "config.yaml").write_text("tools: [unterminated\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "legacy-vip")
    check = next(check for check in section["checks"] if check["name"] == ".vip/config.yaml")
    assert check["state"] == "warn"
    assert check["parse_error"]
    assert check["deletion"]["safe"] is False


def test_doctor_repair_plan_handles_non_mapping_vip_yaml(tmp_path: Path) -> None:
    repo = tmp_path / "list-vip"
    init_run(path=str(repo), name="Acme")
    (repo / ".vip").mkdir()
    (repo / ".vip" / "config.yaml").write_text("- one\n- two\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "legacy-vip")
    check = next(check for check in section["checks"] if check["name"] == ".vip/config.yaml")
    assert check["state"] == "warn"
    assert check["entries"] == []
    assert check["deletion"]["safe"] is False


def test_doctor_repair_plan_flags_vip_yaml_symlink_without_reading(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "symlink-vip"
    init_run(path=str(repo), name="Acme")
    private = tmp_path / "private-config.yaml"
    private.write_text("business_name: Private Business\n", encoding="utf-8")
    (repo / ".vip").mkdir()
    (repo / ".vip" / "config.yaml").symlink_to(private)

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    assert "Private Business" not in result.stdout
    payload = json.loads(result.stdout)
    section = next(section for section in payload["sections"] if section["id"] == "legacy-vip")
    check = next(check for check in section["checks"] if check["name"] == ".vip/config.yaml")
    assert check["state"] == "warn"
    assert check["entries"] == []
    assert check["deletion"]["safe"] is False
    assert "symlink" in check["summary"]


def test_doctor_repair_plan_distinguishes_read_and_write_actions(tmp_path: Path) -> None:
    repo = tmp_path / "legacy"
    (repo / "reference" / "core").mkdir(parents=True)

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    actions = {action["id"]: action for action in payload["actions"]}
    assert actions["migration-preview"]["mode"] == "read"
    assert actions["migration-apply"]["mode"] == "write"
    assert actions["migration-apply"]["safe_to_apply"] is False


def test_doctor_repair_apply_moves_old_clone_symlink_to_backup(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    old_engine = tmp_path / "mb-vip"
    old_lens = old_engine / ".claude" / "lenses" / "ops"
    old_lens.mkdir(parents=True)
    stale_link = repo / ".claude" / "lenses" / "ops"
    stale_link.parent.mkdir(parents=True, exist_ok=True)
    stale_link.symlink_to(old_lens, target_is_directory=True)

    result = runner.invoke(
        app, ["doctor", "repair", "--repo", str(repo), "--apply", "--only", "claude", "--json"]
    )

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    applied_ids = {action["id"] for action in payload["applied_actions"]}
    assert "legacy-claude-link-repair" in applied_ids
    assert not stale_link.exists()
    backups = list((repo / ".mb" / "backups").rglob("claude-links/.claude/lenses/ops"))
    assert backups
    assert ".mb/backups/" in (repo / ".gitignore").read_text(encoding="utf-8")


def test_doctor_rejects_unknown_options_on_existing_path() -> None:
    result = runner.invoke(app, ["doctor", "--jsonn"])

    assert result.exit_code == 2
    assert "unknown option" in result.stderr


def test_doctor_repair_exits_nonzero_when_json_report_is_red(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        doctor_mod,
        "repair_plan",
        lambda repo=".": {
            "ok": False,
            "read_only": True,
            "repo": str(tmp_path),
            "summary": {"error": 1},
        },
    )

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(tmp_path), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False


def test_doctor_repair_plan_json_frames_nonzero_plan_as_usable_findings(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Biz")
    (repo / "AGENTS.md").write_text("# stale\n\nNo facts here.\n", encoding="utf-8")

    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan", "--json"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.stdout)
    interpretation = payload["plan_interpretation"]
    assert interpretation["read_only_plan"] is True
    if payload["actions"]:
        assert interpretation["nonzero_exit_can_still_include_usable_plan"] is True
        assert interpretation["state"] in {
            "plan_produced_with_findings",
            "plan_produced_with_blockers",
        }


def test_doctor_legacy_symlink_keeps_current_active_engine_root(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "biz"
    repo.mkdir()
    active_root = tmp_path / "Documents" / "GitHub" / "mainbranch"
    active_lens = active_root / ".claude" / "lenses" / "ops"
    active_lens.mkdir(parents=True)
    lens_link = repo / ".claude" / "lenses" / "ops"
    lens_link.parent.mkdir(parents=True)
    lens_link.symlink_to(active_lens, target_is_directory=True)

    monkeypatch.setattr(
        doctor_mod.engine_mod,  # type: ignore[attr-defined]
        "engine_root",
        lambda: active_root,
    )

    result = doctor_mod._legacy_claude_symlinks(repo)

    assert result["repairable"] == 0
    assert result["findings"][0]["state"] == "info"
    assert result["findings"][0]["safe_to_repair"] is False


# ---------------------------------------------------------------------------
# Topology drift section (MAIN-289)
# ---------------------------------------------------------------------------


_VALID_TOPOLOGY_REGISTRY = """\
---
type: repo_topology
status: active
schema: mb.repo_topology.v0
home: github:example-co/example
business_display_name: Example Business
repos:
  - slug: example
    display_name: Example Business
    role: business
    lifecycle: active
    github_owner: example-co
    repo_name: example
    remote: github:example-co/example
    visibility: team_private
    relationship: hub_for
  - slug: workshop-site
    display_name: Workshop site
    role: site
    lifecycle: active
    relationship: execution_vehicle_for
    parent: example
    github_owner: example-co
    repo_name: workshop-site
    remote: github:example-co/workshop-site
    visibility: public
---
# Topology
"""


def _write_registry(repo: Path, body: str) -> None:
    path = repo / "core" / "operations" / "repo-topology.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _write_child_descriptor(repo: Path, payload: dict[str, Any]) -> None:
    path = repo / ".mainbranch" / "repo.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _topology_section(payload: dict[str, Any]) -> dict[str, Any]:
    return next(section for section in payload["sections"] if section["id"] == "topology-drift")


def test_doctor_topology_drift_section_info_when_no_registry(tmp_path: Path) -> None:
    repo = tmp_path / "no-topology"
    (repo / "core").mkdir(parents=True)  # minimal business marker (doctor guards bare dirs)

    payload = doctor_mod.repair_plan(repo=str(repo))

    section = _topology_section(payload)
    assert section["state"] == "info"
    assert "optional" in section["summary"].lower() or "no topology" in section["summary"].lower()
    action_ids = {action["id"] for action in payload["actions"]}
    assert "topology-drift-review" not in action_ids


def test_doctor_topology_drift_section_ok_when_registry_clean(tmp_path: Path) -> None:
    repo = tmp_path / "clean-topology"
    repo.mkdir()
    _write_registry(repo, _VALID_TOPOLOGY_REGISTRY)

    payload = doctor_mod.repair_plan(repo=str(repo))

    section = _topology_section(payload)
    assert section["state"] == "ok"
    assert "no drift detected" in section["summary"].lower()
    action_ids = {action["id"] for action in payload["actions"]}
    assert "topology-drift-review" not in action_ids


def test_doctor_topology_drift_section_warn_when_descriptor_orphan(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "orphan-descriptor"
    repo.mkdir()
    _write_child_descriptor(
        repo,
        {
            "schema": "mb.child_repo.v0",
            "role": "site",
            "display_name": "Workshop site",
            "github_owner": "example-co",
            "repo_name": "workshop-site",
            "parent": {
                "display_name": "Example Business",
                "github_owner": "example-co",
                "repo_name": "example",
                "remote": "github:example-co/example",
            },
        },
    )

    payload = doctor_mod.repair_plan(repo=str(repo))

    section = _topology_section(payload)
    assert section["state"] == "warn"
    actions = {action["id"]: action for action in payload["actions"]}
    assert "topology-drift-review" in actions
    review = actions["topology-drift-review"]
    assert review["mode"] == "manual"
    assert review["safe_to_apply"] is False


def test_doctor_topology_drift_section_warn_on_descriptor_role_mismatch(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "role-mismatch"
    repo.mkdir()
    _write_registry(repo, _VALID_TOPOLOGY_REGISTRY)
    # Descriptor handle matches workshop-site (registry role: site) but
    # claims role=product, triggering topology_descriptor_role_mismatch.
    _write_child_descriptor(
        repo,
        {
            "schema": "mb.child_repo.v0",
            "role": "product",
            "display_name": "Workshop site",
            "github_owner": "example-co",
            "repo_name": "workshop-site",
            "parent": {
                "display_name": "Example Business",
                "github_owner": "example-co",
                "repo_name": "example",
                "remote": "github:example-co/example",
            },
        },
    )

    payload = doctor_mod.repair_plan(repo=str(repo))

    section = _topology_section(payload)
    assert section["state"] == "warn"
    check_codes = {str(check.get("name")) for check in section.get("checks", [])}
    assert "topology_descriptor_role_mismatch" in check_codes


def test_doctor_topology_drift_preview_only(tmp_path: Path) -> None:
    repo = tmp_path / "preview-only"
    repo.mkdir()
    _write_child_descriptor(
        repo,
        {
            "schema": "mb.child_repo.v0",
            "role": "site",
            "display_name": "Workshop site",
            "github_owner": "example-co",
            "repo_name": "workshop-site",
            "parent": {
                "display_name": "Example Business",
                "github_owner": "example-co",
                "repo_name": "example",
                "remote": "github:example-co/example",
            },
        },
    )

    payload = doctor_mod.repair_plan(repo=str(repo))

    actions = {action["id"]: action for action in payload["actions"]}
    review = actions["topology-drift-review"]
    assert review["safe_to_apply"] is False
    assert review["mode"] == "manual"
    assert "does not rename" in review["reason"].lower()


def test_derive_audience_maps_mode_and_safety() -> None:
    assert doctor_mod._derive_audience("read", True) == "informational"
    assert doctor_mod._derive_audience("read", False) == "informational"
    assert doctor_mod._derive_audience("write", True) == "mechanical"
    assert doctor_mod._derive_audience("write", False) == "operator_decision"
    assert doctor_mod._derive_audience("manual", True) == "operator_decision"
    assert doctor_mod._derive_audience("manual", False) == "operator_decision"


def test_doctor_action_emits_audience_and_operator_summary() -> None:
    safe_write = doctor_mod._action(
        id="x",
        title="Apply mirror",
        state="warn",
        mode="write",
        command="mb doctor repair --apply",
        safe_to_apply=True,
        reason="Restores the Related links mirror.",
    )
    assert safe_write["audience"] == "mechanical"
    assert safe_write["operator_summary"] == "Restores the Related links mirror."

    read_only = doctor_mod._action(
        id="y",
        title="Inspect",
        state="ok",
        mode="read",
        command="mb doctor",
        safe_to_apply=True,
        reason="",
    )
    assert read_only["audience"] == "informational"
    # falls back to title when reason is empty
    assert read_only["operator_summary"] == "Inspect"

    manual = doctor_mod._action(
        id="z",
        title="Resolve cloud paths",
        state="error",
        mode="manual",
        command="open core/finance",
        safe_to_apply=False,
        reason="Operator must move files out of iCloud.",
    )
    assert manual["audience"] == "operator_decision"


def test_doctor_action_accepts_audience_override() -> None:
    override = doctor_mod._action(
        id="override",
        title="Custom",
        state="info",
        mode="write",
        command="mb x",
        safe_to_apply=True,
        reason="Default would be mechanical.",
        audience="informational",
        operator_summary="Just a heads-up.",
    )
    assert override["audience"] == "informational"
    assert override["operator_summary"] == "Just a heads-up."


def test_doctor_repair_plan_actions_always_carry_audience_and_summary(
    tmp_path: Path,
) -> None:
    """Every action emitted by repair_plan must have a valid audience and a
    non-empty operator_summary. Locks the contract agents read against."""
    repo = tmp_path / "fresh"
    (repo / "core").mkdir(parents=True)  # minimal business marker (doctor guards bare dirs)

    payload = doctor_mod.repair_plan(repo=str(repo))

    assert payload["actions"], "expected at least one action on a fresh repo"
    for action in payload["actions"]:
        assert action["audience"] in doctor_mod.AUDIENCE_VALUES, (
            f"action {action['id']} has invalid audience: {action['audience']!r}"
        )
        assert action["operator_summary"], f"action {action['id']} has empty operator_summary"


def test_dossier_section_absent_is_info(tmp_path: Path) -> None:
    section = doctor_mod._dossier_verify_section(tmp_path)

    assert section["id"] == "capability-dossier"
    assert section["state"] == "info"
    assert "mb-setup scaffolds" in section["summary"]


def test_dossier_verify_runs_only_mb_owned_commands(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    marker = tmp_path / "pwned"
    dossier = tmp_path / "core" / "operations" / "agent-access-dossier.md"
    dossier.parent.mkdir(parents=True)
    dossier.write_text(
        (
            "# Agent access dossier\n\n"
            "## Provider map (verify, don't assume)\n\n"
            "| Provider | Access level | Storage | Verify |\n"
            "|---|---|---|---|\n"
            "| Cloudflare | read | keychain | `mb connect test cloudflare` |\n"
            f"| Sneaky | full | env | `touch {marker}` |\n"
            "| Lookalike | full | env | `mb connect test cloudflare; touch pwned2` |\n"
        ),
        encoding="utf-8",
    )

    section = doctor_mod._dossier_verify_section(tmp_path)
    by_name = {check["name"]: check for check in section["checks"]}

    assert by_name["Cloudflare"]["state"] == "warn"
    assert "not_connected" in by_name["Cloudflare"]["summary"]
    assert by_name["Sneaky"]["state"] == "info"
    assert "not auto-executed" in by_name["Sneaky"]["summary"]
    assert by_name["Lookalike"]["state"] == "info"
    assert not marker.exists()
    assert not (tmp_path / "pwned2").exists()


def test_dossier_verify_reports_connected_provider_ok(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    from mb import connect as connect_mod

    repo = tmp_path
    connect_mod.connect_provider("apify", repo=repo, token="apify-fixture-token")
    dossier = repo / "core" / "operations" / "agent-access-dossier.md"
    dossier.parent.mkdir(parents=True)
    dossier.write_text(
        (
            "| Provider | Access level | Storage | Verify |\n"
            "|---|---|---|---|\n"
            "| Apify | research actors | keychain | `mb connect test apify` |\n"
        ),
        encoding="utf-8",
    )

    section = doctor_mod._dossier_verify_section(repo)

    apify = section["checks"][0]
    assert apify["name"] == "Apify"
    assert "mb connect test apify" in apify["summary"]
    assert apify["state"] in {"ok", "warn"}


def test_doctor_guard_refuses_writes_outside_business_folder(tmp_path: Path) -> None:
    (tmp_path / "stray-notes.md").write_text("# not a business\n", encoding="utf-8")

    plan = doctor_mod.repair_plan(tmp_path)
    assert plan["guard"] == "not_business_folder"
    assert plan["actions"] == []
    assert "mb onboard" in plan["plan_interpretation"]["summary"]
    # Guard payload still honors the repair JSON contract
    assert plan["schema"] == "mb.doctor.repair"
    assert plan["schema_version"] == 1
    assert plan["mode"] == "plan"
    # No phantom validation of stray markdown
    assert len(plan["sections"]) == 1

    applied = doctor_mod.repair_apply(tmp_path)
    assert applied["guard"] == "not_business_folder"
    assert applied["applied_actions"] == []
    assert applied["mode"] == "apply"
    # Nothing scaffolded into the arbitrary cwd
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / ".gitignore").exists()


def test_doctor_guard_passes_business_folders(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")

    plan = doctor_mod.repair_plan(repo)
    assert plan.get("guard") is None
    assert len(plan["sections"]) > 1


def test_doctor_repair_apply_never_switches_symlink_era_repo_to_plugin(tmp_path: Path) -> None:
    # #1042: the plugin-rail switch writes tracked `.claude/settings.json`, so
    # it is a step for a person (M22 on #1023). An agent running
    # `repair --apply` must never switch a repo's wiring, under any scope.
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    # Simulate symlink-era: remove the plugin wiring init now writes by default.
    (repo / ".claude" / "settings.json").unlink()
    assert engine_mod.plugin_wiring_status(repo)["wired"] is False

    for scope in ({"only": "claude"}, {"all_agents": True}, {}):
        applied = doctor_mod.repair_apply(repo=repo, **scope)
        assert "plugin-wiring" not in {action["id"] for action in applied["applied_actions"]}
        assert engine_mod.plugin_wiring_status(repo)["wired"] is False
        assert not (repo / ".claude" / "settings.json").exists()
        assert [item["command"] for item in applied["operator_actions"]] == [
            f"mb skill link{_flag(repo)} --plugin"
        ]


def test_doctor_claude_code_detail_is_plugin_first_when_missing(
    tmp_path: Path, monkeypatch
) -> None:
    # #924: a missing `claude` CLI should point at the plugin (Desktop + terminal).
    monkeypatch.setattr(
        doctor_mod,
        "_which",
        lambda name: "" if name == "claude" else (shutil.which(name) or ""),
    )
    report = run(path=str(tmp_path))

    check = next(c for c in report["checks"] if c["name"] == "claude-code")
    assert check["ok"] is False
    assert "dmthepm/mainbranch" in check["detail"]


def test_doctor_claude_code_detail_is_path_when_present(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        doctor_mod,
        "_which",
        lambda name: "/usr/local/bin/claude" if name == "claude" else (shutil.which(name) or ""),
    )
    report = run(path=str(tmp_path))

    check = next(c for c in report["checks"] if c["name"] == "claude-code")
    assert check["ok"] is True
    assert check["detail"] == "/usr/local/bin/claude"


def test_doctor_repair_plan_lists_plugin_switch_for_a_person(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # #1042: on a symlink-era repo the plan reports the plugin-rail switch the
    # way `mb update` does: in `operator_actions`, never as a repair action.
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    (repo / ".claude" / "settings.json").unlink()
    assert engine_mod.plugin_wiring_status(repo)["wired"] is False

    plan = doctor_mod.repair_plan(repo, only="claude")
    assert not any("--plugin" in action["command"] for action in plan["actions"])
    assert plan["operator_actions"] == [engine_mod.plugin_switch_operator_action(repo)]
    assert plan["operator_actions"][0]["changes"] == [".claude/settings.json"]
    assert "not an agent" in plan["operator_actions"][0]["note"]

    bare = doctor_mod.repair_plan(repo)
    assert bare["operator_actions"] == plan["operator_actions"]
    assert doctor_mod.repair_plan(repo, only="codex")["operator_actions"] == []

    doctor_mod.render_repair(plan)
    out = capsys.readouterr().out
    assert "For you to run" in out
    # The console wraps long paths, so compare without whitespace.
    assert "".join(f"mb skill link{_flag(repo)} --plugin".split()) in "".join(out.split())


def test_doctor_repair_plan_omits_plugin_wiring_when_already_wired(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")  # init wires the plugin by default
    assert engine_mod.plugin_wiring_status(repo)["wired"] is True

    plan = doctor_mod.repair_plan(repo, only="claude")
    assert "plugin-wiring" not in {action["id"] for action in plan["actions"]}
    assert plan["operator_actions"] == []


def test_doctor_repair_apply_already_wired_is_noop_for_plugin(tmp_path: Path) -> None:
    # The `not wired` guard must keep apply from re-firing on an already-wired repo.
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    assert engine_mod.plugin_wiring_status(repo)["wired"] is True

    applied = doctor_mod.repair_apply(repo=repo, only="claude")
    assert "plugin-wiring" not in {action["id"] for action in applied["applied_actions"]}


# --- #1072: every suggested command names the business repo -------------------


def _flag(repo: Path) -> str:
    return f" --repo {shlex.quote(str(repo.resolve()))}"


def _suggested_commands(plan: dict[str, Any]) -> list[str]:
    found: list[str] = []
    found += [str(action["command"]) for action in plan["actions"]]
    for section in plan["sections"]:
        found += [str(action["command"]) for action in section.get("actions", [])]
    surfaces = plan["agent_surfaces"]
    found += [str(surface["repair_command"]) for surface in surfaces["surfaces"]]
    found += [str(item) for item in surfaces["scope_choices"]]
    found += [str(item) for item in surfaces["apply_choices"]]
    found += [str(item["command"]) for item in plan["operator_actions"]]
    return found


def test_doctor_repair_plan_names_the_repo_in_every_command_from_another_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    (repo / ".claude" / "settings.json").unlink()
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    flag = f"--repo {shlex.quote(str(repo.resolve()))}"

    plan = doctor_mod.repair_plan(repo, all_agents=True)

    commands = _suggested_commands(plan)
    assert commands
    surfaces = plan["agent_surfaces"]
    assert surfaces["scope_choices"][1] == f"mb doctor repair {flag} --plan --only codex"
    assert surfaces["apply_choices"][0] == f"mb doctor repair {flag} --apply --only claude"
    assert (
        surfaces["surfaces"][1]["repair_command"] == f"mb doctor repair {flag} --apply --only codex"
    )
    assert plan["operator_actions"][0]["command"] == f"mb skill link {flag} --plugin"
    for command in commands:
        for segment in command.split(" && "):
            if segment.startswith("mb "):
                _assert_each_mb_segment_names_the_repo_once([segment], repo)
    assert "--repo ." not in " ".join(commands)
    assert plan["post_apply"]["structural_verification"] == (
        f"mb doctor repair {flag} --plan --json"
    )


def _all_command_strings(node: Any) -> list[str]:
    """Every suggested-command string anywhere in a plan, shared objects included."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"command", "repair_command"} and isinstance(value, str):
                found.append(value)
            elif key in {"scope_choices", "apply_choices"} and isinstance(value, list):
                found += [str(item) for item in value]
            elif key not in {"raw", "result"}:
                found += _all_command_strings(value)
    elif isinstance(node, list):
        for item in node:
            found += _all_command_strings(item)
    return found


def _assert_each_mb_segment_names_the_repo_once(commands: list[str], repo: Path) -> None:
    target = str(repo.resolve())
    seen_mb = 0
    for command in commands:
        tokens = shlex.split(command)
        segments: list[list[str]] = [[]]
        for token in tokens:
            if token == "&&":
                segments.append([])
            else:
                segments[-1].append(token)
        for segment in segments:
            if segment[:1] != ["mb"]:
                continue
            seen_mb += 1
            if segment[:2] in (["mb", "status"], ["mb", "graph"]):
                assert segment.count(target) == 1, command
                assert segment[-1] == target, command
                assert "--repo" not in segment, command
            else:
                assert segment.count("--repo") == 1, command
                assert segment[segment.index("--repo") + 1] == target, command
                assert segment.count(target) == 1, command
    assert seen_mb


def _repo_with_topology_and_campaigns(tmp_path: Path, name: str = "biz") -> Path:
    repo = tmp_path / name
    init_run(path=str(repo), name="Acme")
    (repo / ".vip").mkdir()
    (repo / ".vip" / "local.yaml").write_text("current_offer: x\n", encoding="utf-8")
    (repo / "campaigns").mkdir()
    (repo / "campaigns" / "a.md").write_text("x\n", encoding="utf-8")
    return repo


def test_doctor_repair_plan_names_the_repo_once_per_command_with_topology_and_campaigns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo_with_topology_and_campaigns(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)

    plan = doctor_mod.repair_plan(repo)

    assert "offer-topology-review" in {action["id"] for action in plan["actions"]}
    commands = _all_command_strings(plan)
    assert any(c.startswith("mb status") for c in commands)
    _assert_each_mb_segment_names_the_repo_once(commands, repo)
    migrate = [c for c in commands if "migrate" in c and "campaigns" in c]
    assert migrate
    for command in migrate:
        assert command.startswith(f"mb migrate{_flag(repo)} campaigns --plan"), command


def test_a_migrate_campaigns_command_runs_from_another_folder_on_the_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo_with_topology_and_campaigns(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    plan = doctor_mod.repair_plan(repo)
    command = next(c for c in _all_command_strings(plan) if "migrate" in c and "campaigns" in c)

    out = runner.invoke(app, [*shlex.split(command)[1:], "--json"])

    assert json.loads(out.stdout)["repo"] == str(repo.resolve())


def test_qualifying_a_command_twice_changes_nothing(tmp_path: Path) -> None:
    repo = tmp_path / "biz one"
    repo.mkdir()
    for command in (
        "mb status --json --peek && mb validate --json",
        "mb graph --json",
        "mb doctor repair --apply --only codex",
        "mb skill link --repo . --plugin",
        "mb migrate campaigns --plan --json",
    ):
        once = doctor_mod._qualify_command(command, repo)
        assert once != command
        assert doctor_mod._qualify_command(once, repo) == once


def test_a_repo_path_that_looks_like_a_command_is_quoted_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = "x --repo . mb status && y"
    repo = tmp_path / name
    init_run(path=str(repo), name="Acme")
    (repo / ".vip").mkdir()
    (repo / ".vip" / "local.yaml").write_text("current_offer: x\n", encoding="utf-8")
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)

    plan = doctor_mod.repair_plan(repo)

    commands = _all_command_strings(plan)
    assert any(c.startswith("mb status") for c in commands)
    _assert_each_mb_segment_names_the_repo_once(commands, repo)
    command = plan["agent_surfaces"]["scope_choices"][1]
    out = runner.invoke(app, [*shlex.split(command)[1:], "--json"])
    assert json.loads(out.stdout)["repo"] == str(repo.resolve())


def test_doctor_repair_plan_commands_stay_bare_inside_the_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    monkeypatch.chdir(repo)

    plan = doctor_mod.repair_plan(repo, all_agents=True)

    assert plan["agent_surfaces"]["scope_choices"][1] == "mb doctor repair --plan --only codex"
    assert not any("--repo" in command for command in _suggested_commands(plan))


def test_a_doctor_suggested_command_runs_from_another_folder_on_the_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    plan = doctor_mod.repair_plan(repo, only="codex")
    command = plan["agent_surfaces"]["scope_choices"][1]

    out = runner.invoke(app, [*shlex.split(command)[1:], "--json"])

    assert json.loads(out.stdout)["repo"] == str(repo.resolve())
    assert sorted(path.name for path in other.iterdir()) == []


# --- #1083: shell-safe rewriting, spine declare and doctor-run fields -------------------


@pytest.fixture
def offline_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Doctor's run reaches for PyPI and the network; keep it local and give it an update."""
    from mb import freshness

    monkeypatch.setattr(doctor_mod, "_net", lambda: (True, "stubbed"))
    monkeypatch.setattr(
        doctor_mod,
        "package_update_status",
        lambda repo=None: freshness.package_update_status(
            repo, latest_version="99.0.0", mode="pipx"
        ),
    )


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("echo $HOME && mb update", "echo $HOME && mb update {flag}"),
        ("mb status --json --peek | jq .", "mb status --json --peek {path} | jq ."),
        ("mb validate --json 2>/dev/null", "mb validate {flag} --json 2>/dev/null"),
        ("mb status --json 2>/dev/null", "mb status --json {path} 2>/dev/null"),
        ("cd ~/biz && mb validate", "cd ~/biz && mb validate {flag}"),
        ("a ; mb update", "a ; mb update {flag}"),
        ("ls *.md || mb update", "ls *.md || mb update {flag}"),
        ("echo 'a && mb x' && mb update", "echo 'a && mb x' && mb update {flag}"),
        ("mb validate --repo", "mb validate --repo"),
        ("mb validate --repo && mb update", "mb validate --repo && mb update {flag}"),
    ],
)
def test_the_rewriter_keeps_shell_syntax_outside_the_mb_segment(
    tmp_path: Path, command: str, expected: str
) -> None:
    repo = tmp_path / "biz one"
    repo.mkdir()
    flag = f"--repo {shlex.quote(str(repo.resolve()))}"
    path = shlex.quote(str(repo.resolve()))

    rewritten = doctor_mod._qualify_command(command, repo)

    assert rewritten == expected.format(flag=flag, path=path)
    assert doctor_mod._qualify_command(rewritten, repo) == rewritten


@pytest.mark.parametrize(
    "command",
    [
        "echo `printf seed; mb status --json`",
        "echo $(printf seed; mb status --json)",
        "cat <<'EOF'\nmb update\nEOF",
        "mb status --json # note",
        "mb update ${MODE}",
        'mb update <<<"seed"',
        "mb status <(printf seed)",
        "mb status >(cat)",
        "mb update $((1 + 2))",
        'mb update "$(printf seed)"',
        'mb update "`printf seed`"',
        'mb update "${MODE}"',
        "cat <<EOF\nmb update\nEOF",
        "cat <<-EOF\n\tmb update\nEOF",
        "mb update;# note",
        "mb update && # note\nmb status",
        "# note\nmb update",
        "mb update ''#literal # note",
    ],
)
def test_the_rewriter_refuses_unsupported_shell_constructs(tmp_path: Path, command: str) -> None:
    repo = tmp_path / "biz one"
    repo.mkdir()

    assert doctor_mod._qualify_command(command, repo) == command


@pytest.mark.parametrize(
    "command",
    [
        "cat <\\\n<'EOF'\nmb update\nEOF\n",
        "echo $\\\n(printf seed; mb status --json)",
        "mb status <\\\n(printf seed)",
        "mb update $\\\n{MODE}",
        'echo "seed\\\nmore" && mb update',
    ],
)
def test_the_rewriter_refuses_backslash_line_continuations(tmp_path: Path, command: str) -> None:
    repo = tmp_path / "biz one"
    repo.mkdir()

    assert doctor_mod._qualify_command(command, repo) == command


@pytest.mark.parametrize(
    "literal",
    [
        "a#b",
        "''#literal",
        r"\#literal",
        "'` $( ${ << <<< <( >( # literal'",
        '"<< <<< <( >( # literal"',
    ],
)
def test_the_rewriter_qualifies_commands_with_shell_literals(tmp_path: Path, literal: str) -> None:
    repo = tmp_path / "biz one"
    repo.mkdir()
    command = f"echo {literal} && mb update"
    expected = f"{command} --repo {shlex.quote(str(repo.resolve()))}"

    assert doctor_mod._qualify_command(command, repo) == expected
    assert doctor_mod._qualify_command(expected, repo) == expected


def test_the_rewriter_leaves_shell_lines_alone_inside_the_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "biz"
    repo.mkdir()
    monkeypatch.chdir(repo)
    for command in (
        "echo $HOME && mb update",
        "mb status --json --peek | jq .",
        "mb validate --json 2>/dev/null",
        "cd ~/biz && mb validate",
        "a ; mb update",
    ):
        assert doctor_mod._qualify_command(command, repo) == command
    assert doctor_mod._qualify_command("mb validate --repo . --json | jq .", repo) == (
        "mb validate --json | jq ."
    )


def test_the_rewriter_names_the_business_repo_flag_and_the_books_positional(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "biz one"
    repo.mkdir()
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    quoted = shlex.quote(str(repo.resolve()))
    cases = {
        'mb site check "/s" --business-repo .': f'mb site check "/s" --business-repo {quoted}',
        "mb site check /s --business-repo /x": "mb site check /s --business-repo /x",
        "mb site check /s --business-repo=.": "mb site check /s --business-repo=.",
        "mb site check /s --business-repo": "mb site check /s --business-repo",
        "mb books status --json": f"mb books status --json {quoted}",
        "mb books doctor --plan --json": f"mb books doctor --plan --json {quoted}",
        f"mb books status --json {quoted}": f"mb books status --json {quoted}",
        "mb books check": "mb books check",
    }
    for command, expected in cases.items():
        assert doctor_mod._qualify_command(command, repo) == expected, command
        assert doctor_mod._qualify_command(expected, repo) == expected, command
    monkeypatch.chdir(repo)
    assert doctor_mod._qualify_command('mb site check "/s" --business-repo .', repo) == (
        'mb site check "/s" --business-repo .'
    )


def _business_repo_without_spine(tmp_path: Path) -> Path:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    return repo


def test_spine_declare_in_the_doctor_summary_writes_into_the_repo_from_another_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _business_repo_without_spine(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)

    plan = doctor_mod.repair_plan(repo)

    section = next(s for s in plan["sections"] if s["id"] == "contact-event-spine")
    command = section["summary"].split("`")[1]
    assert command.startswith(f"mb spine declare{_flag(repo)} --store")
    out = runner.invoke(
        app, [*shlex.split(command.replace("<provider>", "none --intentional"))[1:], "--json"]
    )
    assert out.exit_code == 0, out.output
    assert (repo / "core" / "operations" / "spine.md").is_file()
    assert sorted(path.name for path in other.iterdir()) == []


def test_spine_declare_in_the_doctor_summary_is_bare_inside_the_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _business_repo_without_spine(tmp_path)
    monkeypatch.chdir(repo)

    plan = doctor_mod.repair_plan(repo)

    section = next(s for s in plan["sections"] if s["id"] == "contact-event-spine")
    assert "`mb spine declare --store <provider>`" in section["summary"]


def _repo_with_foreign_hook_and_drift(tmp_path: Path) -> Path:
    repo = _repo_with_topology_and_campaigns(tmp_path)
    (repo / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
    (repo / ".git" / "hooks" / "commit-msg").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    return repo


def test_doctor_run_checks_and_prose_name_the_repo_from_another_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline_doctor: None
) -> None:
    repo = _repo_with_foreign_hook_and_drift(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    flag = _flag(repo)

    report = run(str(repo))

    checks = {check["name"]: check for check in report["checks"]}
    hook = checks["checkpoint-hook"]
    assert hook["state"] == "blocked_existing_hook"
    assert hook["repair_command"] == (
        f"review .git/hooks/commit-msg, then run mb checkpoint{flag} --install-hook"
    )
    assert f"`mb onboard status{flag}`" in checks["onboarding-progress"]["detail"]
    findings = checks["migration-drift"]["findings"]
    assert findings
    for finding in findings:
        assert flag in finding["repair_command"], finding
    assert report["update"]["update_check_command"] == f"mb update{flag} --check --json"
    assert report["update"]["command"] == f"mb update{flag}"


def test_doctor_run_checks_and_prose_stay_bare_inside_the_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline_doctor: None
) -> None:
    repo = _repo_with_foreign_hook_and_drift(tmp_path)
    monkeypatch.chdir(repo)

    report = run(str(repo))

    checks = {check["name"]: check for check in report["checks"]}
    assert checks["checkpoint-hook"]["repair_command"] == (
        "review .git/hooks/commit-msg, then run mb checkpoint --install-hook"
    )
    assert "`mb onboard status`" in checks["onboarding-progress"]["detail"]
    assert report["update"]["update_check_command"] == "mb update --check --json"
    assert checks["migration-drift"]["findings"]
    assert "--repo" not in json.dumps(checks["migration-drift"])
    assert report["update"]["command"] == "mb update"


def test_doctor_repair_plan_prose_and_manual_step_name_the_repo_but_raw_stays_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline_doctor: None
) -> None:
    repo = _repo_with_foreign_hook_and_drift(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    flag = _flag(repo)

    plan = doctor_mod.repair_plan(repo)

    assert plan["plan_interpretation"]["summary"].startswith(f"`mb doctor repair{flag} --plan`")
    manual = next(a for a in plan["actions"] if a["id"] == "checkpoint-hook-existing")
    assert manual["command"] == (
        f"review .git/hooks/commit-msg, then run mb checkpoint{flag} --install-hook"
    )
    section = next(s for s in plan["sections"] if s["id"] == "checkpoint-hook")
    assert section["checks"][0]["repair_command"] == manual["command"]
    drift = next(s for s in plan["sections"] if s["id"] == "migration-drift")
    assert drift["checks"]
    assert all(flag in check["repair_command"] for check in drift["checks"])
    raw = plan["raw"]["migration_drift"]["findings"]
    assert raw
    assert all("--repo" not in finding["repair_command"] for finding in raw)


def test_doctor_repair_plan_inside_the_repo_never_names_the_repo_in_prose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline_doctor: None
) -> None:
    repo = _repo_with_foreign_hook_and_drift(tmp_path)
    monkeypatch.chdir(repo)

    plan = doctor_mod.repair_plan(repo)

    assert plan["plan_interpretation"]["summary"].startswith("`mb doctor repair --plan`")
    assert "--repo" not in json.dumps(
        {k: v for k, v in plan.items() if k not in {"repo", "agent_surfaces"}}
    )


def test_doctor_json_with_an_issue_draft_keeps_paths_out_of_the_command_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline_doctor: None
) -> None:
    from mb import issue

    repo = _repo_with_foreign_hook_and_drift(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)

    body, _ = issue._safe_doctor_json(repo)

    assert "mb checkpoint --repo" not in body
    assert "mb migrate --repo" not in body
    assert '"repair_command": "mb migrate campaigns --plan"' in body


def _validation_prose(plan: dict[str, Any]) -> list[str]:
    section = next(s for s in plan["sections"] if s["id"] == "validation")
    categories = section["checks"][0]["report"]["validation_categories"]
    found = [categories["top_repair"], categories["top_operator_summary"]]
    for entry in categories["by_category"].values():
        found += [entry["repair"], entry["operator_summary"]]
    return found


def test_validation_repair_prose_names_the_repo_but_raw_validation_stays_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline_doctor: None
) -> None:
    repo = _repo_with_foreign_hook_and_drift(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    flag = _flag(repo)

    plan = doctor_mod.repair_plan(repo)

    prose = _validation_prose(plan)
    assert f"Run `mb doctor repair{flag} --plan --json` and review stale layout guidance." in prose
    for text in prose:
        for span in text.split("`")[1::2]:
            if span.startswith("mb "):
                assert flag in span, text
    raw = json.dumps(plan["raw"])
    assert flag not in raw
    assert "Run `mb doctor repair --plan --json` and review stale layout guidance." in raw


def test_validation_repair_prose_is_bare_inside_the_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline_doctor: None
) -> None:
    repo = _repo_with_foreign_hook_and_drift(tmp_path)
    monkeypatch.chdir(repo)

    plan = doctor_mod.repair_plan(repo)

    assert "Run `mb doctor repair --plan --json` and review stale layout guidance." in (
        _validation_prose(plan)
    )
    assert "--repo" not in json.dumps(_validation_prose(plan))


def test_agent_surface_planned_actions_order_does_not_follow_the_hash_seed() -> None:
    # #1100: the order came from a frozenset, so it changed between processes.
    script = (
        "import json\n"
        "from mb import doctor\n"
        "ids = sorted(doctor.AGENT_ACTION_IDS)\n"
        "report = doctor._agent_surfaces([], [{'id': i, 'writes': [i]} for i in ids])\n"
        "print(json.dumps(report['surfaces']))\n"
    )
    package_root = str(Path(doctor_mod.__file__).resolve().parents[1])
    outputs = set()
    for seed in range(8):
        env = {**os.environ, "PYTHONHASHSEED": str(seed), "PYTHONPATH": package_root}
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            env=env,
            stdin=subprocess.DEVNULL,
        )
        outputs.add(proc.stdout)
    assert len(outputs) == 1
    surfaces = json.loads(outputs.pop())
    for surface in surfaces:
        assert surface["planned_actions"] == sorted(surface["planned_actions"])
        assert surface["touched_files"] == surface["planned_actions"]


_OLD_STATUS_LINES = {
    "template": (
        "- Status field: `proposed | running | scaling | killed | graduated | died`\n"
        "  (decisions use `accepted | rejected | superseded`; pushes use\n"
        "  `draft | planned | active | paused | completed | canceled | archived`).\n"
    ),
    "fallback": "- Status field: proposed | running | scaling | killed | graduated | died.\n",
    # 0.1.x releases (#1133): "Status enum:" in the same two shapes.
    "template-0.1": (
        "- Status enum: `proposed | running | scaling | killed | graduated | died`\n"
        "  (with `accepted | rejected | superseded` for decisions).\n"
    ),
    "fallback-0.1": "- Status enum: proposed | running | scaling | killed | graduated | died.\n",
}


@pytest.mark.parametrize("form", sorted(_OLD_STATUS_LINES))
def test_doctor_flags_the_old_claude_md_status_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    # #1122: repos made before #1121 still teach one status set for every file type.
    from mb.init import status_conventions

    repo = tmp_path / "old-line"
    init_run(path=str(repo), name="Acme")
    claude_md = repo / "CLAUDE.md"
    text = claude_md.read_text(encoding="utf-8")
    text = text.replace(status_conventions() + "\n", _OLD_STATUS_LINES[form])
    assert _OLD_STATUS_LINES[form] in text
    claude_md.write_text(text, encoding="utf-8")
    before = claude_md.read_bytes()
    # Clear the one hard failure a bare test host has, so ok is True without the line.
    monkeypatch.setattr(doctor_mod, "_which", lambda name: f"/usr/bin/{name}")

    report = doctor_mod.run(path=str(repo))

    check = next(c for c in report["checks"] if c["name"] == "claude-status-line")
    assert check["ok"] is False
    assert check["severity"] == "warn"
    assert check["path"] == "CLAUDE.md"
    assert check["suggested_text"] == status_conventions()
    assert status_conventions() in check["detail"]
    assert "`running` on a bet" in check["detail"]
    # The text names the line this repo actually has.
    word = "enum" if "enum" in form or "0.1" in form else "field"
    assert f"Replace the `Status {word}:` line" in check["detail"]
    # A warning only: the report's overall verdict matches a repo without the line.
    other = tmp_path / "no-line"
    init_run(path=str(other), name="Acme")
    assert report["ok"] == doctor_mod.run(path=str(other))["ok"]
    assert report["ok"] is True
    # Never rewritten.
    assert claude_md.read_bytes() == before


def test_doctor_has_no_status_line_finding_without_the_old_line(tmp_path: Path) -> None:
    repo = tmp_path / "fresh"
    init_run(path=str(repo), name="Acme")

    report = doctor_mod.run(path=str(repo))

    assert "claude-status-line" not in {c["name"] for c in report["checks"]}
    (repo / "CLAUDE.md").unlink()
    again = doctor_mod.run(path=str(repo))
    assert "claude-status-line" not in {c["name"] for c in again["checks"]}


_OLD_STATUS_SEQUENCE = "proposed | running | scaling | killed | graduated | died"


@pytest.mark.parametrize("word", ["field", "enum"])
def test_doctor_does_not_flag_the_old_status_line_quoted_in_prose(
    tmp_path: Path, word: str
) -> None:
    # #1133: only a list item is the old convention; a sentence that quotes it is not.
    repo = tmp_path / "prose"
    init_run(path=str(repo), name="Acme")
    claude_md = repo / "CLAUDE.md"
    claude_md.write_text(
        claude_md.read_text(encoding="utf-8")
        + f"\nNote: we replaced the line Status {word}: {_OLD_STATUS_SEQUENCE} last month,\n"
        f"and an old copy said `- Status {word}: {_OLD_STATUS_SEQUENCE}` in a code span.\n",
        encoding="utf-8",
    )

    report = doctor_mod.run(path=str(repo))

    assert "claude-status-line" not in {c["name"] for c in report["checks"]}


def test_doctor_flags_the_old_status_line_as_an_indented_star_item(tmp_path: Path) -> None:
    repo = tmp_path / "star"
    init_run(path=str(repo), name="Acme")
    claude_md = repo / "CLAUDE.md"
    claude_md.write_text(
        claude_md.read_text(encoding="utf-8") + f"\n  * Status field: {_OLD_STATUS_SEQUENCE}\n",
        encoding="utf-8",
    )

    report = doctor_mod.run(path=str(repo))

    assert "claude-status-line" in {c["name"] for c in report["checks"]}


_OLD_ITEM = f"- Status field: {_OLD_STATUS_SEQUENCE}\n"


def _status_line_findings(tmp_path: Path, extra: str) -> list[dict[str, Any]]:
    repo = tmp_path / "fence"
    init_run(path=str(repo), name="Acme")
    claude_md = repo / "CLAUDE.md"
    claude_md.write_text(claude_md.read_text(encoding="utf-8") + "\n" + extra, encoding="utf-8")
    report = doctor_mod.run(path=str(repo))
    plan = doctor_mod.repair_plan(repo)
    findings = [c for c in report["checks"] if c["name"] == "claude-status-line"]
    assert len(findings) == len([s for s in plan["sections"] if s["id"] == "claude-status-line"])
    return findings


@pytest.mark.parametrize(
    "fenced",
    [
        "```\n" + _OLD_ITEM + "```\n",
        "~~~\n" + _OLD_ITEM + "~~~\n",
        "```markdown\n" + _OLD_ITEM + "```\n",
        "~~~md\n" + _OLD_ITEM + "~~~\n",
        "   ```\n" + _OLD_ITEM + "   ```\n",
        "````\n```\n" + _OLD_ITEM + "````\n",
        "```\n" + _OLD_ITEM,  # unclosed: runs to the end of the file
    ],
    ids=["backtick", "tilde", "info", "tilde-info", "indented", "longer-fence", "unclosed"],
)
def test_old_status_line_inside_a_fence_is_not_flagged(tmp_path: Path, fenced: str) -> None:
    assert _status_line_findings(tmp_path, fenced) == []


def test_old_status_line_outside_and_after_a_fence_is_still_flagged(tmp_path: Path) -> None:
    assert len(_status_line_findings(tmp_path, _OLD_ITEM)) == 1
    assert len(_status_line_findings(tmp_path / "x", "```\nfoo\n```\n" + _OLD_ITEM)) == 1
    # Four spaces of indent is not a fence, so the line is still live.
    assert len(_status_line_findings(tmp_path / "y", "    ```\n" + _OLD_ITEM)) == 1


def test_one_old_status_line_in_a_fence_and_one_outside_is_one_finding(tmp_path: Path) -> None:
    fenced = "```\n" + _OLD_ITEM.replace("field", "enum") + "```\n\n"
    findings = _status_line_findings(tmp_path, fenced + _OLD_ITEM)
    assert len(findings) == 1
    # The finding names the live line, not the quoted one.
    assert "Replace the `Status field:` line" in findings[0]["detail"]


@pytest.mark.parametrize("form", ["template", "fallback-0.1"])
def test_repair_plan_lists_the_old_status_line_as_a_manual_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    # #1133: the plan names the finding; it is never an apply step.
    from mb.init import status_conventions

    monkeypatch.setattr(doctor_mod, "_which", lambda name: f"/usr/bin/{name}")
    repo = tmp_path / "plan"
    init_run(path=str(repo), name="Acme")
    clean = doctor_mod.repair_plan(repo)
    assert "claude-status-line" not in {a["id"] for a in clean["actions"]}
    assert "claude-status-line" not in {s["id"] for s in clean["sections"]}

    claude_md = repo / "CLAUDE.md"
    text = claude_md.read_text(encoding="utf-8")
    claude_md.write_text(
        text.replace(status_conventions() + "\n", _OLD_STATUS_LINES[form]), encoding="utf-8"
    )
    before = claude_md.read_bytes()

    plan = doctor_mod.repair_plan(repo)

    action = next(a for a in plan["actions"] if a["id"] == "claude-status-line")
    assert (action["mode"], action["safe_to_apply"], action["writes"]) == ("manual", False, [])
    section = next(s for s in plan["sections"] if s["id"] == "claude-status-line")
    assert section["state"] == "warn" and section["actions"] == [action]
    assert plan["ok"] == clean["ok"]
    assert plan["summary"]["write_actions"] == clean["summary"]["write_actions"]
    # --only scopes leave it out, and apply never touches CLAUDE.md.
    for scoped in (
        doctor_mod.repair_plan(repo, only="claude"),
        doctor_mod.repair_plan(repo, only="codex"),
        doctor_mod.repair_plan(repo, all_agents=True),
    ):
        assert "claude-status-line" not in {a["id"] for a in scoped["actions"]}
        assert "claude-status-line" not in {s["id"] for s in scoped["sections"]}
    doctor_mod.repair_apply(repo)
    assert claude_md.read_bytes() == before
