"""Test helpers for the folder record that says which folder may use which repo's keys."""

from __future__ import annotations

from pathlib import Path

from mb import connect as connect_mod


def bind_folder(repo: Path, repo_id: str) -> None:
    """Record ``repo`` as a folder that saved keys under ``repo_id``.

    For fixtures that write a made-up repo id into a folder. It adds the record a
    real save leaves, so the rule stays on.
    """

    identity = connect_mod._repo_identity(Path(repo).resolve())
    connect_mod._record_repo_binding(repo_id, identity["basis_sha256"])


def rebind_folder(repo: Path) -> None:
    """Run the owner's rebind for ``repo`` after its identity changed (for example ``git init``)."""

    connect_mod.rebind(repo, apply=True)
