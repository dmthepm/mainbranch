"""One mb process at a time saves a credential.

A connect snapshots the stored value, stores the new one, records it, and
rolls back if the record fails. Two of those on one credential can undo each
other. ``credential_lock`` holds an exclusive ``flock`` from the snapshot to the
end of the rollback, so no other mb process writes that credential in between.

The lock file lives under the Main Branch state directory and is named from a
hash of the reference, so neither the reference nor a secret appears in a path.
Lock files are never deleted: two processes must always lock the same inode.
"""

from __future__ import annotations

import errno
import hashlib
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # no flock on this platform: refuse rather than save unlocked
    fcntl = None  # type: ignore[assignment]

LOCK_DIR_NAME = "locks"
# How long a second connect waits for the first before refusing. Tests shrink it.
LOCK_WAIT_SECONDS = 5.0
_POLL_SECONDS = 0.05

BUSY_STATE = "credential_busy"
UNAVAILABLE_STATE = "credential_lock_unavailable"

# Lock files this process holds: path -> (file descriptor, nesting depth). A
# nested connect in the same process re-enters instead of deadlocking.
_held: dict[str, list[int]] = {}
# The last value this process stored per (backend, ref), as a digest. A
# rollback only touches an item whose last writer is the transaction rolling back.
_last_stored: dict[tuple[str, str], str] = {}


class CredentialBusyError(RuntimeError):
    """Another mb process holds the credential, or the lock cannot be taken.

    Raised before anything is written. ``state`` is the stable JSON state.
    """

    def __init__(self, message: str, state: str = BUSY_STATE) -> None:
        super().__init__(message)
        self.state = state


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def note_stored(backend: str, ref: str, value: str) -> None:
    """Record, before a store, that this process is about to write ``value``."""

    _last_stored[(backend, ref)] = _digest(value)


def still_ours(backend: str, ref: str, value: str) -> bool:
    """True when no later store in this process replaced what ``value`` wrote."""

    return _last_stored.get((backend, ref)) == _digest(value)


def forget_stored(backend: str, ref: str) -> None:
    _last_stored.pop((backend, ref), None)


def _shown(path: Path) -> str:
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return path.name


def _unavailable(directory: Path, provider_name: str) -> CredentialBusyError:
    return CredentialBusyError(
        f"Main Branch could not take its credential lock in {_shown(directory)}, so the "
        f"{provider_name} credential was not saved. Nothing was stored. Make that folder "
        "writable, then rerun the command.",
        UNAVAILABLE_STATE,
    )


def _no_file_locking(provider_name: str) -> CredentialBusyError:
    return CredentialBusyError(
        f"This platform has no file locking, so the {provider_name} credential was not saved. "
        "Nothing was stored. Use WSL2 on Windows, then rerun the command.",
        UNAVAILABLE_STATE,
    )


def _cannot_lock(directory: Path, provider_name: str, code: int) -> CredentialBusyError:
    name = errno.errorcode.get(code, f"error {code}")
    return CredentialBusyError(
        f"Main Branch could not lock a file in {_shown(directory)} ({name}), so the "
        f"{provider_name} credential was not saved. Nothing was stored. That folder may be on a "
        "file system without file locking, such as a network home folder. Main Branch needs "
        "file locking there to save a credential safely.",
        UNAVAILABLE_STATE,
    )


def _busy(provider_name: str) -> CredentialBusyError:
    return CredentialBusyError(
        f"Another mb connect is saving the {provider_name} credential right now. "
        "Nothing was stored. Try again in a moment."
    )


@contextmanager
def credential_lock(home: Path, refs: list[str], provider_name: str) -> Iterator[None]:
    """Hold the exclusive lock for every ref until the block ends.

    Refs are locked in sorted order so two multi-slot connects cannot deadlock.
    Raises ``CredentialBusyError`` before the block runs if another process keeps
    the lock past ``LOCK_WAIT_SECONDS`` (``credential_busy``), or at once if the
    lock file cannot be opened or the file system cannot lock it
    (``credential_lock_unavailable``). Only EWOULDBLOCK/EAGAIN mean "held": macOS
    and Linux ``flock(2)`` document no EACCES (that comes from ``fcntl`` locks).
    """

    directory = home / LOCK_DIR_NAME
    if fcntl is None:
        raise _no_file_locking(provider_name)
    taken: list[str] = []
    try:
        for ref in sorted(set(refs)):
            path = directory / (hashlib.sha256(ref.encode()).hexdigest()[:32] + ".lock")
            key = str(path)
            if key in _held:
                _held[key][1] += 1
                taken.append(key)
                continue
            try:
                directory.mkdir(mode=0o700, parents=True, exist_ok=True)
                fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0), 0o600)
            except OSError:
                raise _unavailable(directory, provider_name) from None
            deadline = time.monotonic() + LOCK_WAIT_SECONDS
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                        # Not a held lock (no lock support, bad descriptor): waiting
                        # cannot help, and "another connect" would be untrue.
                        os.close(fd)
                        raise _cannot_lock(directory, provider_name, exc.errno or 0) from None
                    if time.monotonic() >= deadline:
                        os.close(fd)
                        raise _busy(provider_name) from None
                    time.sleep(_POLL_SECONDS)
            _held[key] = [fd, 1]
            taken.append(key)
        yield
    finally:
        for key in reversed(taken):
            entry = _held[key]
            entry[1] -= 1
            if entry[1] == 0:
                del _held[key]
                try:
                    fcntl.flock(entry[0], fcntl.LOCK_UN)
                finally:
                    os.close(entry[0])
