"""Small crash-safety helpers for Main Branch state files."""

from __future__ import annotations

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


def _fsync_fd(fd: int | None) -> None:
    if fd is not None:
        os.fsync(fd)


def _close(fd: int | None) -> None:
    if fd is not None:
        os.close(fd)


def _make_parents(parent: Path) -> None:
    """Create missing directories one level at a time, each synced through its own parent.

    A failure removes what this call created, so a retry starts from the same
    state and syncs every level again.
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
            fd = _open_directory(directory.parent)
            try:
                _fsync_fd(fd)
            finally:
                _close(fd)
    except BaseException:
        for directory in reversed(made):
            with suppress(OSError):
                directory.rmdir()
        raise


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    mode: int | None = None,
    newline: str | None = None,
) -> None:
    """Replace a file from a same-directory temp file with its final mode already set.

    Durability: on return the file's contents, its name, and any parent
    directories this call had to create are all synced, each through its own
    parent. Everything that can fail is done before the replace, including
    opening the parent directory, so an error before it leaves the old file in
    place. Only the final directory sync runs after the replace; if it fails,
    ``UnconfirmedWriteError`` is raised: the new content is already visible but
    is not guaranteed to survive a crash. Callers must say so, not "nothing
    was written", and a retry rewrites and syncs it.
    """
    _make_parents(path.parent)
    if mode is None:
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    dir_fd = _open_directory(path.parent)
    tmp: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        tmp = Path(tmp_name)
        with os.fdopen(fd, "w", encoding=encoding, newline=newline) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
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
