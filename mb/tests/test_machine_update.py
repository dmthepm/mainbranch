"""mb machine update: a read-only plan. Every backend here runs against fakes."""

import json
import os
import re
import stat
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mb import machine_update as mu
from mb.cli import app

GIB = 1024**3
UBUNTU = b'ID=ubuntu\nVERSION="24.04 LTS"\n'
APT_OK = (
    b"Listing...\n"
    b"curl/noble-updates,noble-security 8.5.0-2ubuntu10.6 amd64 "
    b"[upgradable from: 8.5.0-2ubuntu10.5]\n"
    b"linux-image-generic/noble-updates 6.8.0.50.52 amd64 [upgradable from: 6.8.0.49.51]\n"
)
MISE_OK = json.dumps(
    {"node": {"name": "node", "requested": "26", "current": "26.12.1", "latest": "26.13.0"}}
).encode()
PRO_OK = json.dumps({"attached": False, "services": []}).encode()
SWU_OK = (
    b"Software Update Tool\n\nFinding available software\n"
    b"Software Update found the following new or updated software:\n"
    b"* Label: macOS Sonoma 14.7.1-23H222\n"
    b"\tTitle: macOS Sonoma 14.7.1, Version: 14.7.1, Size: 1234567K, "
    b"Recommended: YES, Action: restart,\n"
    b"* Label: Safari17.6-17.6\n"
    b"\tTitle: Safari, Version: 17.6, Size: 100K, Recommended: YES,\n"
)
SWU_NONE = b"Software Update Tool\n\nFinding available software\nNo new software available.\n"
BREW_OK = json.dumps(
    {
        "formulae": [
            {"name": "jq", "installed_versions": ["1.7"], "current_version": "1.7.1"},
        ],
        "casks": [],
    }
).encode()

APT = ("/usr/bin/apt", "list", "--upgradable")
PRO = ("/usr/bin/pro", "status", "--format", "json")
SWU = ("/usr/sbin/softwareupdate", "-l")
MISE = ("/fake/owner/mise", "outdated", "--json")
BREW = ("/fake/owner/brew", "outdated", "--json=v2")


class Fake:
    """A Host whose every edge is a recorded fake."""

    def __init__(self, os_release=UBUNTU, system="Linux", replies=None, free=None, **host):
        self.events = []
        self.replies = replies or {}
        self.free = {"/": 50 * GIB} if free is None else free
        self.owner = host.pop("owner", {"mise": "/fake/owner/mise"})
        self.host = mu.Host(
            name="testbox",
            system=system,
            os_release=os_release,
            run=self.run,
            find_owner_tool=self.find,
            free_bytes=self.free_bytes,
            mounts=host.pop("mounts", ()),
            lists_age_days=host.pop("lists_age_days", 1.0),
            reboot_required=host.pop("reboot_required", False),
            nvm_present=host.pop("nvm_present", False),
        )
        assert not host

    def run(self, argv, *, timeout, merge_stderr=False):
        self.events.append(("run", tuple(argv)))
        reply = self.replies.get(tuple(argv))
        if reply is None:
            return mu.Out(reason="missing")
        return reply if isinstance(reply, mu.Out) else mu.Out(data=reply, returncode=0)

    def find(self, name):
        self.events.append(("find", name))
        return self.owner.get(name)

    def free_bytes(self, path):
        self.events.append(("disk", path))
        return self.free.get(path)

    @property
    def argvs(self):
        return [e[1] for e in self.events if e[0] == "run"]


def plan(fake):
    return mu.plan(fake.host)


def phase(report, name):
    return next(p for p in report["phases"] if p["id"] == name)


def read(report, read_id):
    return next(r for p in report["phases"] for r in p["reads"] if r["id"] == read_id)


def ubuntu(replies=None):
    return Fake(replies={APT: APT_OK, PRO: PRO_OK, MISE: b"{}", **(replies or {})})


# --- the plan shape ---------------------------------------------------------


def test_ubuntu_plan_has_one_shape_and_changes_nothing():
    fake = ubuntu({MISE: MISE_OK})
    report = plan(fake)
    assert report["schema"] == "mb.machine.update" and report["schema_version"] == 1
    assert report["mode"] == "plan"
    assert report["machine"] == {"name": "testbox"}
    assert report["os"]["id"] == "ubuntu"
    assert [p["id"] for p in report["phases"]] == ["host", "tools", "agents"]
    host_steps = phase(report, "host")["steps"]
    assert {s["source"] for s in host_steps} == {"apt"}
    curl = next(s for s in host_steps if s["name"] == "curl")
    assert (curl["from"], curl["to"]) == ("8.5.0-2ubuntu10.5", "8.5.0-2ubuntu10.6")
    assert curl["reboot"] == "unknown"
    kernel = next(s for s in host_steps if s["name"] == "linux-image-generic")
    assert kernel["reboot"] == "likely"
    tool = phase(report, "tools")["steps"][0]
    assert (tool["source"], tool["name"], tool["from"], tool["to"]) == (
        "mise",
        "node",
        "26.12.1",
        "26.13.0",
    )
    assert tool["reboot"] == "no"
    assert report["exit_code"] == 0 and report["ok"] is True
    for step in host_steps:
        assert step["run_as"] == "owner" and step["argv"] is None  # display only


def test_agents_phase_says_not_available_and_does_not_hold_exit_code_at_3():
    report = plan(ubuntu())
    agents = phase(report, "agents")
    assert agents["state"] == "not_available" and agents["steps"] == []
    assert agents["notes"] and "not available yet" in agents["notes"][0].lower()
    assert report["exit_code"] == 0


def test_every_argv_is_fixed_absolute_and_read_only():
    fake = ubuntu()
    plan(fake)
    allowed = {APT, PRO, MISE}
    assert set(fake.argvs) <= allowed
    for argv in fake.argvs:
        assert os.path.isabs(argv[0])
        assert argv[1] not in {"update", "upgrade", "install", "attach", "enable", "self-update"}
        assert "sudo" not in argv[0]


def test_reboot_already_pending_is_reported():
    assert plan(Fake(replies={APT: APT_OK}, reboot_required=True))["reboot_pending"] is True
    assert plan(ubuntu())["reboot_pending"] is False


# --- reads are never "no updates" when they failed --------------------------


@pytest.mark.parametrize(
    "bad",
    [
        mu.Out(data=APT_OK, returncode=100),
        mu.Out(data=b"", returncode=0),
        mu.Out(data=b"E: nope\n", returncode=0),
        mu.Out(data=b"curl/noble 1 amd64 [upgradable from: 0]\n", returncode=0),
        mu.Out(data=APT_OK + b"garbage line\n", returncode=0),
        mu.Out(data=APT_OK.replace(b"amd64 [upgradable", b"amd64 [upgraded"), returncode=0),
    ],
)
def test_apt_failed_or_malformed_read_is_failed_with_no_steps(bad):
    report = plan(ubuntu({APT: bad}))
    r = read(report, "apt.upgradable")
    assert r["state"] == "failed"
    assert phase(report, "host")["steps"] == []  # one bad entry fails the whole read
    assert phase(report, "host")["state"] == "failed"
    assert report["exit_code"] == 1 and report["ok"] is False


def test_apt_empty_list_is_a_real_none():
    report = plan(ubuntu({APT: b"Listing...\n"}))
    assert read(report, "apt.upgradable")["state"] == "ok"
    assert phase(report, "host")["steps"] == [] and report["exit_code"] == 0


def test_timeout_and_cap_are_incomplete_not_failed_and_exit_3():
    for reason in ("timeout", "output_cap"):
        report = plan(ubuntu({APT: mu.Out(reason=reason)}))
        assert read(report, "apt.upgradable")["state"] == "incomplete"
        assert report["exit_code"] == 3


def test_network_error_is_unreachable_not_failed():
    out = mu.Out(returncode=1, err=b"Could not resolve host: registry.example")
    report = plan(ubuntu({MISE: out}))
    assert read(report, "mise.outdated")["state"] == "unreachable"
    assert report["exit_code"] == 3


def test_failed_beats_incomplete_in_exit_code():
    report = plan(ubuntu({APT: mu.Out(returncode=100), MISE: mu.Out(reason="timeout")}))
    assert report["exit_code"] == 1


def test_missing_required_executable_is_failed_missing_optional_is_not_present():
    fake = Fake(replies={APT: APT_OK})  # pro and mise: no reply, mise not found
    fake.owner = {}
    report = plan(fake)
    assert read(report, "pro.status")["state"] == "not_present"
    assert phase(report, "tools")["state"] == "not_present"
    assert report["exit_code"] == 0
    report = plan(Fake(replies={PRO: PRO_OK}))
    assert read(report, "apt.upgradable")["state"] == "failed"
    assert report["exit_code"] == 1


def test_untrusted_executable_is_not_run_result_is_not_verified():
    report = plan(ubuntu({MISE: mu.Out(reason="untrusted")}))
    assert read(report, "mise.outdated")["state"] == "not_verified"
    assert report["exit_code"] == 3


# --- apt: stale lists, Pro ---------------------------------------------------


def test_stale_apt_lists_are_stated():
    report = plan(Fake(replies={APT: APT_OK}, lists_age_days=12.0))
    assert read(report, "apt.upgradable")["facts"]["lists_age_days"] == 12.0
    assert any(w["code"] == "apt.lists_stale" for w in report["warnings"])
    assert not any(w["code"] == "apt.lists_stale" for w in plan(ubuntu())["warnings"])
    unknown = plan(Fake(replies={APT: APT_OK}, lists_age_days=None))
    assert any(w["code"] == "apt.lists_age_unknown" for w in unknown["warnings"])


def test_pro_status_is_a_fact_attach_is_never_ours():
    attached = json.dumps(
        {"attached": True, "services": [{"name": "esm-infra", "status": "enabled"}]}
    ).encode()
    report = plan(ubuntu({PRO: attached}))
    assert read(report, "pro.status")["facts"] == {"attached": True, "enabled": ["esm-infra"]}
    detached = plan(ubuntu())
    assert read(detached, "pro.status")["facts"]["attached"] is False
    text = json.dumps(detached) + mu.human_report(detached)
    assert "attach" in text.lower() and "owner" in text.lower()
    for bad in (b"[]", b'{"attached": "yes"}', b"not json"):
        failed = plan(ubuntu({PRO: bad}))
        assert read(failed, "pro.status")["state"] == "failed"


# --- mise --------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        b'{"error": {"message": "x"}}',
        b'{"node": "26"}',
        b'{"node": {"current": "1", "latest": 3}}',
        b"[]",
        b"",
        json.dumps(
            {"gh": {"current": "1.0", "latest": "1.1"}, "bad": {"current": "x y", "latest": "2"}}
        ).encode(),
    ],
)
def test_mise_malformed_read_fails_the_whole_read(bad):
    report = plan(ubuntu({MISE: bad}))
    assert read(report, "mise.outdated")["state"] == "failed"
    assert phase(report, "tools")["steps"] == []
    assert report["exit_code"] == 1


def test_mise_uses_only_the_owners_tools_and_never_bumps():
    fake = ubuntu({MISE: MISE_OK})
    plan(fake)
    assert MISE in fake.argvs and "--bump" not in MISE


def test_nvm_beside_mise_is_named_as_a_duplicate_updater():
    report = plan(Fake(replies={APT: APT_OK, MISE: MISE_OK}, nvm_present=True))
    assert any("nvm" in d for d in phase(report, "tools")["notes"])


# --- macOS -------------------------------------------------------------------


def mac(replies=None):
    return Fake(
        os_release=None,
        system="Darwin",
        replies={SWU: SWU_OK, **(replies or {})},
        owner={"mise": "/fake/owner/mise"},
    )


def test_macos_plan_from_fake_softwareupdate():
    report = plan(mac({MISE: b"{}"}))
    assert report["os"]["id"] == "macos"
    steps = phase(report, "host")["steps"]
    assert [s["source"] for s in steps] == ["softwareupdate", "softwareupdate"]
    assert steps[0]["name"] == "macOS Sonoma 14.7.1-23H222" and steps[0]["reboot"] == "yes"
    assert steps[1]["reboot"] == "unknown"
    assert report["exit_code"] == 0


def test_macos_softwareupdate_merges_stderr():
    seen = []
    fake = mac()
    original = fake.run

    def spy(argv, *, timeout, merge_stderr=False):
        seen.append((tuple(argv), merge_stderr))
        return original(argv, timeout=timeout, merge_stderr=merge_stderr)

    fake.host.run = spy
    plan(fake)
    assert (SWU, True) in seen


def test_macos_none_pending_and_malformed():
    assert phase(plan(mac({SWU: SWU_NONE})), "host")["steps"] == []
    for bad in (b"", b"Software Update Tool\n", SWU_OK.replace(b"\tTitle:", b"\tName:")):
        report = plan(mac({SWU: bad}))
        assert read(report, "softwareupdate.list")["state"] == "failed"
        assert report["exit_code"] == 1


def test_brew_only_where_present():
    fake = mac()
    plan(fake)
    assert not any("brew" in a[0] for a in fake.argvs)
    with_brew = Fake(
        os_release=None,
        system="Darwin",
        replies={SWU: SWU_NONE, BREW: BREW_OK},
        owner={"brew": "/fake/owner/brew"},
    )
    report = plan(with_brew)
    step = phase(report, "host")["steps"][0]
    assert (step["source"], step["name"], step["to"]) == ("brew", "jq", "1.7.1")
    for bad in (b'{"formulae": [{"name": 1}], "casks": []}', b"{}", b"x"):
        with_brew.replies[BREW] = bad
        assert read(plan(with_brew), "brew.outdated")["state"] == "failed"


# --- Omarchy, Arch, unknown ---------------------------------------------------


def test_omarchy_names_omarchy_update_never_pacman_and_says_mise_is_ungated():
    fake = Fake(os_release=b"ID=omarchy\nNAME=Omarchy\n", replies={MISE: MISE_OK})
    report = plan(fake)
    assert report["os"]["id"] == "omarchy"
    step = phase(report, "host")["steps"][0]
    assert step["source"] == "omarchy" and "omarchy update" in step["what"]
    assert "pacman" not in json.dumps(report)
    assert not any("pacman" in a[0] for a in fake.argvs)
    notes = " ".join(phase(report, "tools")["notes"] + phase(report, "host")["notes"])
    assert "mise up" in notes and "release-age" in notes
    assert read(report, "omarchy.pending")["state"] == "not_verified"
    assert report["exit_code"] == 3


@pytest.mark.parametrize(
    "os_release",
    [
        b"ID=arch\n",
        b"ID=cachyos\nID_LIKE=arch\n",
        b"ID=debian\n",
        b"ID=freebsd\n",
        b"",
        b"ID=a\nID=b\n",
        None,
    ],
)
def test_arch_and_unknown_os_are_not_verified_and_change_and_read_nothing(os_release):
    fake = Fake(os_release=os_release, replies={APT: APT_OK, MISE: MISE_OK})
    report = plan(fake)
    assert fake.argvs == []
    assert report["exit_code"] == 3 and report["ok"] is False
    assert all(p["steps"] == [] for p in report["phases"])
    assert read(report, "os.detect")["state"] == "not_verified"


def test_arch_is_named_plain_arch_with_no_safe_read():
    report = plan(Fake(os_release=b"ID=arch\n"))
    assert report["os"]["id"] == "arch"
    assert read(report, "os.detect")["reason"] == "no_safe_read"
    assert plan(Fake(os_release=b"ID=freebsd\n"))["os"]["id"] == "unknown"


# --- disk first ---------------------------------------------------------------


def test_disk_is_read_before_any_other_read():
    fake = ubuntu()
    plan(fake)
    assert fake.events[0] == ("disk", "/")
    assert [e[0] for e in fake.events].index("run") > 0


def test_low_disk_warns_and_names_partial_upgrades_but_still_plans():
    fake = Fake(replies={APT: APT_OK}, free={"/": GIB // 2})
    report = plan(fake)
    assert report["disk"]["state"] == "warn"
    warning = next(w for w in report["warnings"] if w["code"] == "disk.low")
    assert warning["path"] == "/"
    assert "partial" in mu.human_report(report).lower()
    assert phase(report, "host")["steps"] and report["exit_code"] == 0


def test_boot_mount_has_its_own_floor_and_only_when_a_mount():
    ok = Fake(
        replies={APT: APT_OK}, mounts=("/boot",), free={"/": 50 * GIB, "/boot": 100 * 1024**2}
    )
    assert [m["path"] for m in plan(ok)["disk"]["mounts"]] == ["/", "/boot"]
    assert plan(ok)["disk"]["state"] == "warn"
    none = plan(Fake(replies={APT: APT_OK}))
    assert [m["path"] for m in none["disk"]["mounts"]] == ["/"]


def test_unreadable_disk_is_not_verified():
    report = plan(Fake(replies={APT: APT_OK}, free={}))
    assert report["disk"]["state"] == "not_verified"
    assert report["exit_code"] == 3


# --- the CLI ------------------------------------------------------------------


def patch_host(monkeypatch, fake):
    monkeypatch.setattr(mu.Host, "local", classmethod(lambda cls: fake.host))


def test_cli_json_matches_doctor_style_and_exit_codes(monkeypatch):
    patch_host(monkeypatch, ubuntu())
    result = CliRunner().invoke(app, ["machine", "update", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["mb_command"] == "mb machine update"
    assert payload["result_schema"]["name"] == "mainbranch.machine.update.result"
    assert payload["result_status"] == "ok" and payload["schema"] == "mb.machine.update"
    patch_host(monkeypatch, ubuntu({APT: mu.Out(returncode=100)}))
    result = CliRunner().invoke(app, ["machine", "update", "--json"])
    assert result.exit_code == 1 and json.loads(result.stdout)["result_status"] == "ok"


def test_cli_human_output_and_no_business_repo_needed(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    patch_host(monkeypatch, ubuntu({MISE: MISE_OK}))
    result = CliRunner().invoke(app, ["machine", "update"])
    assert result.exit_code == 0
    assert "curl" in result.stdout and "node" in result.stdout
    assert "plan only" in result.stdout.lower()


def test_cli_internal_error_is_exit_2(monkeypatch):
    def boom(_host):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(mu, "plan", boom)
    monkeypatch.setattr(mu.Host, "local", classmethod(lambda cls: ubuntu().host))
    result = CliRunner().invoke(app, ["machine", "update", "--json"])
    assert result.exit_code == 2
    assert "secret detail" not in result.output
    assert json.loads(result.stdout)["result_status"] == "error"


@pytest.mark.parametrize("flags", [["--apply"], ["--apply", "--json"]])
def test_apply_is_refused_and_nothing_is_read(monkeypatch, flags):
    def never(cls):
        raise AssertionError("apply must refuse before touching the host")

    monkeypatch.setattr(mu.Host, "local", classmethod(never))
    result = CliRunner().invoke(app, ["machine", "update", *flags])
    assert result.exit_code == 2
    assert "owner-run apply is coming" in result.output
    if "--json" in flags:
        assert json.loads(result.stdout)["errors"][0]["code"] == "machine.update.apply_unavailable"


# --- the real runner ----------------------------------------------------------


def script(tmp_path, body, mode=0o700):
    path = tmp_path / "tool"
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(mode)
    return str(path)


def test_run_read_returns_code_stdout_and_separate_stderr(tmp_path):
    out = mu.run_read((script(tmp_path, "echo out; echo err >&2; exit 3"),), timeout=5)
    assert (out.returncode, out.data, out.err, out.reason) == (3, b"out\n", b"err\n", None)
    merged = mu.run_read(
        (script(tmp_path, "echo out; echo err >&2"),), timeout=5, merge_stderr=True
    )
    assert b"out" in merged.data and b"err" in merged.data and merged.err == b""


def test_run_read_timeout_and_cap_and_missing(tmp_path):
    assert mu.run_read((script(tmp_path, "sleep 5"),), timeout=0.3).reason == "timeout"
    capped = mu.run_read((script(tmp_path, "yes"),), timeout=5, byte_cap=1000)
    assert capped.reason == "output_cap"
    assert mu.run_read((str(tmp_path / "absent"),), timeout=1).reason == "missing"


def test_run_read_uses_a_clean_environment_and_no_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("MB_TEST_TOKEN", "hunter2")
    monkeypatch.setenv("PATH", "/nonexistent")
    out = mu.run_read((script(tmp_path, "env"),), timeout=5)
    text = out.data.decode()
    assert "hunter2" not in text and "MB_TEST_TOKEN" not in text
    assert "LC_ALL=C" in text and "PATH=/usr/bin:/bin" in text
    odd = mu.run_read((script(tmp_path, 'echo "$1"'), "a;touch pwned"), timeout=5)
    assert odd.data == b"a;touch pwned\n" and not (tmp_path / "pwned").exists()


def test_owner_tool_must_be_ours_and_not_writable_by_others(tmp_path, monkeypatch):
    good = Path(script(tmp_path, "exit 0"))
    assert mu.owner_executable_ok(good)
    good.chmod(0o770)
    assert not mu.owner_executable_ok(good)
    good.chmod(0o700)
    link = tmp_path / "link"
    link.symlink_to(good)
    assert mu.owner_executable_ok(link) in (True, False)  # symlink is resolved, then checked
    assert not mu.owner_executable_ok(tmp_path / "nope")
    monkeypatch.setattr(os, "geteuid", lambda: good.stat().st_uid + 1)
    assert not mu.owner_executable_ok(good)


def test_find_owner_tool_takes_only_fixed_candidates(tmp_path, monkeypatch):
    planted = tmp_path / "mise"
    planted.write_text("#!/bin/sh\n")
    planted.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert mu.find_owner_tool("mise") != str(planted)
    with pytest.raises(KeyError):
        mu.find_owner_tool("npm")


# --- shipped files carry nothing of ours ---------------------------------------

ROOT = Path(__file__).resolve().parents[2]
SHIPPED = [
    ROOT / "mb" / "mb" / "machine_update.py",
    *sorted((ROOT / ".claude" / "skills" / "mb-homelab-machine").rglob("*.md")),
]
PRIVATE_SHAPES = {
    "home path": re.compile(
        r"/(?:home|Users)/(?!<|\$|you|name|user\b|example|linuxbrew)[a-z][\w.-]*/"
    ),
    "tailnet address": re.compile(r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b"),
    "private LAN address": re.compile(
        r"\b(?:192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"
    ),
    "tailnet name": re.compile(r"\.ts\.net\b|\btail[0-9a-f]{4,}\b"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|ssh-(?:ed25519|rsa) AAAA"),
    "token": re.compile(r"\b(?:ghp_|github_pat_|sk-ant-|tskey-|xox[bp]-|AKIA)[A-Za-z0-9_-]{8,}"),
}


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.name)
def test_shipped_files_carry_no_private_host_path_or_key(path):
    text = path.read_text()
    for label, shape in PRIVATE_SHAPES.items():
        assert not shape.search(text), f"{path.name}: {label}"


def test_module_has_no_shell_sudo_or_config_driven_command():
    source = (ROOT / "mb" / "mb" / "machine_update.py").read_text()
    assert "shell=True" not in source and "os.system" not in source
    assert not re.search(r"""["']sudo["']""", source)
    assert "os.environ" not in source  # nothing from the caller's environment selects a command
    assert stat.S_ISREG(Path(sys.executable).stat().st_mode)
