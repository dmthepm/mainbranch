"""SSH-agent opt-in, using invented sockets and fixture runtimes only."""

from __future__ import annotations

import socket
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mb import agent_policy as ap
from mb import agent_up as au
from mb.agent_store import Store
from mb.cli import app
from tests.test_agent_check import Live, lv  # noqa: F401
from tests.test_agent_up import Up


@pytest.fixture
def ssh_socket(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    path = tmp_path_factory.getbasetemp() / "ssh.sock"
    with socket.socket(socket.AF_UNIX) as sock:
        sock.bind(str(path))
        yield str(path)
    path.unlink()


@pytest.mark.parametrize("runtime", ["claude", "codex"])
@pytest.mark.parametrize("setting", [None, False, True])
def test_ssh_agent_launch_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ssh_socket: str,
    runtime: str,
    setting: bool | None,
) -> None:
    u = Up(tmp_path)
    monkeypatch.setattr(au, "is_elf", lambda p: True)
    if runtime == "codex":
        (u.bin / "codex").write_bytes(u.runtime.read_bytes())
        (u.bin / "codex").chmod(0o755)
    row = u.row(runtime=runtime)
    if setting is not None:
        row["ssh_agent"] = setting
    u.write({"version": 1, "agents": [row]})
    env = {"SSH_AUTH_SOCK": ssh_socket}
    code, out, err = u.up(environ=env, dry_run=True)
    assert code == 0, err
    expected = (
        "env passed: SSH_AUTH_SOCK (value not shown)"
        if setting
        else "env dropped: row ssh_agent is off: SSH_AUTH_SOCK"
    )
    assert expected in out
    assert ssh_socket not in out + err
    code, out, err = u.up(environ=env)
    assert code == 0, err
    assert u.runs()[0]["env"].get("SSH_AUTH_SOCK") == (ssh_socket if setting else None)
    assert ("SSH_AUTH_SOCK" in u.last()["env_passed"]) is bool(setting)
    recorded = "".join(p.read_text() for p in u.store.rglob("*.json"))
    assert ssh_socket not in recorded + out + err


@pytest.mark.parametrize("setting", [None, False, True])
def test_bad_socket_is_checked_only_when_opted_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: bool | None
) -> None:
    u = Up(tmp_path)
    monkeypatch.setattr(au, "is_elf", lambda p: True)
    row = u.row()
    if setting is not None:
        row["ssh_agent"] = setting
    u.write({"version": 1, "agents": [row]})
    bad = str(tmp_path / "not-a-socket")
    Path(bad).touch()
    code, out, err = u.up(environ={"SSH_AUTH_SOCK": bad})
    assert code == (2 if setting else 0)
    assert bad not in out + err
    if setting:
        assert "bad-env:SSH_AUTH_SOCK" in err
        assert u.runs() == []


@pytest.mark.parametrize("runtime", ["claude", "codex"])
@pytest.mark.parametrize("value", ["true", 1, 0, None, [], {}])
def test_ssh_agent_requires_a_boolean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runtime: str, value: object
) -> None:
    u = Up(tmp_path)
    u.write({"version": 1, "agents": [u.row(runtime=runtime, ssh_agent=value)]})
    monkeypatch.setattr(ap.Host, "local", lambda: u.host)
    for args in (["agent", "check"], ["agent", "up", "planner", "--dry-run"]):
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 2
        assert "agents[0].ssh_agent: must be a boolean" in result.output


def test_off_row_with_ssh_socket_in_running_environment_is_mismatch(lv: Live) -> None:  # noqa: F811
    lv.runtime(env={**lv.env, "SSH_AUTH_SOCK": "/invented/ssh.sock"})
    code, text = lv.run()
    assert code == 1
    assert "environment: mismatch (env)" in text
    assert "/invented/ssh.sock" not in text


def test_check_uses_recorded_opt_in_decision_without_comparing_value(lv: Live) -> None:  # noqa: F811
    row = lv.u.row(ssh_agent=True)
    lv.u.write({"version": 1, "agents": [row]})
    lv.record["row_rev"] = au.row_rev(row)
    state = lv.u.state()
    state["planner"]["row_rev"] = lv.record["row_rev"]
    Store(lv.u.store, lv.u.host.uid).write_state(state)
    lv.record["env_passed"].append("SSH_AUTH_SOCK")
    lv.save()
    lv.runtime(env={**lv.env, "SSH_AUTH_SOCK": "/invented/changed.sock"})
    code, text = lv.run()
    assert code == 0, text
    lv.runtime(env=lv.env)
    assert lv.run()[0] == 1
