"""Recorded references cannot select a foreign credential."""

import json
import subprocess

import pytest
from typer.testing import CliRunner

from mb import connect as c
from mb import google_connect as gc
from mb.cli import app
from mb.credential_store import SecretStore


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    target = tmp_path / "repo"
    target.mkdir()
    return target


@pytest.mark.parametrize(
    "provider,field",
    [
        ("stripe", "api_key"),
        ("google", "access_token"),
        ("google", "oauth_grant"),
        ("example-tool", "token"),
    ],
)
@pytest.mark.parametrize(
    "foreign", [("repo-b", None, None), (None, "cloudflare", None), (None, None, "other_field")]
)
def test_foreign_refs_never_read_or_release(repo, monkeypatch, provider, field, foreign):
    other_repo, other_provider, other_field = foreign
    ref = c._secret_ref(other_repo or "repo-a", other_provider or provider, other_field or field)
    entry = {"secrets": {field: {"ref": ref, "backend": "local-file"}}}
    c._write_config(repo, {"repo_id": "repo-a", "providers": {provider: entry}})

    def forbidden(*args, **kwargs):
        pytest.fail("foreign reference reached a credential consumer")

    monkeypatch.setattr(c, "_probe_secret_ref", forbidden)
    monkeypatch.setattr(SecretStore, "probe", forbidden)
    monkeypatch.setattr(gc, "_mint", forbidden)
    monkeypatch.setattr(c, "_read_onepassword_ref", forbidden)
    result = c.read_token(provider, repo)
    assert result["state"] == "credential_ref_mismatch"
    assert result["token"] == ""
    assert ref not in json.dumps(result)
    assert "Reconnect" in result["error"]
    status = c.status_provider(provider, repo)
    assert status["state"] == "credential_ref_mismatch"
    assert status["ok"] is False
    assert status["repair_command"]
    assert "not read" in status["summary"]
    assert provider in [item["provider"] for item in c.status_all(repo)["providers"]]
    for action in (c.test_provider, c.rotate_provider):
        with pytest.raises(c.ConnectRefusal, match="Reconnect") as caught:
            action(provider, repo)
        assert caught.value.rule == "credential_ref_mismatch"
    child = c.exec_with_secret(provider, ["synthetic-child"], repo, runner=forbidden)
    assert not child["ok"]
    output = CliRunner().invoke(app, ["connect", "token", provider, "--repo", str(repo), "--print"])
    assert output.exit_code != 0
    assert ref not in output.output
    if field == "oauth_grant":
        minted = gc.read_minted_token(entry, source="repo", target=repo)
        assert minted["state"] == "credential_ref_mismatch"
        assert "--client-file" in minted["repair_command"]
        assert "--client-file" in result["repair_command"]
        assert minted["token"] == ""


@pytest.mark.parametrize("scope", ["repo", "user"])
@pytest.mark.parametrize("provider", ["stripe", "google", "example-tool"])
def test_matching_refs_release_for_both_scopes(repo, monkeypatch, scope, provider):
    c.connect_provider(
        provider,
        repo,
        token="sk_test_synthetic_value",
        scope=scope,
        custom=provider == "example-tool",
    )
    assert c.read_token(provider, repo)["token"] == "sk_test_synthetic_value"
    monkeypatch.setenv("SYNTHETIC_SETTING", "kept")

    def child(command, **kwargs):
        assert command == ["synthetic-child", "--profile", "example"]
        setting = kwargs["env"]["SYNTHETIC_SETTING"]
        assert setting == "kept"
        return subprocess.CompletedProcess(command, 0)

    result = c.exec_with_secret(
        provider,
        ["synthetic-child", "--profile", "example"],
        repo,
        keep_env=["SYNTHETIC_SETTING"],
        runner=child,
    )
    assert result["ok"]


@pytest.mark.parametrize("scope", ["repo", "user"])
def test_matching_oauth_grant_mints(repo, monkeypatch, scope):
    gc.forget_minted()
    ref = c._secret_ref("repo-a", "google", "oauth_grant")
    entry = {"secrets": {"oauth_grant": {"ref": ref, "backend": "local-file"}}}
    config = {"repo_id": "repo-a", "providers": {"google": entry} if scope == "repo" else {}}
    c._write_config(repo, config)
    if scope == "user":
        monkeypatch.setattr(c, "_user_scope_provider_entry", lambda *args: entry)
    grant = json.dumps({"client_id": "synthetic-client", "refresh_token": "synthetic-refresh"})
    SecretStore("local-file").set(ref, grant)
    calls = []

    def mint(fields):
        calls.append(fields.refresh_token)
        return gc._Mint(ok=True, token="synthetic-access", expires_at=float("inf"))

    monkeypatch.setattr(gc, "_mint", mint)
    result = c.read_token("google", repo)
    assert result["token"] == "synthetic-access"
    assert result["source"] == scope
    assert calls == ["synthetic-refresh"]
    existing = gc._existing_entry(c._read_config(repo), "repo-a")
    client = gc._stored_client(existing)
    assert client is not None
    assert client.client_id == "synthetic-client"
    gc.forget_minted()


@pytest.mark.parametrize("scope", ["repo", "user"])
def test_matching_rotation_reads_source(repo, monkeypatch, scope):
    c.connect_provider(
        "example-tool",
        repo,
        custom=True,
        token="synthetic-old",
        scope=scope,
        metadata_pairs=["source=op://vault/item/field"],
    )
    calls = []

    def source(ref, **kwargs):
        calls.append(ref)
        return "synthetic-new"

    monkeypatch.setattr(c, "_read_onepassword_ref", source)
    c.rotate_provider("example-tool", repo)
    assert calls == ["op://vault/item/field"]
    assert c.read_token("example-tool", repo)["token"] == "synthetic-new"


def test_user_scope_mismatch_reports_without_reading(repo, monkeypatch):
    entry = {
        "provider": "stripe",
        "connected": True,
        "scope": "user",
        "secrets": {"api_key": {"ref": "mainbranch://foreign/stripe/api_key"}},
    }
    c._write_config(repo, {"repo_id": "repo-a", "providers": {}})
    monkeypatch.setattr(c, "_user_scope_provider_entry", lambda *args: entry)

    def forbidden(*args, **kwargs):
        pytest.fail("a mismatched user-scope record reached a credential read")

    monkeypatch.setattr(c, "_probe_secret_ref", forbidden)
    monkeypatch.setattr(SecretStore, "probe", forbidden)
    status = c.status_provider("stripe", repo)
    assert status["state"] == "credential_ref_mismatch"
    assert status["repair_command"]
