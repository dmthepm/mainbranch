"""mb agent check <name> --smoke-marker <marker>: the lifetime smoke verdict, and nothing else.

The smoke runs against a disposable fixture row, started with ``mb agent up``. Its start_file asks
the agent to run one foreground tool command, ``sh -c 'echo $$ > <marker>; sleep 120'``. While that
sleeps, this reads /proc and judges whether the process running the tool is a descendant of the
recorded runtime process, through nothing but reviewed helpers. That is what separates a runtime
that keeps its session in the process mb exec'd from an ELF that forks, waits, and lets a child do
the work (``check`` alone cannot see that: the waiting parent still matches its attempt).

A pass is evidence for the installed version under this one observation. It is not proof for
every session or mode, and mb does not run it at launch. Nothing here signals, kills or types.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, TextIO

from mb import agent_policy as ap
from mb import agent_up as au
from mb import roles
from mb.agent_store import Refusal, Store

# Shells and the sandbox helper a tool command may run under, by real path. The design keeps the
# reviewed list per runtime version with homelab and says the first smoke produces it; until that
# list exists this short built-in one stands in. Anything else between the tool command and the
# runtime fails the smoke.
DEFAULT_HELPERS = (
    "/bin/sh",
    "/bin/dash",
    "/bin/bash",
    "/bin/zsh",
    "/usr/bin/bwrap",
)
HELPERS = DEFAULT_HELPERS
MAX_LINKS = 8
PID_MAX = 4_194_304
MARKER_BYTES = 32


def _read(pid: int, name: str) -> bytes:
    """One /proc file of one pid. Denied is unknown (4); gone is ``inconsistent`` (4)."""
    try:
        return Path(f"{au.PROC}/{pid}/{name}").read_bytes()
    except PermissionError:
        raise Refusal(4, "proc-denied", f"cannot read /proc/{pid}/{name}") from None
    except OSError:
        raise Refusal(4, "inconsistent", f"/proc/{pid}/{name} disappeared") from None


def _link(pid: int, name: str) -> str:
    try:
        return os.readlink(f"{au.PROC}/{pid}/{name}")
    except PermissionError:
        raise Refusal(4, "proc-denied", f"cannot read /proc/{pid}/{name}") from None
    except OSError:
        raise Refusal(4, "inconsistent", f"/proc/{pid}/{name} disappeared") from None


def _parent(pid: int) -> int:
    text = _read(pid, "stat").decode(errors="replace")
    try:
        return int(text[text.rindex(")") + 2 :].split()[1])
    except (ValueError, IndexError):
        raise Refusal(4, "inconsistent", f"/proc/{pid}/stat is unreadable as a process") from None


def _marker_pid(marker: str) -> int:
    """The pid the tool command wrote. Missing or odd is ``no-marker``: the tool has not run."""
    try:
        with open(marker, "rb") as f:
            text = f.read(MARKER_BYTES).decode(errors="replace").strip()
    except OSError:
        raise Refusal(
            4, "no-marker", "the marker file is missing; the tool command has not run"
        ) from None
    if not text.isascii() or not text.isdigit() or not 1 < int(text) < PID_MAX:
        raise Refusal(4, "no-marker", "the marker file does not hold one process id")
    pid = int(text)
    if not os.path.isdir(f"{au.PROC}/{pid}"):
        raise Refusal(4, "no-marker", f"marker pid {pid} is not running")
    return pid


def _attempt(host: ap.Host, name: str) -> dict[str, Any]:
    report = ap.check(host, name)
    if not report.ok:
        raise au.PolicyInvalid(report)
    store = Store(Path(report.store), host.uid)
    store.prepare(create=False)
    row = store.read_state().get(name)
    if row is None:
        raise Refusal(4, "no-session-evidence", f"{name} has no recorded launch to check")
    return store.read_attempt(row["last_attempt"])


def _chain(marker: int, runtime: int, runtime_real: str, runtime_id: tuple[int, int]) -> list[str]:
    """Why the tool command is not the session's own child chain; empty when it is."""
    helpers = {os.path.realpath(p) for p in HELPERS}
    cur, links, between = marker, 0, []
    while True:
        parent = _parent(cur)
        links += 1
        if parent == runtime:
            break
        if parent <= 1:
            return [f"marker pid {marker} does not descend from runtime pid {runtime}"]
        if links >= MAX_LINKS:
            return [f"marker pid {marker} is over {MAX_LINKS} links below runtime pid {runtime}"]
        between.append(parent)
        cur = parent
    problems = []
    for pid in between:
        exe = os.path.realpath(_link(pid, "exe"))
        shown = roles.printable(exe, 120)
        try:
            info = os.stat(f"{au.PROC}/{pid}/exe")
            same = (info.st_dev, info.st_ino) == runtime_id
        except OSError:
            same = False
        if same or exe == runtime_real:
            problems.append(f"pid {pid} between them is the runtime itself ({shown})")
        elif exe not in helpers:
            problems.append(f"pid {pid} between them ({shown}) is not a reviewed helper")
    return problems


def _environ(pid: int) -> dict[str, str]:
    pairs = (p.partition(b"=") for p in _read(pid, "environ").split(b"\0") if p)
    return {k.decode(errors="replace"): v.decode(errors="replace") for k, _, v in pairs}


def _verdict(host: ap.Host, name: str, marker: str, out: TextIO) -> int:
    attempt = _attempt(host, name)
    pid, boot, start = (
        int(attempt["runtime_pid"]),
        attempt["boot_id"],
        int(attempt["runtime_start"]),
    )
    runtime_id = (int(attempt["runtime_id"][0]), int(attempt["runtime_id"][1]))
    state = au.identity(pid, start, boot)
    if state.startswith("unknown"):
        raise Refusal(4, state.split(":", 1)[1], f"runtime pid {pid} cannot be read")
    if state == "dead":
        raise Refusal(3, "ended", f"runtime pid {pid} has ended; the smoke needs it running")
    marker_pid = _marker_pid(marker)
    try:
        info = os.stat(f"{au.PROC}/{pid}/exe")
    except PermissionError:
        raise Refusal(4, "proc-denied", f"cannot read /proc/{pid}/exe") from None
    except OSError:
        raise Refusal(4, "inconsistent", f"/proc/{pid}/exe disappeared") from None
    if (info.st_dev, info.st_ino) != runtime_id:
        raise Refusal(4, "exe-changed", f"runtime pid {pid} no longer runs the recorded program")
    env = _environ(pid)
    cwd = _link(pid, "cwd")
    env_set: dict[str, str] = attempt["env_set"]
    passed: list[str] = attempt["env_passed"]
    sid = attempt["session_id"]
    others = [p for p in au.cmdline_hits(sid, host.uid) if p not in (pid, attempt["holder_pid"])]
    if others:
        raise Refusal(4, "session-seen", f"another process carries the session id: {others}")
    chain = _chain(marker_pid, pid, attempt["runtime_real"], runtime_id)
    fields = []
    if set(env) != set(env_set) | set(passed) or any(env.get(k) != v for k, v in env_set.items()):
        fields.append("environ")
    if cwd != attempt["cwd_real"]:
        fields.append("cwd")
    if chain or fields:
        for text in chain:
            print(f"fail (1 not-session-process): {text}", file=out)
        if fields:
            print(f"fail (1 mismatch): {', '.join(fields)} differ from the attempt", file=out)
        return 1
    names = ", ".join(sorted(passed)) or "none"
    print(
        f"smoke ok: marker pid {marker_pid} runs under runtime pid {pid}, through reviewed "
        f"helpers only; the program, environment names, mb-set values and folder match the "
        f"attempt.\nThis is evidence for this version, under this one observation. It is not "
        f"proof for every session or mode, and mb does not run it at launch. Passed values "
        f"(names: {names}) are not stored and passed values are not compared.",
        file=out,
    )
    return 0


def smoke(
    host: ap.Host,
    name: str,
    marker: str,
    *,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Exit 0 pass, 1 fail, 3 runtime ended, 4 unknown, 2 policy. Failures print to ``out``."""
    out, err = out or sys.stdout, err or sys.stderr
    try:
        return _verdict(host, name, marker, out)
    except au.PolicyInvalid as exc:
        print("Policy not valid.", file=err)
        for problem in exc.report.problems:
            print(f"  {problem.text()}", file=err)
        return exc.exit_code
    except Refusal as exc:
        print(
            f"mb: agent check --smoke-marker: no verdict ({exc.exit_code} {exc.tag}): "
            + roles.printable(exc.detail, 300),
            file=err,
        )
        return exc.exit_code
