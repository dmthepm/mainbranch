"""Read-only source warnings preserve wiring and command behavior."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import __version__
from mb import doctor as doctor_mod
from mb import engine as engine_mod
from mb import start as start_mod
from mb import status as status_mod
from mb import update as update_mod
from mb.cli import app
from mb.init import run as init_run

CANONICAL = {"source": "github", "repo": "dmthepm/mainbranch"}
LEGACY = {"source": "github", "repo": "noontide-co/mainbranch"}


def _settings(repo: Path, source: object) -> Path:
    path = repo / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "extraKnownMarketplaces": {"mainbranch": {"source": source}},
                "enabledPlugins": {"mainbranch@mainbranch": True},
            }
        ),
        encoding="utf-8",
    )
    return path


def _registry(source: object) -> Path:
    path = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "plugins" / "known_marketplaces.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "mainbranch": {"source": source},
                "unrelated": {"private_marker": "DO_NOT_SHOW_OTHER_ENTRIES"},
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    "tracked,tracked_class",
    [
        (CANONICAL, "canonical"),
        (LEGACY, "legacy"),
        ({"source": "directory", "path": "./custom"}, "other"),
        ({"source": "github", "repo": ["invalid"]}, "other"),
        ([], "other"),
        (None, "absent"),
    ],
)
@pytest.mark.parametrize(
    "registered,registry_class",
    [
        (CANONICAL, "canonical"),
        (LEGACY, "legacy"),
        ({"source": "github", "repo": "example/custom"}, "other"),
        (False, "other"),
        (None, "absent"),
    ],
)
def test_source_combinations_are_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tracked: object,
    tracked_class: str,
    registered: object,
    registry_class: str,
) -> None:
    settings = _settings(tmp_path, tracked)
    registry = _registry(registered)
    before = {path: path.read_bytes() for path in (settings, registry)}

    def no_process(*args: Any, **kwargs: Any) -> None:
        pytest.fail("source inspection must not run a subprocess")

    monkeypatch.setattr(subprocess, "run", no_process)
    report = engine_mod.plugin_wiring_status(tmp_path)
    assert report["source_classification"] == tracked_class
    assert report["user_registry"] == {"source_classification": registry_class}
    assert report["wired"] is (tracked_class in {"canonical", "legacy"})
    assert report["marketplace_known"] is (tracked_class in {"canonical", "legacy"})
    assert report["plugin_enabled"] is True
    assert bool(report["warnings"]) is ("legacy" in {tracked_class, registry_class})
    assert "DO_NOT_SHOW_OTHER_ENTRIES" not in json.dumps(report)
    assert {path: path.read_bytes() for path in before} == before
    if report["warnings"]:
        assert "Removing the marketplace also uninstalls the plugin" in report["warnings"][0]
        assert "deletes its saved options and data" in report["warnings"][0]
        assert "docs/migrating.md" in report["warnings"][0]


@pytest.mark.parametrize(
    "content,expected",
    [
        (None, "absent"),
        ("{}", "absent"),
        ("{", "unreadable"),
        ("[]", "unreadable"),
        ("null", "unreadable"),
        ('{"mainbranch": []}', "unreadable"),
        ('{"mainbranch": {"source": []}}', "other"),
        ('{"unrelated": {"private_marker": "DO_NOT_SHOW_OTHER_ENTRIES"}}', "absent"),
    ],
)
def test_registry_missing_or_invalid(tmp_path: Path, content: str | None, expected: str) -> None:
    if content is not None:
        path = _registry(None)
        path.write_text(content, encoding="utf-8")
    report = engine_mod.plugin_wiring_status(tmp_path)
    assert report["wired"] is False
    assert report["user_registry"] == {"source_classification": expected}
    assert bool(report["warnings"]) is (expected == "unreadable")
    assert "DO_NOT_SHOW_OTHER_ENTRIES" not in json.dumps(report)


@pytest.mark.parametrize("error", [PermissionError, IsADirectoryError, UnicodeError])
def test_registry_unreadable_is_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: type[Exception],
) -> None:
    registry = _registry(CANONICAL)
    real_open = os.open

    def unreadable(path: Any, *args: Any, **kwargs: Any) -> int:
        if Path(path) == registry:
            raise error("DO_NOT_SHOW_OTHER_ENTRIES")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", unreadable)
    report = engine_mod.plugin_wiring_status(tmp_path)
    assert report["user_registry"] == {"source_classification": "unreadable"}
    assert "source is unknown" in report["warnings"][0]
    assert "DO_NOT_SHOW_OTHER_ENTRIES" not in json.dumps(report)


@pytest.fixture()
def business(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("COLUMNS", "240")
    monkeypatch.setattr(doctor_mod, "_which", lambda name: "")
    monkeypatch.setattr(status_mod, "_which", lambda name: "")
    monkeypatch.setattr(
        start_mod,
        "_which",
        lambda name: "/usr/bin/claude" if name == "claude" else (shutil.which(name) or ""),
    )
    repo = tmp_path / "business"
    init_run(path=str(repo), name="Example Business")
    return repo


@pytest.mark.parametrize("command", ["doctor", "status", "start"])
@pytest.mark.parametrize(
    "tracked,registered", [(LEGACY, CANONICAL), (CANONICAL, LEGACY), (LEGACY, LEGACY)]
)
def test_commands_warn_in_text_and_json_without_changing_success(
    business: Path,
    command: str,
    tracked: object,
    registered: object,
) -> None:
    runner = CliRunner()
    args = (
        [command, str(business)]
        if command in {"doctor", "status"}
        else [command, "--repo", str(business)]
    )
    _settings(business, CANONICAL)
    _registry(CANONICAL)
    baseline = runner.invoke(app, [*args, "--json"])
    baseline_report = json.loads(baseline.stdout)
    settings = _settings(business, tracked)
    registry = _registry(registered)
    before = {path: path.read_bytes() for path in (settings, registry)}
    result = runner.invoke(app, [*args, "--json"])
    assert result.exit_code == baseline.exit_code, result.stdout
    report = json.loads(result.stdout)
    assert report["ok"] == baseline_report["ok"]
    if command == "doctor":
        check = next(c for c in report["checks"] if c["name"] == "plugin-source")
        assert check["severity"] == "warn"
        assert check["ok"] is False
        plugin = check["plugin"]
    else:
        plugin = report["runtime"]["skill_wiring"]["plugin"]
    assert plugin["wired"] is True
    assert plugin["warnings"] == [engine_mod.PLUGIN_SOURCE_MOVE_WARNING]
    human = runner.invoke(app, args)
    assert human.exit_code == baseline.exit_code, human.stdout
    text = " ".join(re.sub(r"\x1b\[[0-9;]*m", "", human.stdout).split())
    assert "old noontide-co/mainbranch" in text
    assert "docs/migrating.md" in text
    assert "deletes its saved options and data" in text
    assert "DO_NOT_SHOW_OTHER_ENTRIES" not in result.stdout + text
    assert {path: path.read_bytes() for path in before} == before


def test_legacy_source_does_not_block_launch(
    business: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings(business, LEGACY)
    _registry(LEGACY)
    launched: list[Path] = []
    monkeypatch.setattr(start_mod, "_is_interactive_terminal", lambda: True)

    def launch(path: Path) -> int:
        launched.append(path)
        return 0

    monkeypatch.setattr(start_mod, "_launch_claude", launch)
    report = start_mod.run(str(business), launch=True)
    assert report["ok"] is True, report["checks"]
    assert report["launch"]["attempted"] is True
    assert launched == [business.resolve()]


@pytest.mark.parametrize("check", [True, False])
@pytest.mark.parametrize(
    "tracked,registered", [(LEGACY, CANONICAL), (CANONICAL, LEGACY), (LEGACY, LEGACY)]
)
def test_update_warns_even_when_versions_match(
    business: Path,
    monkeypatch: pytest.MonkeyPatch,
    tracked: object,
    registered: object,
    check: bool,
) -> None:
    _settings(business, tracked)
    registry = _registry(registered)
    before = registry.read_bytes()
    monkeypatch.setattr(update_mod, "install_mode", lambda: "wheel")
    monkeypatch.setattr(update_mod, "_uv_tool_dir_holds_this_install", lambda: False)
    monkeypatch.setattr(update_mod, "_latest_pypi_version", lambda: __version__)
    monkeypatch.setattr(
        update_mod,
        "claude_mainbranch_plugin_status",
        lambda **kwargs: {
            "state": "current",
            "ok": True,
            "installed_version": __version__,
        },
    )

    def no_command(*args: Any, **kwargs: Any) -> None:
        pytest.fail("matching-version warning must not execute a command")

    monkeypatch.setattr(update_mod, "_run_command", no_command)
    args = ["update", "--repo", str(business), "--no-refresh-surfaces"]
    if check:
        args.append("--check")
    runner = CliRunner()
    result = runner.invoke(app, [*args, "--json"])
    assert result.exit_code == 0, result.stdout
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["plugin_rail"]["wired"] is True
    assert engine_mod.PLUGIN_SOURCE_MOVE_WARNING in report["warnings"]
    assert not any("symlink-only" in w for w in report["warnings"])
    human = runner.invoke(app, args)
    assert human.exit_code == 0, human.stdout
    assert "old noontide-co/mainbranch" in human.stdout
    assert "deletes its saved options and data" in human.stdout
    assert "DO_NOT_SHOW_OTHER_ENTRIES" not in result.stdout + human.stdout
    assert registry.read_bytes() == before


@pytest.mark.parametrize("content", ["{", "[]", "null", '{"extraKnownMarketplaces": []}'])
def test_invalid_tracked_settings_keep_existing_wiring_result(tmp_path: Path, content: str) -> None:
    path = _settings(tmp_path, None)
    path.write_text(content, encoding="utf-8")
    report = engine_mod.plugin_wiring_status(tmp_path)
    assert report["wired"] is False
    assert report["source_classification"] == "absent"
    assert path.read_text(encoding="utf-8") == content


def test_registry_uses_default_claude_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = Path.home() / ".claude" / "plugins" / "known_marketplaces.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"mainbranch": {"source": LEGACY}}), encoding="utf-8")
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert engine_mod.plugin_registry_status() == {"source_classification": "legacy"}


def _registry_path() -> Path:
    path = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "plugins" / "known_marketplaces.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_fifo_registry_is_unreadable_and_does_not_block() -> None:
    os.mkfifo(_registry_path())
    assert engine_mod.plugin_registry_status() == {"source_classification": "unreadable"}


def test_symlink_to_a_fifo_is_unreadable_and_does_not_block(tmp_path: Path) -> None:
    fifo = tmp_path / "example-fifo"
    os.mkfifo(fifo)
    _registry_path().symlink_to(fifo)
    assert engine_mod.plugin_registry_status() == {"source_classification": "unreadable"}


def test_symlink_to_a_regular_registry_still_reads(tmp_path: Path) -> None:
    real = tmp_path / "example-registry.json"
    real.write_text(json.dumps({"mainbranch": {"source": LEGACY}}), encoding="utf-8")
    _registry_path().symlink_to(real)
    assert engine_mod.plugin_registry_status() == {"source_classification": "legacy"}


def test_directory_registry_is_unreadable() -> None:
    _registry_path().mkdir()
    assert engine_mod.plugin_registry_status() == {"source_classification": "unreadable"}


def test_oversized_registry_is_unreadable() -> None:
    _registry_path().write_text(
        " " * (engine_mod.PLUGIN_REGISTRY_MAX_BYTES + 1) + "{}", encoding="utf-8"
    )
    assert engine_mod.plugin_registry_status() == {"source_classification": "unreadable"}


def test_deeply_nested_registry_is_unreadable() -> None:
    depth = 200_000
    _registry_path().write_text('{"other":' + "[" * depth + "]" * depth + "}", encoding="utf-8")
    assert engine_mod.plugin_registry_status() == {"source_classification": "unreadable"}


def test_unresolvable_config_dir_is_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "~example-no-such-user/.claude")
    assert engine_mod.plugin_registry_status() == {"source_classification": "unreadable"}


def test_warning_reserves_the_move_for_the_owner() -> None:
    warning = engine_mod.PLUGIN_SOURCE_MOVE_WARNING
    assert "must not do it without their approval" in warning
    assert "deletes its saved options" in warning
