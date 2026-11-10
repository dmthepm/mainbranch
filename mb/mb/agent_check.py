"""mb agent check <name>: does a running agent still have the launch configuration it was given?

It reads the attempt ``mb agent up`` recorded and compares it with what /proc shows now: the
process identity (read twice), its program, the *names* in its environment and the values mb set
itself, its folder, the profile directory, the policy row and role card, and a transcript record
written after the launch. Each field is ``match``, ``mismatch`` or ``unverified(reason)``.

Exit 0 ok, 1 mismatch, 2 invalid policy or unsafe store, 3 ended, 4 unknown. A required field that
could not be observed is 4 even when another field mismatches; 1 needs every required field
observed. Unknown is never dead and never ok. Nothing here takes a lock, writes, signals or types.

What a pass does not prove: that the session runs in this process (the smoke gives evidence for
that, per runtime version), that the agent behaves like its role, that passed values such as
``SSH_AUTH_SOCK`` are unchanged (they are not stored), or anything the runtime changed in memory.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from mb import agent_policy as ap
from mb import agent_smoke as sm
from mb import agent_up as au
from mb import roles
from mb.agent_store import Refusal, Store, audit
from mb.json_result import envelope

SCHEMA = "mainbranch.agent.check"
SHAPE_VERSION = 1
WAIT_DEFAULT = 30
WAIT_MAX = 300
WAIT_POLL = 0.5
TAIL_BYTES = 262_144
RESULTS = {0: "ok", 1: "mismatch", 2: "refused", 3: "ended", 4: "unknown"}
REQUIRED = ("identity", "exe", "role", "card", "profile", "cwd", "environment", "session")
ASSUMPTION = (
    "A supported runtime keeps its session in the process mb started; mb does not check that."
)
LIMITS = (
    "Passed values (SSH_AUTH_SOCK, HEAVY_LOCK, terminal and Herdr ids) are not stored; only their "
    "names are compared.",
    "The environment shown is what the process started with, not its settings in memory.",
    "The card is checked as the launched file named by policy, not as text the runtime loaded.",
    "Not checked: model and effort in effect, account, whether a hook ran, declared work.",
)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _clock() -> float:
    return time.monotonic()


@dataclass
class Field:
    name: str
    status: str  # match | mismatch | unverified
    reason: str = ""
    required: bool = True

    def text(self) -> str:
        return f"{self.name}: {self.status}" + (f" ({self.reason})" if self.reason else "")

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "reason": self.reason or None,
            "required": self.required,
        }


@dataclass
class Result:
    exit_code: int
    agent: str
    tag: str | None = None
    detail: str = ""
    attempt: str | None = None
    row_rev: str | None = None
    launched: bool = True
    fields: list[Field] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def result(self) -> str:
        return RESULTS[self.exit_code]

    def as_dict(self) -> dict[str, Any]:
        return {
            "shape_version": SHAPE_VERSION,
            "agent": self.agent,
            "result": self.result,
            "exit_code": self.exit_code,
            "tag": self.tag,
            "detail": self.detail,
            "attempt": self.attempt,
            "row_rev": self.row_rev,
            "launched": self.launched,
            "fields": [f.as_dict() for f in self.fields],
            "problems": self.problems,
            "assumption": ASSUMPTION,
            "limits": list(LIMITS),
        }


@dataclass
class Scope:
    """Where the transcript search looks, built from the attempt and the policy."""

    home: str
    profile_real: str
    policy_profiles: list[str]


def _try(fn: Any, *args: Any) -> tuple[Any, str | None]:
    """A fact and no tag, or no fact and the reason it could not be read."""
    try:
        return fn(*args), None
    except Refusal as refusal:
        return None, refusal.tag


# --- the lock table -------------------------------------------------------------------------


def _lock_owners(store: Store, name: str) -> list[int]:
    """Pids holding the row lock. Never creates the lock file and never takes the lock."""
    if not audit(store.locks / f"{name}.lock", store.uid, directory=False):
        return []
    lock = store.row_lock(name)
    try:
        owners = au.lock_owners(lock)
    finally:
        lock.close()
    if owners is None:
        raise Refusal(4, "lock-owner-unknown", "cannot read /proc/locks")
    return owners


def _holder_owns(owners: list[int], last: dict[str, Any]) -> bool:
    if owners != [last["holder_pid"]]:
        return False
    return au.identity(last["holder_pid"], last["holder_start"], last["boot_id"]) == "live"


# --- the fields -----------------------------------------------------------------------------


def _fresh_record(path: str, session_id: str, since: datetime) -> bool | None:
    """True when a record in the file's tail carries the id and is stamped after ``since``."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            return None
        offset = max(0, info.st_size - TAIL_BYTES)
        os.lseek(fd, offset, os.SEEK_SET)
        data = os.read(fd, TAIL_BYTES)
    except OSError:
        return None
    finally:
        os.close(fd)
    lines = data.split(b"\n")
    for raw in lines[1:] if offset else lines:  # the first line of a tail may be cut
        try:
            record = json.loads(raw)
            stamp = datetime.fromisoformat(str(record.get("timestamp", "")).replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        if record.get("sessionId") == session_id and stamp > since:
            return True
    return False


def _session(last: dict[str, Any]) -> Field:
    sid = last["session_id"]
    expect = last.get("profile_id")
    found = au.Search()
    au._look(last["profile_real"], tuple(expect) if expect else None, sid, found)
    for _, path, _ in found.found:
        fresh = _fresh_record(path, sid, datetime.fromisoformat(last["utc"]))
        if fresh is None:
            return Field("session", "unverified", "unsupported-format")
        if fresh:
            return Field("session", "match")
    if found.found:
        return Field("session", "unverified", "no-session-evidence")
    why = found.incomplete or ""
    if why.startswith("unsupported"):
        return Field("session", "unverified", "unsupported-format")
    return Field("session", "unverified", "search-incomplete" if why else "no-session-evidence")


def _profile(last: dict[str, Any]) -> Field:
    try:
        info = os.lstat(last["profile_real"])
    except FileNotFoundError:
        return Field("profile", "mismatch", "profile-missing")
    except OSError:
        return Field("profile", "unverified", "proc-denied")
    expect = last.get("profile_id")
    if not stat.S_ISDIR(info.st_mode) or (expect and tuple(expect) != (info.st_dev, info.st_ino)):
        return Field("profile", "mismatch", "profile-changed")
    return Field("profile", "match")


def _environment(env: dict[str, str], last: dict[str, Any]) -> tuple[Field, Field]:
    """The names equal env_set plus env_passed; each mb-set value equals the attempt's."""
    env_set: dict[str, str] = last["env_set"]
    bad = []
    if set(env) != set(env_set) | set(last["env_passed"]):
        bad.append("env")
    bad += [f"env:{k}" for k, v in env_set.items() if k in env and env[k] != v]
    role = env.get("MB_ROLE") == env_set["MB_ROLE"]
    return (
        Field("environment", "mismatch", ", ".join(bad)) if bad else Field("environment", "match"),
        Field("role", "match") if role else Field("role", "mismatch", "MB_ROLE"),
    )


def _live_fields(report: ap.Report, host: ap.Host, last: dict[str, Any]) -> list[Field]:
    pid, start = int(last["runtime_pid"]), int(last["runtime_start"])
    runtime_id = (int(last["runtime_id"][0]), int(last["runtime_id"][1]))
    before, tag = _try(sm._observe, pid)
    env, env_tag = _try(sm._environ, pid)
    cwd, cwd_tag = _try(sm._link, pid, "cwd")
    cmdline, cmd_tag = _try(sm._read, pid, "cmdline")
    after, _ = _try(sm._observe, pid)
    by_name: dict[str, Field] = {}

    def put(item: Field) -> None:
        by_name[item.name] = item

    if before is None:
        put(Field("identity", "unverified", tag or "inconsistent"))
        put(Field("exe", "unverified", tag or "inconsistent"))
    else:
        reused = before.start != start or after != before
        put(
            Field("identity", "unverified", "inconsistent")
            if reused
            else Field("identity", "match")
        )
        exe_ok = before.exe == runtime_id
        put(Field("exe", "match") if exe_ok else Field("exe", "unverified", "exe-changed"))
    if env is None:
        for name in ("environment", "role"):
            put(Field(name, "unverified", env_tag or "inconsistent"))
    else:
        for item in _environment(env, last):
            put(item)
    if cwd is None:
        put(Field("cwd", "unverified", cwd_tag or "inconsistent"))
    else:
        put(Field("cwd", "match") if cwd == last["cwd_real"] else Field("cwd", "mismatch", "cwd"))
    card = report.cards.get(last["name"])
    put(Field("card", "match") if card == last["card_real"] else Field("card", "mismatch", "card"))
    put(_profile(last))
    put(_session(last))
    row = next((r for r in report.policy["agents"] if r["name"] == last["name"]), None)
    same_row = row is not None and au.row_rev(row) == last["row_rev"]
    put(
        Field("row", "match", required=False)
        if same_row
        else Field("row", "mismatch", "row", False)
    )
    if cmdline is None:
        put(Field("argv", "unverified", cmd_tag or "inconsistent", False))
    else:
        seen = cmdline.decode(errors="replace").split("\0")
        same = seen[:-1] == last["argv"] if seen and seen[-1] == "" else seen == last["argv"]
        put(
            Field("argv", "match", required=False)
            if same
            else Field("argv", "unverified", "argv-rewritten", False)
        )
    put(Field("env-passed", "unverified", "not-stored", False))
    return [*(by_name[n] for n in REQUIRED), *(by_name[n] for n in ("row", "argv", "env-passed"))]


# --- one observation ------------------------------------------------------------------------


def _ended(report: ap.Report, host: ap.Host, store: Store, last: dict[str, Any]) -> Result:
    """Lock free and the identity dead: ended, unless the tripwire sees the session elsewhere."""
    sid = last["session_id"]
    profiles = [d["claude"] for d in report.profiles.values() if "claude" in d]
    scope = Scope(report.home, last["profile_real"], profiles)
    found = au.search(scope, au.chain_of(store, last["id"]), sid)
    recent = [f for _, f, mtime in found.found if au._now() - mtime < au.TRIPWIRE_SECONDS]
    hits, unreadable = au.cmdline_scan(sid, host.uid)
    if recent or hits:
        names = [f"pid {p}" for p in hits] + recent
        raise Refusal(4, "session-seen", "; ".join(names))
    if unreadable:
        raise Refusal(4, "scan-incomplete", f"could not read the command line of {unreadable}")
    if found.incomplete:
        raise Refusal(4, "search-incomplete", found.incomplete)
    pid = last["runtime_pid"]
    return Result(3, last["name"], "ended", f"runtime pid {pid} has ended; the lock is free")


def _judge(report: ap.Report, host: ap.Host, store: Store, name: str) -> Result:
    state = store.read_state().get(name)
    if state is None:
        return Result(4, name, "no-session-evidence", "no recorded launch to check", launched=False)
    last = au._cross_check(store, name, state)
    if last is None or last["session_id"] is None:
        raise Refusal(4, "no-session-evidence", "the attempt has no session id to check")
    identity = au.identity(last["runtime_pid"], last["runtime_start"], last["boot_id"])
    if identity.startswith("unknown"):
        raise au._unknown(identity, last)
    owners = _lock_owners(store, name)
    pid = last["runtime_pid"]
    if owners and not _holder_owns(owners, last):
        raise Refusal(4, "lock-owner-unknown", f"lock held by pid {owners[0]}, not the holder")
    if identity == "dead":
        if owners:
            raise Refusal(
                4, "lock-orphan", f"holder pid {owners[0]} holds the lock; runtime is gone"
            )
        return _ended(report, host, store, last)
    if not owners:
        raise Refusal(4, "holder-lost", f"runtime pid {pid} lives and nothing holds the lock")
    fields = _live_fields(report, host, last)
    unknown = [f for f in fields if f.required and f.status == "unverified"]
    bad = [f for f in fields if f.status == "mismatch"]
    code = 4 if unknown else 1 if bad else 0
    tag = unknown[0].reason if unknown else None
    detail = {0: "launch configuration verified", 1: "differs from the attempt", 4: "not observed"}
    return Result(code, name, tag, detail[code], last["id"], last["row_rev"], True, fields)


def observe(host: ap.Host, name: str, report: ap.Report | None = None) -> Result:
    """One read-only observation. Policy first; every other stop is a ``Refusal`` with its code."""
    report = report or ap.check(host, name)
    if not report.ok:
        return Result(
            2,
            name,
            "policy",
            "agents.json is not valid",
            problems=[p.text() for p in report.problems],
        )
    store = Store(Path(report.store), host.uid)
    try:
        store.prepare(create=False)
        return _judge(report, host, store, name)
    except Refusal as refusal:
        return Result(refusal.exit_code, name, refusal.tag, refusal.detail)


# --- output ---------------------------------------------------------------------------------


def render(result: Result, out: TextIO) -> None:
    head = {
        0: "ok: launch configuration verified",
        1: "mismatch",
        2: "refused",
        3: "ended",
        4: "unknown",
    }[result.exit_code]
    tag = f" ({result.tag})" if result.tag else ""
    lines = [f"agent {result.agent}: {head}{tag}"]
    if result.detail and result.exit_code != 0:
        lines.append(f"  {roles.printable(result.detail, 300)}")
    lines += [f"  {roles.printable(p, 300)}" for p in result.problems]
    if result.attempt:
        lines.append(f"  attempt {result.attempt}, row {str(result.row_rev)[:12]}")
    lines += [f"  {item.text()}" for item in result.fields]
    if result.exit_code in (0, 1, 3, 4):
        lines.append(f"Assumption: {ASSUMPTION}")
    if result.fields:
        lines += [f"Limit: {text}" for text in LIMITS]
    print("\n".join(lines), file=out)


def check(
    host: ap.Host,
    name: str,
    *,
    wait: float | None = None,
    as_json: bool = False,
    out: TextIO | None = None,
) -> int:
    """Observe once, or with ``wait`` seconds keep observing while the answer is 3 or 4."""
    out = out or sys.stdout
    deadline = _clock() + wait if wait else None
    while True:
        result = observe(host, name)
        if deadline is None or result.exit_code in (0, 1, 2) or _clock() >= deadline:
            break
        _sleep(WAIT_POLL)
    if as_json:
        payload = envelope(
            {**result.as_dict(), "ok": result.exit_code == 0},
            command="mb agent check",
            schema_name=SCHEMA,
        )
        print(json.dumps(payload, indent=2), file=out)
    else:
        render(result, out)
    return result.exit_code


# --- doctor ---------------------------------------------------------------------------------


def doctor_check(host: ap.Host | None = None) -> dict[str, Any] | None:
    """One doctor row from a read-only check of every agent, or None when there is no policy.

    Ended and unknown agents warn; a mismatch fails. An agent never launched is not a finding.
    """
    try:
        return _doctor_row(host or ap.Host.local())
    except Exception:  # noqa: BLE001
        return {"name": "agents", "ok": False, "severity": "warn", "detail": "could not check"}


def _doctor_row(host: ap.Host) -> dict[str, Any] | None:
    home = Path(host.home)
    if not (home.joinpath(*ap.STORE_PARTS) / "agents.json").exists():
        return None
    report = ap.check(host)
    if not report.ok:
        return {
            "name": "agents",
            "ok": False,
            "severity": "warn",
            "detail": "agents.json is not valid; run `mb agent check`",
        }
    results = [
        observe(host, row["name"], ap.check(host, row["name"])) for row in report.policy["agents"]
    ]
    launched = [r for r in results if r.launched]
    codes = {r.exit_code for r in launched}
    detail = "; ".join(f"{r.agent}: {r.result}" for r in launched) or "no agent launched yet"
    check_row: dict[str, Any] = {"name": "agents", "ok": not codes - {0}, "detail": detail}
    if codes - {0, 1} and 1 not in codes:
        check_row["severity"] = "warn"  # ended or unknown; only a mismatch is a failure
    return check_row
