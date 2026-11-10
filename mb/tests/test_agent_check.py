"""mb agent check <name>, slice 3: the live check on a fake /proc root. Invented paths only.

No real claude runs. A fixture ``up`` writes a real attempt; the test then points it at fake pids
whose facts (stat, environ, cwd, exe, cmdline) live in a tmp directory standing in for /proc,
together with a fake /proc/locks. Transcripts are real files under the fixture's profile.
"""

from __future__ import annotations

import io
import json
import os
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import agent_check as ac
from mb import agent_policy as ap
from mb import agent_smoke as sm
from mb import agent_store as store_mod
from mb import agent_up as au
from mb import doctor
from mb.cli import app
from tests.test_agent_smoke import BOOT, RUNTIME_PID, START, FakeProc
from tests.test_agent_up import Up

HOLDER_PID, HOLDER_START = 40000, 4000
OTHER_PID = 40300
MARKER = "MARKER-5c1e22"


class Live:
    def __init__(self, u: Up, proc: FakeProc) -> None:
        self.u, self.proc = u, proc
        u.up()
        self.profile = u.home / ".claude"
        self.profile.mkdir(mode=0o700, exist_ok=True)
        record = u.last()
        st = os.stat(proc.exe("claude"))
        record.update(
            boot_id=BOOT,
            runtime_pid=RUNTIME_PID,
            runtime_start=START,
            runtime_real=str(proc.exe("claude")),
            runtime_id=[st.st_dev, st.st_ino],
            holder_pid=HOLDER_PID,
            holder_start=HOLDER_START,
            env_passed=["TERM"],
            profile_id=[os.stat(self.profile).st_dev, os.stat(self.profile).st_ino],
        )
        self.record = record
        self.save()
        self.env = {**record["env_set"], "TERM": "xterm"}
        self.runtime()
        self.proc.add(HOLDER_PID, 1, "mb", start=HOLDER_START)
        self.lock(HOLDER_PID)
        self.transcript()

    def save(self) -> None:
        path = self.u.store / "attempts" / f"{self.record['id']}.json"
        path.write_text(json.dumps(self.record))

    @property
    def slug(self) -> str:
        return str(Path(self.record["cwd_real"]).resolve()).replace("/", "-").replace(".", "-")

    @property
    def sid(self) -> str:
        return str(self.record["session_id"])

    def runtime(self, **kw: Any) -> None:
        kw.setdefault("env", self.env)
        kw.setdefault("cwd", self.record["cwd_real"])
        kw.setdefault("cmdline", "\0".join(self.record["argv"]) + "\0")
        self.proc.add(RUNTIME_PID, HOLDER_PID, "claude", start=START, **kw)

    def lock(self, *pids: int) -> None:
        info = os.stat(self.u.store / "locks" / "planner.lock")
        self.lock_table(pids, f"{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}")

    def lock_table(self, pids: tuple[int, ...], device: str) -> None:
        inode = os.stat(self.u.store / "locks" / "planner.lock").st_ino
        lines = [
            f"{i}: FLOCK  ADVISORY  WRITE {p} {device}:{inode} 0 EOF" for i, p in enumerate(pids)
        ]
        (self.proc.root / "locks").write_text("\n".join(lines) + "\n")

    def transcript(self, *, at: timedelta = timedelta(seconds=5), sid: str | None = None) -> Path:
        stamp = datetime.fromisoformat(self.record["utc"]) + at
        path = self.profile / "projects" / self.slug / f"{self.sid}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"sessionId": sid or self.sid, "timestamp": stamp.isoformat()}
        path.write_text(json.dumps(record) + "\n")
        return path

    def end(self) -> None:
        for name in ("stat", "environ", "cmdline", "exe", "cwd"):
            (self.proc.root / str(RUNTIME_PID) / name).unlink()
        (self.proc.root / str(RUNTIME_PID)).rmdir()

    def result(self) -> ac.Result:
        return ac.observe(self.u.host, "planner")

    def fields(self) -> dict[str, ac.Field]:
        return {f.name: f for f in self.result().fields}

    def run(self, **kw: Any) -> tuple[int, str]:
        out = io.StringIO()
        code = ac.check(self.u.host, "planner", out=out, **kw)
        return code, out.getvalue()


@pytest.fixture
def lv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Live]:
    u = Up(tmp_path)
    monkeypatch.setattr(au, "is_elf", lambda p: True)
    proc_root = tmp_path / "fakeproc"
    proc_root.mkdir()
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    live = Live(u, FakeProc(proc_root, bin_dir))  # its fixture `up` runs on the real /proc
    monkeypatch.setattr(au, "PROC", str(proc_root))
    u.age()
    yield live
    u.stop()


# --- ok, and what ok does not claim --------------------------------------------------------


def test_everything_matching_is_ok_with_the_assumption_and_the_limits_shown(lv: Live) -> None:
    code, text = lv.run()
    assert code == 0
    assert "launch configuration verified" in text
    assert "keeps its session in the process mb started" in text
    assert "env-passed: unverified (not-stored)" in text
    assert "Passed values" in text and "Not checked: model" in text
    states = {f.name: f.status for f in lv.result().fields}
    assert set(states.values()) == {"match", "unverified"}


def test_a_changed_passed_value_alone_is_still_ok(lv: Live) -> None:
    lv.runtime(env={**lv.env, "TERM": "something-else"})
    assert lv.run()[0] == 0


def test_check_from_another_pane_still_compares_with_the_attempt(
    lv: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERDR_PANE_ID", "a-different-pane")
    assert lv.run()[0] == 0


def test_a_rewritten_or_unreadable_command_line_is_optional_and_never_blocks(lv: Live) -> None:
    lv.runtime(cmdline="claude: renamed title\0")
    code, text = lv.run()
    assert code == 0 and "argv: unverified (argv-rewritten)" in text
    (lv.proc.root / str(RUNTIME_PID) / "cmdline").chmod(0)
    assert lv.run()[0] == 0
    assert lv.fields()["argv"].status == "unverified"


# --- each required field failing on its own ------------------------------------------------


def test_environment_name_set_differences_are_mismatch_env(lv: Live) -> None:
    lv.runtime(env={**lv.env, "EXTRA": "1"})
    code, text = lv.run()
    assert code == 1 and "environment: mismatch (env)" in text
    lv.runtime(env={k: v for k, v in lv.env.items() if k != "TERM"})
    assert lv.run()[0] == 1


def test_a_changed_mb_set_value_names_the_variable_and_never_its_value(lv: Live) -> None:
    lv.runtime(env={**lv.env, "MB_ROLE": MARKER})
    code, text = lv.run()
    assert code == 1
    assert "environment: mismatch (env:MB_ROLE)" in text and "role: mismatch" in text
    assert MARKER not in text


def test_cwd_mismatch_alone_is_exit_1(lv: Live) -> None:
    lv.runtime(cwd="/elsewhere")
    code, text = lv.run()
    assert code == 1 and "cwd: mismatch" in text
    assert [f.name for f in lv.result().fields if f.status == "mismatch"] == ["cwd"]


def test_a_card_that_is_no_longer_the_launched_one_is_mismatch_card(lv: Live) -> None:
    lv.record["card_real"] = "/invented/other-card.md"
    lv.save()
    code, text = lv.run()
    assert code == 1 and "card: mismatch" in text


def test_a_policy_row_edited_since_launch_is_mismatch_row(lv: Live) -> None:
    lv.u.write({"version": 1, "agents": [lv.u.row(model="claude-test-2")]})
    code, text = lv.run()
    assert code == 1 and "row: mismatch (row)" in text


def test_a_changed_profile_directory_is_mismatch_and_its_transcript_is_then_unverified(
    lv: Live,
) -> None:
    lv.record["profile_id"] = [1, 1]
    lv.save()
    result = lv.result()
    named = {f.name: f for f in result.fields}
    assert named["profile"].status == "mismatch" and named["session"].status == "unverified"
    assert result.exit_code == 4  # a required field is unknown, so not 1


def test_a_profile_recorded_as_absent_matches_once_it_is_a_directory(lv: Live) -> None:
    lv.record["profile_id"] = None
    lv.save()
    assert lv.run()[0] == 0


def test_a_missing_profile_directory_is_mismatch_profile(lv: Live) -> None:
    for path in sorted(lv.profile.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    lv.profile.rmdir()
    named = lv.fields()
    assert named["profile"].status == "mismatch"


# --- unknown: a required field that could not be observed ---------------------------------


def test_a_changed_exe_is_4_exe_changed_even_while_another_field_mismatches(lv: Live) -> None:
    lv.runtime(cwd="/elsewhere")
    (lv.proc.root / str(RUNTIME_PID) / "exe").unlink()
    (lv.proc.root / str(RUNTIME_PID) / "exe").symlink_to(lv.proc.exe("another-program"))
    code, text = lv.run()
    assert code == 4 and "exe-changed" in text and "cwd: mismatch" in text


def test_an_unreadable_environ_is_4_proc_denied_never_a_pass(lv: Live) -> None:
    (lv.proc.root / str(RUNTIME_PID) / "environ").chmod(0)
    code, text = lv.run()
    assert code == 4 and "proc-denied" in text
    assert lv.fields()["environment"].status == "unverified"


def test_an_unreadable_cwd_link_or_stat_is_4(lv: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    real = os.readlink

    def readlink(path: Any, *a: Any, **k: Any) -> str:
        if str(path).endswith(f"/{RUNTIME_PID}/cwd"):
            raise PermissionError(13, "denied")
        return str(real(path, *a, **k))

    monkeypatch.setattr(os, "readlink", readlink)
    code, text = lv.run()
    assert code == 4 and "proc-denied" in text
    (lv.proc.root / str(RUNTIME_PID) / "stat").chmod(0)
    code, text = lv.run()
    assert code == 4 and "proc-denied" in text


def test_a_pid_reused_between_the_reads_is_4_inconsistent(
    lv: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    real, calls = sm._observe, []

    def observe(pid: int) -> sm.Seen:
        if pid == RUNTIME_PID:
            calls.append(pid)
            if len(calls) == 2:  # the second stat read: a new process has the pid
                lv.proc.add(RUNTIME_PID, 1, "claude", env=lv.env, start=START + 7)
        return real(pid)

    monkeypatch.setattr(sm, "_observe", observe)
    code, text = lv.run()
    assert code == 4 and "identity: unverified (inconsistent)" in text


def test_a_pid_reused_before_the_first_read_is_4_inconsistent(
    lv: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    real, done = sm._observe, list[int]()

    def observe(pid: int) -> sm.Seen:
        if pid == RUNTIME_PID and not done:
            done.append(1)  # identity() said live; the pid then went to a new process
            lv.proc.add(RUNTIME_PID, 1, "claude", env=lv.env, start=START + 7)
        return real(pid)

    monkeypatch.setattr(sm, "_observe", observe)
    assert lv.run()[0] == 4


def test_no_proc_is_4_no_proc(lv: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(au, "PROC", str(lv.proc.root / "nowhere"))
    code, text = lv.run()
    assert code == 4 and "no-proc" in text


def test_runtime_stat_unreadable_is_4_never_ended(lv: Live) -> None:
    (lv.proc.root / str(RUNTIME_PID) / "stat").chmod(0)
    code, text = lv.run()
    assert code == 4 and "proc-denied" in text and "ended" not in text.split("\n")[0]


# --- transcript evidence ------------------------------------------------------------------


def test_a_missing_transcript_is_4_no_session_evidence(lv: Live) -> None:
    lv.transcript().unlink()
    code, text = lv.run()
    assert code == 4 and "no-session-evidence" in text


def test_a_stale_transcript_or_one_for_another_id_is_not_evidence(lv: Live) -> None:
    lv.transcript(at=timedelta(seconds=-60))
    assert lv.run()[0] == 4  # recorded before the launch
    lv.transcript(sid="11111111-2222-3333-4444-555555555555")
    assert lv.run()[0] == 4


def test_a_recent_mtime_alone_is_not_evidence(lv: Live) -> None:
    path = lv.transcript(at=timedelta(seconds=-60))
    os.utime(path, None)
    assert lv.run()[0] == 4


def test_a_transcript_in_a_format_mb_does_not_know_is_4_unsupported_format(lv: Live) -> None:
    lv.transcript().write_text("not json at all\n")
    code, text = lv.run()
    assert code == 4 and "unsupported-format" in text


def test_the_evidence_is_read_from_the_end_of_a_long_transcript(lv: Live) -> None:
    path = lv.transcript()
    stamp = (datetime.fromisoformat(lv.record["utc"]) + timedelta(seconds=9)).isoformat()
    filler = json.dumps({"sessionId": lv.sid, "timestamp": "2020-01-01T00:00:00+00:00"}) + "\n"
    tail = json.dumps({"sessionId": lv.sid, "timestamp": stamp}) + "\n"
    path.write_text(filler * (ac.TAIL_BYTES // len(filler) + 50) + tail)
    assert lv.run()[0] == 0


# --- the lock table -----------------------------------------------------------------------


def test_a_dead_runtime_with_the_lock_free_is_3_ended_with_the_assumption(lv: Live) -> None:
    lv.end()
    lv.lock()
    code, text = lv.run()
    assert code == 3 and "ended" in text and "keeps its session in the process mb started" in text


def test_a_reused_runtime_pid_reads_as_ended(lv: Live) -> None:
    lv.proc.add(RUNTIME_PID, 1, "claude", env=lv.env, start=START + 1)
    lv.lock()
    assert lv.run()[0] == 3


def test_the_tripwire_turns_ended_into_session_seen(lv: Live) -> None:
    lv.end()
    lv.lock()
    lv.proc.add(OTHER_PID, 1, "claude", cmdline=f"claude\0--resume\0{lv.sid}\0")
    code, text = lv.run()
    assert code == 4 and "session-seen" in text and str(OTHER_PID) in text


def test_a_transcript_written_in_the_last_minute_trips_the_wire(lv: Live) -> None:
    lv.end()
    lv.lock()
    os.utime(lv.transcript(), None)
    assert "session-seen" in lv.run()[1]


def test_an_unreadable_command_line_in_the_scan_is_4_not_ended(lv: Live) -> None:
    lv.end()
    lv.lock()
    lv.proc.add(OTHER_PID, 1, "other")
    (lv.proc.root / str(OTHER_PID) / "cmdline").chmod(0)
    code, text = lv.run()
    assert code == 4 and "scan-incomplete" in text


def test_an_unreadable_transcript_search_is_4_not_ended(lv: Live) -> None:
    lv.end()
    lv.lock()
    lv.transcript().write_text("garbage\n")
    lv.u.age()
    code, text = lv.run()
    assert code == 4 and "search-incomplete" in text


def test_a_live_runtime_and_a_free_lock_is_4_holder_lost(lv: Live) -> None:
    lv.lock()
    code, text = lv.run()
    assert code == 4 and "holder-lost" in text and str(RUNTIME_PID) in text


def test_a_dead_runtime_under_a_held_lock_is_4_lock_orphan(lv: Live) -> None:
    lv.end()
    assert "lock-orphan" in lv.run()[1] and lv.run()[0] == 4


def test_a_lock_held_by_someone_else_or_unreadable_is_4_lock_owner_unknown(lv: Live) -> None:
    lv.proc.add(OTHER_PID, 1, "other")
    lv.lock(OTHER_PID)
    code, text = lv.run()
    assert code == 4 and "lock-owner-unknown" in text and str(OTHER_PID) in text
    lv.lock(HOLDER_PID, OTHER_PID)
    assert lv.run()[0] == 4
    (lv.proc.root / "locks").unlink()
    assert "lock-owner-unknown" in lv.run()[1]


def test_a_holder_that_is_not_the_recorded_process_does_not_count(lv: Live) -> None:
    lv.proc.add(HOLDER_PID, 1, "mb", start=HOLDER_START + 1)
    assert "lock-owner-unknown" in lv.run()[1]


# --- state, store and policy --------------------------------------------------------------


def test_an_agent_never_launched_is_4_and_not_launched(lv: Live) -> None:
    (lv.u.store / "state.json").unlink()
    result = lv.result()
    assert result.exit_code == 4 and result.launched is False
    assert "no recorded launch" in result.detail


def test_state_that_disagrees_with_its_attempt_is_4_corrupt_state(lv: Live) -> None:
    state = json.loads((lv.u.store / "state.json").read_text())
    state["rows"]["planner"]["row_rev"] = "0" * 64
    (lv.u.store / "state.json").write_text(json.dumps(state))
    assert "corrupt-state" in lv.run()[1]


def test_an_unsafe_store_is_2_and_nothing_is_changed(lv: Live) -> None:
    lv.u.store.chmod(0o755)
    code, text = lv.run()
    lv.u.store.chmod(0o700)
    assert code == 2 and "unsafe-store" in text


def test_an_unknown_agent_or_invalid_policy_is_2(lv: Live) -> None:
    out = io.StringIO()
    assert ac.check(lv.u.host, "nobody", out=out) == 2
    assert "unknown-agent" in out.getvalue()


def test_check_is_read_only_and_never_creates_the_lock_file(lv: Live) -> None:
    def snapshot() -> list[tuple[str, int, int]]:
        items = [p for p in lv.u.store.rglob("*") if p.is_file()]
        return sorted((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in items)

    before = snapshot()
    lv.run()
    lv.run()
    assert snapshot() == before
    (lv.u.store / "locks" / "planner.lock").unlink()
    (lv.proc.root / "locks").write_text("")
    assert lv.run()[0] == 4  # a live runtime and nothing holding the lock
    assert not (lv.u.store / "locks" / "planner.lock").exists()


def test_no_passed_or_changed_value_appears_in_any_output(lv: Live) -> None:
    lv.env = {**lv.env, "TERM": MARKER}
    lv.runtime(env={**lv.env, "MB_ROLE": MARKER, "EXTRA_TOKEN": MARKER})
    for kw in ({}, {"as_json": True}):
        assert MARKER not in lv.run(**kw)[1]


# --- --wait and --json --------------------------------------------------------------------


class Clock:
    def __init__(self, mp: pytest.MonkeyPatch, on_sleep: Any = None) -> None:
        self.now, self.sleeps, self.on_sleep = 1000.0, 0, on_sleep
        mp.setattr(ac, "_clock", lambda: self.now)
        mp.setattr(ac, "_sleep", self.sleep)

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        self.sleeps += 1
        if self.on_sleep:
            self.on_sleep(self.sleeps)


def test_wait_times_out_with_the_last_answer(lv: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock(monkeypatch)
    lv.transcript().unlink()
    code, text = lv.run(wait=3)
    assert code == 4 and "no-session-evidence" in text
    assert clock.sleeps == 6  # 3 seconds in half-second steps


def test_wait_succeeds_when_the_evidence_appears(lv: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    lv.transcript().unlink()
    clock = Clock(monkeypatch, lambda n: lv.transcript() if n == 3 else None)
    code, text = lv.run(wait=30)
    assert code == 0 and "launch configuration verified" in text
    assert clock.sleeps == 3


def test_wait_does_not_retry_a_verdict(lv: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock(monkeypatch)
    lv.runtime(cwd="/elsewhere")
    assert lv.run(wait=30)[0] == 1
    assert clock.sleeps == 0
    lv.u.store.chmod(0o755)
    assert lv.run(wait=30)[0] == 2
    lv.u.store.chmod(0o700)
    assert clock.sleeps == 0


def test_wait_keeps_looking_while_the_agent_has_ended(
    lv: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock(monkeypatch)
    lv.end()
    lv.lock()
    assert lv.run(wait=2)[0] == 3
    assert clock.sleeps == 4


def test_json_shape_is_pinned_for_ok(lv: Live) -> None:
    code, text = lv.run(as_json=True)
    data = json.loads(text)
    assert code == 0
    assert data["result_schema"]["name"] == "mainbranch.agent.check"
    assert data["mb_command"] == "mb agent check" and data["ok"] is True
    assert set(data) >= set(
        [
            "agent",
            "assumption",
            "attempt",
            "detail",
            "exit_code",
            "fields",
            "launched",
            "limits",
            "problems",
            "result",
            "row_rev",
            "shape_version",
            "tag",
        ]
    )
    assert data["shape_version"] == 1 and data["result"] == "ok" and data["exit_code"] == 0
    assert data["attempt"] == lv.record["id"] and data["row_rev"] == lv.record["row_rev"]
    names = [f["name"] for f in data["fields"]]
    assert names == [*ac.REQUIRED, "row", "argv", "env-passed"]
    assert all(set(f) == {"name", "reason", "required", "status"} for f in data["fields"])
    assert {f["name"] for f in data["fields"] if f["required"]} == set(ac.REQUIRED)
    assert data["fields"][-1] == {
        "name": "env-passed",
        "status": "unverified",
        "reason": "not-stored",
        "required": False,
    }


def test_json_shape_holds_for_each_result(lv: Live) -> None:
    lv.runtime(cwd="/elsewhere")
    mismatch = json.loads(lv.run(as_json=True)[1])
    assert (mismatch["result"], mismatch["exit_code"], mismatch["ok"]) == ("mismatch", 1, False)
    assert [f["name"] for f in mismatch["fields"] if f["status"] == "mismatch"] == ["cwd"]
    lv.end()
    lv.lock()
    ended = json.loads(lv.run(as_json=True)[1])
    assert (ended["result"], ended["exit_code"], ended["tag"]) == ("ended", 3, "ended")
    lv.lock(HOLDER_PID)
    unknown = json.loads(lv.run(as_json=True)[1])
    assert (unknown["result"], unknown["tag"]) == ("unknown", "lock-orphan")
    assert unknown["fields"] == [] and unknown["problems"] == []
    out = io.StringIO()
    ac.check(lv.u.host, "nobody", as_json=True, out=out)
    refused = json.loads(out.getvalue())
    assert refused["result"] == "refused" and refused["exit_code"] == 2
    assert any("unknown-agent" in p for p in refused["problems"])


# --- doctor -------------------------------------------------------------------------------


def test_doctor_row_maps_ok_ended_unknown_and_mismatch(lv: Live) -> None:
    row = ac.doctor_check(lv.u.host)
    assert row is not None and row["ok"] is True and "planner: ok" in row["detail"]
    lv.runtime(cwd="/elsewhere")
    row = ac.doctor_check(lv.u.host)
    assert row is not None and row["ok"] is False and "severity" not in row  # a hard fail
    lv.end()
    lv.lock()
    row = ac.doctor_check(lv.u.host)
    assert row is not None and row["ok"] is False and row["severity"] == "warn"
    assert "planner: ended" in row["detail"]
    lv.lock(HOLDER_PID)
    row = ac.doctor_check(lv.u.host)
    assert row is not None and row["severity"] == "warn" and "planner: unknown" in row["detail"]


def test_doctor_row_is_absent_without_a_policy_and_quiet_for_a_never_launched_agent(
    lv: Live,
) -> None:
    (lv.u.store / "state.json").unlink()
    row = ac.doctor_check(lv.u.host)
    assert row is not None and row["ok"] is True and "no agent launched" in row["detail"]
    (lv.u.store / "agents.json").unlink()
    assert ac.doctor_check(lv.u.host) is None


def test_doctor_run_carries_the_row(lv: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ap.Host, "local", classmethod(lambda cls: lv.u.host))
    report = doctor.run(str(lv.u.biz))
    names = [c["name"] for c in report["checks"]]
    assert "agents" in names


# --- the command --------------------------------------------------------------------------


@pytest.fixture
def local(lv: Live, monkeypatch: pytest.MonkeyPatch) -> Live:
    monkeypatch.setattr(ap.Host, "local", classmethod(lambda cls: lv.u.host))
    return lv


def test_cli_named_check_is_the_live_check(local: Live) -> None:
    result = CliRunner().invoke(app, ["agent", "check", "planner"])
    assert result.exit_code == 0 and "launch configuration verified" in result.output
    as_json = CliRunner().invoke(app, ["agent", "check", "planner", "--json"])
    assert json.loads(as_json.output)["result"] == "ok"


def test_cli_without_a_name_is_still_the_policy_check(local: Live) -> None:
    result = CliRunner().invoke(app, ["agent", "check"])
    assert result.exit_code == 0 and result.output.startswith("Policy valid.")


def test_cli_flags_that_need_a_name_or_conflict_exit_2(local: Live) -> None:
    for argv in (
        ["agent", "check", "--json"],
        ["agent", "check", "--wait"],
        ["agent", "check", "planner", "--smoke-marker", "m", "--json"],
        ["agent", "check", "planner", "--wait", "--timeout", "0"],
        ["agent", "check", "planner", "--wait", "--timeout", "301"],
    ):
        assert CliRunner().invoke(app, argv).exit_code == 2, argv


def test_cli_wait_uses_the_timeout(local: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock(monkeypatch)
    local.transcript().unlink()
    result = CliRunner().invoke(app, ["agent", "check", "planner", "--wait", "--timeout", "2"])
    assert result.exit_code == 4 and clock.sleeps == 4


def test_the_agent_module_still_sends_no_signals() -> None:
    text = Path(ac.__file__).read_text()
    assert not any(
        word in text for word in ("os.kill", "os.killpg", "pthread_kill", "pidfd_send_signal")
    )


# --- M3-A: what changes while the fields are being collected is 4 --------------------------


def test_a_lock_that_loses_its_holder_while_the_fields_are_read_is_4(
    lv: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = ac._environment

    def environment(env: dict[str, str], last: dict[str, Any]) -> tuple[ac.Field, ac.Field]:
        (lv.proc.root / "locks").write_text("")  # the holder exits mid-observation
        return real(env, last)

    monkeypatch.setattr(ac, "_environment", environment)
    code, text = lv.run()
    assert code == 4 and "holder-lost" in text


def test_a_pid_reused_while_the_session_is_read_is_4(
    lv: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = ac._session

    def session(last: dict[str, Any]) -> ac.Field:
        lv.proc.add(RUNTIME_PID, 1, "claude", env=lv.env, start=START + 7)
        return real(last)

    monkeypatch.setattr(ac, "_session", session)
    assert lv.run()[0] == 4


def test_a_change_during_collection_beats_a_mismatch_found_in_the_same_pass(
    lv: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    lv.runtime(cwd="/elsewhere")  # a mismatch on its own would be 1
    real = ac._session

    def session(last: dict[str, Any]) -> ac.Field:
        (lv.proc.root / "locks").write_text("")
        return real(last)

    monkeypatch.setattr(ac, "_session", session)
    assert lv.run()[0] == 4


def test_a_transcript_rewritten_after_its_tail_was_read_is_4(
    lv: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = lv.transcript()
    real, done = os.read, list[int]()

    def read(fd: int, n: int) -> bytes:
        data = real(fd, n)
        if not done and data.startswith(b'{"sessionId"'):
            done.append(1)
            path.write_text("{}\n")
        return data

    monkeypatch.setattr(os, "read", read)
    code, text = lv.run()
    assert code == 4 and "transcript-changed" in text


def test_a_transcript_replaced_by_another_file_after_the_read_is_4(
    lv: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = lv.transcript()
    real, done = os.read, list[int]()

    def read(fd: int, n: int) -> bytes:
        data = real(fd, n)
        if not done and data.startswith(b'{"sessionId"'):
            done.append(1)
            other = path.with_name("other")
            other.write_bytes(data)
            os.replace(other, path)  # same bytes and size, a different file
        return data

    monkeypatch.setattr(os, "read", read)
    assert lv.run()[0] == 4


# --- M3-B: observing the row lock never creates it -----------------------------------------


def test_a_row_lock_removed_after_the_audit_is_not_recreated_and_is_4(
    lv: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = lv.u.store / "locks" / "planner.lock"
    real = store_mod.audit

    def audit(path: Path, uid: int, *, directory: bool) -> bool:
        found = real(path, uid, directory=directory)
        if path == lock:
            lock.unlink()
        return found

    monkeypatch.setattr(ac, "audit", audit)
    code, _ = lv.run()
    assert not lock.exists()
    assert code == 4


def test_a_row_lock_that_is_consistently_absent_is_free_and_not_created(lv: Live) -> None:
    lock = lv.u.store / "locks" / "planner.lock"
    lock.unlink()
    lv.end()
    assert lv.run()[0] in (3, 4)
    assert not lock.exists()


# --- M3-C: a lock is identified by device and inode ----------------------------------------


def test_a_lock_on_another_device_with_the_same_inode_is_not_this_lock(lv: Live) -> None:
    lv.lock_table((HOLDER_PID,), "ff:ff")
    code, text = lv.run()
    assert code == 4 and "holder-lost" in text


def test_a_lock_on_another_device_does_not_hide_the_holder(lv: Live) -> None:
    info = os.stat(lv.u.store / "locks" / "planner.lock")
    inode = info.st_ino
    here = f"{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}"
    (lv.proc.root / "locks").write_text(
        f"0: FLOCK  ADVISORY  WRITE {OTHER_PID} ff:ff:{inode} 0 EOF\n"
        f"1: FLOCK  ADVISORY  WRITE {HOLDER_PID} {here}:{inode} 0 EOF\n"
    )
    assert lv.run()[0] == 0


def test_the_shared_helper_compares_both_device_parts_in_hex(lv: Live, tmp_path: Path) -> None:
    lock = store_mod.FileLock(lv.u.store / "locks" / "planner.lock", os.getuid())
    try:
        info = os.fstat(lock.fd or 0)
        assert lock.device == info.st_dev and lock.inode == info.st_ino
        lv.lock_table((HOLDER_PID,), f"{os.major(info.st_dev):x}:{os.minor(info.st_dev):x}")
        assert au.lock_owners(lock) == [HOLDER_PID]
        lv.lock_table((HOLDER_PID,), "ff:ff")
        assert au.lock_owners(lock) == []
    finally:
        lock.close()


# --- M3-D: tests never resolve the real password-database home ----------------------------


def test_doctor_without_a_host_never_resolves_the_real_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pwd

    real_home = tmp_path / "pretend-real-home"
    store = real_home.joinpath(*ap.STORE_PARTS)
    store.mkdir(parents=True)
    (store / "agents.json").write_text("{}")  # present, so a doctor that reads it reports a row
    entry = pwd.getpwuid(os.getuid())
    monkeypatch.setattr(pwd, "getpwuid", lambda uid: entry._replace(pw_dir=str(real_home)))  # type: ignore[attr-defined]
    assert ac.doctor_check() is None
    assert str(real_home) not in ap.Host.local().home


# --- M3-E: session evidence is bound to the recorded folder -------------------------------


def test_a_transcript_in_another_projects_folder_is_not_evidence(lv: Live) -> None:
    path = lv.transcript()
    other = lv.profile / "projects" / "-some-other-folder"
    other.mkdir()
    os.replace(path, other / path.name)
    code, text = lv.run()
    assert code == 4 and "no-session-evidence" in text


def test_the_folder_slug_replaces_slashes_and_dots_with_dashes(lv: Live) -> None:
    assert "." not in lv.slug and "/" not in lv.slug and lv.slug.startswith("-")
    assert ac.project_slug("/home/u/.local/state/x") == "-home-u--local-state-x"
