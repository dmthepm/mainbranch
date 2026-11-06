"""A file inside a repo may not choose another repo's keys.

The business folder saves a key under its repo id. A folder whose
`.mb/connect.yaml` names that id, without ever having saved under it, is
refused until the owner runs `mb connect rebind`.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from mb import connect as c
from mb.cli import app
from mb.credential_store import SecretStore
from tests.connect_binding import bind_folder

runner = CliRunner()
KEY = "sk_test_business_fixture_key"
REMOTE = "https://github.com/example-org/example-business.git"


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    for provider in c.PROVIDERS:
        for env_var in provider.env_vars:
            monkeypatch.delenv(env_var, raising=False)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _business(tmp_path: Path) -> Path:
    """A git folder with a public remote that saved a Stripe key."""

    repo = tmp_path / "business"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "remote", "add", "origin", REMOTE)
    c.connect_provider("stripe", repo=repo, token=KEY)
    return repo


def _borrower(tmp_path: Path, business: Path, *, providers: dict[str, Any] | None = None) -> Path:
    """A plain folder whose file names the business's repo id."""

    repo = tmp_path / "borrower"
    (repo / ".mb").mkdir(parents=True)
    config = yaml.safe_load((business / ".mb" / "connect.yaml").read_text(encoding="utf-8"))
    config["providers"] = providers if providers is not None else config["providers"]
    (repo / ".mb" / "connect.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    return repo


def _user_scope_business(tmp_path: Path) -> Path:
    repo = tmp_path / "business"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "remote", "add", "origin", REMOTE)
    c.connect_provider("stripe", repo=repo, token=KEY, scope="user")
    return repo


def _no_key_in(value: Any) -> None:
    assert KEY not in json.dumps(value, default=str)


def _refused(callable_: Any, *args: Any, **kwargs: Any) -> c.ConnectRefusal:
    with pytest.raises(c.ConnectRefusal) as caught:
        callable_(*args, **kwargs)
    assert caught.value.rule == "repo_binding_required"
    assert "mb connect rebind" in str(caught.value)
    assert KEY not in str(caught.value)
    return caught.value


def test_normal_folder_reads_its_own_key(tmp_path: Path) -> None:
    business = _business(tmp_path)

    result = c.read_token("stripe", business)

    assert result["ok"] is True
    assert result["token"] == KEY


def test_worktree_of_the_same_remote_is_unaffected(tmp_path: Path) -> None:
    business = _business(tmp_path)
    _git(
        business,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "start",
    )
    tree = tmp_path / "tree"
    _git(business, "worktree", "add", "-q", str(tree), "-b", "other")
    (tree / ".mb").mkdir(exist_ok=True)
    (tree / ".mb" / "connect.yaml").write_text(
        (business / ".mb" / "connect.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )

    assert c.read_token("stripe", tree)["token"] == KEY
    assert c.status_provider("stripe", tree)["state"] != "repo_binding_required"


def test_borrowed_id_is_refused_for_repo_scope_read(tmp_path: Path) -> None:
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)

    refusal = _refused(c.read_token, "stripe", borrower)

    assert f"--repo {borrower}" in str(refusal)


def test_borrowed_id_is_refused_for_the_user_scope_fallback(tmp_path: Path) -> None:
    business = _user_scope_business(tmp_path)
    borrower = _borrower(tmp_path, business, providers={})

    _refused(c.read_token, "stripe", borrower)
    assert c.read_metadata("stripe", borrower) == {}
    assert c.status_provider("stripe", borrower)["state"] == "repo_binding_required"


def test_borrowed_id_never_reaches_the_secret_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("a borrowed id reached the secret store")

    monkeypatch.setattr(c, "_probe_secret_ref", forbidden)
    monkeypatch.setattr(SecretStore, "probe", forbidden)

    _refused(c.read_token, "stripe", borrower)
    status = c.status_provider("stripe", borrower)
    assert status["state"] == "repo_binding_required"
    assert status["ok"] is False
    assert status["secrets"] == {}
    assert "mb connect rebind" in status["repair_command"]
    everything = c.status_all(borrower, include_all=True)
    assert {item["state"] for item in everything["providers"] if item["configured"]} == {
        "repo_binding_required"
    }
    _no_key_in([status, everything])


def test_exec_is_refused_with_a_refused_audit_line_and_runs_nothing(tmp_path: Path) -> None:
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)
    ran: list[Any] = []

    _refused(
        c.exec_with_secret,
        "stripe",
        ["true"],
        borrower,
        runner=lambda *args, **kwargs: ran.append(args),
    )

    assert ran == []
    last = c.read_release_audit(limit=1)[0]
    assert (last["verb"], last["result"], last["reason"]) == (
        "exec",
        "refused",
        "repo_binding_required",
    )
    _no_key_in(last)


def test_token_command_is_refused_and_audited(tmp_path: Path) -> None:
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)

    result = runner.invoke(app, ["connect", "token", "stripe", "--print", "--repo", str(borrower)])

    assert result.exit_code != 0
    assert KEY not in result.output
    assert "mb connect rebind" in result.output
    assert c.read_release_audit(limit=1)[0]["result"] == "refused"


def test_test_and_rotate_are_refused(tmp_path: Path) -> None:
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)

    _refused(c.test_provider, "stripe", borrower)
    _refused(c.rotate_provider, "stripe", borrower)
    for verb in ("test", "rotate"):
        result = runner.invoke(app, ["connect", verb, "stripe", "--repo", str(borrower)])
        assert result.exit_code != 0
        assert KEY not in result.output


def test_a_save_in_a_borrowed_folder_is_refused_and_stores_nothing(tmp_path: Path) -> None:
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business, providers={})

    _refused(c.connect_provider, "stripe", repo=borrower, token="sk_test_attacker_value")

    assert c.read_token("stripe", business)["token"] == KEY


def test_legacy_folder_gets_the_exact_rebind_command(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    (legacy / ".mb").mkdir(parents=True)
    (legacy / ".mb" / "connect.yaml").write_text(
        yaml.safe_dump({"version": 1, "repo_id": "old-random-id", "providers": {}}),
        encoding="utf-8",
    )

    refusal = _refused(c.read_token, "stripe", legacy)

    assert f"`mb connect rebind --repo {legacy}`" in str(refusal)


def test_rebind_previews_then_allows_and_says_so_plainly(tmp_path: Path) -> None:
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)

    preview = runner.invoke(app, ["connect", "rebind", "--repo", str(borrower)])
    assert preview.exit_code == 0
    assert "lets this folder use the keys saved under repo id" in preview.output
    assert "Nothing was changed" in preview.output
    _refused(c.read_token, "stripe", borrower)

    applied = runner.invoke(app, ["connect", "rebind", "--repo", str(borrower), "--yes"])
    assert applied.exit_code == 0
    assert "This folder is now allowed" in applied.output
    assert c.read_token("stripe", borrower)["token"] == KEY
    assert KEY not in preview.output + applied.output


def test_rebind_in_a_normal_folder_changes_nothing(tmp_path: Path) -> None:
    business = _business(tmp_path)
    before = (c._repo_bindings_path()).read_text(encoding="utf-8")

    result = c.rebind(business, apply=True)

    assert result["needed"] is False
    assert result["applied"] is False
    assert c._repo_bindings_path().read_text(encoding="utf-8") == before


def test_remote_moved_in_the_same_folder_needs_a_rebind(tmp_path: Path) -> None:
    business = _business(tmp_path)
    assert c.read_token("stripe", business)["ok"] is True

    _git(business, "remote", "set-url", "origin", "https://github.com/example-org/renamed.git")

    refusal = _refused(c.read_token, "stripe", business)
    assert f"--repo {business}" in str(refusal)
    c.rebind(business, apply=True)
    assert c.read_token("stripe", business)["token"] == KEY


def test_every_save_records_its_folder_by_hash_only(tmp_path: Path) -> None:
    business = _business(tmp_path)
    identity = c._repo_identity(business)

    path = c._repo_bindings_path()
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)

    assert data["repos"][identity["repo_id"]]["folders"] == [identity["basis_sha256"]]
    assert str(tmp_path) not in text
    assert "github.com" not in text
    assert KEY not in text
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) & 0o077 == 0


def test_record_refuses_a_symlink_and_reads_nothing_through_it(tmp_path: Path) -> None:
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)
    path = c._repo_bindings_path()
    other = tmp_path / "elsewhere.json"
    other.write_text(
        json.dumps(
            {
                "version": 1,
                "repos": {
                    c._repo_identity(business)["repo_id"]: {
                        "folders": [c._repo_identity(borrower)["basis_sha256"]]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    other.chmod(0o600)
    path.unlink()
    path.symlink_to(other)

    _refused(c.read_token, "stripe", borrower)
    with pytest.raises(c.ConnectRefusal) as caught:
        c.rebind(borrower, apply=True)
    assert caught.value.rule == "repo_binding_record_unsafe"
    assert path.is_symlink()
    assert json.loads(other.read_text(encoding="utf-8"))["version"] == 1


def test_record_in_a_symlinked_folder_is_refused(tmp_path: Path) -> None:
    business = _business(tmp_path)
    folder = c._repo_bindings_path().parent
    moved = tmp_path / "moved"
    folder.rename(moved)
    folder.symlink_to(moved)

    with pytest.raises(c.ConnectRefusal) as caught:
        c._load_repo_bindings()
    assert caught.value.rule == "repo_binding_record_unsafe"
    assert business.exists()


def test_record_other_users_can_write_is_not_trusted(tmp_path: Path) -> None:
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)
    c.rebind(borrower, apply=True)
    assert c.read_token("stripe", borrower)["ok"] is True

    c._repo_bindings_path().chmod(0o666)

    _refused(c.read_token, "stripe", borrower)


def test_unreadable_record_does_not_open_the_gate(tmp_path: Path) -> None:
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)
    c._repo_bindings_path().write_text("not json", encoding="utf-8")

    _refused(c.read_token, "stripe", borrower)
    assert c.read_token("stripe", business)["ok"] is True


@pytest.mark.parametrize(
    "body",
    [
        b"[" * 100_000 + b"]" * 100_000,
        b'{"repos": {}, "pad": "' + b"x" * (c.REPO_BINDINGS_MAX_BYTES + 1) + b'"}',
    ],
    ids=["deep-nesting", "over-cap"],
)
def test_hostile_record_is_refused_cleanly(tmp_path: Path, body: bytes) -> None:
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)
    c._repo_bindings_path().write_bytes(body)

    _refused(c.read_token, "stripe", borrower)
    with pytest.raises(c.ConnectRefusal):
        c._load_repo_bindings()


def test_record_fifo_is_refused_without_blocking(tmp_path: Path) -> None:
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)
    record = c._repo_bindings_path()
    record.unlink()
    os.mkfifo(record, 0o600)

    _refused(c.read_token, "stripe", borrower)


def test_concurrent_saves_keep_the_record_whole(tmp_path: Path) -> None:
    ids = [f"repo-{n}" for n in range(12)]
    errors: list[BaseException] = []

    def record(repo_id: str) -> None:
        try:
            c._record_repo_binding(repo_id, f"{repo_id}-folder")
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=record, args=(repo_id,)) for repo_id in ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert c._load_repo_bindings() == {repo_id: [f"{repo_id}-folder"] for repo_id in ids}


def test_concurrent_processes_keep_the_record_whole(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    code = (
        "import sys; from mb import connect as c; c._record_repo_binding('shared-id', sys.argv[1])"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    procs = [
        subprocess.Popen([sys.executable, "-c", code, f"folder-{n}"], env=env) for n in range(6)
    ]
    assert [proc.wait(timeout=60) for proc in procs] == [0] * 6

    assert sorted(c._load_repo_bindings()["shared-id"]) == [f"folder-{n}" for n in range(6)]


def test_fixture_helper_records_the_binding(tmp_path: Path) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()
    c._write_config(repo, {"repo_id": "made-up-id", "providers": {}})
    _refused(c.read_token, "stripe", repo)

    bind_folder(repo, "made-up-id")

    assert c.read_token("stripe", repo)["state"] == "not_connected"


def test_validation_recording_never_writes_under_a_changed_unbound_id(tmp_path: Path) -> None:
    business = _user_scope_business(tmp_path)
    config = c._read_config(business)
    entry = dict(config["providers"]["stripe"])
    before = c._read_user_scope()
    path = business / ".mb" / "connect.yaml"
    edited = yaml.safe_load(path.read_text(encoding="utf-8"))
    edited["repo_id"] = "foreign-unbound-id"
    path.write_text(yaml.safe_dump(edited), encoding="utf-8")

    result = c._record_validation(business, config, "stripe", entry)

    assert result == {"recorded": False, "not_recorded_reason": "repo_id_changed"}
    assert c._user_scope_provider_entry("foreign-unbound-id", "stripe") is None
    assert c._read_user_scope() == before


def test_validation_recording_refuses_an_unbound_id_in_the_file(tmp_path: Path) -> None:
    business = _user_scope_business(tmp_path)
    path = business / ".mb" / "connect.yaml"
    edited = yaml.safe_load(path.read_text(encoding="utf-8"))
    edited["repo_id"] = "foreign-unbound-id"
    path.write_text(yaml.safe_dump(edited), encoding="utf-8")
    config = c._read_config(business)

    result = c._record_validation(business, config, "stripe", dict(config["providers"]["stripe"]))

    assert result == {"recorded": False, "not_recorded_reason": "repo_binding_required"}
    assert c._user_scope_provider_entry("foreign-unbound-id", "stripe") is None


def test_rebind_text_says_only_the_owner_approves(tmp_path: Path) -> None:
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)

    refusal = _refused(c.read_token, "stripe", borrower)
    assert "only the owner may approve" in str(refusal)
    preview = c.rebind(borrower)
    assert "never adds --yes on its own" in preview["message"]


@pytest.mark.parametrize("terminal", [True, False])
def test_rebind_audits_before_allowing_and_status_shows_it(tmp_path, monkeypatch, terminal):
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: terminal)
    assert c.rebind(borrower, apply=True)["applied"]
    entries = c.read_release_audit(limit=2)
    entry = entries[0]
    assert entries[1]["result"] == "applied"
    assert entry["verb"] == "rebind"
    assert entry["result"] == "allowed"
    assert ("noninteractive" in entry["flags"]) is not terminal
    _no_key_in(entry)
    status = runner.invoke(app, ["connect", "status", "--repo", str(borrower), "--json"])
    assert json.loads(status.stdout)["recent_rebinds"] == entries
    assert json.loads(status.stdout)["recent_rebinds_state"] == "ok"
    text = runner.invoke(app, ["connect", "status", "--repo", str(borrower)])
    assert "Recent rebinds" in text.stdout


def test_rebind_audit_failure_does_not_allow_folder(tmp_path, monkeypatch):
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)

    def fail(*args, **kwargs):
        raise c.ConnectRefusal("audit_unavailable", "audit_unavailable")

    monkeypatch.setattr(c, "write_release_audit", fail)
    with pytest.raises(c.ConnectRefusal, match="audit_unavailable"):
        c.rebind(borrower, apply=True)
    _refused(c.read_token, "stripe", borrower)


def test_identity_ignores_git_environment_and_global_remote(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    global_config = tmp_path / "global-config"
    global_config.write_text('[remote "origin"]\nurl = https://example.com/foreign.git\n')
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".gitconfig").write_text(global_config.read_text())
    before = c._repo_identity(repo)
    assert before["source"] == "git_common_dir"
    _git(repo, "remote", "add", "origin", REMOTE)
    expected = c._repo_identity(repo)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "remote.origin.url")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://example.com/injected.git")
    monkeypatch.setenv(
        "GIT_CONFIG_PARAMETERS", "'remote.origin.url=https://example.com/override.git'"
    )
    assert c._repo_identity(repo) == expected


def test_identity_resolves_linked_worktree(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(
        repo,
        "-c",
        "user.name=Example",
        "-c",
        "user.email=example@example.com",
        "commit",
        "--allow-empty",
        "-qm",
        "initial",
    )
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", "-qb", "linked", str(linked))
    expected = c._repo_identity(repo)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "remote.origin.url")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://example.com/injected.git")
    assert c._repo_identity(linked) == expected


def test_rebind_already_allowed_records_preview(tmp_path):
    business = _business(tmp_path)

    result = c.rebind(business, apply=True)

    assert result["applied"] is False
    assert result["needed"] is False
    assert c.read_release_audit(limit=1)[0]["result"] == "preview"


@pytest.mark.parametrize("error", [None, OSError, ValueError])
def test_rebind_unavailable_stdin_records_noninteractive(tmp_path, monkeypatch, error):
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)

    class UnavailableStdin:
        def isatty(self):
            raise error("stdin unavailable")

    monkeypatch.setattr(sys, "stdin", None if error is None else UnavailableStdin())

    assert c.rebind(borrower, apply=True)["applied"] is True
    entry = c.read_release_audit(limit=2)[0]
    assert entry["result"] == "allowed"
    assert "noninteractive" in entry["flags"]


def test_recent_rebinds_survive_deeply_nested_audit_lines(tmp_path, monkeypatch):
    audit = tmp_path / "audit.log"
    audit.write_text("[" * 100000 + "0" + "]" * 100000 + "\n")
    monkeypatch.setattr(c, "audit_path", lambda: audit)
    assert c.recent_rebinds("fixture-id") == ([], "incomplete")


def test_recent_rebinds_keep_valid_lines_and_report_incomplete(tmp_path):
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)
    c.rebind(borrower, apply=True)
    entries = c.read_release_audit()
    with c.audit_path().open("ab") as stream:
        stream.write(b"{broken\n\xff\n[]\n")
    status = runner.invoke(app, ["connect", "status", "--repo", str(borrower), "--json"])
    result = json.loads(status.stdout)
    assert result["recent_rebinds"] == entries
    assert result["recent_rebinds_state"] == "incomplete"
    text = runner.invoke(app, ["connect", "status", "--repo", str(borrower)])
    assert "history is incomplete" in text.stdout


def test_recent_rebinds_unavailable_and_missing(tmp_path, monkeypatch):
    missing = tmp_path / "missing"
    monkeypatch.setattr(c, "audit_path", lambda: missing)
    assert c.recent_rebinds("fixture") == ([], "ok")
    monkeypatch.setattr(c, "audit_path", lambda: tmp_path)
    assert c.recent_rebinds("fixture") == ([], "unavailable")


def test_status_finishes_when_the_audit_path_is_a_named_pipe(tmp_path, monkeypatch):
    business = _business(tmp_path)
    audit = tmp_path / "audit.fifo"
    os.mkfifo(audit)
    monkeypatch.setattr(c, "audit_path", lambda: audit)
    outcome: list[Any] = []

    def run() -> None:
        outcome.append(runner.invoke(app, ["connect", "status", "--repo", str(business), "--json"]))

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout=10)
    if worker.is_alive():  # unblock the stuck open so the thread can end
        fd = os.open(audit, os.O_WRONLY | os.O_NONBLOCK)
        os.close(fd)
        worker.join(timeout=5)
        pytest.fail("mb connect status hung on a named pipe at the audit path")
    assert json.loads(outcome[0].stdout)["recent_rebinds_state"] == "unavailable"
    with pytest.raises(OSError):
        c.read_release_audit()


def test_audit_symlink_is_unavailable(tmp_path, monkeypatch):
    target = tmp_path / "real.jsonl"
    target.write_text("")
    link = tmp_path / "audit.jsonl"
    link.symlink_to(target)
    monkeypatch.setattr(c, "audit_path", lambda: link)
    assert c.recent_rebinds("fixture") == ([], "unavailable")
    with pytest.raises(OSError):
        c.read_release_audit()


def test_audit_readers_read_only_the_tail_and_skip_the_cut_line(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    row = {"verb": "rebind", "repo_id": "r", "ts": "t", "result": "applied", "flags": []}
    old = (json.dumps({**row, "result": "old"}) + "\n") * 3
    audit.write_text(old + json.dumps(row) + "\n")
    monkeypatch.setattr(c, "audit_path", lambda: audit)
    # A window that starts inside the old rows cuts one line in half.
    monkeypatch.setattr(c, "AUDIT_READ_MAX_BYTES", len(json.dumps(row)) + 20)
    rows, state = c.recent_rebinds("r")
    assert state == "ok"
    assert [entry["result"] for entry in rows] == ["applied"]
    assert [entry["result"] for entry in c.read_release_audit()] == ["applied"]


def test_failed_binding_records_outcome(tmp_path, monkeypatch):
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)

    def fail(*args):
        raise OSError("fixture write failure")

    monkeypatch.setattr(c, "_record_repo_binding", fail)
    with pytest.raises(OSError, match="fixture write failure"):
        c.rebind(borrower, apply=True)
    entries = c.read_release_audit(limit=2)
    assert [entry["result"] for entry in entries] == ["allowed", "failed"]
    assert entries[-1]["exit_code"] == 1


@pytest.mark.parametrize("binding_fails", [True, False])
def test_outcome_audit_failure_preserves_binding_result(tmp_path, monkeypatch, binding_fails):
    business = _business(tmp_path)
    borrower = _borrower(tmp_path, business)
    write = c.write_release_audit

    def audit(*args, **kwargs):
        if kwargs["result"] != "allowed":
            raise OSError("fixture audit failure")
        return write(*args, **kwargs)

    def fail(*args):
        raise OSError("fixture binding failure")

    monkeypatch.setattr(c, "write_release_audit", audit)
    if binding_fails:
        monkeypatch.setattr(c, "_record_repo_binding", fail)
        with pytest.raises(OSError, match="fixture binding failure"):
            c.rebind(borrower, apply=True)
    else:
        assert c.rebind(borrower, apply=True)["applied"]
    text = runner.invoke(app, ["connect", "status", "--repo", str(borrower)])
    assert "unconfirmed" in text.stdout
