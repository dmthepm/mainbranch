"""Reading a source: read-only, no-follow, and every file accounted for."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from mb import library_source as source
from tests.library_fixtures import (
    OLD,
    blob,
    lock,
    make_tree,
    needs_nonroot,
    sha,
    snapshot,
    unlock,
)

pytestmark = needs_nonroot

NOW_NS = (OLD + 10_000) * 1_000_000_000


def scan(root: Path, known=None, reverify=False):
    found, skipped = {}, {}
    for item in source.scan_source(root, known or {}, now_ns=NOW_NS, reverify=reverify):
        if isinstance(item, source.Found):
            found[item.rel] = item
        else:
            skipped[item.rel] = item.reason
    return found, skipped


def test_finds_files_with_their_content_fingerprint(read_only_source):
    pour = blob("pour")
    root = read_only_source({"candle-pour-01.jpg": pour, "reels/wick.mp4": blob("wick")})
    found, skipped = scan(root)
    assert skipped == {}
    assert sorted(found) == ["candle-pour-01.jpg", "reels/wick.mp4"]
    assert found["candle-pour-01.jpg"].sha256 == sha(pour)
    assert found["candle-pour-01.jpg"].size == len(pour)


def test_a_writable_root_is_refused(tmp_path):
    root = make_tree(tmp_path / "open-folder", {"a.jpg": blob("a")})
    assert source.root_problem(root) == "writable"


def test_a_read_only_root_is_accepted(read_only_source):
    assert source.root_problem(read_only_source({"a.jpg": blob("a")})) is None


def test_missing_root_and_file_root_are_refused(tmp_path):
    (tmp_path / "plain.txt").write_text("x")
    assert "not a directory" in (source.root_problem(tmp_path / "nope") or "")
    assert "not a directory" in (source.root_problem(tmp_path / "plain.txt") or "")


def test_a_writable_file_is_skipped_and_listed(read_only_source):
    root = read_only_source({"ok.jpg": blob("ok"), "loose.jpg": blob("loose")})
    root.chmod(0o755)
    (root / "loose.jpg").chmod(0o644)
    root.chmod(0o555)
    found, skipped = scan(root)
    assert sorted(found) == ["ok.jpg"]
    assert skipped == {"loose.jpg": "writable"}


def test_files_in_a_writable_subfolder_are_listed_not_indexed(read_only_source):
    root = read_only_source({"ok.jpg": blob("ok"), "inbox/new.jpg": blob("new")})
    (root / "inbox").chmod(0o755)
    found, skipped = scan(root)
    assert sorted(found) == ["ok.jpg"]
    assert skipped == {"inbox/new.jpg": "writable-directory"}


def test_a_multiply_linked_file_is_skipped_and_listed(tmp_path):
    outside = make_tree(tmp_path / "elsewhere", {"orig.jpg": blob("orig")})
    root = make_tree(tmp_path / "sources" / "studio", {"solo.jpg": blob("solo")})
    os.link(outside / "orig.jpg", root / "linked.jpg")
    os.link(root / "solo.jpg", root / "solo-again.jpg")
    for path in (root, root / "linked.jpg", root / "solo.jpg", root / "solo-again.jpg"):
        path.chmod(0o444 if path.is_file() else 0o555)
    try:
        found, skipped = scan(root)
        assert found == {}
        assert skipped == {
            "linked.jpg": "multiple-links",
            "solo.jpg": "multiple-links",
            "solo-again.jpg": "multiple-links",
        }
    finally:
        root.chmod(0o755)


def test_symlinks_and_other_non_regular_files_are_skipped(tmp_path):
    outside = make_tree(tmp_path / "elsewhere", {"secret.jpg": blob("secret")})
    root = make_tree(tmp_path / "sources" / "studio", {"ok.jpg": blob("ok")})
    os.symlink(outside / "secret.jpg", root / "out.jpg")
    os.symlink(outside, root / "outdir")
    os.symlink("ok.jpg", root / "inside.jpg")
    os.mkfifo(root / "pipe.jpg")
    (root / "ok.jpg").chmod(0o444)
    (root / "pipe.jpg").chmod(0o444)
    root.chmod(0o555)
    try:
        found, skipped = scan(root)
        assert sorted(found) == ["ok.jpg"]
        assert skipped == {
            "out.jpg": "symlink",
            "outdir": "symlink",
            "inside.jpg": "symlink",
            "pipe.jpg": "not-regular",
        }
    finally:
        root.chmod(0o755)


def test_recently_modified_files_are_skipped(read_only_source):
    root = read_only_source({"fresh.jpg": blob("fresh"), "old.jpg": blob("old")})
    fresh = NOW_NS - 5 * 1_000_000_000
    root.chmod(0o755)
    os.utime(root / "fresh.jpg", ns=(fresh, fresh))
    root.chmod(0o555)
    found, skipped = scan(root)
    assert sorted(found) == ["old.jpg"]
    assert skipped == {"fresh.jpg": "recently-modified"}


def test_cloud_placeholders_are_skipped(tmp_path):
    root = make_tree(tmp_path / "sources" / "studio", {"ok.jpg": blob("ok")})
    with open(root / "stub.jpg", "wb") as handle:
        handle.truncate(1 << 20)
    os.utime(root / "stub.jpg", (OLD, OLD))
    if (root / "stub.jpg").stat().st_blocks != 0:
        pytest.skip("this filesystem allocates blocks for sparse files; placeholder rule unproven")
    for name in ("ok.jpg", "stub.jpg"):
        (root / name).chmod(0o444)
    root.chmod(0o555)
    try:
        found, skipped = scan(root)
        assert sorted(found) == ["ok.jpg"]
        assert skipped == {"stub.jpg": "placeholder"}
    finally:
        root.chmod(0o755)


def test_every_entry_is_indexed_or_listed(tmp_path):
    root = make_tree(
        tmp_path / "sources" / "studio",
        {"a.jpg": blob("a"), "b/c.jpg": blob("c"), "b/d/e.mp4": blob("e")},
    )
    os.symlink("a.jpg", root / "link.jpg")
    os.mkfifo(root / "pipe")
    os.link(root / "a.jpg", root / "a2.jpg")
    lock(root)
    try:
        found, skipped = scan(root)
        on_disk = {
            str(Path(d, f).relative_to(root)) for d, _, files in os.walk(root) for f in files
        }
        assert sorted(found) == ["b/c.jpg", "b/d/e.mp4"]
        assert on_disk == set(found) | set(skipped)
        assert set(found).isdisjoint(skipped)
    finally:
        unlock(root)


def test_known_unchanged_files_are_not_read_again(read_only_source, monkeypatch):
    data = blob("a")
    root = read_only_source({"a.jpg": data})
    info = (root / "a.jpg").stat()
    known = {"a.jpg": (info.st_size, info.st_mtime_ns, "f" * 64)}
    opened: list[str] = []
    real_open = os.open

    def spy(path, flags, *args, **kwargs):
        opened.append(str(path))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", spy)
    found, _ = scan(root, known)
    assert found["a.jpg"].sha256 == "f" * 64  # trusted from the index
    assert "a.jpg" not in opened
    found, _ = scan(root, known, reverify=True)
    assert found["a.jpg"].sha256 == sha(data)  # --verify re-reads


def test_a_changed_file_is_rehashed(read_only_source):
    root = read_only_source({"a.jpg": blob("a")})
    known = {"a.jpg": (1, 1, "0" * 64)}
    found, _ = scan(root, known)
    assert found["a.jpg"].sha256 == sha(blob("a"))


def test_reading_never_asks_for_write_access(read_only_source, monkeypatch):
    root = read_only_source({"a.jpg": blob("a"), "sub/b.jpg": blob("b")})
    flags_seen: list[int] = []
    real_open = os.open

    def spy(path, flags, *args, **kwargs):
        flags_seen.append(flags)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", spy)
    scan(root)
    assert flags_seen
    write_bits = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    assert all(flag & write_bits == 0 for flag in flags_seen)
    assert all(flag & os.O_NOFOLLOW for flag in flags_seen)


def test_scanning_leaves_the_source_byte_for_byte_alone(read_only_source):
    root = read_only_source({"a.jpg": blob("a"), "sub/b.jpg": blob("b")})
    before = snapshot(root)
    modes = {p: stat.S_IMODE(p.lstat().st_mode) for p in root.rglob("*")}
    scan(root)
    scan(root, reverify=True)
    assert snapshot(root) == before
    assert {p: stat.S_IMODE(p.lstat().st_mode) for p in root.rglob("*")} == modes


def test_a_file_swapped_for_a_symlink_after_listing_is_not_followed(read_only_source, tmp_path):
    secret = tmp_path / "secret.bin"
    secret.write_bytes(b"outside")
    root = read_only_source({"a.jpg": blob("a")})
    root.chmod(0o755)
    (root / "a.jpg").unlink()
    os.symlink(secret, root / "a.jpg")
    root.chmod(0o555)
    found, skipped = scan(root)
    assert found == {}
    assert skipped == {"a.jpg": "symlink"}
