"""Hardening follow-ups for the Google sign-in and reads (#1004).

Unsetting a recorded id, a tracked `.mb/connect.yaml`, per-product status
lines, `--timeout`/`--scope`/backend refusals, sign-in token-endpoint
wording, sentinel leaks on the sign-in paths, the crash label, the inspect
link, a non-object inspect result, IDN hosts, GA4 names with a newline and
the one no-redirect opener. No network: the token endpoint and the APIs are
stub senders behind the existing seams, as in test_google_probe.
"""

# The fixtures are imported from test_google_connect, so test parameters
# share their names by design.
# ruff: noqa: F811

from __future__ import annotations

import json
import re
import subprocess
import threading
import urllib.parse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from mb import connect as connect_mod
from mb import google_connect as gc
from mb import google_oauth as go
from mb import google_reads as gr
from mb import http_safe
from mb.cli import app
from tests.connect_binding import rebind_folder
from tests.test_google_connect import (  # noqa: F401 (fixtures are used by name)
    ACCESS,
    BOTH_SCOPES,
    REFRESH,
    Browser,
    TokenEndpoint,
    _google_entry,
    _local_secrets,
    _loopback_get,
    _oauth,
    client_file,
    google,
    google_env,
    loopback_only_network,
    repo,
    runner,
)
from tests.test_google_probe import (  # noqa: F401 (fixtures are used by name)
    CODE_SENTINEL,
    PROPERTY,
    SITE,
    _api,
    _assert_never_shown,
    _mint,
    _sign_in,
    _status,
    _test,
    _test_json,
    _yaml,
    fixed_day,
)
from tests.test_google_reads import _json, _signed_in

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
PAGE = "https://www.example.com/shoes/"
INSPECT_ARGS = ["google", "sc", "inspect", "--url", PAGE]


def _plain(text: str) -> str:
    return ANSI_RE.sub("", text)


def _edit(repo: Path, *pairs: str) -> Any:
    args = ["connect", "google", "--repo", str(repo)]
    for pair in pairs:
        args += ["--metadata", pair]
    return runner.invoke(app, args)


def _metadata(repo: Path) -> dict[str, Any]:
    return dict(_google_entry(repo).get("metadata") or {})


# --- 1. Removing a recorded site or property id ------------------------------------------


def test_an_empty_value_removes_the_recorded_site_and_keeps_the_rest(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    assert _metadata(repo)["search_console_site"] == SITE

    edit = _edit(repo, "search_console_site=")

    assert edit.exit_code == 0, edit.output
    metadata = _metadata(repo)
    assert "search_console_site" not in metadata
    assert metadata["ga4_property_id"] == PROPERTY
    assert metadata["oauth_grants"] == "search_console,ga4"
    assert gc.entry_is_oauth(_google_entry(repo))
    # The read refuses before any token is minted.
    code, payload, _ = _json(
        repo, ["google", "sc", "query", "--start", "2026-09-01", "--end", "2026-09-02"]
    )
    assert code == 2
    assert payload["rule"] == "site_not_recorded"


def test_an_empty_value_removes_the_recorded_property(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)

    assert _edit(repo, "ga4_property_id=").exit_code == 0

    metadata = _metadata(repo)
    assert "ga4_property_id" not in metadata
    assert metadata["search_console_site"] == SITE
    code, payload, _ = _json(
        repo,
        [
            "google",
            "ga4",
            "report",
            "--metrics",
            "activeUsers",
            "--start",
            "2026-09-01",
            "--end",
            "2026-09-02",
        ],
    )
    assert code == 2
    assert payload["rule"] == "property_not_recorded"
    # The check names the missing id instead of failing the other product.
    _mint(monkeypatch)
    _api(monkeypatch)
    _, result = _test_json(repo)
    assert result["products"]["ga4"]["rule"] == "ga4_property_not_recorded"
    assert result["products"]["search_console"]["state"] == "ok"


# --- 2. A tracked .mb/connect.yaml ---------------------------------------------------------


def _track_config(repo: Path) -> None:
    for args in (["init", "-q"], ["add", "-f", ".mb/connect.yaml"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    # `git init` changes the folder's identity, so the owner rebinds it.
    rebind_folder(repo)


def _git_status(repo: Path) -> str:
    """Unstaged changes to the tracked file: empty when nothing touched it."""

    return subprocess.run(
        ["git", "diff", "--name-only", "--", ".mb/connect.yaml"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_a_read_never_writes_reauth_required_into_a_tracked_config(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _track_config(repo)
    before = _yaml(repo)
    _mint(monkeypatch, status=400, payload={"error": "invalid_grant"})

    token = runner.invoke(app, ["connect", "token", "google", "--repo", str(repo), "--print"])

    assert token.exit_code == 1
    # The read itself still says what is wrong and how to fix it.
    assert "reauth_required" in token.output
    assert "mb connect google --oauth --reauth" in token.output
    assert _yaml(repo) == before
    assert _git_status(repo) == ""


def test_a_check_is_not_recorded_into_a_tracked_config(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _track_config(repo)
    before = _yaml(repo)
    _mint(monkeypatch)
    _api(monkeypatch, ga4=(403, {"error": {"code": 403, "status": "PERMISSION_DENIED"}}))

    code, result = _test_json(repo)
    human = _test(repo)

    assert code == 1
    assert result["products"]["ga4"]["rule"] == "ga4_no_access"
    assert result["recorded"] is False
    assert result["not_recorded_reason"] == "connect_yaml_tracked"
    assert "recorded: no (.mb/connect.yaml is tracked by git" in _plain(human.output)
    assert _yaml(repo) == before
    assert _git_status(repo) == ""


def test_an_untracked_config_still_records_the_check(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    rebind_folder(repo)
    _mint(monkeypatch, status=400, payload={"error": "invalid_grant"})

    _, result = _test_json(repo)

    assert result["recorded"] is True
    assert result["not_recorded_reason"] == ""
    assert _status(repo)[1]["state"] == "reauth_required"


def test_the_sign_in_itself_records_into_a_tracked_config(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A person running the sign-in asked for the write; its check lands too."""

    _sign_in(repo, client_file, google, monkeypatch)
    _track_config(repo)
    _edit(repo, "search_console_site=")
    google()
    _api(monkeypatch)

    result = _oauth(repo, "--reauth", "--json")

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["check"]["recorded"] is True
    assert "connect_yaml_tracked" not in _yaml(repo)


# --- 3. Per-product lines in human status ------------------------------------------------


def test_status_shows_one_line_per_product(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _mint(monkeypatch)
    _api(monkeypatch, ga4=(403, {"error": {"code": 403, "status": "PERMISSION_DENIED"}}))
    _test_json(repo)

    human = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo)])
    code, payload = _status(repo)

    lines = _plain(human.stdout).splitlines()
    assert "  search_console: granted, last check: ok" in lines
    assert "  ga4: granted, last check: invalid (ga4_no_access)" in lines
    assert code == 1
    # JSON keys are additive only.
    assert payload["oauth"]["grants"] == ["search_console", "ga4"]
    assert payload["validation"]["products"] == {
        "search_console": {"state": "ok", "rule": "ok"},
        "ga4": {"state": "invalid", "rule": "ga4_no_access"},
    }
    assert "refresh_token_expires_on" in payload["oauth"]


def test_status_says_not_granted_and_not_checked(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch, scope=go.SCOPE_SEARCH_CONSOLE)
    # A metadata edit clears the recorded check.
    _edit(repo, f"search_console_site={SITE}")

    human = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo)])

    lines = _plain(human.stdout).splitlines()
    assert "  search_console: granted, last check: not checked yet" in lines
    assert "  ga4: not granted" in lines


def test_status_product_lines_ignore_a_hand_edited_rule(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    config = connect_mod._read_config(repo)
    config["providers"]["google"]["validation"]["products"] = {
        "search_console": {"state": "invalid", "rule": "x\x1b[31m " + REFRESH},
        "ga4": {"state": "pwned", "rule": "ok"},
        "drive": {"state": "ok", "rule": "ok"},
    }
    connect_mod._write_config(repo, config)

    human = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo)])
    _, payload = _status(repo)

    assert payload["validation"]["products"] == {"search_console": {"state": "invalid", "rule": ""}}
    assert "  search_console: granted, last check: invalid (no rule)" in human.stdout
    assert "  ga4: granted, last check: not checked yet" in human.stdout
    assert REFRESH not in human.output + json.dumps(payload)
    assert "drive" not in human.stdout


def test_a_plain_access_token_status_has_no_product_lines(repo: Path) -> None:
    connected = runner.invoke(
        app,
        ["connect", "google", "--repo", str(repo), "--token-stdin"],
        input="SYNTH-LEGACY-0009\n",
    )
    assert connected.exit_code == 0, connected.output

    human = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo)])

    assert "search_console:" not in human.stdout
    assert "ga4:" not in human.stdout


# --- 4 and 5. Options that would be ignored ----------------------------------------------


@pytest.mark.parametrize("value", ["300", "60"])
def test_timeout_without_oauth_is_refused(repo: Path, value: str) -> None:
    result = runner.invoke(
        app, ["connect", "status", "google", "--repo", str(repo), "--timeout", value, "--json"]
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["rule"] == "oauth_option_without_oauth"
    assert "--timeout needs --oauth" in payload["summary"]


def test_timeout_help_names_its_default() -> None:
    result = runner.invoke(app, ["connect", "--help"], env={"FORCE_COLOR": "1", "COLUMNS": "200"})

    assert result.exit_code == 0
    assert "seconds to wait for the browser sign-in (default 300)" in _plain(result.output)


def test_an_explicit_scope_on_an_existing_sign_in_is_refused(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    before = _yaml(repo)
    browser, endpoint = google()

    result = _oauth(repo, "--reauth", "--scope", "user", "--json")

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["rule"] == "oauth_scope_kept"
    assert "recorded in repo scope" in payload["summary"]
    assert browser.urls == [] and endpoint.calls == []
    assert _yaml(repo) == before


def test_the_recorded_scope_given_again_is_fine(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    google()
    _api(monkeypatch)

    result = _oauth(repo, "--reauth", "--scope", "repo", "--json")

    assert result.exit_code == 0, result.output


def test_another_backend_on_an_existing_sign_in_is_refused(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    before = _yaml(repo)
    browser, endpoint = google()
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "secret-service")

    result = _oauth(repo, "--reauth", "--json")

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["rule"] == "oauth_backend_kept"
    assert "stored in local-file" in payload["summary"]
    assert browser.urls == [] and endpoint.calls == []
    assert _yaml(repo) == before


# --- 6 and 7. The sign-in's token exchange: wording and sentinels ------------------------


class RefusingExchange(TokenEndpoint):
    """The token endpoint refusing the sign-in's code exchange with ``error``."""

    def __init__(self, browser: Browser, error: str, status: int = 400) -> None:
        super().__init__(browser)
        self.error = error
        self.refuse_status = status

    def __call__(
        self, url: str, body: bytes, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, bytes]:
        self.calls.append(urllib.parse.parse_qs(body.decode("ascii")))
        payload = {"error": self.error, "error_description": REFRESH + " " + CODE_SENTINEL}
        return self.refuse_status, json.dumps(payload).encode("utf-8")


def _refusing(monkeypatch: pytest.MonkeyPatch, error: str, status: int = 400) -> RefusingExchange:
    browser = Browser("ok")
    endpoint = RefusingExchange(browser, error, status)
    monkeypatch.setattr(gc, "open_browser", browser)
    monkeypatch.setattr(gc, "token_sender", endpoint)
    return endpoint


EXCHANGE_REFUSALS = {
    "invalid_client": ("oauth_client_rejected", "refused the OAuth client (invalid_client)"),
    "unauthorized_client": ("oauth_client_unauthorized", "Desktop app client"),
    "invalid_scope": ("oauth_scope_rejected", "read-only Search Console and Analytics scopes"),
    "invalid_grant": ("authorization_code_rejected", "refused the authorization code"),
    "invalid_request": ("token_request_failed", "token endpoint refused the request"),
}


@pytest.mark.parametrize("error", sorted(EXCHANGE_REFUSALS))
def test_sign_in_exchange_refusals_are_worded_by_class(
    error: str, repo: Path, client_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _refusing(monkeypatch, error)

    result = _oauth(repo, "--client-file", str(client_file), "--json")

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    rule, words = EXCHANGE_REFUSALS[error]
    assert payload["rule"] == rule
    assert words in payload["summary"]
    assert payload["summary"].endswith("Nothing was stored.")
    # A first sign-in is never told to `--reauth` (it would refuse).
    assert "--reauth" not in payload["repair"] + payload["repair_command"]
    assert payload["state"] == "invalid"
    assert _google_entry(repo) == {}
    assert _local_secrets() == {}


def test_a_transient_exchange_refusal_keeps_the_generic_rule(
    repo: Path, client_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _refusing(monkeypatch, "invalid_client", status=503)

    payload = json.loads(_oauth(repo, "--client-file", str(client_file), "--json").stdout)

    assert payload["rule"] == "token_request_failed"
    assert payload["state"] == "unvalidated"


def test_refresh_rules_are_unchanged() -> None:
    def sender(
        url: str, body: bytes, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, bytes]:
        return 401, b'{"error": "invalid_client"}'

    with pytest.raises(go.GoogleOAuthError) as caught:
        go.refresh_access_token(
            client_id="c", client_secret=None, refresh_token=REFRESH, sender=sender
        )
    assert caught.value.rule == "token_request_failed"
    assert caught.value.upstream["error_code"] == "invalid_client"


def test_a_sentinel_error_code_from_the_exchange_never_leaks(
    repo: Path, client_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = []
    for args in (["--json"], []):
        _refusing(monkeypatch, CODE_SENTINEL)
        result = _oauth(repo, "--client-file", str(client_file), *args)
        assert result.exit_code == 1
        outputs.append(result.output)
    outputs.append(json.dumps(_local_secrets()))
    outputs += [path.read_text() for path in repo.rglob("*") if path.is_file()]
    for text in outputs:
        assert CODE_SENTINEL not in text
        assert REFRESH not in text


class ErrorBrowser(Browser):
    """Google redirecting back with an OAuth ``error`` instead of a code."""

    def __call__(self, url: str) -> bool:
        self.urls.append(url)
        params = self.params()
        path = "/?" + urllib.parse.urlencode({"state": params["state"], "error": CODE_SENTINEL})

        def run() -> None:
            self.statuses.append(_loopback_get(params["redirect_uri"], path))

        thread = threading.Thread(target=run)
        self.threads.append(thread)
        thread.start()
        return True


def test_a_sentinel_error_code_in_the_redirect_never_leaks(
    repo: Path, client_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = []
    for args in (["--json"], []):
        browser = ErrorBrowser()
        endpoint = TokenEndpoint(browser)
        monkeypatch.setattr(gc, "open_browser", browser)
        monkeypatch.setattr(gc, "token_sender", endpoint)
        result = _oauth(repo, "--client-file", str(client_file), *args)
        browser.join()
        assert result.exit_code == 1
        assert endpoint.calls == []
        if args:
            assert json.loads(result.stdout)["rule"] == "authorization_error"
        outputs.append(result.output)
    outputs += [path.read_text() for path in repo.rglob("*") if path.is_file()]
    for text in outputs:
        assert CODE_SENTINEL not in text


# --- 9. The crash label ------------------------------------------------------------------


def test_a_crash_in_connect_token_names_the_subcommand(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)

    def deep(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RecursionError(REFRESH)

    monkeypatch.setattr(connect_mod, "read_token", deep)

    result = runner.invoke(app, ["connect", "token", "google", "--repo", str(repo), "--print"])

    assert result.exit_code == 1
    assert result.output.startswith("mb connect token: unexpected error (RecursionError)")
    assert REFRESH not in result.output


# --- 10-12. Inspect and names --------------------------------------------------------------


@pytest.mark.parametrize(
    "link",
    [
        "https://search.google.com/ sign in again at https://evil.example/login",
        "https://search.google.com/x\tthen",
        "https://search.google.com/x https://evil.example/",
        "https://search.google.com/x‮cod.exe",
        "https://search.google.com/x y",
    ],
)
def test_an_inspection_link_is_one_plain_token(link: str) -> None:
    assert gr._inspection_link(link) is None
    assert (
        gr._inspection_link("https://search.google.com/search-console/inspect?id=abc") is not None
    )


def test_a_non_object_inspection_result_is_malformed(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_google_inspect import _inspect_api

    _signed_in(repo, client_file, google, monkeypatch)
    _inspect_api(monkeypatch, (200, {"inspectionResult": ["PASS"]}))

    code, payload, stderr = _json(repo, INSPECT_ARGS)

    assert code == 1
    assert payload["rule"] == "search_console_response_malformed"
    assert "(search_console_response_malformed)" in stderr


@pytest.mark.parametrize(
    "url",
    ["https://www.bücher.example/page", "https://www.example.com./page"],
)
def test_idn_and_trailing_dot_hosts_name_the_punycode_form(url: str) -> None:
    with pytest.raises(gr.ReadRefusal) as caught:
        gr._inspection_parts(url)
    assert caught.value.rule == "url_format"
    assert "punycode (xn--)" in str(caught.value)


def test_a_punycode_host_passes_the_format_check() -> None:
    assert gr._inspection_parts("https://www.xn--bcher-kva.example/page").hostname == (
        "www.xn--bcher-kva.example"
    )


@pytest.mark.parametrize("name", ["customEvent:p[e]\n", "activeUsers\n", "\tsessions", "date\r"])
def test_ga4_names_with_a_newline_or_tab_are_refused(name: str) -> None:
    with pytest.raises(gr.ReadRefusal) as caught:
        gr.ga4_names([name], "--metrics")
    assert caught.value.rule == "name_format"


def test_ga4_names_still_trim_surrounding_spaces() -> None:
    assert gr.ga4_names([" activeUsers , sessions "], "--metrics") == ["activeUsers", "sessions"]
    assert gr.sc_dimensions(["query, page"]) == ["query", "page"]
    with pytest.raises(gr.ReadRefusal):
        gr.sc_dimensions(["query\n"])


# --- 13. One no-redirect opener --------------------------------------------------------------


def test_google_calls_use_the_shared_no_redirect_opener(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not hasattr(go, "_OPENER") and not hasattr(go, "_NoRedirect")
    seen: list[str] = []

    class Answer:
        status = 200

        def __enter__(self) -> Answer:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            return b"{}"

    def opener(request: Any, timeout: float) -> Answer:
        seen.append(request.full_url)
        return Answer()

    monkeypatch.setattr(http_safe, "open_no_redirect", opener)

    assert go._urllib_sender("https://oauth2.googleapis.com/token", b"", {}, 1.0) == (200, b"{}")
    assert seen == ["https://oauth2.googleapis.com/token"]


def test_nothing_secret_reaches_the_new_outputs(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _edit(repo, "ga4_property_id=")
    _mint(monkeypatch)
    _api(monkeypatch)
    _test_json(repo)

    human = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo)])
    _, payload = _status(repo)

    _assert_never_shown(human.output + json.dumps(payload) + _yaml(repo))
    assert ACCESS not in human.output
    assert BOTH_SCOPES not in human.output
