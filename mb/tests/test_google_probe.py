"""Tests for `mb connect test google` on a Google sign-in (#1004, PR5).

An OAuth-mode `google` connection is checked with one read-only call per
granted product (Search Console `searchAnalytics.query`, GA4 `runReport`).
A legacy access-token `google` connection and the `ga4` provider keep their
old behaviour. No network: the token endpoint and both APIs are stub senders
behind the existing seams; the loopback-only guard, the local-file credential
store and the synthetic sentinels come from test_google_connect.
"""

# The fixtures are imported from test_google_connect, so test parameters
# share their names by design.
# ruff: noqa: F811

from __future__ import annotations

import http.server
import json
import socketserver
import sys
import threading
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from mb import connect as connect_mod
from mb import google_connect as gc
from mb import google_oauth as go
from mb import google_probe as gp
from mb.cli import app
from tests.test_google_connect import (  # noqa: F401 (fixtures are used by name)
    ACCESS,
    CLIENT_ID,
    CLIENT_SECRET,
    LEGACY_TOKEN,
    MINTED,
    REFRESH,
    SENTINELS,
    _config,
    _google_entry,
    _local_secrets,
    _oauth,
    client_file,
    google,
    google_env,
    loopback_only_network,
    repo,
    runner,
)
from tests.test_google_mint import DESCRIPTION, MintEndpoint

TODAY = date(2026, 10, 5)
PROBE_DAY = "2026-10-02"
SITE = "sc-domain:example.com"
PROPERTY = "123456789"
SC_URL = (
    "https://www.googleapis.com/webmasters/v3/sites/sc-domain%3Aexample.com/searchAnalytics/query"
)
GA4_URL = "https://analyticsdata.googleapis.com/v1beta/properties/123456789:runReport"
# Google text that must never be shown or recorded: a row value and an error message.
GOOGLE_TEXT = "SYNTH-GOOGLE-TEXT-0001"
GOOGLE_ROW = "SYNTH-GOOGLE-ROW-0001"
CODE_SENTINEL = "synthsentinelcode0001"
NEVER_SHOWN = (CLIENT_SECRET, REFRESH, MINTED, ACCESS, DESCRIPTION, GOOGLE_TEXT, GOOGLE_ROW)


def _ok_body(product: str) -> dict[str, Any]:
    if product == gp.SEARCH_CONSOLE:
        return {"rows": [{"keys": [GOOGLE_ROW], "clicks": 1}], "responseAggregationType": "x"}
    return {"rows": [{"metricValues": [{"value": GOOGLE_ROW}]}], "rowCount": 1}


def _error_body(status: int, *reasons: str) -> dict[str, Any]:
    return {
        "error": {
            "code": status,
            "message": f"{GOOGLE_TEXT} {DESCRIPTION}",
            "status": "PERMISSION_DENIED" if status == 403 else "OTHER",
            "errors": [{"reason": reason, "message": GOOGLE_TEXT} for reason in reasons],
            "details": [{"reason": reason, "metadata": {"x": GOOGLE_TEXT}} for reason in reasons],
        }
    }


class ApiEndpoint:
    """Stub for the Search Console and GA4 read endpoints.

    ``answers`` maps a product to ``(status, payload)``, ``(status, raw bytes)``
    or an exception to raise; a product not listed answers 200 with rows.
    """

    def __init__(self, **answers: Any) -> None:
        self.answers = answers
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self, url: str, body: bytes, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, bytes]:
        if url == SC_URL:
            product = gp.SEARCH_CONSOLE
        elif url == GA4_URL:
            product = gp.GA4
        else:
            pytest.fail("unexpected Google URL")
        self.calls.append(
            {
                "product": product,
                "url": url,
                "body": json.loads(body.decode("utf-8")),
                "authorization": headers.get("Authorization"),
                "content_type": headers.get("Content-Type"),
            }
        )
        answer = self.answers.get(product)
        if isinstance(answer, BaseException):
            raise answer
        if answer is None:
            return 200, json.dumps(_ok_body(product)).encode("utf-8")
        status, payload = answer
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        return status, raw

    def products(self) -> list[str]:
        return [call["product"] for call in self.calls]


@pytest.fixture(autouse=True)
def fixed_day(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gp, "today", lambda: TODAY)


def _api(monkeypatch: pytest.MonkeyPatch, **answers: Any) -> ApiEndpoint:
    endpoint = ApiEndpoint(**answers)
    monkeypatch.setattr(gp, "api_sender", endpoint)
    return endpoint


def _mint(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> MintEndpoint:
    gc.forget_minted()
    endpoint = MintEndpoint(**kwargs)
    monkeypatch.setattr(gc, "token_sender", endpoint)
    return endpoint


def _no_google(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> tuple[int, bytes]:
        pytest.fail("Google was called")

    monkeypatch.setattr(gc, "token_sender", refuse)
    monkeypatch.setattr(gp, "api_sender", refuse)


def _sign_in(
    repo: Path,
    client_file: Path,
    google: Any,
    monkeypatch: pytest.MonkeyPatch,
    *extra: str,
    site: bool = True,
    property_id: bool = True,
    **endpoint: Any,
) -> dict[str, Any]:
    google(**endpoint)
    _api(monkeypatch)
    args = ["--client-file", str(client_file)]
    if site:
        args += ["--metadata", f"search_console_site={SITE}"]
    if property_id:
        args += ["--metadata", f"ga4_property_id=properties/{PROPERTY}"]
    result = _oauth(repo, *args, *extra, "--json")
    # A sign-in that granted only one product exits 1 by design (PR3).
    assert result.exit_code == (0 if "scope" not in endpoint else 1), result.output
    return dict(json.loads(result.stdout))


def _test(repo: Path, *extra: str) -> Any:
    return runner.invoke(app, ["connect", "test", "google", "--repo", str(repo), *extra])


def _test_json(repo: Path) -> tuple[int, dict[str, Any]]:
    result = _test(repo, "--json")
    return result.exit_code, json.loads(result.stdout)


def _status(repo: Path) -> tuple[int, dict[str, Any]]:
    result = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo), "--json"])
    return result.exit_code, json.loads(result.stdout)


def _yaml(repo: Path) -> str:
    return (repo / ".mb" / "connect.yaml").read_text(encoding="utf-8")


def _assert_never_shown(text: str) -> None:
    for sentinel in (*NEVER_SHOWN, *SENTINELS):
        assert sentinel not in text


# --- Passing -----------------------------------------------------------------


def test_both_products_pass(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    token = _mint(monkeypatch)
    api = _api(monkeypatch)

    code, result = _test_json(repo)

    assert code == 0, result
    assert result["ok"] is True
    assert result["state"] == "ready"
    assert result["rule"] == "ok"
    assert result["provider_verified"] is True
    assert result["recorded"] is True
    assert {name: p["state"] for name, p in result["products"].items()} == {
        "search_console": "ok",
        "ga4": "ok",
    }
    assert len(token.calls) == 1
    assert api.products() == ["search_console", "ga4"]
    assert all(call["authorization"] == f"Bearer {MINTED}" for call in api.calls)
    status_code, status = _status(repo)
    assert status_code == 0
    assert status["state"] == "ready"
    assert status["has_probe"] is True
    assert status["provider_verified"] is True
    assert _config(repo)["providers"]["google"]["validation"]["products"] == {
        "search_console": {"state": "ok", "rule": "ok"},
        "ga4": {"state": "ok", "rule": "ok"},
    }


def test_request_bodies_match_the_plan(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _mint(monkeypatch)
    api = _api(monkeypatch)

    assert _test_json(repo)[0] == 0

    sc, ga4 = api.calls
    # Search Console: one past day, rowLimit 1, no dimensions; the site is
    # percent-encoded into the path.
    assert sc["url"] == SC_URL
    assert sc["body"] == {"startDate": PROBE_DAY, "endDate": PROBE_DAY, "rowLimit": 1}
    # GA4: activeUsers on one explicit past date, limit 1.
    assert ga4["url"] == GA4_URL
    assert ga4["body"] == {
        "dateRanges": [{"startDate": PROBE_DAY, "endDate": PROBE_DAY}],
        "metrics": [{"name": "activeUsers"}],
        "limit": 1,
    }
    assert {call["content_type"] for call in api.calls} == {"application/json"}


def test_url_prefix_site_is_percent_encoded() -> None:
    url, _body = gp.search_console_request("https://www.example.com/blog/", PROBE_DAY)
    assert url == (
        "https://www.googleapis.com/webmasters/v3/sites/"
        "https%3A%2F%2Fwww.example.com%2Fblog%2F/searchAnalytics/query"
    )


def test_sign_in_last_step_checks_with_the_exchanged_token(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser_endpoint = google()
    api = _api(monkeypatch)

    result = _oauth(
        repo,
        "--client-file",
        str(client_file),
        "--metadata",
        f"search_console_site={SITE}",
        "--metadata",
        f"ga4_property_id={PROPERTY}",
        "--json",
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["ready"] is True
    assert payload["provider_verified"] is True
    assert payload["check"]["state"] == "ready"
    assert payload["status"]["state"] == "ready"
    # The exchange's own access token; no refresh call was spent.
    assert [call["grant_type"] for call in browser_endpoint[1].calls] == [["authorization_code"]]
    assert all(call["authorization"] == f"Bearer {ACCESS}" for call in api.calls)
    _assert_never_shown(result.output)


def test_sign_in_human_output_shows_the_check(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    google()
    _api(monkeypatch, ga4=(403, _error_body(403, "forbidden")))

    result = _oauth(
        repo,
        "--client-file",
        str(client_file),
        "--metadata",
        f"search_console_site={SITE}",
        "--metadata",
        f"ga4_property_id={PROPERTY}",
    )

    # The sign-in is stored, so its exit code is the sign-in's.
    assert result.exit_code == 0, result.output
    assert "Checked with Google (read-only): warn (invalid)" in result.stdout
    assert "search_console: ok" in result.stdout
    assert "ga4: invalid (ga4_no_access)" in result.stdout
    assert "Property access management" in result.stdout
    assert "next: mb connect test google" in result.stdout
    _assert_never_shown(result.output)


def test_a_check_that_crashes_never_fails_the_sign_in(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    google()
    _api(monkeypatch, search_console=RuntimeError(f"boom {GOOGLE_TEXT}"))

    result = _oauth(
        repo, "--client-file", str(client_file), "--metadata", f"search_console_site={SITE}"
    )

    assert result.exit_code == 0, result.output
    assert "check_failed" not in result.stdout  # rendered as text, not a rule dump
    assert "RuntimeError" in result.stdout
    assert "next: mb connect test google" in result.stdout
    assert _google_entry(repo)["secrets"]["oauth_grant"]["ref"]
    _assert_never_shown(result.output)


# --- Partial: missing metadata, not granted -----------------------------------


def test_one_passes_and_one_is_missing_metadata(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch, property_id=False)
    _mint(monkeypatch)
    api = _api(monkeypatch)

    code, result = _test_json(repo)

    assert code == 1
    assert result["state"] == "unvalidated"
    assert result["rule"] == "ga4_property_not_recorded"
    assert result["repair_command"] == "mb connect google --metadata ga4_property_id=<property-id>"
    assert result["recorded"] is True
    assert result["products"]["search_console"]["state"] == "ok"
    assert result["products"]["ga4"]["state"] == "unvalidated"
    assert api.products() == ["search_console"]
    status_code, status = _status(repo)
    assert status_code == 1
    assert status["state"] == "unvalidated"
    assert status["repair_command"] == result["repair_command"]

    # The exact repair command works and keeps the recorded site.
    fixed = runner.invoke(
        app,
        ["connect", "google", "--repo", str(repo), "--metadata", f"ga4_property_id={PROPERTY}"],
        input="",
    )
    assert fixed.exit_code in {0, 1}, fixed.output
    metadata = _google_entry(repo)["metadata"]
    assert metadata["search_console_site"] == SITE
    assert metadata["ga4_property_id"] == PROPERTY
    assert sorted(_google_entry(repo)["secrets"]) == ["access_token", "oauth_grant"]
    assert _test_json(repo)[0] == 0


def test_missing_site_names_its_own_repair(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch, site=False)
    _mint(monkeypatch)
    _api(monkeypatch)

    result = _test(repo)

    assert result.exit_code == 1
    assert "search_console: unvalidated (search_console_site_not_recorded)" in result.stdout
    assert "ga4: ok" in result.stdout
    assert "next: mb connect google --metadata search_console_site=<site>" in result.stdout


def test_hand_edited_bad_site_reads_as_not_recorded(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    path = repo / ".mb" / "connect.yaml"
    path.write_text(_yaml(repo).replace(SITE, "not a site"), encoding="utf-8")
    _mint(monkeypatch)
    api = _api(monkeypatch)

    code, result = _test_json(repo)

    assert code == 1
    assert result["rule"] == "search_console_site_not_recorded"
    assert api.products() == ["ga4"]


def test_a_product_not_granted_is_skipped(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch, scope=go.SCOPE_SEARCH_CONSOLE)
    _mint(monkeypatch)
    api = _api(monkeypatch)

    code, result = _test_json(repo)

    assert code == 0, result
    assert result["state"] == "ready"
    assert result["products"]["ga4"]["state"] == "grant_missing"
    assert result["products"]["ga4"]["rule"] == "grant_missing"
    assert "not granted (skipped)" in result["summary"]
    assert api.products() == ["search_console"]
    human = _test(repo)
    assert "ga4: grant_missing" in human.stdout
    assert "--oauth --reauth" in human.stdout


def test_nothing_granted_reads_as_grant_missing(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    path = repo / ".mb" / "connect.yaml"
    path.write_text(_yaml(repo).replace("search_console,ga4", "''"), encoding="utf-8")
    _mint(monkeypatch)
    api = _api(monkeypatch)

    code, result = _test_json(repo)

    assert code == 1
    assert result["rule"] == "grant_missing"
    assert result["repair_command"] == "mb connect google --oauth --reauth"
    assert api.calls == []


# --- Refusals by Google -------------------------------------------------------

REFUSALS = {
    "sc_403": ("search_console", 403, (), "search_console_no_access", "Users and permissions"),
    "sc_404": ("search_console", 404, (), "search_console_no_access", "Users and permissions"),
    "sc_disabled": (
        "search_console",
        403,
        ("SERVICE_DISABLED",),
        "search_console_api_disabled",
        "Google Search Console API",
    ),
    "sc_401": ("search_console", 401, (), "search_console_auth_rejected", "--oauth --reauth"),
    "sc_400": ("search_console", 400, (), "search_console_request_rejected", "mb connect status"),
    "ga4_403": ("ga4", 403, ("forbidden",), "ga4_no_access", "Property access management"),
    "ga4_404": ("ga4", 404, (), "ga4_no_access", "Viewer"),
    "ga4_disabled": (
        "ga4",
        403,
        ("accessNotConfigured",),
        "ga4_api_disabled",
        "Google Analytics Data API",
    ),
    "ga4_401": ("ga4", 401, (), "ga4_auth_rejected", "--oauth --reauth"),
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_refusals_are_recorded_with_their_own_rule(
    case: str,
    repo: Path,
    client_file: Path,
    google: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product, status_code, reasons, rule, fix = REFUSALS[case]
    _sign_in(repo, client_file, google, monkeypatch)
    _mint(monkeypatch)
    _api(monkeypatch, **{product: (status_code, _error_body(status_code, *reasons))})

    code, result = _test_json(repo)
    human = _test(repo)

    assert code == 1
    assert human.exit_code == 1
    assert result["state"] == "invalid"
    assert result["rule"] == rule
    assert result["recorded"] is True
    assert result["products"][product]["rule"] == rule
    assert result["products"][product]["upstream"]["http_status"] == status_code
    assert fix in human.stdout
    entry = _google_entry(repo)
    assert entry["validation"]["state"] == "invalid"
    assert entry["validation"]["rule"] == rule
    status_exit, status = _status(repo)
    assert status_exit == 1
    assert status["state"] == "invalid"
    for text in (json.dumps(result), human.output, _yaml(repo), json.dumps(status)):
        _assert_never_shown(text)


def test_a_later_pass_records_ready_and_keeps_verified_at(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _mint(monkeypatch)
    _api(monkeypatch)
    _code, first = _test_json(repo)
    verified_at = first["verified_at"]
    assert verified_at

    _mint(monkeypatch)
    _api(monkeypatch, search_console=(403, _error_body(403)))
    assert _test_json(repo)[1]["verified_at"] == verified_at

    _mint(monkeypatch)
    _api(monkeypatch)
    code, again = _test_json(repo)
    assert code == 0
    assert again["status"]["state"] == "ready"


# --- The token -----------------------------------------------------------------


def test_invalid_grant_records_reauth_required(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _mint(
        monkeypatch,
        status=400,
        payload={"error": "invalid_grant", "error_description": DESCRIPTION},
    )
    api = _api(monkeypatch)

    code, result = _test_json(repo)
    human = _test(repo)

    assert code == 1
    assert result["state"] == "reauth_required"
    assert result["rule"] == "reauth_required"
    assert result["recorded"] is True
    assert result["repair_command"] == "mb connect google --oauth --reauth"
    assert {p["state"] for p in result["products"].values()} == {"not_checked"}
    assert api.calls == []
    assert "next: mb connect google --oauth --reauth" in human.stdout
    assert "recorded: no" not in human.stdout
    _no_google(monkeypatch)
    status_exit, status = _status(repo)
    assert status_exit == 1
    assert status["state"] == "reauth_required"
    _assert_never_shown(json.dumps(result) + human.output + _yaml(repo))


def test_a_pass_clears_a_recorded_reauth_required(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _mint(monkeypatch, status=400, payload={"error": "invalid_grant"})
    _test_json(repo)
    assert _status(repo)[1]["state"] == "reauth_required"

    _mint(monkeypatch)
    _api(monkeypatch)
    assert _test_json(repo)[0] == 0
    assert _status(repo)[1]["state"] == "ready"


TOKEN_REFUSALS = {
    "invalid_client": "oauth_client_rejected",
    "unauthorized_client": "oauth_client_unauthorized",
    "invalid_scope": "oauth_scope_rejected",
}


@pytest.mark.parametrize("error_code", sorted(TOKEN_REFUSALS))
def test_token_refusals_have_accurate_rules_and_are_recorded(
    error_code: str,
    repo: Path,
    client_file: Path,
    google: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _mint(monkeypatch, status=400, payload={"error": error_code, "error_description": DESCRIPTION})
    api = _api(monkeypatch)

    code, result = _test_json(repo)

    assert code == 1
    assert result["rule"] == TOKEN_REFUSALS[error_code]
    assert result["state"] == "invalid"
    assert result["recorded"] is True
    assert api.calls == []
    refused_client = "refused the OAuth client" in result["summary"]
    assert refused_client is (error_code == "invalid_client")
    assert result["repair_command"] == gc.REAUTH_WITH_CLIENT_COMMAND
    assert _status(repo)[1]["state"] == "invalid"


def test_a_sentinel_in_the_error_code_is_never_shown_or_recorded(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `error` code is Google's text too; nothing echoes or records it."""

    _sign_in(repo, client_file, google, monkeypatch)
    outputs = []
    for args in (["--json"], []):
        _mint(monkeypatch, status=400, payload={"error": CODE_SENTINEL})
        outputs.append(_test(repo, *args).output)
    _mint(monkeypatch, status=400, payload={"error": CODE_SENTINEL})
    token = runner.invoke(app, ["connect", "token", "google", "--repo", str(repo), "--print"])
    assert token.exit_code == 1
    outputs.append(token.output)
    _mint(monkeypatch, status=400, payload={"error": CODE_SENTINEL})
    outputs.append(repr(connect_mod.read_token("google", repo)))
    outputs += [_yaml(repo), json.dumps(_status(repo)[1])]
    for text in outputs:
        assert CODE_SENTINEL not in text


# --- Transient: state unchanged --------------------------------------------------

TRANSIENT = {
    "sc_network": ("search_console", OSError("down"), "search_console_unreachable"),
    "sc_500": ("search_console", (500, _error_body(500)), "search_console_server_error"),
    "sc_503": (
        "search_console",
        (503, b"<html>" + GOOGLE_TEXT.encode()),
        "search_console_server_error",
    ),
    "sc_429": ("search_console", (429, _error_body(429)), "search_console_quota_exhausted"),
    "sc_403_quota": (
        "search_console",
        (403, _error_body(403, "rateLimitExceeded")),
        "search_console_quota_exhausted",
    ),
    "sc_malformed": (
        "search_console",
        (200, b"not json " + GOOGLE_TEXT.encode()),
        "search_console_response_malformed",
    ),
    "ga4_network": ("ga4", TimeoutError("slow"), "ga4_unreachable"),
    "ga4_500": ("ga4", (500, _error_body(500)), "ga4_server_error"),
    "ga4_deep_json": ("ga4", (500, b"[" * 200000 + b"]" * 200000), "ga4_server_error"),
    "ga4_quota": ("ga4", (429, _error_body(429, "RESOURCE_EXHAUSTED")), "ga4_quota_exhausted"),
}


@pytest.mark.parametrize("case", sorted(TRANSIENT))
def test_network_and_server_trouble_leave_the_state_unchanged(
    case: str,
    repo: Path,
    client_file: Path,
    google: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product, answer, rule = TRANSIENT[case]
    _sign_in(repo, client_file, google, monkeypatch)
    assert _status(repo)[1]["state"] == "ready"  # the sign-in's own check passed
    before = _yaml(repo)
    _mint(monkeypatch)
    _api(monkeypatch, **{product: answer})

    code, result = _test_json(repo)
    human = _test(repo)

    assert code == 1
    assert human.exit_code == 1
    assert result["ok"] is False
    assert result["state"] == "unvalidated"
    assert result["rule"] == rule
    assert result["recorded"] is False
    assert result["needs_action"] is True
    assert result["status"]["state"] == "ready"
    assert "recorded: no" in human.stdout
    assert "status still reads ready" in human.stdout
    assert _yaml(repo) == before
    _assert_never_shown(json.dumps(result) + human.output)


@pytest.mark.parametrize(
    ("endpoint", "rule"),
    [
        ({"raises": OSError("down")}, "token_unreachable"),
        ({"status": 503, "payload": {"error": "backend"}}, "token_request_failed"),
        ({"raw": b"[" * 200000}, "token_response_malformed"),
    ],
)
def test_token_trouble_leaves_the_state_unchanged(
    endpoint: dict[str, Any],
    rule: str,
    repo: Path,
    client_file: Path,
    google: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    before = _yaml(repo)
    _mint(monkeypatch, **endpoint)
    api = _api(monkeypatch)

    code, result = _test_json(repo)

    assert code == 1
    assert result["rule"] == rule
    assert result["recorded"] is False
    assert api.calls == []
    assert _yaml(repo) == before
    assert _status(repo)[1]["state"] == "ready"


def test_deeply_nested_token_answer_names_the_token_command(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _mint(monkeypatch, raw=b"[" * 200000)

    result = runner.invoke(app, ["connect", "token", "google", "--repo", str(repo), "--print"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.startswith("mb connect token: ")
    assert "unreadable" in result.stderr


# --- User scope -------------------------------------------------------------------


def test_user_scope_entry_records_in_user_scope_too(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch, "--scope", "user")
    _mint(monkeypatch)
    _api(monkeypatch, ga4=(403, _error_body(403)))

    code, result = _test_json(repo)

    assert code == 1
    assert result["rule"] == "ga4_no_access"
    stored = connect_mod._user_scope_provider_entry(str(_config(repo)["repo_id"]), "google")
    assert stored is not None
    assert stored["validation"]["rule"] == "ga4_no_access"


# --- The conditional probe ----------------------------------------------------------


def test_status_and_doctor_never_call_google(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    _no_google(monkeypatch)

    for args in (
        ["connect", "status", "google"],
        ["connect", "status", "google", "--json"],
        ["connect", "status"],
        ["connect", "status", "--all"],
        ["connect", "doctor"],
        ["connect", "doctor", "--json"],
        ["connect", "list"],
    ):
        result = runner.invoke(app, [*args, "--repo", str(repo)])
        assert result.exit_code in {0, 1}, args


def test_oauth_entry_has_a_probe_and_leaves_the_probe_gap(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    entry = _google_entry(repo)
    # A sign-in from before this release recorded `stored_unverified` from the
    # probe-less test; that is now actionable on every surface.
    entry["validation"] = {"state": connect_mod.UNVERIFIED_STATE, "provider_verified": False}
    config = _config(repo)
    config["providers"]["google"] = entry
    connect_mod._write_config(repo, config)
    _no_google(monkeypatch)

    assert connect_mod.has_provider_probe("google", entry) is True
    status_exit, status = _status(repo)
    assert status["has_probe"] is True
    assert status["state"] == connect_mod.UNVERIFIED_STATE
    assert status_exit == 1
    doctor = runner.invoke(app, ["connect", "doctor", "--repo", str(repo), "--json"])
    report = json.loads(doctor.stdout)
    (item,) = report["integrations"]["providers"]
    assert connect_mod.provider_needs_action(item) is True
    assert doctor.exit_code == 1
    assert report["probe_gap"]["providers"] == []


def test_unhydrated_user_scope_sign_in_has_a_probe(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch, "--scope", "user")
    config = _config(repo)
    del config["providers"]["google"]
    connect_mod._write_config(repo, config)
    _no_google(monkeypatch)

    item = connect_mod.status_provider("google", repo)

    assert item["state"] == "needs_hydration"
    assert item["has_probe"] is True
    assert connect_mod._probe_gap({"providers": [item]})["providers"] == []


def test_legacy_google_stays_probe_less_and_unchanged(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect_mod.connect_provider("google", repo=repo, token=LEGACY_TOKEN)
    _no_google(monkeypatch)
    entry = _google_entry(repo)

    assert connect_mod.has_provider_probe("google", entry) is False
    code, result = _test_json(repo)
    assert code == 0
    assert "products" not in result
    assert result["validation"]["state"] == connect_mod.UNVERIFIED_STATE
    assert "needs_action" not in result
    human = _test(repo)
    assert human.exit_code == 0
    assert human.stdout.startswith("mb connect test google: stored, not checked with the provider")
    status_exit, status = _status(repo)
    assert status_exit == 0
    assert status["has_probe"] is False
    assert status["credential_mode"] == "access_token"
    doctor = runner.invoke(app, ["connect", "doctor", "--repo", str(repo), "--json"])
    report = json.loads(doctor.stdout)
    # Doctor's exit also covers the GitHub CLI, absent here; the Google part
    # is what must not ask for action.
    (item,) = report["integrations"]["providers"]
    assert connect_mod.provider_needs_action(item) is False
    assert report["probe_gap"]["providers"] == ["google"]
    assert connect_mod.read_token("google", repo)["token"] == LEGACY_TOKEN


def test_ga4_provider_is_unchanged(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    connect_mod.connect_provider(
        "ga4", repo=repo, token="SYNTH-GA4-0001", metadata_pairs=["property_id=123"]
    )
    _no_google(monkeypatch)
    calls: list[str] = []

    def fake_http(url: str, headers: Any = None, **kwargs: Any) -> dict[str, Any]:
        calls.append(url)
        return {"ok": True, "state": "ready", "summary": "simulated", "upstream": {}}

    monkeypatch.setattr(connect_mod, "_http_get_json", fake_http)

    result = runner.invoke(app, ["connect", "test", "ga4", "--repo", str(repo), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert "products" not in payload
    assert payload["status"]["state"] == "ready"
    assert calls == ["https://analyticsadmin.googleapis.com/v1beta/properties/123"]
    assert connect_mod.has_provider_probe("ga4") is True


# --- No secret or Google text leaves the process -------------------------------------


def test_nothing_secret_or_from_google_leaks(
    repo: Path,
    client_file: Path,
    google: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outputs: list[str] = []
    google()
    _api(monkeypatch)
    signed = _oauth(
        repo,
        "--client-file",
        str(client_file),
        "--metadata",
        f"search_console_site={SITE}",
        "--metadata",
        f"ga4_property_id={PROPERTY}",
    )
    outputs.append(signed.output)
    answers: list[dict[str, Any]] = [
        {},
        {
            "search_console": (403, _error_body(403)),
            "ga4": (403, _error_body(403, "SERVICE_DISABLED")),
        },
        {"search_console": (500, _error_body(500)), "ga4": (200, b"x" + GOOGLE_TEXT.encode())},
        {"ga4": (400, _error_body(400, "badRequest"))},
    ]
    for answer in answers:
        for args in (["--json"], []):
            _mint(monkeypatch)
            _api(monkeypatch, **answer)
            result = _test(repo, *args)
            outputs += [result.stdout, result.stderr]
    _mint(
        monkeypatch,
        status=400,
        payload={"error": "invalid_grant", "error_description": DESCRIPTION},
    )
    _api(monkeypatch)
    outputs.append(_test(repo, "--json").output)
    _mint(monkeypatch)
    _api(monkeypatch)
    direct = connect_mod.test_provider("google", repo)
    outputs += [repr(direct), json.dumps(direct)]
    for args in (
        ["connect", "status", "google", "--json"],
        ["connect", "status", "google"],
        ["connect", "doctor", "--json"],
        ["connect", "list"],
        ["connect", "identity", "--json"],
    ):
        outputs.append(runner.invoke(app, [*args, "--repo", str(repo)]).output)
    for path in repo.rglob("*"):
        if path.is_file():
            outputs.append(path.read_text(encoding="utf-8", errors="replace"))
    for path in (tmp_path / "home").rglob("*.yaml"):
        outputs.append(path.read_text(encoding="utf-8", errors="replace"))
    for text in outputs:
        _assert_never_shown(text)
    # The minted token and the grant stay in memory and the store only.
    assert MINTED not in json.dumps(_local_secrets())


# --- Fix round 1: transient token answers, redirects, exact matching ------------

# Token-endpoint answers that say nothing about the client or the grant:
# (status, raw body, rule). None of them is recorded or names a new sign-in.
TRANSIENT_TOKEN = {
    "429_empty": (429, b"", "token_request_failed"),
    "429_with_code": (429, b'{"error": "invalid_grant"}', "token_request_failed"),
    "408_empty": (408, b"", "token_request_failed"),
    "400_empty": (400, b"", "token_request_failed"),
    "401_no_code": (401, b'{"message": "x"}', "token_request_failed"),
    "invalid_request": (400, b'{"error": "invalid_request"}', "token_request_rejected"),
    "unknown_code": (400, json.dumps({"error": CODE_SENTINEL}).encode(), "token_request_rejected"),
    "redirect": (302, b"", "token_unexpected_redirect"),
}


@pytest.mark.parametrize("case", sorted(TRANSIENT_TOKEN))
def test_transient_token_answers_are_never_recorded(
    case: str,
    repo: Path,
    client_file: Path,
    google: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    status_code, raw, rule = TRANSIENT_TOKEN[case]
    _sign_in(repo, client_file, google, monkeypatch)
    before = _yaml(repo)
    assert _status(repo)[1]["state"] == "ready"
    api = _api(monkeypatch)

    _mint(monkeypatch, status=status_code, raw=raw)
    code, result = _test_json(repo)
    _mint(monkeypatch, status=status_code, raw=raw)
    human = _test(repo)
    _mint(monkeypatch, status=status_code, raw=raw)
    token = runner.invoke(app, ["connect", "token", "google", "--repo", str(repo), "--print"])
    _mint(monkeypatch, status=status_code, raw=raw)
    marker = tmp_path / "child-ran"
    child = runner.invoke(
        app,
        [
            "connect",
            "exec",
            "google",
            "--repo",
            str(repo),
            "--",
            sys.executable,
            "-c",
            f"open({str(marker)!r}, 'w').close()",
        ],
    )

    assert code == 1
    assert result["rule"] == rule
    assert result["state"] == "unvalidated"
    assert result["recorded"] is False
    assert result["repair_command"] == ""
    assert api.calls == []
    assert human.exit_code == 1
    assert "try again later" in human.stdout
    assert "recorded: no" in human.stdout
    for output in (human.output, token.output, child.output, json.dumps(result)):
        assert "--reauth" not in output
        assert "sign in again" not in output
        assert CODE_SENTINEL not in output
    assert token.exit_code == 1
    assert token.stdout == ""
    assert "try again later" in token.stderr
    assert child.exit_code == 1
    assert not marker.exists()
    assert _yaml(repo) == before
    status_exit, status = _status(repo)
    assert status_exit == 0
    assert status["state"] == "ready"


def test_api_redirect_is_not_followed_or_recorded(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    before = _yaml(repo)
    _mint(monkeypatch)
    api = _api(monkeypatch, ga4=(302, b""))

    code, result = _test_json(repo)

    assert code == 1
    assert result["rule"] == "ga4_unexpected_redirect"
    assert result["recorded"] is False
    assert api.products() == ["search_console", "ga4"]
    assert _yaml(repo) == before


class _Recorder(http.server.BaseHTTPRequestHandler):
    """Loopback server: the first path redirects, anything else is recorded."""

    received: list[dict[str, Any]] = []
    status = 302
    target = ""

    def _answer(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if self.path == "/start":
            self.send_response(self.status)
            self.send_header("Location", self.target)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        type(self).received.append(
            {"path": self.path, "authorization": self.headers.get("Authorization"), "body": body}
        )
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    do_GET = do_POST = _answer

    def log_message(self, *args: Any) -> None:
        return None


@pytest.mark.parametrize("status_code", [301, 302, 303, 307, 308])
def test_the_sender_never_follows_a_redirect(status_code: int) -> None:
    received: list[dict[str, Any]] = []

    class Handler(_Recorder):
        pass

    Handler.received = received
    Handler.status = status_code
    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    Handler.target = f"http://127.0.0.1:{port}/second"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _raw = go._urllib_sender(
            f"http://127.0.0.1:{port}/start",
            b"refresh_token=" + REFRESH.encode(),
            {"Authorization": f"Bearer {MINTED}", "Content-Type": "application/json"},
            5.0,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == status_code
    # Nothing reached the second URL: no bearer token, no form body.
    assert received == []


@pytest.mark.parametrize(
    "site",
    [
        "sc-domain:example.com\n.org",
        "sc-domain:exam\nple.com",
        "sc-domain:example.com\x00",
        "https://www.example.com/a\nb/",
        "https://www.example.com/a b/",
    ],
)
def test_a_site_with_a_newline_or_control_character_is_refused(site: str) -> None:
    with pytest.raises(connect_mod.ConnectRefusal) as caught:
        gc.normalize_search_console_site(site)
    assert caught.value.rule == "search_console_site_format"


@pytest.mark.parametrize("value", ["123\n456", "１２３", "123\x00"])
def test_a_property_id_that_is_not_only_ascii_digits_is_refused(value: str) -> None:
    with pytest.raises(connect_mod.ConnectRefusal) as caught:
        gc.normalize_ga4_property_id(value)
    assert caught.value.rule == "ga4_property_id_format"


def test_a_hand_edited_value_with_a_newline_reads_as_not_recorded(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    config = _config(repo)
    config["providers"]["google"]["metadata"]["search_console_site"] = "sc-domain:example.com\n.org"
    connect_mod._write_config(repo, config)
    _mint(monkeypatch)
    api = _api(monkeypatch)

    code, result = _test_json(repo)

    assert code == 1
    assert result["rule"] == "search_console_site_not_recorded"
    assert api.products() == ["ga4"]


def test_connect_refuses_a_site_with_a_newline(repo: Path, client_file: Path, google: Any) -> None:
    google()
    result = _oauth(
        repo,
        "--client-file",
        str(client_file),
        "--metadata",
        "search_console_site=sc-domain:example.com\n.org",
    )
    assert result.exit_code == 2
    assert _google_entry(repo) == {}
