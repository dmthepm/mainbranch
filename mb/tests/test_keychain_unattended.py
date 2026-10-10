"""No unattended credential read may wait on a macOS keychain dialog (#1005).

Unit tests run everywhere. The integration test runs only on macOS with
``MB_KEYCHAIN_INTEGRATION=1``; it creates a throwaway keychain under the temp
directory, never touches the login keychain, and leaves the user keychain
search list exactly as it found it.
"""

from __future__ import annotations

import ast
import ctypes
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import sysconfig
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from mb import _credential_helper as helper_mod
from mb import connect as connect_mod
from mb import credential_store as store_mod
from mb import fleet as fleet_mod

MB_PACKAGE = Path(connect_mod.__file__).resolve().parent


def _popen_running(run: Any) -> Any:
    """A ``subprocess.Popen`` stand-in that answers through a ``run``-style fake."""

    class FakePopen:
        def __init__(self, args: list[str], **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs
            self.pid = None
            self.returncode: int | None = None

        def communicate(self, input: str | None = None, timeout: float | None = None) -> Any:
            result = run(
                self.args,
                input=input,
                timeout=timeout,
                stdout=self.kwargs.get("stdout"),
                stderr=self.kwargs.get("stderr"),
                text=True,
                start_new_session=self.kwargs.get("start_new_session"),
            )
            self.returncode = result.returncode
            return result.stdout, None

        def kill(self) -> None:
            pass

    return FakePopen


def _fake_subprocess(run: Any) -> SimpleNamespace:
    return SimpleNamespace(
        run=run,
        Popen=_popen_running(run),
        PIPE=subprocess.PIPE,
        DEVNULL=subprocess.DEVNULL,
        TimeoutExpired=subprocess.TimeoutExpired,
        SubprocessError=subprocess.SubprocessError,
    )


def _keychain_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo whose Cloudflare and Resend refs are recorded in the macOS Keychain."""

    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    repo = tmp_path / "business"
    repo.mkdir()
    connect_mod.connect_provider(
        "cloudflare", repo, token="fixture-cloudflare", metadata_pairs=["account_id=acct-1"]
    )
    connect_mod.connect_provider("resend", repo, token="re_fixture")
    path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    for provider, field in (("cloudflare", "api_token"), ("resend", "api_key")):
        config["providers"][provider]["secrets"][field]["backend"] = "macos-keychain"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "macos-keychain")
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]
    return repo


class _RecordingHelper:
    """Stands in for the helper subprocess and records every payload."""

    def __init__(self, get_state: str = "ready", *, always_allow: bool = True) -> None:
        self.get_state = get_state
        # Always Allow trusts this Python from then on; Allow passes one read.
        self.always_allow = always_allow
        self.trusted: set[str] = set()
        self.calls: list[dict[str, Any]] = []

    def run(self, args: list[str], **kwargs: Any) -> SimpleNamespace:
        action = args[-1]
        payload = json.loads(kwargs["input"])
        self.calls.append({"action": action, "payload": payload, "timeout": kwargs["timeout"]})
        if action == "get":
            state = self.get_state
            if payload["ref"] in self.trusted:
                state = "ready"
            if state == "prompt-pending" and payload.get("interactive") is True:
                state = "ready"
                if self.always_allow:
                    self.trusted.add(payload["ref"])
            if state == "ready":
                return SimpleNamespace(
                    returncode=0,
                    stdout='{"state":"ready","value":"fixture","owner":"security"}',
                )
            return SimpleNamespace(returncode=1, stdout=json.dumps({"state": state}))
        return SimpleNamespace(returncode=0, stdout='{"state":"ready"}')

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(store_mod, "subprocess", _fake_subprocess(self.run))


def test_every_unattended_caller_reads_with_interaction_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _keychain_repo(tmp_path, monkeypatch)
    helper = _RecordingHelper()
    helper.install(monkeypatch)
    monkeypatch.setattr(
        connect_mod,
        "_validate_with_provider",
        lambda provider, secret, metadata=None, **kwargs: {
            "ok": True,
            "state": "ready",
            "checked_at": "2026-01-01T00:00:00Z",
            "provider_verified": True,
            "summary": "fixture",
        },
    )

    connect_mod.connect_provider("resend", repo, token="re_rotated")
    connect_mod.status_provider("cloudflare", repo)
    connect_mod.status_all(repo)
    connect_mod.test_provider("cloudflare", repo)
    connect_mod.read_token("cloudflare", repo)
    connect_mod.exec_with_secret(
        "cloudflare",
        ["true"],
        repo,
        runner=lambda *args, **kwargs: subprocess.CompletedProcess(args, 0),
    )
    connect_mod.doctor(repo)
    token, account_id, error = fleet_mod._cloudflare_credentials("cloudflare", repo, "hub-a")

    assert (token, account_id, error) == ("fixture", "acct-1", "")
    actions = {call["action"] for call in helper.calls}
    assert {"get", "set"} <= actions
    for call in helper.calls:
        assert call["payload"]["interactive"] is False, call["action"]
        assert call["timeout"] <= store_mod.CREDENTIAL_HELPER_TIMEOUT_SECONDS


# Calls that carry `interactive` into the keychain helper.
CREDENTIAL_CALLS = {
    "_run_helper",
    "set",
    "probe",
    "_probe_secret_ref",
    "repair_keychain",
    "repair_keychain_all",
    "_repair_keychain_ref",
    "_MacSecurity",
}


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def _is_repair_branch(node: ast.AST) -> bool:
    """True only for the exact ``if target == "repair":`` branch of ``mb connect``."""

    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "target"
        and len(node.test.ops) == 1
        and isinstance(node.test.ops[0], ast.Eq)
        and len(node.test.comparators) == 1
        and isinstance(node.test.comparators[0], ast.Constant)
        and node.test.comparators[0].value == "repair"
    )


def _keywords_in(tree: ast.AST, filename: str) -> list[tuple[str, str, ast.expr, bool]]:
    """Every ``interactive=`` keyword passed into the credential path in one module.

    Returned as (file, function, value, in_repair_branch).
    """

    found: list[tuple[str, str, ast.expr, bool]] = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        repair_calls: set[int] = set()
        for node in ast.walk(function):
            if _is_repair_branch(node):
                for inner in node.body:  # type: ignore[attr-defined]
                    repair_calls.update(id(call) for call in ast.walk(inner))
        for call in ast.walk(function):
            if not isinstance(call, ast.Call) or _call_name(call) not in CREDENTIAL_CALLS:
                continue
            for keyword in call.keywords:
                if keyword.arg == "interactive":
                    found.append((filename, function.name, keyword.value, id(call) in repair_calls))
    return found


def _interactive_keywords() -> list[tuple[str, str, ast.expr, bool]]:
    found: list[tuple[str, str, ast.expr, bool]] = []
    for path in sorted(MB_PACKAGE.rglob("*.py")):
        found.extend(_keywords_in(ast.parse(path.read_text(encoding="utf-8")), path.name))
    return found


def _forwards_false_default(path: str, function: str) -> bool:
    tree = ast.parse((MB_PACKAGE / path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function:
            for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
                if arg.arg == "interactive":
                    return isinstance(default, ast.Constant) and default.value is False
    return False


def _guard_offenders(
    keywords: list[tuple[str, str, ast.expr, bool]],
) -> tuple[list[str], list[str]]:
    """Apply the interactive guard; return (offenders, literal-True sites)."""

    offenders: list[str] = []
    literal_true: list[str] = []
    for path, function, value, in_repair_branch in keywords:
        where = f"{path}:{function}"
        if isinstance(value, ast.Constant) and value.value is False:
            continue
        if isinstance(value, ast.Constant) and value.value is True:
            literal_true.append(where)
            if where == "connect.py:_repair_keychain_ref" or (
                where == "cli.py:connect_cmd" and in_repair_branch
            ):
                continue
        elif isinstance(value, ast.Name) and value.id == "interactive":
            if _forwards_false_default(path, function):
                continue
        elif where == "_credential_helper.py:_macos" and ast.unparse(value) == (
            "payload.get('interactive') is True"
        ):
            continue
        offenders.append(f"{where}: interactive={ast.unparse(value)}")
    return offenders, literal_true


def test_only_the_keychain_repair_passes_interactive_true() -> None:
    """A source guard: a new interactive caller must be a deliberate choice.

    ``interactive=True`` is allowed only in ``_repair_keychain_ref`` (the one
    per-item path behind ``repair_keychain`` and ``repair_keychain_all``) and in the exact
    ``mb connect repair`` CLI branch. Elsewhere the value must be ``False`` or a
    parameter named ``interactive`` that itself defaults to ``False``. The one
    computed value is the helper reading its payload, which only accepts JSON
    ``true``.
    """

    offenders, literal_true = _guard_offenders(_interactive_keywords())
    assert offenders == []
    assert sorted(set(literal_true)) == ["cli.py:connect_cmd", "connect.py:_repair_keychain_ref"]


@pytest.mark.parametrize(
    ("test", "allowed"),
    [
        ('target == "repair"', True),
        ('target != "repair"', False),
        ('target is "repair"', False),
        ('"repair" == target', False),
        ('target == "test"', False),
        ('target == "repair" == other', False),
    ],
)
def test_guard_accepts_only_the_exact_repair_branch(test: str, allowed: bool) -> None:
    source = (
        "def connect_cmd(target, repo, other):\n"
        f"    if {test}:\n"
        "        connect_mod.repair_keychain(repo, interactive=True)\n"
    )

    offenders, _ = _guard_offenders(_keywords_in(ast.parse(source), "cli.py"))

    assert (offenders == []) is allowed


class _OrderedLibrary:
    """A fake Security/CoreFoundation library that logs calls in order."""

    def __init__(self, log: list[str]) -> None:
        object.__setattr__(self, "_log", log)

    def __getattr__(self, name: str) -> Any:
        log = self._log

        def call(*args: Any) -> int:
            log.append(name)
            if name == "SecKeychainGetStatus":
                args[1]._obj.value = helper_mod.KEYCHAIN_UNLOCKED_STATUS
                return 0
            if name in {"SecKeychainSetUserInteractionAllowed", "SecKeychainCopyDefault"}:
                return 0
            return 1

        fn: Any = call
        object.__setattr__(self, name, fn)
        return fn


@pytest.mark.parametrize("action", ["health", "get", "set", "delete"])
def test_helper_disables_interaction_before_any_keychain_call(
    monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    monkeypatch.delenv(helper_mod.TEST_KEYCHAIN_ENV, raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    log: list[str] = []
    monkeypatch.setattr(ctypes, "CDLL", lambda path: _OrderedLibrary(log))
    monkeypatch.setattr(helper_mod._MacSecurity, "_constant", staticmethod(lambda lib, name: 1))

    helper_mod._macos(action, {"ref": "fixture-ref", "value": "fixture"})

    keychain_calls = [
        index
        for index, name in enumerate(log)
        if name.startswith(("SecKeychain", "SecItem"))
        and name != "SecKeychainSetUserInteractionAllowed"
    ]
    assert keychain_calls, log
    assert log.index("SecKeychainSetUserInteractionAllowed") < keychain_calls[0]
    if action != "health":
        assert any(name.startswith("SecItem") for name in log), log


def test_denied_read_on_unlocked_keychain_is_prompt_pending() -> None:
    assert (
        helper_mod._denied_state(helper_mod.ERR_SEC_AUTH_FAILED, health="ready") == "prompt-pending"
    )
    assert (
        helper_mod._denied_state(helper_mod.ERR_SEC_INTERACTION_NOT_ALLOWED, health="ready")
        == "prompt-pending"
    )
    assert helper_mod._denied_state(helper_mod.ERR_SEC_ITEM_NOT_FOUND, health="ready") == "missing"
    assert (
        helper_mod._denied_state(helper_mod.ERR_SEC_AUTH_FAILED, health="locked") == "auth-failed"
    )


def test_adapter_get_checks_lock_first_and_never_reads_a_locked_keychain() -> None:
    reads: list[int] = []
    adapter: Any = object.__new__(helper_mod._MacSecurity)
    adapter.health = lambda: "locked"

    def query(ref: str, return_data: bool = False) -> tuple[int, list[int]]:
        reads.append(1)
        return 0, []

    adapter._query = query

    assert adapter.get("fixture-ref") == ("locked", None)
    assert reads == []


def test_adapter_get_maps_untrusted_read_to_prompt_pending() -> None:
    adapter: Any = object.__new__(helper_mod._MacSecurity)
    adapter.health = lambda: "ready"
    adapter._item_owner = lambda ref: "legacy"
    adapter._query = lambda ref, **kwargs: (7, [])
    adapter._release_all = lambda values: None
    adapter.security = SimpleNamespace(
        SecItemCopyMatching=lambda query, result: helper_mod.ERR_SEC_AUTH_FAILED
    )
    adapter.core = SimpleNamespace(CFRelease=lambda value: None)

    assert adapter.get("fixture-ref") == ("prompt-pending", None)


def _present_then_not_found_adapter(
    owner: str, *, owners_after: list[str]
) -> tuple[Any, list[str]]:
    """An adapter whose existence check finds the item but whose data read says not found.

    ``owners_after`` are the answers to any further existence checks, in order.
    """

    answers = [owner, *owners_after]
    checks: list[str] = []

    def item_owner(ref: str) -> str:
        checks.append(ref)
        return answers[min(len(checks) - 1, len(answers) - 1)]

    adapter: Any = object.__new__(helper_mod._MacSecurity)
    adapter.health = lambda: "ready"
    adapter._recover = lambda ref: None
    adapter._item_owner = item_owner
    adapter._query = lambda ref, **kwargs: (7, [])
    adapter._release_all = lambda values: None
    adapter.security = SimpleNamespace(
        SecItemCopyMatching=lambda query, result: helper_mod.ERR_SEC_ITEM_NOT_FOUND
    )
    adapter.core = SimpleNamespace(CFRelease=lambda value: None)
    adapter._security_get = lambda ref: ("missing", None)
    adapter.stage_kind = "absent"
    adapter.owner = ""
    adapter.migrated = False
    return adapter, checks


@pytest.mark.parametrize("owner", ["legacy", "security"])
def test_an_item_found_but_refused_on_read_is_never_missing(owner: str) -> None:
    # The existence check found the item; a "not found" from the data read is a
    # refusal (#1150), so it reads as a pending prompt, never as missing.
    adapter, checks = _present_then_not_found_adapter(owner, owners_after=[owner])

    assert adapter.get("fixture-ref") == ("prompt-pending", None)
    assert len(checks) == 2


@pytest.mark.parametrize("owner", ["legacy", "security"])
def test_an_item_gone_between_the_two_reads_is_missing(owner: str) -> None:
    adapter, _checks = _present_then_not_found_adapter(owner, owners_after=["absent"])

    assert adapter.get("fixture-ref") == ("missing", None)


def test_a_security_item_refused_on_read_is_not_taken_for_absent_by_recovery() -> None:
    # `_recover` rewrites an absent item from its staged copy; a refused read
    # must not look absent to it.
    adapter, _checks = _present_then_not_found_adapter("security", owners_after=["security"])

    assert adapter._main_state("fixture-ref") == ("unreadable", None, "prompt-pending")


class _FakeLibrary:
    """Accepts ctypes argtypes/restype assignments and records calls."""

    def __init__(self, log: list[tuple[str, tuple[Any, ...]]]) -> None:
        object.__setattr__(self, "_log", log)

    def __getattr__(self, name: str) -> Any:
        log = self._log

        def call(*args: Any) -> int:
            log.append((name, args))
            return 0

        fn: Any = call
        object.__setattr__(self, name, fn)
        return fn


@pytest.mark.parametrize(("interactive", "disabled"), [(False, True), (True, False)])
def test_adapter_disables_interaction_unless_explicitly_interactive(
    monkeypatch: pytest.MonkeyPatch, interactive: bool, disabled: bool
) -> None:
    monkeypatch.delenv(helper_mod.TEST_KEYCHAIN_ENV, raising=False)
    log: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(ctypes, "CDLL", lambda path: _FakeLibrary(log))

    helper_mod._MacSecurity(interactive=interactive)

    assert (("SecKeychainSetUserInteractionAllowed", (False,)) in log) is disabled


def test_helper_payload_without_explicit_true_stays_non_interactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[bool] = []

    class Adapter:
        def __init__(self, *, interactive: bool = False, **kwargs: Any) -> None:
            seen.append(interactive)

        def health(self) -> str:
            return "ready"

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(helper_mod, "_MacSecurity", Adapter)
    for payload in ({}, {"interactive": "true"}, {"interactive": 1}, {"interactive": True}):
        helper_mod._macos("health", payload)

    assert seen == [False, False, False, True]


def test_prompt_pending_fails_fast_with_named_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _keychain_repo(tmp_path, monkeypatch)
    _RecordingHelper(get_state="prompt-pending").install(monkeypatch)

    started = time.monotonic()
    status = connect_mod.status_provider("cloudflare", repo)
    token = connect_mod.read_token("cloudflare", repo)
    elapsed = time.monotonic() - started

    assert elapsed < 1.0
    assert status["state"] == connect_mod.BACKEND_FAILURE_STATE
    assert status["secrets"]["api_token"]["backend_state"] == "keychain_prompt_pending"
    assert "Cloudflare" in status["summary"]
    assert "keychain prompt pending" in status["summary"]
    assert status["repair_command"] == "mb connect repair --keychain"
    assert "mb connect repair --keychain" in status["repair"]
    assert "timeout" not in status["summary"].lower()
    assert token["error"] == "Cloudflare credential: keychain prompt pending"
    assert token["repair_command"] == "mb connect repair --keychain"


def test_fleet_warning_names_hub_provider_and_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _keychain_repo(tmp_path, monkeypatch)
    _RecordingHelper(get_state="prompt-pending").install(monkeypatch)

    _, _, error = fleet_mod._cloudflare_credentials("cloudflare", repo, "hub-a")

    assert error == (
        "cloudflare connection 'cloudflare': keychain prompt pending; "
        "run mb connect repair --keychain in hub-a"
    )


def test_keychain_repair_asks_only_for_pending_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _keychain_repo(tmp_path, monkeypatch)
    helper = _RecordingHelper(get_state="prompt-pending")
    helper.install(monkeypatch)

    result = connect_mod.repair_keychain(repo, interactive=True)

    assert result["ok"] is True
    assert [(item["provider"], item["state"]) for item in result["items"]] == [
        ("cloudflare", "repaired"),
        ("resend", "repaired"),
    ]
    interactive = [call for call in helper.calls if call["payload"]["interactive"]]
    assert len(interactive) == 2
    assert all(
        call["timeout"] == store_mod.INTERACTIVE_CREDENTIAL_TIMEOUT_SECONDS for call in interactive
    )
    assert "fixture" not in json.dumps(result)


def test_keychain_repair_after_allow_once_is_still_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _keychain_repo(tmp_path, monkeypatch)
    helper = _RecordingHelper(get_state="prompt-pending", always_allow=False)
    helper.install(monkeypatch)

    result = connect_mod.repair_keychain(repo, interactive=True)

    assert result["ok"] is False
    assert [item["state"] for item in result["items"]] == ["still_pending", "still_pending"]
    assert all("Always Allow" in item["summary"] for item in result["items"])
    assert result["repair_command"] == "mb connect repair --keychain"
    # Each item: unattended probe, interactive read, fresh unattended verify.
    assert [call["payload"]["interactive"] for call in helper.calls] == [
        False,
        True,
        False,
    ] * 2


def test_prompt_pending_repair_text_says_always_allow() -> None:
    assert "Always Allow" in store_mod.backend_repair("keychain_prompt_pending")["repair"]


def test_keychain_repair_without_consent_never_asks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _keychain_repo(tmp_path, monkeypatch)
    helper = _RecordingHelper(get_state="prompt-pending")
    helper.install(monkeypatch)

    result = connect_mod.repair_keychain(repo)

    assert result["ok"] is False
    assert result["pending"] == 2
    assert all(call["payload"]["interactive"] is False for call in helper.calls)


def test_cli_keychain_repair_refuses_without_a_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from mb.cli import app

    repo = _keychain_repo(tmp_path, monkeypatch)
    helper = _RecordingHelper(get_state="prompt-pending")
    helper.install(monkeypatch)

    result = CliRunner().invoke(app, ["connect", "repair", "--keychain", "--repo", str(repo)])
    assert result.exit_code == 2
    assert "terminal" in result.stderr
    assert helper.calls == []

    missing_flag = CliRunner().invoke(app, ["connect", "repair", "--repo", str(repo)])
    assert missing_flag.exit_code == 2
    assert helper.calls == []


def test_keychain_listing_asks_for_attributes_never_data() -> None:
    """The ``--all`` enumeration cannot decrypt a value, so it has nothing to ask about."""

    pairs: list[tuple[Any, Any]] = []
    adapter: Any = object.__new__(helper_mod._MacSecurity)
    adapter.search_list = None
    adapter._constant = lambda library, name: name
    adapter._string = lambda value: f"str:{value}"

    def dictionary(items: list[tuple[Any, Any]]) -> int:
        pairs.extend(items)
        return 1

    adapter._dictionary = dictionary
    adapter.security = SimpleNamespace(
        SecItemCopyMatching=lambda query, result: helper_mod.ERR_SEC_ITEM_NOT_FOUND
    )
    adapter.core = SimpleNamespace(CFRelease=lambda value: None)

    assert adapter._ctypes_accounts() == ("ready", [])
    query = dict(pairs)
    assert query["kSecReturnAttributes"] == "kCFBooleanTrue"
    assert "kSecReturnData" not in query
    assert "kSecReturnRef" not in query
    assert query["kSecAttrService"] == f"str:{helper_mod.SERVICE_NAME}"
    assert query["kSecMatchLimit"] == "kSecMatchLimitAll"
    assert query["kSecUseAuthenticationUI"] == "kSecUseAuthenticationUIFail"


def test_keychain_listing_is_never_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[bool] = []

    class Adapter:
        def __init__(self, *, interactive: bool = False, **kwargs: Any) -> None:
            seen.append(interactive)

        def list_refs(self) -> tuple[str, list[str], int]:
            return "ready", [], 0

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(helper_mod, "_MacSecurity", Adapter)

    assert helper_mod._macos_list({"interactive": True}) == ("ready", [], 0)
    assert seen == [False]


def test_keychain_listing_checks_the_lock_and_keeps_only_mb_refs() -> None:
    listed: list[int] = []
    adapter: Any = object.__new__(helper_mod._MacSecurity)
    adapter.health = lambda: "locked"

    def accounts() -> tuple[str, list[str]]:
        listed.append(1)
        return "ready", ["mainbranch://b/x/y", "mainbranch://a/x/y", 'bad "ref', "a.mbstage"]

    adapter._ctypes_accounts = accounts
    assert adapter.list_refs() == ("locked", [], 0)
    assert listed == []

    adapter.health = lambda: "ready"
    assert adapter.list_refs() == (
        "ready",
        ["a.mbstage", "mainbranch://a/x/y", "mainbranch://b/x/y"],
        3,
    )


def _listing_json(refs: list[str]) -> str:
    """A complete ``list`` response in the current helper protocol."""

    return json.dumps(
        {"state": "ready", "refs": refs, "found": len(refs), "limit": helper_mod.LIST_LIMIT}
    )


def _fake_refs(count: int) -> list[str]:
    return [f"mainbranch://{index:024x}/stripe/api_key" for index in range(count)]


def test_keychain_listing_past_the_cap_says_it_was_cut(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """2001 refs: the helper returns the first 2000 and says it found 2001 (P2 on #1013)."""

    refs = _fake_refs(helper_mod.LIST_LIMIT + 1)

    class Adapter:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def health(self) -> str:
            return "ready"

        def _ctypes_accounts(self) -> tuple[str, list[str]]:
            return "ready", list(reversed(refs))

        list_refs = helper_mod._MacSecurity.list_refs

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(helper_mod, "_MacSecurity", Adapter)
    monkeypatch.setattr(sys, "argv", ["helper", "macos-keychain", "list"])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(read=lambda size: "{}"))

    assert helper_mod.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["refs"] == refs[: helper_mod.LIST_LIMIT]
    assert (out["truncated"], out["limit"], out["found"]) == (True, 2000, 2001)
    assert "value" not in out

    # Exactly at the cap is complete, and still says what it found.
    refs = _fake_refs(helper_mod.LIST_LIMIT)
    assert helper_mod.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"state", "refs", "found", "limit"}
    assert len(out["refs"]) == out["found"] == helper_mod.LIST_LIMIT


def test_keychain_listing_is_macos_only(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setattr(sys, "argv", ["helper", "secret-service", "list"])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(read=lambda size: "{}"))

    assert helper_mod.main() == 1
    assert json.loads(capsys.readouterr().out) == {"state": "unavailable"}


class _FakeKeychainHelper:
    """The helper subprocess over an in-memory keychain of mb refs, for ``--all``.

    ``items`` maps a ref to its state: ``security`` (owned by security,
    readable), ``legacy`` (this Python reads it but cannot move it),
    ``pending`` (needs Always Allow; the answered read moves it), ``once``
    (Allow only: the answered read works, unattended reads stay pending) or
    ``staged`` (only its staged copy survives; any read recovers it).
    """

    def __init__(self, items: dict[str, str]) -> None:
        self.items = dict(items)
        self.calls: list[dict[str, Any]] = []

    def run(self, args: list[str], **kwargs: Any) -> SimpleNamespace:
        action = args[-1]
        payload = json.loads(kwargs["input"])
        self.calls.append({"action": action, "payload": payload})
        if action == "list":
            refs = sorted(
                ref + helper_mod.STAGE_SUFFIX if kind == "staged" else ref
                for ref, kind in self.items.items()
            )
            return SimpleNamespace(returncode=0, stdout=_listing_json(refs))
        assert action == "get"
        ref: str = payload["ref"]
        assert not ref.endswith(helper_mod.STAGE_SUFFIX), "a staged copy is never read directly"
        kind = self.items.get(ref)
        if kind is None:
            return SimpleNamespace(returncode=0, stdout='{"state":"missing"}')
        ready = '{"state":"ready","value":"fixture","owner":"%s"}'
        if kind == "staged":
            self.items[ref] = "security"
            return SimpleNamespace(
                returncode=0,
                stdout='{"state":"ready","value":"fixture","migrated":true,"owner":"security"}',
            )
        if kind == "security":
            return SimpleNamespace(returncode=0, stdout=ready % "security")
        if kind == "legacy":
            return SimpleNamespace(returncode=0, stdout=ready % "legacy")
        if payload["interactive"] is True:
            if kind == "pending":
                self.items[ref] = "security"
            return SimpleNamespace(returncode=0, stdout=ready % "legacy")
        return SimpleNamespace(returncode=1, stdout='{"state":"prompt-pending"}')

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(store_mod, "subprocess", _fake_subprocess(self.run))


def _recorded_refs(repo: Path) -> dict[str, str]:
    return {
        f"{provider}.{field}": ref
        for provider, field, ref in connect_mod._recorded_keychain_refs(repo)
    }


def test_keychain_repair_all_repairs_every_item_in_one_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    hub_b = _keychain_repo(tmp_path / "b", monkeypatch)
    hub_a = _keychain_repo(tmp_path / "a", monkeypatch)
    fleet_file = tmp_path / "config" / "mainbranch" / "fleet.toml"
    fleet_file.parent.mkdir(parents=True)
    fleet_file.write_text(
        f'[[hubs]]\nname = "hub-b"\nremote = "github:example-co/hub-b"\ncheckout = "{hub_b}"\n',
        encoding="utf-8",
    )
    a, b = _recorded_refs(hub_a), _recorded_refs(hub_b)
    unknown = "mainbranch://ffffffffffffffffffffffff/stripe/api_key"
    helper = _FakeKeychainHelper(
        {
            a["cloudflare.api_token"]: "security",
            a["resend.api_key"]: "pending",
            b["cloudflare.api_token"]: "once",
            b["resend.api_key"]: "legacy",
            unknown: "staged",
        }
    )
    helper.install(monkeypatch)

    result = connect_mod.repair_keychain_all(hub_a, interactive=True)

    by_ref = {item["ref"]: item for item in result["items"]}
    assert set(by_ref) == {*a.values(), *b.values(), unknown}
    assert by_ref[a["cloudflare.api_token"]]["state"] == "ready"
    assert by_ref[a["resend.api_key"]]["state"] == "repaired"
    assert by_ref[b["cloudflare.api_token"]]["state"] == "still_pending"
    assert by_ref[b["resend.api_key"]]["state"] == "readable_not_migrated"
    assert by_ref[unknown]["state"] == "ready"
    assert by_ref[unknown]["migrated"] is True
    assert by_ref[unknown]["staged_only"] is True
    # Labelled by hub where a hub records the ref, by the ref otherwise.
    assert {by_ref[ref]["hub"] for ref in a.values()} == {hub_a.name}
    # `mb fleet` reads fleet.toml with tomllib (Python 3.11+); on 3.10 the hub
    # list adds nothing and hub-b's items are shown by their refs.
    fleet_readable = sys.version_info >= (3, 11)
    assert {by_ref[ref]["hub"] for ref in b.values()} == {"hub-b" if fleet_readable else ""}
    assert (by_ref[unknown]["hub"], by_ref[unknown]["provider"]) == ("", "stripe")
    assert by_ref[b["resend.api_key"]]["provider"] == "resend"
    # One summary for the machine.
    assert result["total"] == 5
    assert result["counts"] == {
        "readable_not_migrated": 1,
        "ready": 2,
        "repaired": 1,
        "still_pending": 1,
    }
    assert result["pending"] == 2
    assert result["unmapped"] == (1 if fleet_readable else 3)
    assert result["ok"] is False
    assert result["repair_command"] == "mb connect repair --keychain --all"
    assert all("--all" in item["summary"] for item in result["items"] if "again" in item["summary"])
    # One attribute-only listing, never interactive; dialogs only for pending items.
    assert [call["action"] for call in helper.calls].count("list") == 1
    assert helper.calls[0]["action"] == "list"
    assert helper.calls[0]["payload"]["interactive"] is False
    interactive = sorted(
        call["payload"]["ref"] for call in helper.calls if call["payload"]["interactive"]
    )
    assert interactive == sorted([a["resend.api_key"], b["cloudflare.api_token"]])
    assert "fixture" not in json.dumps(result)


def test_keychain_repair_all_past_the_cap_is_never_a_clean_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from mb import cli as cli_mod
    from mb.cli import app

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    repo = _keychain_repo(tmp_path, monkeypatch)
    refs = _fake_refs(helper_mod.LIST_LIMIT + 1)
    helper = _FakeKeychainHelper(dict.fromkeys(refs[: helper_mod.LIST_LIMIT], "security"))
    original = helper.run

    def run(args: list[str], **kwargs: Any) -> SimpleNamespace:
        if args[-1] != "list":
            return original(args, **kwargs)
        helper.calls.append({"action": "list", "payload": json.loads(kwargs["input"])})
        listing = {
            "state": "ready",
            "refs": refs[: helper_mod.LIST_LIMIT],
            "truncated": True,
            "limit": helper_mod.LIST_LIMIT,
            "found": len(refs),
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(listing))

    monkeypatch.setattr(store_mod, "subprocess", _fake_subprocess(run))

    result = connect_mod.repair_keychain_all(repo, interactive=True)

    # Every listed item is fine, yet the pass is incomplete, not ok.
    assert result["counts"] == {"ready": helper_mod.LIST_LIMIT}
    assert result["pending"] == 0
    assert result["ok"] is False
    assert result["complete"] is False
    assert (result["listed"], result["unlisted"], result["list_limit"]) == (2000, 1, 2000)
    assert result["repair_command"] == "mb connect repair --keychain"

    class _TerminalSys:
        stdin = SimpleNamespace(isatty=lambda: True)

        def __getattr__(self, name: str) -> Any:
            return getattr(sys, name)

    monkeypatch.setattr(cli_mod, "sys", _TerminalSys())
    cli = CliRunner().invoke(app, ["connect", "repair", "--keychain", "--all", "--repo", str(repo)])

    assert cli.exit_code == 1
    assert "incomplete:" in cli.stdout
    assert "2000 listed, 1 not checked" in cli.stdout
    assert "next: run `mb connect repair --keychain`" in cli.stdout


def _repair_all_from_listing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, listing_stdout: str
) -> tuple[dict[str, Any], Any]:
    """Run ``repair_keychain_all`` and the CLI on one raw ``list`` response."""

    from typer.testing import CliRunner

    from mb import cli as cli_mod
    from mb.cli import app

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    repo = _keychain_repo(tmp_path, monkeypatch)
    listed = json.loads(listing_stdout)["refs"]
    helper = _FakeKeychainHelper(dict.fromkeys(listed, "security"))
    original = helper.run

    def run(args: list[str], **kwargs: Any) -> SimpleNamespace:
        if args[-1] == "list":
            return SimpleNamespace(returncode=0, stdout=listing_stdout)
        return original(args, **kwargs)

    monkeypatch.setattr(store_mod, "subprocess", _fake_subprocess(run))
    result = connect_mod.repair_keychain_all(repo, interactive=True)

    class _TerminalSys:
        stdin = SimpleNamespace(isatty=lambda: True)

        def __getattr__(self, name: str) -> Any:
            return getattr(sys, name)

    monkeypatch.setattr(cli_mod, "sys", _TerminalSys())
    cli = CliRunner().invoke(app, ["connect", "repair", "--keychain", "--all", "--repo", str(repo)])
    return result, cli


@pytest.mark.parametrize(
    "extra",
    [
        {},  # a helper from before the protocol: no `found`, no `truncated`
        {"found": True},
        {"found": "2001"},
        {"found": 3},  # fewer than it returned
        {"truncated": True},
        {"found": 5, "truncated": True},
    ],
    ids=["no-found", "bool-found", "str-found", "found-too-small", "flag-only", "flag-and-equal"],
)
def test_keychain_repair_all_accepts_only_a_proven_whole_listing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra: dict[str, Any]
) -> None:
    refs = _fake_refs(5)
    stdout = json.dumps({"state": "ready", "refs": refs, **extra})

    result, cli = _repair_all_from_listing(tmp_path, monkeypatch, stdout)

    assert result["counts"] == {"ready": 5}
    assert result["pending"] == 0
    assert (result["ok"], result["complete"]) == (False, False)
    assert result["repair_command"] == "mb connect repair --keychain"
    assert cli.exit_code == 1
    assert "incomplete:" in cli.stdout


def _base_helper_module(tmp_path: Path) -> Any:
    """The 3759fc4 helper (before the list protocol), loaded as its own module."""

    import importlib.util

    root = MB_PACKAGE.parent.parent
    shown = subprocess.run(
        ["git", "-C", str(root), "show", "3759fc4:mb/mb/_credential_helper.py"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if shown.returncode != 0:
        pytest.skip("commit 3759fc4 is not in this checkout (shallow clone)")
    path = tmp_path / "base_credential_helper.py"
    path.write_text(shown.stdout, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("base_credential_helper", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_keychain_repair_all_with_an_older_helper_past_its_cap_is_not_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """Mixed versions: the 3759fc4 helper caps 2001 refs at 2000 without saying so."""

    base = _base_helper_module(tmp_path)
    refs = _fake_refs(base.LIST_LIMIT + 1)

    class Adapter:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def health(self) -> str:
            return "ready"

        def _ctypes_accounts(self) -> tuple[str, list[str]]:
            return "ready", refs

        list_refs = base._MacSecurity.list_refs

    monkeypatch.setattr(base.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(base, "_MacSecurity", Adapter)
    monkeypatch.setattr(sys, "argv", ["helper", "macos-keychain", "list"])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(read=lambda size: "{}"))
    assert base.main() == 0
    stdout = capsys.readouterr().out
    assert set(json.loads(stdout)) == {"state", "refs"}  # the old protocol
    assert len(json.loads(stdout)["refs"]) == 2000

    result, cli = _repair_all_from_listing(tmp_path, monkeypatch, stdout)

    assert result["counts"] == {"ready": 2000}
    assert (result["ok"], result["complete"], result["unlisted"]) == (False, False, None)
    assert cli.exit_code == 1
    assert "did not say whether it is complete" in cli.stdout


def test_a_full_listing_of_the_longest_refs_fits_the_output_limit(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """2000 refs of the longest accepted shape still fit under HELPER_OUTPUT_LIMIT."""

    longest = [f"{index:04d}" + "x" * 508 for index in range(helper_mod.LIST_LIMIT)]
    assert all(helper_mod._SAFE_REF.fullmatch(ref) for ref in longest)
    assert len(longest[0]) == 512

    helper_mod._emit("ready", refs=longest, found=helper_mod.LIST_LIMIT + 1)
    out = capsys.readouterr().out

    assert len(out) < store_mod.HELPER_OUTPUT_LIMIT
    assert json.loads(out)["truncated"] is True


def test_keychain_repair_all_complete_listing_reports_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    repo = _keychain_repo(tmp_path, monkeypatch)
    _FakeKeychainHelper({"mainbranch://abc/stripe/api_key": "security"}).install(monkeypatch)

    result = connect_mod.repair_keychain_all(repo, interactive=True)

    assert (result["ok"], result["complete"], result["unlisted"]) == (True, True, 0)
    assert result["repair_command"] == ""


def test_keychain_repair_all_skips_a_staged_copy_when_its_item_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    repo = _keychain_repo(tmp_path, monkeypatch)
    ref = _recorded_refs(repo)["cloudflare.api_token"]
    helper = _FakeKeychainHelper({ref: "security"})
    original = helper.run

    def run(args: list[str], **kwargs: Any) -> SimpleNamespace:
        if args[-1] == "list":
            refs = [ref, ref + helper_mod.STAGE_SUFFIX]
            return SimpleNamespace(returncode=0, stdout=_listing_json(refs))
        return original(args, **kwargs)

    monkeypatch.setattr(store_mod, "subprocess", _fake_subprocess(run))

    result = connect_mod.repair_keychain_all(repo, interactive=True)

    assert [(item["ref"], item["staged_only"], item["state"]) for item in result["items"]] == [
        (ref, False, "ready")
    ]
    assert [call["payload"]["ref"] for call in helper.calls] == [ref]
    assert result["ok"] is True
    assert result["repair_command"] == ""


def test_keychain_repair_all_with_an_empty_keychain_is_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    repo = _keychain_repo(tmp_path, monkeypatch)
    helper = _FakeKeychainHelper({})
    helper.install(monkeypatch)

    result = connect_mod.repair_keychain_all(repo, interactive=True)

    assert (result["ok"], result["total"], result["pending"], result["items"]) == (True, 0, 0, [])
    assert [call["action"] for call in helper.calls] == ["list"]


def test_keychain_repair_all_reports_a_keychain_it_cannot_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _keychain_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        store_mod,
        "subprocess",
        _fake_subprocess(
            lambda args, **kwargs: SimpleNamespace(returncode=1, stdout='{"state":"locked"}')
        ),
    )

    with pytest.raises(store_mod.CredentialStoreError) as caught:
        connect_mod.repair_keychain_all(repo, interactive=True)

    assert caught.value.reason == "keychain_locked"


def test_cli_keychain_repair_all_refuses_without_a_terminal_before_any_keychain_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from mb.cli import app

    repo = _keychain_repo(tmp_path, monkeypatch)
    helper = _FakeKeychainHelper({"mainbranch://abc/cloudflare/api_token": "pending"})
    helper.install(monkeypatch)

    result = CliRunner().invoke(
        app, ["connect", "repair", "--keychain", "--all", "--repo", str(repo)]
    )
    assert result.exit_code == 2
    assert "terminal" in result.stderr
    assert helper.calls == []

    without_keychain = CliRunner().invoke(app, ["connect", "repair", "--all", "--repo", str(repo)])
    assert without_keychain.exit_code == 2
    assert helper.calls == []


def test_cli_keychain_repair_all_runs_the_all_items_pass_from_a_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from mb import cli as cli_mod
    from mb.cli import app

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    repo = _keychain_repo(tmp_path, monkeypatch)
    ref = _recorded_refs(repo)["resend.api_key"]
    helper = _FakeKeychainHelper({ref: "pending", "mainbranch://ffff/stripe/api_key": "security"})
    helper.install(monkeypatch)

    class _TerminalSys:
        """``sys`` as the CLI sees it, but with stdin at a terminal."""

        stdin = SimpleNamespace(isatty=lambda: True)

        def __getattr__(self, name: str) -> Any:
            return getattr(sys, name)

    monkeypatch.setattr(cli_mod, "sys", _TerminalSys())

    result = CliRunner().invoke(
        app, ["connect", "repair", "--keychain", "--all", "--repo", str(repo)]
    )

    assert result.exit_code == 0, result.output
    assert "summary: 2 items (1 ready, 1 repaired), 0 pending" in result.stdout
    assert "mainbranch://ffff/stripe/api_key  stripe.api_key: ready" in result.stdout
    assert f"{repo.name}  resend.api_key: repaired" in result.stdout
    assert "fixture" not in result.output


@pytest.mark.parametrize(
    "name",
    ["login.keychain-db", "mbtest-x.keychain", "other.keychain-db"],
)
def test_test_keychain_seam_refuses_anything_but_a_throwaway_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    path = tmp_path / name
    path.write_text("", encoding="utf-8")
    monkeypatch.setenv(helper_mod.TEST_KEYCHAIN_ENV, str(path))

    with pytest.raises(RuntimeError):
        helper_mod._test_keychain_path()


@pytest.mark.parametrize("value", ["", "   "])
def test_test_keychain_seam_refuses_an_empty_value(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(helper_mod.TEST_KEYCHAIN_ENV, value)

    with pytest.raises(RuntimeError):
        helper_mod._test_keychain_path()


def test_test_keychain_seam_absent_means_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(helper_mod.TEST_KEYCHAIN_ENV, raising=False)

    assert helper_mod._test_keychain_path() is None


def test_test_keychain_seam_refuses_a_hard_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Synthetic files under a mocked home only; never the real login keychain.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    keychains = tmp_path / "home" / "Library" / "Keychains"
    keychains.mkdir(parents=True)
    protected = keychains / "login.keychain-db"
    protected.write_text("", encoding="utf-8")
    alias = tmp_path / "mbtest-alias.keychain-db"
    os.link(protected, alias)
    monkeypatch.setenv(helper_mod.TEST_KEYCHAIN_ENV, str(alias))

    with pytest.raises(RuntimeError):
        helper_mod._test_keychain_path()


@pytest.mark.parametrize("target", ["missing", "symlink"])
def test_test_keychain_seam_refuses_missing_files_and_symlinks_into_keychains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    keychains = tmp_path / "home" / "Library" / "Keychains"
    keychains.mkdir(parents=True)
    alias = tmp_path / "mbtest-alias.keychain-db"
    if target == "symlink":
        protected = keychains / "mbtest-login.keychain-db"
        protected.write_text("", encoding="utf-8")
        alias.symlink_to(protected)
    monkeypatch.setenv(helper_mod.TEST_KEYCHAIN_ENV, str(alias))

    with pytest.raises(RuntimeError):
        helper_mod._test_keychain_path()


def test_test_keychain_seam_accepts_a_single_throwaway_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    path = tmp_path / "mbtest-ok.keychain-db"
    path.write_text("", encoding="utf-8")
    monkeypatch.setenv(helper_mod.TEST_KEYCHAIN_ENV, str(path))

    assert helper_mod._test_keychain_path() == str(path.resolve())


def test_test_keychain_seam_refuses_the_user_keychains_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    keychains = tmp_path / "Library" / "Keychains"
    keychains.mkdir(parents=True)
    path = keychains / "mbtest-x.keychain-db"
    path.write_text("", encoding="utf-8")
    monkeypatch.setenv(helper_mod.TEST_KEYCHAIN_ENV, str(path))

    with pytest.raises(RuntimeError):
        helper_mod._test_keychain_path()


# ---------------------------------------------------------------------------
# macOS integration: throwaway keychain only.
# ---------------------------------------------------------------------------

SECURITY = "/usr/bin/security"
integration = pytest.mark.skipif(
    platform.system() != "Darwin" or os.environ.get("MB_KEYCHAIN_INTEGRATION") != "1",
    reason="macOS keychain integration runs only with MB_KEYCHAIN_INTEGRATION=1 on macOS",
)


def _search_list() -> str:
    return subprocess.run(
        [SECURITY, "list-keychains", "-d", "user"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout


@pytest.fixture
def throwaway_keychain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    before = _search_list()
    path = tmp_path / f"mbtest-{secrets.token_hex(4)}.keychain-db"
    password = secrets.token_hex(16)
    try:
        subprocess.run(
            [SECURITY, "create-keychain", "-p", password, str(path)],
            check=True,
            capture_output=True,
            timeout=10,
        )
        # Never leave the throwaway keychain in the user's search list.
        if _search_list() != before:
            listed = [line.strip().strip('"') for line in before.splitlines() if line.strip()]
            subprocess.run(
                [SECURITY, "list-keychains", "-d", "user", "-s", *listed],
                check=True,
                capture_output=True,
                timeout=10,
            )
        subprocess.run(
            [SECURITY, "unlock-keychain", "-p", password, str(path)],
            check=True,
            capture_output=True,
            timeout=10,
        )
        subprocess.run(
            [SECURITY, "set-keychain-settings", str(path)],
            check=True,
            capture_output=True,
            timeout=10,
        )
        monkeypatch.setenv(helper_mod.TEST_KEYCHAIN_ENV, str(path))
        yield path
    finally:
        subprocess.run(
            [SECURITY, "delete-keychain", str(path)], capture_output=True, timeout=10, check=False
        )
        assert _search_list() == before


def _require_seam(path: Path) -> None:
    """Refuse to touch any keychain unless the seam names the throwaway one."""

    # Read only the seam key so a failure never prints the whole environment (#1025).
    seam = os.environ.get(helper_mod.TEST_KEYCHAIN_ENV)
    assert seam == str(path)
    assert helper_mod._test_keychain_path() == str(path.resolve())


def _foreign_python(tmp_path: Path) -> list[str]:
    """An interpreter the keychain sees as a different app (new code hash)."""

    if sysconfig.get_config_var("PYTHONFRAMEWORK"):
        # In a framework build bin/python only launches Python.app, so a
        # re-signed copy of it still runs as the same app to the keychain.
        pytest.skip("framework Python: use a non-framework (for example uv-managed) Python")
    copy = tmp_path / "foreign-python"
    shutil.copy2(Path(sys.executable).resolve(), copy)
    subprocess.run(
        ["/usr/bin/codesign", "--force", "--sign", "-", str(copy)],
        check=True,
        capture_output=True,
        timeout=60,
    )
    subprocess.run(
        [str(copy), "-c", "pass"], env=_helper_env(), check=True, capture_output=True, timeout=60
    )
    return [str(copy)]


def _helper_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONHOME"] = sys.base_prefix
    env["PYTHONPATH"] = str(MB_PACKAGE.parent)
    return env


@integration
def test_macos_item_from_another_python_reports_prompt_pending_fast(
    tmp_path: Path, throwaway_keychain: Path
) -> None:
    _require_seam(throwaway_keychain)
    ref = "mbtest-ref-foreign"
    # The pre-#1005 write path: SecItemAdd from another interpreter.
    _legacy_add(_foreign_python(tmp_path), ref, "dummy-not-a-secret")

    store = store_mod.SecretStore("macos-keychain")
    started = time.monotonic()
    probe = store.probe(ref)
    elapsed = time.monotonic() - started

    assert probe.reason == "keychain_prompt_pending"
    assert probe.value == ""
    assert elapsed < 1.0


@integration
def test_macos_item_from_this_python_still_reads(throwaway_keychain: Path) -> None:
    _require_seam(throwaway_keychain)
    store = store_mod.SecretStore("macos-keychain")
    assert store.health()["ok"] is True

    store.set("mbtest-ref-own", "dummy-not-a-secret")

    assert store.probe("mbtest-ref-own") == store_mod.SecretProbe(
        "dummy-not-a-secret", True, True, "", False, "security"
    )
    store.delete("mbtest-ref-own")
    assert store.probe("mbtest-ref-own").present is False


# ---------------------------------------------------------------------------
# Phase 2: items owned by Apple-signed /usr/bin/security (#1005).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('password: "abc"\n', "abc"),
        ('password: "a"b"\n', 'a"b'),
        ('password: " lead"\n', " lead"),
        ('password: "0x41"\n', "0x41"),
        ('password: 0x615C62  "a\\134b"\n', "a\\b"),
        ("password: 0xC3A9 \n", "é"),
        ("password: \n", ""),
        ("nothing useful\n", None),
        ("password: 0xZZ\n", None),
    ],
)
def test_security_password_line_is_parsed_without_ambiguity(
    text: str, expected: str | None
) -> None:
    assert helper_mod._parse_security_password(text) == expected


def _note(log: list[Any], entry: Any, result: Any) -> Any:
    log.append(entry)
    return result


def _tool_adapter(monkeypatch: pytest.MonkeyPatch, runs: list[dict[str, Any]]) -> Any:
    adapter: Any = object.__new__(helper_mod._MacSecurity)
    adapter.keychain_path = None
    adapter.deadline = time.time() + 30
    adapter.migrated = False

    def fake_run(args: list[str], **kwargs: Any) -> SimpleNamespace:
        runs.append({"args": args, **kwargs})
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(helper_mod.subprocess, "run", fake_run)  # type: ignore[attr-defined]
    return adapter


@pytest.mark.parametrize(
    "value",
    [
        "plain-token",
        "with space",
        'with "quotes"',
        "back\\slash",
        "new\nline",
        "naïve-✓",
        "",
        "x" * 1700,
    ],
)
def test_security_write_keeps_value_out_of_argv_and_round_trips_hex(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    runs: list[dict[str, Any]] = []
    adapter = _tool_adapter(monkeypatch, runs)

    assert adapter._security_put("mainbranch://abc/cloudflare/api_token", value, exists=False) == (
        "ready"
    )

    assert len(runs) == 1
    assert runs[0]["args"] == ["/usr/bin/security", "-i"]
    command = runs[0]["input"]
    assert command.count("\n") == 1 and command.endswith("\n")
    hex_value = command.split(' -X "', 1)[1].split('"', 1)[0]
    assert bytes.fromhex(hex_value).decode("utf-8") == value
    if value:
        assert value not in command or value == hex_value


def test_security_write_of_a_long_value_never_puts_it_on_the_security_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs: list[dict[str, Any]] = []
    adapter = _tool_adapter(monkeypatch, runs)
    updates: list[tuple[str, str]] = []
    adapter._update = lambda ref, value: _note(updates, (ref, value), 0)
    value = "y" * 4096

    assert adapter._security_put("fixture-ref", value, exists=False) == "ready"

    assert runs[0]["args"] == ["/usr/bin/security", "-i"]
    assert ' -X ""' in runs[0]["input"]
    assert value not in runs[0]["input"]
    assert value.encode().hex() not in runs[0]["input"]
    assert updates == [("fixture-ref", value)]


def test_security_tool_deadline_reports_prompt_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter: Any = object.__new__(helper_mod._MacSecurity)
    adapter.keychain_path = None
    adapter.deadline = time.time() + 30

    def hang(args: list[str], **kwargs: Any) -> SimpleNamespace:
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(helper_mod.subprocess, "run", hang)  # type: ignore[attr-defined]

    with pytest.raises(helper_mod._PromptPending):
        adapter._security_get("fixture-ref")


class _Crash(BaseException):
    """Stands in for the helper process dying (SIGKILL, power loss)."""


class _FakeKeychain:
    """An in-memory keychain with the rules that matter for a move.

    ``security`` may touch only items it owns; a legacy item can be read or
    deleted only by a trusted Python. ``log`` records every step in order.
    """

    def __init__(self) -> None:
        self.items: dict[str, tuple[str, str]] = {}
        self.trusted = True
        self.log: list[str] = []
        self.fail: dict[str, BaseException] = {}
        self.fail_security_call: int | None = None
        self.security_calls = 0
        self.crash_at = ""
        self.fill_fails = False
        # Fault injection: per-ref read failures (a state, or an exception to
        # raise), delete failures, and an exception for every `security` call.
        self.get_fail: dict[str, str | BaseException] = {}
        self.delete_fails = False
        self.delete_fail_refs: set[str] = set()
        self.security_raises: BaseException | None = None

    def _hook(self, step: str) -> None:
        self.log.append(step)
        if step in self.fail:
            raise self.fail.pop(step)

    def _security(self) -> None:
        self.security_calls += 1
        if self.fail_security_call == self.security_calls:
            raise OSError("could not start security")
        if self.security_raises is not None:
            raise self.security_raises

    def adapter(self, *, seconds: float = 30.0) -> Any:
        adapter: Any = object.__new__(helper_mod._MacSecurity)
        adapter.migrated = False
        adapter.owner = ""
        adapter.keychain_path = None
        adapter.deadline = time.monotonic() + seconds
        adapter.stage_kind = "absent"
        adapter.health = lambda: "ready"
        adapter._item_owner = lambda ref: self.items.get(ref, ("absent", ""))[0]
        adapter._security_get = self.security_get
        adapter._security_put = self.security_put
        adapter._security_delete = self.security_delete
        adapter._ctypes_get = self.ctypes_get
        adapter._ctypes_delete = self.ctypes_delete
        adapter._ctypes_add = self.ctypes_add
        adapter._update = self.update
        adapter._crash_point = self.crash_point
        return adapter

    def crash_point(self, step: str) -> None:
        self.log.append(f"point:{step}")
        if step == self.crash_at:
            raise _Crash(step)

    def security_get(self, ref: str) -> tuple[str, str | None]:
        self._security()
        owner, value = self.items.get(ref, ("absent", ""))
        assert owner != "legacy", "security must never read a legacy item"
        self._hook(f"security_get:{ref}")
        failure = self.get_fail.get(ref)
        if isinstance(failure, BaseException):
            raise failure
        if failure is not None:
            return failure, None
        return ("ready", value) if owner == "security" else ("missing", None)

    def security_put(self, ref: str, value: str, *, exists: bool) -> str:
        self._security()
        owner = self.items.get(ref, ("absent", ""))[0]
        assert owner != "legacy", "security must never write over a legacy item"
        self._hook(f"security_put:{ref}")
        if not exists and owner != "absent":
            return "unavailable"
        long = len(value.encode().hex()) > helper_mod.SECURITY_HEX_LIMIT
        if long and not exists:
            self.items[ref] = ("security", "")
            self.crash_point("after-placeholder")
            if self.fill_fails:
                del self.items[ref]
                return "unavailable"
        self.items[ref] = ("security", value)
        return "ready"

    def security_delete(self, ref: str) -> str:
        self._security()
        owner = self.items.get(ref, ("absent", ""))[0]
        assert owner != "legacy", "security must never delete a legacy item"
        self._hook(f"security_delete:{ref}")
        if self.delete_fails or ref in self.delete_fail_refs:
            return "unavailable"
        if owner == "absent":
            return "missing"
        del self.items[ref]
        return "ready"

    def ctypes_get(self, ref: str, *, health: str) -> tuple[str, str | None]:
        self._hook(f"ctypes_get:{ref}")
        owner, value = self.items.get(ref, ("absent", ""))
        if owner == "absent":
            return "missing", None
        return ("ready", value) if self.trusted else ("prompt-pending", None)

    def ctypes_delete(self, ref: str) -> int:
        self._hook(f"ctypes_delete:{ref}")
        if ref not in self.items:
            return helper_mod.ERR_SEC_ITEM_NOT_FOUND
        if not self.trusted or self.delete_fails:
            return helper_mod.ERR_SEC_AUTH_FAILED
        del self.items[ref]
        return 0

    def ctypes_add(self, ref: str, value: str) -> int:
        self._hook(f"ctypes_add:{ref}")
        if ref in self.items:
            return helper_mod.ERR_SEC_DUPLICATE_ITEM
        self.items[ref] = ("legacy", value)
        return 0

    def update(self, ref: str, value: str) -> int:
        self._hook(f"update:{ref}")
        if ref not in self.items:
            return helper_mod.ERR_SEC_ITEM_NOT_FOUND
        self.items[ref] = (self.items[ref][0], value)
        return 0

    def holds(self, value: str) -> bool:
        return any(stored == value for _, stored in self.items.values())


REF = "mainbranch://abc/cloudflare/api_token"
STAGE = REF + helper_mod.STAGE_SUFFIX
SHORT = "dummy-not-a-secret"
LONG = "d" * 4096


def _legacy_keychain(value: str = SHORT) -> _FakeKeychain:
    keychain = _FakeKeychain()
    keychain.items[REF] = ("legacy", value)
    return keychain


def test_legacy_item_is_never_read_through_security() -> None:
    keychain = _legacy_keychain()
    keychain.trusted = False

    assert keychain.adapter().get(REF) == ("prompt-pending", None)
    assert keychain.items == {REF: ("legacy", SHORT)}


def test_security_owned_item_is_read_through_security_only() -> None:
    keychain = _FakeKeychain()
    keychain.items[REF] = ("security", SHORT)
    adapter = keychain.adapter()

    assert adapter.get(REF) == ("ready", SHORT)
    assert adapter.owner == "security"
    assert not any(step.startswith("ctypes_") for step in keychain.log)


@pytest.mark.parametrize("value", [SHORT, LONG])
def test_move_stages_a_verified_copy_before_deleting_the_legacy_item(value: str) -> None:
    keychain = _legacy_keychain(value)
    adapter = keychain.adapter()

    assert adapter.get(REF) == ("ready", value)
    assert adapter.migrated is True
    assert adapter.owner == "security"
    assert keychain.items == {REF: ("security", value)}
    log = keychain.log
    assert log.index(f"security_put:{STAGE}") < log.index(f"security_get:{STAGE}")
    assert log.index(f"security_get:{STAGE}") < log.index(f"ctypes_delete:{REF}")
    assert log.index(f"ctypes_delete:{REF}") < log.index(f"security_put:{REF}")
    assert log.index(f"security_get:{REF}") < log.index(f"security_delete:{STAGE}")


@pytest.mark.parametrize(
    ("value", "crash_at"),
    [
        (SHORT, "after-stage"),
        (SHORT, "after-legacy-delete"),
        (SHORT, "after-final"),
        (LONG, "after-placeholder"),
        (LONG, "after-legacy-delete"),
    ],
)
def test_a_crash_at_any_step_keeps_the_value_and_the_next_read_finishes(
    value: str, crash_at: str
) -> None:
    keychain = _legacy_keychain(value)
    keychain.crash_at = crash_at
    with pytest.raises(_Crash):
        keychain.adapter().get(REF)
    assert keychain.holds(value)

    keychain.crash_at = ""
    nxt = keychain.adapter()
    assert nxt.get(REF) == ("ready", value)
    assert keychain.items == {REF: ("security", value)}


def test_a_crash_while_filling_the_final_long_item_recovers_from_the_staged_copy() -> None:
    keychain = _legacy_keychain(LONG)
    seen = 0

    def crash_on_second_placeholder(step: str) -> None:
        nonlocal seen
        keychain.log.append(f"point:{step}")
        if step == "after-placeholder":
            seen += 1
            if seen == 2:  # the first placeholder is the staged copy's
                raise _Crash(step)

    keychain.crash_point = crash_on_second_placeholder  # type: ignore[method-assign]
    with pytest.raises(_Crash):
        keychain.adapter().get(REF)
    del keychain.crash_point
    assert keychain.items[REF] == ("security", "")
    assert keychain.items[STAGE] == ("security", LONG)

    assert keychain.adapter().get(REF) == ("ready", LONG)
    assert keychain.items == {REF: ("security", LONG)}


@pytest.mark.parametrize("call", range(1, 9))
def test_a_security_launch_failure_at_any_call_never_loses_the_value(call: int) -> None:
    keychain = _legacy_keychain()
    keychain.fail_security_call = call

    state, value = keychain.adapter().get(REF)

    assert (state, value) == ("ready", SHORT)
    assert keychain.holds(SHORT)
    assert REF in keychain.items
    keychain.fail_security_call = None
    assert keychain.adapter().get(REF) == ("ready", SHORT)
    assert keychain.items == {REF: ("security", SHORT)}


def test_a_failed_final_write_restores_the_legacy_item_and_keeps_the_staged_copy() -> None:
    keychain = _legacy_keychain()
    keychain.fail[f"security_put:{REF}"] = OSError("security failed")

    adapter = keychain.adapter()
    assert adapter.get(REF) == ("ready", SHORT)
    assert adapter.migrated is False
    assert keychain.items[REF] == ("legacy", SHORT)
    assert keychain.items[STAGE] == ("security", SHORT)

    assert keychain.adapter().get(REF) == ("ready", SHORT)
    assert keychain.items == {REF: ("security", SHORT)}


def test_a_refused_legacy_delete_leaves_the_item_and_drops_the_staged_copy() -> None:
    keychain = _legacy_keychain()
    keychain.fail[f"ctypes_delete:{REF}"] = OSError("refused")

    with pytest.raises(OSError):
        keychain.adapter().get(REF)
    assert keychain.items[REF] == ("legacy", SHORT)
    assert keychain.adapter().get(REF) == ("ready", SHORT)
    assert keychain.items == {REF: ("security", SHORT)}


def test_no_move_without_time_for_all_of_it() -> None:
    keychain = _legacy_keychain()
    adapter = keychain.adapter(seconds=helper_mod.MIN_MOVE_SECONDS - 0.5)

    assert adapter.get(REF) == ("ready", SHORT)
    assert adapter.migrated is False
    assert adapter.owner == "legacy"
    assert keychain.items == {REF: ("legacy", SHORT)}
    assert not any(step.startswith(("ctypes_delete", "security_")) for step in keychain.log)


def test_replacing_a_legacy_item_updates_in_place_before_moving() -> None:
    keychain = _legacy_keychain()

    assert keychain.adapter().set(REF, "replacement") == "ready"

    assert keychain.log.index(f"update:{REF}") < keychain.log.index(f"ctypes_delete:{REF}")
    assert keychain.items == {REF: ("security", "replacement")}


def test_replacing_an_untrusted_legacy_item_keeps_it_legacy() -> None:
    keychain = _legacy_keychain()
    keychain.trusted = False

    assert keychain.adapter().set(REF, "replacement") == "ready"
    assert keychain.items == {REF: ("legacy", "replacement")}


@pytest.mark.parametrize("value", [SHORT, LONG])
def test_new_items_are_written_through_security(value: str) -> None:
    keychain = _FakeKeychain()

    assert keychain.adapter().set(REF, value) == "ready"
    assert keychain.items == {REF: ("security", value)}


def test_a_crash_in_a_new_long_write_leaves_no_empty_credential() -> None:
    keychain = _FakeKeychain()
    keychain.crash_at = "after-placeholder"
    with pytest.raises(_Crash):
        keychain.adapter().set(REF, LONG)
    assert keychain.items == {STAGE: ("security", "")}

    keychain.crash_at = ""
    assert keychain.adapter().get(REF) == ("missing", None)
    assert keychain.items == {}


def test_a_failed_new_write_falls_back_without_an_empty_item() -> None:
    keychain = _FakeKeychain()
    keychain.fill_fails = True

    assert keychain.adapter().set(REF, LONG) == "ready"
    assert keychain.items == {REF: ("legacy", LONG)}


def test_a_failed_long_fill_removes_the_empty_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter: Any = object.__new__(helper_mod._MacSecurity)
    adapter.keychain_path = None
    adapter.deadline = time.time() + 30
    deleted: list[str] = []
    adapter._security_tool = lambda args, stdin=None: SimpleNamespace(returncode=0, stderr="")
    adapter._update = lambda ref, value: helper_mod.ERR_SEC_AUTH_FAILED
    adapter._security_delete = lambda ref: _note(deleted, ref, "ready")
    adapter._crash_point = lambda step: None

    assert adapter._security_put(REF, LONG, exists=False) != "ready"
    assert deleted == [REF]


def test_delete_removes_a_staged_copy_too() -> None:
    keychain = _FakeKeychain()
    keychain.items[REF] = ("security", SHORT)
    keychain.items[STAGE] = ("security", SHORT)

    assert keychain.adapter().delete(REF) == "ready"
    assert keychain.items == {}


def test_recovery_keeps_a_staged_copy_it_cannot_read() -> None:
    """Crash after the legacy delete, then a failed staged read: never `missing`."""

    keychain = _legacy_keychain()
    keychain.crash_at = "after-legacy-delete"
    with pytest.raises(_Crash):
        keychain.adapter().get(REF)
    keychain.crash_at = ""
    assert keychain.items == {STAGE: ("security", SHORT)}

    failures: list[str | BaseException] = [
        "unavailable",
        helper_mod._PromptPending(),
        OSError("no security"),
    ]
    for failure in failures:
        keychain.get_fail[STAGE] = failure
        state, value = keychain.adapter().get(REF)
        assert state in {"unavailable", "prompt-pending"}
        assert value is None
        assert keychain.items == {STAGE: ("security", SHORT)}

    keychain.get_fail.clear()
    assert keychain.adapter().get(REF) == ("ready", SHORT)
    assert keychain.items == {REF: ("security", SHORT)}


def test_a_failed_staged_delete_leaves_the_credential_and_reports_it() -> None:
    """Only the staged copy's delete fails: the item must stay and the delete
    must fail, or the next access would bring the credential back."""

    keychain = _FakeKeychain()
    keychain.items[REF] = ("security", SHORT)
    keychain.items[STAGE] = ("security", SHORT)
    keychain.delete_fail_refs = {STAGE}

    assert keychain.adapter().delete(REF) == "unavailable"
    assert keychain.items[REF] == ("security", SHORT)
    keychain.delete_fail_refs = set()
    assert keychain.adapter().delete(REF) == "ready"
    assert keychain.adapter().get(REF) == ("missing", None)


def test_a_deleted_credential_never_comes_back() -> None:
    keychain = _FakeKeychain()
    keychain.items[REF] = ("security", SHORT)
    keychain.items[STAGE] = ("security", SHORT)

    assert keychain.adapter().delete(REF) == "ready"
    assert keychain.adapter().get(REF) == ("missing", None)
    assert keychain.items == {}


def test_the_time_gate_is_checked_again_before_the_legacy_delete() -> None:
    keychain = _legacy_keychain()
    adapter = keychain.adapter()
    answers = iter([True])  # enough time to stage, then not enough to delete
    adapter._can_move = lambda: next(answers, False)

    assert adapter.get(REF) == ("ready", SHORT)
    assert keychain.items[REF] == ("legacy", SHORT)
    assert not any("delete" in step for step in keychain.log)


def test_an_empty_value_is_never_staged() -> None:
    keychain = _legacy_keychain("")

    assert keychain.adapter().get(REF) == ("ready", "")
    assert keychain.items == {REF: ("legacy", "")}
    assert not any(step.startswith("security_put") for step in keychain.log)


def test_the_helper_deadline_is_monotonic() -> None:
    before = time.monotonic()
    deadline = helper_mod._monotonic_deadline(time.time() + 5.0)
    assert before + 4.5 < deadline < time.monotonic() + 5.5


_OLD = "dummy-old-not-a-secret"
_NEW = "dummy-new-not-a-secret"
_STAGE_KINDS = ["absent", "empty", "readable", "unreadable"]
_MAIN_KINDS = ["absent", "legacy", "security-readable", "security-empty", "unreadable"]
_FAULTS = [
    "none",
    "read-error",
    "prompt",
    "owner-error",
    "delete-error",
    "deadline-short",
    "exception",
]


def _table_keychain(stage: str, main: str) -> _FakeKeychain:
    keychain = _FakeKeychain()
    if stage == "empty":
        keychain.items[STAGE] = ("security", "")
    elif stage in {"readable", "unreadable"}:
        keychain.items[STAGE] = ("security", _OLD)
        if stage == "unreadable":
            keychain.get_fail[STAGE] = "unavailable"
    if main == "legacy":
        keychain.items[REF] = ("legacy", _OLD)
    elif main in {"security-readable", "unreadable"}:
        keychain.items[REF] = ("security", _OLD)
        if main == "unreadable":
            keychain.get_fail[REF] = "unavailable"
    elif main == "security-empty":
        keychain.items[REF] = ("security", "")
    return keychain


def _held(keychain: _FakeKeychain) -> set[str]:
    return {value for _, value in keychain.items.values() if value}


@pytest.mark.parametrize("fault", _FAULTS)
@pytest.mark.parametrize("main", _MAIN_KINDS)
@pytest.mark.parametrize("stage", _STAGE_KINDS)
@pytest.mark.parametrize("action", ["get", "set", "delete"])
def test_staged_copy_state_table_invariants(action: str, stage: str, main: str, fault: str) -> None:
    """Every (staged copy x item) cell, each fault, against the four invariants:
    (a) a stored value keeps a durable copy, (b) a deleted credential never
    comes back, (c) no move or recovery delete without the time gate,
    (d) unreadable never becomes `missing`."""

    keychain = _table_keychain(stage, main)
    held_before = _held(keychain)
    item_before = keychain.items.get(REF)
    seconds = helper_mod.MIN_MOVE_SECONDS - 0.5 if fault == "deadline-short" else 30.0
    adapter = keychain.adapter(seconds=seconds)
    if fault == "read-error":
        for ref in (REF, STAGE):
            keychain.get_fail.setdefault(ref, "unavailable")
    elif fault == "prompt":
        for ref in (REF, STAGE):
            keychain.get_fail.setdefault(ref, helper_mod._PromptPending())
    elif fault == "delete-error":
        keychain.delete_fails = True
    elif fault == "exception":
        keychain.security_raises = OSError("could not start security")
    elif fault == "owner-error":
        adapter._item_owner = lambda ref: "unavailable"

    try:
        if action == "get":
            result: Any = adapter.get(REF)[0]
        elif action == "set":
            result = adapter.set(REF, _NEW)
        else:
            result = adapter.delete(REF)
    except (OSError, helper_mod._PromptPending):
        result = "raised"

    deleted = [step for step in keychain.log if "delete" in step]
    if fault == "deadline-short" and action != "delete":
        assert not deleted, "(c) a delete started without the time gate"
    if action == "get" and held_before:
        assert result != "missing", "(d) a stored value was reported missing"

    succeeded = result == "ready" or (action == "delete" and result == "missing")
    if action == "set" and succeeded:
        assert _NEW in _held(keychain)
    elif action == "delete" and succeeded:
        assert _OLD not in _held(keychain)
    else:
        assert held_before <= _held(keychain), "(a) a stored value lost its last copy"
    if action == "delete" and not succeeded:
        assert keychain.items.get(REF) == item_before, "a failed delete touched the item"

    # Later, with every fault gone and time to spare, the credential settles.
    keychain.get_fail.clear()
    keychain.delete_fails = False
    keychain.security_raises = None
    after = keychain.adapter().get(REF)
    if action == "delete" and succeeded:
        assert after == ("missing", None), "(b) a deleted credential came back"
    elif action == "set" and succeeded:
        assert after == ("ready", _NEW)
    elif _OLD in held_before:
        assert after == ("ready", _OLD)
        assert keychain.items == {REF: ("security", _OLD)}


def test_helper_rejects_refs_that_could_break_security_quoting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Adapter:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def get(self, ref: str) -> tuple[str, str | None]:
            raise AssertionError("unsafe ref reached the adapter")

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(helper_mod, "_MacSecurity", Adapter)
    for ref in ['a" -X "00', "a\nb", "a b", "-flag", "mainbranch://abc/x/y.mbstage"]:
        assert helper_mod._macos("get", {"ref": ref})[0] == "unavailable"


def test_probe_reports_migration_without_the_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]
    monkeypatch.setattr(
        store_mod,
        "_run_helper",
        lambda backend, action, **kwargs: {
            "state": "ready",
            "value": "fixture",
            "migrated": True,
            "owner": "security",
        },
    )

    probe = store_mod.SecretStore("macos-keychain").probe("fixture-ref")

    assert probe == store_mod.SecretProbe("fixture", True, True, "", True, "security")


def test_helper_deadline_ends_before_the_parent_stops_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _RecordingHelper()
    helper.install(monkeypatch)
    monkeypatch.setattr(store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]

    started = time.time()
    store_mod.SecretStore("macos-keychain").probe("fixture-ref")
    store_mod.SecretStore("macos-keychain").probe("fixture-ref", interactive=True)

    for call in helper.calls:
        epoch = call["payload"]["deadline_epoch"]
        assert "budget_seconds" not in call["payload"]
        assert epoch <= started + call["timeout"] - store_mod.HELPER_EXIT_HEADROOM_SECONDS + 0.5


@pytest.mark.parametrize("budget", [0.1, 2.0])
def test_a_nearly_spent_shared_deadline_never_starts_a_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, budget: float
) -> None:
    """status_all shares one deadline; with less than a move's minimum left the
    helper may only read. At 0.1 s a loaded machine may spend it all before the
    helper starts (also safe); 2.0 s always reaches the helper."""

    repo = _keychain_repo(tmp_path, monkeypatch)
    keychain = _legacy_keychain()
    timeouts: list[float] = []

    def run(args: list[str], **kwargs: Any) -> SimpleNamespace:
        payload = json.loads(kwargs["input"])
        timeouts.append(kwargs["timeout"])
        adapter = keychain.adapter()
        adapter.deadline = helper_mod._monotonic_deadline(payload["deadline_epoch"])
        state, value = adapter.get(REF)
        body = {"state": state, "value": value} if value is not None else {"state": state}
        return SimpleNamespace(returncode=0 if state == "ready" else 1, stdout=json.dumps(body))

    monkeypatch.setattr(store_mod, "subprocess", _fake_subprocess(run))

    # Measured from when status_all takes its deadline, not from test setup:
    # setup on a loaded machine can itself spend 0.1 s.
    def nearly_spent() -> float:
        return time.monotonic() + budget

    monkeypatch.setattr(store_mod, "new_credential_deadline", nearly_spent)
    monkeypatch.setattr(connect_mod, "new_credential_deadline", nearly_spent)

    connect_mod.status_all(repo)

    if budget >= 1.0:
        assert timeouts
    assert all(timeout <= budget for timeout in timeouts)
    assert keychain.items == {REF: ("legacy", SHORT)}
    assert not any(step.startswith(("ctypes_delete", "security_put")) for step in keychain.log)


def test_a_timed_out_helper_takes_its_children_with_it(tmp_path: Path) -> None:
    """The parent kills the helper's whole process group, grandchildren included."""

    pid_file = tmp_path / "child.pid"
    script = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen(['sleep', '60'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
        "time.sleep(60)\n"
    )

    with pytest.raises(subprocess.TimeoutExpired):
        store_mod._invoke_helper([sys.executable, "-c", script], "", 1.5)

    child = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        os.kill(child, 9)
        pytest.fail("the helper's child outlived it")


def _python_as(tmp_path: Path, identifier: str) -> list[str]:
    """A copy of this interpreter that the keychain treats as another app."""

    copy = tmp_path / f"python-{identifier}"
    shutil.copy2(Path(sys.executable).resolve(), copy)
    subprocess.run(
        ["/usr/bin/codesign", "--force", "--sign", "-", "--identifier", identifier, str(copy)],
        check=True,
        capture_output=True,
        timeout=60,
    )
    # The first launch of a newly signed binary pays for macOS signature
    # checks; warm it so timings measure the keychain, not the launch.
    subprocess.run(
        [str(copy), "-c", "pass"], env=_helper_env(), check=True, capture_output=True, timeout=60
    )
    return [str(copy)]


def _helper(python: list[str], action: str, payload: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    completed = subprocess.run(
        [*python, "-m", "mb._credential_helper", "macos-keychain", action],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=_helper_env(),
        timeout=30,
        check=False,
    )
    result: dict[str, Any] = json.loads(completed.stdout)
    result["elapsed"] = time.monotonic() - started
    return result


def _legacy_add(python: list[str], ref: str, value: str) -> None:
    """Create an item the way mb did before #1005: SecItemAdd from Python."""

    script = (
        "import sys; from mb import _credential_helper as h; "
        "sys.exit(h._MacSecurity()._ctypes_add(sys.argv[1], sys.argv[2]) != 0)"
    )
    subprocess.run(
        [*python, "-c", script, ref, value],
        env=_helper_env(),
        check=True,
        capture_output=True,
        timeout=30,
    )


@integration
def test_macos_migrated_item_survives_python_swaps(
    tmp_path: Path, throwaway_keychain: Path
) -> None:
    _require_seam(throwaway_keychain)
    python_a = [sys.executable]
    python_b = _python_as(tmp_path, "com.example.mbtest-b")
    python_c = _python_as(tmp_path, "com.example.mbtest-c")
    ref = "mbtest-ref-swap"
    _legacy_add(python_a, ref, "dummy-not-a-secret")

    before = _helper(python_b, "get", {"ref": ref})
    assert before["state"] == "prompt-pending"
    assert before["elapsed"] < 1.0

    migrated = _helper(python_a, "get", {"ref": ref})
    assert migrated["state"] == "ready"
    assert migrated["migrated"] is True
    assert migrated["value"] == "dummy-not-a-secret"

    for python in (python_b, python_c, python_a):
        result = _helper(python, "get", {"ref": ref})
        assert result["state"] == "ready"
        assert result["value"] == "dummy-not-a-secret"
        assert "migrated" not in result
        assert result["elapsed"] < 2.0


@integration
@pytest.mark.parametrize(
    "value",
    ["dummy plain", 'dummy "quoted" \\ back', "dummy\nnewline", "dümmy-✓", "d" * 4096],
)
def test_macos_security_round_trip(throwaway_keychain: Path, value: str) -> None:
    _require_seam(throwaway_keychain)
    store = store_mod.SecretStore("macos-keychain")
    ref = "mbtest-ref-roundtrip"

    store.set(ref, value)
    assert store.probe(ref).value == value
    store.set(ref, value + "-2")
    assert store.probe(ref).value == value + "-2"

    adapter = helper_mod._MacSecurity()
    assert adapter._item_owner(ref) == "security"
    store.delete(ref)
    assert store.probe(ref).present is False


@integration
def test_macos_new_write_is_readable_by_another_python(
    tmp_path: Path, throwaway_keychain: Path
) -> None:
    _require_seam(throwaway_keychain)
    ref = "mbtest-ref-new"
    store_mod.SecretStore("macos-keychain").set(ref, "dummy-not-a-secret")

    result = _helper(_python_as(tmp_path, "com.example.mbtest-d"), "get", {"ref": ref})

    assert result["state"] == "ready"
    assert result["value"] == "dummy-not-a-secret"


def test_keychain_repair_reports_each_migration_without_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _keychain_repo(tmp_path, monkeypatch)
    calls: list[bool] = []
    moved: set[str] = set()

    def run(args: list[str], **kwargs: Any) -> SimpleNamespace:
        payload = json.loads(kwargs["input"])
        calls.append(payload["interactive"])
        if payload["ref"] in moved:
            # Owned by /usr/bin/security now: any Python reads it unattended.
            return SimpleNamespace(
                returncode=0, stdout='{"state":"ready","value":"fixture","owner":"security"}'
            )
        if not payload["interactive"]:
            return SimpleNamespace(returncode=1, stdout='{"state":"prompt-pending"}')
        moved.add(payload["ref"])
        return SimpleNamespace(
            returncode=0,
            stdout='{"state":"ready","value":"fixture","migrated":true,"owner":"security"}',
        )

    monkeypatch.setattr(store_mod, "subprocess", _fake_subprocess(run))

    result = connect_mod.repair_keychain(repo, interactive=True)

    assert result["ok"] is True
    assert [item["state"] for item in result["items"]] == ["repaired", "repaired"]
    assert [item["migrated"] for item in result["items"]] == [True, True]
    assert all("security tool" in item["summary"] for item in result["items"])
    # Each item: unattended probe, answered read, fresh unattended verify.
    assert calls == [False, True, False] * 2
    assert "fixture" not in json.dumps(result)


def test_keychain_repair_does_not_call_a_legacy_read_a_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Readable now is not immune to the next Python change until security owns it."""

    repo = _keychain_repo(tmp_path, monkeypatch)
    answered: set[str] = set()

    def run(args: list[str], **kwargs: Any) -> SimpleNamespace:
        payload = json.loads(kwargs["input"])
        if payload["interactive"]:
            answered.add(payload["ref"])
        if payload["ref"] in answered or "cloudflare" in payload["ref"]:
            # Readable, but the move did not finish: a Python still owns it.
            return SimpleNamespace(
                returncode=0, stdout='{"state":"ready","value":"fixture","owner":"legacy"}'
            )
        return SimpleNamespace(returncode=1, stdout='{"state":"prompt-pending"}')

    monkeypatch.setattr(store_mod, "subprocess", _fake_subprocess(run))

    result = connect_mod.repair_keychain(repo, interactive=True)

    assert [(item["provider"], item["state"]) for item in result["items"]] == [
        ("cloudflare", "readable_not_migrated"),
        ("resend", "readable_not_migrated"),
    ]
    assert result["ok"] is False
    assert result["repair_command"] == "mb connect repair --keychain"
    assert all("again" in item["summary"] for item in result["items"])


def test_crash_hook_is_inert_without_the_test_keychain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(helper_mod.TEST_CRASH_ENV, "after-stage")
    adapter: Any = object.__new__(helper_mod._MacSecurity)
    adapter.keychain_path = None

    adapter._crash_point("after-stage")  # returns; never exits outside tests


@integration
@pytest.mark.parametrize(
    ("value", "crash_at"),
    [
        ("dummy-not-a-secret", "after-stage"),
        ("dummy-not-a-secret", "after-legacy-delete"),
        ("dummy-not-a-secret", "after-final"),
        ("d" * 4096, "after-placeholder"),
        ("d" * 4096, "after-legacy-delete"),
    ],
)
def test_macos_a_killed_move_is_recovered_on_the_next_read(
    throwaway_keychain: Path, monkeypatch: pytest.MonkeyPatch, value: str, crash_at: str
) -> None:
    _require_seam(throwaway_keychain)
    ref = "mbtest-ref-crash"
    _legacy_add([sys.executable], ref, value)

    monkeypatch.setenv(helper_mod.TEST_CRASH_ENV, crash_at)
    crashed = subprocess.run(
        [sys.executable, "-m", "mb._credential_helper", "macos-keychain", "get"],
        input=json.dumps({"ref": ref}),
        capture_output=True,
        text=True,
        env=_helper_env(),
        timeout=30,
        check=False,
    )
    assert crashed.returncode == 70
    monkeypatch.delenv(helper_mod.TEST_CRASH_ENV)

    result = _helper([sys.executable], "get", {"ref": ref})

    assert result["state"] == "ready"
    assert result["value"] == value
    adapter = helper_mod._MacSecurity()
    assert adapter._item_owner(ref) == "security"
    assert adapter._item_owner(ref + helper_mod.STAGE_SUFFIX) == "absent"


@integration
def test_macos_a_whole_move_fits_well_inside_the_minimum(
    throwaway_keychain: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _require_seam(throwaway_keychain)
    timings: list[float] = []
    for index in range(3):
        ref = f"mbtest-ref-timing-{index}"
        _legacy_add([sys.executable], ref, "dummy-not-a-secret")
        adapter = helper_mod._MacSecurity()
        started = time.monotonic()
        assert adapter.get(ref) == ("ready", "dummy-not-a-secret")
        timings.append(time.monotonic() - started)
        assert adapter.migrated is True
    with capsys.disabled():
        print(f"\nmove seconds: {', '.join(f'{t:.2f}' for t in timings)}")
    assert max(timings) < helper_mod.MIN_MOVE_SECONDS


@integration
def test_macos_listing_every_item_is_prompt_free(tmp_path: Path, throwaway_keychain: Path) -> None:
    """``--all`` lists items this Python may not read, without a dialog or a value."""

    _require_seam(throwaway_keychain)
    foreign = "mainbranch://000000000000000000000001/stripe/api_key"
    own = "mainbranch://000000000000000000000002/resend/api_key"
    _legacy_add(_foreign_python(tmp_path), foreign, "dummy-not-a-secret")
    store_mod.SecretStore("macos-keychain").set(own, "dummy-not-a-secret")
    # Control: this Python is not trusted to read the foreign item's value.
    assert _helper([sys.executable], "get", {"ref": foreign})["state"] == "prompt-pending"

    for payload in ({}, {"interactive": True}):
        listed = _helper([sys.executable], "list", payload)
        assert listed["state"] == "ready"
        assert listed["refs"] == sorted([foreign, own])
        assert set(listed) == {"state", "refs", "found", "limit", "elapsed"}
        assert listed["found"] == 2
        assert listed["elapsed"] < 2.0
    assert store_mod.list_keychain_refs().refs == sorted([foreign, own])


@integration
def test_macos_repair_all_moves_legacy_items_and_recovers_staged_ones(
    tmp_path: Path, throwaway_keychain: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_seam(throwaway_keychain)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    legacy = "mainbranch://000000000000000000000003/cloudflare/api_token"
    staged = "mainbranch://000000000000000000000004/apify/api_token"
    foreign = "mainbranch://000000000000000000000005/stripe/api_key"
    owned = "mainbranch://000000000000000000000006/resend/api_key"
    _legacy_add([sys.executable], legacy, "dummy-legacy")
    _legacy_add([sys.executable], staged, "dummy-staged")
    _legacy_add(_foreign_python(tmp_path), foreign, "dummy-foreign")
    store_mod.SecretStore("macos-keychain").set(owned, "dummy-owned")
    # Interrupt a move after the legacy delete: only the staged copy is left.
    crashed = subprocess.run(
        [sys.executable, "-m", "mb._credential_helper", "macos-keychain", "get"],
        input=json.dumps({"ref": staged}),
        capture_output=True,
        text=True,
        env={**_helper_env(), helper_mod.TEST_CRASH_ENV: "after-legacy-delete"},
        timeout=30,
        check=False,
    )
    assert crashed.returncode == 70
    assert staged + helper_mod.STAGE_SUFFIX in store_mod.list_keychain_refs().refs
    assert staged not in store_mod.list_keychain_refs().refs

    # Unattended only: the foreign item would need a dialog, which a test never shows.
    result = connect_mod.repair_keychain_all(tmp_path, interactive=False)

    by_ref = {item["ref"]: item for item in result["items"]}
    assert set(by_ref) == {legacy, staged, foreign, owned}
    assert (by_ref[legacy]["state"], by_ref[legacy]["migrated"]) == ("ready", True)
    assert (by_ref[staged]["state"], by_ref[staged]["staged_only"]) == ("ready", True)
    assert by_ref[owned]["state"] == "ready"
    assert by_ref[foreign]["state"] == "keychain_prompt_pending"
    assert result["pending"] == 1
    assert result["repair_command"] == "mb connect repair --keychain --all"
    assert "dummy" not in json.dumps(result)
    adapter = helper_mod._MacSecurity()
    for ref in (legacy, staged, owned):
        assert adapter._item_owner(ref) == "security"
    assert adapter._item_owner(staged + helper_mod.STAGE_SUFFIX) == "absent"
    assert store_mod.list_keychain_refs().refs == sorted([legacy, staged, foreign, owned])


def test_the_helper_starts_from_the_installed_package_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []

    def run(args: list[str], **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stdout='{"state":"unavailable"}')

    fake = _fake_subprocess(run)

    class RecordingPopen(fake.Popen):  # type: ignore[misc,name-defined]
        def __init__(self, args: list[str], **kwargs: Any) -> None:
            seen.append(kwargs)
            super().__init__(args, **kwargs)

    fake.Popen = RecordingPopen
    monkeypatch.setattr(store_mod, "subprocess", fake)

    store_mod._run_helper("no-such-backend", "get", ref="fixture-ref")

    assert [call["cwd"] for call in seen] == [str(MB_PACKAGE.parent)]
    assert (Path(seen[0]["cwd"]) / "mb" / "_credential_helper.py").is_file()


def test_the_working_directory_cannot_stand_in_for_the_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory holding another ``mb`` package is ignored when the helper starts."""

    other = tmp_path / "checkout"
    (other / "mb").mkdir(parents=True)
    (other / "mb" / "__init__.py").write_text("", encoding="utf-8")
    (other / "mb" / "_credential_helper.py").write_text(
        'import sys\nsys.stdout.write(\'{"state":"ready","value":"NOT-THE-HELPER"}\')\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(other)
    monkeypatch.delenv("PYTHONPATH", raising=False)

    # An unknown backend: the real helper answers at once and touches no keychain.
    result = store_mod._run_helper("no-such-backend", "get", ref="fixture-ref")

    assert result.get("value") != "NOT-THE-HELPER"
    assert result == {"state": "unavailable"}
