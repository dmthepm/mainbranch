"""mb machine update: a read-only plan of what updating this one machine would change.

Nothing here installs, upgrades, attaches or runs as root. Every read is a fixed
argv chosen in this file, run without a shell and with a clean environment. A read
that failed, timed out or came back malformed is never reported as "no updates".
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import pwd
import re
import selectors
import shlex
import signal
import stat
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mb import machine_probe as probe

DEFAULT_BYTE_CAP = 1024 * 1024
OVERALL_SECONDS = 300
LISTS_STALE_DAYS = 7
GIB = 1024**3
MIB = 1024**2
DISK_FLOORS = {"/": 2 * GIB, "/var": 2 * GIB, "/boot": 256 * MIB}
BASE_ENV = {"LC_ALL": "C", "PATH": "/usr/bin:/bin"}

APT = ("/usr/bin/apt", "list", "--upgradable")
PRO = ("/usr/bin/pro", "status", "--format", "json")
SOFTWAREUPDATE = ("/usr/sbin/softwareupdate", "-l")
SYSTEM_EXECUTABLES = frozenset({APT[0], PRO[0], SOFTWAREUPDATE[0]})
OWNER_CANDIDATES: dict[str, tuple[str, ...]] = {
    "mise": ("~/.local/bin/mise", "/usr/local/bin/mise", "/usr/bin/mise", "/opt/homebrew/bin/mise"),
    "brew": (
        "/opt/homebrew/bin/brew",
        "/usr/local/bin/brew",
        "/home/linuxbrew/.linuxbrew/bin/brew",
    ),
}

# Rank of a read state, worst last. not_present is neutral: the tool is simply not here.
READ_RANK = {
    s: i
    for i, s in enumerate(
        ("not_present", "ok", "not_verified", "unreachable", "incomplete", "failed")
    )
}
NETWORK = re.compile(
    rb"could not resolve|temporary failure in name resolution|network is unreachable"
    rb"|error sending request|connection (?:refused|timed out)|unable to connect|no route to host",
    re.IGNORECASE,
)
VERSION = r"[A-Za-z0-9.+~:_\-]{1,64}"
_VERSION = re.compile(VERSION + r"\Z")
_TOOL = re.compile(r"[A-Za-z0-9._:/@\-]{1,100}\Z")
_APT_LINE = re.compile(
    r"(?P<name>[a-z0-9][a-z0-9+.\-]{0,99})/[A-Za-z0-9.,_\-]+ (?P<new>" + VERSION + r") "
    r"[a-z0-9_\-]+ \[upgradable from: (?P<old>" + VERSION + r")\]\Z"
)
_SWU_TITLE = re.compile(
    r"\s*Title: (?P<title>[^,]{1,100}), Version: (?P<ver>[^,]{1,40}), Size: [^,]+,(?P<rest>.*)\Z"
)
REBOOT_PREFIXES = ("linux-image", "linux-generic", "linux-hwe", "linux-modules")
REBOOT_NAMES = frozenset({"libc6", "systemd", "dbus"})


@dataclass(frozen=True)
class Out:
    """One finished read. ``reason`` is set only when it did not finish normally."""

    data: bytes = b""
    err: bytes = b""
    returncode: int | None = None
    reason: str | None = None  # timeout, output_cap, missing, untrusted, error


def run_read(
    argv: tuple[str, ...],
    *,
    timeout: float,
    merge_stderr: bool = False,
    byte_cap: int = DEFAULT_BYTE_CAP,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> Out:
    """Run one argv with no shell, a clean environment, a time limit and an output cap."""
    deadline = time.monotonic() + timeout
    try:
        process = subprocess.Popen(  # noqa: S603
            list(argv),
            shell=False,
            env=BASE_ENV if env is None else env,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            close_fds=True,
            start_new_session=True,
        )
    except (FileNotFoundError, NotADirectoryError):
        return Out(reason="missing")
    except OSError:
        return Out(reason="error")
    buffers = {"out": bytearray(), "err": bytearray()}
    reason: str | None = None
    try:
        with selectors.DefaultSelector() as selector:
            assert process.stdout is not None
            selector.register(process.stdout, selectors.EVENT_READ, "out")
            if process.stderr is not None:
                selector.register(process.stderr, selectors.EVENT_READ, "err")
            while selector.get_map() and reason is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    reason = "timeout"
                    break
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    buffers[key.data].extend(chunk)
                    if len(buffers[key.data]) > byte_cap:
                        reason = "output_cap"
                        break
        code = None
        if reason is None:
            try:
                code = process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                reason = "timeout"
    finally:
        if process.poll() is None or reason:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
    if reason:
        return Out(reason=reason)
    return Out(bytes(buffers["out"]), bytes(buffers["err"]), code)


def owner_executable_ok(path: Path | str) -> bool:
    """An owner-run tool is ours (or root's) and nobody else can swap it."""
    try:
        path = Path(path)
        real = path.resolve(strict=True)
        owners = {0, os.geteuid()}
        if not stat.S_ISREG(real.stat().st_mode) or not os.access(real, os.X_OK):
            return False
        for candidate in (real, *real.parents, *path.parents):
            info = candidate.stat()
            sticky_dir = stat.S_ISDIR(info.st_mode) and info.st_mode & stat.S_ISVTX
            if info.st_uid not in owners or (info.st_mode & 0o022 and not sticky_dir):
                return False
        return True
    except OSError:
        return False


def _home() -> str:
    return pwd.getpwuid(os.geteuid()).pw_dir


def find_owner_tool(name: str) -> str | None:
    """First existing fixed candidate for an owner's tool. PATH is never searched."""
    for candidate in OWNER_CANDIDATES[name]:
        path = candidate.replace("~", _home(), 1) if candidate.startswith("~") else candidate
        if os.path.lexists(path):
            return path
    return None


def local_run(argv: tuple[str, ...], *, timeout: float, merge_stderr: bool = False) -> Out:
    """The real runner: trust the executable first, then run it read-only."""
    system = argv[0] in SYSTEM_EXECUTABLES
    if not (probe._trusted_executable(Path(argv[0])) if system else owner_executable_ok(argv[0])):  # noqa: SLF001
        return Out(reason="untrusted")
    env = dict(BASE_ENV)
    cwd = "/"
    if not system:
        env["HOME"] = cwd = _home()
        if Path(argv[0]).name == "brew":
            env.update(
                HOMEBREW_NO_AUTO_UPDATE="1", HOMEBREW_NO_ANALYTICS="1", HOMEBREW_NO_ENV_HINTS="1"
            )
    return run_read(argv, timeout=timeout, merge_stderr=merge_stderr, env=env, cwd=cwd)


@dataclass
class Host:
    """Everything the plan reads from this machine, so tests can fake each edge."""

    name: str
    system: str
    os_release: bytes | None
    run: Callable[..., Out]
    find_owner_tool: Callable[[str], str | None]
    free_bytes: Callable[[str], int | None]
    mounts: tuple[str, ...] = ()
    lists_age_days: float | None = None
    reboot_required: bool | None = None
    nvm_present: bool = False

    @classmethod
    def local(cls) -> Host:
        system = platform.system()
        data = probe.read_file(Path("/etc/os-release"), prefix=Path("/etc"))
        if data.reason == "ambiguous_config":
            data = probe.read_file(Path("/usr/lib/os-release"), prefix=Path("/usr/lib"))
        linux = system == "Linux"
        return cls(
            name=probe.display_text(platform.node())[:100] or "unknown",
            system=system,
            os_release=data.data if linux and not data.reason else None,
            run=local_run,
            find_owner_tool=find_owner_tool,
            free_bytes=_free_bytes,
            mounts=tuple(m for m in ("/var", "/boot") if os.path.ismount(m)) if linux else (),
            lists_age_days=_lists_age_days() if linux else None,
            reboot_required=os.path.exists("/run/reboot-required") if linux else None,
            nvm_present=os.path.isdir(os.path.join(_home(), ".nvm")),
        )


def _free_bytes(path: str) -> int | None:
    try:
        info = os.statvfs(path)
    except OSError:
        return None
    return info.f_bavail * info.f_frsize


def _lists_age_days() -> float | None:
    for path in ("/var/lib/apt/periodic/update-success-stamp", "/var/lib/apt/lists"):
        try:
            return max(0.0, (time.time() - os.stat(path).st_mtime) / 86400)
        except OSError:
            continue
    return None


# --- parsers: a malformed answer is None, never an empty list -----------------


def _lines(data: bytes) -> list[str] | None:
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        return None
    if any(not (c.isprintable() or c in "\n\t") for c in text):
        return None
    lines = text.split("\n")
    return lines[:-1] if lines and lines[-1] == "" else lines


def _step(
    phase: str, source: str, name: str, old: str | None, new: str | None, what: str, reboot: str
) -> dict[str, Any]:
    return {
        "id": f"{phase}.{source}.{name}",
        "phase": phase,
        "source": source,
        "name": name,
        "from": old,
        "to": new,
        "what": what,
        "reboot": reboot,
        "run_as": "owner",
        "argv": None,
    }


def parse_apt(data: bytes) -> list[dict[str, Any]] | None:
    lines = _lines(data)
    if not lines or lines[0] not in ("Listing...", "Listing... Done"):
        return None
    steps = []
    for line in lines[1:]:
        match = _APT_LINE.match(line)
        if not match:
            return None
        name = match["name"]
        reboot = "likely" if name.startswith(REBOOT_PREFIXES) or name in REBOOT_NAMES else "unknown"
        steps.append(
            _step(
                "host",
                "apt",
                name,
                match["old"],
                match["new"],
                f"upgrade {name} {match['old']} -> {match['new']}",
                reboot,
            )
        )
    return steps


def parse_mise(data: bytes) -> list[dict[str, Any]] | None:
    try:
        value = json.loads(data)
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    steps = []
    for name, entry in value.items():
        if not (isinstance(name, str) and _TOOL.match(name) and isinstance(entry, dict)):
            return None
        current, latest = entry.get("current"), entry.get("latest")
        if not (
            isinstance(current, str)
            and isinstance(latest, str)
            and _VERSION.match(current)
            and _VERSION.match(latest)
        ):
            return None
        steps.append(
            _step(
                "tools",
                "mise",
                name,
                current,
                latest,
                f"upgrade {name} {current} -> {latest}",
                "no",
            )
        )
    return steps


def parse_brew(data: bytes) -> list[dict[str, Any]] | None:
    try:
        value = json.loads(data)
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    steps = []
    for kind in ("formulae", "casks"):
        entries = value.get(kind)
        if not isinstance(entries, list):
            return None
        for entry in entries:
            if not isinstance(entry, dict):
                return None
            name, new, old = (
                entry.get("name"),
                entry.get("current_version"),
                entry.get("installed_versions"),
            )
            olds = [old] if isinstance(old, str) else old
            if not (
                isinstance(name, str)
                and _TOOL.match(name)
                and isinstance(new, str)
                and _VERSION.match(new)
                and isinstance(olds, list)
                and all(isinstance(v, str) and _VERSION.match(v) for v in olds)
            ):
                return None
            first = olds[0] if olds else None
            steps.append(
                _step("host", "brew", name, first, new, f"upgrade {name} {first} -> {new}", "no")
            )
    return steps


def parse_softwareupdate(data: bytes) -> list[dict[str, Any]] | None:
    lines = _lines(data)
    if lines is None:
        return None
    labels = [i for i, line in enumerate(lines) if line.startswith("* Label: ")]
    if any("No new software available" in line for line in lines):
        return [] if not labels else None
    if not any("found the following" in line for line in lines) or not labels:
        return None
    steps = []
    for index in labels:
        label = lines[index][len("* Label: ") :].strip()
        title = _SWU_TITLE.match(lines[index + 1]) if index + 1 < len(lines) else None
        if not title or not 0 < len(label) <= 120:
            return None
        restart = "Action: restart" in title["rest"]
        steps.append(
            _step(
                "host",
                "softwareupdate",
                label,
                None,
                title["ver"].strip(),
                f"install {title['title'].strip()} {title['ver'].strip()}",
                "yes" if restart else "unknown",
            )
        )
    return steps


def parse_pro(data: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(data)
    except ValueError:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("attached"), bool):
        return None
    enabled: list[str] = []
    # An unattached machine lists services with `available` and no `status`.
    services = value.get("services", [])
    if not isinstance(services, list):
        return None
    for service in services:
        name = service.get("name") if isinstance(service, dict) else None
        status = service.get("status") if isinstance(service, dict) else None
        if not (
            isinstance(name, str)
            and re.fullmatch(r"[a-z0-9\-]{1,40}", name)
            and (status is None or isinstance(status, str))
        ):
            return None
        if status == "enabled":
            enabled.append(name)
    return {"attached": value["attached"], "enabled": sorted(enabled)}


# --- reads ----------------------------------------------------------------------


def _classify(out: Out, optional: bool) -> tuple[str, str] | None:
    """The state a read earned before its output is parsed, or None if it can be parsed."""
    if out.reason == "missing":
        return (
            ("not_present", "executable_missing") if optional else ("failed", "executable_missing")
        )
    if out.reason == "untrusted":
        return "not_verified", "untrusted_executable"
    if out.reason in {"timeout", "output_cap"}:
        return "incomplete", out.reason
    if out.reason:
        return "failed", "probe_error"
    if out.returncode != 0:
        if NETWORK.search(out.data + out.err):
            return "unreachable", "network"
        return "failed", "exit_nonzero"
    return None


def _read(
    host: Host,
    deadline: float,
    read_id: str,
    argv: tuple[str, ...],
    parse: Callable[[bytes], Any],
    *,
    timeout: float,
    optional: bool = False,
    merge_stderr: bool = False,
) -> tuple[dict[str, Any], Any]:
    record: dict[str, Any] = {
        "id": read_id,
        "source": Path(argv[0]).name,
        "state": "ok",
        "reason": None,
        "returncode": None,
        "facts": {},
    }
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        out = Out(reason="timeout")
    else:
        out = host.run(argv, timeout=min(timeout, remaining), merge_stderr=merge_stderr)
    record["returncode"] = out.returncode
    verdict = _classify(out, optional)
    if verdict:
        record["state"], record["reason"] = verdict
        return record, None
    parsed = parse(out.data)
    if parsed is None:
        record["state"], record["reason"] = "failed", "malformed_output"
    return record, parsed


def _absent(read_id: str, source: str) -> dict[str, Any]:
    return {
        "id": read_id,
        "source": source,
        "state": "not_present",
        "reason": "executable_missing",
        "returncode": None,
        "facts": {},
    }


def _os_release_id(data: bytes | None) -> dict[str, str] | None:
    if data is None:
        return None
    fields: dict[str, str] = {}
    try:
        for line in data.decode("utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                tokens = shlex.split(value, comments=False)
                if len(tokens) != 1 or key in fields:
                    return None
                fields[key] = tokens[0]
    except (UnicodeError, ValueError):
        return None
    return fields


def detect_os(host: Host) -> str:
    """ubuntu, macos, omarchy, arch or unknown. Detected on this machine, never configured."""
    if host.system == "Darwin":
        return "macos"
    if host.system != "Linux":
        return "unknown"
    fields = _os_release_id(host.os_release)
    if not fields:
        return "unknown"
    os_id = fields.get("ID")
    if os_id in {"ubuntu", "omarchy"}:
        return os_id
    if os_id == "arch" or "arch" in fields.get("ID_LIKE", "").split():
        return "arch"
    return "unknown"


def _disk(host: Host) -> dict[str, Any]:
    mounts = []
    for path in ("/", *host.mounts):
        free = host.free_bytes(path)
        floor = DISK_FLOORS.get(path, DISK_FLOORS["/"])
        state = "not_verified" if free is None else "warn" if free < floor else "ok"
        mounts.append({"path": path, "free_bytes": free, "min_free_bytes": floor, "state": state})
    states = {m["state"] for m in mounts}
    state = "not_verified" if "not_verified" in states else "warn" if "warn" in states else "ok"
    return {"state": state, "mounts": mounts}


def _phase(
    phase_id: str, reads: list[dict[str, Any]], steps: list[dict[str, Any]], notes: list[str]
) -> dict[str, Any]:
    state = max((r["state"] for r in reads), key=READ_RANK.__getitem__, default="ok")
    return {"id": phase_id, "state": state, "reads": reads, "steps": steps, "notes": notes}


UNGATED_MISE = (
    "omarchy update also runs its own mise up with no release-age wait, so tool versions "
    "move there outside this plan's tools phase."
)
PRO_NOTE = (
    "Ubuntu Pro: attaching is the owner's step. mb never attaches, and no token passes through mb."
)
AGENTS_NOTE = "Not available yet: updating the agents on this machine is a later stage."


def plan(host: Host) -> dict[str, Any]:
    deadline = time.monotonic() + OVERALL_SECONDS
    disk = _disk(host)  # first: a full disk is how partial upgrades happen
    os_id = detect_os(host)
    warnings: list[dict[str, Any]] = []
    for mount in disk["mounts"]:
        if mount["state"] == "warn":
            warnings.append(
                {
                    "code": "disk.low",
                    "path": mount["path"],
                    "message": f"Low disk space on {mount['path']}: a full disk is a known cause "
                    "of partial upgrades. Free space before the owner applies updates.",
                }
            )
    host_reads: list[dict[str, Any]] = [
        {
            "id": "os.detect",
            "source": "os-release",
            "state": "ok" if os_id not in {"arch", "unknown"} else "not_verified",
            "reason": None
            if os_id not in {"arch", "unknown"}
            else ("no_safe_read" if os_id == "arch" else "os_unknown"),
            "returncode": None,
            "facts": {"id": os_id},
        }
    ]
    host_steps: list[dict[str, Any]] = []
    host_notes: list[str] = []
    tools_reads: list[dict[str, Any]] = []
    tools_steps: list[dict[str, Any]] = []
    tools_notes: list[str] = []
    known = os_id in {"ubuntu", "macos", "omarchy"}

    if os_id == "ubuntu":
        record, steps = _read(host, deadline, "apt.upgradable", APT, parse_apt, timeout=30)
        record["facts"]["lists_age_days"] = (
            None if host.lists_age_days is None else round(host.lists_age_days, 1)
        )
        if host.lists_age_days is None:
            warnings.append(
                {
                    "code": "apt.lists_age_unknown",
                    "message": "The age of the apt package lists is unknown.",
                }
            )
        elif host.lists_age_days > LISTS_STALE_DAYS:
            warnings.append(
                {
                    "code": "apt.lists_stale",
                    "message": f"The apt package lists are {host.lists_age_days:.0f} days old, so "
                    "newer updates may be missing from this plan. The owner refreshes them.",
                }
            )
        host_reads.append(record)
        host_steps += steps or []
        record, facts = _read(
            host, deadline, "pro.status", PRO, parse_pro, timeout=20, optional=True
        )
        if facts is not None:
            record["facts"] = facts
        host_reads.append(record)
        host_notes.append(PRO_NOTE)
    elif os_id == "macos":
        record, steps = _read(
            host,
            deadline,
            "softwareupdate.list",
            SOFTWAREUPDATE,
            parse_softwareupdate,
            timeout=120,
            merge_stderr=True,
        )
        host_reads.append(record)
        host_steps += steps or []
        brew = host.find_owner_tool("brew")
        if brew:
            record, steps = _read(
                host,
                deadline,
                "brew.outdated",
                (brew, "outdated", "--json=v2"),
                parse_brew,
                timeout=60,
                optional=True,
            )
            record["facts"]["index"] = "local only; brew was not asked to update itself"
            host_reads.append(record)
            host_steps += steps or []
    elif os_id == "omarchy":
        host_reads.append(
            {
                "id": "omarchy.pending",
                "source": "omarchy",
                "state": "not_verified",
                "reason": "no_safe_read",
                "returncode": None,
                "facts": {},
            }
        )
        host_steps.append(
            _step(
                "host",
                "omarchy",
                "omarchy update",
                None,
                None,
                "The owner runs `omarchy update`, Omarchy's supported full update. "
                "mb runs no package manager here, and the pending list is not read.",
                "unknown",
            )
        )
        host_notes.append(UNGATED_MISE)
        tools_notes.append(UNGATED_MISE)
    elif os_id == "arch":
        host_notes.append("Plain Arch: no safe read of pending updates is built. NOT VERIFIED.")
    else:
        host_notes.append(
            "This operating system is not recognised. NOT VERIFIED; nothing was read."
        )

    if known:
        mise = host.find_owner_tool("mise")
        if mise:
            record, steps = _read(
                host,
                deadline,
                "mise.outdated",
                (mise, "outdated", "--json"),
                parse_mise,
                timeout=60,
                optional=True,
            )
            tools_reads.append(record)
            tools_steps += steps or []
            if host.nvm_present:
                tools_notes.append(
                    "nvm is installed beside mise: two updaters for Node. Pick one per layer."
                )
        else:
            tools_reads.append(_absent("mise.outdated", "mise"))
            tools_notes.append("mise was not found, so tools are not planned.")
    else:
        tools_notes.append("Not checked: the operating system is not verified.")

    phases = [
        _phase("host", host_reads, host_steps, host_notes),
        _phase("tools", tools_reads, tools_steps, tools_notes),
        {
            "id": "agents",
            "state": "not_available",
            "reads": [],
            "steps": [],
            "notes": [AGENTS_NOTE],
        },
    ]
    if not known:
        phases[1]["state"] = "not_verified"
    states = [r["state"] for p in phases for r in p["reads"]]
    if disk["state"] == "not_verified":
        states.append("not_verified")
    if "failed" in states:
        code = 1
    elif any(s in {"incomplete", "unreachable", "not_verified"} for s in states):
        code = 3
    else:
        code = 0
    counts: dict[str, int] = {}
    for state in states:
        counts[state] = counts.get(state, 0) + 1
    return {
        "schema": "mb.machine.update",
        "schema_version": 1,
        "mode": "plan",
        "safe_to_share": False,
        "ok": code == 0,
        "exit_code": code,
        "machine": {"name": host.name},
        "os": {"id": os_id},
        "reboot_pending": host.reboot_required,
        "disk": disk,
        "phases": phases,
        "summary": {
            "steps": sum(len(p["steps"]) for p in phases),
            "reads": counts,
        },
        "warnings": warnings,
        "errors": [],
    }


def human_report(report: dict[str, Any]) -> str:
    lines = [
        f"Machine update: {report['machine']['name']} ({report['os']['id']}). "
        "Plan only; nothing was changed."
    ]
    if report["reboot_pending"]:
        lines.append("A reboot is already pending on this machine.")
    for mount in report["disk"]["mounts"]:
        free = mount["free_bytes"]
        shown = "NOT VERIFIED" if free is None else f"{free / GIB:.1f} GiB free"
        lines.append(f"Disk {mount['path']}: {shown} ({mount['state']})")
    lines += [f"Warning: {w['message']}" for w in report["warnings"]]
    for phase in report["phases"]:
        lines.append(f"{phase['id'].capitalize()}: {phase['state'].replace('_', ' ')}")
        for item in phase["reads"]:
            label = "NOT VERIFIED" if item["state"] == "not_verified" else item["state"]
            why = f" ({item['reason']})" if item["reason"] else ""
            lines.append(f"  {item['id']}: {label}{why}")
        for step in phase["steps"][:25]:
            lines.append(f"  - [{step['source']}] {step['what']} (reboot: {step['reboot']})")
        if len(phase["steps"]) > 25:
            lines.append(f"  ... and {len(phase['steps']) - 25} more; see --json")
        lines += [f"  Note: {note}" for note in phase["notes"]]
    lines.append("The owner-run apply is not built yet. This command never changes the machine.")
    return "\n".join(lines)
