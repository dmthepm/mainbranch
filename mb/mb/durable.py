"""Small crash-safety helpers for Main Branch state files."""

from __future__ import annotations

import errno
import json
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any


class CorruptStateError(ValueError):
    """Raised when a state file exists but cannot be safely parsed."""

    def __init__(self, path: Path, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"{path} is not valid state: {detail}")


def read_json_object(
    path: Path, *, default: dict[str, Any] | None = None, strict: bool = False
) -> dict[str, Any]:
    """Read a JSON object, distinguishing missing from corrupt state.

    An empty file reads as the default unless ``strict``, where it is corrupt:
    a state file that was written but came back empty is a lost write.
    """
    if not path.exists():
        return {} if default is None else dict(default)
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        if strict:
            raise CorruptStateError(path, "file is empty")
        return {} if default is None else dict(default)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CorruptStateError(path, exc.msg) from exc
    if not isinstance(data, dict):
        raise CorruptStateError(path, "expected a JSON object")
    return data


class UnconfirmedWriteError(OSError):
    """The new content replaced the file, but a directory sync after it failed."""


def _open_directory(directory: Path) -> int | None:
    """Open a directory for syncing; None on Windows, which cannot."""
    return None if os.name == "nt" else os.open(directory, os.O_RDONLY)


# A directory fsync these errnos answer means "this disk cannot do that", not
# "the data may be lost": some network and FUSE filesystems refuse it outright.
_UNSUPPORTED_DIRECTORY_SYNC = frozenset(
    {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EBADF}
)


def _fsync_fd(fd: int | None) -> None:
    """Sync a directory descriptor; a disk that cannot do it is carried on past."""
    if fd is None:
        return
    try:
        os.fsync(fd)
    except OSError as exc:
        if exc.errno not in _UNSUPPORTED_DIRECTORY_SYNC:
            raise


def _close(fd: int | None) -> None:
    if fd is not None:
        os.close(fd)


def _sync_directory(directory: Path) -> None:
    fd = _open_directory(directory)
    try:
        _fsync_fd(fd)
    finally:
        _close(fd)


def _make_parents(parent: Path) -> None:
    """Create missing directories one level at a time, each synced through its own parent.

    A failure removes the directories this call created, so a retry starts from
    the same state and syncs every level again. Cleanup is best effort: it
    removes only empty directories, and a concurrent swap by the same user can
    lose an empty directory.
    """
    missing = [parent, *parent.parents]
    missing = missing[: next((i for i, d in enumerate(missing) if d.exists()), len(missing))]
    made: list[Path] = []
    try:
        for directory in reversed(missing):
            try:
                directory.mkdir()
                made.append(directory)
            except FileExistsError:
                pass  # another process made it: it exists, and is not ours to remove
            _sync_directory(directory.parent)
    except BaseException:
        for directory in reversed(made):
            with suppress(OSError):
                directory.rmdir()
        raise


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError(errno.EIO, "write made no progress")
        view = view[written:]


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    mode: int | None = None,
    newline: str | None = None,
) -> None:
    """Replace a file from a same-directory temp file with its final mode already set.

    A filesystem that refuses a directory sync (EINVAL, ENOTSUP, EBADF) is
    carried on past; any other sync error, EIO included, still counts.

    Durability: on return the file's contents, its name, and any parent
    directories this call had to create are all synced, each through its own
    parent. Everything that can fail is done before the replace, including
    opening the parent directory, so an error before it leaves the old file in
    place. Only the final directory sync runs after the replace; if it fails,
    ``UnconfirmedWriteError`` is raised: the new content is already visible but
    is not guaranteed to survive a crash. Callers must say so, not "nothing
    was written", and a retry rewrites and syncs it.
    """
    # Encode first so no encoding failure sits between mkstemp and owning the descriptor.
    # Newlines follow text mode: None translates to os.linesep, "" keeps as is,
    # and anything else text mode rejected is still rejected.
    if newline not in (None, "", "\n", "\r", "\r\n"):
        raise ValueError(f"illegal newline value: {newline!r}")
    eol = os.linesep if newline is None else (newline or "\n")
    data = text.replace("\n", eol).encode(encoding)
    _make_parents(path.parent)
    if mode is None:
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    dir_fd = _open_directory(path.parent)
    tmp: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        tmp = Path(tmp_name)
        try:
            _write_all(fd, data)
            os.fsync(fd)
        except BaseException:
            with suppress(OSError):  # a close error never replaces the pending one
                os.close(fd)
            raise
        os.close(fd)  # the one close: this function owns fd from mkstemp on
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        _close(dir_fd)
        if tmp is not None:
            with suppress(OSError):
                tmp.unlink()
        raise
    try:
        _fsync_fd(dir_fd)
    except OSError as exc:
        raise UnconfirmedWriteError(exc.errno, exc.strerror or str(exc)) from exc
    finally:
        _close(dir_fd)


def atomic_write_json(
    path: Path,
    data: Any,
    *,
    indent: int = 2,
    sort_keys: bool = False,
) -> None:
    atomic_write_text(path, json.dumps(data, indent=indent, sort_keys=sort_keys) + "\n")


@contextmanager
def state_lock(path: Path, *, timeout: float = 10.0) -> Iterator[None]:
    """Best-effort interprocess lock using an atomic lock directory."""
    lock_dir = path.with_name(f".{path.name}.lock")
    deadline = time.monotonic() + timeout
    while True:
        try:
            lock_dir.mkdir()
            break
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for lock {lock_dir}") from exc
            time.sleep(0.05)
    try:
        yield
    finally:
        with suppress(OSError):
            lock_dir.rmdir()
