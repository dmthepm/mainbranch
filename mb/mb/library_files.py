"""The media library's own file writes: anchored, no-follow, never through an alias.

Config, records and the index live inside the business folder. Every folder is
opened one component at a time without following symlinks, and each one, the
business folder included, must be owned by the running user and closed to group
and others. Every read and write then goes through the open folder descriptor,
never back through a path, so a folder swapped for a symlink afterwards cannot
redirect it. Every file is refused if it is a symlink, not regular, or has more
than one link. This is same-user accident prevention, not protection from a
process with the same OS user.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import secrets
import stat
import unicodedata
from collections.abc import Iterable, Iterator
from pathlib import Path

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_UNSAFE = frozenset({"Cc", "Cf", "Zl", "Zp", "Cs", "Co", "Cn"})


class LibraryError(Exception):
    """A refusal the person running the command should read."""


class MissingFolder(LibraryError):
    """A library folder that does not exist yet."""


def display(text: str) -> str:
    """`text` made safe to print: controls, line breaks and backslashes are written out.

    Every name, creator, said-by and path that came from outside the library goes
    through this before it reaches a terminal, so it cannot start a line of its own.
    """
    out: list[str] = []
    for char in text:
        code = ord(char)
        if char == "\\":
            out.append("\\\\")
        elif unicodedata.category(char) in _UNSAFE:
            out.append(_escape(code))
        else:
            out.append(char)
    return "".join(out)


def _escape(code: int) -> str:
    """Fixed width, so no escape can run into the characters after it and match another."""
    if code < 0x100:
        return f"\\x{code:02x}"
    return f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}"


def open_dir(root: Path, rel: str, *, create: bool) -> int:
    """Open `rel` under `root`, refusing symlinks, strangers' folders and loose permissions."""
    try:
        fd = os.open(root, _DIR_FLAGS)
    except OSError as exc:
        raise LibraryError(f"cannot open the business folder {root}: {exc.strerror}") from exc
    walked = ""
    try:
        _check_dir(fd, "the business folder")
        for part in [p for p in rel.split("/") if p]:
            walked = f"{walked}/{part}" if walked else part
            fd = _step(fd, part, walked, create)
            _check_dir(fd, walked)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _step(parent_fd: int, part: str, walked: str, create: bool) -> int:
    try:
        child = _open_child(parent_fd, part)
    except FileNotFoundError:
        if not create:
            raise MissingFolder(f"{walked} does not exist") from None
        os.mkdir(part, 0o700, dir_fd=parent_fd)
        child = _open_child(parent_fd, part)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise LibraryError(f"{walked} is a symlink or not a folder; not following") from exc
        raise LibraryError(f"cannot open {walked}: {exc.strerror}") from exc
    os.close(parent_fd)
    return child


def _open_child(parent_fd: int, part: str) -> int:
    return os.open(part, _DIR_FLAGS, dir_fd=parent_fd)


def _check_dir(fd: int, label: str) -> None:
    info = os.fstat(fd)
    if info.st_uid != os.geteuid():
        raise LibraryError(f"{label} is not owned by the running user")
    if info.st_mode & 0o022:
        raise LibraryError(f"{label} is writable by group or others; run chmod go-w on it")


def _plain(name: str) -> None:
    if not name or "/" in name or name in (".", ".."):
        raise LibraryError(f"{name!r} is not a plain file name")


def check_file(dir_fd: int, name: str) -> bool:
    """True if `name` exists as a safe regular file; False if absent; refuse an alias."""
    _plain(name)
    try:
        info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        raise LibraryError(f"{name} is a symlink; refusing to use it")
    if not stat.S_ISREG(info.st_mode):
        raise LibraryError(f"{name} is not a regular file")
    if info.st_nlink > 1:
        raise LibraryError(f"{name} has more than one link; refusing to use it")
    if info.st_uid != os.geteuid():
        raise LibraryError(f"{name} is not owned by the running user")
    if info.st_mode & 0o022:
        raise LibraryError(f"{name} is writable by group or others; run chmod go-w on it")
    return True


def read_file(dir_fd: int, name: str, *, limit: int | None = None) -> bytes | None:
    """The file's bytes, or None if absent. With `limit`, a bigger file is refused."""
    if not check_file(dir_fd, name):
        return None
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)
    except OSError as exc:
        raise LibraryError(f"cannot read {name}: {exc.strerror}") from exc
    with os.fdopen(fd, "rb") as handle:
        if limit is None:
            return handle.read()
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise LibraryError(f"{name} is too large (limit {limit} bytes)")
    return data


def write_file(dir_fd: int, name: str, data: bytes) -> None:
    """Replace `name` atomically with `data`, mode 0600, unless it is an alias."""
    check_file(dir_fd, name)
    temp = f".{name}.tmp-{os.getpid()}-{secrets.token_hex(4)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(temp, flags, 0o600, dir_fd=dir_fd)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.rename(temp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp, dir_fd=dir_fd)
        raise


@contextlib.contextmanager
def exclusive(dir_fd: int, name: str) -> Iterator[None]:
    """Hold an advisory lock on a plain file in the checked folder; one holder at a time."""
    _plain(name)
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        fd = os.open(name, flags, 0o600, dir_fd=dir_fd)
    except OSError as exc:
        raise LibraryError(f"cannot open {name}: {exc.strerror}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1 or info.st_uid != os.geteuid():
            raise LibraryError(f"{name} is not a plain file of our own; refusing to use it")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LibraryError(
                "another scan is already running here; wait for it to finish"
            ) from None
        yield
    finally:
        os.close(fd)


def refuse_overlap(path: Path, sources: Iterable[Path]) -> None:
    """A library folder or file may not sit inside a source, nor contain one."""
    resolved = path.resolve()
    for source in sources:
        root = source.resolve()
        if resolved == root or resolved.is_relative_to(root):
            raise LibraryError(f"{path} is inside a source ({source}); refusing")
        if root.is_relative_to(resolved):
            raise LibraryError(f"{path} contains a source ({source}); refusing")
