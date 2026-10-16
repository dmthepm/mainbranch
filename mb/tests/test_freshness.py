"""Package freshness metadata and update alert copy."""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest

from mb import freshness as freshness_mod
from mb.freshness import (
    checked_release_version,
    compare_versions,
    format_update_alert,
    package_update_status,
)


def test_required_update_status_for_version_below_minimum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    update = package_update_status(
        tmp_path,
        installed_version="0.1.2",
        latest_version="0.2.1",
        mode="pipx",
    )

    assert update["installed"] == "0.1.2"
    assert update["latest"] == "0.2.1"
    assert update["minimum_supported"] == "0.2.0"
    assert update["severity"] == "required"
    assert update["command"] == "pipx upgrade mainbranch"
    assert update["update_check_command"] == "mb update --check --json"
    assert update["post_update_commands"] == ["mb skill link --repo .", "mb doctor"]
    assert update["latest_source"] == "provided"
    assert update["release_notes_url"].endswith("/oe-v0.2.1")
    assert update["reason"] == (
        "Installed version predates mb update and the current skill-link repair flow."
    )

    alert = format_update_alert(update)
    assert "Update required." in alert
    assert "setup and skills may not work correctly" in alert
    assert "pipx upgrade mainbranch" in alert
    assert "mb update is not available in 0.1.2" in alert
    assert "mb skill link --repo ." in alert
    assert "mb doctor" in alert


def test_required_update_without_repo_still_has_generic_repair_commands() -> None:
    update = package_update_status(
        None,
        installed_version="0.1.2",
        latest_version="0.2.1",
        mode="pipx",
    )

    assert update["post_update_commands"] == ["mb skill link --repo .", "mb doctor"]
    alert = format_update_alert(update)
    assert "Then, from your business repo:" in alert
    assert "mb skill link --repo ." in alert
    assert "mb doctor" in alert


def test_recommended_update_status_for_supported_stale_version(tmp_path: Path) -> None:
    update = package_update_status(
        tmp_path,
        installed_version="0.2.0",
        latest_version="0.2.1",
        mode="pipx",
    )

    assert update["severity"] == "recommended"
    assert update["command"] == "mb update"
    assert update["update_check_command"] == "mb update --check --json"
    assert update["installed"] == "0.2.0"
    assert update["latest"] == "0.2.1"
    assert update["minimum_supported"] == "0.2.0"
    assert update["latest_source"] == "provided"
    assert update["release_notes_url"].endswith("/oe-v0.2.1")

    alert = format_update_alert(update)
    assert "Update recommended." in alert
    assert "Your install is still supported" in alert
    assert "mb update" in alert


def test_current_source_install_does_not_render_alert(tmp_path: Path) -> None:
    update = package_update_status(
        tmp_path,
        installed_version="0.2.0",
        latest_version="0.2.1",
        mode="source",
    )

    assert update["severity"] == "current"
    assert update["latest"] == "0.2.1"
    assert update["latest_source"] == "not_applicable"
    assert update["update_check_command"] == ""
    assert format_update_alert(update) == ""


@pytest.mark.parametrize(
    ("mode", "command"),
    [
        ("pipx", "pipx upgrade mainbranch"),
        ("uv", "uv tool install --refresh mainbranch==0.6.2"),
        ("wheel", "pip install --upgrade mainbranch"),
    ],
)
def test_required_update_names_the_command_for_the_install_mode(mode: str, command: str) -> None:
    # #965: the required-update command follows the install, not always pipx.
    update = package_update_status(
        None, installed_version="0.1.0", latest_version="0.6.2", mode=mode
    )

    assert update["severity"] == "required"
    assert update["install_mode"] == mode
    assert update["command"] == command
    alert = format_update_alert(update)
    assert f"  {command}" in alert
    assert ("must use pipx" in alert) is (mode == "pipx")
    if mode != "pipx":
        assert "pipx" not in alert


def test_required_update_unknown_mode_gets_mode_neutral_copy() -> None:
    update = package_update_status(
        None, installed_version="0.1.0", latest_version="0.6.2", mode="unknown"
    )

    assert update["severity"] == "required"
    assert update["command"] == ""
    alert = format_update_alert(update)
    assert "with the tool that installed it (pipx, uv or pip)" in alert
    assert "Run this first:" not in alert
    assert "must use pipx" not in alert


@pytest.mark.parametrize("mode", ["clone", "source"])
def test_required_update_does_not_apply_to_clone_or_source(mode: str) -> None:
    update = package_update_status(
        None, installed_version="0.1.0", latest_version="0.6.2", mode=mode
    )

    assert update["severity"] == "current"
    assert update["command"] == ""
    assert format_update_alert(update) == ""


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("0.6.3rc1", "0.6.2", 1),
        ("0.6.3rc1", "0.6.3", -1),
        ("0.6.3.dev0", "0.6.3rc1", -1),
        ("0.6.3", "0.6.3.0", 0),
        ("0.6.3.post1", "0.6.3", 1),
        ("0.6.3+local", "0.6.3", 1),
        ("0.6.10", "0.6.9", 1),
    ],
)
def test_compare_versions_follows_pep440(left: str, right: str, expected: int) -> None:
    assert compare_versions(left, right) == expected


@pytest.mark.parametrize(
    ("installed", "latest", "severity"),
    [
        ("0.6.3rc1", "0.6.3", "recommended"),
        ("0.6.3.dev2", "0.6.3", "recommended"),
        ("0.6.3", "0.6.3rc1", "current"),
        ("0.6.3", "0.6.3.post1", "recommended"),
    ],
)
def test_recommended_update_orders_pre_releases_like_installers(
    installed: str, latest: str, severity: str
) -> None:
    # "recommended" uses the same PEP 440 ordering as `mb update` (#1028).
    update = package_update_status(
        None, installed_version=installed, latest_version=latest, mode="pipx"
    )

    assert update["severity"] == severity


@pytest.mark.parametrize("latest", ["not-a-version", "<html>", "0.6.x"])
def test_unparseable_latest_version_counts_as_unknown(latest: str) -> None:
    update = package_update_status(
        None, installed_version="0.6.3", latest_version=latest, mode="pipx"
    )

    assert update["severity"] == "unknown"
    assert update["latest"] == ""
    assert update["command"] == ""
    assert update["release_notes_url"] == ""


def test_unparseable_pypi_answer_counts_as_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(freshness_mod, "latest_pypi_version", lambda: "<html>")

    update = package_update_status(None, installed_version="0.6.3", mode="pipx")

    assert update["severity"] == "unknown"
    assert update["latest"] == ""
    assert update["latest_source"] == "unavailable"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.6.3", "0.6.3"),
        (" 0.6.3rc1\n", "0.6.3rc1"),
        ("0.7.0.dev2", "0.7.0.dev2"),
        ("0.6.3.post1", "0.6.3.post1"),
        ("not-a-version", None),
        ("", None),
        (None, None),
    ],
)
def test_checked_release_version(raw: object, expected: str | None) -> None:
    assert checked_release_version(raw) == expected


class _Response:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("[1, 2]", None),
        ("null", None),
        ("3", None),
        ('"x"', None),
        ('{"info": [1]}', None),
        ('{"info": {"version": "0.6.3"}}', "0.6.3"),
    ],
)
def test_latest_pypi_version_treats_non_object_json_as_unknown(
    monkeypatch: pytest.MonkeyPatch, body: str, expected: str | None
) -> None:
    # #1039: valid JSON that is not an object carries no version.
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda url, timeout=0.0: _Response(body),
    )

    assert freshness_mod.latest_pypi_version() == expected
