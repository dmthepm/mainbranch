"""Machine doctor output and assurance contracts."""

import json
import platform
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from mb import machine_doctor as doctor
from mb import machine_probe as probe
from mb.cli import app
from mb.machine_probe import ProbeResult


@pytest.mark.parametrize(
    "system,data,package,expected,state,reason",
    [
        ("Linux", b'ID=ubuntu\nVERSION="24.04 LTS"', 1, "ubuntu", "pass", None),
        ("Linux", b'ID=ubuntu\nVERSION="24.10"', 1, "ubuntu", "fail", None),
        ("Linux", b"ID=omarchy", 0, "omarchy", "pass", None),
        ("Linux", b"ID=omarchy", 1, "unsupported", "not_verified", "ambiguous_platform"),
        ("Linux", b"ID=arch", 0, "unsupported", "not_verified", "ambiguous_platform"),
        ("Linux", b"ID=arch", 1, "unsupported", "not_verified", "platform_unsupported"),
        ("Linux", b'ID="broken', 1, "unsupported", "not_verified", "ambiguous_config"),
        ("Darwin", b"", 0, "macos", "not_verified", "platform_partial"),
        ("Windows", b"", 1, "unsupported", "not_verified", "platform_unsupported"),
    ],
)
def test_platform_table(monkeypatch, system, data, package, expected, state, reason):
    monkeypatch.setattr(platform, "system", lambda: system)
    monkeypatch.setattr(probe, "read_file", lambda *a, **kw: ProbeResult(data=data))
    monkeypatch.setattr(
        probe, "run_probe", lambda *a, **kw: ProbeResult(data=b"15.0", returncode=package)
    )
    detected, reads = doctor.detect_platform(100)
    assert detected["id"] == expected
    check = doctor.check_result(
        doctor.CheckSpec("host.os-release", "section", lambda _: reads), reads
    )
    assert (check["state"], check["reason"]) == (state, reason)
    if expected == "omarchy":
        assert detected["family"] == "arch"
        assert detected["distribution"] == "omarchy"
        assert [read.name for read in reads] == ["os_release", "pacman_package"]


def test_os_release_symlink_fallback(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    read = Mock(
        side_effect=[
            ProbeResult(reason="ambiguous_config"),
            ProbeResult(data=b'ID=ubuntu\nVERSION="24.04 LTS"'),
        ]
    )
    monkeypatch.setattr(probe, "read_file", read)
    assert doctor.detect_platform(100)[0]["id"] == "ubuntu"
    assert [(str(call.args[0]), str(call.kwargs["prefix"])) for call in read.call_args_list] == [
        ("/etc/os-release", "/etc"),
        ("/usr/lib/os-release", "/usr/lib"),
    ]


@pytest.mark.parametrize("reason", ["probe_missing", "probe_error"])
def test_no_fallback_for_other_errors(monkeypatch, reason):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    read = Mock(return_value=ProbeResult(reason=reason))
    monkeypatch.setattr(probe, "read_file", read)
    assert doctor.detect_platform(100)[1][0].reason == reason
    assert read.call_count == 1


@pytest.mark.parametrize("state", ["not_verified", "attested", "skipped"])
def test_baseline_incomplete(state):
    assert doctor.exit_code([{"state": state, "tier": "baseline"}]) == 3


def test_exit_precedence():
    checks = [{"state": "pass", "tier": "baseline"}]
    assert doctor.exit_code(checks) == 0
    checks += [{"state": "not_verified", "tier": "baseline"}]
    assert doctor.exit_code(checks) == 3
    checks += [{"state": "fail", "tier": "baseline"}]
    assert doctor.exit_code(checks) == 1
    assert doctor.exit_code(checks, error=True) == 2
    assert (
        doctor.exit_code(
            [
                {"state": "warn", "tier": "baseline"},
                {"state": "skipped", "tier": "advanced"},
                {"state": "not_applicable", "tier": "baseline"},
            ]
        )
        == 0
    )


@pytest.mark.parametrize(
    "states,expected",
    [
        (["pass", "fail"], "fail"),
        (["pass", "not_verified"], "not_verified"),
        (["warn", "attested"], "attested"),
        (["pass", "warn"], "warn"),
        (["attested", "not_verified"], "not_verified"),
    ],
)
def test_worst_read_keeps_every_read(states, expected):
    reasons: dict[str, doctor.Reason] = {
        "not_verified": "probe_error",
        "attested": "owner_attested",
        "warn": "no_section",
    }
    reads = [
        doctor.ReadResult(str(i), state, {"parsed": True}, reasons.get(state))
        for i, state in enumerate(states)
    ]
    result = doctor.check_result(doctor.CheckSpec("test", "section", lambda _: reads), reads)
    assert result["state"] == expected
    assert result["reads"] == [
        dict(name=str(i), state=state, observed={"parsed": True}, reason=reasons.get(state))
        for i, state in enumerate(states)
    ]


def test_reasons_closed():
    with pytest.raises(ValueError, match="Unknown"):
        doctor.ReadResult("test", "not_verified", {}, "private/path")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="coded"):
        doctor.ReadResult("test", "not_verified", {})


@pytest.fixture
def supported(monkeypatch):
    monkeypatch.setattr(
        doctor,
        "detect_platform",
        lambda _: (
            {"id": "ubuntu", "family": "ubuntu", "signals": {}},
            [doctor.ReadResult("os_release", "pass", {"lts": True})],
        ),
    )


def test_no_manifest_never_passes(supported):
    report = doctor.doctor()
    assert report["exit_code"] == 3
    assert report["ok"] is False
    assert report["manifest"] == {"source": "none", "reason": "no_manifest"}
    assert [check["id"] for check in report["checks"]] == ["host.os-release"]


def test_json_stdout_only_and_envelope(supported):
    result = CliRunner().invoke(app, ["machine", "doctor", "--json"], input="")
    assert result.exit_code == 3
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["mb_command"] == "mb machine doctor"
    assert payload["result_schema"] == {
        "name": "mainbranch.machine.doctor.result",
        "version": "1.0",
    }
    assert payload["result_envelope_version"] == "1.0"
    assert payload["schema"] == "mb.machine.doctor"
    assert payload["schema_version"] == 1
    assert payload["safe_to_share"] is False
    assert payload["scope"] == "self"
    assert payload["summary"]["pass"] == 1
    assert payload["errors"] == []


def test_human_scope_and_limits(supported):
    result = CliRunner().invoke(app, ["machine", "doctor"], input="")
    assert result.exit_code == 3
    assert "scope self, current account only" in result.stdout
    assert "Does not prove:" in result.stdout
    assert "incomplete" in result.stdout
    assert "healthy" not in result.stdout.lower()


def test_internal_error_has_no_verdict_or_exception_text(monkeypatch):
    def broken():
        raise RuntimeError("private/path")

    monkeypatch.setattr(doctor, "doctor", broken)
    result = CliRunner().invoke(app, ["machine", "doctor", "--json"])
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["checks"] == []
    assert payload["errors"] == [{"code": "machine.internal"}]
    assert payload["result_status"] == "error"
    assert "private/path" not in result.output
