"""Storing a secret again keeps the provider's metadata and account label (#1149)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from typer.testing import CliRunner

from mb import connect as connect_mod
from mb import google_connect as google_connect_mod
from mb.cli import app

runner = CliRunner()


def _env(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    for provider in connect_mod.PROVIDERS:
        for env_var in provider.env_vars:
            monkeypatch.delenv(env_var, raising=False)
    repo = tmp_path / "biz"
    repo.mkdir()
    return repo


def _store(
    repo: Path, provider: str, *extra: str, custom: bool = False, token: str = "new-token"
) -> dict[str, Any]:
    args = ["connect", provider, "--repo", str(repo), "--token", token, "--json", *extra]
    if custom:
        args.append("--custom")
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert token not in result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    return payload


def _entry(repo: Path, provider: str) -> dict[str, Any]:
    data = yaml.safe_load((repo / ".mb" / "connect.yaml").read_text(encoding="utf-8"))
    entry: dict[str, Any] = data["providers"][provider]
    return entry


def _first(repo: Path, provider: str, *, custom: bool = False) -> dict[str, Any]:
    return _store(
        repo,
        provider,
        "--account",
        "Example Co",
        "--metadata",
        "account_id=acct-1",
        "--metadata",
        "api_user=svc",
        custom=custom,
        token="first-token",
    )


def test_custom_restore_without_flags_keeps_label_and_metadata(tmp_path, monkeypatch) -> None:
    repo = _env(monkeypatch, tmp_path)
    first = _first(repo, "examplehook", custom=True)
    assert "reconnect" not in first
    second = _store(repo, "examplehook")
    entry = _entry(repo, "examplehook")
    assert entry["account_label"] == "Example Co"
    assert entry["metadata"] == {"account_id": "acct-1", "api_user": "svc"}
    assert second["status"]["account_label"] == "Example Co"
    assert second["reconnect"] == {
        "account_label": "kept",
        "metadata": {"kept": ["account_id", "api_user"], "set": [], "removed": []},
    }


def test_custom_restore_with_account_replaces_label_only(tmp_path, monkeypatch) -> None:
    repo = _env(monkeypatch, tmp_path)
    _first(repo, "examplehook", custom=True)
    second = _store(repo, "examplehook", "--account", "Other Co", custom=True)
    entry = _entry(repo, "examplehook")
    assert entry["account_label"] == "Other Co"
    assert entry["metadata"] == {"account_id": "acct-1", "api_user": "svc"}
    assert second["reconnect"]["account_label"] == "replaced"


def test_account_empty_clears_label(tmp_path, monkeypatch) -> None:
    repo = _env(monkeypatch, tmp_path)
    _first(repo, "examplehook", custom=True)
    second = _store(repo, "examplehook", "--account", "")
    assert _entry(repo, "examplehook")["account_label"] == ""
    assert _entry(repo, "examplehook")["metadata"] == {"account_id": "acct-1", "api_user": "svc"}
    assert second["reconnect"]["account_label"] == "cleared"


def test_registry_provider_restore_keeps_label_and_metadata(tmp_path, monkeypatch) -> None:
    repo = _env(monkeypatch, tmp_path)
    _first(repo, "cloudflare")
    _store(repo, "cloudflare")
    entry = _entry(repo, "cloudflare")
    assert entry["account_label"] == "Example Co"
    assert entry["metadata"] == {"account_id": "acct-1", "api_user": "svc"}
    replaced = _store(repo, "cloudflare", "--account", "Other Co")
    assert _entry(repo, "cloudflare")["account_label"] == "Other Co"
    assert _entry(repo, "cloudflare")["metadata"]["account_id"] == "acct-1"
    assert replaced["reconnect"]["account_label"] == "replaced"


def test_metadata_update_and_removal_on_restore(tmp_path, monkeypatch) -> None:
    repo = _env(monkeypatch, tmp_path)
    _first(repo, "examplehook", custom=True)
    result = _store(
        repo,
        "examplehook",
        "--metadata",
        "account_id=acct-2",
        "--metadata",
        "api_user=",
        "--metadata",
        "region=eu",
    )
    entry = _entry(repo, "examplehook")
    assert entry["metadata"] == {"account_id": "acct-2", "region": "eu"}
    assert entry["account_label"] == "Example Co"
    assert result["reconnect"]["metadata"] == {
        "kept": [],
        "set": ["account_id", "region"],
        "removed": ["api_user"],
    }


def test_user_scope_restore_keeps_record_from_another_workspace(tmp_path, monkeypatch) -> None:
    repo = _env(monkeypatch, tmp_path)
    other = tmp_path / "workspace"
    other.mkdir()
    monkeypatch.setattr(
        connect_mod,
        "_git_output",
        lambda _repo, args: (
            "git@github.com:acme/business.git"
            if args == ["config", "--get", "remote.origin.url"]
            else ""
        ),
    )
    connect_mod.connect_provider(
        "examplehook",
        repo,
        token="first-token",
        account_label="Example Co",
        metadata_pairs=["account_id=acct-1"],
        scope="user",
        custom=True,
    )
    result = connect_mod.connect_provider(
        "examplehook", other, token="new-token", scope="user", custom=True
    )
    entry = _entry(other, "examplehook")
    assert entry["account_label"] == "Example Co"
    assert entry["metadata"] == {"account_id": "acct-1"}
    assert result["reconnect"]["account_label"] == "kept"
    # The same repo, scope user, keeps its own record too.
    connect_mod.connect_provider("examplehook", repo, token="third-token", scope="user")
    assert _entry(repo, "examplehook")["metadata"] == {"account_id": "acct-1"}


def test_first_connect_and_tokenless_edit_unchanged(tmp_path, monkeypatch) -> None:
    repo = _env(monkeypatch, tmp_path)
    first = _store(repo, "examplehook", "--metadata", "gone=", custom=True)
    assert "reconnect" not in first
    assert _entry(repo, "examplehook")["metadata"] == {"gone": ""}
    assert _entry(repo, "examplehook")["account_label"] == ""
    # A tokenless edit still records exactly what it was given.
    result = runner.invoke(
        app,
        ["connect", "examplehook", "--repo", str(repo), "--metadata", "only=1", "--json"],
    )
    assert result.exit_code == 0, result.output
    assert "reconnect" not in json.loads(result.stdout)
    assert _entry(repo, "examplehook")["metadata"] == {"only": "1"}


def test_restore_keeping_test_mode_refuses_live_key(tmp_path, monkeypatch) -> None:
    repo = _env(monkeypatch, tmp_path)
    _store(repo, "stripe", "--metadata", "mode=live", token="sk_live_" + "a" * 24)
    result = runner.invoke(
        app,
        ["connect", "stripe", "--repo", str(repo), "--token", "sk_test_" + "a" * 24, "--json"],
    )
    assert result.exit_code != 0
    assert _entry(repo, "stripe")["metadata"] == {"mode": "live"}


def test_secret_like_key_names_stay_out_of_reconnect(tmp_path, monkeypatch) -> None:
    repo = _env(monkeypatch, tmp_path)
    _store(repo, "examplehook", custom=True, token="first-token")
    path = repo / ".mb" / "connect.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["providers"]["examplehook"]["metadata"] = {"api_secret_x": "v", "account_id": "a"}
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    result = _store(repo, "examplehook")
    assert result["reconnect"]["metadata"]["kept"] == ["account_id"]


def test_google_merge_unchanged() -> None:
    merged = google_connect_mod.merge_oauth_metadata(
        {"ga4_property_id": "123456789", "search_console_site": "sc-domain:example.com", "x": ""},
        {"ga4_property_id": "", "search_console_site": "sc-domain:other.example"},
    )
    assert merged == {"search_console_site": "sc-domain:other.example"}
