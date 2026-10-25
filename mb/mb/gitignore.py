"""Safety checks shared by repo-local .gitignore readers and writers."""

from __future__ import annotations

import stat
from pathlib import Path


def gitignore_problem(repo: Path) -> str:
    """Return an actionable finding unless .gitignore is absent or a regular file."""
    path = repo / ".gitignore"
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return ""
    if stat.S_ISLNK(mode):
        kind = "a symlink"
    elif not stat.S_ISREG(mode) or not path.resolve().is_relative_to(repo.resolve()):
        kind = "not a regular file inside the repo"
    else:
        return ""
    return (
        f".gitignore is {kind}; Main Branch will not read or edit it. "
        "Replace it with a regular file, then rerun."
    )
