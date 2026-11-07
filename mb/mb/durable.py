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


def _fsync_directory(directory: Path) -> None:
    """Persist a directory's entries. Errors surface; only Windows, which cannot open one, skips."""
    if os.name == "nt":
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


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
    parent, up to the first directory that already existed. An OSError from any
    sync propagates. After such an error the new content may already be
    visible but is not guaranteed to survive a crash, so treat the write as
    failed and retry it.
    """
    created: list[Path] = []
    ancestor = path.parent
    while not ancestor.exists():
        created.append(ancestor)
        ancestor = ancestor.parent
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline=newline) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        _fsync_directory(path.parent)
        for directory in created:
            _fsync_directory(directory.parent)
    except BaseException:
        with suppress(OSError):
            tmp.unlink()
        raise


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
