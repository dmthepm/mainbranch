"""Reading a media source. The only module that opens source bytes.

Everything here is read-only: directories and files are opened without write
flags, without following symlinks, relative to an already-open directory, and
only after the running user is shown unable to write them. Nothing under a
source is created, renamed, locked or deleted.
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

RECENT_NS = 60 * 1_000_000_000
_CHUNK = 1 << 20
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK


@dataclass(frozen=True)
class Found:
    rel: str
    size: int
    mtime_ns: int
    sha256: str


@dataclass(frozen=True)
class Skipped:
    rel: str
    reason: str


def root_problem(root: Path) -> str | None:
    """Why this folder cannot be a source, or None. A writable root is never allowed."""
    try:
        info = os.lstat(root)
    except OSError:
        return "not a directory (missing or unreadable)"
    if not stat.S_ISDIR(info.st_mode):
        return "not a directory"
    if os.access(root, os.W_OK):
        return "writable"
    if not os.access(root, os.R_OK | os.X_OK):
        return "unreadable"
    return None


def scan_source(
    root: Path,
    known: Mapping[str, tuple[int, int, str]],
    *,
    now_ns: int,
    reverify: bool = False,
) -> Iterator[Found | Skipped]:
    """Yield one Found or Skipped for every file under root.

    `known` maps a relative path to (size, mtime_ns, sha256) from the index; an
    unchanged known file is not read again unless `reverify` is set.
    """
    root_fd = os.open(root, _DIR_FLAGS)
    try:
        yield from _walk(root_fd, "", False, known, now_ns, reverify)
    finally:
        os.close(root_fd)


def _walk(
    dir_fd: int,
    prefix: str,
    dir_writable: bool,
    known: Mapping[str, tuple[int, int, str]],
    now_ns: int,
    reverify: bool,
) -> Iterator[Found | Skipped]:
    try:
        with os.scandir(dir_fd) as scanner:
            entries = sorted(scanner, key=lambda entry: entry.name)
    except OSError:
        yield Skipped(prefix or ".", "unreadable")
        return
    for entry in entries:
        name = entry.name
        rel = prefix + name
        try:
            name.encode("utf-8")
        except UnicodeEncodeError:
            yield Skipped(prefix + name.encode("utf-8", "replace").decode(), "unreadable-name")
            continue
        try:
            info = entry.stat(follow_symlinks=False)
        except OSError:
            yield Skipped(rel, "unreadable")
            continue
        if stat.S_ISLNK(info.st_mode):
            yield Skipped(rel, "symlink")
        elif stat.S_ISDIR(info.st_mode):
            yield from _walk_child(dir_fd, name, rel, dir_writable, known, now_ns, reverify)
        elif not stat.S_ISREG(info.st_mode):
            yield Skipped(rel, "not-regular")
        else:
            yield _file(dir_fd, name, rel, info, dir_writable, known, now_ns, reverify)


def _walk_child(
    dir_fd: int,
    name: str,
    rel: str,
    dir_writable: bool,
    known: Mapping[str, tuple[int, int, str]],
    now_ns: int,
    reverify: bool,
) -> Iterator[Found | Skipped]:
    try:
        child_fd = os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
    except OSError:
        yield Skipped(rel + "/", "unreadable")
        return
    try:
        writable = dir_writable or os.access(name, os.W_OK, dir_fd=dir_fd)
        yield from _walk(child_fd, rel + "/", writable, known, now_ns, reverify)
    finally:
        os.close(child_fd)


def _file(
    dir_fd: int,
    name: str,
    rel: str,
    info: os.stat_result,
    dir_writable: bool,
    known: Mapping[str, tuple[int, int, str]],
    now_ns: int,
    reverify: bool,
) -> Found | Skipped:
    if dir_writable:
        return Skipped(rel, "writable-directory")
    if os.access(name, os.W_OK, dir_fd=dir_fd):
        return Skipped(rel, "writable")
    if info.st_nlink > 1:
        return Skipped(rel, "multiple-links")
    if now_ns - info.st_mtime_ns < RECENT_NS:
        return Skipped(rel, "recently-modified")
    if info.st_size > 0 and info.st_blocks == 0:
        return Skipped(rel, "placeholder")
    seen = known.get(rel)
    if not reverify and seen is not None and seen[:2] == (info.st_size, info.st_mtime_ns):
        return Found(rel, info.st_size, info.st_mtime_ns, seen[2])
    return _hash(dir_fd, name, rel, info)


def _open_read(name: str, dir_fd: int) -> int:
    noatime = getattr(os, "O_NOATIME", 0)
    try:
        return os.open(name, _FILE_FLAGS | noatime, dir_fd=dir_fd)
    except PermissionError:
        if not noatime:
            raise
        return os.open(name, _FILE_FLAGS, dir_fd=dir_fd)  # O_NOATIME needs ownership


def _hash(dir_fd: int, name: str, rel: str, listed: os.stat_result) -> Found | Skipped:
    try:
        fd = _open_read(name, dir_fd)
    except OSError as exc:
        return Skipped(rel, "symlink" if exc.errno == errno.ELOOP else "unreadable")
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            return Skipped(rel, "not-regular")
        if opened.st_nlink > 1:
            return Skipped(rel, "multiple-links")
        if (opened.st_dev, opened.st_ino) != (listed.st_dev, listed.st_ino):
            return Skipped(rel, "changed-during-scan")
        digest = hashlib.sha256()
        while chunk := os.read(fd, _CHUNK):
            digest.update(chunk)
        after = os.fstat(fd)
    except OSError:
        return Skipped(rel, "unreadable")
    finally:
        os.close(fd)
    if (after.st_size, after.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns):
        return Skipped(rel, "changed-during-read")
    return Found(rel, opened.st_size, opened.st_mtime_ns, digest.hexdigest())
