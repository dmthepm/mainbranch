"""Repo maintenance skips unsafe .gitignore files and preserves regular files."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mb import doctor, engine
from mb.cli import app
from mb.init import run as init_run

SENTINEL = b"private-sentinel-content\n"
HINT = "Replace it with a regular file, then rerun."


def _unsafe_gitignore(tmp_path: Path, repo: Path, dangling: bool) -> Path:
    sentinel = tmp_path / "sentinel"
    if not dangling:
        sentinel.write_bytes(SENTINEL)
    (repo / ".gitignore").symlink_to(sentinel)
    return sentinel


def _assert_preserved(repo: Path, sentinel: Path, dangling: bool) -> None:
    assert (repo / ".gitignore").is_symlink()
    if dangling:
        assert not sentinel.exists()
    else:
        assert sentinel.read_bytes() == SENTINEL


@pytest.mark.parametrize("dangling", [False, True])
def test_doctor_repair_skips_link_and_applies_other_repairs(tmp_path: Path, dangling: bool) -> None:
    repo = tmp_path / "repo"
    init_run(path=str(repo), name="Test", infer_github_identity=False)
    (repo / ".gitignore").unlink()
    sentinel = _unsafe_gitignore(tmp_path, repo, dangling)
    hook = repo / ".git/hooks/commit-msg"
    hook.unlink()

    result = CliRunner().invoke(app, ["doctor", "repair", "--repo", str(repo), "--apply", "--json"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    _assert_preserved(repo, sentinel, dangling)
    assert HINT in result.output
    assert ".gitignore is a symlink" in result.output
    assert hook.is_file()
    assert any(a["id"] == "checkpoint-hook-install" for a in report["applied_actions"])
    assert not any(a["id"] == "gitignore-local-state" for a in report["applied_actions"])

    # The existing append contract includes preserving the input's final newline behavior.
    (repo / ".gitignore").unlink()
    (repo / ".gitignore").write_text("custom\n.mb/local.yaml")
    assert doctor._append_unique_lines(repo / ".gitignore", [".mb/local.yaml", ".mb/backups/"])
    assert (repo / ".gitignore").read_bytes() == b"custom\n.mb/local.yaml\n.mb/backups/\n"


@pytest.mark.parametrize("dangling", [False, True])
@pytest.mark.parametrize("json_out", [False, True])
@pytest.mark.parametrize("plan", [False, True])
def test_skill_link_skips_link_without_copying_content(
    tmp_path: Path, dangling: bool, json_out: bool, plan: bool
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    sentinel = _unsafe_gitignore(tmp_path, repo, dangling)
    args = [sys.executable, "-m", "mb", "skill", "link", "--repo", str(repo)]
    if json_out:
        args.append("--json")
    if plan:
        args.append("--plan")
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        cwd=Path(engine.__file__).parents[1],
    )

    assert result.returncode == 0, result.stdout + result.stderr
    _assert_preserved(repo, sentinel, dangling)
    assert HINT in result.stderr
    assert SENTINEL.decode().strip() not in result.stdout + result.stderr
    if json_out:
        report = json.loads(result.stdout)
        assert HINT in report["warnings"][0]
        assert ".gitignore" in report["skipped"]
        if plan:
            assert not any(op["path"] == str(repo / ".gitignore") for op in report["operations"])
            assert report["gitignore_add"] == []
            assert report["gitignore_remove"] == []
        else:
            assert ".gitignore" not in report["created"]
    if plan:
        assert not (repo / ".claude").exists()
    else:
        assert (repo / ".claude/skills/mb-start").is_symlink()
        assert (repo / ".claude/settings.local.json").is_file()
        for path in repo.rglob("*"):
            if path.is_file() and not path.is_symlink():
                assert SENTINEL not in path.read_bytes()


@pytest.mark.parametrize("dangling", [False, True])
def test_init_keeps_link_and_other_scaffolding(tmp_path: Path, dangling: bool) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    sentinel = _unsafe_gitignore(tmp_path, repo, dangling)

    result = init_run(path=str(repo), name="Test", infer_github_identity=False)

    assert result["status"] == "ok"
    _assert_preserved(repo, sentinel, dangling)
    assert any(HINT in warning for warning in result["warnings"])
    assert (repo / "CLAUDE.md").is_file()
    assert (repo / ".claude/skills/mb-start").is_symlink()
    assert SENTINEL.decode().strip() not in json.dumps(result)


def test_doctor_read_skips_symlink_and_reports_finding(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    sentinel = _unsafe_gitignore(tmp_path, repo, False)

    assert doctor._read_gitignore_entries(repo) == set()
    assert HINT in doctor._local_state_summary(repo)["summary"]
    assert sentinel.read_bytes() == SENTINEL


def test_nonregular_gitignore_is_skipped(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    path = repo / ".gitignore"
    path.mkdir()
    assert doctor._read_gitignore_entries(repo) == set()
    assert not doctor._append_unique_lines(path, [".mb/local.yaml"])
    result = engine.plan_link_skills(repo)
    assert result["ok"]
    assert any(HINT in warning for warning in result["warnings"])
    assert not any(op["path"] == str(path) for op in result["operations"])
