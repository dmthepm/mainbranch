"""Tests for `mb connect google --oauth` (mb.google_connect and its CLI wiring).

No network: an autouse guard fails any lookup or connection that is not
127.0.0.1. The browser is an injected opener that sends Google's redirect
through the real loopback receiver; the token endpoint is a stub sender. The
credential store is the local-file backend under a temporary MAINBRANCH_HOME.
Every secret is a synthetic sentinel so leak checks can search for it.
"""

from __future__ import annotations

import errno
import http.client
import io
import json
import socket
import threading
import urllib.parse
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from mb import connect as connect_mod
from mb import credential_store as credential_store_mod
from mb import google_connect as gc
from mb import google_oauth as go
from mb.cli import app

runner = CliRunner()

CLIENT_ID = "0000-synthetic.apps.example.invalid"
CLIENT_SECRET = "SYNTH-CLIENT-SECRET-0001"
REFRESH = "SYNTH-REFRESH-0001"
REFRESH_2 = "SYNTH-REFRESH-0002"
ACCESS = "SYNTH-ACCESS-0001"
MINTED = "SYNTH-MINTED-0001"
CODE = "SYNTH-CODE-0001"
VERIFIER = "SYNTH-VERIFIER-0001-" + "v" * 40
LEGACY_TOKEN = "SYNTH-LEGACY-ACCESS-0001"
SENTINELS = (CLIENT_SECRET, REFRESH, REFRESH_2, ACCESS, CODE, VERIFIER)
BOTH_SCOPES = " ".join(go.SCOPES)

_REAL_GETADDRINFO = socket.getaddrinfo
_REAL_CREATE_CONNECTION = socket.create_connection


@pytest.fixture(autouse=True)
def loopback_only_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host not in {"127.0.0.1", b"127.0.0.1"}:
            raise OSError("network blocked in tests")
        return _REAL_GETADDRINFO(host, *args, **kwargs)

    def guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> Any:
        if address[0] != "127.0.0.1":
            raise OSError("network blocked in tests")
        return _REAL_CREATE_CONNECTION(address, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)


@pytest.fixture(autouse=True)
def google_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Minted tokens live for the process; each test starts without any.
    gc.forget_minted()
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    for provider in connect_mod.PROVIDERS:
        for env_var in provider.env_vars:
            monkeypatch.delenv(env_var, raising=False)
    # A fixed sentinel verifier, so leak checks can look for it.
    monkeypatch.setattr(go, "new_code_verifier", lambda: VERIFIER)
    yield
    gc.forget_minted()


def assert_no_sentinel(text: str) -> None:
    for sentinel in SENTINELS:
        assert sentinel not in text


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "biz"
    path.mkdir()
    return path


@pytest.fixture()
def client_file(tmp_path: Path) -> Path:
    path = tmp_path / "client_secret_synthetic.json"
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
        ),
        encoding="utf-8",
    )
    return path


# --- Fake browser and token endpoint -----------------------------------------


def _loopback_get(redirect_uri: str, path: str) -> int:
    parsed = urllib.parse.urlsplit(redirect_uri)
    conn = http.client.HTTPConnection("127.0.0.1", parsed.port, timeout=5)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        assert_no_sentinel(response.read().decode("utf-8"))
        return int(response.status)
    finally:
        conn.close()


class Browser:
    """An opener that plays the person in the browser.

    ``mode`` picks what Google sends back to the loopback redirect. The
    redirect runs in a thread, as a real browser would, after the opener
    returns and the receiver starts waiting.
    """

    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.urls: list[str] = []
        self.statuses: list[int] = []
        self.threads: list[threading.Thread] = []

    def params(self) -> dict[str, str]:
        query = urllib.parse.urlsplit(self.urls[-1]).query
        return {key: values[0] for key, values in urllib.parse.parse_qs(query).items()}

    def __call__(self, url: str) -> bool:
        self.urls.append(url)
        params = self.params()
        redirect_uri, state = params["redirect_uri"], params["state"]
        paths: list[str] = []
        if self.mode == "wrong_path_first":
            paths.append(f"/favicon.ico?{urllib.parse.urlencode({'state': state, 'code': CODE})}")
        if self.mode in {"ok", "wrong_path_first"}:
            paths.append(f"/?{urllib.parse.urlencode({'state': state, 'code': CODE})}")
        elif self.mode == "wrong_state":
            paths.append(f"/?{urllib.parse.urlencode({'state': 'forged', 'code': CODE})}")
        elif self.mode == "denied":
            paths.append(f"/?{urllib.parse.urlencode({'state': state, 'error': 'access_denied'})}")

        def run() -> None:
            for path in paths:
                self.statuses.append(_loopback_get(redirect_uri, path))

        thread = threading.Thread(target=run)
        self.threads.append(thread)
        thread.start()
        return True

    def join(self) -> None:
        for thread in self.threads:
            thread.join(timeout=10)


class TokenEndpoint:
    """Stub for https://oauth2.googleapis.com/token that checks PKCE."""

    def __init__(
        self,
        browser: Browser | None = None,
        *,
        scope: str = BOTH_SCOPES,
        refresh: str | None = REFRESH,
        status: int = 200,
        raises: BaseException | None = None,
    ) -> None:
        self.browser = browser
        self.scope = scope
        self.refresh = refresh
        self.status = status
        self.raises = raises
        self.calls: list[dict[str, list[str]]] = []

    def __call__(
        self, url: str, body: bytes, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, bytes]:
        assert url == go.TOKEN_ENDPOINT
        fields = urllib.parse.parse_qs(body.decode("ascii"))
        self.calls.append(fields)
        if self.raises is not None:
            raise self.raises
        if fields["grant_type"] == ["refresh_token"]:
            # Read-time minting (`mb connect token`/`exec`): a fresh access token.
            minted = {"access_token": MINTED, "expires_in": 3599, "token_type": "Bearer"}
            return 200, json.dumps(minted).encode("utf-8")
        if self.browser is not None and self.browser.urls:
            challenge = self.browser.params()["code_challenge"]
            assert go.code_challenge(fields["code_verifier"][0]) == challenge
        payload: dict[str, Any] = {
            "access_token": ACCESS,
            "expires_in": 3599,
            "scope": self.scope,
            "token_type": "Bearer",
        }
        if self.refresh:
            payload["refresh_token"] = self.refresh
            payload["refresh_token_expires_in"] = 604799
        return self.status, json.dumps(payload).encode("utf-8")


@pytest.fixture()
def google(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[..., tuple[Browser, TokenEndpoint]]]:
    """Install a fake browser and token endpoint for CLI runs."""

    browsers: list[Browser] = []

    def install(mode: str = "ok", **endpoint: Any) -> tuple[Browser, TokenEndpoint]:
        browser = Browser(mode)
        browsers.append(browser)
        sender = TokenEndpoint(browser, **endpoint)
        monkeypatch.setattr(gc, "open_browser", browser)
        monkeypatch.setattr(gc, "token_sender", sender)
        return browser, sender

    yield install
    for browser in browsers:
        browser.join()


def _oauth(repo: Path, *args: str, input: str | None = None) -> Any:
    return runner.invoke(
        app, ["connect", "google", "--oauth", "--repo", str(repo), *args], input=input
    )


def _signin_args(client_file: Path) -> list[str]:
    return [
        "--client-file",
        str(client_file),
        "--metadata",
        "search_console_site=sc-domain:Example.com",
        "--metadata",
        "ga4_property_id=properties/123456789",
    ]


def _config(repo: Path) -> dict[str, Any]:
    path = repo / ".mb" / "connect.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _google_entry(repo: Path) -> dict[str, Any]:
    return dict((_config(repo).get("providers") or {}).get("google") or {})


def _local_secrets() -> dict[str, str]:
    return credential_store_mod._read_local_secrets()


def _stored_grant(repo: Path) -> dict[str, Any]:
    ref = _google_entry(repo)["secrets"]["oauth_grant"]["ref"]
    return dict(json.loads(_local_secrets()[ref]))


def _connect_legacy_token(repo: Path) -> None:
    connect_mod.connect_provider("google", repo=repo, token=LEGACY_TOKEN)


# --- Success -----------------------------------------------------------------


def test_oauth_bootstrap_success_stores_grant_then_reads_as_oauth(
    repo: Path, client_file: Path, google: Any
) -> None:
    browser, endpoint = google()

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["credential_mode"] == "oauth"
    assert payload["oauth_grants"] == ["search_console", "ga4"]
    assert payload["missing_grants"] == []
    assert payload["provider_verified"] is False
    assert len(browser.urls) == 1
    assert browser.statuses == [200]
    # The exchange carried the code, the PKCE verifier and the client secret.
    (call,) = endpoint.calls
    assert call["grant_type"] == ["authorization_code"]
    assert call["code"] == [CODE]
    assert call["client_secret"] == [CLIENT_SECRET]
    assert call["redirect_uri"][0].startswith("http://127.0.0.1:")

    entry = _google_entry(repo)
    assert entry["metadata"] == {
        "search_console_site": "sc-domain:example.com",
        "ga4_property_id": "123456789",
        "oauth_grants": "search_console,ga4",
    }
    assert sorted(entry["secrets"]) == ["access_token", "oauth_grant"]
    assert _stored_grant(repo) == {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH,
        "refresh_token_expires_in": 604799,
    }

    status = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo), "--json"])
    item = json.loads(status.stdout)
    assert item["credential_mode"] == "oauth"
    assert item["stored"] is True
    assert item["secrets"]["oauth_grant"]["optional"] is True
    assert item["secrets"]["oauth_grant"]["presence"] == "present"
    assert item["provider_verified"] is False


def test_oauth_human_output_names_grants_and_claims_no_verification(
    repo: Path, client_file: Path, google: Any
) -> None:
    google()

    result = _oauth(repo, *_signin_args(client_file))

    assert result.exit_code == 0, result.output
    assert "Granted (read-only): Search Console, Analytics (GA4)" in result.stdout
    # The sign-in's last step is the read-only check. The network guard
    # blocks Google here, so it reports that and claims nothing.
    assert "Checked with Google (read-only): warn (unvalidated)" in result.stdout
    assert "search_console: unvalidated (search_console_unreachable)" in result.stdout
    assert "next: mb connect test google" in result.stdout
    assert "verified" not in result.stdout.lower()
    assert "Opening your browser" in result.stderr
    assert "https://accounts.google.com/o/oauth2/v2/auth?" in result.stderr


def test_oauth_wrong_path_then_real_callback_succeeds(
    repo: Path, client_file: Path, google: Any
) -> None:
    browser, _ = google("wrong_path_first")

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 0, result.output
    browser.join()
    assert browser.statuses == [404, 200]
    assert _google_entry(repo)["secrets"]["oauth_grant"]["ref"]


def test_oauth_no_browser_prints_url_and_never_opens(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser, endpoint = google()
    captured: list[str] = []

    def emit(line: str) -> None:
        captured.append(line)
        if line.strip().startswith("https://accounts.google.com/"):
            # The person opens the printed URL on another machine.
            Browser.__call__(browser, line.strip())

    result = gc.bootstrap(
        repo,
        client_json=client_file.read_text(encoding="utf-8"),
        no_browser=True,
        emit=emit,
        opener=lambda url: pytest.fail("--no-browser must not open a browser"),
        sender=endpoint,
    )
    browser.join()
    assert result["ok"] is True
    assert any(
        "Open this URL in a browser that can reach http://127.0.0.1:" in line for line in captured
    )


def test_oauth_fixed_port(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser, _ = google()
    bind_refusals: list[int] = []

    class _RecordingReceiver(go.LoopbackReceiver):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            try:
                super().__init__(*args, **kwargs)
            except OSError as exc:
                bind_refusals.append(exc.errno or 0)
                raise

    monkeypatch.setattr(go, "LoopbackReceiver", _RecordingReceiver)
    # The free port is probed, then rebound by the receiver. Another process
    # can take it in between, so only that bind refusal retries a new port.
    for _attempt in range(5):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        bind_refusals.clear()
        result = _oauth(repo, *_signin_args(client_file), "--port", str(port), "--json")
        if bind_refusals != [errno.EADDRINUSE]:
            break

    assert bind_refusals == []
    assert result.exit_code == 0, result.output
    assert browser.params()["redirect_uri"] == f"http://127.0.0.1:{port}"


class _TTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_oauth_paste_mode(repo: Path, client_file: Path) -> None:
    lines: list[str] = []
    endpoint = TokenEndpoint()

    def reader(prompt: str) -> str:
        url = next(line.strip() for line in lines if "accounts.google.com" in line)
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        query = urllib.parse.urlencode({"state": params["state"], "code": CODE})
        return f"{params['redirect_uri']}/?{query}"

    result = gc.bootstrap(
        repo,
        client_json=client_file.read_text(encoding="utf-8"),
        paste=True,
        emit=lines.append,
        opener=lambda url: pytest.fail("paste mode must not open a browser"),
        sender=endpoint,
        stdin=_TTY(),
        paste_reader=reader,
    )

    assert result["ok"] is True
    assert endpoint.calls[0]["code"] == [CODE]
    assert any("Never paste it into a chat" in line for line in lines)
    assert_no_sentinel("\n".join(lines))


def test_oauth_paste_refuses_without_terminal(repo: Path, client_file: Path, google: Any) -> None:
    browser, endpoint = google()

    result = _oauth(repo, *_signin_args(client_file), "--paste", "--json")

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["rule"] == "paste_needs_tty"
    assert browser.urls == [] and endpoint.calls == []
    assert _google_entry(repo) == {}


# --- Failures that store nothing ---------------------------------------------


@pytest.mark.parametrize(
    ("mode", "rule", "state"),
    [
        ("wrong_state", "state_mismatch", "invalid"),
        ("denied", "consent_denied", "consent_denied"),
    ],
)
def test_oauth_redirect_failures_store_nothing(
    repo: Path, client_file: Path, google: Any, mode: str, rule: str, state: str
) -> None:
    _, endpoint = google(mode)

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["rule"] == rule
    assert payload["state"] == state
    assert "Nothing was stored" in payload["summary"]
    assert endpoint.calls == []
    assert _google_entry(repo) == {}
    assert _local_secrets() == {}
    assert_no_sentinel(result.output)


def test_oauth_timeout_stores_nothing(repo: Path, client_file: Path) -> None:
    with pytest.raises(go.GoogleOAuthError) as caught:
        gc.bootstrap(
            repo,
            client_json=client_file.read_text(encoding="utf-8"),
            timeout=0.5,
            emit=lambda line: None,
            opener=lambda url: True,
            sender=TokenEndpoint(),
        )
    assert caught.value.rule == "bootstrap_timeout"
    assert caught.value.state == go.STATE_BOOTSTRAP_TIMEOUT
    assert _google_entry(repo) == {}
    assert _local_secrets() == {}


def test_oauth_without_refresh_token_stores_nothing(
    repo: Path, client_file: Path, google: Any
) -> None:
    google(refresh=None)

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["rule"] == "oauth_no_refresh_token"
    assert "Nothing was stored" in payload["summary"]
    assert _google_entry(repo) == {}
    assert _local_secrets() == {}


def test_oauth_token_endpoint_failure_stores_nothing(
    repo: Path, client_file: Path, google: Any
) -> None:
    google(status=400)

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["rule"] == "token_request_failed"
    assert _google_entry(repo) == {}
    assert _local_secrets() == {}


def test_oauth_no_scope_granted_stores_nothing(repo: Path, client_file: Path, google: Any) -> None:
    google(scope="openid")

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 1
    assert json.loads(result.stdout)["rule"] == "oauth_no_scope_granted"
    assert _google_entry(repo) == {}
    assert _local_secrets() == {}


# --- Partial grant -----------------------------------------------------------


def test_oauth_partial_grant_is_stored_and_reported(
    repo: Path, client_file: Path, google: Any
) -> None:
    google(scope=go.SCOPE_ANALYTICS)

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["oauth_grants"] == ["ga4"]
    assert payload["missing_grants"] == ["search_console"]
    assert payload["repair_command"] == "mb connect google --oauth --reauth"
    assert _google_entry(repo)["metadata"]["oauth_grants"] == "ga4"

    human = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo), "--json"])
    assert json.loads(human.stdout)["credential_mode"] == "oauth"


# --- Write order and partial failures ----------------------------------------


class FailingSet:
    """Record each credential write; fail the ``fail_on``-th one (1-based)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, fail_on: int | None) -> None:
        self.refs: list[str] = []
        self.fail_on = fail_on
        real_set = credential_store_mod.SecretStore.set

        def fake_set(store: Any, ref: str, value: str, **kwargs: Any) -> None:
            self.refs.append(ref)
            if self.fail_on is not None and len(self.refs) == self.fail_on:
                raise credential_store_mod.CredentialStoreError("keychain_locked")
            real_set(store, ref, value, **kwargs)

        monkeypatch.setattr(credential_store_mod.SecretStore, "set", fake_set)


def test_oauth_write_order_grant_then_token_then_metadata(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    google()
    writes = FailingSet(monkeypatch, None)
    order: list[str] = []
    real_write_config = connect_mod._write_config

    def recording_write_config(target: Path, config: dict[str, Any]) -> Path:
        order.extend(ref.rsplit("/", 1)[-1] for ref in writes.refs)
        order.append("metadata")
        return real_write_config(target, config)

    monkeypatch.setattr(connect_mod, "_write_config", recording_write_config)

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 0, result.output
    assert order == ["oauth_grant", "access_token", "metadata"]


def test_oauth_grant_write_failure_changes_nothing(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    google()
    FailingSet(monkeypatch, 1)

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["state"] == connect_mod.BACKEND_FAILURE_STATE
    assert payload["backend_state"] == "keychain_locked"
    assert "Nothing was stored and the repo metadata is unchanged." in payload["summary"]
    assert _google_entry(repo) == {}
    assert_no_sentinel(result.output)


def test_oauth_token_write_failure_on_first_connect_says_not_set_up(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    google()
    FailingSet(monkeypatch, 2)

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 1
    summary = json.loads(result.stdout)["summary"]
    assert "this repo does not record it, so the connection is not set up" in summary
    assert "Nothing was stored" not in summary
    assert _google_entry(repo) == {}


def test_oauth_token_write_failure_on_reauth_says_new_grant_is_stored(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    google()
    assert _oauth(repo, *_signin_args(client_file)).exit_code == 0
    google(refresh=REFRESH_2)
    FailingSet(monkeypatch, 2)

    result = _oauth(repo, "--reauth", "--json")

    assert result.exit_code == 1
    summary = json.loads(result.stdout)["summary"]
    assert "The new Google grant is stored and replaced the old one" in summary
    assert "mb connect test google" in summary
    assert "Nothing was stored" not in summary
    assert "unchanged" not in summary
    assert _stored_grant(repo)["refresh_token"] == REFRESH_2


def test_oauth_metadata_write_failure_first_connect_and_reauth(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_write_config(target: Path, config: dict[str, Any]) -> Path:
        raise OSError("disk full")

    google()
    with monkeypatch.context() as patch:
        patch.setattr(connect_mod, "_write_config", broken_write_config)
        first = _oauth(repo, *_signin_args(client_file), "--json")
    assert first.exit_code == 1
    first_summary = json.loads(first.stdout)["summary"]
    assert json.loads(first.stdout)["state"] == "metadata_write_failed"
    assert "the connection is not set up" in first_summary

    google()
    assert _oauth(repo, *_signin_args(client_file)).exit_code == 0
    google(refresh=REFRESH_2)
    monkeypatch.setattr(connect_mod, "_write_config", broken_write_config)
    again = _oauth(repo, "--reauth", "--json")
    assert again.exit_code == 1
    summary = json.loads(again.stdout)["summary"]
    assert "The new Google grant and access token are stored and replaced the old ones" in summary
    assert "Nothing was stored" not in summary
    assert_no_sentinel(first.output + again.output)


def test_oauth_replace_access_token_metadata_failure_says_token_was_replaced(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _connect_legacy_token(repo)
    google()

    def broken_write_config(target: Path, config: dict[str, Any]) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(connect_mod, "_write_config", broken_write_config)
    result = _oauth(repo, *_signin_args(client_file), "--replace-access-token", "--json")

    assert result.exit_code == 1
    summary = json.loads(result.stdout)["summary"]
    assert "previously stored Google access token was already replaced" in summary


# --- Refusals ----------------------------------------------------------------


def test_oauth_refuses_to_replace_access_token_without_flag(
    repo: Path, client_file: Path, google: Any
) -> None:
    _connect_legacy_token(repo)
    before = (repo / ".mb" / "connect.yaml").read_text(encoding="utf-8")
    browser, _ = google()

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["rule"] == "oauth_replaces_access_token"
    assert "--replace-access-token" in payload["summary"]
    assert browser.urls == []
    assert (repo / ".mb" / "connect.yaml").read_text(encoding="utf-8") == before
    assert connect_mod.read_token("google", repo)["token"] == LEGACY_TOKEN


def test_oauth_refuses_when_access_token_connected_during_sign_in(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser, _ = google()

    def connect_while_signing_in(*args: Any, **kwargs: Any) -> Any:
        _connect_legacy_token(repo)
        return browser(*args, **kwargs)

    monkeypatch.setattr(gc, "open_browser", connect_while_signing_in)

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["rule"] == "oauth_replaces_access_token"
    assert "--replace-access-token" in payload["summary"]
    assert connect_mod.status_provider("google", repo)["credential_mode"] != "oauth"
    assert connect_mod.read_token("google", repo)["token"] == LEGACY_TOKEN


def test_oauth_replace_access_token_upgrades_to_oauth(
    repo: Path, client_file: Path, google: Any
) -> None:
    _connect_legacy_token(repo)
    google()

    result = _oauth(repo, *_signin_args(client_file), "--replace-access-token", "--json")

    assert result.exit_code == 0, result.output
    assert connect_mod.status_provider("google", repo)["credential_mode"] == "oauth"
    assert connect_mod.read_token("google", repo)["token"] == MINTED


def test_oauth_again_without_reauth_refuses(repo: Path, client_file: Path, google: Any) -> None:
    google()
    assert _oauth(repo, *_signin_args(client_file)).exit_code == 0
    browser, _ = google()

    result = _oauth(repo, *_signin_args(client_file), "--json")

    assert result.exit_code == 2
    assert json.loads(result.stdout)["rule"] == "oauth_use_reauth"
    assert browser.urls == []


def test_oauth_reauth_without_grant_refuses(repo: Path, client_file: Path, google: Any) -> None:
    browser, _ = google()

    result = _oauth(repo, *_signin_args(client_file), "--reauth", "--json")

    assert result.exit_code == 2
    assert json.loads(result.stdout)["rule"] == "oauth_reauth_without_grant"
    assert browser.urls == []


def test_oauth_reauth_reuses_stored_client_and_metadata(
    repo: Path, client_file: Path, google: Any
) -> None:
    google()
    assert _oauth(repo, *_signin_args(client_file)).exit_code == 0
    _, endpoint = google(refresh=REFRESH_2)

    result = _oauth(repo, "--reauth", "--json")

    assert result.exit_code == 0, result.output
    assert endpoint.calls[0]["client_id"] == [CLIENT_ID]
    assert endpoint.calls[0]["client_secret"] == [CLIENT_SECRET]
    assert _stored_grant(repo)["refresh_token"] == REFRESH_2
    assert _google_entry(repo)["metadata"]["search_console_site"] == "sc-domain:example.com"


def test_oauth_needs_a_client(repo: Path, google: Any) -> None:
    browser, _ = google()

    result = _oauth(repo, "--json")

    assert result.exit_code == 2
    assert json.loads(result.stdout)["rule"] == "oauth_client_required"
    assert browser.urls == []


def test_oauth_reads_client_from_stdin(repo: Path, client_file: Path, google: Any) -> None:
    google()

    result = _oauth(repo, "--client-stdin", "--json", input=client_file.read_text(encoding="utf-8"))

    assert result.exit_code == 0, result.output
    assert _stored_grant(repo)["client_id"] == CLIENT_ID


@pytest.mark.parametrize(
    ("body", "rule"),
    [
        ("not json", "oauth_client_malformed"),
        (json.dumps({"installed": {"client_secret": CLIENT_SECRET}}), "oauth_client_malformed"),
        (json.dumps({"installed": {"client_id": "bad id with spaces"}}), "oauth_client_malformed"),
        (json.dumps({"web": {"client_id": CLIENT_ID}}), "oauth_client_not_desktop"),
        ("x" * (gc.CLIENT_JSON_MAX_BYTES + 10), "oauth_client_malformed"),
    ],
)
def test_oauth_refuses_bad_client_json(
    repo: Path, tmp_path: Path, google: Any, body: str, rule: str
) -> None:
    browser, _ = google()
    bad = tmp_path / "client.json"
    bad.write_text(body, encoding="utf-8")

    result = _oauth(repo, "--client-file", str(bad), "--json")

    assert result.exit_code == 2
    assert json.loads(result.stdout)["rule"] == rule
    assert browser.urls == []
    assert_no_sentinel(result.output)


def test_oauth_refuses_unreadable_client_file(repo: Path, tmp_path: Path, google: Any) -> None:
    google()
    result = _oauth(repo, "--client-file", str(tmp_path / "missing.json"), "--json")
    assert result.exit_code == 2
    assert json.loads(result.stdout)["rule"] == "oauth_client_unreadable"


@pytest.mark.parametrize(
    ("pair", "rule"),
    [
        ("search_console_site=example.com", "search_console_site_format"),
        ("search_console_site=https://www.example.com", "search_console_site_format"),
        ("search_console_site=https://www.example.com/?q=1/", "search_console_site_format"),
        ("search_console_site=ftp://example.com/", "search_console_site_format"),
        ("search_console_site=sc-domain:localhost", "search_console_site_format"),
        ("ga4_property_id=G-ABC123", "ga4_property_id_format"),
        ("ga4_property_id=properties/", "ga4_property_id_format"),
        ("oauth_grants=search_console", "oauth_metadata_reserved"),
    ],
)
def test_oauth_refuses_bad_metadata(
    repo: Path, client_file: Path, google: Any, pair: str, rule: str
) -> None:
    browser, _ = google()

    result = _oauth(repo, "--client-file", str(client_file), "--metadata", pair, "--json")

    assert result.exit_code == 2
    assert json.loads(result.stdout)["rule"] == rule
    assert browser.urls == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("sc-domain:Example.COM", "sc-domain:example.com"),
        ("https://www.example.com/", "https://www.example.com/"),
        ("http://example.com/blog/", "http://example.com/blog/"),
    ],
)
def test_search_console_site_forms(value: str, expected: str) -> None:
    assert gc.normalize_search_console_site(value) == expected


@pytest.mark.parametrize(("value", "expected"), [("123", "123"), ("properties/987", "987")])
def test_ga4_property_forms(value: str, expected: str) -> None:
    assert gc.normalize_ga4_property_id(value) == expected


def test_token_reconnect_on_oauth_entry_refuses(repo: Path, client_file: Path, google: Any) -> None:
    google()
    assert _oauth(repo, *_signin_args(client_file)).exit_code == 0
    before = _google_entry(repo)

    piped = runner.invoke(
        app,
        ["connect", "google", "--token-stdin", "--repo", str(repo), "--json"],
        input=LEGACY_TOKEN,
    )
    flagged = runner.invoke(
        app, ["connect", "google", "--token", LEGACY_TOKEN, "--repo", str(repo), "--json"]
    )

    for result in (piped, flagged):
        assert result.exit_code == 2
        assert json.loads(result.stdout)["rule"] == "oauth_connection_exists"
        assert LEGACY_TOKEN not in result.output
    assert _google_entry(repo)["secrets"] == before["secrets"]
    assert _stored_grant(repo)["refresh_token"] == REFRESH


def test_tokenless_reconnect_keeps_oauth_grants(repo: Path, client_file: Path, google: Any) -> None:
    google(scope=go.SCOPE_ANALYTICS)
    _oauth(repo, *_signin_args(client_file))

    result = runner.invoke(
        app,
        [
            "connect",
            "google",
            "--repo",
            str(repo),
            "--metadata",
            "account_email=ops@example.com",
            "--metadata",
            "oauth_grants=search_console,ga4",
            "--json",
        ],
        input="",
    )

    assert result.exit_code == 0, result.output
    entry = _google_entry(repo)
    # The edit adds the key it was given and keeps the recorded ones.
    assert entry["metadata"] == {
        "search_console_site": "sc-domain:example.com",
        "ga4_property_id": "123456789",
        "account_email": "ops@example.com",
        "oauth_grants": "ga4",
    }
    assert sorted(entry["secrets"]) == ["access_token", "oauth_grant"]


def test_token_reconnect_on_user_scope_oauth_entry_refuses(
    repo: Path, client_file: Path, google: Any
) -> None:
    google()
    assert _oauth(repo, *_signin_args(client_file), "--scope", "user").exit_code == 0
    config = _config(repo)
    del config["providers"]["google"]
    (repo / ".mb" / "connect.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(connect_mod.ConnectRefusal) as caught:
        connect_mod.connect_provider("google", repo=repo, token=LEGACY_TOKEN)
    assert caught.value.rule == "oauth_connection_exists"


def test_rotate_on_oauth_entry_refuses(repo: Path, client_file: Path, google: Any) -> None:
    google()
    assert _oauth(repo, *_signin_args(client_file)).exit_code == 0

    result = runner.invoke(app, ["connect", "rotate", "google", "--repo", str(repo), "--json"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["rule"] == "rotate_oauth_use_reauth"
    assert "--oauth --reauth" in payload["summary"]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["connect", "google", "--paste"], "--paste needs --oauth"),
        (["connect", "google", "--client-file", "x.json"], "--client-file needs --oauth"),
        (["connect", "google", "--replace-access-token"], "--replace-access-token needs --oauth"),
        (["connect", "stripe", "--oauth"], "--oauth is only for `mb connect google`"),
        (
            ["connect", "google", "--oauth", "--token-stdin"],
            "cannot be combined with --token-stdin",
        ),
        (
            ["connect", "google", "--oauth", "--client-file", "a", "--client-stdin"],
            "choose one of --client-file and --client-stdin",
        ),
        (
            ["connect", "google", "--oauth", "--paste", "--client-stdin"],
            "pass the client with --client-file",
        ),
    ],
)
def test_oauth_usage_errors(repo: Path, args: list[str], message: str) -> None:
    result = runner.invoke(app, [*args, "--repo", str(repo)])
    assert result.exit_code == 2
    assert message in result.stderr


def test_bare_connect_google_never_opens_a_browser(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gc, "open_browser", lambda url: pytest.fail("browser opened"))

    result = runner.invoke(app, ["connect", "google", "--repo", str(repo), "--json"])

    assert result.exit_code in {0, 1}
    assert "accounts.google.com" not in result.output


# --- Legacy connections ------------------------------------------------------


def test_legacy_access_token_google_is_unchanged(repo: Path) -> None:
    _connect_legacy_token(repo)
    item = connect_mod.status_provider("google", repo)
    assert item["credential_mode"] == "access_token"
    assert sorted(item["secrets"]) == ["access_token"]
    # A token reconnect and a rotate refusal for other reasons work as before.
    connect_mod.connect_provider("google", repo=repo, token=LEGACY_TOKEN + "-2")
    assert connect_mod.read_token("google", repo)["token"] == LEGACY_TOKEN + "-2"
    with pytest.raises(connect_mod.ConnectRefusal) as caught:
        connect_mod.rotate_provider("google", repo)
    assert caught.value.rule == "rotate_no_source"


# --- No secret leaves the process --------------------------------------------


def test_crash_and_ctrl_c_print_no_secret(repo: Path, client_file: Path, google: Any) -> None:
    google(raises=RuntimeError(f"boom {REFRESH} {CODE} {CLIENT_SECRET} {VERIFIER}"))
    crashed = _oauth(repo, *_signin_args(client_file), "--json")
    assert crashed.exit_code == 1
    assert json.loads(crashed.stdout)["state"] == "unexpected_error"
    assert_no_sentinel(crashed.output)

    google(raises=KeyboardInterrupt())
    cancelled = _oauth(repo, *_signin_args(client_file), "--json")
    assert cancelled.exit_code == 130
    assert json.loads(cancelled.stdout)["state"] == "cancelled"
    assert_no_sentinel(cancelled.output)
    assert _google_entry(repo) == {}


def test_no_secret_in_output_json_files_or_repr(
    repo: Path, client_file: Path, google: Any, tmp_path: Path
) -> None:
    google()
    outputs = [
        _oauth(repo, *_signin_args(client_file), "--json"),
    ]
    google(refresh=REFRESH_2)
    outputs.append(_oauth(repo, "--reauth"))
    for args in (
        ["connect", "status", "google", "--json"],
        ["connect", "status", "--json"],
        ["connect", "list", "--json"],
        ["connect", "doctor", "--json"],
        ["connect", "identity", "--json"],
        ["connect", "hygiene", "--json"],
    ):
        outputs.append(runner.invoke(app, [*args, "--repo", str(repo)]))
    for result in outputs:
        assert_no_sentinel(result.stdout)
        assert_no_sentinel(result.stderr)

    for path in repo.rglob("*"):
        if path.is_file():
            assert_no_sentinel(path.read_text(encoding="utf-8", errors="replace"))
    user_scope = connect_mod._user_scope_path()
    if user_scope.exists():
        assert_no_sentinel(user_scope.read_text(encoding="utf-8"))

    client = gc.parse_client_json(client_file.read_text(encoding="utf-8"))
    assert_no_sentinel(repr(client))
    tokens = go.TokenResponse({"access_token": ACCESS, "refresh_token": REFRESH})
    assert_no_sentinel(repr(tokens) + str(tokens))
    other = tmp_path / "other"
    other.mkdir()
    browser = Browser()
    result = gc.bootstrap(
        other,
        client_json=client_file.read_text(encoding="utf-8"),
        emit=assert_no_sentinel,
        opener=browser,
        sender=TokenEndpoint(browser),
    )
    browser.join()
    assert_no_sentinel(repr(result) + json.dumps(result))
