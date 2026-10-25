"""Repo maintenance skips unsafe .gitignore files and preserves regular files."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mb import books, dashboard, doctor, engine, issue, migrate, onboard, status
from mb.cli import app
from mb.init import run as init_run
from mb.migrations.base import MigrationInfo, MigrationPlan

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
def test_doctor_repair_skips_link_and_applies_other_repairs(
    tmp_path: Path, dangling: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor, "_which", lambda name: f"/usr/bin/{name}")
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


@pytest.mark.parametrize("dangling", [False, True])
def test_status_marker_check_skips_unsafe_gitignore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dangling: bool
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    sentinel = tmp_path / "sentinel"
    if not dangling:
        sentinel.write_text(status.LAST_STATUS_SEEN_GITIGNORE_ENTRY + "\n", encoding="utf-8")
    (repo / ".gitignore").symlink_to(sentinel)
    monkeypatch.setattr(status, "_which", lambda name: "")

    state = status._marker_gitignore_state(repo)

    assert state["ok"] is False
    assert HINT in state["repair"]
    assert (repo / ".gitignore").is_symlink()


def test_books_entries_skip_symlinked_gitignore(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    sentinel = _unsafe_gitignore(tmp_path, repo, False)

    assert books._gitignore_entries(repo) == set()
    assert sentinel.read_bytes() == SENTINEL


@pytest.mark.parametrize("dangling", [False, True])
def test_migration_plans_no_write_through_unsafe_gitignore(tmp_path: Path, dangling: bool) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    sentinel = _unsafe_gitignore(tmp_path, repo, dangling)
    info = MigrationInfo(id="t", name="t", from_version="0", to_version="1", description="t")
    plans = [MigrationPlan(migration=info)]

    migrate._ensure_gitignore_plan(repo, plans)

    assert plans[0].changes == []
    _assert_preserved(repo, sentinel, dangling)


def test_migration_still_plans_regular_gitignore(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    info = MigrationInfo(id="t", name="t", from_version="0", to_version="1", description="t")
    plans = [MigrationPlan(migration=info)]

    migrate._ensure_gitignore_plan(repo, plans)

    assert [change.path for change in plans[0].changes] == [".gitignore"]


@pytest.mark.parametrize("dangling", [False, True])
@pytest.mark.parametrize(
    "ensure", [onboard._ensure_onboarding_gitignore, issue.ensure_issue_gitignore]
)
def test_default_ignore_helpers_skip_unsafe_gitignore(
    tmp_path: Path, dangling: bool, ensure: Callable[[Path], bool]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    sentinel = _unsafe_gitignore(tmp_path, repo, dangling)

    assert ensure(repo) is False
    _assert_preserved(repo, sentinel, dangling)


@pytest.mark.parametrize(
    "ensure", [onboard._ensure_onboarding_gitignore, issue.ensure_issue_gitignore]
)
def test_default_ignore_helpers_still_append_to_regular_gitignore(
    tmp_path: Path, ensure: Callable[[Path], bool]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")

    assert ensure(repo) is True
    assert (repo / ".gitignore").read_text(encoding="utf-8").startswith("node_modules/\n")


def test_dashboard_does_not_write_through_dangling_ignore_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    out_dir = repo / ".mb" / "dashboard"
    out_dir.mkdir(parents=True)
    target = tmp_path / "created-outside"
    (out_dir / ".gitignore").symlink_to(target)
    monkeypatch.setattr(dashboard, "collect", lambda root: {"repo": str(root)})
    monkeypatch.setattr(dashboard, "render_html", lambda data: "<html></html>")

    dashboard.build(repo, out_dir / "index.html")

    assert (out_dir / ".gitignore").is_symlink()
    assert not target.exists()


def test_dashboard_still_writes_its_own_ignore_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    out_dir = repo / ".mb" / "dashboard"
    repo.mkdir()
    monkeypatch.setattr(dashboard, "collect", lambda root: {"repo": str(root)})
    monkeypatch.setattr(dashboard, "render_html", lambda data: "<html></html>")

    dashboard.build(repo, out_dir / "index.html")

    assert (out_dir / ".gitignore").read_text(encoding="utf-8") == "*\n"
