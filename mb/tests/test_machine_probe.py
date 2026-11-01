"""Trust boundaries for the machine doctor probe layer."""

import ast
import os
import subprocess
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from mb import machine_probe as probe


@pytest.fixture
def root_owned(monkeypatch):
    original = Path.lstat

    def root_stat(path):
        fields = list(original(path))
        fields[4] = 0
        return os.stat_result(fields)

    monkeypatch.setattr(Path, "lstat", root_stat)


def test_path_hijack_never_runs(tmp_path, monkeypatch, root_owned):
    binary = tmp_path / "systemctl"
    binary.write_text("#!/bin/sh\nexit 99\n")
    binary.chmod(0o777)
    monkeypatch.setenv("PATH", str(tmp_path))
    popen = Mock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    result = probe.run_probe("ubuntu", ("systemctl",), deadline=time.monotonic() + 1)
    assert result.reason == "untrusted_executable"
    popen.assert_not_called()


@pytest.mark.parametrize("ancestor", [False, True])
def test_writable_executable_or_ancestor_rejected(monkeypatch, ancestor, root_owned):
    real_stat = Path.lstat

    def fake_stat(path):
        result = real_stat(path)
        if path == (Path("/usr") if ancestor else Path("/usr/bin/true").resolve()):
            fields = list(result)
            fields[0] = int(fields[0]) | 0o020
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(Path, "lstat", fake_stat)
    monkeypatch.setitem(probe.EXECUTABLES, "ubuntu", frozenset({"/usr/bin/true"}))
    popen = Mock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    assert probe.run_probe("ubuntu", ("/usr/bin/true",), deadline=time.monotonic() + 1).reason == (
        "untrusted_executable"
    )
    popen.assert_not_called()


def test_file_confinement_and_symlinks(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"private")
    link = allowed / "record"
    link.symlink_to(outside)
    assert probe.read_file(link, prefix=allowed).reason == "ambiguous_config"
    assert probe.read_file(outside, prefix=allowed).reason == "ambiguous_config"
    link.unlink()
    link.symlink_to(allowed / "regular")
    (allowed / "regular").write_bytes(b"ok")
    assert probe.read_file(link, prefix=allowed).reason == "ambiguous_config"


def test_fifo_never_opened(tmp_path, monkeypatch):
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    original = os.open

    def checked_open(path, flags, *args, **kwargs):
        assert path != "fifo", "FIFO reached open"
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", checked_open)
    assert probe.read_file(fifo, prefix=tmp_path).reason == "ambiguous_config"


def test_regular_file_and_cap(tmp_path):
    record = tmp_path / "record"
    record.write_bytes(b"12345")
    assert probe.read_file(record, prefix=tmp_path, byte_cap=5).data == b"12345"
    result = probe.read_file(record, prefix=tmp_path, byte_cap=4)
    assert result.reason == "probe_error"
    assert result.data == b""


def test_timeout(monkeypatch, root_owned):
    monkeypatch.setitem(probe.EXECUTABLES, "ubuntu", frozenset({"/usr/bin/sleep"}))
    result = probe.run_probe("ubuntu", ("/usr/bin/sleep", "1"), deadline=time.monotonic() + 0.02)
    assert result.reason == "probe_timeout"


def test_fixed_environment(monkeypatch, root_owned):
    monkeypatch.setenv("MACHINE_PROBE_SECRET_TEST", "must not inherit")
    monkeypatch.setitem(probe.EXECUTABLES, "ubuntu", frozenset({"/usr/bin/env"}))
    result = probe.run_probe("ubuntu", ("/usr/bin/env",), deadline=time.monotonic() + 1)
    assert result.reason is None
    assert result.returncode == 0
    matches_fixed_environment = set(result.data.splitlines()) == {
        b"LC_ALL=C",
        b"PATH=/usr/bin:/bin",
    }
    assert matches_fixed_environment


def test_command_output_cap(monkeypatch, root_owned):
    monkeypatch.setitem(probe.EXECUTABLES, "ubuntu", frozenset({"/usr/bin/yes"}))
    result = probe.run_probe("ubuntu", ("/usr/bin/yes",), deadline=time.monotonic() + 1, byte_cap=8)
    assert result.reason == "probe_error"
    assert result.data == b""


def test_display_is_inert():
    value = probe.display_text("admin\x1b[31m\r\n[link=https://example.org]name[/link]\x07")
    assert "\x1b" not in value
    assert all(c.isprintable() for c in value)
    assert "\\[link=" in value
    assert len(probe.display_text("a" * 300)) == 200


def test_static_probe_contract():
    tree = ast.parse(Path(probe.__file__).read_text())
    forbidden = {"sudo", "pkexec", "doas", "su"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value not in forbidden
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "shell":
                    assert isinstance(keyword.value, ast.Constant)
                    assert keyword.value.value is False
    for paths in probe.EXECUTABLES.values():
        assert all(Path(path).is_absolute() for path in paths)
        assert all(Path(path).name not in forbidden for path in paths)


def test_trusted_file_requires_root(monkeypatch, root_owned):
    original = Path.lstat

    def nonroot(path):
        fields = list(original(path))
        if path == Path("/usr"):
            fields[4] = 1000
        return os.stat_result(fields)

    monkeypatch.setattr(Path, "lstat", nonroot)
    assert not probe._trusted_executable(Path("/usr/bin/true"))


def test_user_runtime_environment(monkeypatch, root_owned):
    captured = {}

    def capture(*args, **kwargs):
        captured.update(kwargs)
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "Popen", capture)
    monkeypatch.setattr(probe, "_trusted_executable", lambda path: True)
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/untrusted")
    probe.run_probe(
        "ubuntu", ("/usr/bin/systemctl", "--user", "show"), deadline=time.monotonic() + 1
    )
    assert captured["env"] == {
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}",
    }


def test_absolute_executable_ignores_path(tmp_path, monkeypatch, root_owned):
    binary = tmp_path / "true"
    binary.write_text("#!/bin/sh\nexit 99\n")
    binary.chmod(0o777)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setitem(probe.EXECUTABLES, "ubuntu", frozenset({"/usr/bin/true"}))
    result = probe.run_probe("ubuntu", ("/usr/bin/true",), deadline=time.monotonic() + 1)
    assert result.reason is None
    assert result.returncode == 0
