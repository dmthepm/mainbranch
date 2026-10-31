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


def _unavailable(directory: Path, saved: str) -> CredentialBusyError:
    return CredentialBusyError(
        f"Main Branch could not take its credential lock in {_shown(directory)}, so {saved} "
        "was not saved. Nothing was stored. Make that folder "
        "writable, then rerun the command.",
        UNAVAILABLE_STATE,
    )


def _no_file_locking(saved: str) -> CredentialBusyError:
    return CredentialBusyError(
        f"This platform has no file locking, so {saved} was not saved. "
        "Nothing was stored. Use WSL2 on Windows, then rerun the command.",
        UNAVAILABLE_STATE,
    )


def _cannot_lock(directory: Path, saved: str, code: int) -> CredentialBusyError:
    name = errno.errorcode.get(code, f"error {code}")
    return CredentialBusyError(
        f"Main Branch could not lock a file in {_shown(directory)} ({name}), so {saved} "
        "was not saved. Nothing was stored. That folder may be on a "
        "file system without file locking, such as a network home folder. Main Branch needs "
        "file locking there to save a credential safely.",
        UNAVAILABLE_STATE,
    )


def _busy(saving: str) -> CredentialBusyError:
    return CredentialBusyError(
        f"Another mb connect is saving {saving} right now. Nothing was stored. "
        "Try again in a moment."
    )


@contextmanager
def _hold(
    directory: Path, names: list[str], saved: str, saving: str, *, lock_directory: bool = False
) -> Iterator[None]:
    """Hold an exclusive ``flock`` on each named file in ``directory``, in the order given.

    With ``lock_directory`` the lock is on ``directory`` itself (opened read-only, so
    no file is created) and ``names`` is ignored.
    """

    if fcntl is None:
        raise _no_file_locking(saved)
    items = [directory] if lock_directory else [directory / name for name in names]
    taken: list[str] = []
    try:
        for path in items:
            # Resolved, so two spellings of one folder share one entry and one inode.
            key = os.path.realpath(path) if lock_directory else str(path)
            if key in _held:
                _held[key][1] += 1
                taken.append(key)
                continue
            try:
                if lock_directory:
                    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                    fd = os.open(path, flags | getattr(os, "O_CLOEXEC", 0))
                else:
                    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
                    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
                    fd = os.open(path, flags, 0o600)
            except OSError:
                raise _unavailable(directory, saved) from None
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
                        raise _cannot_lock(directory, saved, exc.errno or 0) from None
                    if time.monotonic() >= deadline:
                        os.close(fd)
                        raise _busy(saving) from None
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


def _name(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32] + ".lock"


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

    with _hold(
        home / LOCK_DIR_NAME,
        [_name(ref) for ref in sorted(set(refs))],
        f"the {provider_name} credential",
        f"the {provider_name} credential",
    ):
        yield


TRANSACTION_LOCK_NAME = "save-transaction.lock"
LOCAL_STORE_LOCK_NAME = "local-secrets.lock"


@contextmanager
def save_transaction(
    home: Path, config_dir: Path | None = None, *, create: bool = True
) -> Iterator[None]:
    """Hold the save-transaction lock: one mb save at a time per Main Branch home.

    Take it before reading any config a save will rewrite, and keep it through
    the write and any rollback, so a second save re-reads what the first wrote
    instead of replacing it. With ``config_dir`` (the folder holding the repo
    config) it also locks that folder itself, second, for a repo shared by several
    homes. The folder is locked, not a file in it, so nothing is created or left
    behind in the repo, and every path to it meets at one inode. ``create`` makes
    the folder first, as a save would; without it a missing folder is not locked.
    Order everywhere: home, repo config folder, then ``credential_lock`` refs, then
    the local secret file. Never hold it across a network sign-in.
    """

    with _hold(home / LOCK_DIR_NAME, [TRANSACTION_LOCK_NAME], "the connection", "a connection"):
        if config_dir is None or not (create or config_dir.is_dir()):
            yield
            return
        if create:
            try:
                config_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                raise _unavailable(config_dir, "the connection") from None
        with _hold(config_dir, [], "the connection", "a connection", lock_directory=True):
            yield


@contextmanager
def local_store_lock(home: Path) -> Iterator[None]:
    """Hold the lock that serializes read-modify-write of the local secret file."""

    with _hold(home / LOCK_DIR_NAME, [LOCAL_STORE_LOCK_NAME], "the credential", "a credential"):
        yield
