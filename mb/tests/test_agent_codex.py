"""Codex launcher contract, using invented profiles and process facts only."""

from __future__ import annotations

import io
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mb import agent_smoke as sm
from mb import agent_up as au
from mb.agent_store import Store
from tests.test_agent_check import HOLDER_PID, Live, lv  # noqa: F401, F811
from tests.test_agent_smoke import MARKER_PID, RUNTIME_PID, START
from tests.test_agent_up import Up

SID = "00000000-0000-0000-0000-000000000001"
SID2 = "00000000-0000-0000-0000-000000000002"


def rollout(
    profile: Path, sid: str = SID, *, cwd: str, stamp: str, other_id: str | None = None
) -> Path:
    path = profile / "sessions" / "2030" / "01" / f"rollout-{sid}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "type": "session_meta",
        "timestamp": stamp,
        "payload": {"id": sid, "session_id": other_id or sid, "cwd": cwd, "timestamp": stamp},
    }
    path.write_text(json.dumps(meta) + "\n")
    return path


@pytest.fixture
def cu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Up:
    u = Up(tmp_path)
    (u.bin / "codex").write_bytes(u.runtime.read_bytes())
    (u.bin / "codex").chmod(0o755)
    u.mkdir(u.home / ".codex")
    u.write({"version": 1, "agents": [u.row(runtime="codex", model="codex-test", effort="high")]})
    monkeypatch.setattr(au, "is_elf", lambda p: True)
    return u


@pytest.fixture
def cv(lv: Live) -> Live:  # noqa: F811
    (lv.u.bin / "codex").write_bytes(lv.u.runtime.read_bytes())
    (lv.u.bin / "codex").chmod(0o755)
    lv.u.write({"version": 1, "agents": [lv.u.row(runtime="codex")]})
    lv.profile = lv.u.mkdir(lv.u.home / ".codex")
    row = lv.u.row(runtime="codex")
    lv.record.update(
        runtime="codex",
        profile_real=str(lv.profile),
        profile_id=list(au._stat_id(str(lv.profile)) or ()),
        session_id=SID,
        session_provenance="owner-confirmed",
        mode="resume",
        row_rev=au.row_rev(row),
    )
    lv.save()
    state = lv.u.state()
    state["planner"].update(
        session_id=SID, session_provenance="owner-confirmed", row_rev=lv.record["row_rev"]
    )
    Store(lv.u.store, lv.u.host.uid).write_state(state)
    rollout(
        lv.profile,
        cwd=lv.record["cwd_real"],
        stamp=(datetime.fromisoformat(lv.record["utc"]) + timedelta(seconds=1)).isoformat(),
    )
    return lv


def null_session(cv: Live) -> None:
    cv.record.update(session_id=None, session_provenance="spawned", mode="new")
    cv.save()
    state = cv.u.state()
    state["planner"].update(session_id=None, session_provenance="spawned")
    Store(cv.u.store, cv.u.host.uid).write_state(state)


def test_new_and_resume_argv_and_state(cu: Up) -> None:
    code, _, err = cu.up()
    assert code == 0, err
    record = cu.last()
    expected = [
        "codex",
        "--no-daemon",
        "-m",
        "codex-test",
        "-c",
        "model_reasoning_effort=high",
    ]
    assert record["argv"] == expected
    assert record["session_id"] is None and record["session_provenance"] == "spawned"
    rollout(cu.home / ".codex", cwd=str(cu.biz), stamp=record["utc"])
    cu.age()
    code, _, err = cu.up(session=SID)
    assert code == 0, err
    assert cu.last()["argv"] == ["codex", "resume", SID, *expected[1:]]
    assert cu.last()["session_provenance"] == "owner-confirmed"
    assert cu.up()[0] == 0


def test_no_session_hints_never_change_state(cu: Up) -> None:
    assert cu.up()[0] == 0
    before = (cu.store / "state.json").read_bytes()
    record = cu.last()
    for sid in (SID, SID2):
        path = rollout(cu.home / ".codex", sid, cwd=str(cu.biz), stamp=record["utc"])
        os.utime(path, (1, 1))
    code, _, err = cu.up()
    assert code == 5 and "no-session" in err
    assert "discovered (not adopted)" in err and SID in err and SID2 in err
    assert (cu.store / "state.json").read_bytes() == before


def test_named_profile_only_sets_codex_home(cu: Up) -> None:
    plan, _ = au.prepare(cu.host, "planner", {})
    names = set(plan.env_set)
    assert "CODEX_HOME" not in names
    alt = cu.mkdir(cu.home / "alt")
    cu.write(
        {
            "version": 1,
            "profiles": {"alt": {"codex": str(alt)}},
            "agents": [cu.row(runtime="codex", profile="alt")],
        }
    )
    plan, _ = au.prepare(cu.host, "planner", {})
    selected = plan.env_set.get("CODEX_HOME")
    assert selected == str(alt)
    assert plan.argv("new", None) == [
        "codex",
        "--no-daemon",
        "-m",
        "claude-test-1",
    ]


def test_explicit_session_absent_or_wrong_profile(cu: Up) -> None:
    assert cu.up(session=SID)[0] == 2
    alt = cu.mkdir(cu.home / "alt")
    cu.write(
        {
            "version": 1,
            "profiles": {"alt": {"codex": str(alt)}},
            "agents": [cu.row(runtime="codex")],
        }
    )
    rollout(alt, cwd=str(cu.biz), stamp="2030-01-01T00:00:00+00:00")
    code, _, err = cu.up(session=SID)
    assert code == 4 and "wrong-profile" in err


@pytest.mark.parametrize("count", [0, 1, 2])
def test_check_discovery_is_ephemeral(cv: Live, count: int) -> None:
    for path in cv.profile.rglob("*.jsonl"):
        path.unlink()
    null_session(cv)
    for sid in (SID, SID2)[:count]:
        rollout(cv.profile, sid, cwd=cv.record["cwd_real"], stamp=cv.record["utc"])
    before = (cv.u.store / "state.json").read_bytes()
    code, text = cv.run()
    assert code == 4
    assert (SID in text) is (count > 0)
    assert (SID2 in text) is (count > 1)
    if count:
        assert "discovered (not adopted)" in text
    assert (cv.u.store / "state.json").read_bytes() == before


@pytest.mark.parametrize("where,delta", [("elsewhere", 1), ("same", -1)])
def test_discovery_ignores_wrong_cwd_and_stale(cv: Live, where: str, delta: int) -> None:
    null_session(cv)
    rollout(
        cv.profile,
        cwd=cv.record["cwd_real"] if where == "same" else "/invented/elsewhere",
        stamp=(datetime.fromisoformat(cv.record["utc"]) + timedelta(seconds=delta)).isoformat(),
    )
    assert SID not in cv.run()[1]


def test_discovery_does_not_search_another_profile(cv: Live) -> None:
    null_session(cv)
    for path in cv.profile.rglob("*.jsonl"):
        path.unlink()
    rollout(cv.u.home / "other-profile", cwd=cv.record["cwd_real"], stamp=cv.record["utc"])
    assert SID not in cv.run()[1]


def test_discovery_cap_and_conflicting_ids_are_unknown(
    cv: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    null_session(cv)
    monkeypatch.setattr(au, "SEARCH_ENTRY_CAP", 1)
    code, text = cv.run()
    assert code == 4 and "inconsistent" in text
    monkeypatch.setattr(au, "SEARCH_ENTRY_CAP", 10_000)
    rollout(cv.profile, cwd=cv.record["cwd_real"], stamp=cv.record["utc"], other_id=SID2)
    code, text = cv.run()
    assert code == 4 and "inconsistent" in text


def test_codex_check_match_mismatch_unknown_and_ended(cv: Live) -> None:
    assert cv.run()[0] == 0
    cv.runtime(cwd="/invented/changed")
    assert cv.run()[0] == 1
    rollout(
        cv.profile,
        cwd=cv.record["cwd_real"],
        stamp=(datetime.fromisoformat(cv.record["utc"]) - timedelta(seconds=1)).isoformat(),
    )
    assert cv.run()[0] == 4
    cv.end()
    cv.lock()
    cv.u.age()
    assert cv.run()[0] == 3


@pytest.mark.parametrize("null", [False, True])
def test_codex_transcript_tripwire(cv: Live, null: bool) -> None:
    if null:
        null_session(cv)
    cv.end()
    cv.lock()
    code, text = cv.run()
    assert code == 4 and "session-seen" in text
    code, _, err = cv.u.up(new=True)
    assert code == 4 and "session-seen" in err


def test_codex_tail_requires_meta_binding_and_a_fresh_event(cv: Live) -> None:
    path = rollout(
        cv.profile,
        cwd=cv.record["cwd_real"],
        stamp=(datetime.fromisoformat(cv.record["utc"]) - timedelta(seconds=1)).isoformat(),
    )
    with path.open("a") as handle:
        handle.write(
            json.dumps(
                {
                    "type": "event_msg",
                    "timestamp": (
                        datetime.fromisoformat(cv.record["utc"]) + timedelta(seconds=1)
                    ).isoformat(),
                    "payload": {"type": "task_started"},
                }
            )
            + "\n"
        )
    assert cv.run()[0] == 0
    path.write_text("{}\n")
    assert cv.run()[0] == 4


def test_codex_smoke_with_null_session_and_waiting_wrapper(cv: Live) -> None:
    null_session(cv)
    cv.proc.add(MARKER_PID, RUNTIME_PID, "sh")
    marker = cv.u.floor / "marker"
    marker.write_text(str(MARKER_PID))
    out, err = io.StringIO(), io.StringIO()
    assert sm.smoke(cv.u.host, "planner", str(marker), out=out, err=err) == 0
    cv.proc.add(HOLDER_PID + 10, RUNTIME_PID, "claude", start=START + 1)
    cv.proc.add(MARKER_PID, HOLDER_PID + 10, "sh")
    assert sm.smoke(cv.u.host, "planner", str(marker), out=out, err=err) == 1
    assert "not-session-process" in out.getvalue()


def test_codex_start_file_and_options_are_new_only(cu: Up) -> None:
    (cu.biz / "start.md").write_text("Fixture instructions.")
    cu.write(
        {
            "version": 1,
            "agents": [
                cu.row(runtime="codex", start_file="start.md", options=["--sandbox read-only"])
            ],
        }
    )
    plan, _ = au.prepare(cu.host, "planner", {})
    new = plan.argv("new", None)
    resumed = plan.argv("resume", SID)
    assert new[-3:] == ["--sandbox", "read-only", "Read start.md first."]
    assert resumed[-2:] == ["--sandbox", "read-only"]
    assert not any("Read start.md" in arg for arg in resumed)
    assert not any("model_reasoning_effort" in arg for arg in new)


def test_codex_script_entrypoint_is_refused(cu: Up, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(au, "is_elf", lambda p: False)
    code, _, err = cu.up()
    assert code == 2 and "unsupported-runtime" in err
    assert not (cu.store / "state.json").exists()


@pytest.mark.parametrize("kind", ["link", "fifo", "invalid-json", "bad-time", "bad-meta"])
def test_bad_codex_rollouts_fail_closed(cv: Live, kind: str) -> None:
    path = next(cv.profile.rglob("*.jsonl"))
    if kind == "link":
        path.unlink()
        path.symlink_to("/invented/rollout.jsonl")
    elif kind == "fifo":
        path.unlink()
        os.mkfifo(path)
    elif kind == "invalid-json":
        path.write_text("{truncated")
    else:
        record = json.loads(path.read_text())
        if kind == "bad-time":
            record["payload"]["timestamp"] = 42
        else:
            record["type"] = "event_msg"
        path.write_text(json.dumps(record))
    code, text = cv.run()
    assert code == 4 and "unsupported-format" in text


def test_discovery_over_ten_thousand_entries_is_unknown(cv: Live) -> None:
    null_session(cv)
    directory = cv.profile / "sessions"
    for index in range(10_001):
        (directory / f"ignored-{index}").touch()
    code, text = cv.run()
    assert code == 4 and "inconsistent" in text


def test_null_session_with_no_rollout_can_end(cv: Live) -> None:
    null_session(cv)
    for path in cv.profile.rglob("*.jsonl"):
        path.unlink()
    cv.end()
    cv.lock()
    assert cv.run()[0] == 3


def test_codex_null_ids_do_not_alias_other_new_rows(cu: Up) -> None:
    cu.write(
        {"version": 1, "agents": [cu.row(runtime="codex"), cu.row(runtime="codex", name="worker")]}
    )
    assert cu.up()[0] == 0
    assert cu.up("worker", new=True)[0] == 0
    assert cu.state()["worker"]["session_id"] is None


def test_explicit_codex_id_is_reserved_across_rows(cu: Up) -> None:
    cu.write(
        {"version": 1, "agents": [cu.row(runtime="codex"), cu.row(runtime="codex", name="worker")]}
    )
    rollout(cu.home / ".codex", cwd=str(cu.biz), stamp="2030-01-01T00:00:00+00:00")
    assert cu.up(session=SID)[0] == 0
    code, _, err = cu.up("worker", session=SID)
    assert code == 5 and "alias" in err


@pytest.mark.parametrize("mode", ["new", "resume"])
def test_codex_keeps_native_instructions_and_selects_hook_role(cu: Up, mode: str) -> None:
    plan, _ = au.prepare(cu.host, "planner", {})
    argv = plan.argv(mode, SID if mode == "resume" else None)
    assert not any("model_instructions_file" in arg for arg in argv)
    assert plan.card_real not in argv
    assert plan.env_set["MB_ROLE"] == plan.row["role"]


@pytest.mark.parametrize("stored", [False, True])
def test_codex_resume_refuses_right_profile_wrong_cwd(cu: Up, stored: bool) -> None:
    path = rollout(cu.home / ".codex", cwd=str(cu.biz), stamp="2030-01-01T00:00:00+00:00")
    if stored:
        assert cu.up(session=SID)[0] == 0
        cu.age()
    path = rollout(
        cu.home / ".codex", cwd="/invented/other-business", stamp="2030-01-01T00:00:00+00:00"
    )
    os.utime(path, (1, 1))
    before = {str(p): p.read_bytes() for p in cu.store.rglob("*.json")}
    runs = len(cu.runs())
    code, _, err = cu.up(session=None if stored else SID)
    assert code == 4 and "wrong-cwd" in err
    assert len(cu.runs()) == runs
    assert {str(p): p.read_bytes() for p in cu.store.rglob("*.json")} == before


def test_named_codex_profile_reaches_fixture_child_without_inherited_overrides(cu: Up) -> None:
    alt = cu.mkdir(cu.home / "alt")
    cu.write(
        {
            "version": 1,
            "profiles": {"alt": {"codex": str(alt)}},
            "agents": [cu.row(runtime="codex", profile="alt")],
        }
    )
    code, _, err = cu.up(
        environ={"CODEX_HOME": "/invented/poison", "OPENAI_API_KEY": "fixture-marker"}
    )
    assert code == 0, err
    captured = cu.runs()[-1]["env"]
    selected = captured.get("CODEX_HOME")
    names = set(captured)
    assert selected == str(alt)
    assert "OPENAI_API_KEY" not in names
    assert cu.last()["profile_real"] == str(alt)
    stored = "".join(p.read_text() for p in cu.store.rglob("*.json"))
    assert "fixture-marker" not in stored and "/invented/poison" not in stored


def test_rollout_replaced_between_search_and_evidence_cannot_match(
    cv: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mb import agent_codex as cx

    original = cx.rollouts

    def replace(*args):
        rows = original(*args)
        rollout(cv.profile, cwd=cv.record["cwd_real"], stamp=cv.record["utc"], other_id=SID2)
        return rows

    monkeypatch.setattr(cx, "rollouts", replace)
    code, text = cv.run()
    assert code == 4 and "transcript-changed" in text


@pytest.mark.parametrize("kind", ["symlink", "directory", "file"])
def test_rollout_parent_or_file_replaced_before_evidence_is_unknown(
    cv: Live, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    from mb import agent_codex as cx

    original = cx.rollouts

    def replace(*args):
        rows = original(*args)
        path = next(cv.profile.rglob("*.jsonl"))
        data = path.read_bytes()
        if kind == "file":
            path.rename(path.with_suffix(".old"))
            path.write_bytes(data)
        else:
            sessions = cv.profile / "sessions"
            relative = path.relative_to(sessions)
            sessions.rename(cv.profile / "old-sessions")
            target = cv.u.floor / "outside-profile" if kind == "symlink" else sessions
            (target / relative).parent.mkdir(parents=True)
            (target / relative).write_bytes(data)
            if kind == "symlink":
                sessions.symlink_to(target, target_is_directory=True)
        return rows

    monkeypatch.setattr(cx, "rollouts", replace)
    code, text = cv.run()
    assert code == 4 and "transcript-changed" in text
