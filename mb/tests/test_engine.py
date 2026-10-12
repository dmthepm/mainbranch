"""Claude Code skill wiring and personal-shadow repair."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mb import __version__
from mb import engine as engine_mod


def _write_skill(root: Path, name: str) -> Path:
    skill = root / ".claude" / "skills" / name
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill.\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return skill


def test_personal_legacy_mainbranch_symlink_is_reported_and_backed_up(
    tmp_path: Path, monkeypatch
) -> None:
    old_engine = tmp_path / "old-engine"
    (old_engine / "mb" / "mb").mkdir(parents=True)
    (old_engine / "mb" / "mb" / "__init__.py").write_text('__version__ = "0.1.0"\n')
    old_start = _write_skill(old_engine, "start")
    personal = tmp_path / "home" / ".claude" / "skills"
    personal.mkdir(parents=True)
    (personal / "start").symlink_to(old_start, target_is_directory=True)
    repo = tmp_path / "biz"
    _write_skill(repo, "mb-start")

    monkeypatch.setattr(engine_mod, "bundled_skills", lambda: ["mb-start"])

    dry = engine_mod.inspect_personal_skill_conflicts(repo, personal_skills_dir=personal)

    assert dry["ok"] is True
    assert dry["summary"]["legacy_globals"] == 1
    assert dry["summary"]["repairable"] == 1
    assert dry["findings"][0]["classification"] == "stale-mainbranch-link"
    assert (personal / "start").is_symlink()

    applied = engine_mod.inspect_personal_skill_conflicts(
        repo,
        apply=True,
        personal_skills_dir=personal,
    )

    assert applied["summary"]["repaired"] == 1
    assert not (personal / "start").exists()
    assert Path(applied["findings"][0]["backup_path"]).is_symlink()


def test_personal_legacy_broken_symlink_is_reported_and_backed_up(
    tmp_path: Path, monkeypatch
) -> None:
    personal = tmp_path / "home" / ".claude" / "skills"
    personal.mkdir(parents=True)
    (personal / "start").symlink_to(tmp_path / "missing-engine" / "start")
    repo = tmp_path / "biz"
    _write_skill(repo, "mb-start")

    monkeypatch.setattr(engine_mod, "bundled_skills", lambda: ["mb-start"])

    dry = engine_mod.inspect_personal_skill_conflicts(repo, personal_skills_dir=personal)

    assert dry["ok"] is True
    assert dry["summary"]["legacy_globals"] == 1
    assert dry["summary"]["repairable"] == 1
    assert dry["findings"][0]["classification"] == "broken-symlink"
    assert (personal / "start").is_symlink()

    applied = engine_mod.inspect_personal_skill_conflicts(
        repo,
        apply=True,
        personal_skills_dir=personal,
    )

    assert applied["summary"]["repaired"] == 1
    assert not (personal / "start").exists()
    assert not (personal / "start").is_symlink()
    assert Path(applied["findings"][0]["backup_path"]).is_symlink()


def test_personal_third_party_active_shadow_is_reported_but_not_repaired(
    tmp_path: Path, monkeypatch
) -> None:
    personal = tmp_path / "home" / ".claude" / "skills"
    _write_skill(personal.parent.parent, "mb-start")
    repo = tmp_path / "biz"
    _write_skill(repo, "mb-start")

    monkeypatch.setattr(engine_mod, "bundled_skills", lambda: ["mb-start"])

    result = engine_mod.inspect_personal_skill_conflicts(
        repo,
        apply=True,
        personal_skills_dir=personal,
    )

    assert result["ok"] is False
    assert result["summary"]["active_shadows"] == 1
    assert result["summary"]["repairable"] == 0
    assert result["findings"][0]["classification"] == "not-mainbranch-link"
    assert (personal / "mb-start" / "SKILL.md").exists()


def test_link_skills_auto_repairs_broken_legacy_personal_symlink(
    tmp_path: Path, monkeypatch
) -> None:
    personal = tmp_path / "home" / ".claude" / "skills"
    personal.mkdir(parents=True)
    (personal / "start").symlink_to(tmp_path / "missing-engine" / "start")
    repo = tmp_path / "biz"

    monkeypatch.setattr(engine_mod, "bundled_skills", lambda: ["mb-start"])
    monkeypatch.setattr(engine_mod, "_personal_skills_dir", lambda: personal)

    result = engine_mod.link_skills(repo)

    assert result["ok"] is True
    assert result["shadow_report"]["summary"]["repaired"] == 1
    assert result["shadow_report"]["findings"][0]["classification"] == "broken-symlink"
    assert not (personal / "start").exists()
    assert not (personal / "start").is_symlink()
    assert (repo / ".claude" / "skills" / "mb-start" / "SKILL.md").exists()


def test_bundled_skills_ignores_directories_without_skill_md(tmp_path: Path, monkeypatch) -> None:
    engine = tmp_path / "engine"
    _write_skill(engine, "mb-start")
    leftover = engine / ".claude" / "skills" / "start"
    leftover.mkdir(parents=True)
    (leftover / ".DS_Store").write_bytes(b"")
    (engine / ".claude" / "skills" / "setup").mkdir()

    monkeypatch.setattr(engine_mod, "skills_dir", lambda root=None: engine / ".claude" / "skills")

    assert engine_mod.bundled_skills() == ["mb-start"]


def test_link_skills_does_not_relink_engine_leftover_without_skill_md(
    tmp_path: Path, monkeypatch
) -> None:
    """A removed legacy project symlink stays removed even when the engine root
    still carries a leftover same-named directory with no SKILL.md (rename
    residue). Regression for link_skills re-creating `.claude/skills/start`."""
    repo = tmp_path / "biz"
    engine = tmp_path / "engine"
    _write_skill(engine, "mb-start")
    leftover = engine / ".claude" / "skills" / "start"
    leftover.mkdir(parents=True)
    (leftover / ".DS_Store").write_bytes(b"")
    legacy = repo / ".claude" / "skills" / "start"
    legacy.parent.mkdir(parents=True)
    legacy.symlink_to(leftover, target_is_directory=True)

    monkeypatch.setattr(engine_mod, "engine_root", lambda: engine)
    monkeypatch.setattr(engine_mod, "skills_dir", lambda root=None: engine / ".claude" / "skills")

    result = engine_mod.link_skills(repo)

    assert result["ok"] is True
    assert ".claude/skills/start" in result["removed_legacy"]
    assert not legacy.exists()
    assert not legacy.is_symlink()
    assert (repo / ".claude" / "skills" / "mb-start" / "SKILL.md").exists()
    gitignore = (repo / ".gitignore").read_text(encoding="utf-8")
    assert ".claude/skills/start" not in gitignore.splitlines()


def test_link_skills_removes_legacy_project_symlink(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    old_engine = tmp_path / "old-engine"
    old_start = _write_skill(old_engine, "start")
    legacy = repo / ".claude" / "skills" / "start"
    legacy.parent.mkdir(parents=True)
    legacy.symlink_to(old_start, target_is_directory=True)

    result = engine_mod.link_skills(repo)

    assert result["ok"] is True
    assert ".claude/skills/start" in result["removed_legacy"]
    assert not legacy.exists()
    assert (repo / ".claude" / "skills" / "mb-start" / "SKILL.md").exists()


def test_link_skills_refuses_to_clobber_corrupt_local_settings(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "biz"
    engine = tmp_path / "engine"
    _write_skill(engine, "mb-start")
    settings = repo / ".claude" / "settings.local.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{not json", encoding="utf-8")

    monkeypatch.setattr(engine_mod, "engine_root", lambda: engine)
    monkeypatch.setattr(engine_mod, "skills_dir", lambda root=None: engine / ".claude" / "skills")

    result = engine_mod.link_skills(repo)

    assert result["ok"] is False
    assert "not valid JSON" in result["errors"][0]
    assert settings.read_text(encoding="utf-8") == "{not json"
    assert not (repo / ".claude" / "skills" / "mb-start").exists()


def test_link_skills_removes_retired_project_symlinks_and_gitignore_entries(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "biz"
    old_engine = tmp_path / "old-engine"
    old_vsl = _write_skill(old_engine, "mb-vsl")
    old_pull = _write_skill(old_engine, "mb-pull")
    skills = repo / ".claude" / "skills"
    skills.mkdir(parents=True)
    (skills / "mb-vsl").symlink_to(old_vsl, target_is_directory=True)
    (skills / "mb-pull").symlink_to(old_pull, target_is_directory=True)
    (repo / ".gitignore").write_text(
        "\n".join(
            [
                engine_mod.GITIGNORE_HEADER,
                ".claude/settings.local.json",
                ".claude/skills/mb-start",
                ".claude/skills/mb-vsl",
                ".claude/skills/mb-pull",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(engine_mod, "bundled_skills", lambda: ["mb-start"])

    result = engine_mod.link_skills(repo)

    assert result["ok"] is True
    assert ".claude/skills/mb-vsl" in result["removed_legacy"]
    assert ".claude/skills/mb-pull" in result["removed_legacy"]
    assert not (skills / "mb-vsl").exists()
    assert not (skills / "mb-pull").exists()
    gitignore = (repo / ".gitignore").read_text(encoding="utf-8")
    assert ".claude/skills/mb-start" in gitignore
    assert ".claude/skills/mb-vsl" not in gitignore
    assert ".claude/skills/mb-pull" not in gitignore


def test_link_skills_ignores_claude_code_worktrees(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "biz"

    monkeypatch.setattr(engine_mod, "bundled_skills", lambda: ["mb-start"])

    result = engine_mod.link_skills(repo)

    assert result["ok"] is True
    gitignore = (repo / ".gitignore").read_text(encoding="utf-8")
    assert ".claude/settings.local.json" in gitignore
    assert ".claude/worktrees/" in gitignore
    assert ".claude/skills/mb-start" in gitignore


def test_link_skills_removes_stale_mainbranch_engine_paths(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    stale_engine = tmp_path / "old-mainbranch"
    other_dir = tmp_path / "other-tools"
    unrelated_missing = tmp_path / "vip-clients"
    _write_skill(stale_engine, "start")
    (stale_engine / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    other_dir.mkdir()
    settings = repo / ".claude" / "settings.local.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps(
            {
                "permissions": {
                    "additionalDirectories": [
                        str(stale_engine),
                        str(tmp_path / "mb-vip"),
                        str(unrelated_missing),
                        str(other_dir),
                    ]
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = engine_mod.link_skills(repo)

    assert result["ok"] is True
    assert str(stale_engine) in result["removed_stale_engine_paths"]
    assert str(tmp_path / "mb-vip") in result["removed_stale_engine_paths"]
    repaired = json.loads(settings.read_text(encoding="utf-8"))
    dirs = repaired["permissions"]["additionalDirectories"]
    assert dirs[0] == result["engine_root"]
    assert str(stale_engine) not in dirs
    assert str(tmp_path / "mb-vip") not in dirs
    assert str(unrelated_missing) in dirs
    assert str(other_dir) in dirs


def test_mb_install_diagnostics_reports_multiple_versions(tmp_path: Path, monkeypatch) -> None:
    bin_a = tmp_path / "a"
    bin_b = tmp_path / "b"
    bin_a.mkdir()
    bin_b.mkdir()
    mb_a = bin_a / "mb"
    mb_b = bin_b / "mb"
    mb_a.write_text("#!/bin/sh\necho 'mb 0.3.22'\n", encoding="utf-8")
    mb_b.write_text("#!/bin/sh\necho 'mb 0.3.18'\n", encoding="utf-8")
    mb_a.chmod(0o755)
    mb_b.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_a}:{bin_b}")
    versions = {
        str(mb_a): "0.3.22",
        str(mb_b): "0.3.18",
    }
    monkeypatch.setattr(
        engine_mod,
        "_mb_binary_version",
        lambda path: {
            "ok": True,
            "version": versions[path],
            "output": f"mb {versions[path]}",
            "error": "",
        },
    )

    result = engine_mod.mb_install_diagnostics()

    assert result["active_path"] == str(mb_a)
    assert result["multiple_installs"] is True
    assert result["multiple_versions"] is True
    assert [item["version"] for item in result["installs"]] == ["0.3.22", "0.3.18"]
    assert result["repair_command"] == "mb skill link --repo ."


def _stub_mb(bin_dir: Path, marker: Path, version: str) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    mb = bin_dir / "mb"
    mb.write_text(f"#!/bin/sh\necho ran > {marker}\necho 'mb {version}'\n", encoding="utf-8")
    mb.chmod(0o755)
    return mb


def _login_shell(tmp_path: Path, login_path: Path, banner: str = "") -> Path:
    """A login shell whose PATH holds only `login_path` (no /etc/profile).

    Callers also pin the test process PATH so no real `mb` can be looked up.
    """

    shell = tmp_path / "login-shell"
    shell.write_text(
        f'#!/bin/sh\n{banner}PATH={login_path} exec /bin/sh -c "$2"\n',
        encoding="utf-8",
    )
    shell.chmod(0o755)
    return shell


def test_login_shell_mb_diagnostics_reports_other_mb_without_running_it(
    tmp_path: Path, monkeypatch
) -> None:
    marker = tmp_path / "ran-marker"
    running_mb = _stub_mb(tmp_path / "running", tmp_path / "running-marker", "0.3.29")
    stale_mb = _stub_mb(tmp_path / "stale", marker, "0.3.18")
    shell = _login_shell(tmp_path, stale_mb.parent)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(sys, "executable", str(running_mb.parent / "python"))

    result = engine_mod.login_shell_mb_diagnostics(str(shell))

    assert not marker.exists()
    assert "--version" not in result["command"]
    assert result["ok"] is False
    assert result["mismatch"] is True
    assert result["path_mismatch"] is True
    assert result["version_mismatch"] is False
    assert result["path"] == str(stale_mb)
    assert result["version"] == ""
    assert result["active_path"] == str(running_mb)
    assert result["active_version"] == __version__
    assert "different mb" in result["summary"]
    assert "0.3.18" not in result["summary"]


def test_login_shell_mb_diagnostics_ignores_login_shell_banner(tmp_path: Path, monkeypatch) -> None:
    marker = tmp_path / "ran-marker"
    mb = _stub_mb(tmp_path / "bin", marker, "0.3.29")
    shell = _login_shell(tmp_path, mb.parent, banner="echo welcome-banner\n")
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(sys, "executable", str(mb.parent / "python"))

    result = engine_mod.login_shell_mb_diagnostics(str(shell))

    assert not marker.exists()
    assert result["ok"] is True
    assert result["mismatch"] is False
    assert result["path"] == str(mb)
    assert result["version"] == __version__


def test_login_shell_mb_diagnostics_resolves_symlinked_same_install(
    tmp_path: Path, monkeypatch
) -> None:
    marker = tmp_path / "ran-marker"
    running_mb = _stub_mb(tmp_path / "running", marker, "0.3.29")
    link_dir = tmp_path / "link"
    link_dir.mkdir()
    (link_dir / "mb").symlink_to(running_mb)
    shell = _login_shell(tmp_path, link_dir)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(sys, "executable", str(running_mb.parent / "python"))

    result = engine_mod.login_shell_mb_diagnostics(str(shell))

    assert not marker.exists()
    assert result["ok"] is True
    assert result["path_mismatch"] is False


def test_login_shell_mb_diagnostics_unknown_active_path_claims_no_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    marker = tmp_path / "ran-marker"
    other = _stub_mb(tmp_path / "other", marker, "0.3.18")
    shell = _login_shell(tmp_path, other.parent)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(sys, "executable", str(tmp_path / "nowhere" / "python"))
    monkeypatch.setattr(sys, "argv", ["python", "-m", "mb"])

    result = engine_mod.login_shell_mb_diagnostics(str(shell))

    assert not marker.exists()
    assert result["active_path"] == ""
    assert result["path_mismatch"] is False
    assert result["version_mismatch"] is False
    assert result["ok"] is True
    assert "not compared" in result["summary"]
    assert "current mb command" not in result["summary"]


def test_login_shell_mb_diagnostics_prefers_the_script_that_started_the_process(
    tmp_path: Path, monkeypatch
) -> None:
    marker = tmp_path / "ran-marker"
    venv_mb = _stub_mb(tmp_path / "venv-bin", tmp_path / "venv-marker", "0.3.29")
    exposed_mb = _stub_mb(tmp_path / "exposed", marker, "0.3.29")
    shell = _login_shell(tmp_path, exposed_mb.parent)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(sys, "executable", str(venv_mb.parent / "python"))
    monkeypatch.setattr(sys, "argv", [str(exposed_mb), "status"])

    result = engine_mod.login_shell_mb_diagnostics(str(shell))

    assert not marker.exists()
    assert result["active_path"] == str(exposed_mb)
    assert result["path_mismatch"] is False
    assert result["ok"] is True


def test_link_status_explains_stale_engine_path_from_other_install(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "biz"
    stale_engine = tmp_path / "mb-vip"
    _write_skill(stale_engine, "start")
    (stale_engine / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    settings = repo / ".claude" / "settings.local.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"permissions": {"additionalDirectories": [str(stale_engine)]}}) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        engine_mod,
        "mb_install_diagnostics",
        lambda: {
            "active_path": "/tmp/new/mb",
            "current_version": "0.3.22",
            "multiple_installs": True,
            "multiple_versions": True,
            "installs": [
                {"path": "/tmp/new/mb", "version": "0.3.22"},
                {"path": "/tmp/old/mb", "version": "0.3.18"},
            ],
            "repair_command": "mb skill link --repo .",
        },
    )

    result = engine_mod.link_status(repo)

    assert result["ok"] is False
    assert str(stale_engine) in result["stale_engine_paths"]
    assert result["stale_from_other_install"] is True
    assert result["current_mb"]["path"] == "/tmp/new/mb"
    assert result["repair_command"] == "mb skill link --repo ."


def test_link_status_explains_worktree_wiring_gap(tmp_path: Path) -> None:
    import subprocess

    repo = tmp_path / "biz"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)

    git("init")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")
    (repo / "README.md").write_text("hi\n", encoding="utf-8")
    git("add", "README.md")
    git("commit", "-m", "baseline")
    worktree = repo / ".claude" / "worktrees" / "fresh"
    git("worktree", "add", "-b", "fresh", str(worktree))

    status = engine_mod.link_status(worktree)

    assert status["ok"] is False
    assert status["is_linked_worktree"] is True
    assert "git worktree" in status["summary"]
    assert "worktrees do not inherit" in status["summary"]
    assert "mb skill link --repo ." in status["summary"]

    primary = engine_mod.link_status(repo)
    assert primary["is_linked_worktree"] is False
    if not primary["ok"]:
        assert "worktree" not in primary["summary"]


def test_plugin_wiring_write_and_status(tmp_path: Path) -> None:
    import json as json_mod

    status = engine_mod.plugin_wiring_status(tmp_path)
    assert status["wired"] is False

    result = engine_mod.write_plugin_wiring(tmp_path)
    assert result["ok"] is True
    assert result["changed"] is True
    assert "/reload-plugins" in result["summary"]

    settings = json_mod.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings["extraKnownMarketplaces"]["mainbranch"]["source"] == {
        "source": "github",
        "repo": "noontide-co/mainbranch",
    }
    assert settings["enabledPlugins"]["mainbranch@mainbranch"] is True

    again = engine_mod.write_plugin_wiring(tmp_path)
    assert again["ok"] is True
    assert again["changed"] is False  # idempotent

    assert engine_mod.plugin_wiring_status(tmp_path)["wired"] is True
    assert engine_mod.link_status(tmp_path)["plugin"]["wired"] is True


def test_plugin_wiring_preserves_existing_settings(tmp_path: Path) -> None:
    import json as json_mod

    path = tmp_path / ".claude" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json_mod.dumps(
            {
                "permissions": {"allow": ["Bash(ls:*)"]},
                "extraKnownMarketplaces": {
                    "other": {"source": {"source": "github", "repo": "a/b"}}
                },
            }
        ),
        encoding="utf-8",
    )

    engine_mod.write_plugin_wiring(tmp_path)

    settings = json_mod.loads(path.read_text(encoding="utf-8"))
    assert settings["permissions"]["allow"] == ["Bash(ls:*)"]
    assert settings["extraKnownMarketplaces"]["other"]["source"]["repo"] == "a/b"
    assert settings["extraKnownMarketplaces"]["mainbranch"]["source"]["repo"] == (
        "noontide-co/mainbranch"
    )


def test_plugin_wiring_refuses_to_clobber_malformed_settings(tmp_path: Path) -> None:
    # A hand-edited-but-broken settings file (trailing comma) must NOT be
    # overwritten — that would silently destroy the operator's other keys.
    path = tmp_path / ".claude" / "settings.json"
    path.parent.mkdir(parents=True)
    malformed = '{\n  "permissions": {"allow": ["Bash(ls:*)"]},\n}\n'
    path.write_text(malformed, encoding="utf-8")

    result = engine_mod.write_plugin_wiring(tmp_path)

    assert result["ok"] is False
    assert result["changed"] is False
    assert "not valid JSON" in result["summary"]
    # File is untouched: bytes unchanged, no plugin keys injected.
    assert path.read_text(encoding="utf-8") == malformed
    assert "enabledPlugins" not in path.read_text(encoding="utf-8")
    assert engine_mod.plugin_wiring_status(tmp_path)["wired"] is False


def test_claude_plugin_status_reports_current_enabled_plugin(monkeypatch) -> None:
    payload = [
        {
            "id": "mainbranch@mainbranch",
            "version": "0.4.2",
            "scope": "user",
            "enabled": True,
            "installPath": "/tmp/mainbranch/0.4.2",
        }
    ]

    monkeypatch.setattr(
        engine_mod,
        "_run_claude_plugin_list",
        lambda timeout=5.0: subprocess.CompletedProcess(
            ["claude", "plugin", "list", "--json"],
            0,
            stdout=json.dumps(payload),
            stderr="",
        ),
    )

    status = engine_mod.claude_mainbranch_plugin_status(expected_version="0.4.2")

    assert status["checked"] is True
    assert status["ok"] is True
    assert status["state"] == "current"
    assert status["installed_version"] == "0.4.2"
    assert status["enabled_versions"] == ["0.4.2"]


def test_claude_plugin_status_reports_stale_enabled_plugin(monkeypatch) -> None:
    payload = [
        {
            "id": "mainbranch@mainbranch",
            "version": "0.4.1",
            "scope": "user",
            "enabled": True,
            "installPath": "/tmp/mainbranch/0.4.1",
        }
    ]

    monkeypatch.setattr(
        engine_mod,
        "_run_claude_plugin_list",
        lambda timeout=5.0: subprocess.CompletedProcess(
            ["claude", "plugin", "list", "--json"],
            0,
            stdout=json.dumps(payload),
            stderr="",
        ),
    )

    status = engine_mod.claude_mainbranch_plugin_status(expected_version="0.4.2")

    assert status["ok"] is False
    assert status["state"] == "stale"
    assert status["installed_version"] == "0.4.1"
    assert "expected 0.4.2" in status["summary"]


def test_claude_plugin_status_prefers_current_enabled_among_multiple_scopes(monkeypatch) -> None:
    payload = [
        {
            "id": "mainbranch@mainbranch",
            "version": "0.4.1",
            "scope": "project",
            "enabled": True,
            "installPath": "/tmp/mainbranch/0.4.1",
        },
        {
            "id": "mainbranch@mainbranch",
            "version": "0.4.2",
            "scope": "user",
            "enabled": True,
            "installPath": "/tmp/mainbranch/0.4.2",
        },
    ]

    monkeypatch.setattr(
        engine_mod,
        "_run_claude_plugin_list",
        lambda timeout=5.0: subprocess.CompletedProcess(
            ["claude", "plugin", "list", "--json"],
            0,
            stdout=json.dumps(payload),
            stderr="",
        ),
    )

    status = engine_mod.claude_mainbranch_plugin_status(expected_version="0.4.2")

    assert status["state"] == "current"
    assert status["installed_version"] == "0.4.2"
    assert status["enabled_versions"] == ["0.4.1", "0.4.2"]
    assert status["installed_versions"] == ["0.4.1", "0.4.2"]


def test_claude_plugin_status_reports_not_installed(monkeypatch) -> None:
    monkeypatch.setattr(
        engine_mod,
        "_run_claude_plugin_list",
        lambda timeout=5.0: subprocess.CompletedProcess(
            ["claude", "plugin", "list", "--json"],
            0,
            stdout=json.dumps([{"id": "other@market", "version": "1.0.0"}]),
            stderr="",
        ),
    )

    status = engine_mod.claude_mainbranch_plugin_status(expected_version="0.4.2")

    assert status["state"] == "not_installed"
    assert status["entries"] == []
    assert status["repair"].startswith("claude plugin marketplace update")


def test_worktree_summary_mentions_plugin_rail_when_wired(tmp_path: Path) -> None:
    import subprocess

    repo = tmp_path / "biz"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)

    git("init")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    engine_mod.write_plugin_wiring(repo)
    (repo / "README.md").write_text("hi\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "baseline")
    worktree = repo / ".claude" / "worktrees" / "fresh"
    git("worktree", "add", "-b", "fresh", str(worktree))

    status = engine_mod.link_status(worktree)

    assert status["ok"] is False  # symlink rail still missing in the worktree
    assert status["plugin"]["wired"] is True  # tracked wiring carried over
    assert "survives fresh worktrees" in status["summary"]
