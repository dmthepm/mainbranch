"""The agent launcher's private store: state.json, attempts, locks, and who may touch them.

Everything here is written through the slice 0 helpers (file fsync, rename, directory fsync).
Directories are created 0700 and files 0600 by explicit mode. Every use first checks, by
``lstat``, that the thing is the caller's, has no group or other bits and carries no POSIX ACL;
otherwise the launcher refuses ``unsafe-store`` and does not chmod. The same uid can still read
and edit all of it: that is a stated limit, not a defence.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mb import durable

ATTEMPT_ID_RE = re.compile(r"^[a-z0-9-]{1,40}\.[0-9]{8}T[0-9]{6}Z\.[0-9a-f]{8}$")
PROVENANCE = ("spawned", "owner-confirmed", "discovered")
STATE_ROW_KEYS = ("session_id", "session_provenance", "row_rev", "last_attempt")
ACL_ATTRS = ("system.posix_acl_access", "system.posix_acl_default")
STORE_LOCK_WAIT = 10.0


class Refusal(Exception):
    """A stop with a documented exit code and tag."""

    def __init__(self, exit_code: int, tag: str, detail: str) -> None:
        self.exit_code, self.tag, self.detail = exit_code, tag, detail
        super().__init__(f"{tag}: {detail}")


def _has_acl(path: Path) -> bool:
    try:
        return any(a in ACL_ATTRS for a in os.listxattr(path, follow_symlinks=False))
    except OSError:
        return False  # no extended attributes on this filesystem, so no ACL


def audit(path: Path, uid: int, *, directory: bool) -> bool:
    """True when ``path`` exists and passes; False when missing; ``unsafe-store`` when it fails."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise Refusal(2, "unsafe-store", f"{path}: {exc.strerror}") from None
    kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not kind:
        why = "not a directory" if directory else "not a regular file"
    elif info.st_uid != uid:
        why = "owned by someone else"
    elif info.st_mode & 0o077:
        why = f"mode {info.st_mode & 0o777:04o} gives group or other access"
    elif _has_acl(path):
        why = "has a POSIX ACL"
    else:
        return True
    raise Refusal(2, "unsafe-store", f"{path}: {why}")


def read_object(path: Path, uid: int) -> dict[str, Any] | None:
    """A private JSON object, None when missing. Empty or unparsable is ``corrupt-state``."""
    if not audit(path, uid, directory=False):
        return None
    try:
        return durable.read_json_object(path, strict=True)
    except (durable.CorruptStateError, OSError, UnicodeDecodeError) as exc:
        raise Refusal(4, "corrupt-state", f"{path}: {exc}") from None


def write_private(path: Path, record: dict[str, Any]) -> None:
    durable.atomic_write_text(path, json.dumps(record, indent=2, sort_keys=True) + "\n", mode=0o600)


class FileLock:
    """An flock on a store file. The descriptor is close-on-exec and never handed to a child."""

    def __init__(self, path: Path, uid: int) -> None:
        self.path = path
        flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            self.fd: int | None = os.open(path, flags, 0o600)
        except OSError as exc:
            raise Refusal(2, "unsafe-store", f"{path}: {exc.strerror}") from None
        info = os.fstat(self.fd)
        if info.st_uid != uid or info.st_mode & 0o077 or not stat.S_ISREG(info.st_mode):
            self.close()
            raise Refusal(2, "unsafe-store", f"{path}: not a private regular file")
        self.inode = info.st_ino

    def try_lock(self) -> bool:
        assert self.fd is not None
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True

    def lock(self, wait: float) -> None:
        deadline = time.monotonic() + wait
        while not self.try_lock():
            if time.monotonic() >= deadline:
                raise Refusal(4, "store-lock-timeout", f"{self.path.name} stayed held; try again")
            time.sleep(0.02)

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)  # closing the descriptor releases the flock
            self.fd = None


@dataclass(frozen=True)
class Store:
    root: Path
    uid: int

    @property
    def attempts(self) -> Path:
        return self.root / "attempts"

    @property
    def locks(self) -> Path:
        return self.root / "locks"

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    def prepare(self, *, create: bool) -> None:
        """Audit the store directory tree; with ``create``, make the missing parts 0700."""
        if not audit(self.root, self.uid, directory=True):
            raise Refusal(2, "unsafe-store", f"{self.root}: missing")
        for sub in (self.attempts, self.locks):
            if audit(sub, self.uid, directory=True) or not create:
                continue
            os.mkdir(sub, 0o700)
            durable._sync_directory(self.root)
            audit(sub, self.uid, directory=True)

    def store_lock(self) -> FileLock:
        lock = FileLock(self.root / ".store.lock", self.uid)
        lock.lock(STORE_LOCK_WAIT)
        return lock

    def row_lock(self, name: str) -> FileLock:
        return FileLock(self.locks / f"{name}.lock", self.uid)

    def read_state(self) -> dict[str, dict[str, Any]]:
        """Per-row state. A missing file is no state; anything malformed is ``corrupt-state``."""
        data = read_object(self.state_path, self.uid)
        if data is None:
            return {}
        rows = data.get("rows")
        if data.get("version") != 1 or not isinstance(rows, dict):
            raise Refusal(4, "corrupt-state", "state.json has the wrong shape")
        for name, row in rows.items():
            ok = (
                isinstance(row, dict)
                and set(row) == set(STATE_ROW_KEYS)
                and (row["session_id"] is None or isinstance(row["session_id"], str))
                and row["session_provenance"] in PROVENANCE
                and isinstance(row["row_rev"], str)
                and isinstance(row["last_attempt"], str)
                and ATTEMPT_ID_RE.fullmatch(row["last_attempt"]) is not None
            )
            if not ok:
                raise Refusal(4, "corrupt-state", f"state.json row {name!r} is malformed")
        return rows

    def write_state(self, rows: dict[str, dict[str, Any]]) -> None:
        write_private(self.state_path, {"version": 1, "rows": rows})

    def attempt_path(self, attempt_id: str) -> Path:
        if not ATTEMPT_ID_RE.fullmatch(attempt_id):
            raise Refusal(4, "corrupt-state", "malformed attempt id")
        return self.attempts / f"{attempt_id}.json"

    def read_attempt(self, attempt_id: str) -> dict[str, Any]:
        record = read_object(self.attempt_path(attempt_id), self.uid)
        if record is None:
            raise Refusal(4, "corrupt-state", f"attempt {attempt_id} is missing")
        return record

    def write_attempt(self, record: dict[str, Any]) -> None:
        """Attempts are created once. An existing id is refused rather than replaced."""
        path = self.attempt_path(record["id"])
        if os.path.lexists(path):
            raise OSError(f"attempt {record['id']} already exists")
        write_private(path, record)

    def write_exit(self, attempt_id: str, record: dict[str, Any]) -> None:
        """Best effort, and never promised after a crash."""
        with contextlib.suppress(OSError):
            write_private(self.attempts / f"{attempt_id}.exit.json", record)
