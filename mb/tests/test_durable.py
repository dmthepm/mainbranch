"""Crash-safety helpers: parent-directory fsync and the strict JSON read."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from mb.durable import CorruptStateError, atomic_write_text, read_json_object


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


def test_a_directory_fsync_failure_surfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_fsync = os.fsync

    def fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(5, "directory fsync failed")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)

    with pytest.raises(OSError, match="directory fsync failed"):
        atomic_write_text(tmp_path / "state.json", "{}\n")
