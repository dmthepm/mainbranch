"""mb agent check --smoke-marker, slice 2b: the smoke verdict on a fake /proc root.

No real claude runs and no process is forked for the chains: each test writes the process facts
(stat, environ, cwd, exe, cmdline) a runtime and its children would show, under a tmp directory
that stands in for /proc. The attempt comes from a real fixture ``up`` and is then pointed at the
fake pids. A fake ELF that "forks without exec and waits" is a chain whose middle process shows the
runtime's own exe.
"""

from __future__ import annotations

import io
import json
import os
import re
import signal
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import agent_smoke as sm
from mb import agent_up as au
from mb.cli import app
from tests.test_agent_up import Up, _default_signals

RUNTIME_PID, START, BOOT = 40001, 5000, "fake-boot-id"
MARKER_PID = 40100


class FakeProc:
    """A directory shaped like /proc, with only the files the smoke reads."""

    def __init__(self, root: Path, bin_dir: Path) -> None:
        self.root, self.bin = root, bin_dir
        (root / "sys/kernel/random").mkdir(parents=True)
        (root / "sys/kernel/random/boot_id").write_text(BOOT + "\n")

    def exe(self, name: str) -> Path:
        path = self.bin / name
        if not path.exists():
            path.write_text("x")
        return path

    def add(
        self,
        pid: int,
        ppid: int,
        exe: str,
        *,
        env: dict[str, str] | None = None,
        cwd: str = "/",
        cmdline: str = "x",
        start: int = 100,
    ) -> None:
        d = self.root / str(pid)
        d.mkdir(exist_ok=True)
        rest = ["S", str(ppid)] + ["0"] * 17 + [str(start)]
        (d / "stat").write_text(f"{pid} (x) " + " ".join(rest) + "\n")
        (d / "environ").write_bytes(b"\0".join(f"{k}={v}".encode() for k, v in (env or {}).items()))
        (d / "cmdline").write_bytes(cmdline.encode())
        for link, target in (("exe", str(self.exe(exe))), ("cwd", cwd)):
            if os.path.lexists(d / link):
                (d / link).unlink()
            (d / link).symlink_to(target)


class Smoke:
    def __init__(self, u: Up, proc: FakeProc, marker: Path) -> None:
        self.u, self.proc, self.marker = u, proc, marker
        u.up()
        record = u.last()
        st = os.stat(proc.exe("claude"))
        record.update(
            boot_id=BOOT,
            runtime_pid=RUNTIME_PID,
            runtime_start=START,
            runtime_real=str(proc.exe("claude")),
            runtime_id=[st.st_dev, st.st_ino],
        )
        path = u.store / "attempts" / f"{record['id']}.json"
        path.write_text(json.dumps(record))
        path.chmod(0o600)
        self.record = record
        self.env = {**record["env_set"], "TERM": "xterm"}
        record["env_passed"] = ["TERM"]
        path.write_text(json.dumps(record))
        self.runtime(env=self.env)

    def runtime(self, **kw: Any) -> None:
        kw.setdefault("env", self.env)
        kw.setdefault("cwd", self.record["cwd_real"])
        self.proc.add(
            RUNTIME_PID, 1, "claude", start=START, cmdline=f"claude\0--session-id\0{self.sid}", **kw
        )

    @property
    def sid(self) -> str:
        return str(self.record["session_id"])

    def chain(self, *middle: tuple[str, str]) -> None:
        """marker sh -> middle processes (exe, via fork/exec) -> the recorded runtime."""
        parent = RUNTIME_PID
        for i, (exe, _note) in enumerate(middle):
            pid = MARKER_PID + 10 + i
            self.proc.add(pid, parent, exe, env={"MB_ROLE": "other"}, cwd="/elsewhere")
            parent = pid
        self.proc.add(MARKER_PID, parent, "sh")
        self.marker.write_text(f"{MARKER_PID}\n")

    def run(self) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        code = sm.smoke(self.u.host, "planner", str(self.marker), out=out, err=err)
        return code, out.getvalue() + err.getvalue()


@pytest.fixture
def s(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Smoke]:
    u = Up(tmp_path)
    monkeypatch.setattr(au, "is_elf", lambda p: True)
    proc_root = tmp_path / "fakeproc"
    proc_root.mkdir()
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    fake = FakeProc(proc_root, bin_dir)
    monkeypatch.setattr(sm, "HELPERS", (str(bin_dir / "sh"), str(bin_dir / "bwrap")))
    smoke = Smoke(u, fake, tmp_path / "marker")  # its fixture `up` runs on the real /proc
    monkeypatch.setattr(au, "PROC", str(proc_root))
    yield smoke
    u.stop()


# --- the passing shapes ------------------------------------------------------------------


def test_a_tool_command_run_by_the_runtime_itself_passes(s: Smoke) -> None:
    s.chain()
    code, text = s.run()
    assert code == 0
    assert "smoke ok" in text and "evidence for this version" in text


def test_a_tool_command_under_a_listed_helper_passes(s: Smoke) -> None:
    s.chain(("sh", "shell"), ("bwrap", "sandbox helper"))
    assert s.run()[0] == 0


def test_eight_links_pass_and_nine_fail(s: Smoke) -> None:
    s.chain(*[("sh", "shell")] * 7)  # marker + 7 helpers: 8 links to the runtime
    assert s.run()[0] == 0
    s.chain(*[("sh", "shell")] * 8)
    code, text = s.run()
    assert code == 1 and "not-session-process" in text


# --- the waiting wrappers: the smoke fails them, so they never enter verified support ----


def test_a_fake_elf_that_forks_without_exec_and_waits_fails_not_session_process(s: Smoke) -> None:
    # the child is a fork of the runtime, so it still shows the runtime's exe; it did the work
    s.chain(("claude", "forked child, no exec"))
    code, text = s.run()
    assert code == 1 and "not-session-process" in text
    assert "runtime itself" in text


def test_a_fake_elf_that_execs_another_elf_not_on_the_helper_list_fails(s: Smoke) -> None:
    s.chain(("other-elf", "forked then exec'd"))
    code, text = s.run()
    assert code == 1 and "not-session-process" in text and "not a reviewed helper" in text


def test_a_passing_chain_with_one_unlisted_helper_fails(s: Smoke) -> None:
    s.chain(("sh", "shell"), ("node", "unlisted"), ("bwrap", "sandbox helper"))
    code, text = s.run()
    assert code == 1 and "not-session-process" in text


def test_a_waiting_parent_still_matches_its_environ_and_cwd_so_only_the_smoke_catches_it(
    s: Smoke,
) -> None:
    # the recorded pid matches the attempt exactly (what a live check would see)...
    s.chain(("claude", "forked child, no exec"))
    s.runtime()
    # ...and the verdict is still a failure, because the child ran the tool
    assert s.run()[0] == 1


def test_a_marker_whose_parents_never_reach_the_runtime_fails(s: Smoke) -> None:
    s.proc.add(MARKER_PID, 1, "sh")
    s.marker.write_text(str(MARKER_PID))
    code, text = s.run()
    assert code == 1 and "not-session-process" in text


# --- the recorded process itself ---------------------------------------------------------


def test_environ_name_or_mb_set_value_mismatch_is_exit_1_naming_the_field(s: Smoke) -> None:
    s.chain()
    s.runtime(env={**s.env, "MB_ROLE": "someone-else"})
    code, text = s.run()
    assert code == 1 and "environ" in text and "someone-else" not in text
    s.runtime(env={**s.env, "EXTRA": "1"})
    assert s.run()[0] == 1
    s.runtime(env={k: v for k, v in s.env.items() if k != "TERM"})
    assert s.run()[0] == 1


def test_a_passed_value_that_changed_is_not_compared(s: Smoke) -> None:
    s.chain()
    s.runtime(env={**s.env, "TERM": "other"})
    code, text = s.run()
    assert code == 0 and "passed values" in text and "not compared" in text


def test_cwd_mismatch_is_exit_1(s: Smoke) -> None:
    s.chain()
    s.runtime(cwd="/elsewhere")
    code, text = s.run()
    assert code == 1 and "cwd" in text


def test_a_changed_exe_is_exit_4_exe_changed(s: Smoke) -> None:
    s.chain()
    s.runtime()
    (s.proc.root / str(RUNTIME_PID) / "exe").unlink()
    (s.proc.root / str(RUNTIME_PID) / "exe").symlink_to(s.proc.exe("another-program"))
    code, text = s.run()
    assert code == 4 and "exe-changed" in text


def test_a_dead_runtime_is_exit_3_ended_and_a_reused_pid_is_dead(s: Smoke) -> None:
    s.chain()
    s.runtime()
    s.proc.add(RUNTIME_PID, 1, "claude", env=s.env, start=START + 1)
    assert s.run()[0] == 3
    for name in ("stat", "environ", "cmdline", "exe", "cwd"):
        (s.proc.root / str(RUNTIME_PID) / name).unlink()
    (s.proc.root / str(RUNTIME_PID)).rmdir()
    assert s.run()[0] == 3


def test_an_unreadable_environ_is_unknown_never_a_pass(s: Smoke) -> None:
    s.chain()
    (s.proc.root / str(RUNTIME_PID) / "environ").chmod(0)
    code, text = s.run()
    (s.proc.root / str(RUNTIME_PID) / "environ").chmod(0o600)
    assert code == 4 and "proc-denied" in text


def test_another_process_carrying_the_session_id_is_session_seen(s: Smoke) -> None:
    s.chain()
    s.proc.add(40200, 1, "claude", cmdline=f"claude\0--resume\0{s.sid}")
    code, text = s.run()
    assert code == 4 and "session-seen" in text and "40200" in text


# --- facts that fail to read, or change while read, are unknown (4), never a pass --------


def _denied(monkeypatch: pytest.MonkeyPatch, pid: int, exc: type[OSError]) -> None:
    real = os.stat

    def stat(path: Any, *a: Any, **k: Any) -> os.stat_result:
        if str(path) == f"{au.PROC}/{pid}/exe":
            raise exc(13, "injected")
        return real(path, *a, **k)

    monkeypatch.setattr(os, "stat", stat)


@pytest.mark.parametrize("exc", [PermissionError, FileNotFoundError])
def test_a_helper_exe_that_cannot_be_statted_is_unknown(
    s: Smoke, monkeypatch: pytest.MonkeyPatch, exc: type[OSError]
) -> None:
    s.chain(("sh", "shell"))
    _denied(monkeypatch, MARKER_PID + 10, exc)
    code, text = s.run()
    assert code == 4 and "smoke ok" not in text


def test_a_same_user_cmdline_that_cannot_be_read_makes_the_scan_incomplete(s: Smoke) -> None:
    s.chain()
    s.proc.add(40200, 1, "other")
    (s.proc.root / "40200" / "cmdline").chmod(0)
    code, text = s.run()
    (s.proc.root / "40200" / "cmdline").chmod(0o600)
    assert code == 4 and "scan-incomplete" in text


def test_a_process_that_exits_mid_scan_does_not_block_a_pass(s: Smoke) -> None:
    s.chain()
    s.proc.add(40200, 1, "other")
    (s.proc.root / "40200" / "cmdline").unlink()
    assert s.run()[0] == 0


def test_cmdline_hits_keeps_its_old_reading_of_an_unreadable_process(s: Smoke) -> None:
    s.chain()
    s.proc.add(40200, 1, "other", cmdline=s.sid)
    (s.proc.root / "40200" / "cmdline").chmod(0)
    try:
        assert 40200 not in au.cmdline_hits(s.sid, os.getuid())
        assert au.cmdline_scan(s.sid, os.getuid())[1] == [40200]
    finally:
        (s.proc.root / "40200" / "cmdline").chmod(0o600)


def _during_read(monkeypatch: pytest.MonkeyPatch, change: Any) -> None:
    """Run ``change`` once, after the chain's first facts were read and before the final check."""
    real = au.cmdline_scan

    def scan(*a: Any) -> tuple[list[int], list[int]]:
        change()
        return real(*a)

    monkeypatch.setattr(au, "cmdline_scan", scan)


def test_a_runtime_that_dies_during_the_read_is_unknown(
    s: Smoke, monkeypatch: pytest.MonkeyPatch
) -> None:
    s.chain()
    _during_read(
        monkeypatch, lambda: s.proc.add(RUNTIME_PID, 1, "claude", env=s.env, start=START + 1)
    )
    code, text = s.run()
    assert code == 4 and "changed" in text


def test_a_runtime_pid_reused_after_the_identity_check_is_unknown(
    s: Smoke, monkeypatch: pytest.MonkeyPatch
) -> None:
    s.chain()
    real = au.identity

    def identity(pid: int, start: int, boot: str) -> str:
        state = real(pid, start, boot)
        # the recorded runtime exits and a same-program process takes its pid
        s.proc.add(RUNTIME_PID, 1, "claude", env=s.env, start=START + 1)
        return state

    monkeypatch.setattr(au, "identity", identity)
    code, text = s.run()
    assert code == 4 and "changed" in text


def test_a_runtime_that_execs_during_the_read_is_unknown(
    s: Smoke, monkeypatch: pytest.MonkeyPatch
) -> None:
    s.chain()

    def swap() -> None:
        link = s.proc.root / str(RUNTIME_PID) / "exe"
        link.unlink()
        link.symlink_to(s.proc.exe("another-program"))

    _during_read(monkeypatch, swap)
    assert s.run()[0] == 4


def test_a_middle_process_that_execs_during_the_read_is_unknown(
    s: Smoke, monkeypatch: pytest.MonkeyPatch
) -> None:
    s.chain(("sh", "shell"))
    _during_read(monkeypatch, lambda: s.proc.add(MARKER_PID + 10, RUNTIME_PID, "node"))
    assert s.run()[0] == 4


def test_a_chain_pid_reused_between_its_parent_read_and_exe_read_is_unknown(
    s: Smoke, monkeypatch: pytest.MonkeyPatch
) -> None:
    s.chain(("sh", "shell"))
    middle, real = MARKER_PID + 10, sm._exe_id
    done: list[int] = []

    def exe_id(pid: int) -> tuple[int, int]:
        if pid == middle and not done:
            done.append(1)  # the old process is gone and a new one took the pid
            s.proc.add(middle, RUNTIME_PID, "sh", start=999)
        return real(pid)

    monkeypatch.setattr(sm, "_exe_id", exe_id)
    assert s.run()[0] == 4


def test_an_unlisted_path_replaced_by_a_link_to_a_listed_shell_fails_closed(
    s: Smoke, monkeypatch: pytest.MonkeyPatch
) -> None:
    s.chain(("node", "unlisted program"))
    real = sm._link

    def link(pid: int, name: str) -> str:  # the saved path now resolves to the listed shell
        return str(s.proc.exe("sh")) if (pid, name) == (MARKER_PID + 10, "exe") else real(pid, name)

    monkeypatch.setattr(sm, "_link", link)
    code, text = s.run()
    assert code == 4 and "helper-mismatch" in text


# --- inputs and refusals -----------------------------------------------------------------


@pytest.mark.parametrize("content", [None, "", "abc\n", "-5", "99999999999999999999", "1\n2\n"])
def test_a_missing_or_malformed_marker_is_no_marker(s: Smoke, content: str | None) -> None:
    if content is not None:
        s.marker.write_text(content)
    code, text = s.run()
    assert code == 4 and "no-marker" in text


def test_a_marker_pid_that_is_not_running_is_no_marker(s: Smoke) -> None:
    s.marker.write_text("40999")
    assert s.run()[0] == 4


def test_no_attempt_for_the_agent_is_no_session_evidence(s: Smoke) -> None:
    s.chain()
    (s.u.store / "state.json").unlink()
    code, text = s.run()
    assert code == 4 and "no-session-evidence" in text


def test_the_output_never_shows_an_environment_value(s: Smoke) -> None:
    s.chain()
    s.runtime(env={**s.env, "TERM": "secret-terminal-value-91"})
    _, text = s.run()
    assert "secret-terminal-value-91" not in text and s.env["HOME"] not in text


def test_the_built_in_helper_list_is_short_and_names_shells_and_the_sandbox_helper() -> None:
    names = {os.path.basename(p) for p in sm.DEFAULT_HELPERS}
    assert {"sh", "bash", "dash", "bwrap"} <= names and len(sm.DEFAULT_HELPERS) <= 10
    assert all(p.startswith("/") for p in sm.DEFAULT_HELPERS)


def test_the_cli_requires_a_name_with_the_flag_and_keeps_the_policy_check_without_it() -> None:
    result = CliRunner().invoke(app, ["agent", "check", "--smoke-marker", "/nowhere/marker"])
    assert result.exit_code == 2 and "agent name" in result.output
    # CI renders help in colour; strip the escapes so the flag name is one string.
    help_text = re.sub(
        r"\x1b\[[0-9;]*m", "", CliRunner().invoke(app, ["agent", "check", "--help"]).output
    )
    assert "--smoke-marker" in help_text


# --- the holder starts with odd signal state and the runtime still sees defaults ---------


def _odd_signals() -> None:
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    signal.pthread_sigmask(signal.SIG_BLOCK, [signal.SIGUSR2])


def _status_bits(text: str) -> tuple[int, int]:
    rows = dict(line.split(":\t", 1) for line in text.splitlines() if ":\t" in line)
    return int(rows["SigIgn"], 16), int(rows["SigBlk"], 16)


def test_a_holder_started_with_sighup_ignored_and_a_signal_blocked_runs_a_clean_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    u = Up(tmp_path)
    hup, usr2 = 1 << (signal.SIGHUP - 1), 1 << (signal.SIGUSR2 - 1)
    probe = "print(open('/proc/self/status').read())"
    seeded = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        preexec_fn=_odd_signals,
    ).stdout
    ign, blk = _status_bits(seeded)
    assert ign & hup and blk & usr2  # the seed works: a plain child inherits both
    clean = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        preexec_fn=_default_signals,
    ).stdout
    # run the real holder in a driver process started with the same odd state
    cfg = {"home": str(u.home), "floor": str(u.floor), "path": [str(u.bin)], "name": "planner"}
    driver = subprocess.run(
        [sys.executable, "-c", _driver(), json.dumps(cfg)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        preexec_fn=_odd_signals,
        timeout=30,
    )
    assert driver.returncode == 0, driver.stderr
    (run,) = u.runs()
    assert int(run["sigign"], 16) == _status_bits(clean)[0]  # only the fixture Python's own
    assert int(run["sigign"], 16) & hup == 0
    assert int(run["sigblk"], 16) == 0 and int(run["sigblk"], 16) & usr2 == 0


def _driver() -> str:
    return (
        "import json, os, sys\n"
        "from mb import agent_policy as ap, agent_up as au\n"
        "cfg = json.loads(sys.argv[1])\n"
        "host = ap.Host(home=cfg['home'], uid=os.getuid(), floor=cfg['floor'],\n"
        "               default_path=tuple(cfg['path']))\n"
        "au.is_elf = lambda p: True\n"
        "sys.exit(au.up(host, cfg['name'], new=True, environ={}))\n"
    )
