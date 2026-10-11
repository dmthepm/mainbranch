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


def _edit(repo: Path, *args: str, ok: bool = True) -> dict[str, Any]:
    result = runner.invoke(app, ["connect", "examplehook", "--repo", str(repo), "--json", *args])
    assert (result.exit_code == 0) == ok, result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    return payload


def test_first_tokenless_connect_unchanged(tmp_path, monkeypatch) -> None:
    repo = _env(monkeypatch, tmp_path)
    first = _store(repo, "examplehook", "--metadata", "gone=", custom=True)
    assert "reconnect" not in first
    assert _entry(repo, "examplehook")["metadata"] == {"gone": ""}
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    out = _edit(
        fresh, "--custom", "--account", "Only", "--metadata", "k=v", "--metadata", "z=", ok=False
    )
    assert "reconnect" not in out
    assert _entry(fresh, "examplehook")["account_label"] == "Only"
    assert _entry(fresh, "examplehook")["metadata"] == {"k": "v", "z": ""}


def test_tokenless_metadata_edit_keeps_label_and_other_keys(tmp_path, monkeypatch) -> None:
    repo = _env(monkeypatch, tmp_path)
    _first(repo, "examplehook", custom=True)
    out = _edit(repo, "--custom", "--metadata", "region=eu", "--metadata", "api_user=")
    entry = _entry(repo, "examplehook")
    assert entry["metadata"] == {"account_id": "acct-1", "region": "eu"}
    assert entry["account_label"] == "Example Co"
    assert entry["connected"] is True
    assert entry["secrets"]
    assert out["reconnect"]["metadata"]["removed"] == ["api_user"]


def test_tokenless_account_alone_keeps_metadata_and_clear_works(tmp_path, monkeypatch) -> None:
    repo = _env(monkeypatch, tmp_path)
    _first(repo, "examplehook", custom=True)
    _edit(repo, "--account", "Other Co")
    assert _entry(repo, "examplehook")["account_label"] == "Other Co"
    assert _entry(repo, "examplehook")["metadata"] == {"account_id": "acct-1", "api_user": "svc"}
    _edit(repo, "--account", "")
    assert _entry(repo, "examplehook")["account_label"] == ""
    assert _entry(repo, "examplehook")["metadata"] == {"account_id": "acct-1", "api_user": "svc"}


def test_tokenless_scope_change_keeps_label_and_metadata(tmp_path, monkeypatch) -> None:
    repo = _env(monkeypatch, tmp_path)
    _first(repo, "examplehook", custom=True)
    _edit(repo, "--scope", "user")
    entry = _entry(repo, "examplehook")
    assert entry["scope"] == "user"
    assert entry["account_label"] == "Example Co"
    assert entry["metadata"] == {"account_id": "acct-1", "api_user": "svc"}


def _restore_refusal(repo: Path, kept_mode: str, key_prefix: str) -> dict[str, Any]:
    other = "test" if kept_mode == "live" else "live"
    _store(repo, "stripe", "--metadata", f"mode={kept_mode}", token=f"sk_{kept_mode}_" + "a" * 24)
    result = runner.invoke(
        app,
        ["connect", "stripe", "--repo", str(repo), "--token", key_prefix + "a" * 24, "--json"],
    )
    assert result.exit_code != 0
    assert _entry(repo, "stripe")["metadata"] == {"mode": kept_mode}
    assert f"sk_{other}_" + "a" * 24 not in result.output
    payload: dict[str, Any] = json.loads(result.stdout)
    return payload


def test_restore_kept_live_refuses_test_key_names_fix(tmp_path, monkeypatch) -> None:
    repo = _env(monkeypatch, tmp_path)
    payload = _restore_refusal(repo, "live", "sk_test_")
    assert payload["rule"] == "stripe_mode_mismatch"
    assert "`--metadata mode=test`" in payload["summary"]


def test_restore_kept_test_refuses_live_key_names_fix(tmp_path, monkeypatch) -> None:
    repo = _env(monkeypatch, tmp_path)
    payload = _restore_refusal(repo, "test", "sk_live_")
    assert payload["rule"] == "stripe_mode_mismatch"
    assert "`--metadata mode=live`" in payload["summary"]


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
