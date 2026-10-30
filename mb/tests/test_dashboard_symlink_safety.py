"""The dashboard never writes through a symlink stored inside the repo."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mb import dashboard as dashboard_mod
from mb.cli import app
from mb.init import run as init_run

RUNNER = CliRunner()
SENTINEL = b"private-sentinel-content\n"


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "biz"
    init_run(path=str(repo), name="Acme")
    return repo


def _outside_file(tmp_path: Path) -> Path:
    target = tmp_path / "outside" / "target.txt"
    target.parent.mkdir()
    target.write_bytes(SENTINEL)
    return target


def _files(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


@pytest.mark.parametrize("command", ["build", "open"])
def test_output_file_symlink_is_refused_and_target_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    repo = _repo(tmp_path)
    target = _outside_file(tmp_path)
    link = repo / ".mb" / "dashboard" / "index.html"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)
    opened: list[str] = []

    def fake_open(uri: str) -> bool:
        opened.append(uri)
        return True

    monkeypatch.setattr(dashboard_mod, "_open_browser", fake_open)

    result = RUNNER.invoke(app, ["dashboard", command, "--repo", str(repo)])

    assert result.exit_code == 1
    assert ".mb/dashboard/index.html is a symlink" in result.output
    assert "Traceback" not in result.output
    assert target.read_bytes() == SENTINEL
    assert link.is_symlink()
    assert not opened


def test_dangling_output_symlink_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = tmp_path / "not-created.txt"
    link = repo / ".mb" / "dashboard" / "index.html"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)

    result = RUNNER.invoke(app, ["dashboard", "build", "--repo", str(repo)])

    assert result.exit_code == 1
    assert not target.exists()


@pytest.mark.parametrize(
    ("link_at", "named"),
    [(".mb", ".mb is a symlink"), (".mb/dashboard", ".mb/dashboard is a symlink")],
)
def test_parent_folder_symlink_is_refused(tmp_path: Path, link_at: str, named: str) -> None:
    repo = _repo(tmp_path)
    target = _outside_file(tmp_path)
    existing = target.parent / "index.html"
    existing.write_bytes(SENTINEL)
    (target.parent / "dashboard").symlink_to(target.parent)
    link = repo / link_at
    shutil.rmtree(link, ignore_errors=True)
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target.parent)
    before = _files(target.parent)

    result = RUNNER.invoke(app, ["dashboard", "build", "--repo", str(repo)])

    assert result.exit_code == 1
    assert named in result.output
    assert existing.read_bytes() == SENTINEL
    assert _files(target.parent) == before


def test_explicit_output_inside_repo_through_symlink_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = _outside_file(tmp_path)
    (repo / "reports").symlink_to(target.parent)

    result = RUNNER.invoke(
        app, ["dashboard", "build", "--repo", str(repo), "--output", "reports/../reports/x.html"]
    )

    assert result.exit_code == 1
    assert "reports is a symlink" in result.output
    assert _files(target.parent) == ["target.txt"]


def test_repo_reached_through_an_alias_is_still_checked(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = _outside_file(tmp_path)
    (repo / "reports").symlink_to(target.parent)
    alias = tmp_path / "alias"
    alias.symlink_to(repo)

    result = RUNNER.invoke(
        app,
        ["dashboard", "build", "--repo", str(repo), "--output", str(alias / "reports" / "x.html")],
    )

    assert result.exit_code == 1
    assert "reports is a symlink" in result.output
    assert _files(target.parent) == ["target.txt"]


def test_json_error_names_the_link(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / ".mb" / "dashboard").parent.mkdir(exist_ok=True)
    (repo / ".mb" / "dashboard").symlink_to(tmp_path)

    result = RUNNER.invoke(app, ["dashboard", "build", "--repo", str(repo), "--json"])

    payload = json.loads(result.output)
    assert result.exit_code == 1
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "unsafe_output_path"
    assert str(tmp_path) not in result.output


def test_default_output_rebuilds_as_a_regular_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    first = dashboard_mod.build(repo)
    second = dashboard_mod.build(repo)

    output = repo / ".mb" / "dashboard" / "index.html"
    assert first["output"]["path"] == second["output"]["path"] == ".mb/dashboard/index.html"
    assert output.is_file() and not output.is_symlink()
    assert output.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert (output.parent / ".gitignore").read_text(encoding="utf-8") == "*\n"


def test_explicit_output_outside_repo_keeps_working(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    output = tmp_path / "exports" / "dashboard.html"

    result = dashboard_mod.build(repo, output)

    assert result["output"]["inside_repo"] is False
    assert output.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert _files(output.parent) == ["dashboard.html"]


def test_explicit_output_through_symlink_outside_repo_keeps_working(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    real = tmp_path / "real-exports"
    real.mkdir()
    (tmp_path / "exports").symlink_to(real)

    dashboard_mod.build(repo, "../exports/dashboard.html")

    assert (real / "dashboard.html").is_file()


def test_output_symlink_outside_repo_is_replaced_not_followed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    target = _outside_file(tmp_path)
    link = tmp_path / "dashboard.html"
    link.symlink_to(target)

    dashboard_mod.build(repo, link)

    assert not link.is_symlink()
    assert link.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert target.read_bytes() == SENTINEL
