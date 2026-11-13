"""Stored-secret comparisons use synthetic credentials and local stores."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mb import connect
from mb.cli import app
from mb.credential_store import SecretProbe, SecretStore

runner = CliRunner()
SECRET = "fixture-only-café-secret\n"


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    target = tmp_path / "repo"
    target.mkdir()
    return target


@pytest.mark.parametrize(
    "provider,custom,slot", [("cloudflare", False, "api_token"), ("fixture-alias", True, "api_key")]
)
@pytest.mark.parametrize("json_out", [False, True])
def test_fingerprint_exact_bytes_without_terminal(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    custom: bool,
    slot: str,
    json_out: bool,
) -> None:
    connect.connect_provider(provider, repo=repo, token=SECRET, custom=custom)
    # Install preserves its own input rules; set the exact synthetic stored bytes.
    entry = connect._read_config(repo)["providers"][provider]
    SecretStore("local-file").set(entry["secrets"][slot]["ref"], SECRET)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    args = ["connect", "fingerprint", provider, "--repo", str(repo)]
    result = runner.invoke(app, args + (["--json"] if json_out else []))
    assert result.exit_code == 0, result.output
    expected = "sha256:" + hashlib.sha256(SECRET.encode("utf-8")).hexdigest()[:8]
    if json_out:
        assert json.loads(result.stdout) == {
            "ok": True,
            "provider": provider,
            "slot": slot,
            "fingerprint": expected,
        }
    else:
        assert result.stdout.strip() == f"{provider} {slot} {expected}"
    audit = connect.audit_path().read_text()
    records = [json.loads(line) for line in audit.splitlines()]
    assert len(records) == 1
    assert records[0]["verb"] == "fingerprint"
    assert records[0]["result"] == "released"
    assert expected not in audit
    for output in (result.stdout, result.stderr, audit):
        assert SECRET not in output
        assert SECRET.strip() not in output


@pytest.mark.parametrize(
    "state", ["not_connected", "missing_secret", connect.BACKEND_FAILURE_STATE]
)
def test_fingerprint_failure_is_scriptable(
    repo: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    if state != "not_connected":
        connect.connect_provider("cloudflare", repo=repo, token="fixture-only")
        if state == "missing_secret":
            entry = connect._read_config(repo)["providers"]["cloudflare"]
            SecretStore("local-file").delete(entry["secrets"]["api_token"]["ref"])
        else:
            monkeypatch.setattr(
                connect,
                "_entry_secret_probe",
                lambda *args: SecretProbe(
                    present=False, value="", backend_ok=False, reason="keychain_unavailable"
                ),
            )
    result = runner.invoke(
        app, ["connect", "fingerprint", "cloudflare", "--repo", str(repo), "--json"]
    )
    assert result.exit_code == 1, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["state"] == state
    assert len(result.stderr.strip().splitlines()) == 1
    assert len(connect.audit_path().read_text().splitlines()) == 1


@pytest.mark.parametrize("json_out", [False, True])
def test_custom_alias_has_no_test_repair(repo: Path, json_out: bool) -> None:
    connect.connect_provider("fixture-alias", repo=repo, token="fixture-only", custom=True)
    for verb in ("status", "test"):
        result = runner.invoke(
            app,
            ["connect", verb, "fixture-alias", "--repo", str(repo)]
            + (["--json"] if json_out else []),
        )
        if not json_out:
            assert "no probe for custom aliases" in result.stdout
            assert "can't verify" in result.stdout
            assert "next: mb connect test" not in result.stdout
            continue
        payload = json.loads(result.stdout)
        status = payload["status"] if verb == "test" else payload
        assert status["stored"] is True
        assert status["provider_verified"] is False
        assert "no probe for custom aliases" in status["summary"]
        assert "can't verify" in status["summary"]
        assert status["repair_command"] == ""
        assert "mb connect test" not in status["repair"]


def test_fingerprint_google_does_not_mint(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    connect.connect_provider("google", repo=repo, token="fixture-stored-google")
    monkeypatch.setattr(connect, "_records_oauth_grant", lambda *args: True)
    from mb import google_connect

    def no_mint(*args: object, **kwargs: object) -> None:
        pytest.fail("fingerprint must not mint an access token")

    monkeypatch.setattr(google_connect, "read_minted_token", no_mint)
    result = runner.invoke(app, ["connect", "fingerprint", "google", "--repo", str(repo), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["fingerprint"] == (
        "sha256:" + hashlib.sha256(b"fixture-stored-google").hexdigest()[:8]
    )


@pytest.mark.parametrize("refusal", ["audit", "caller", "unknown", "missing_provider"])
def test_fingerprint_refusals(repo: Path, monkeypatch: pytest.MonkeyPatch, refusal: str) -> None:
    connect.connect_provider("cloudflare", repo=repo, token="fixture-only")
    args = ["connect", "fingerprint", "cloudflare", "--repo", str(repo), "--json"]
    expected = 2
    if refusal == "audit":
        connect.audit_path().parent.mkdir(parents=True, exist_ok=True)
        connect.audit_path().mkdir()
        expected = 1
    elif refusal == "caller":
        config = connect._read_config(repo)
        config["caller_policy"] = {"default": "deny"}
        connect._write_config(repo, config)
        expected = 3
    elif refusal == "unknown":
        args[2] = "unknown-fixture"
    else:
        args.pop(2)
    result = runner.invoke(app, args)
    assert result.exit_code == expected, result.output
    assert json.loads(result.stdout)["ok"] is False
    assert "sha256:" not in result.output
    assert "fixture-only" not in result.output
    if refusal != "audit":
        assert len(connect.audit_path().read_text().splitlines()) == 1


def test_fingerprint_resolves_repo_from_subfolder(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    connect.connect_provider("cloudflare", repo=repo, token="fixture-only")
    nested = repo / "nested"
    nested.mkdir()
    monkeypatch.chdir(nested)
    result = runner.invoke(app, ["connect", "fingerprint", "cloudflare", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["fingerprint"] == (
        "sha256:" + hashlib.sha256(b"fixture-only").hexdigest()[:8]
    )


def test_custom_alias_aggregate_status_explains_probe(repo: Path) -> None:
    connect.connect_provider("fixture-alias", repo=repo, token="fixture-only", custom=True)
    result = runner.invoke(app, ["connect", "status", "--repo", str(repo)])
    assert "no probe for custom aliases" in result.stdout
    assert "next: mb connect test fixture-alias" not in result.stdout
