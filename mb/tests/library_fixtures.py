"""Generated-bytes media sources for the library tests. No real media."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

OLD = 1_700_000_000  # an mtime far enough in the past to clear the recent-write skip

needs_nonroot = pytest.mark.skipif(
    os.geteuid() == 0,
    reason=(
        "running as root: os.access reports every path writable, so write refusal "
        "cannot be shown here; run as an ordinary user to prove it"
    ),
)


def blob(label: str, size: int = 96) -> bytes:
    """Deterministic fake image bytes, distinct per label."""
    seed = hashlib.sha256(label.encode()).digest()
    return (seed * (size // len(seed) + 1))[:size]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_tree(root: Path, files: dict[str, bytes]) -> Path:
    """Write files (relative path -> bytes), age them, leave everything writable."""
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.utime(path, (OLD, OLD))
    return root


def lock(root: Path) -> Path:
    """Make a tree read-only for its owner: files 0444, directories 0555."""
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for name in filenames:
            path = Path(dirpath, name)
            if not path.is_symlink() and stat.S_ISREG(path.lstat().st_mode):
                path.chmod(0o444)
        for name in dirnames:
            path = Path(dirpath, name)
            if not path.is_symlink():
                path.chmod(0o555)
    root.chmod(0o555)
    return root


def unlock(root: Path) -> None:
    """Undo `lock` so pytest can delete the tree."""
    if not root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        Path(dirpath).chmod(0o755)
        for name in filenames:
            path = Path(dirpath, name)
            if not path.is_symlink():
                path.chmod(0o644)
        for name in dirnames:
            path = Path(dirpath, name)
            if not path.is_symlink():
                path.chmod(0o755)


@pytest.fixture()
def read_only_source(tmp_path: Path):
    """Factory: `read_only_source(files)` returns a locked source folder."""
    made: list[Path] = []

    def factory(files: dict[str, bytes], name: str = "studio-media") -> Path:
        root = make_tree(tmp_path / "sources" / name, files)
        made.append(root)
        return lock(root)

    yield factory
    for root in made:
        unlock(root)


def snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    """Path -> (size, mtime_ns, sha256) of every file under root, plus directories."""
    state: dict[str, tuple[int, int, str]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames:
            path = Path(dirpath, name)
            state[str(path.relative_to(root)) + "/"] = (0, path.lstat().st_mtime_ns, "")
        for name in filenames:
            path = Path(dirpath, name)
            info = path.lstat()
            digest = sha(path.read_bytes()) if stat.S_ISREG(info.st_mode) else ""
            state[str(path.relative_to(root))] = (info.st_size, info.st_mtime_ns, digest)
    return state
