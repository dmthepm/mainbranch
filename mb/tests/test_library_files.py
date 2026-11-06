"""The library's own writes: anchored, no-follow, never through an alias."""

from __future__ import annotations

import os
import stat

import pytest

from mb import library_files as files


@pytest.fixture()
def biz(tmp_path):
    root = tmp_path / "acme-candles"
    root.mkdir()
    return root


def test_write_creates_a_private_file_and_replaces_it(biz):
    fd = files.open_dir(biz, ".mb/private/library", create=True)
    files.write_file(fd, "config.yaml", b"one")
    files.write_file(fd, "config.yaml", b"two")
    path = biz / ".mb/private/library/config.yaml"
    assert path.read_bytes() == b"two"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert sorted(p.name for p in path.parent.iterdir()) == ["config.yaml"]  # no temp left
    assert files.read_file(fd, "config.yaml") == b"two"
    assert files.read_file(fd, "absent.yaml") is None
    os.close(fd)


def test_a_missing_folder_is_not_created_unless_asked(biz):
    with pytest.raises(files.LibraryError, match="does not exist"):
        files.open_dir(biz, "library/records", create=False)
    assert not (biz / "library").exists()


def test_a_symlinked_folder_component_is_refused(biz, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(elsewhere, biz / "library")
    with pytest.raises(files.LibraryError, match="symlink"):
        files.open_dir(biz, "library/records", create=True)
    assert list(elsewhere.iterdir()) == []


def test_a_group_or_world_writable_folder_is_refused(biz):
    folder = biz / "library"
    folder.mkdir()
    folder.chmod(0o775)
    with pytest.raises(files.LibraryError, match="writable by group or others"):
        files.open_dir(biz, "library", create=True)


def test_a_folder_owned_by_someone_else_is_refused(biz, monkeypatch):
    (biz / "library").mkdir(mode=0o700)
    me = os.geteuid()
    monkeypatch.setattr(os, "geteuid", lambda: me + 1)
    with pytest.raises(files.LibraryError, match="not owned"):
        files.open_dir(biz, "library", create=True)


def test_a_destination_symlink_is_refused_and_the_target_untouched(biz, tmp_path):
    fd = files.open_dir(biz, "library", create=True)
    target = tmp_path / "original.jpg"
    target.write_bytes(b"original")
    os.symlink(target, biz / "library" / "rec.yaml")
    with pytest.raises(files.LibraryError, match="symlink"):
        files.write_file(fd, "rec.yaml", b"overwrite")
    assert target.read_bytes() == b"original"
    with pytest.raises(files.LibraryError, match="symlink"):
        files.read_file(fd, "rec.yaml")


def test_a_hardlinked_destination_is_refused_and_the_other_link_untouched(biz, tmp_path):
    fd = files.open_dir(biz, "library", create=True)
    original = tmp_path / "original.jpg"
    original.write_bytes(b"original")
    os.link(original, biz / "library" / "index.db")
    with pytest.raises(files.LibraryError, match="more than one link"):
        files.write_file(fd, "index.db", b"overwrite")
    assert original.read_bytes() == b"original"
    with pytest.raises(files.LibraryError, match="more than one link"):
        files.check_file(fd, "index.db")


def test_a_non_regular_destination_is_refused(biz):
    fd = files.open_dir(biz, "library", create=True)
    os.mkdir(biz / "library" / "rec.yaml")
    with pytest.raises(files.LibraryError, match="not a regular file"):
        files.write_file(fd, "rec.yaml", b"x")


def test_a_file_writable_by_others_is_refused_on_read(biz):
    fd = files.open_dir(biz, "library", create=True)
    path = biz / "library" / "rec.yaml"
    path.write_bytes(b"x")
    path.chmod(0o666)
    with pytest.raises(files.LibraryError, match="writable by group or others"):
        files.read_file(fd, "rec.yaml")


def test_a_name_with_a_slash_is_refused(biz):
    fd = files.open_dir(biz, "library", create=True)
    with pytest.raises(files.LibraryError, match="plain file name"):
        files.write_file(fd, "../escape.yaml", b"x")


@pytest.mark.parametrize(
    ("where", "refused"),
    [
        ("sources/studio/records", True),  # inside a source
        ("sources/studio", True),  # is a source
        ("sources", True),  # contains a source
        ("sources-elsewhere/records", False),
        ("library/records", False),
    ],
)
def test_library_paths_may_not_overlap_a_source(tmp_path, where, refused):
    source = tmp_path / "sources" / "studio"
    source.mkdir(parents=True)
    (tmp_path / "sources-elsewhere").mkdir()
    (tmp_path / "library").mkdir()
    target = tmp_path / where
    target.mkdir(parents=True, exist_ok=True)
    if refused:
        with pytest.raises(files.LibraryError, match="inside a source|contains a source"):
            files.refuse_overlap(target, [source])
    else:
        files.refuse_overlap(target, [source])


def test_overlap_is_judged_after_resolving_symlinks(tmp_path):
    source = tmp_path / "sources" / "studio"
    source.mkdir(parents=True)
    alias = tmp_path / "alias"
    os.symlink(source, alias)
    with pytest.raises(files.LibraryError):
        files.refuse_overlap(alias, [source])
