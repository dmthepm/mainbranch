"""Crash-safety helpers: parent-directory fsync and the strict JSON read."""

from __future__ import annotations

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
    real_mkdir = os.mkdir

    def racing_mkdir(name: str, *args: object, **kwargs: object) -> None:
        if name == "a":
            real_mkdir(name, *args, **kwargs)  # type: ignore[arg-type]  # the other process wins
        real_mkdir(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "mkdir", racing_mkdir)
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


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="uses directory descriptors")
def test_a_directory_replaced_after_our_mkdir_is_not_removed_by_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a" / "b" / "state.json"
    real_fsync = os.fsync
    swapped: list[bool] = []

    def fsync(fd: int) -> None:
        if not swapped:
            swapped.append(True)
            os.rename(tmp_path / "a", tmp_path / "moved")  # another call takes ours away
            os.mkdir(tmp_path / "a")  # and puts its own empty directory at the name
            raise OSError(5, "directory fsync failed")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)

    with pytest.raises(OSError, match="directory fsync failed"):
        atomic_write_text(target, "{}\n")

    assert (tmp_path / "a").is_dir()  # not ours any more: cleanup must leave it


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads /proc/self/fd")
def test_a_failure_before_fdopen_takes_ownership_closes_the_temp_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_fdopen(fd: int, *args: object, **kwargs: object) -> None:
        raise RuntimeError("wrapper setup failed")  # raised before it owns fd

    monkeypatch.setattr(os, "fdopen", broken_fdopen)
    before = len(os.listdir("/proc/self/fd"))

    with pytest.raises(RuntimeError, match="wrapper setup failed"):
        atomic_write_text(tmp_path / "state.json", "new\n")

    assert len(os.listdir("/proc/self/fd")) == before
    assert list(tmp_path.iterdir()) == []
