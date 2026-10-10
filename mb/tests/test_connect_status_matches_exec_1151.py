"""`mb connect status`, `list` and `mb doctor` agree with `mb connect exec` (#1151).

Both read a credential the same way (one helper `get`, interaction off). They
used to disagree because the status commands read every provider under one
shared credential budget: the providers reached last were starved of time and
reported as a broken backend or a pending keychain prompt, while `exec` (its own
budget, one item) read the same credential at once. Everything here uses a fake
helper and a fake clock; no keychain is touched.
"""

from __future__ import annotations

import json
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from mb import _credential_helper as helper_mod
from mb import connect as connect_mod
from mb import credential_store as store_mod
from mb.cli import app

runner = CliRunner()

PLAIN = {
    "cloudflare": ("api_token", "fixture-cloudflare-1151"),
    "resend": ("api_key", "re_fixture1151"),
}
CUSTOM = {
    "orbit-books": "fixture-orbit-1151",
    "harbor-ledger": "fixture-harbor-1151",
}
IDS = [*PLAIN, *CUSTOM]


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.tick = 0.05

    def monotonic(self) -> float:
        # Reading the clock costs a little, as the repo and git work an
        # aggregate command does before its first credential read does.
        self.now += self.tick
        return self.now

    def time(self) -> float:
        return self.now


class FakeKeychain:
    """Stands in for `_invoke_helper`: answers `get` per ref, costing fake time."""

    def __init__(self, clock: Clock, cost: float) -> None:
        self.clock = clock
        self.cost = cost
        self.modes: dict[str, str] = {}
        self.costs: dict[str, float] = {}
        # Refs whose first read answers "prompt-pending" after using its time.
        self.pending_first: set[str] = set()
        self.calls: list[tuple[str, str, float]] = []

    def __call__(self, args: list[str], stdin: str, timeout: float) -> tuple[int, str]:
        action = args[-1]
        ref = json.loads(stdin)["ref"]
        self.calls.append((action, ref, timeout))
        cost = self.costs.get(ref, self.cost)
        if timeout < cost:
            self.clock.now += timeout
            raise subprocess.TimeoutExpired(args, timeout)
        if ref in self.pending_first:
            self.pending_first.discard(ref)
            self.clock.now += timeout
            return 1, json.dumps({"state": "prompt-pending"})
        self.clock.now += cost
        assert action == "get"
        mode = self.modes.get(ref, "ready")
        if mode == "ready":
            stored = store_mod._read_local_secrets()
            if ref in stored:
                return 0, json.dumps({"state": "ready", "value": stored[ref]})
            return 0, json.dumps({"state": "missing"})
        if mode == "missing":
            return 0, json.dumps({"state": "missing"})
        return 1, json.dumps({"state": mode})


def _connect_all(repo: Path, ids: list[str]) -> dict[str, str]:
    """Connect each provider, then point its recorded refs at the keychain."""

    for provider_id in ids:
        if provider_id in PLAIN:
            token = PLAIN[provider_id][1]
            connect_mod.connect_provider(provider_id, repo, token=token)
        else:
            connect_mod.connect_provider(provider_id, repo, token=CUSTOM[provider_id], custom=True)
    path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    refs: dict[str, str] = {}
    for provider_id in ids:
        for slot in config["providers"][provider_id]["secrets"].values():
            slot["backend"] = "macos-keychain"
            refs[provider_id] = slot["ref"]
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return refs


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    repo = tmp_path / "business"
    repo.mkdir()

    def build(ids: list[str], *, cost: float) -> tuple[Path, dict[str, str], FakeKeychain]:
        refs = _connect_all(repo, ids)
        clock = Clock()
        keychain = FakeKeychain(clock, cost)
        monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]
        monkeypatch.setattr(time, "monotonic", clock.monotonic)
        monkeypatch.setattr(time, "time", clock.time)
        monkeypatch.setattr(store_mod, "_invoke_helper", keychain)
        return repo, refs, keychain

    return build


def _by_id(status: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["provider"]: item for item in status["providers"]}


def test_starved_probes_are_not_reported_as_a_broken_backend(world: Any) -> None:
    """Each read costs 3 s; the shared 8 s budget reaches only the first providers."""

    repo, refs, keychain = world(IDS, cost=3.0)

    status = connect_mod.status_all(repo)
    providers = _by_id(status)

    # exec reads every one of them, each on its own budget.
    for provider_id in IDS:
        assert connect_mod.read_token(provider_id, repo)["ok"] is True
    skipped = [pid for pid in IDS if providers[pid]["state"] == "credential_not_checked"]
    assert skipped, "the fake clock should starve the later providers"
    for provider_id in IDS:
        item = providers[provider_id]
        assert item["state"] != connect_mod.BACKEND_FAILURE_STATE
        assert item["state"] != "missing_secret"
        slot = next(iter(item["secrets"].values()))
        assert slot["backend_state"] not in {"keychain_prompt_pending", "credential_store_timeout"}
        if provider_id in skipped:
            assert item["ok"] is False
            assert item["stored"] is False
            assert slot["present"] is None
            assert slot["presence"] == "unknown"
            assert slot["backend_ok"] is True
            assert slot["backend_state"] == "not_checked"
            assert item["repair_command"] == f"mb connect status {provider_id}"
            assert "repair" not in item["summary"].lower().replace("nothing to repair", "")
    assert status["summary"]["not_checked"] == len(skipped)
    # What needs repair is only what status can see: never a skipped provider,
    # and never as a broken backend (these are merely not validated yet).
    assert status["summary"]["needs_repair"] == len(IDS) - len(skipped)
    assert {pid for pid in IDS if providers[pid]["state"] == "unvalidated"} == set(IDS) - set(
        skipped
    )
    assert status["ok"] is False
    assert status["credential_backend"]["ok"] is True
    assert keychain.calls  # the fake was exercised


def test_doctor_never_sends_an_agent_to_repair_what_exec_can_read(world: Any) -> None:
    repo, _refs, _keychain = world(IDS, cost=3.0)
    status = connect_mod.status_all(repo)

    # Nothing left to repair but the skipped ones: validate the rest.
    for item in status["providers"]:
        if item["state"] == "unvalidated":
            item.update(ok=True, state="ready")
    status["summary"]["needs_repair"] = 0
    status["summary"]["healthy"] = len(status["providers"]) - status["summary"]["not_checked"]
    check = connect_mod.doctor_check(repo, status=status)
    backend = connect_mod._configured_backend_health(status)

    assert backend is not None and backend["ok"] is True
    assert "keychain" not in (check["repair"] + check["detail"]).lower()
    assert "repair --keychain" not in check["repair_command"]
    assert check["repair_command"].startswith("mb connect status ")
    assert "not checked" in check["detail"]
    assert check["severity"] == "info"


def test_cli_status_and_list_do_not_report_a_broken_backend(world: Any) -> None:
    repo, _refs, _keychain = world(IDS, cost=3.0)

    status = runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"])
    listed = runner.invoke(app, ["connect", "list", "--repo", str(repo), "--json"])

    for result in (status, listed):
        assert "backend_unavailable" not in result.stdout
        assert "keychain_prompt_pending" not in result.stdout
    states = {item["id"]: item["state"] for item in json.loads(listed.stdout)["custom_providers"]}
    assert set(states.values()) <= {"credential_not_checked", "unvalidated"}


def test_single_provider_status_has_its_own_budget(world: Any) -> None:
    repo, _refs, _keychain = world(IDS, cost=3.0)
    last = "orbit-books"  # sorted last: the retry of the one before it spent the budget
    assert _by_id(connect_mod.status_all(repo))[last]["state"] == "credential_not_checked"

    result = runner.invoke(app, ["connect", "status", last, "--repo", str(repo), "--json"])

    payload = json.loads(result.stdout)
    assert payload["state"] == "unvalidated"
    assert payload["stored"] is True
    assert next(iter(payload["secrets"].values()))["presence"] == "present"


def test_a_genuine_slow_store_still_times_out_inside_a_read(world: Any) -> None:
    """A read that starts and does not finish is still a store timeout."""

    repo, _refs, _keychain = world(["cloudflare"], cost=30.0)

    status = connect_mod.status_all(repo)

    item = _by_id(status)["cloudflare"]
    assert item["state"] == connect_mod.BACKEND_FAILURE_STATE
    assert next(iter(item["secrets"].values()))["backend_state"] == "credential_store_timeout"


@pytest.mark.parametrize(
    ("mode", "status_state", "backend_state", "exec_state"),
    [
        ("ready", "unvalidated", "ready", "ready"),
        ("missing", "missing_secret", "ready", "missing_secret"),
        ("locked", "backend_unavailable", "keychain_locked", "backend_unavailable"),
        # Present, but this reader is not on the item's access list: with
        # interaction off macOS refuses at once, which means a dialog is waiting.
        (
            "prompt-pending",
            "backend_unavailable",
            "keychain_prompt_pending",
            "backend_unavailable",
        ),
        ("auth-failed", "backend_unavailable", "keychain_auth_failed", "backend_unavailable"),
    ],
)
def test_status_and_exec_give_the_same_answer_for_the_same_item(
    world: Any, mode: str, status_state: str, backend_state: str, exec_state: str
) -> None:
    repo, refs, keychain = world(["cloudflare"], cost=0.2)
    keychain.modes[refs["cloudflare"]] = mode

    status = connect_mod.status_provider("cloudflare", repo)
    token = connect_mod.read_token("cloudflare", repo)

    slot = status["secrets"]["api_token"]
    assert status["state"] == status_state
    assert slot["backend_state"] == backend_state
    assert token["state"] == exec_state
    assert token["backend_state"] == backend_state
    # The same item gives the same answer in the aggregate command.
    aggregate = _by_id(connect_mod.status_all(repo))["cloudflare"]
    assert aggregate["state"] == status_state
    assert aggregate["secrets"]["api_token"]["backend_state"] == backend_state
    assert token["ok"] is (mode == "ready")


def test_exec_tells_a_missing_item_from_one_that_exists_but_cannot_be_read(world: Any) -> None:
    repo, refs, keychain = world(["cloudflare"], cost=0.2)
    keychain.modes[refs["cloudflare"]] = "missing"
    missing = connect_mod.read_token("cloudflare", repo)
    for mode in ("locked", "prompt-pending", "auth-failed"):
        keychain.modes[refs["cloudflare"]] = mode
        unreadable = connect_mod.read_token("cloudflare", repo)
        assert unreadable["state"] == "backend_unavailable"
        assert "missing" not in unreadable["error"].lower()
        assert unreadable["error"] != missing["error"]
    assert missing["state"] == "missing_secret"
    assert "missing from the secret store" in missing["error"]


def test_a_spent_budget_never_launches_a_read_and_other_callers_keep_the_timeout() -> None:
    launched: list[str] = []

    def invoke(args: list[str], stdin: str, timeout: float) -> tuple[int, str]:
        launched.append(args[-1])
        return 0, json.dumps({"state": "missing"})

    store = store_mod.SecretStore("local-file")
    store.backend = "macos-keychain"
    spent = time.monotonic() + store_mod.MIN_PROBE_SECONDS / 2
    original = store_mod._invoke_helper
    store_mod._invoke_helper = invoke
    try:
        status_probe = store.probe("fixture-ref", deadline=spent, allow_not_checked=True)
        other = store.probe("fixture-ref", deadline=spent)
    finally:
        store_mod._invoke_helper = original

    assert launched == []
    assert status_probe.not_checked is True
    assert (status_probe.present, status_probe.backend_ok, status_probe.reason) == (False, True, "")
    assert other.not_checked is False
    assert (other.backend_ok, other.reason) == (False, "credential_store_timeout")
    assert "not_checked" not in repr(other)
    assert "not_checked=True" in repr(status_probe)


class _NoBudgetAdapter:
    def __init__(self, **_kwargs: Any) -> None:
        pass

    migrated = False
    owner = ""

    def get(self, ref: str) -> tuple[str, str | None]:
        raise helper_mod._BudgetSpent

    health = get


def test_helper_reports_a_spent_budget_as_not_checked_and_a_started_call_as_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_adapter = helper_mod._MacSecurity
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(helper_mod, "_MacSecurity", _NoBudgetAdapter)

    state, value, _migrated, _owner = helper_mod._macos("get", {"ref": "fixture-ref"})
    assert (state, value) == ("not-checked", None)

    # No `security` call ever started: not a dialog.
    adapter = object.__new__(real_adapter)
    adapter.deadline = time.monotonic() - 1
    with pytest.raises(helper_mod._BudgetSpent):
        adapter._security_tool(["find-generic-password"])

    # One that started and ran out of time is a pending prompt, whatever the
    # budget it was given: the parent decides whether to read it again.
    def hang(*_args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired("security", kwargs["timeout"])

    adapter.deadline = time.monotonic() + 5
    monkeypatch.setattr(subprocess, "run", hang)
    with pytest.raises(helper_mod._PromptPending):
        adapter._security_tool(["find-generic-password"])
    assert helper_mod._failure_state(helper_mod._BudgetSpent()) == "not-checked"
    assert helper_mod._failure_state(helper_mod._PromptPending()) == "prompt-pending"


def _clipped_pair(world: Any) -> tuple[Path, dict[str, str], FakeKeychain]:
    """Cloudflare uses 2.5 s of the shared 8 s, so resend's read is clipped."""

    repo, refs, keychain = world(["cloudflare", "resend"], cost=0.1)
    keychain.costs[refs["cloudflare"]] = 2.5
    return repo, refs, keychain


def test_a_clipped_read_that_hangs_is_a_store_timeout_like_exec(world: Any) -> None:
    repo, refs, keychain = _clipped_pair(world)
    keychain.costs[refs["resend"]] = 999.0

    resend = _by_id(connect_mod.status_all(repo))["resend"]
    slot = next(iter(resend["secrets"].values()))
    assert resend["state"] == connect_mod.BACKEND_FAILURE_STATE
    assert slot["backend_state"] == "credential_store_timeout"
    resend_calls = [timeout for _a, ref, timeout in keychain.calls if ref == refs["resend"]]
    assert len(resend_calls) == 2 and resend_calls[0] < 8 <= resend_calls[1]
    status = connect_mod.status_all(repo)
    assert status["credential_backend"]["state"] == "credential_store_timeout"
    assert "not_checked" not in status["summary"]
    exec_read = store_mod.SecretStore("macos-keychain").probe(refs["resend"])
    assert (exec_read.backend_ok, exec_read.reason) == (False, "credential_store_timeout")


def test_a_launched_read_the_helper_gave_up_on_is_a_store_timeout_like_exec(world: Any) -> None:
    repo, refs, keychain = world(["cloudflare"], cost=0.1)
    keychain.modes[refs["cloudflare"]] = "not-checked"

    provider = _by_id(connect_mod.status_all(repo))["cloudflare"]
    assert provider["state"] == connect_mod.BACKEND_FAILURE_STATE
    exec_read = store_mod.SecretStore("macos-keychain").probe(refs["cloudflare"])
    assert exec_read.reason == "credential_store_timeout"


def test_a_clipped_read_the_helper_gave_up_on_is_read_again_then_a_store_timeout(
    world: Any,
) -> None:
    repo, refs, keychain = _clipped_pair(world)
    keychain.modes[refs["resend"]] = "not-checked"

    resend = _by_id(connect_mod.status_all(repo))["resend"]
    assert resend["state"] == connect_mod.BACKEND_FAILURE_STATE
    assert len([call for call in keychain.calls if call[1] == refs["resend"]]) == 2


def test_a_clipped_read_reads_ready_on_the_retry(world: Any) -> None:
    repo, refs, keychain = _clipped_pair(world)
    keychain.costs[refs["resend"]] = 6.0

    status = connect_mod.status_all(repo)
    assert {item["provider"]: item["state"] for item in status["providers"]} == {
        "cloudflare": "unvalidated",
        "resend": "unvalidated",
    }
    assert status["credential_backend"]["state"] == "ready"


def test_a_started_dialog_wait_on_a_clipped_read_is_pending(world: Any) -> None:
    repo, refs, keychain = _clipped_pair(world)
    keychain.modes[refs["resend"]] = "prompt-pending"

    resend = _by_id(connect_mod.status_all(repo))["resend"]
    assert next(iter(resend["secrets"].values()))["backend_state"] == "keychain_prompt_pending"
    assert resend["state"] == connect_mod.BACKEND_FAILURE_STATE

    # A cut-short call that only looked like a dialog reads ready on the retry.
    keychain.modes.pop(refs["resend"])
    keychain.pending_first.add(refs["resend"])
    assert _by_id(connect_mod.status_all(repo))["resend"]["state"] == "unvalidated"


def test_the_retry_spends_the_budget_so_later_providers_are_not_checked(world: Any) -> None:
    repo, refs, keychain = world(["cloudflare", "resend", "orbit-books"], cost=0.1)
    keychain.costs[refs["cloudflare"]] = 2.5
    keychain.costs[refs["resend"]] = 999.0

    states = {item["provider"]: item["state"] for item in connect_mod.status_all(repo)["providers"]}
    assert states["resend"] == connect_mod.BACKEND_FAILURE_STATE
    assert states["orbit-books"] == "credential_not_checked"
    assert not [call for call in keychain.calls if call[1] == refs["orbit-books"]]


def test_a_wedged_store_is_still_reported_as_a_store_failure(
    world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read that had essentially its whole time and hung is the store's answer."""

    repo, _refs, keychain = world(IDS, cost=60.0)

    status = connect_mod.status_all(repo)
    states = {item["state"] for item in status["providers"]}
    first = _by_id(status)[IDS[0]]

    assert first["state"] == connect_mod.BACKEND_FAILURE_STATE
    assert next(iter(first["secrets"].values()))["backend_state"] == "credential_store_timeout"
    assert states <= {connect_mod.BACKEND_FAILURE_STATE, "credential_not_checked"}
    assert status["credential_backend"]["state"] == "credential_store_timeout"
    assert status["credential_backend"]["ok"] is False
    assert connect_mod.doctor_check(repo, status=status)["severity"] == "warn"
    result = runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"])
    assert result.exit_code == 1
    assert [call for call in keychain.calls if call[0] != "get"] == []
