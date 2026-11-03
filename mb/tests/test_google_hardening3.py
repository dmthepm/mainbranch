"""Google connect follow-ups from the #1069 reviews (#1073).

One rule for a usable stored grant (the matrix in test_google_hardening2
covers status and `mb connect test` over every grant shape), a deeply
nested grant, doctor's dossier row in a repo that tracks `.mb/connect.yaml`,
the stale user-scope entry after a `--scope repo` sign-in, and the rotate
guidance for Google. No network: stub senders and the local-file backend.
"""

# The fixtures are imported from test_google_connect, so test parameters
# share their names by design.
# ruff: noqa: F811

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mb import connect as connect_mod
from mb import credential_store
from mb import doctor as doctor_mod
from mb import google_connect as gc
from mb.cli import app
from tests.connect_binding import rebind_folder
from tests.test_google_connect import (  # noqa: F401 (fixtures are used by name)
    _google_entry,
    _oauth,
    client_file,
    google,
    google_env,
    loopback_only_network,
    repo,
    runner,
)
from tests.test_google_hardening import _plain, _track_config
from tests.test_google_hardening2 import (
    GRANT_SENTINEL,
    STRIPE_SENTINEL,
    _connect_stripe,
    _metadata_only,
    _next_line,
    _stripe_check,
)
from tests.test_google_probe import (  # noqa: F401 (fixtures are used by name)
    SITE,
    _api,
    _assert_never_shown,
    _mint,
    _sign_in,
    _status,
    _test_json,
    _yaml,
    fixed_day,
)

# Deep enough that the JSON parser gives up with RecursionError.
NESTED = "[" * 200_000


def _set_grant(repo: Path, value: str) -> None:
    ref = _google_entry(repo)["secrets"]["oauth_grant"]["ref"]
    credential_store.SecretStore("local-file").set(ref, value)


# --- 1. One rule for a stored grant ------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "command"),
    [
        (None, gc.REAUTH_WITH_CLIENT_COMMAND),
        (f"not json {GRANT_SENTINEL}", gc.REAUTH_WITH_CLIENT_COMMAND),
        (json.dumps({"client_secret": GRANT_SENTINEL}), gc.REAUTH_WITH_CLIENT_COMMAND),
        (json.dumps({"client_id": "id.example.com", "client_secret": "s"}), gc.REAUTH_COMMAND),
        (
            json.dumps({"client_id": "id.example.com", "client_secret": "s", "refresh_token": ""}),
            gc.REAUTH_COMMAND,
        ),
        (
            json.dumps(
                {"client_id": "id.example.com", "client_secret": None, "refresh_token": "t"}
            ),
            "",
        ),
        (NESTED, gc.REAUTH_WITH_CLIENT_COMMAND),
    ],
)
def test_one_rule_judges_a_stored_grant(value: str | None, command: str) -> None:
    """`--reauth` (client), the mint path (fields) and status agree on every grant."""

    assert gc.grant_repair_command(value) == command
    client_ok = value is not None and gc.client_from_grant(value) is not None
    assert client_ok is (command != gc.REAUTH_WITH_CLIENT_COMMAND)
    assert (value is not None and gc._grant_fields(value) is not None) is (command == "")


# --- 2. A deeply nested grant ------------------------------------------------------------


def test_a_deeply_nested_grant_reads_as_unreadable_not_a_crash(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(RecursionError):
        json.loads(NESTED)
    assert gc.client_from_grant(NESTED) is None
    assert gc._grant_fields(NESTED) is None
    _sign_in(repo, client_file, google, monkeypatch)
    _set_grant(repo, NESTED)

    as_json = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo), "--json"])
    human = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo)])
    _mint(monkeypatch)
    _api(monkeypatch)
    _, tested = _test_json(repo)

    for result in (as_json, human):
        assert not isinstance(result.exception, RecursionError), result.exception
        assert "Traceback" not in result.output
    payload = json.loads(as_json.stdout)
    assert payload["state"] == "invalid"
    assert payload["secrets"]["oauth_grant"]["readable"] is False
    assert payload["repair_command"] == gc.REAUTH_WITH_CLIENT_COMMAND
    assert "unreadable or incomplete" in payload["summary"]
    assert _next_line(human.stdout) == gc.REAUTH_WITH_CLIENT_COMMAND
    assert tested["rule"] == "oauth_grant_malformed"
    assert tested["repair_command"] == gc.REAUTH_WITH_CLIENT_COMMAND


# --- 3. Status over a grant that is gone or cannot mint ---------------------------------


def test_status_over_an_unreadable_grant_with_a_passing_check_is_not_ready(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sign-in recorded a passing check; then the grant became unreadable."""

    _sign_in(repo, client_file, google, monkeypatch)
    assert _status(repo)[1]["state"] == "ready"
    _set_grant(repo, f"not json {{ {GRANT_SENTINEL}")

    code, payload = _status(repo)

    assert code == 1
    assert payload["state"] == "invalid"
    assert payload["repair_command"] == gc.REAUTH_WITH_CLIENT_COMMAND
    _mint(monkeypatch)
    _api(monkeypatch)
    _, tested = _test_json(repo)
    assert tested["repair_command"] == payload["repair_command"]
    _assert_never_shown(json.dumps(payload) + json.dumps(tested))
    assert GRANT_SENTINEL not in json.dumps(payload) + json.dumps(tested)


def test_status_over_a_missing_grant_names_the_client_file(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    ref = _google_entry(repo)["secrets"]["oauth_grant"]["ref"]
    credential_store.SecretStore("local-file").delete(ref)

    code, payload = _status(repo)

    assert code == 1
    assert payload["state"] == "missing_secret"
    assert payload["secrets"]["oauth_grant"]["presence"] == "absent"
    assert payload["repair_command"] == gc.REAUTH_WITH_CLIENT_COMMAND
    assert "missing from the credential store" in payload["summary"]


# --- 4. Doctor's dossier row in a repo that tracks .mb/connect.yaml ---------------------


def _dossier(repo: Path, label: str, provider_id: str) -> None:
    path = repo / "core" / "operations" / "agent-access-dossier.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "| Provider | Access level | Storage | Verify |\n"
        "|---|---|---|---|\n"
        f"| {label} | read | local | `mb connect test {provider_id}` |\n",
        encoding="utf-8",
    )


def _record_stale_failure(repo: Path, provider_id: str) -> None:
    config = connect_mod._read_config(repo)
    config["providers"][provider_id]["validation"] = {
        "state": "invalid",
        "checked_at": "2026-10-01T00:00:00Z",
        "provider_verified": False,
        "summary": "An old failed check.",
    }
    connect_mod._write_config(repo, config)


def test_doctor_row_in_a_tracked_repo_shows_the_check_not_the_stale_status(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _connect_stripe(repo)
    _record_stale_failure(repo, "stripe")
    _track_config(repo)
    before = _yaml(repo)
    _stripe_check(monkeypatch, ok=True)
    _dossier(repo, "Stripe", "stripe")

    row = doctor_mod._dossier_verify_section(repo)["checks"][0]

    assert row["state"] == "ok"
    assert row["summary"] == (
        "`mb connect test stripe` → ready (not recorded: .mb/connect.yaml is tracked by git)"
    )
    assert _yaml(repo) == before
    assert STRIPE_SENTINEL not in json.dumps(row)


def test_doctor_row_for_a_failing_google_check_in_a_tracked_repo(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sign-in recorded a pass; the check now finds the sign-in revoked."""

    _sign_in(repo, client_file, google, monkeypatch)
    _track_config(repo)
    _mint(monkeypatch, status=400, payload={"error": "invalid_grant"})
    _dossier(repo, "Google", "google")

    row = doctor_mod._dossier_verify_section(repo)["checks"][0]

    assert row["state"] == "warn"
    tail = "→ reauth_required (not recorded: .mb/connect.yaml is tracked by git)"
    assert tail in row["summary"]
    _assert_never_shown(json.dumps(row))


def test_doctor_row_in_an_untracked_repo_reads_the_recorded_status(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _connect_stripe(repo)
    _record_stale_failure(repo, "stripe")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    rebind_folder(repo)
    _stripe_check(monkeypatch, ok=True)
    _dossier(repo, "Stripe", "stripe")

    row = doctor_mod._dossier_verify_section(repo)["checks"][0]

    assert row == {"name": "Stripe", "state": "ok", "summary": "`mb connect test stripe` → ready"}


# --- 5. The stale user-scope entry after a --scope repo sign-in --------------------------


def _user_entry(repo: Path, provider_id: str = "google") -> dict[str, Any] | None:
    repo_id = str(connect_mod._read_config(repo)["repo_id"])
    return connect_mod._user_scope_provider_entry(repo_id, provider_id)


def test_a_repo_scope_sign_in_drops_the_metadata_only_user_scope_entry(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect_mod.connect_provider(
        "google", repo=repo, metadata_pairs=[f"search_console_site={SITE}"], scope="user"
    )
    connect_mod.connect_provider("stripe", repo=repo, token=STRIPE_SENTINEL, scope="user")
    assert _user_entry(repo) is not None
    google()
    _api(monkeypatch)

    result = _oauth(repo, "--client-file", str(client_file), "--scope", "repo", "--json")

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["scope"] == "repo"
    assert _user_entry(repo) is None
    entry = _google_entry(repo)
    assert entry["scope"] == "repo"
    assert entry["metadata"]["search_console_site"] == SITE
    # Another provider's user-scope entry for this repo is left alone.
    assert _user_entry(repo, "stripe") is not None
    assert _status(repo)[1]["scope"] == "repo"
    _assert_never_shown(result.output + _yaml(repo))


def test_a_user_scope_entry_holding_a_credential_is_never_dropped(repo: Path) -> None:
    connect_mod.connect_provider("stripe", repo=repo, token=STRIPE_SENTINEL, scope="user")
    repo_id = str(connect_mod._read_config(repo)["repo_id"])

    assert connect_mod._drop_user_scope_metadata_only(repo_id, "stripe") is False
    assert _user_entry(repo, "stripe") is not None


def test_a_user_scope_sign_in_keeps_its_user_scope_entry(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect_mod.connect_provider(
        "google", repo=repo, metadata_pairs=[f"search_console_site={SITE}"], scope="user"
    )
    google()
    _api(monkeypatch)

    result = _oauth(repo, "--client-file", str(client_file), "--json")

    assert result.exit_code == 0, result.output
    user = _user_entry(repo)
    assert user is not None and gc.entry_is_oauth(user)


# --- 6. mb connect rotate guidance for Google -------------------------------------------


def _rotate(repo: Path) -> tuple[int, str]:
    result = runner.invoke(app, ["connect", "rotate", "google", "--repo", str(repo), "--json"])
    return result.exit_code, str(json.loads(result.stdout)["summary"])


def test_rotate_without_a_google_connection_names_the_sign_in(repo: Path) -> None:
    code, message = _rotate(repo)

    assert code == 2
    assert f"`{connect_mod.GOOGLE_SIGN_IN_COMMAND}`" in message
    assert "--token-stdin" not in message


def test_rotate_over_a_metadata_only_google_entry_names_the_sign_in(repo: Path) -> None:
    _metadata_only(repo)

    code, message = _rotate(repo)

    assert code == 2
    assert f"`{connect_mod.GOOGLE_SIGN_IN_COMMAND}`" in message
    assert "--token-stdin" not in message


@pytest.mark.parametrize("grant", ["valid", "garbage", "absent"])
def test_rotate_over_a_sign_in_names_the_reauth_that_works(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch, grant: str
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    if grant == "garbage":
        _set_grant(repo, f"not json {GRANT_SENTINEL}")
    elif grant == "absent":
        ref = _google_entry(repo)["secrets"]["oauth_grant"]["ref"]
        credential_store.SecretStore("local-file").delete(ref)

    code, message = _rotate(repo)

    assert code == 2
    expected = gc.REAUTH_COMMAND if grant == "valid" else gc.REAUTH_WITH_CLIENT_COMMAND
    assert f"`{expected}`" in message
    assert "--token-stdin" not in message
    assert GRANT_SENTINEL not in message
    _assert_never_shown(message)


def test_rotate_over_a_legacy_google_access_token_keeps_token_stdin(repo: Path) -> None:
    connect_mod.connect_provider("google", repo=repo, token="SYNTH-LEGACY-1073")

    code, message = _rotate(repo)

    assert code == 2
    assert "`mb connect google --token-stdin`" in message
    assert "SYNTH-LEGACY-1073" not in message


# --- Every new message path, plain and --json, shows no secret ---------------------------


def test_the_new_paths_never_show_a_secret(
    repo: Path, client_file: Path, google: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sign_in(repo, client_file, google, monkeypatch)
    secret_grant = json.dumps(
        {
            "client_id": "id.example.com",
            "client_secret": GRANT_SENTINEL,
            "note": GRANT_SENTINEL,
        }
    )
    seen: list[str] = []
    for value in (secret_grant, f"not json {GRANT_SENTINEL}", NESTED + GRANT_SENTINEL):
        _set_grant(repo, value)
        for args in (["status", "google"], ["rotate", "google"]):
            for flag in ([], ["--json"]):
                seen.append(
                    runner.invoke(app, ["connect", *args, "--repo", str(repo), *flag]).output
                )
        _mint(monkeypatch)
        _api(monkeypatch)
        seen.append(runner.invoke(app, ["connect", "test", "google", "--repo", str(repo)]).output)
        seen.append(
            runner.invoke(app, ["connect", "token", "google", "--repo", str(repo), "--json"]).output
        )
    _track_config(repo)
    _dossier(repo, "Google", "google")
    seen.append(json.dumps(doctor_mod._dossier_verify_section(repo)))

    text = "\n".join(_plain(output) for output in seen) + _yaml(repo)
    assert GRANT_SENTINEL not in text
    _assert_never_shown(text)
