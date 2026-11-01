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
    monkeypatch.setattr(doctor, "registry", lambda _: ())
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


@pytest.mark.parametrize("masked", [True, False])
def test_sleep_targets(monkeypatch, masked):
    run = Mock(return_value=ProbeResult(data=b"masked" if masked else b"enabled", returncode=0))
    monkeypatch.setattr(probe, "run_probe", run)
    reads = doctor.no_sleep("ubuntu", 100)
    assert [r.state for r in reads] == ["pass" if masked else "fail"] * 3
    assert [call.args[1][-1] for call in run.call_args_list] == [
        "sleep.target",
        "suspend.target",
        "hibernate.target",
    ]


@pytest.mark.parametrize("enabled", [True, False])
def test_gdm_autologin(monkeypatch, enabled):
    monkeypatch.setattr(
        probe,
        "read_file",
        lambda *a, **kw: ProbeResult(
            data=f"[daemon]\nAutomaticLoginEnable={str(enabled).lower()}".encode()
        ),
    )
    assert doctor.desktop_ubuntu(100)[0].state == ("fail" if enabled else "pass")


@pytest.mark.parametrize("enabled", [True, False])
def test_arch_autologin(monkeypatch, enabled):
    from pathlib import Path

    monkeypatch.setattr(doctor, "_config_files", lambda pattern: ([Path("/etc/test.conf")], None))
    data = (
        b"[Autologin]\nUser=agent\nExecStart=agetty --autologin agent"
        if enabled
        else b"[Autologin]\nUser=\nExecStart=agetty"
    )
    monkeypatch.setattr(probe, "read_file", lambda *a, **kw: ProbeResult(data=data))
    assert [r.state for r in doctor.desktop_arch(100)] == ["fail" if enabled else "pass"] * 2


@pytest.mark.parametrize(
    "suffix,state,reason",
    [
        ("", "pass", None),
        ("PasswordAuthentication yes", "not_verified", "ambiguous_config"),
        ("Match User agent", "not_verified", "ambiguous_config"),
        ("Include /tmp/config", "not_verified", "ambiguous_config"),
    ],
)
def test_sshd_ambiguous(monkeypatch, suffix, state, reason):
    monkeypatch.setattr(doctor, "_config_files", lambda _: ([], None))
    data = (
        "PasswordAuthentication no\nKbdInteractiveAuthentication no\nPubkeyAuthentication yes\n"
        + suffix
    ).encode()
    monkeypatch.setattr(probe, "read_file", lambda *a, **kw: ProbeResult(data=data))
    read = doctor.sshd_keys(100)[0]
    assert (read.state, read.reason) == (state, reason)


def test_sshd_password_authentication_fails(monkeypatch):
    monkeypatch.setattr(doctor, "_config_files", lambda _: ([], None))
    monkeypatch.setattr(
        probe,
        "read_file",
        lambda *a, **kw: ProbeResult(
            data=(
                b"PasswordAuthentication yes\nKbdInteractiveAuthentication no\n"
                b"PubkeyAuthentication yes"
            )
        ),
    )
    assert doctor.sshd_keys(100)[0].state == "fail"


@pytest.mark.parametrize(
    "data,code,state",
    [
        (b'{"RunSSH": false}', 0, "pass"),
        (b'{"RunSSH": true}', 0, "fail"),
        (b"denied private data", 1, "not_verified"),
        (b'{"RunSSH": "false"}', 0, "not_verified"),
    ],
)
def test_tailscale_prefs(monkeypatch, data, code, state):
    monkeypatch.setattr(
        probe, "run_probe", lambda *a, **kw: ProbeResult(data=data, returncode=code)
    )
    read = doctor.tailscale_no_ssh("omarchy", 100)[0]
    assert read.state == state
    assert "private" not in str(read.observed)


@pytest.mark.parametrize("ready", [True, False])
def test_store_health_never_reads_secret(monkeypatch, ready):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    from mb.credential_store import SecretStore

    monkeypatch.setattr(
        SecretStore, "__init__", lambda self: setattr(self, "backend", "secret-service")
    )
    health = Mock(return_value={"ok": ready})
    monkeypatch.setattr(SecretStore, "health", health)
    monkeypatch.setattr(SecretStore, "get", Mock(side_effect=AssertionError("secret read")))
    monkeypatch.setattr(SecretStore, "probe", Mock(side_effect=AssertionError("secret read")))
    assert doctor.credential_store(100)[0].state == ("pass" if ready else "fail")
    health.assert_called_once_with(deadline=100)


def test_local_store_never_calls_health(monkeypatch):
    from mb.credential_store import SecretStore

    monkeypatch.setattr(
        SecretStore, "__init__", lambda self: setattr(self, "backend", "local-file")
    )
    monkeypatch.setattr(SecretStore, "health", Mock(side_effect=AssertionError("secret read")))
    assert doctor.credential_store(100)[0].state == "not_verified"


@pytest.mark.parametrize("good", [True, False])
def test_unattended_reads(monkeypatch, good):
    config = (
        b'APT::Periodic::Unattended-Upgrade "1";\n'
        b'Unattended-Upgrade::Automatic-Reboot "false";\n'
        b"Unattended-Upgrade::Allowed-Origins:: "
        b'"${distro_id}:${distro_codename}-security";'
    )
    run = Mock(
        side_effect=[
            ProbeResult(
                data=b"install ok installed" if good else b"deinstall ok config-files", returncode=0
            ),
            ProbeResult(data=config if good else b"", returncode=0),
            ProbeResult(data=b"enabled" if good else b"disabled", returncode=0),
        ]
    )
    monkeypatch.setattr(probe, "run_probe", run)
    assert [r.state for r in doctor.unattended(100)] == ["pass" if good else "fail"] * 3


@pytest.mark.parametrize("arch", [True, False])
@pytest.mark.parametrize("present", [True, False])
def test_reboot_metadata(monkeypatch, arch, present):
    import stat
    from pathlib import Path
    from types import SimpleNamespace

    def metadata(self):
        if not present:
            raise FileNotFoundError
        return SimpleNamespace(st_mode=stat.S_IFDIR if arch else stat.S_IFREG)

    monkeypatch.setattr(Path, "lstat", metadata)
    pending = (not present) if arch else present
    read = doctor.reboot_pending(arch)[0]
    assert read.state == ("warn" if pending else "pass")
    assert read.observed == {"pending": pending}


def test_registry_anchors_and_platforms():
    import re
    from pathlib import Path

    guide = (Path(__file__).resolve().parents[2] / "docs/machine-setup.md").read_text()
    anchors = {
        re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        for heading in re.findall(r"^#{1,6} (.+)$", guide, re.M)
    }
    specs = {spec.id: spec for os_id in ("ubuntu", "omarchy") for spec in doctor.registry(os_id)}
    assert len(specs) == 10
    for os_id in ("ubuntu", "omarchy"):
        ids = [spec.id for spec in doctor.registry(os_id)]
        assert len(ids) == len(set(ids))
    for spec in specs.values():
        assert spec.section.split("#")[1] in anchors
    assert doctor.registry("macos") == ()
    assert doctor.registry("unsupported") == ()
    manifest = specs["manifest.integrity"].run(100)[0]
    assert (manifest.state, manifest.reason) == ("not_verified", "no_manifest")


def test_doctor_routes_supported_checks_without_real_probes(monkeypatch):
    monkeypatch.setattr(
        doctor,
        "detect_platform",
        lambda _: ({"id": "omarchy"}, [doctor.ReadResult("os_release", "pass", {})]),
    )
    for name in (
        "no_sleep",
        "desktop_arch",
        "sshd_keys",
        "tailscale_no_ssh",
        "reboot_pending",
        "credential_store",
    ):
        monkeypatch.setattr(doctor, name, lambda *args: [doctor.ReadResult("fixture", "pass", {})])
    report = doctor.doctor()
    assert len(report["checks"]) == 8
    assert report["exit_code"] == 3
    assert "A systemd or glibc update since boot." in doctor.human_report(report)


@pytest.mark.parametrize("name", ["DISPLAY", "WAYLAND_DISPLAY"])
def test_desktop_store_does_not_prove_headless(monkeypatch, name):
    from mb.credential_store import SecretStore

    monkeypatch.setenv(name, "synthetic")
    monkeypatch.setattr(
        SecretStore, "__init__", lambda self: setattr(self, "backend", "secret-service")
    )
    monkeypatch.setattr(SecretStore, "health", lambda *a, **kw: {"ok": True})
    assert doctor.credential_store(100)[0].state == "not_verified"


@pytest.mark.parametrize("check", [doctor.desktop_ubuntu, doctor.sshd_keys])
def test_config_read_denied_is_unknown(monkeypatch, check):
    monkeypatch.setattr(doctor, "_config_files", lambda _: ([], None))
    monkeypatch.setattr(probe, "read_file", lambda *a, **kw: ProbeResult(reason="probe_error"))
    read = check(100)[0]
    assert (read.state, read.reason, read.observed) == ("not_verified", "probe_error", {})


def test_arch_missing_config_is_unknown(monkeypatch):
    monkeypatch.setattr(doctor, "_config_files", lambda _: ([], None))
    assert [r.state for r in doctor.desktop_arch(100)] == ["not_verified", "not_verified"]


def test_gdm_setting_in_wrong_section_is_unknown(monkeypatch):
    monkeypatch.setattr(
        probe,
        "read_file",
        lambda *a, **kw: ProbeResult(data=b"[wrong]\nAutomaticLoginEnable=false"),
    )
    assert doctor.desktop_ubuntu(100)[0].state == "not_verified"
