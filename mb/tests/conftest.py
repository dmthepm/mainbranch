"""Pytest fixtures for mb tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mb import __version__
from mb import codex as codex_mod
from mb import engine as engine_mod


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    """Empty directory ready for ``mb init``."""
    return tmp_path / "biz"


@pytest.fixture(autouse=True)
def isolated_state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every test's ``mb feedback`` writes out of the real user state dir.

    Connect boundary refusals log themselves, so any test that reaches one
    would otherwise append to the operator's own feedback file.
    """

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    monkeypatch.delenv("MB_FEEDBACK_LOG", raising=False)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every test out of the contributor's real home folder.

    Doctor repairs, `mb update` and the Codex adapter resolve global roots
    such as ``~/.codex/skills``, ``~/.claude/skills`` and the XDG data and
    config folders from ``HOME``. Without this a test that does not set
    ``MAINBRANCH_CODEX_SKILLS_ROOT`` or ``MAINBRANCH_CODEX_PLUGIN_ROOT``
    would write into the real ones. Tests that set their own ``HOME`` or
    roots still win, because their ``monkeypatch`` calls run after this.
    """

    home = tmp_path / "isolated-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "CODEX_HOME", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def isolated_credential_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every test away from the operator's own credential store.

    `mb connect status` probes credential-backend health even with no
    provider connected, so without this a status-reading test would ask the
    real Keychain or Secret Service. Tests that need another backend set it.
    """

    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "mainbranch-home"))


@pytest.fixture(autouse=True)
def stable_runtime_mb_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep Codex runtime readiness tests independent of the host PATH."""

    monkeypatch.setattr(
        codex_mod,
        "_login_shell_mb_diagnostics",
        lambda: {
            "checked": True,
            "ok": True,
            "state": "ok",
            "shell": "/bin/sh",
            "command": "command -v mb",
            "path": "/usr/local/bin/mb",
            "version": __version__,
            "active_path": "/usr/local/bin/mb",
            "active_version": __version__,
            "path_mismatch": False,
            "version_mismatch": False,
            "mismatch": False,
            "error": "",
            "summary": "Login-shell runtime resolves the current mb command.",
            "repair": "",
            "safe_to_share": True,
        },
    )


@pytest.fixture(autouse=True)
def no_installed_mb_version_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never run a real ``mb --version`` from a test.

    `mb doctor` and the migration lint list every ``mb`` on PATH and ask each
    for its version. Unstubbed, every such test starts the contributor's own
    installed ``mb`` (a full interpreter start), which under parallel workers
    loads the host heavily. Tests that check the version probe set their own.
    """

    monkeypatch.setattr(
        engine_mod,
        "_mb_binary_version",
        lambda path, **_: {
            "ok": True,
            "version": __version__,
            "output": f"mb {__version__}",
            "error": "",
        },
    )


@pytest.fixture(autouse=True)
def no_installed_mb_on_path(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Put a no-op ``mb`` first on PATH so no test starts the contributor's own.

    The commit-msg hook writes ``shutil.which("mb")`` into itself, so a test
    that installs the hook and then commits would run the installed
    ``mb checkpoint --validate -``. Hooks installed from a test, and the hook's
    own ``command -v mb`` fallback, now resolve to this stub. Tests that need
    real validation put their own shim (``sys.executable -m mb``) first on
    PATH, which wins because their ``monkeypatch`` calls run after this one.
    """

    # Outside the test's own ``tmp_path``, which some tests list in full.
    stub_dir = tmp_path_factory.mktemp("no-installed-mb")
    stub = stub_dir / "mb"
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub_dir}{os.pathsep}{os.environ.get('PATH', '')}")
