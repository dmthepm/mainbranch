"""Read-only probe boundaries. Raw data stays internal to check parsers."""

from __future__ import annotations

import os
import re
import selectors
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ProbeReason = Literal[
    "untrusted_executable", "ambiguous_config", "probe_missing", "probe_timeout", "probe_error"
]
Platform = Literal["ubuntu", "omarchy", "macos"]

# Check code supplies argv; policy data must never select an executable.
EXECUTABLES: dict[Platform, frozenset[str]] = {
    "ubuntu": frozenset(
        {
            "/usr/bin/systemctl",
            "/usr/bin/lsblk",
            "/usr/bin/tailscale",
            "/usr/bin/gsettings",
            "/usr/bin/dpkg-query",
            "/usr/bin/apt-config",
        }
    ),
    "omarchy": frozenset(
        {"/usr/bin/systemctl", "/usr/bin/lsblk", "/usr/bin/tailscale", "/usr/bin/pacman"}
    ),
    "macos": frozenset(
        {"/usr/bin/pmset", "/usr/bin/fdesetup", "/usr/bin/sw_vers", "/usr/bin/defaults"}
    ),
}
DEFAULT_BYTE_CAP = 256 * 1024


@dataclass(frozen=True)
class ProbeResult:
    """A parser input, never a doctor observed field or terminal message."""

    data: bytes = b""
    returncode: int | None = None
    reason: ProbeReason | None = None


def _trusted_executable(path: Path) -> bool:
    try:
        real = path.resolve(strict=True)
        if not stat.S_ISREG(real.lstat().st_mode) or not os.access(real, os.X_OK):
            return False
        # Inspect both the alias parents and resolved parents before execution.
        for candidate in (real, *real.parents, *path.parents):
            info = candidate.lstat()
            if info.st_uid != 0 or info.st_mode & 0o022:
                return False
        return True
    except OSError:
        return False


def run_probe(
    platform: Platform,
    argv: tuple[str, ...],
    *,
    deadline: float,
    byte_cap: int = DEFAULT_BYTE_CAP,
) -> ProbeResult:
    """Run a registry argv under a caller-owned monotonic overall deadline.

    Each invocation also has a five-second limit. Output above the cap is
    discarded, as is stderr. Callers parse only the named fields they need.
    """
    if not argv or argv[0] not in EXECUTABLES[platform]:
        return ProbeResult(reason="untrusted_executable")
    if not _trusted_executable(Path(argv[0])):
        return ProbeResult(reason="untrusted_executable")
    if byte_cap < 1:
        raise ValueError("byte_cap must be positive")
    end = min(deadline, time.monotonic() + 5)
    if end <= time.monotonic():
        return ProbeResult(reason="probe_timeout")
    env = {"LC_ALL": "C", "PATH": "/usr/bin:/bin"}
    if argv[0] == "/usr/bin/systemctl" and "--user" in argv[1:]:
        # Derive this from the running uid, never from inherited environment.
        env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
    try:
        with subprocess.Popen(
            argv,
            shell=False,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        ) as process:
            assert process.stdout is not None
            output = bytearray()
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while selector.get_map():
                        remaining = end - time.monotonic()
                        if remaining <= 0 or not selector.select(remaining):
                            return ProbeResult(reason="probe_timeout")
                        chunk = os.read(
                            process.stdout.fileno(), min(65536, byte_cap + 1 - len(output))
                        )
                        if not chunk:
                            selector.unregister(process.stdout)
                        else:
                            output.extend(chunk)
                            if len(output) > byte_cap:
                                return ProbeResult(reason="probe_error")
                    try:
                        code = process.wait(timeout=max(0, end - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        return ProbeResult(reason="probe_timeout")
                    return ProbeResult(bytes(output), code)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
    except FileNotFoundError:
        return ProbeResult(reason="probe_missing")
    except OSError:
        return ProbeResult(reason="probe_error")


def read_file(path: Path, *, prefix: Path, byte_cap: int = DEFAULT_BYTE_CAP) -> ProbeResult:
    """Read a regular file below a registry prefix without following symlinks.

    Walk from the root using directory descriptors so swapped parent paths
    cannot redirect the open. Nonblocking open also prevents a FIFO race.
    """
    if byte_cap < 1:
        raise ValueError("byte_cap must be positive")
    if not path.is_absolute() or not prefix.is_absolute() or ".." in path.parts:
        return ProbeResult(reason="ambiguous_config")
    descriptor: int | None = None
    try:
        path.resolve(strict=True).relative_to(prefix.resolve(strict=True))
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        for component in path.parts[1:-1]:
            info = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode):
                return ProbeResult(reason="ambiguous_config")
            child = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        name = path.name
        info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            return ProbeResult(reason="ambiguous_config")
        file_descriptor = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor
        )
        with os.fdopen(file_descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return ProbeResult(reason="ambiguous_config")
            data = stream.read(byte_cap + 1)
            if len(data) > byte_cap:
                return ProbeResult(reason="probe_error")
            return ProbeResult(data=data)
    except FileNotFoundError:
        return ProbeResult(reason="probe_missing")
    except ValueError:
        return ProbeResult(reason="ambiguous_config")
    except OSError:
        return ProbeResult(reason="probe_error")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def display_text(value: str) -> str:
    """Return at most 200 printable characters, inert even in Rich markup."""
    value = re.sub(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))", "", value)
    return "".join(character for character in value if character.isprintable()).replace("[", r"\[")[
        :200
    ]
