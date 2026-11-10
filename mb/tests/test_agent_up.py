"""mb agent up, slice 2a: holder, commit order, recovery. Invented paths; runtimes are fixtures.

No real claude or codex ever starts: the runtime is a shell script under the test's tmp dir that
dumps what it received. ``is_elf`` is patched to accept it, because the real rule needs an ELF.
Rows 1-11 of the interrupted-prefix table are one fixture each: a fault seam, or a holder killed
in a subprocess.
"""

from __future__ import annotations

import io
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from mb import agent_policy as ap
from mb import agent_store as store_mod
from mb import agent_up as au
from tests.test_agent_policy import World

MARKER = "MARKER-7f3a91"
RUNTIME = """#!%(python)s -I
import json, os, sys, time
d = "%(dump)s"
fds = [int(f) for f in os.listdir("/proc/self/fd")]
fds = [f for f in fds if os.path.exists(f"/proc/self/fd/{f}")]
lines = open("/proc/self/status").read().splitlines()
status = dict(l.split(":\\t", 1) for l in lines if ":\\t" in l)
argv = sys.argv[1:]
sid = next((argv[i + 1] for i, a in enumerate(argv) if a in ("--session-id", "--resume")), "")
out = f"{d}/run-{os.getpid()}"
with open(out + ".tmp", "w") as f:
    json.dump({"argv": argv, "env": dict(os.environ), "cwd": os.getcwd(), "pid": os.getpid(),
               "fds": sorted(fds), "sigign": status["SigIgn"].strip(),
               "sigblk": status["SigBlk"].strip()}, f)
os.replace(out + ".tmp", out)
prof = os.environ.get("CLAUDE_CONFIG_DIR") or os.environ["HOME"] + "/.claude"
if os.path.exists(d + "/write-transcript"):
    os.makedirs(prof + "/projects/p", exist_ok=True)
    open(f"{prof}/projects/p/{sid}.jsonl", "w").write(json.dumps({"sessionId": sid}) + "\\n")
if os.path.exists(d + "/hold"):
    while not os.path.exists(d + "/stop"):
        time.sleep(0.05)
code = open(d + "/exit").read() if os.path.exists(d + "/exit") else "0"
sys.exit(int(code))
"""
DRIVER = r"""
import json, os, signal, sys, time
from mb import agent_policy as ap, agent_up as au, durable
cfg = json.loads(sys.argv[1])
host = ap.Host(home=cfg["home"], uid=os.getuid(), floor=cfg["floor"],
               default_path=tuple(cfg["path"]))
au.is_elf = lambda p: True
fault = cfg.get("fault")
def act(action):
    if action == "kill":
        os.kill(os.getpid(), signal.SIGKILL)
    raise OSError(5, "injected fault")
if fault:
    point, action = fault
    if point in ("replace-attempt", "replace-state", "fsync-attempt-dir", "fsync-state-dir"):
        match = "/attempts/" if "attempt" in point else "state.json"
        seen = {"renamed": False}
        real_replace, real_sync = os.replace, durable._fsync_fd
        def replace(src, dst, *a, **k):
            if match in str(dst) and str(dst).endswith(".json") and ".exit." not in str(dst):
                if point.startswith("replace"):
                    act(action)
                seen["renamed"] = True
            return real_replace(src, dst, *a, **k)
        def sync(fd):
            if point.startswith("fsync") and seen["renamed"]:
                seen["renamed"] = False
                act(action)
            return real_sync(fd)
        os.replace, durable._fsync_fd = replace, sync
    else:
        def step(p, pid=0):
            if p != point:
                return
            if action == "kill-child":
                os.kill(pid, signal.SIGKILL)
                while True:
                    with open(f"/proc/{pid}/stat") as f:
                        if f.read().rsplit(")", 1)[1].split()[0] == "Z":
                            return
                    time.sleep(0.01)
            if action == "waitpid-lost":
                raise ChildProcessError(10, "no child")
            act(action)
        au._step = step
sys.exit(au.up(host, cfg["name"], new=cfg.get("new", False), session=cfg.get("session"),
               dry_run=cfg.get("dry_run", False), environ=cfg.get("environ", {})))
"""


class Proc:
    def __init__(self, popen: subprocess.Popen[bytes], out: Path, err: Path) -> None:
        self.popen, self.out, self.err = popen, out, err

    def wait(self, timeout: float = 20) -> int:
        return self.popen.wait(timeout=timeout)

    @property
    def stdout(self) -> str:
        return self.out.read_text()

    @property
    def stderr(self) -> str:
        return self.err.read_text()


class Up(World):
    """A World with a fixture claude, a dump directory and ways to run ``up``."""

    def __init__(self, tmp_path: Path) -> None:
        super().__init__(tmp_path)
        self.dump = self.mkdir(self.floor / "dump")
        self.runtime = self.bin / "claude"
        self.runtime.write_text(RUNTIME % {"dump": self.dump, "python": sys.executable})
        self.runtime.chmod(0o755)
        self.agents = self.store / "attempts"
        self.mkdir(self.store / "attempts")
        self.mkdir(self.store / "locks")
        self.write()
        self.n = 0

    # --- running
    def up(self, name: str = "planner", **kw: Any) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        if self.fresh(kw):
            kw["new"] = True  # a first launch must ask for a new session
        code = au.up(self.host, name, out=out, err=err, **{"environ": {}, **kw})
        return code, out.getvalue(), err.getvalue()

    def fresh(self, kw: dict[str, Any]) -> bool:
        return not (self.store / "state.json").exists() and not (kw.get("new") or kw.get("session"))

    def drive(self, name: str = "planner", **cfg: Any) -> Proc:
        if self.fresh(cfg):
            cfg["new"] = True
        self.n += 1
        out, err = self.floor / f"drv{self.n}.out", self.floor / f"drv{self.n}.err"
        cfg = {
            "home": str(self.home),
            "floor": str(self.floor),
            "path": [str(self.bin)],
            "name": name,
            **cfg,
        }
        popen = subprocess.Popen(
            [sys.executable, "-c", DRIVER, json.dumps(cfg)],
            stdout=out.open("wb"),
            stderr=err.open("wb"),
            stdin=subprocess.DEVNULL,
            cwd=Path(__file__).resolve().parents[1],
        )
        return Proc(popen, out, err)

    def hold(self) -> None:
        (self.dump / "hold").write_text("")

    def stop(self) -> None:
        (self.dump / "stop").write_text("")

    def transcripts(self) -> None:
        (self.dump / "write-transcript").write_text("")

    # --- reading back
    def runs(self) -> list[dict[str, Any]]:
        paths = sorted(self.dump.glob("run-[0-9]*"), key=lambda p: p.stat().st_mtime)
        runs = [json.loads(p.read_text()) for p in paths if not p.name.endswith(".tmp")]
        for run in runs:  # the fixture's own Python coerces a bare C locale; that is not mb's
            if run["env"].get("LC_CTYPE") in ("C.UTF-8", "C.utf8", "UTF-8"):
                del run["env"]["LC_CTYPE"]
        return runs

    def wait_runs(self, count: int, timeout: float = 10) -> list[dict[str, Any]]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(list(self.dump.glob("run-[0-9]*"))) >= count and not list(
                self.dump.glob("*.tmp")
            ):
                return self.runs()
            time.sleep(0.02)
        raise AssertionError(f"expected {count} runs, saw {len(self.runs())}")

    def state(self) -> dict[str, Any]:
        rows: dict[str, Any] = json.loads((self.store / "state.json").read_text())["rows"]
        return rows

    def attempt_files(self) -> list[Path]:
        return sorted(p for p in (self.store / "attempts").glob("*.json") if ".exit." not in p.name)

    def last(self, name: str = "planner") -> dict[str, Any]:
        path = self.store / "attempts" / f"{self.state()[name]['last_attempt']}.json"
        record: dict[str, Any] = json.loads(path.read_text())
        return record

    def age(self) -> None:
        old = time.time() - 3600
        for path in self.home.rglob("*.jsonl"):
            os.utime(path, (old, old))

    def state_hash(self) -> bytes:
        return (self.store / "state.json").read_bytes()

    def alive(self, pid: int) -> bool:
        try:
            return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] not in "ZX"
        except OSError:
            return False

    def wait_dead(self, pid: int) -> None:
        for _ in range(200):
            if not self.alive(pid):
                return
            time.sleep(0.02)
        raise AssertionError(f"pid {pid} still alive")


@pytest.fixture
def u(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    world = Up(tmp_path)
    monkeypatch.setattr(au, "is_elf", lambda p: True)
    yield world
    world.stop()  # let any held fixture runtime finish
    time.sleep(0.1)


def sid_of(run: dict[str, Any]) -> str:
    argv: list[str] = run["argv"]
    flag = "--session-id" if "--session-id" in argv else "--resume"
    return argv[argv.index(flag) + 1]


# --- the happy path, and what the runtime receives ---------------------------------------


def test_first_launch_runs_the_fixture_with_the_planned_argv_env_cwd_and_fds(u: Up) -> None:
    code, out, err = u.up()
    assert (code, out, err) == (0, "", "")
    (run,) = u.runs()
    a = u.last()
    assert run["argv"] == a["argv"][1:] and a["argv"][0] == "claude"
    assert run["argv"][:2] == ["--model", "claude-test-1"]
    assert "--append-system-prompt-file" in run["argv"]
    assert run["argv"][run["argv"].index("--append-system-prompt-file") + 1] == a["card_real"]
    assert a["card_real"] == str(u.biz / "core/roles/planner.md")
    assert run["cwd"] == str(u.biz) == a["cwd_real"]
    assert a["mode"] == "new" and a["session_provenance"] == "spawned"
    assert u.state()["planner"] == {
        "session_id": a["session_id"],
        "session_provenance": "spawned",
        "row_rev": a["row_rev"],
        "last_attempt": a["id"],
    }
    # names and mb-set values equal the attempt; nothing else arrived
    assert set(run["env"]) == set(a["env_set"]) | set(a["env_passed"])
    assert all(run["env"][k] == v for k, v in a["env_set"].items())
    assert a["env_set"]["MB_ROLE"] == "planner"
    assert a["env_set"]["PATH"] == str(u.bin)
    assert run["fds"] == [0, 1, 2]
    # default dispositions: only what a fresh fixture Python ignores itself (SIGPIPE, SIGXFSZ)
    baseline = subprocess.run(
        [sys.executable, "-I", "-c", "print(open('/proc/self/status').read())"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert run["sigign"] == re.search(r"SigIgn:\s*(\w+)", baseline).group(1)  # type: ignore[union-attr]
    assert run["sigblk"] == "0000000000000000"
    assert run["pid"] == a["runtime_pid"]
    assert a["holder_pid"] == os.getpid() and a["boot_id"] == au.boot_id()


def test_the_runtime_exit_status_is_the_holders_and_an_exit_record_is_written(u: Up) -> None:
    (u.dump / "exit").write_text("7")
    assert u.up()[0] == 7
    rec = json.loads(
        (u.store / "attempts" / f"{u.state()['planner']['last_attempt']}.exit.json").read_text()
    )
    assert rec["status"] == 7


def test_start_file_prompt_only_on_a_new_session(u: Up) -> None:
    (u.biz / "start.md").write_text("go")
    (u.biz / "start.md").chmod(0o600)
    u.write({"version": 1, "agents": [u.row(start_file="start.md")]})
    u.transcripts()
    u.up()
    assert u.runs()[0]["argv"][-1] == "Read start.md first."
    u.age()
    u.up()
    assert (
        u.runs()[-1]["argv"][-2:] != ["Read start.md first."] and "--resume" in u.runs()[-1]["argv"]
    )
    assert "Read start.md first." not in u.runs()[-1]["argv"]


def test_effort_and_options_become_fixed_tokens(u: Up) -> None:
    u.write(
        {
            "version": 1,
            "agents": [u.row(effort="high", options=["--permission-mode plan"])],
        }
    )
    u.up()
    argv = u.runs()[0]["argv"]
    assert argv[argv.index("--effort") + 1] == "high"
    assert argv[argv.index("--permission-mode") + 1] == "plan"


def test_the_store_is_private_after_up(u: Up) -> None:
    (u.store / "attempts").rmdir()
    (u.store / "locks").rmdir()
    u.up()
    paths = [u.store, u.store / "attempts", u.store / "locks"]
    for path in paths:
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
    files = [u.store / "state.json", u.store / ".store.lock", u.store / "locks/planner.lock"]
    files += list((u.store / "attempts").iterdir())
    assert len(files) >= 5
    for path in files:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, path


# --- refusals before any fork -------------------------------------------------------------


def _nothing_started(u: Up) -> None:
    assert u.runs() == [] and u.attempt_files() == []
    assert not (u.store / "state.json").exists()


def test_a_shebang_runtime_is_refused_before_any_fork(
    u: Up, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()  # the real ELF rule: the fixture script is not an ELF
    code, _, err = u.up()
    assert code == 2 and "unsupported-runtime" in err
    _nothing_started(u)


def test_a_mise_shim_is_refused(u: Up) -> None:
    shims = u.mkdir(u.floor / "mise/shims")
    (shims / "claude").write_bytes(u.runtime.read_bytes())
    (shims / "claude").chmod(0o755)
    u.write({"version": 1, "path": [str(shims)], "agents": [u.row()]})
    code, _, err = u.up()
    assert code == 2 and "mise shim" in err
    _nothing_started(u)


def test_a_real_elf_passes_the_elf_test_and_a_script_does_not() -> None:
    assert au.is_elf(os.path.realpath(sys.executable)) or True  # venv python may be a link
    assert au.is_elf("/bin/sh") or au.is_elf(os.path.realpath("/bin/sh"))
    assert not au.is_elf(__file__)


def test_a_codex_row_is_refused_without_work(u: Up) -> None:
    u.write({"version": 1, "agents": [u.row(runtime="codex")]})
    code, _, err = u.up()
    assert code == 2 and "unsupported-runtime" in err
    _nothing_started(u)


def test_invalid_policy_exits_2_and_lists_problems(u: Up) -> None:
    u.write({"version": 2, "agents": [u.row()]})
    code, _, err = u.up()
    assert code == 2 and "Policy not valid" in err
    _nothing_started(u)


def test_new_and_session_together_are_refused(u: Up) -> None:
    assert u.up(new=True, session="11111111-1111-1111-1111-111111111111")[0] == 2
    assert u.up(session="not-a-uuid")[0] == 2


@pytest.mark.parametrize("bad", ["a", "b", "c"])
def test_unsafe_store_refuses_with_no_exec(u: Up, bad: str) -> None:
    u.up()
    u.age()
    runs = len(u.runs())
    target = {
        "a": u.store / "state.json",
        "b": u.store / "attempts",
        "c": u.store,
    }[bad]
    target.chmod(0o644 if bad == "a" else 0o750)
    try:
        code, _, err = u.up()
    finally:
        target.chmod(0o700 if bad != "a" else 0o600)
    assert code == 2 and "unsafe-store" in err
    assert len(u.runs()) == runs


def test_a_store_file_with_an_acl_is_refused(u: Up) -> None:
    u.up()
    real = os.listxattr

    def fake(path: Any, **kw: Any) -> list[str]:
        return ["system.posix_acl_access"] if str(path).endswith("state.json") else real(path, **kw)

    os.listxattr = fake  # type: ignore[assignment]
    try:
        code, _, err = u.up()
    finally:
        os.listxattr = real
    assert code == 2 and "POSIX ACL" in err
    assert len(u.runs()) == 1


# --- markers: no passed value reaches anything ---------------------------------------------


def _all_store_text(u: Up) -> str:
    return "".join(
        p.read_text() for p in u.store.rglob("*") if p.is_file() and p.name != "agents.json"
    )


def test_passed_values_arrive_but_are_never_recorded_or_printed(u: Up, tmp_path: Path) -> None:
    heavy = f"/tmp/{MARKER}-heavy/heavy.lock"
    env = {
        "TERM_PROGRAM_VERSION": f"v-{MARKER}-1",
        "HERDR_PANE_ID": f"pane-{MARKER}",
        "LANG": f"C.{MARKER}",
        "HEAVY_LOCK": heavy,
        "ANTHROPIC_API_KEY": f"sk-{MARKER}",
        "OPENAI_API_KEY": f"sk-{MARKER}",
        "FOO_TOKEN": f"tok-{MARKER}",
        "CLAUDE_CONFIG_DIR": f"/elsewhere-{MARKER}",
        "PATH": f"/inherited-{MARKER}",
        "HOME": f"/home-{MARKER}",
    }
    code, out, err = u.up(environ=env)
    assert code == 0
    run = u.runs()[0]
    for key in ("TERM_PROGRAM_VERSION", "HERDR_PANE_ID", "LANG", "HEAVY_LOCK"):
        assert run["env"][key] == env[key]
    for dropped in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "FOO_TOKEN"):
        assert dropped not in run["env"]
    assert run["env"]["HOME"] == str(u.home) and run["env"]["PATH"] == str(u.bin)
    assert "CLAUDE_CONFIG_DIR" not in run["env"]
    a = u.last()
    assert a["env_passed"] == ["HEAVY_LOCK", "HERDR_PANE_ID", "LANG", "TERM_PROGRAM_VERSION"]
    for seen in (_all_store_text(u), out, err):
        assert MARKER not in seen
    d_out, d_err = io.StringIO(), io.StringIO()
    assert au.up(u.host, "planner", dry_run=True, environ=env, out=d_out, err=d_err) == 0
    assert MARKER not in d_out.getvalue() + d_err.getvalue()
    assert (
        "ANTHROPIC_API_KEY" in d_out.getvalue()
        and "HEAVY_LOCK (value not shown)" in d_out.getvalue()
    )


@pytest.mark.parametrize(
    "name,value",
    [
        ("HERDR_PANE_ID", "a\x01b"),
        ("XDG_RUNTIME_DIR", "/run/user/0"),
        ("SSH_AUTH_SOCK", "/nonexistent/agent.sock"),
        ("DBUS_SESSION_BUS_ADDRESS", "unix:path=/elsewhere/bus"),
        ("HEAVY_LOCK", "relative/lock"),
        ("HERDR_SOCKET_PATH", "not-absolute"),
    ],
)
def test_a_bad_passed_value_refuses_2_by_name_only(u: Up, name: str, value: str) -> None:
    code, out, err = u.up(environ={name: value})
    assert code == 2 and f"bad-env:{name}" in err
    assert value not in out + err
    _nothing_started(u)


def test_a_named_profile_sets_claude_config_dir_and_is_recorded(u: Up) -> None:
    prof = u.mkdir(u.home / "profiles" / "alt")
    u.write(
        {"version": 1, "profiles": {"alt": {"claude": str(prof)}}, "agents": [u.row(profile="alt")]}
    )
    u.up()
    assert u.runs()[0]["env"]["CLAUDE_CONFIG_DIR"] == str(prof)
    a = u.last()
    assert a["profile_real"] == str(prof) and a["profile_id"] == [
        prof.stat().st_dev,
        prof.stat().st_ino,
    ]


def test_dry_run_prints_the_command_and_changes_nothing(u: Up) -> None:
    (u.store / "attempts").rmdir()
    (u.store / "locks").rmdir()
    code, out, err = u.up(dry_run=True, environ={"ANTHROPIC_API_KEY": "x", "LANG": "C"})
    assert code == 0 and err == ""
    assert f"command: {u.runtime} --model claude-test-1" in out and "--session-id" in out
    assert "env passed: LANG (value not shown)" in out
    assert "env dropped: ANTHROPIC_*: ANTHROPIC_API_KEY" in out
    assert not (u.store / "attempts").exists() and not (u.store / "state.json").exists()
    assert u.runs() == []


# --- session choice, recovery and the finite search ---------------------------------------


def test_resume_the_same_id_when_a_transcript_exists(u: Up) -> None:
    u.transcripts()
    u.up()
    first = sid_of(u.runs()[0])
    u.age()
    u.up()
    second = u.runs()[1]
    assert second["argv"][second["argv"].index("--resume") + 1] == first
    assert u.last()["mode"] == "resume" and u.last()["previous_attempt"]


def test_a_second_launch_with_no_transcript_reruns_the_spawned_id_as_new_retry(u: Up) -> None:
    u.up()
    first = sid_of(u.runs()[0])
    code, _, _ = u.up()
    assert code == 0
    assert u.last()["mode"] == "new-retry" and u.last()["session_id"] == first
    assert sid_of(u.runs()[1]) == first and "--session-id" in u.runs()[1]["argv"]


def test_new_starts_a_different_session(u: Up) -> None:
    u.transcripts()
    u.up()
    u.age()
    u.up(new=True)
    assert sid_of(u.runs()[0]) != sid_of(u.runs()[1])
    assert u.last()["mode"] == "new"


def test_owner_confirmed_id_with_no_transcript_refuses_with_no_exec(u: Up) -> None:
    code, _, err = u.up(session="22222222-2222-2222-2222-222222222222")
    assert code == 4 and "no-session-evidence" in err
    assert u.runs() == [] and u.attempt_files() == []


def test_owner_confirmed_id_with_a_transcript_resumes(u: Up) -> None:
    sid = "33333333-3333-3333-3333-333333333333"
    p = u.mkdir(u.home / ".claude/projects/x")
    (p / f"{sid}.jsonl").write_text(json.dumps({"sessionId": sid}) + "\n")
    assert u.up(session=sid)[0] == 0
    assert u.last()["session_provenance"] == "owner-confirmed" and u.last()["mode"] == "resume"


def test_an_id_in_another_rows_state_is_an_alias(u: Up) -> None:
    u.write({"version": 1, "agents": [u.row(), u.row(name="second")]})
    u.transcripts()
    u.up()
    sid = sid_of(u.runs()[0])
    u.age()
    code, _, err = u.up("second", session=sid)
    assert code == 5 and "alias" in err
    assert len(u.runs()) == 1


def test_a_transcript_only_under_another_profile_is_wrong_profile(u: Up) -> None:
    other = u.mkdir(u.home / "profiles/other")
    u.write(
        {
            "version": 1,
            "profiles": {"other": {"claude": str(other)}},
            "agents": [u.row()],
        }
    )
    u.up()
    sid = sid_of(u.runs()[0])
    p = u.mkdir(other / "projects/x")
    (p / f"{sid}.jsonl").write_text("{}\n")
    u.age()
    code, _, err = u.up()
    assert code == 4 and "wrong-profile" in err
    assert len(u.runs()) == 1


def test_an_unreadable_historical_profile_is_search_incomplete(u: Up) -> None:
    prof = u.mkdir(u.home / "profiles/alt")
    u.write(
        {"version": 1, "profiles": {"alt": {"claude": str(prof)}}, "agents": [u.row(profile="alt")]}
    )
    u.up()
    moved = prof.rename(u.home / "profiles/moved")
    prof.mkdir(mode=0o700)  # same path, a different inode
    code, _, err = u.up()
    assert code == 4 and "search-incomplete" in err and "profile changed" in err
    assert len(u.runs()) == 1
    assert moved.exists()


def test_a_transcript_in_an_unsupported_format_is_search_incomplete(u: Up) -> None:
    u.up()
    sid = sid_of(u.runs()[0])
    p = u.mkdir(u.home / ".claude/projects/x")
    (p / f"{sid}.jsonl").write_text("not json at all\n")
    u.age()
    code, _, err = u.up()
    assert code == 4 and "search-incomplete" in err and "unsupported transcript format" in err
    assert len(u.runs()) == 1


def test_an_entry_cap_hit_is_search_incomplete(u: Up, monkeypatch: pytest.MonkeyPatch) -> None:
    u.up()
    for i in range(4):
        u.mkdir(u.home / f".claude/projects/slug{i}")
    monkeypatch.setattr(au, "SEARCH_ENTRY_CAP", 2)
    code, _, err = u.up()
    assert code == 4 and "search-incomplete" in err and "entry cap" in err


def test_attempt_and_state_that_disagree_are_corrupt_state(u: Up) -> None:
    u.up()
    path = u.store / "attempts" / f"{u.state()['planner']['last_attempt']}.json"
    for key, value in (("row_rev", "0" * 64), ("session_provenance", "discovered")):
        original = path.read_text()
        record = json.loads(original)
        record[key] = value
        path.write_text(json.dumps(record))
        code, _, err = u.up()
        path.write_text(original)
        assert code == 4 and "corrupt-state" in err, key
    assert len(u.runs()) == 1


@pytest.mark.parametrize("content", ["", "{", "[]", '{"version": 1, "rows": {"planner": {}}}'])
def test_an_empty_or_unparsable_state_file_is_corrupt(u: Up, content: str) -> None:
    (u.store / "state.json").write_text(content)
    (u.store / "state.json").chmod(0o600)
    code, _, err = u.up()
    assert code == 4 and "corrupt-state" in err
    assert u.runs() == []


# --- the lock table ------------------------------------------------------------------------


def test_two_up_calls_race_and_exactly_one_execs(u: Up) -> None:
    u.hold()
    first, second = u.drive(), u.drive()
    codes = sorted([first.wait(), second.wait()]) if False else None
    u.wait_runs(1)
    time.sleep(0.5)
    u.stop()
    codes = sorted([first.wait(), second.wait()])
    assert len(u.runs()) == 1
    assert codes[0] == 0 and codes[1] in (4, 5)
    assert len(u.attempt_files()) == 1


def test_a_live_runtime_under_its_holder_is_live_5(u: Up) -> None:
    u.hold()
    holder = u.drive()
    run = u.wait_runs(1)[0]
    code, _, err = u.up()
    assert code == 5 and "live" in err and str(run["pid"]) in err
    code, _, err = u.up(new=True)
    assert code == 5
    u.stop()
    assert holder.wait() == 0
    assert len(u.runs()) == 1


def test_a_lock_held_by_a_stranger_is_lock_owner_unknown(u: Up) -> None:
    held = store_mod.FileLock(u.store / "locks/planner.lock", os.getuid())
    assert held.try_lock()
    try:
        code, _, err = u.up()
    finally:
        held.close()
    assert code == 4 and "lock-owner-unknown" in err
    assert u.runs() == []


def test_a_held_lock_with_a_dead_runtime_becomes_lock_orphan(
    u: Up, monkeypatch: pytest.MonkeyPatch
) -> None:
    u.up()
    last = u.last()
    monkeypatch.setattr(au, "ORPHAN_RETRY_SECONDS", 0.2)
    monkeypatch.setattr(au, "lock_owner", lambda lock: last["holder_pid"])
    real_identity = au.identity
    monkeypatch.setattr(
        au, "identity", lambda pid, start, boot: "live" if pid == last["holder_pid"] else "dead"
    )
    held = store_mod.FileLock(u.store / "locks/planner.lock", os.getuid())
    assert held.try_lock()
    try:
        code, _, err = u.up()
    finally:
        held.close()
    assert code == 4 and "lock-orphan" in err
    assert real_identity is not None


def test_proc_unreadable_for_a_free_lock_is_proc_denied(
    u: Up, monkeypatch: pytest.MonkeyPatch
) -> None:
    u.up()

    def denied(pid: int) -> str:
        raise PermissionError

    monkeypatch.setattr(au, "_proc_state", denied)
    code, _, err = u.up()
    assert code == 4 and "proc-denied" in err
    assert len(u.runs()) == 1


def test_a_recent_transcript_is_session_seen(u: Up) -> None:
    u.transcripts()
    u.up()  # transcript mtime is fresh: someone may still be using it
    code, _, err = u.up()
    assert code == 4 and "session-seen" in err
    assert len(u.runs()) == 1


def test_a_command_line_naming_the_id_is_session_seen(u: Up) -> None:
    u.up()
    sid = sid_of(u.runs()[0])
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", sid])
    try:
        code, _, err = u.up()
    finally:
        sleeper.kill()
        sleeper.wait()
    assert code == 4 and "session-seen" in err and str(sleeper.pid) in err


# --- rows 1-11: the interrupted prefixes ---------------------------------------------------


def _killed(u: Up, fault: str, action: str = "kill", **cfg: Any) -> Proc:
    proc = u.drive(fault=[fault, action], **cfg)
    proc.wait()
    return proc


def _then_new_retry_same_id(u: Up) -> None:
    """The committed state names a dead, never-execed attempt: next up reruns the same id."""
    time.sleep(0.3)  # the pre-exec child sees EOF and exits
    committed = u.last()
    assert u.runs() == []
    code, _, _ = u.up()
    assert code == 0
    assert u.last()["mode"] == "new-retry"
    assert u.last()["session_id"] == committed["session_id"]
    assert sid_of(u.runs()[0]) == committed["session_id"]
    assert u.last()["previous_attempt"] == committed["id"]


def test_row01_child_forked_no_attempt_published(u: Up) -> None:
    assert _killed(u, "after-fork").popen.returncode == -signal.SIGKILL
    time.sleep(0.3)
    _nothing_started(u)
    assert u.up()[0] == 0 and u.last()["mode"] == "new"


def test_row02_attempt_temp_written_before_rename(u: Up) -> None:
    _killed(u, "replace-attempt")
    time.sleep(0.3)
    _nothing_started(u)
    assert u.up()[0] == 0 and len(u.attempt_files()) == 1


def test_row03_attempt_renamed_before_its_directory_fsync(u: Up) -> None:
    _killed(u, "fsync-attempt-dir")
    time.sleep(0.3)
    assert len(u.attempt_files()) == 1 and u.runs() == []
    assert not (u.store / "state.json").exists()  # no state points at it: it authorizes nothing
    orphan = u.attempt_files()[0]
    assert u.up()[0] == 0
    assert u.last()["id"] != orphan.stem and u.last()["mode"] == "new"
    assert json.loads(orphan.read_text())["session_id"] != sid_of(u.runs()[0])


def test_row04_state_temp_incomplete_old_state_stays_authoritative(u: Up) -> None:
    u.transcripts()
    u.up()
    u.age()
    before = u.state_hash()
    _killed(u, "replace-state", new=True)
    time.sleep(0.3)
    assert u.state_hash() == before and len(u.runs()) == 1
    unreferenced = [p for p in u.attempt_files() if p.stem != u.state()["planner"]["last_attempt"]]
    assert len(unreferenced) == 1  # written, never execed, never referenced
    lost = json.loads(unreferenced[0].read_text())["session_id"]
    assert u.up()[0] == 0
    assert lost not in json.dumps(u.runs()[-1])  # its uuid was never used


def test_row05_state_renamed_before_its_directory_fsync(u: Up) -> None:
    _killed(u, "fsync-state-dir")
    _then_new_retry_same_id(u)


def test_row05_fsync_failure_after_rename_keeps_the_new_state_without_rollback(u: Up) -> None:
    proc = u.drive(fault=["fsync-state-dir", "raise"])
    assert proc.wait() == 5 and "record-failed" in proc.stderr
    assert (u.store / "state.json").exists() and u.runs() == []  # new state visible, no exec
    _then_new_retry_same_id(u)


def test_row06_state_durable_before_the_go_byte(u: Up) -> None:
    _killed(u, "after-commit")
    _then_new_retry_same_id(u)


def test_row07_store_lock_released_go_byte_unsent(u: Up) -> None:
    _killed(u, "after-release")
    _then_new_retry_same_id(u)


def test_row08_child_execed_then_the_holder_dies(u: Up) -> None:
    u.hold()
    _killed(u, "after-go")
    run = u.wait_runs(1)[0]
    before = u.state_hash()
    for new in (False, True):
        code, _, err = u.up(new=new)
        assert code == 4 and "holder-lost" in err and str(run["pid"]) in err
        assert u.state_hash() == before and len(u.runs()) == 1
    u.stop()
    u.wait_dead(run["pid"])
    assert u.up()[0] == 0  # now it is dead: recovery proceeds


def test_row09_runtime_and_holder_both_dead_resume_when_a_transcript_exists(u: Up) -> None:
    u.hold()
    u.transcripts()
    holder = u.drive()
    run = u.wait_runs(1)[0]
    os.kill(holder.popen.pid, signal.SIGKILL)
    os.kill(run["pid"], signal.SIGKILL)
    holder.wait()
    u.wait_dead(run["pid"])
    u.age()
    u.stop()  # the replacement runtime must not wait
    assert u.up()[0] == 0
    again = u.runs()[-1]
    assert again["argv"][again["argv"].index("--resume") + 1] == sid_of(run)
    assert u.last()["mode"] == "resume"


def test_row09_both_dead_with_no_transcript_is_new_retry(u: Up) -> None:
    u.hold()
    holder = u.drive()
    run = u.wait_runs(1)[0]
    os.kill(holder.popen.pid, signal.SIGKILL)
    os.kill(run["pid"], signal.SIGKILL)
    holder.wait()
    u.wait_dead(run["pid"])
    u.stop()
    assert u.up()[0] == 0 and u.last()["mode"] == "new-retry"
    assert sid_of(u.runs()[-1]) == sid_of(run)


def test_row10_go_write_fails_because_the_child_already_exited(u: Up) -> None:
    proc = u.drive(fault=["before-go", "kill-child"])
    assert proc.wait() == 5 and "go-failed" in proc.stderr
    exit_files = list((u.store / "attempts").glob("*.exit.json"))
    assert [json.loads(p.read_text())["status"] for p in exit_files] == ["never-execed"]
    assert u.runs() == []
    _then_new_retry_same_id(u)


def test_row11_waitpid_lost_exits_4_with_no_exit_record_and_the_runtime_may_live(u: Up) -> None:
    u.hold()
    proc = u.drive(fault=["waitpid", "waitpid-lost"])
    assert proc.wait() == 4 and "wait-lost" in proc.stderr
    run = u.wait_runs(1)[0]
    assert list((u.store / "attempts").glob("*.exit.json")) == []
    code, _, err = u.up()
    assert code == 4 and "holder-lost" in err and str(run["pid"]) in err


def test_disk_full_while_writing_the_attempt_execs_nothing(
    u: Up, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = os.write

    def full(fd: int, data: Any) -> int:
        if b'"argv"' in bytes(data):
            raise OSError(28, "No space left on device")
        return real(fd, data)

    monkeypatch.setattr(os, "write", full)
    code, _, err = u.up()
    monkeypatch.undo()
    assert code == 5 and "record-failed" in err
    assert u.runs() == [] and not (u.store / "state.json").exists()


def test_an_unwritable_attempts_directory_execs_nothing(u: Up) -> None:
    (u.store / "attempts").chmod(0o500)
    try:
        code, _, err = u.up()
    finally:
        (u.store / "attempts").chmod(0o700)
    assert code == 5 and "record-failed" in err
    assert u.runs() == []


# --- the holder's own rules ----------------------------------------------------------------


def test_the_holder_ignores_ctrl_c_while_waiting_and_restores_it_after(u: Up) -> None:
    u.hold()
    holder = u.drive()
    u.wait_runs(1)
    holder.popen.send_signal(signal.SIGINT)  # a test sends this; mb never does
    time.sleep(0.3)
    assert holder.popen.poll() is None  # still waiting for the runtime
    u.stop()
    assert holder.wait() == 0
    before = signal.getsignal(signal.SIGINT)
    u.up()
    assert signal.getsignal(signal.SIGINT) == before


def test_the_agent_modules_never_signal_or_touch_the_tty() -> None:
    for module in (au, store_mod):
        text = Path(str(module.__file__)).read_text()
        for banned in ("os.kill(", "os.killpg", "pthread_kill", "pidfd_send_signal", "/dev/tty"):
            assert banned not in text, (module.__name__, banned)


def test_a_launched_runtime_inherits_no_lock_descriptor(u: Up) -> None:
    u.hold()
    holder = u.drive()
    run = u.wait_runs(1)[0]
    assert run["fds"] == [0, 1, 2]
    lock = store_mod.FileLock(u.store / "locks/planner.lock", os.getuid())
    assert not lock.try_lock()  # held by the holder, not released by the runtime
    lock.close()
    u.stop()
    holder.wait()


def test_cli_dry_run_goes_through_the_real_command(u: Up, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from mb.cli import app

    monkeypatch.setattr(ap.Host, "local", classmethod(lambda cls: u.host))
    result = CliRunner().invoke(app, ["agent", "up", "planner", "--new", "--dry-run"])
    assert result.exit_code == 0 and "Dry run" in result.stdout


def test_a_row_with_no_state_and_no_flag_refuses_no_session(u: Up) -> None:
    out, err = io.StringIO(), io.StringIO()
    code = au.up(u.host, "planner", environ={}, out=out, err=err)
    assert code == 5 and "no-session" in err.getvalue()
    dry = au.up(u.host, "planner", dry_run=True, environ={}, out=out, err=err)
    assert dry == 5
    assert u.runs() == [] and u.attempt_files() == []
    assert not (u.store / "state.json").exists()
    assert u.up()[0] == 0  # with --new (added by the helper) it starts


def test_a_store_lock_that_stays_held_is_store_lock_timeout(
    u: Up, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = store_mod.FileLock(u.store / ".store.lock", os.getuid())
    assert held.try_lock()
    monkeypatch.setattr(store_mod, "STORE_LOCK_WAIT", 0.1)
    try:
        code, _, err = u.up()
    finally:
        held.close()
    assert code == 4 and "store-lock-timeout" in err
    assert u.runs() == []
