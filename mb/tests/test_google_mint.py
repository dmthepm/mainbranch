"""Tests for read-time minting on an OAuth `google` connection (#1004, PR4).

`read_token`, `mb connect token google` and `mb connect exec google` mint a
short-lived access token from the stored grant. No network: the token
endpoint is a stub sender, and the loopback-only guard, the local-file
credential store and the synthetic sentinels come from test_google_connect.
"""

# The fixtures are imported from test_google_connect, so test parameters
# share their names by design.
# ruff: noqa: F811

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from mb import connect as connect_mod
from mb import credential_store as credential_store_mod
from mb import google_connect as gc
from mb import google_oauth as go
from mb.cli import app
from tests.test_google_connect import (  # noqa: F401 (fixtures are used by name)
    CLIENT_ID,
    CLIENT_SECRET,
    LEGACY_TOKEN,
    MINTED,
    REFRESH,
    REFRESH_2,
    SENTINELS,
    FailingSet,
    _config,
    _google_entry,
    _local_secrets,
    _oauth,
    _signin_args,
    _stored_grant,
    assert_no_sentinel,
    client_file,
    google,
    google_env,
    loopback_only_network,
    repo,
    runner,
)

MINTED_2 = "SYNTH-MINTED-0002"
DESCRIPTION = "SYNTH-DESCRIPTION-0001"
# Never printed by a read: the long-lived grant and Google's free text.
GRANT_SENTINELS = (CLIENT_SECRET, REFRESH, REFRESH_2, DESCRIPTION)


class MintEndpoint:
    """Stub token endpoint for the refresh grant only."""

    def __init__(
        self,
        *,
        status: int = 200,
        payload: Any = None,
        raw: bytes | None = None,
        raises: BaseException | None = None,
        tokens: tuple[str, ...] = (MINTED,),
    ) -> None:
        self.status = status
        self.payload = payload
        self.raw = raw
        self.raises = raises
        self.tokens = tokens
        self.calls: list[dict[str, list[str]]] = []

    def __call__(
        self, url: str, body: bytes, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, bytes]:
        import urllib.parse

        assert url == go.TOKEN_ENDPOINT
        fields = urllib.parse.parse_qs(body.decode("ascii"))
        assert fields["grant_type"] == ["refresh_token"]
        self.calls.append(fields)
        if self.raises is not None:
            raise self.raises
        if self.raw is not None:
            return self.status, self.raw
        payload = self.payload
        if payload is None:
            token = self.tokens[min(len(self.calls), len(self.tokens)) - 1]
            payload = {"access_token": token, "expires_in": 3599, "token_type": "Bearer"}
        return self.status, json.dumps(payload).encode("utf-8")


def _signed_in(repo: Path, client_file: Path, google: Any, *extra: str) -> None:
    google()
    result = _oauth(repo, *_signin_args(client_file), *extra)
    assert result.exit_code == 0, result.output


def _mint_with(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> MintEndpoint:
    endpoint = MintEndpoint(**kwargs)
    monkeypatch.setattr(gc, "token_sender", endpoint)
    return endpoint


def _no_google(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> tuple[int, bytes]:
        pytest.fail("Google's token endpoint was called")

    monkeypatch.setattr(gc, "token_sender", refuse)


def _token(repo: Path) -> Any:
    return runner.invoke(app, ["connect", "token", "google", "--repo", str(repo), "--print"])


def _status(repo: Path) -> tuple[int, dict[str, Any]]:
    result = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo), "--json"])
    return result.exit_code, json.loads(result.stdout)


CHILD = """
import json, os, sys
secrets = json.loads(sys.argv[2])
report = {
    "names_holding_minted": sorted(k for k, v in os.environ.items() if v == secrets["minted"]),
    "names_holding_grant": sorted(
        k for k, v in os.environ.items() if any(s in v for s in secrets["grant"])
    ),
    "argv_leak": any(s in " ".join(sys.argv[3:]) for s in secrets["grant"] + [secrets["minted"]]),
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(report, handle)
print("child ran")
sys.exit(int(os.environ.get("CHILD_EXIT", "0")))
"""


def _exec(repo: Path, report: Path, *extra: str) -> Any:
    secrets = json.dumps({"minted": MINTED, "grant": list(GRANT_SENTINELS)})
    command = [sys.executable, "-c", CHILD, str(report), secrets, *extra]
    return runner.invoke(
        app,
        [
            "connect",
            "exec",
            "google",
            "--repo",
            str(repo),
            "--keep-env",
            "CHILD_EXIT",
            "--",
            *command,
        ],
    )


# --- Minting -----------------------------------------------------------------


def test_read_token_mints_from_the_grant(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google)
    endpoint = _mint_with(monkeypatch)

    result = connect_mod.read_token("google", repo)

    assert result["ok"] is True
    assert result["field"] == "access_token"
    assert result["token"] == MINTED
    assert result["state"] == "ready"
    assert result["source"] == "repo"
    (call,) = endpoint.calls
    assert call["refresh_token"] == [REFRESH]
    assert call["client_id"] == [CLIENT_ID]
    assert call["client_secret"] == [CLIENT_SECRET]
    # Nothing minted is written back to the store.
    assert MINTED not in json.dumps(_local_secrets())


def test_read_token_mints_from_a_user_scope_entry(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google, "--scope", "user")
    (repo / ".mb" / "connect.yaml").unlink()
    _mint_with(monkeypatch)

    result = connect_mod.read_token("google", repo)

    assert result["ok"] is True
    assert result["source"] == "user"
    assert result["token"] == MINTED


def test_grant_without_client_secret_sends_none(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google)
    ref = _google_entry(repo)["secrets"]["oauth_grant"]["ref"]
    credential_store_mod.SecretStore("local-file").set(
        ref, json.dumps({"client_id": CLIENT_ID, "refresh_token": REFRESH})
    )
    endpoint = _mint_with(monkeypatch)

    assert connect_mod.read_token("google", repo)["token"] == MINTED
    assert "client_secret" not in endpoint.calls[0]


def test_token_command_prints_only_the_minted_token(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google)
    _mint_with(monkeypatch)

    result = _token(repo)

    assert result.exit_code == 0, result.output
    assert result.stdout == MINTED
    assert "--print without an interactive terminal is deprecated" in result.stderr


def test_token_command_still_refuses_a_terminal_without_print(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google)
    endpoint = _mint_with(monkeypatch)

    result = runner.invoke(app, ["connect", "token", "google", "--repo", str(repo)])

    assert result.exit_code == connect_mod.TOKEN_REFUSED_EXIT_CODE
    assert endpoint.calls == []
    assert MINTED not in result.output


def test_exec_child_gets_only_the_minted_token(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _signed_in(repo, client_file, google)
    _mint_with(monkeypatch)
    report_path = tmp_path / "child.json"

    result = _exec(repo, report_path)

    assert result.exit_code == 0, result.output
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["names_holding_minted"] == ["GOOGLE_OAUTH_TOKEN"]
    assert report["names_holding_grant"] == []
    assert report["argv_leak"] is False


def test_one_mint_per_process(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _signed_in(repo, client_file, google)
    endpoint = _mint_with(monkeypatch, tokens=(MINTED, MINTED_2))

    first = connect_mod.read_token("google", repo)["token"]
    second = connect_mod.read_token("google", repo)["token"]
    assert _token(repo).stdout == MINTED
    assert _exec(repo, tmp_path / "child.json").exit_code == 0

    assert first == second == MINTED
    assert len(endpoint.calls) == 1


def test_minted_token_is_reminted_near_expiry(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google)
    endpoint = _mint_with(monkeypatch, tokens=(MINTED, MINTED_2))
    now = [1000.0]
    monkeypatch.setattr(gc, "monotonic", lambda: now[0])

    assert connect_mod.read_token("google", repo)["token"] == MINTED
    now[0] += 3599 - gc.MINT_EXPIRY_MARGIN_SECONDS - 1
    assert connect_mod.read_token("google", repo)["token"] == MINTED
    now[0] += 2
    assert connect_mod.read_token("google", repo)["token"] == MINTED_2
    assert len(endpoint.calls) == 2


def test_reauth_drops_a_token_minted_from_the_old_grant(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google)
    _mint_with(monkeypatch)
    assert connect_mod.read_token("google", repo)["token"] == MINTED

    google(refresh=REFRESH_2)
    assert _oauth(repo, "--reauth").exit_code == 0
    endpoint = _mint_with(monkeypatch, tokens=(MINTED_2,))

    assert connect_mod.read_token("google", repo)["token"] == MINTED_2
    assert endpoint.calls[0]["refresh_token"] == [REFRESH_2]


# --- Failures ----------------------------------------------------------------

FAILURES: dict[str, dict[str, Any]] = {
    "invalid_grant": {
        "endpoint": {
            "status": 400,
            "payload": {"error": "invalid_grant", "error_description": DESCRIPTION},
        },
        "rule": "reauth_required",
        "state": "reauth_required",
        "repair": "mb connect google --oauth --reauth",
        "recorded": True,
    },
    "invalid_rapt": {
        "endpoint": {
            "status": 400,
            "payload": {
                "error": "invalid_grant",
                "error_subtype": "invalid_rapt",
                "error_description": DESCRIPTION,
            },
        },
        "rule": "reauth_required",
        "state": "reauth_required",
        "repair": "mb connect google --oauth --reauth",
        "recorded": True,
    },
    "unreachable": {
        "endpoint": {"raises": OSError(f"connection refused {DESCRIPTION}")},
        "rule": "token_unreachable",
        "state": "unvalidated",
        "repair": "",
        "recorded": False,
    },
    "transport_value_error": {
        "endpoint": {"raises": ValueError(f"bad url {DESCRIPTION}")},
        "rule": "token_unreachable",
        "state": "unvalidated",
        "repair": "",
        "recorded": False,
    },
    "malformed_html": {
        "endpoint": {"raw": f"<html>{DESCRIPTION}</html>".encode()},
        "rule": "token_response_malformed",
        "state": "unvalidated",
        "repair": "",
        "recorded": False,
    },
    "malformed_no_token": {
        "endpoint": {"payload": {"token_type": "Bearer", "note": DESCRIPTION}},
        "rule": "token_response_malformed",
        "state": "unvalidated",
        "repair": "",
        "recorded": False,
    },
    "server_error": {
        "endpoint": {"status": 503, "payload": {"error_description": DESCRIPTION}},
        "rule": "token_request_failed",
        "state": "unvalidated",
        "repair": "",
        "recorded": False,
    },
    "invalid_client": {
        "endpoint": {
            "status": 401,
            "payload": {"error": "invalid_client", "error_description": DESCRIPTION},
        },
        "rule": "oauth_client_rejected",
        "state": "invalid",
        "repair": gc.REAUTH_WITH_CLIENT_COMMAND,
        "recorded": False,
    },
}


@pytest.mark.parametrize("case", sorted(FAILURES))
def test_mint_failures(
    case: str,
    repo: Path,
    client_file: Path,
    google: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = FAILURES[case]
    _signed_in(repo, client_file, google)
    _, before = _status(repo)
    endpoint = _mint_with(monkeypatch, **spec["endpoint"])

    result = connect_mod.read_token("google", repo)
    token = _token(repo)
    report_path = tmp_path / "child.json"
    executed = _exec(repo, report_path)

    assert result["ok"] is False
    assert result["token"] == ""
    assert result["field"] == "access_token"
    assert result["rule"] == spec["rule"]
    assert result["state"] == spec["state"]
    assert result["repair_command"] == spec["repair"]
    # Exit codes follow the existing contracts: 1, and the child never runs.
    assert token.exit_code == 1
    assert token.stdout == ""
    assert executed.exit_code == 1
    assert not report_path.exists()
    for output in (token, executed):
        assert output.stderr.startswith(("mb connect token: ", "mb connect exec: "))
        if spec["repair"]:
            assert f"repair: {spec['repair']}" in output.stderr
        for sentinel in (*GRANT_SENTINELS, MINTED):
            assert sentinel not in output.output
    assert_no_sentinel(json.dumps(result))
    assert DESCRIPTION not in json.dumps(result)
    # One token call for the whole process, failure included.
    assert len(endpoint.calls) == 1

    code, after = _status(repo)
    assert len(endpoint.calls) == 1  # status never calls Google
    if spec["recorded"]:
        assert code == 1
        assert after["state"] == "reauth_required"
        assert after["repair_command"] == "mb connect google --oauth --reauth"
        assert after["validation"]["state"] == "reauth_required"
        assert after["provider_verified"] is False
    else:
        assert after["state"] == before["state"]
        assert after["validation"] == before["validation"]


def test_reauth_required_is_recorded_once_and_cleared_by_reauth(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google)
    _mint_with(monkeypatch, status=400, payload={"error": "invalid_grant"})
    assert connect_mod.read_token("google", repo)["rule"] == "reauth_required"
    doctor = runner.invoke(app, ["connect", "doctor", "--repo", str(repo), "--json"])
    assert doctor.exit_code == 1

    google(refresh=REFRESH_2)
    assert _oauth(repo, "--reauth").exit_code == 0
    _, item = _status(repo)
    assert item["state"] == "unvalidated"
    assert item["repair_command"] == "mb connect test google"


def test_a_later_successful_mint_clears_a_recorded_reauth_required(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google)
    _mint_with(monkeypatch, status=400, payload={"error": "invalid_grant"})
    connect_mod.read_token("google", repo)
    assert _status(repo)[1]["state"] == "reauth_required"
    gc.forget_minted()  # a new `mb` process
    _mint_with(monkeypatch)

    assert connect_mod.read_token("google", repo)["ok"] is True
    assert _status(repo)[1]["state"] == "unvalidated"


def test_reauth_required_recorded_in_user_scope(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google, "--scope", "user")
    _mint_with(monkeypatch, status=400, payload={"error": "invalid_grant"})
    connect_mod.read_token("google", repo)

    assert _status(repo)[1]["state"] == "reauth_required"
    repo_id = str(_config(repo)["repo_id"])
    user_entry = connect_mod._user_scope_provider_entry(repo_id, "google") or {}
    assert user_entry["validation"]["state"] == "reauth_required"


def test_recording_failure_does_not_change_the_read_result(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google)
    _mint_with(monkeypatch, status=400, payload={"error": "invalid_grant"})

    def broken_write_config(target: Path, config: dict[str, Any]) -> Path:
        raise OSError("read-only file system")

    monkeypatch.setattr(connect_mod, "_write_config", broken_write_config)
    result = connect_mod.read_token("google", repo)

    assert result["rule"] == "reauth_required"


@pytest.mark.parametrize(
    "stored",
    [
        "not json",
        "[]",
        json.dumps({"client_id": CLIENT_ID}),
        json.dumps({"refresh_token": REFRESH}),
        json.dumps({"client_id": CLIENT_ID, "refresh_token": REFRESH, "client_secret": 7}),
    ],
)
def test_corrupt_grant(
    stored: str,
    repo: Path,
    client_file: Path,
    google: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _signed_in(repo, client_file, google)
    ref = _google_entry(repo)["secrets"]["oauth_grant"]["ref"]
    credential_store_mod.SecretStore("local-file").set(ref, stored)
    _, before = _status(repo)
    _no_google(monkeypatch)

    result = connect_mod.read_token("google", repo)
    token = _token(repo)

    assert result["ok"] is False
    assert result["rule"] == "oauth_grant_malformed"
    assert result["state"] == "invalid"
    # One rule (#1073): a grant that still holds its OAuth client renews with
    # bare --reauth, which reads the client from it; otherwise the client file.
    expected = gc.REAUTH_COMMAND if gc.client_from_grant(stored) else gc.REAUTH_WITH_CLIENT_COMMAND
    assert result["repair_command"] == expected
    assert token.exit_code == 1
    assert expected in token.stderr
    assert ("--client-file" in token.stderr) is (expected == gc.REAUTH_WITH_CLIENT_COMMAND)
    for sentinel in GRANT_SENTINELS:
        assert sentinel not in token.output + json.dumps(result)
    assert _status(repo)[1]["state"] == before["state"]


def test_missing_grant(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google)
    ref = _google_entry(repo)["secrets"]["oauth_grant"]["ref"]
    credential_store_mod.SecretStore("local-file").delete(ref)
    _no_google(monkeypatch)

    result = connect_mod.read_token("google", repo)

    assert result["ok"] is False
    assert result["rule"] == "oauth_grant_missing"
    assert result["state"] == "missing_secret"
    assert result["repair_command"] == gc.REAUTH_WITH_CLIENT_COMMAND


def test_locked_store_reads_as_backend_failure(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google)
    _no_google(monkeypatch)

    def locked(*args: Any, **kwargs: Any) -> credential_store_mod.SecretProbe:
        return credential_store_mod.SecretProbe("", False, False, "keychain_locked")

    monkeypatch.setattr(connect_mod, "_probe_secret_ref", locked)
    result = connect_mod.read_token("google", repo)

    assert result["ok"] is False
    assert result["state"] == connect_mod.BACKEND_FAILURE_STATE
    assert result["backend_state"] == "keychain_locked"


# --- Legacy and other providers are unchanged --------------------------------


def test_legacy_access_token_google_never_mints(
    repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    connect_mod.connect_provider("google", repo=repo, token=LEGACY_TOKEN)
    _no_google(monkeypatch)

    result = connect_mod.read_token("google", repo)
    assert result == {
        "ok": True,
        "provider": "google",
        "field": "access_token",
        "source": "repo",
        "token": LEGACY_TOKEN,
        "state": "ready",
        "backend_state": "ready",
        "error": "",
        "repair_command": "",
    }
    token = _token(repo)
    assert token.exit_code == 0
    assert token.stdout == LEGACY_TOKEN
    item = connect_mod.status_provider("google", repo)
    assert item["credential_mode"] == "access_token"
    assert "oauth" not in item


def test_ga4_provider_is_untouched(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    connect_mod.connect_provider("ga4", repo=repo, token=LEGACY_TOKEN)
    _no_google(monkeypatch)

    result = connect_mod.read_token("ga4", repo)

    assert result["token"] == LEGACY_TOKEN
    assert "rule" not in result
    assert "credential_mode" not in connect_mod.status_provider("ga4", repo)


def test_not_connected_google_is_unchanged(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_google(monkeypatch)
    result = connect_mod.read_token("google", repo)
    assert result["state"] == "not_connected"
    assert "rule" not in result


# --- exec exit codes ---------------------------------------------------------


def test_exec_exit_codes_unchanged_in_oauth_mode(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _signed_in(repo, client_file, google)
    _mint_with(monkeypatch)
    monkeypatch.setenv("CHILD_EXIT", "3")

    assert _exec(repo, tmp_path / "child.json").exit_code == 3
    missing = runner.invoke(
        app,
        ["connect", "exec", "google", "--repo", str(repo), "--", str(tmp_path / "no-such-cmd")],
    )
    assert missing.exit_code == 127
    no_command = runner.invoke(app, ["connect", "exec", "google", "--repo", str(repo)])
    assert no_command.exit_code == 2


# --- Status ------------------------------------------------------------------


def test_status_shows_a_coarse_refresh_token_expiry(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google)
    _no_google(monkeypatch)

    code, item = _status(repo)

    expires_on = item["oauth"]["refresh_token_expires_on"]
    assert re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", expires_on)
    # The stub grants 604799 s (7 days); allow for a run across midnight UTC.
    today = datetime.now(timezone.utc).date()
    assert expires_on in {
        (today + timedelta(days=6)).isoformat(),
        (today + timedelta(days=7)).isoformat(),
    }
    assert _google_entry(repo)["oauth"] == {"refresh_token_expires_on": expires_on}


def test_status_expiry_is_empty_without_a_time_limit_or_when_hand_edited(
    repo: Path, client_file: Path, google: Any
) -> None:
    _signed_in(repo, client_file, google)
    config = _config(repo)
    config["providers"]["google"]["oauth"] = {"refresh_token_expires_on": "next week"}
    connect_mod._write_config(repo, config)

    item = connect_mod.status_provider("google", repo)

    # `grants` was added beside it (additive, #1004 hardening).
    assert item["oauth"] == {"refresh_token_expires_on": "", "grants": ["search_console", "ga4"]}
    assert gc.refresh_token_expires_on({}) == ""
    assert gc._expires_on(go.TokenResponse({"access_token": MINTED})) == ""
    assert gc._expires_on(go.TokenResponse({"refresh_token_expires_in": True})) == ""


# --- Bootstrap follow-ups: Ctrl-C, crashes and user scope --------------------


class InterruptingSet:
    """Let the first ``after`` credential writes through, then raise ``exc``."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, after: int, exc: BaseException) -> None:
        self.count = 0
        real_set = credential_store_mod.SecretStore.set

        def fake_set(store: Any, ref: str, value: str, **kwargs: Any) -> None:
            self.count += 1
            if self.count > after:
                raise exc
            real_set(store, ref, value, **kwargs)

        monkeypatch.setattr(credential_store_mod.SecretStore, "set", fake_set)


def test_ctrl_c_before_any_write_says_nothing_was_stored(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    google()

    def interrupted_browser(url: str) -> bool:
        raise KeyboardInterrupt

    monkeypatch.setattr(gc, "open_browser", interrupted_browser)

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 130
    assert "Nothing was stored." in json.loads(result.stdout)["summary"]
    assert _local_secrets() == {}


def test_ctrl_c_during_the_grant_write_says_it_may_have_been_stored(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    google()
    InterruptingSet(monkeypatch, 0, KeyboardInterrupt())

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 130
    summary = json.loads(result.stdout)["summary"]
    assert "Nothing was stored" not in summary
    assert "may have been stored" in summary
    assert "the connection is not set up" in summary
    assert "Re-run `mb connect google --oauth --scope repo" in summary
    assert f"--repo {repo}` to finish it, with the same OAuth client and metadata." in summary
    assert_no_sentinel(result.output)


def test_ctrl_c_during_the_grant_write_on_reauth(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google)
    google(refresh=REFRESH_2)
    InterruptingSet(monkeypatch, 0, KeyboardInterrupt())

    result = _oauth(repo, "--reauth", "--client-file", str(client_file), "--json")

    assert result.exit_code == 130
    summary = json.loads(result.stdout)["summary"]
    assert "may have been stored" in summary
    assert "replaced the old grant" in summary
    assert f"`mb connect test google --repo {repo}`" in summary
    assert_no_sentinel(result.output)


def test_ctrl_c_after_grant_write_on_first_sign_in(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    google()
    InterruptingSet(monkeypatch, 1, KeyboardInterrupt())

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 130
    payload = json.loads(result.stdout)
    assert payload["state"] == "cancelled"
    summary = payload["summary"]
    assert "Nothing was stored" not in summary
    assert "cancelled part way" in summary
    assert "the connection is not set up" in summary
    assert "Re-run `mb connect google --oauth --scope repo" in summary
    assert f"--repo {repo}` to finish it, with the same OAuth client and metadata." in summary
    assert_no_sentinel(result.output)


def test_ctrl_c_after_grant_write_on_reauth(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google)
    google(refresh=REFRESH_2)
    InterruptingSet(monkeypatch, 1, KeyboardInterrupt())

    result = _oauth(repo, "--reauth", "--json")

    assert result.exit_code == 130
    summary = json.loads(result.stdout)["summary"]
    assert "Nothing was stored" not in summary
    assert "The new Google grant is stored and replaced the old one" in summary
    assert _stored_grant(repo)["refresh_token"] == REFRESH_2
    assert_no_sentinel(result.output)


def test_ctrl_c_during_metadata_write(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    google()

    def interrupted(target: Path, config: dict[str, Any]) -> Path:
        raise KeyboardInterrupt

    monkeypatch.setattr(connect_mod, "_write_config", interrupted)
    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 130
    summary = json.loads(result.stdout)["summary"]
    assert "Nothing was stored" not in summary
    assert "the connection is not set up" in summary


def test_ctrl_c_after_the_sign_in_finished(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    google()

    def interrupted(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise KeyboardInterrupt

    monkeypatch.setattr(connect_mod, "status_provider", interrupted)
    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 130
    summary = json.loads(result.stdout)["summary"]
    assert "after it finished: the new sign-in is stored and recorded" in summary


def test_crash_after_grant_write_says_what_is_stored(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    google()
    InterruptingSet(monkeypatch, 1, RuntimeError(f"boom {REFRESH} {CLIENT_SECRET}"))

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["state"] == "unexpected_error"
    assert "RuntimeError" in payload["summary"]
    assert "the connection is not set up" in payload["summary"]
    assert "boom" not in result.output
    assert_no_sentinel(result.output)


def test_crash_before_any_write_still_goes_to_the_generic_handler(
    repo: Path, client_file: Path, google: Any
) -> None:
    google(raises=RuntimeError(f"boom {REFRESH}"))

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["state"] == "unexpected_error"
    assert "Nothing was stored" not in payload["summary"]
    assert_no_sentinel(result.output)


def test_user_scope_metadata_failure_points_at_commands_that_work(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    google()

    def broken_write_config(target: Path, config: dict[str, Any]) -> Path:
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(connect_mod, "_write_config", broken_write_config)
        failed = _oauth(repo, *_signin_args(client_file), "--scope", "user", "--json")

    assert failed.exit_code == 1
    summary = json.loads(failed.stdout)["summary"]
    assert "recorded in user scope" in summary
    assert f"mb connect hydrate --repo {repo}" in summary
    assert "mb connect google --oauth --reauth" in summary
    assert "Re-run `mb connect google --oauth`" not in summary
    assert_no_sentinel(failed.output)

    # Both named commands work: hydrate records it here without a sign-in ...
    hydrated = runner.invoke(app, ["connect", "hydrate", "--repo", str(repo), "--json"])
    assert hydrated.exit_code == 0, hydrated.output
    assert _google_entry(repo)["secrets"]["oauth_grant"]["ref"]
    # ... and --reauth does not refuse with oauth_use_reauth.
    google(refresh=REFRESH_2)
    renewed = _oauth(repo, "--reauth", "--json")
    assert renewed.exit_code == 0, renewed.output


def test_user_scope_metadata_failure_reauth_without_hydrate(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    google()

    def broken_write_config(target: Path, config: dict[str, Any]) -> Path:
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(connect_mod, "_write_config", broken_write_config)
        assert _oauth(repo, *_signin_args(client_file), "--scope", "user").exit_code == 1

    refused = _oauth(repo, *_signin_args(client_file))
    assert refused.exit_code == 2
    assert "--reauth" in refused.output
    google(refresh=REFRESH_2)
    assert _oauth(repo, "--reauth").exit_code == 0


# --- Leaks -------------------------------------------------------------------


def test_no_grant_or_minted_token_leaks(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _signed_in(repo, client_file, google)
    _mint_with(monkeypatch)
    report_path = tmp_path / "child.json"

    token = _token(repo)
    executed = _exec(repo, report_path)
    read = connect_mod.read_token("google", repo)
    outputs = [executed]
    for args in (
        ["connect", "status", "google", "--json"],
        ["connect", "status", "google"],
        ["connect", "status", "--json"],
        ["connect", "list", "--json"],
        ["connect", "doctor", "--json"],
        ["connect", "identity", "--json"],
        ["connect", "hygiene", "--json"],
    ):
        outputs.append(runner.invoke(app, [*args, "--repo", str(repo)]))

    # The token command's stdout is the minted token and nothing else.
    assert token.stdout == MINTED
    for sentinel in (*SENTINELS, *GRANT_SENTINELS, MINTED):
        assert sentinel not in token.stderr
        for result in outputs:
            assert sentinel not in result.output
    # The read result carries the minted token only, never the grant.
    for sentinel in GRANT_SENTINELS:
        assert sentinel not in repr(read) + json.dumps(read)
    # The child saw the minted token in one variable and nothing of the grant.
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["names_holding_minted"] == ["GOOGLE_OAUTH_TOKEN"]
    assert report["names_holding_grant"] == []
    assert report["argv_leak"] is False
    # Process state and repo files hold no token or grant.
    assert MINTED not in repr(gc._minted)
    for path in repo.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            for sentinel in (*SENTINELS, MINTED):
                assert sentinel not in text
    user_scope = connect_mod._user_scope_path()
    if user_scope.exists():
        assert MINTED not in user_scope.read_text(encoding="utf-8")
    assert MINTED not in json.dumps(_local_secrets())


def test_failing_reads_leak_nothing_in_json_errors(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signed_in(repo, client_file, google)
    _mint_with(
        monkeypatch,
        status=400,
        payload={"error": "invalid_grant", "error_description": f"{REFRESH} {DESCRIPTION}"},
    )
    connect_mod.read_token("google", repo)

    for args in (
        ["connect", "status", "google", "--json"],
        ["connect", "doctor", "--json"],
        ["connect", "token", "google", "--json"],
    ):
        result = runner.invoke(app, [*args, "--repo", str(repo)])
        for sentinel in GRANT_SENTINELS:
            assert sentinel not in result.output
    for path in repo.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            for sentinel in GRANT_SENTINELS:
                assert sentinel not in text
