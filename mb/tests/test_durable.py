"""Crash-safety helpers: parent-directory fsync and the strict JSON read."""

from __future__ import annotations

import errno
import os
import stat
import sys
from pathlib import Path

import pytest

from mb.durable import (
    CorruptStateError,
    UnconfirmedWriteError,
    atomic_write_text,
    read_json_object,
)


def test_atomic_write_fsyncs_the_parent_directory_after_the_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "state.json"
    events: list[str] = []
    real_fsync = os.fsync
    real_replace = os.replace

    def fsync(fd: int) -> None:
        events.append("fsync-dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "fsync-file")
        real_fsync(fd)

    def replace(src: str | Path, dst: str | Path) -> None:
        events.append("replace")
        real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)

    atomic_write_text(target, "{}\n")

    assert target.read_text(encoding="utf-8") == "{}\n"
    assert events == ["fsync-file", "replace", "fsync-dir"]


def test_empty_json_file_still_reads_as_default_by_default(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("  \n", encoding="utf-8")

    assert read_json_object(path) == {}
    assert read_json_object(path, default={"a": 1}) == {"a": 1}


def test_strict_read_treats_an_empty_file_as_corrupt(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("", encoding="utf-8")

    with pytest.raises(CorruptStateError, match="empty"):
        read_json_object(path, strict=True)


def test_strict_read_still_defaults_a_missing_file_and_reads_valid_json(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert read_json_object(path, default={"a": 1}, strict=True) == {"a": 1}

    path.write_text('{"b": 2}', encoding="utf-8")
    assert read_json_object(path, strict=True) == {"b": 2}


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads /proc/self/fd")
def test_new_parent_directories_are_persisted_through_their_own_parents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    synced: list[Path] = []
    real_fsync = os.fsync

    def fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            synced.append(Path(os.readlink(f"/proc/self/fd/{fd}")))
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)

    atomic_write_text(tmp_path / "a" / "b" / "state.json", "{}\n")

    assert set(synced) == {tmp_path / "a" / "b", tmp_path / "a", tmp_path}


def test_a_file_fsync_failure_surfaces_and_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fsync(fd: int) -> None:
        raise OSError(5, "file fsync failed")

    monkeypatch.setattr(os, "fsync", fsync)

    with pytest.raises(OSError, match="file fsync failed"):
        atomic_write_text(tmp_path / "state.json", "{}\n")

    assert list(tmp_path.iterdir()) == []


def _fail_directory_fsync(monkeypatch: pytest.MonkeyPatch, *, times: int = 99) -> list[int]:
    real_fsync = os.fsync
    failures: list[int] = []

    def fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode) and len(failures) < times:
            failures.append(fd)
            raise OSError(5, "directory fsync failed")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    return failures


def test_a_directory_fsync_failure_after_the_replace_is_named_unconfirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "state.json"
    _fail_directory_fsync(monkeypatch)

    with pytest.raises(UnconfirmedWriteError, match="directory fsync failed"):
        atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_an_unopenable_directory_fails_before_the_destination_changes(tmp_path: Path) -> None:
    folder = tmp_path / "locked"
    folder.mkdir()
    target = folder / "state.json"
    target.write_text("old\n", encoding="utf-8")
    folder.chmod(0o300)  # write and search, but no read: the directory cannot be opened
    try:
        with pytest.raises(PermissionError):
            atomic_write_text(target, "new\n")
    finally:
        folder.chmod(0o700)

    assert target.read_text(encoding="utf-8") == "old\n"
    assert [p.name for p in folder.iterdir()] == ["state.json"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads /proc/self/fd")
def test_a_retry_after_a_failed_directory_sync_still_persists_every_new_ancestor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a" / "b" / "state.json"
    _fail_directory_fsync(monkeypatch, times=1)

    with pytest.raises(OSError, match="directory fsync failed"):
        atomic_write_text(target, "{}\n")

    synced: list[Path] = []
    real_fsync = os.fsync

    def fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            synced.append(Path(os.readlink(f"/proc/self/fd/{fd}")))
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    atomic_write_text(target, "{}\n")

    assert target.read_text(encoding="utf-8") == "{}\n"
    assert set(synced) == {tmp_path / "a" / "b", tmp_path / "a", tmp_path}


def test_a_directory_made_by_another_process_survives_a_later_sync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a" / "b" / "state.json"
    real_mkdir = Path.mkdir

    def racing_mkdir(self: Path, mode: int = 0o777) -> None:
        if self == tmp_path / "a":
            real_mkdir(self, mode)  # the other process wins
        real_mkdir(self, mode)

    monkeypatch.setattr(Path, "mkdir", racing_mkdir)
    _fail_directory_fsync(monkeypatch)

    with pytest.raises(OSError, match="directory fsync failed"):
        atomic_write_text(target, "{}\n")

    assert (tmp_path / "a").is_dir()
    assert not (tmp_path / "a" / "b").exists()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads /proc/self/fd")
@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_an_unopenable_parent_leaves_no_descriptor_behind(tmp_path: Path) -> None:
    folder = tmp_path / "locked"
    folder.mkdir()
    folder.chmod(0o300)
    before = len(os.listdir("/proc/self/fd"))
    try:
        for _ in range(3):
            with pytest.raises(PermissionError):
                atomic_write_text(folder / "state.json", "new\n")
    finally:
        folder.chmod(0o700)

    assert len(os.listdir("/proc/self/fd")) == before
    assert list(folder.iterdir()) == []


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads /proc/self/fd")
def test_an_encoding_failure_leaves_no_descriptor_and_no_temp_file(tmp_path: Path) -> None:
    before = len(os.listdir("/proc/self/fd"))

    with pytest.raises(UnicodeEncodeError):
        atomic_write_text(tmp_path / "state.json", "caf\u00e9\n", encoding="ascii")

    assert len(os.listdir("/proc/self/fd")) == before
    assert list(tmp_path.iterdir()) == []


def test_newline_translation_matches_text_mode(tmp_path: Path) -> None:
    atomic_write_text(tmp_path / "a", "x\ny\n", newline="\r\n")
    atomic_write_text(tmp_path / "b", "x\ny\n", newline="")
    atomic_write_text(tmp_path / "c", "x\ny\n")

    assert (tmp_path / "a").read_bytes() == b"x\r\ny\r\n"
    assert (tmp_path / "b").read_bytes() == b"x\ny\n"
    assert (tmp_path / "c").read_bytes() == ("x\ny\n".replace("\n", os.linesep)).encode()


def test_newline_values_text_mode_rejected_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="newline"):
        atomic_write_text(tmp_path / "state.json", "x\n", newline="\n\n")

    assert list(tmp_path.iterdir()) == []


def test_partial_writes_are_completed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_write = os.write

    def short_write(fd: int, data: bytes | memoryview) -> int:
        return real_write(fd, bytes(data)[:3])

    monkeypatch.setattr(os, "write", short_write)

    atomic_write_text(tmp_path / "state.json", "hello world\n", newline="")

    assert (tmp_path / "state.json").read_bytes() == b"hello world\n"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads /proc/self/fd")
def test_a_write_failure_closes_once_leaves_no_temp_and_surfaces_the_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_close = os.close
    closed: list[int] = []

    def broken_write(fd: int, data: bytes | memoryview) -> int:
        raise OSError(28, "No space left on device")

    def counting_close(fd: int) -> None:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(os, "write", broken_write)
    monkeypatch.setattr(os, "close", counting_close)
    before = len(os.listdir("/proc/self/fd"))

    with pytest.raises(OSError, match="No space left"):
        atomic_write_text(tmp_path / "state.json", "new\n")

    assert len(closed) == 1
    assert len(os.listdir("/proc/self/fd")) == before
    assert list(tmp_path.iterdir()) == []


def test_a_zero_progress_write_raises_instead_of_spinning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def zero_write(fd: int, data: bytes | memoryview) -> int:
        nonlocal calls
        calls += 1
        assert calls < 100, "write loop is spinning"
        return 0

    monkeypatch.setattr(os, "write", zero_write)

    with pytest.raises(OSError, match="no progress"):
        atomic_write_text(tmp_path / "state.json", "new\n")

    assert list(tmp_path.iterdir()) == []


def _close_raising_for_files(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    real_close = os.close
    attempts: list[int] = []

    def failing_close(fd: int) -> None:
        is_dir = stat.S_ISDIR(os.fstat(fd).st_mode)
        real_close(fd)
        if not is_dir:
            attempts.append(fd)
            raise OSError(5, "close failed")

    monkeypatch.setattr(os, "close", failing_close)
    return attempts


def test_a_close_failure_never_replaces_a_pending_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_write(fd: int, data: bytes | memoryview) -> int:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "write", broken_write)
    attempts = _close_raising_for_files(monkeypatch)

    with pytest.raises(OSError, match="No space left"):
        atomic_write_text(tmp_path / "state.json", "new\n")

    assert len(attempts) == 1
    assert list(tmp_path.iterdir()) == []


def test_a_close_failure_surfaces_when_nothing_failed_earlier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = _close_raising_for_files(monkeypatch)

    with pytest.raises(OSError, match="close failed"):
        atomic_write_text(tmp_path / "state.json", "new\n")

    assert len(attempts) == 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("code", [errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP])
def test_a_disk_that_cannot_sync_a_directory_is_carried_on_past(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    real_fsync = os.fsync

    def fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(code, "directory sync not supported")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    target = tmp_path / "a" / "b" / "state.json"

    atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert [p.name for p in target.parent.iterdir()] == ["state.json"]


def test_eio_on_a_directory_sync_is_still_unconfirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_fsync = os.fsync

    def fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(errno.EIO, "input/output error")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)

    with pytest.raises(UnconfirmedWriteError):
        atomic_write_text(tmp_path / "state.json", "new\n")


def test_ebadf_on_a_directory_sync_is_still_unconfirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_fsync = os.fsync

    def fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(errno.EBADF, "bad file descriptor")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)

    with pytest.raises(UnconfirmedWriteError):
        atomic_write_text(tmp_path / "state.json", "new\n")


@pytest.mark.parametrize("code", [errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP])
def test_an_unsupported_errno_on_a_descriptor_that_is_not_a_directory_is_not_carried_past(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    from mb import durable

    plain = tmp_path / "plain"
    plain.write_text("x", encoding="utf-8")
    wrong: list[int] = []

    def open_wrong(_directory: Path) -> int:
        wrong.append(os.open(plain, os.O_RDONLY))
        return wrong[0]

    monkeypatch.setattr(durable, "_open_directory", open_wrong)
    real_fsync = os.fsync

    def fsync(fd: int) -> None:
        if wrong and fd == wrong[0]:
            raise OSError(code, "not supported")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)

    with pytest.raises(UnconfirmedWriteError):
        atomic_write_text(tmp_path / "state.json", "new\n")


@pytest.mark.skipif(not hasattr(os, "O_DIRECTORY"), reason="needs O_DIRECTORY")
def test_a_directory_is_opened_with_o_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flags: list[int] = []
    real_open = os.open

    def spy(path: object, flag: int, *args: object, **kwargs: object) -> int:
        flags.append(flag)
        return real_open(path, flag, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", spy)
    atomic_write_text(tmp_path / "state.json", "new\n")

    assert any(flag & os.O_DIRECTORY for flag in flags)
