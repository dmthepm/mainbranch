"""mb agent up: start one Claude or Codex agent from one agents.json row, and say what it got.

``up`` is a small holder. It takes the row lock, forks one child, records the child's identity,
commits the attempt and state, lets the child exec the runtime, then waits and exits with the
child's status. The claim is *launch configuration verified at start*; it does not check that the
agent behaves like its role. Nothing here sends a signal, and the holder neither reads nor writes
the tty while the runtime runs. The attempt records mb-set values and the *names* of passed
variables, never a passed value.

The smoke verdict lives in ``agent_smoke`` and the live ``check`` in ``agent_check``.
Runtime flag and lifetime confirmation remain manual steps in the docs.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import pwd
import re
import secrets
import shlex
import signal
import stat
import sys
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, TextIO

from mb import agent_codex as cx
from mb import agent_policy as ap
from mb import roles
from mb.agent_store import FileLock, Refusal, Store

PROC = "/proc"
RUNTIME = "claude"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
PASSED_PLAIN = ("LANG", "LC_ALL", "LC_CTYPE", "TZ", "TERM", "COLORTERM") + (
    "TERM_PROGRAM",
    "TERM_PROGRAM_VERSION",
)
HERDR = ("HERDR_ENV", "HERDR_BIN_PATH", "HERDR_SOCKET_PATH", "HERDR_SESSION") + (
    "HERDR_WORKSPACE_ID",
    "HERDR_TAB_ID",
    "HERDR_PANE_ID",
)
HERDR_PATHS = ("HERDR_BIN_PATH", "HERDR_SOCKET_PATH")
DROP_PREFIXES = ("ANTHROPIC_", "OPENAI_", "CLAUDE_", "CODEX_", "__MISE_", "MISE_", "LC_")
SEARCH_ENTRY_CAP = 10_000
CHAIN_LIMIT = 20
TRIPWIRE_SECONDS = 60
ORPHAN_RETRY_SECONDS = 2.0
DRY_RUN_NOTE = (
    "Env-only auth and endpoint overrides are dropped; a login prompt, a failure or the account\n"
    "the profile holds can result. The profile path is not a verified account choice."
)


def _step(point: str, pid: int = 0) -> None:
    """Test seam: a named point in the launch order. Does nothing in production."""


def _waitpid(pid: int) -> int:
    return os.waitpid(pid, 0)[1]


def _now() -> float:
    return time.time()


# --- the plan: everything built from policy, before any state is touched ------------------


@dataclass
class Plan:
    name: str
    row: dict[str, Any]
    row_rev: str
    home: str
    store: Store
    runtime_real: str
    runtime_id: tuple[int, int]
    cwd_real: str
    card_real: str
    profile_real: str
    profile_id: tuple[int, int] | None
    policy_profiles: list[str]
    env_set: dict[str, str]
    env_passed: list[str]
    dropped: dict[str, list[str]] = field(default_factory=dict)

    @property
    def runtime(self) -> str:
        return str(self.row["runtime"])

    def argv(self, mode: str, session_id: str | None) -> list[str]:
        row = self.row
        if self.runtime == "codex":
            argv = ["codex"]
            if mode == "resume":
                assert session_id is not None
                argv += ["resume", session_id]
            argv += ["--no-daemon", "-m", row["model"]]
            if "effort" in row:
                argv += ["-c", "model_reasoning_effort=" + row["effort"]]
            for option in row.get("options", []):
                argv += option.split(" ", 1)
            if mode != "resume" and "start_file" in row:
                argv.append(f"Read {row['start_file']} first.")
            return argv
        assert session_id is not None
        argv = [RUNTIME, "--model", row["model"]]
        if "effort" in row:
            argv += ["--effort", row["effort"]]
        for option in row.get("options", []):
            argv += option.split(" ", 1)
        argv += ["--append-system-prompt-file", self.card_real]
        argv += ["--resume" if mode == "resume" else "--session-id", session_id]
        if mode != "resume" and "start_file" in row:
            argv.append(f"Read {row['start_file']} first.")
        return argv


class PolicyInvalid(Refusal):
    def __init__(self, report: ap.Report) -> None:
        super().__init__(2, "policy", "agents.json is not valid; run `mb agent check`")
        self.report = report


def row_rev(row: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _passed_env(
    host: ap.Host, environ: Mapping[str, str], *, ssh_agent: bool = False
) -> dict[str, str]:
    """The variables passed through if present, each validated. An invalid one refuses 2."""
    present = {k: environ[k] for k in (*PASSED_PLAIN, *HERDR, "XDG_RUNTIME_DIR") if k in environ}
    for key in ("DBUS_SESSION_BUS_ADDRESS", "SSH_AUTH_SOCK", "HEAVY_LOCK"):
        if key == "SSH_AUTH_SOCK" and not ssh_agent:
            continue
        if key in environ:
            present[key] = environ[key]
    xdg = f"/run/user/{host.uid}"

    def bad(name: str) -> Refusal:
        return Refusal(2, f"bad-env:{name}", f"{name} is not acceptable; its value is not shown")

    for key, value in present.items():
        if len(value) > ap.MAX_STRING or roles.has_control(value):
            raise bad(key)
        if key in HERDR_PATHS and not value.startswith("/"):
            raise bad(key)
        if key == "XDG_RUNTIME_DIR":
            try:
                info = os.lstat(value)
            except OSError:
                raise bad(key) from None
            if value != xdg or not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
                raise bad(key)
            if info.st_uid != host.uid:
                raise bad(key)
        elif key == "DBUS_SESSION_BUS_ADDRESS":
            if value != f"unix:path={present.get('XDG_RUNTIME_DIR', xdg)}/bus":
                raise bad(key)
        elif key == "SSH_AUTH_SOCK":
            try:
                info = os.stat(value)
            except OSError:
                raise bad(key) from None
            if not value.startswith("/") or not stat.S_ISSOCK(info.st_mode):
                raise bad(key)
            if info.st_uid != host.uid:
                raise bad(key)
        elif key == "HEAVY_LOCK" and not value.startswith("/"):
            raise bad(key)
    return present


def _stat_id(path: str) -> tuple[int, int] | None:
    try:
        info = os.stat(path)
    except OSError:
        return None
    return info.st_dev, info.st_ino


def _resolve_runtime(
    host: ap.Host, dirs: list[str], runtime: str = RUNTIME
) -> tuple[str, tuple[int, int]]:
    """The first selected runtime in the executed PATH, reached safely and an ELF."""
    for directory in dirs:
        candidate = f"{directory}/{runtime}"
        try:
            found = ap._walk(candidate, host)
        except ap._Unsafe as exc:
            raise Refusal(2, "unsafe-path", f"{candidate}: {exc}") from None
        if found is None:
            continue
        problem = ap._file_problem(found.st, host.uid, caller_only=False)
        if problem or not found.st.st_mode & 0o111:
            raise Refusal(2, "unsafe-path", f"{candidate}: {problem or 'not executable'}")
        if "/mise/shims/" in candidate or Path(found.real).name == "mise":
            raise Refusal(2, "unsupported-runtime", f"{candidate} is a mise shim")
        if not is_elf(found.real):
            raise Refusal(2, "unsupported-runtime", f"{found.real} is not an ELF program")
        return found.real, (found.st.st_dev, found.st.st_ino)
    raise Refusal(2, "unsupported-runtime", f"no {runtime} in the policy PATH")


def is_elf(path: str) -> bool:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return False
    try:
        return os.read(fd, 4) == b"\x7fELF"
    finally:
        os.close(fd)


def prepare(host: ap.Host, name: str, environ: Mapping[str, str]) -> tuple[Plan, dict[str, str]]:
    """Step 1: validate policy and row, read only. Raises ``Refusal`` (exit 2) on any problem."""
    report = ap.check(host, name)
    if not report.ok:
        raise PolicyInvalid(report)
    row = next(r for r in report.policy["agents"] if r["name"] == name)
    runtime = row["runtime"]
    home = report.home
    if row["profile"] == ap.DEFAULT:
        profile = f"{home}/.{runtime}"
    else:
        profile = report.profiles[row["profile"]][runtime]
    runtime_real, runtime_id = _resolve_runtime(host, report.path, runtime)
    passed = _passed_env(host, environ, ssh_agent=row.get("ssh_agent", False))
    pw = pwd.getpwuid(host.uid)
    env_set = {
        "HOME": home,
        "USER": pw.pw_name,
        "LOGNAME": pw.pw_name,
        "SHELL": pw.pw_shell,
        "PATH": ":".join(report.path),
        "MB_ROLE": row["role"],
    }
    if row["profile"] != ap.DEFAULT:
        env_set["CLAUDE_CONFIG_DIR" if runtime == "claude" else "CODEX_HOME"] = profile
    kept = set(env_set) | set(passed)
    dropped: dict[str, list[str]] = {}
    for key in sorted(set(environ) - kept):
        prefix = next((p for p in DROP_PREFIXES if key.startswith(p)), "other")
        if key == "SSH_AUTH_SOCK" and not row.get("ssh_agent", False):
            prefix = "row ssh_agent is off"
        dropped.setdefault(prefix, []).append(key)
    return Plan(
        name=name,
        row=row,
        row_rev=row_rev(row),
        home=home,
        store=Store(Path(report.store), host.uid),
        runtime_real=runtime_real,
        runtime_id=runtime_id,
        cwd_real=row["cwd"],
        card_real=report.cards[name],
        profile_real=profile,
        profile_id=_stat_id(profile),
        policy_profiles=[d[runtime] for d in report.profiles.values() if runtime in d],
        env_set=env_set,
        env_passed=sorted(passed),
        dropped=dropped,
    ), passed


# --- processes ----------------------------------------------------------------------------


def boot_id() -> str:
    try:
        return Path(f"{PROC}/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        raise Refusal(4, "no-proc", "cannot read the boot id") from None


def start_time(pid: int) -> int:
    """Field 22 of /proc/<pid>/stat, in clock ticks since boot."""
    text = Path(f"{PROC}/{pid}/stat").read_text()
    rest = text[text.rindex(")") + 2 :].split()
    return int(rest[19])


def _proc_state(pid: int) -> str:
    text = Path(f"{PROC}/{pid}/stat").read_text()
    return text[text.rindex(")") + 2 :].split()[0]


def identity(pid: int, start: int, boot: str) -> str:
    """``live``, ``dead`` or ``unknown:<tag>``. Unknown is never dead."""
    if boot != boot_id():
        return "dead"
    try:
        if _proc_state(pid) in ("Z", "X"):
            return "dead"
        return "live" if start_time(pid) == start else "dead"
    except (FileNotFoundError, ProcessLookupError):
        return "dead"
    except PermissionError:
        return "unknown:proc-denied"
    except (ValueError, IndexError):
        return "unknown:inconsistent"
    except OSError:
        return "unknown:proc-denied"


def owners_of(device: int, inode: int) -> list[int] | None:
    """The pids /proc/locks lists for the file with this device and inode; None when unreadable.

    The table prints ``major:minor:inode``, the device parts in hex. A line that does not parse is
    not this file.
    """
    try:
        lines = Path(f"{PROC}/locks").read_text().splitlines()
    except OSError:
        return None
    owners: list[int] = []
    for line in lines:
        parts = line.split()
        if len(parts) < 6 or parts[1] != "FLOCK":
            continue
        try:
            major, minor, ino = parts[5].split(":")
            same = os.makedev(int(major, 16), int(minor, 16)) == device and int(ino) == inode
            pid = int(parts[4])
        except ValueError:
            continue
        if same:
            owners.append(pid)
    return owners


def lock_owners(lock: FileLock) -> list[int] | None:
    """The pids /proc/locks lists for this lock file; None when it cannot be read."""
    return owners_of(lock.device, lock.inode)


def lock_owner(lock: FileLock) -> int | None:
    """The first pid /proc/locks lists for this lock file; None when unreadable or absent."""
    owners = lock_owners(lock)
    return owners[0] if owners else None


def cmdline_scan(session_id: str, uid: int) -> tuple[list[int], list[int]]:
    """Same-uid processes naming the session id, and the pids that could not be read.

    A process that exited mid-scan is not unreadable. Any other failure to stat a candidate or
    read its command line leaves that pid in the second list: the scan is then incomplete.
    """
    needle = session_id.encode()
    hits: list[int] = []
    unreadable: list[int] = []
    for entry in os.listdir(PROC):
        if not entry.isdigit() or int(entry) == os.getpid():
            continue
        try:
            if os.stat(f"{PROC}/{entry}").st_uid != uid:
                continue
            if needle in Path(f"{PROC}/{entry}/cmdline").read_bytes():
                hits.append(int(entry))
        except (FileNotFoundError, ProcessLookupError):
            continue
        except OSError:
            unreadable.append(int(entry))
    return hits, unreadable


def cmdline_hits(session_id: str, uid: int) -> list[int]:
    """Same-uid processes whose command line names the session id (a tripwire, not proof)."""
    return cmdline_scan(session_id, uid)[0]


# --- finding a transcript: the finite search ----------------------------------------------


class Where(Protocol):
    """What the search needs to know: ``Plan`` for ``up``, a small record for ``check``."""

    home: str
    profile_real: str
    policy_profiles: list[str]

    @property
    def runtime(self) -> str: ...


@dataclass
class Search:
    found: list[tuple[str, str, float]] = field(default_factory=list)  # profile, file, mtime
    incomplete: str | None = None

    def under(self, profile: str) -> bool:
        return any(p == profile for p, _, _ in self.found)


def _look(
    profile: str,
    expect: tuple[int, int] | None,
    session_id: str,
    out: Search,
    folder: str | None = None,
    runtime: str = RUNTIME,
) -> None:
    """Candidates under the profile's projects; with ``folder``, only that one project folder."""
    try:
        info = os.lstat(profile)
    except FileNotFoundError:
        if expect is not None:
            out.incomplete = out.incomplete or f"profile missing: {profile}"
        return
    except OSError as exc:
        out.incomplete = out.incomplete or f"profile unreadable: {profile}: {exc.strerror}"
        return
    if not stat.S_ISDIR(info.st_mode) or (expect and expect != (info.st_dev, info.st_ino)):
        out.incomplete = out.incomplete or f"profile changed: {profile}"
        return
    if runtime == "codex":
        for row in cx.rollouts(profile, expect, SEARCH_ENTRY_CAP):
            if row.sid == session_id:
                out.found.append((profile, row.path, row.mtime))
        return
    if folder is not None:
        _candidate(profile, f"{profile}/projects/{folder}/{session_id}.jsonl", out)
        return
    count = 0
    try:
        with os.scandir(f"{profile}/projects") as entries:
            for entry in entries:
                count += 1
                if count > SEARCH_ENTRY_CAP:
                    out.incomplete = out.incomplete or f"entry cap hit: {profile}"
                    return
                _candidate(profile, f"{entry.path}/{session_id}.jsonl", out)
    except FileNotFoundError:
        return
    except OSError as exc:
        out.incomplete = out.incomplete or f"projects unreadable: {profile}: {exc.strerror}"


def _candidate(profile: str, path: str, out: Search) -> None:
    def unsupported() -> None:
        out.incomplete = out.incomplete or f"unsupported transcript format: {path}"

    try:
        info = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return
    except OSError as exc:
        out.incomplete = out.incomplete or f"cannot read {path}: {exc.strerror}"
        return
    if not stat.S_ISREG(info.st_mode):  # a FIFO, device or link would block or misread
        return unsupported()
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return unsupported()
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):  # swapped after the lstat
            return unsupported()
        with os.fdopen(fd, "rb", closefd=False) as handle:
            first = handle.readline(65_536)
        ok = isinstance(json.loads(first), dict)
    except (OSError, ValueError):
        ok = False
    finally:
        os.close(fd)
    if ok:
        out.found.append((profile, path, info.st_mtime))
    else:
        unsupported()


def chain_of(store: Store, last: str | None) -> list[dict[str, Any]]:
    """The attempts from ``last`` back through ``previous_attempt``, at most CHAIN_LIMIT."""
    chain: list[dict[str, Any]] = []
    while last is not None and len(chain) < CHAIN_LIMIT:
        record = store.read_attempt(last)
        chain.append(record)
        last = record.get("previous_attempt")
    if last is not None:
        raise Refusal(4, "search-incomplete", f"attempt chain is longer than {CHAIN_LIMIT}")
    return chain


def search(plan: Where, chain: list[dict[str, Any]], session_id: str) -> Search:
    """Profiles of this id's attempts, every policy profile for the runtime, and default."""
    out = Search()
    seen: set[str] = set()
    scope: list[tuple[str, tuple[int, int] | None]] = []
    for record in chain:
        if record.get("session_id") == session_id and record["profile_real"] not in seen:
            seen.add(record["profile_real"])
            expect = record.get("profile_id")
            scope.append((record["profile_real"], tuple(expect) if expect else None))
    for profile in [*plan.policy_profiles, plan.profile_real, f"{plan.home}/.{plan.runtime}"]:
        if profile not in seen:
            seen.add(profile)
            scope.append((profile, None))
    for profile, expect in scope:
        _look(profile, expect, session_id, out, runtime=plan.runtime)
    return out


# --- the lock table and recovery ----------------------------------------------------------


@dataclass
class Decision:
    mode: str
    session_id: str | None
    provenance: str
    previous: str | None


def _runtime_state(last: dict[str, Any]) -> str:
    return identity(last["runtime_pid"], last["runtime_start"], last["boot_id"])


def _unknown(state: str, last: dict[str, Any]) -> Refusal:
    return Refusal(
        4, state.split(":", 1)[1], f"cannot tell if runtime pid {last['runtime_pid']} lives"
    )


def _cross_check(store: Store, name: str, row: dict[str, Any] | None) -> dict[str, Any] | None:
    """The row's last attempt, agreeing with state; any disagreement is ``corrupt-state``."""
    if row is None:
        return None
    last = store.read_attempt(row["last_attempt"])
    same = (
        last.get("name") == name
        and last.get("session_id") == row["session_id"]
        and last.get("row_rev") == row["row_rev"]
        and last.get("session_provenance") == row["session_provenance"]
        and (last.get("mode") not in ("new", "new-retry") or row["session_provenance"] == "spawned")
    )
    if not same:
        raise Refusal(4, "corrupt-state", f"attempt {row['last_attempt']} disagrees with state")
    return last


def _held(plan: Plan, lock: FileLock) -> None:
    """The row lock is held elsewhere: raise, or return once a retry takes the lock."""
    deadline = time.monotonic() + ORPHAN_RETRY_SECONDS
    while True:
        owner = lock_owner(lock)
        brief = plan.store.store_lock()
        try:
            row = plan.store.read_state().get(plan.name)
            last = plan.store.read_attempt(row["last_attempt"]) if row else None
        finally:
            brief.close()
        holder = last is not None and owner == last["holder_pid"]
        if holder and last is not None:
            holder = identity(last["holder_pid"], last["holder_start"], last["boot_id"]) == "live"
        if not holder or last is None:
            where = f"lock held by pid {owner}" if owner else "lock held by an unreadable owner"
            raise Refusal(4, "lock-owner-unknown", where)
        state = _runtime_state(last)
        if state == "live":
            raise Refusal(5, "live", f"runtime pid {last['runtime_pid']} is running")
        if state.startswith("unknown"):
            raise _unknown(state, last)
        if time.monotonic() >= deadline:
            raise Refusal(4, "lock-orphan", f"holder pid {owner} holds the lock; runtime is gone")
        time.sleep(0.05)
        if lock.try_lock():
            return


def decide(
    plan: Plan,
    row: dict[str, Any] | None,
    chain: list[dict[str, Any]],
    *,
    new: bool,
    session: str | None,
    seen: dict[str, Search],
) -> Decision:
    previous = chain[0]["id"] if chain else None

    def evidence(sid: str) -> Search:
        if sid not in seen:
            seen[sid] = search(plan, chain, sid)
        return seen[sid]

    if new:
        sid = None if plan.runtime == "codex" else str(uuid.uuid4())
        return Decision("new", sid, "spawned", previous)
    if row is None and session is None:
        raise Refusal(5, "no-session", "no stored session for this agent; use --new or --session")
    if session is not None and (row is None or row["session_id"] != session):
        sid, provenance = session, "owner-confirmed"
    else:
        assert row is not None
        sid, provenance = row["session_id"], row["session_provenance"]
        if sid is None:
            if plan.runtime == "codex":
                hint = cx.hints(cx.discover(chain[0], SEARCH_ENTRY_CAP)) if chain else ""
                raise Refusal(5, "no-session", "use --session <id> or --new; " + hint)
            raise Refusal(4, "corrupt-state", "a claude row has no session id")
    found = evidence(sid)
    if found.incomplete:
        raise Refusal(4, "search-incomplete", found.incomplete)
    if found.under(plan.profile_real):
        if plan.runtime == "codex" and not any(
            r.sid == sid and r.cwd == plan.cwd_real
            for r in cx.rollouts(plan.profile_real, plan.profile_id, SEARCH_ENTRY_CAP)
        ):
            raise Refusal(4, "wrong-cwd", "the rollout is not for the selected working folder")
        return Decision("resume", sid, provenance, previous)
    if found.found:
        raise Refusal(4, "wrong-profile", "the transcript is under another profile")
    if provenance == "spawned":
        return Decision("new-retry", sid, provenance, previous)
    if plan.runtime == "codex" and session is not None:
        raise Refusal(2, "no-session-evidence", "no rollout under the selected Codex profile")
    raise Refusal(4, "no-session-evidence", "no transcript for an id mb did not create")


def _tripwire(plan: Plan, last: dict[str, Any], seen: dict[str, Search]) -> None:
    sid = last["session_id"]
    if sid is None:
        if plan.runtime == "codex":
            recent = [
                r.path
                for r in cx.discover(last, SEARCH_ENTRY_CAP)
                if _now() - r.mtime < TRIPWIRE_SECONDS
            ]
            if recent:
                raise Refusal(4, "session-seen", "; ".join(recent))
        return
    seen[sid] = search(plan, chain_of(plan.store, last["id"]), sid)
    recent = [f for _, f, mtime in seen[sid].found if _now() - mtime < TRIPWIRE_SECONDS]
    pids = cmdline_hits(sid, plan.store.uid)
    if recent or pids:
        names = [f"pid {p}" for p in pids] + recent
        raise Refusal(4, "session-seen", "; ".join(names))
    if (why := seen[sid].incomplete) is not None:  # before --new or any resume
        raise Refusal(4, "search-incomplete", why)


def _reserve(plan: Plan, state: dict[str, dict[str, Any]], sid: str | None) -> None:
    if sid is None:
        return
    for other, row in state.items():
        if other == plan.name:
            continue
        last = plan.store.read_attempt(row["last_attempt"])
        if sid in (row["session_id"], last.get("session_id")):
            raise Refusal(5, "alias", f"session id belongs to agent {other}")


# --- the holder ---------------------------------------------------------------------------


def _child(rfd: int, plan: Plan, argv: list[str], env: dict[str, str]) -> None:
    """Runs in the forked child only. Never returns: it execs, or exits without running anything."""
    try:
        for fd in os.listdir("/proc/self/fd"):
            if int(fd) > 2 and int(fd) != rfd:
                with contextlib.suppress(OSError):
                    os.close(int(fd))
        for sig in signal.valid_signals():
            if sig not in (signal.SIGKILL, signal.SIGSTOP):
                with contextlib.suppress(OSError, ValueError):
                    signal.signal(sig, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_SETMASK, ())
        if os.read(rfd, 1) == b"1":
            os.chdir(plan.cwd_real)
            os.execve(plan.runtime_real, argv, env)
    except BaseException:  # noqa: BLE001
        pass
    with contextlib.suppress(OSError):
        os.write(2, b"mb agent up: the runtime could not be started (exit 127)\n")
    os._exit(127)


def _record(
    plan: Plan, decision: Decision, argv: list[str], holder: int, child: int
) -> dict[str, Any]:
    utc = datetime.now(timezone.utc)
    return {
        "id": f"{plan.name}.{utc:%Y%m%dT%H%M%SZ}.{secrets.token_hex(4)}",
        "name": plan.name,
        "runtime": plan.runtime,
        "row_rev": plan.row_rev,
        "utc": utc.isoformat(),
        "mode": decision.mode,
        "session_id": decision.session_id,
        "session_provenance": decision.provenance,
        "uid": plan.store.uid,
        "boot_id": boot_id(),
        "holder_pid": holder,
        "holder_start": start_time(holder),
        "runtime_pid": child,
        "runtime_start": start_time(child),
        "runtime_real": plan.runtime_real,
        "runtime_id": list(plan.runtime_id),
        "cwd_real": plan.cwd_real,
        "card_real": plan.card_real,
        "profile_real": plan.profile_real,
        "profile_id": list(plan.profile_id) if plan.profile_id else None,
        "argv": argv,
        "env_set": plan.env_set,
        "env_passed": plan.env_passed,
        "previous_attempt": decision.previous,
    }


def _hold(
    plan: Plan,
    state: dict[str, dict[str, Any]],
    decision: Decision,
    passed: Mapping[str, str],
    store_lock: FileLock,
) -> int:
    """Steps 5-7: fork, record, commit, release, go, wait. Returns the runtime's exit status."""
    argv = plan.argv(decision.mode, decision.session_id)
    env = {**plan.env_set, **passed}
    rfd, wfd = os.pipe()
    pid = os.fork()
    if pid == 0:
        _child(rfd, plan, argv, env)
    os.close(rfd)
    record: dict[str, Any] = {}
    try:
        _step("after-fork")
        record = _record(plan, decision, argv, os.getpid(), pid)
        plan.store.write_attempt(record)
        state[plan.name] = {
            "session_id": decision.session_id,
            "session_provenance": decision.provenance,
            "row_rev": plan.row_rev,
            "last_attempt": record["id"],
        }
        plan.store.write_state(state)
        _step("after-commit")
    except (OSError, ValueError) as exc:
        os.close(wfd)  # the child gets EOF and exits without exec
        _waitpid(pid)
        raise Refusal(
            5, "record-failed", f"nothing was started: {getattr(exc, 'strerror', None) or exc}"
        ) from None
    store_lock.close()
    _step("after-release")
    try:
        _step("before-go", pid)
        os.write(wfd, b"1")
    except OSError:
        os.close(wfd)
        _waitpid(pid)
        plan.store.write_exit(record["id"], {"id": record["id"], "status": "never-execed"})
        raise Refusal(5, "go-failed", "the child ended before it could start the runtime") from None
    os.close(wfd)
    _step("after-go")
    try:
        _step("waitpid")
        raw = _waitpid(pid)
    except OSError:
        raise Refusal(
            4, "wait-lost", f"cannot wait for runtime pid {pid}; it may still run"
        ) from None
    code = os.waitstatus_to_exitcode(raw)
    plan.store.write_exit(record["id"], {"id": record["id"], "status": code, "utc": _now()})
    return code if code >= 0 else 128 - code


# --- the verb -----------------------------------------------------------------------------


def up(
    host: ap.Host,
    name: str,
    *,
    new: bool = False,
    session: str | None = None,
    dry_run: bool = False,
    environ: Mapping[str, str] | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    out, err = out or sys.stdout, err or sys.stderr
    try:
        return _up(
            host, name, new, session, dry_run, os.environ if environ is None else environ, out
        )
    except PolicyInvalid as exc:
        print("Policy not valid.", file=err)
        for problem in exc.report.problems:
            print(f"  {problem.text()}", file=err)
        return exc.exit_code
    except Refusal as exc:
        print(
            f"mb: agent up: refused ({exc.exit_code} {exc.tag}): "
            + roles.printable(exc.detail, len(exc.detail) if exc.tag == "no-session" else 300),
            file=err,
        )
        return exc.exit_code


def _up(
    host: ap.Host,
    name: str,
    new: bool,
    session: str | None,
    dry_run: bool,
    environ: Mapping[str, str],
    out: TextIO,
) -> int:
    if new and session is not None:
        raise Refusal(2, "bad-args", "--new and --session cannot be used together")
    if session is not None and not UUID_RE.fullmatch(session):
        raise Refusal(2, "bad-args", "--session needs a lowercase session id (uuid)")
    plan, passed = prepare(host, name, environ)
    store = plan.store
    store.prepare(create=not dry_run)
    seen: dict[str, Search] = {}
    if dry_run:
        state = store.read_state()
        row = state.get(name)
        last = _cross_check(store, name, row)
        decision = decide(
            plan,
            row,
            chain_of(store, last["id"] if last else None),
            new=new,
            session=session,
            seen=seen,
        )
        _dry_run(plan, decision, out)
        return 0
    lock = store.row_lock(name)
    old = {
        s: signal.signal(s, signal.SIG_IGN) for s in (signal.SIGINT, signal.SIGQUIT, signal.SIGHUP)
    }
    store_lock: FileLock | None = None
    try:
        if not lock.try_lock():
            _held(plan, lock)
        store_lock = store.store_lock()
        state = store.read_state()
        row = state.get(name)
        last = _cross_check(store, name, row)
        if last is not None:
            ident = _runtime_state(last)
            if ident == "live":
                raise Refusal(
                    4, "holder-lost", f"runtime pid {last['runtime_pid']} lives; no holder"
                )
            if ident.startswith("unknown"):
                raise _unknown(ident, last)
            _tripwire(plan, last, seen)
        decision = decide(
            plan,
            row,
            chain_of(store, last["id"] if last else None),
            new=new,
            session=session,
            seen=seen,
        )
        _reserve(plan, state, decision.session_id)
        return _hold(plan, state, decision, passed, store_lock)
    finally:
        if store_lock is not None:
            store_lock.close()
        lock.close()
        for sig, handler in old.items():
            signal.signal(sig, handler)


def _dry_run(plan: Plan, decision: Decision, out: TextIO) -> None:
    """Prints the command and the plan. Passed variables appear by name only."""
    sid = decision.session_id if decision.mode != "new" else "<chosen at launch>"
    argv = plan.argv(decision.mode, sid)
    lines = [
        "Dry run: nothing started, nothing written, no lock taken.",
        f"agent: {plan.name} (role {plan.row['role']}, {plan.runtime})",
        f"mode: {decision.mode} ({decision.provenance} session)",
        "command: " + shlex.join([plan.runtime_real, *argv[1:]]),
        f"cwd: {plan.cwd_real}",
        f"card: {plan.card_real}",
        f"profile: {plan.profile_real}",
    ]
    lines += [f"env set: {k}={shlex.quote(v)}" for k, v in plan.env_set.items()]
    lines += [f"env passed: {k} (value not shown)" for k in plan.env_passed]
    for prefix, names in plan.dropped.items():
        lines.append(
            f"env dropped: {prefix}{'*' if prefix in DROP_PREFIXES else ''}: {', '.join(names)}"
        )
    lines.append(DRY_RUN_NOTE)
    print("\n".join(lines), file=out)
