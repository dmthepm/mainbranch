"""Manifest syntax, trust, and policy assurance regressions."""

import copy
import json
import os
import pwd
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from typer.testing import CliRunner

from mb import machine_doctor as doctor
from mb import machine_manifest as manifest
from mb import machine_probe as probe
from mb.cli import app

FIXTURES = Path(__file__).parent / "fixtures/machine-manifest"


def example(name: str = "ubuntu") -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())  # type: ignore[no-any-return]


def altered(path: str, value: Any, name: str = "ubuntu") -> dict[str, Any]:
    data = example(name)
    obj = data
    parts = path.split(".")
    for part in parts[:-1]:
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    obj[parts[-1]] = value
    return data


BAD = [
    altered("extra", True),
    altered("checks", [{"read": "echo unsafe"}]),
    altered("hardening.updates.command", "omarchy update", "omarchy"),
    altered("heavy_work.wrapper", "../wrapper"),
    altered("backups.restore_test.record", "/tmp/restore.json"),
    altered("runtime.session_unit", "../bad.service"),
    altered("checks.skip", [{"id": "unknown.check", "reason": "fixture"}]),
    altered("checks.skip", [{"id": "host.no-sleep", "reason": "\x1b[31m"}]),
    altered("manifest_version", True),
    altered("shared_tools.tools", [{"name": "test", "version": "1", "source": "npm-tarball"}]),
    altered("hardening.updates", {"model": "rolling-manual"}),
    altered("businesses.size_classes", {}),
]


@pytest.mark.parametrize("data", [example(), example("omarchy"), *BAD])
def test_schema_agreement(data: dict[str, Any]) -> None:
    Draft202012Validator.check_schema(manifest.SCHEMA)
    expected = Draft202012Validator(manifest.SCHEMA).is_valid(data)
    try:
        manifest.validate(data)
        actual = True
    except manifest.ManifestError:
        actual = False
    assert actual == expected


def test_unknown_size_class() -> None:
    data = example()
    data["businesses"]["users"][0]["size_class"] = "missing"
    with pytest.raises(manifest.ManifestError, match="size class"):
        manifest.validate(data)


@pytest.mark.parametrize("body", [b'{"a":1,"a":2}', b" " * (manifest.MAX_BYTES + 1), b"NaN"])
def test_parse_rejections(tmp_path: Path, body: bytes) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(body)
    with pytest.raises(manifest.ManifestError):
        manifest.load(path)


def test_cap_before_parse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(b" " * (manifest.MAX_BYTES + 1))
    parse = Mock(side_effect=AssertionError("parse must not run"))
    monkeypatch.setattr(json, "loads", parse)
    with pytest.raises(manifest.ManifestError, match="byte cap"):
        manifest.load(path)
    parse.assert_not_called()


@pytest.mark.parametrize("defect", ["symlink", "owner", "parent"])
def test_default_trust_stops_all_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(example()))
    original_stat = os.stat
    original_fstat = os.fstat

    def root_info(info: os.stat_result, bad: bool = False) -> os.stat_result:
        fields = list(info)
        fields[4] = 1234 if bad and defect == "owner" else 0
        fields[0] = int(fields[0]) & ~0o022
        if bad and defect == "parent":
            fields[0] = int(fields[0]) | 0o020
        return os.stat_result(fields)

    def fake_stat(*args: Any, **kwargs: Any) -> os.stat_result:
        return root_info(original_stat(*args, **kwargs), defect == "owner")

    def fake_fstat(fd: int) -> os.stat_result:
        info = original_fstat(fd)
        return root_info(info, defect == "parent")

    if defect == "symlink":
        link = tmp_path / "link.json"
        link.symlink_to(path)
        path = link
    monkeypatch.setattr(manifest, "DEFAULT_PATH", path)
    monkeypatch.setattr(os, "stat", fake_stat)
    monkeypatch.setattr(os, "fstat", fake_fstat)
    detect = Mock(side_effect=AssertionError("No platform probes after failed trust"))
    monkeypatch.setattr(doctor, "detect_platform", detect)
    report = doctor.doctor()
    assert report["exit_code"] == 1
    assert [(c["id"], c["state"]) for c in report["checks"]] == [("manifest.integrity", "fail")]
    detect.assert_not_called()


def test_caller_selected_never_assures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(example()))
    monkeypatch.setattr(
        doctor,
        "detect_platform",
        lambda _: (
            {"id": "ubuntu", "family": "ubuntu"},
            [doctor.ReadResult("os_release", "pass", {})],
        ),
    )
    monkeypatch.setattr(doctor, "registry", lambda _: ())
    monkeypatch.setattr(doctor, "account_checks", lambda *args: [])
    monkeypatch.setattr(doctor, "tool_checks", lambda *args: [])
    monkeypatch.setattr(doctor, "linux_checks", lambda *args: [])
    report = doctor.doctor(path)
    assert report["exit_code"] == 3
    assert report["manifest"]["source"] == "caller_selected"
    integrity = next(c for c in report["checks"] if c["id"] == "manifest.integrity")
    assert (integrity["state"], integrity["reason"]) == ("not_verified", "caller_selected_policy")
    coverage = next(c for c in report["checks"] if c["id"] == "manifest.coverage")
    assert all(r["state"] == "not_verified" for r in coverage["reads"])
    result = CliRunner().invoke(app, ["machine", "doctor", "--manifest", str(path), "--json"])
    assert result.exit_code == 3
    assert json.loads(result.stdout)["manifest"]["source"] == "caller_selected"


def test_no_manifest_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manifest, "DEFAULT_PATH", tmp_path / "absent.json")
    assert manifest.load() == (None, {"source": "none", "reason": "no_manifest"})


@pytest.mark.parametrize(
    "data",
    [
        *BAD,
        altered(
            "businesses.users", [dict(example()["businesses"]["users"][0], size_class="missing")]
        ),
    ],
)
def test_invalid_manifest_exit_two_no_probes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data: dict[str, Any]
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(copy.deepcopy(data)))
    detect = Mock(side_effect=AssertionError("No probes for invalid policy"))
    monkeypatch.setattr(doctor, "detect_platform", detect)
    report = doctor.doctor(path)
    assert (report["exit_code"], report["checks"]) == (2, [])
    detect.assert_not_called()


def test_data_strings_are_inert() -> None:
    data = example()
    data["backups"]["paths"] = ["$(echo unsafe)", "*.json"]
    data["backups"]["schedule"] = "$(echo unsafe)"
    data["shared_tools"]["tools"][0]["bins"] = ["$(echo unsafe)"]
    manifest.validate(data)


def test_id_inventory_matches_schema() -> None:
    assert (
        set(
            manifest.SCHEMA["properties"]["checks"]["properties"]["skip"]["items"]["properties"][
                "id"
            ]["enum"]
        )
        == manifest.CHECK_IDS
    )


def test_trusted_default_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(example()))
    original_stat = os.stat
    original_fstat = os.fstat

    def trusted_info(info: os.stat_result) -> os.stat_result:
        values = list(info)
        values[0] = int(values[0]) & ~0o022
        values[4] = 0
        return os.stat_result(values)

    monkeypatch.setattr(os, "stat", lambda *a, **kw: trusted_info(original_stat(*a, **kw)))
    monkeypatch.setattr(os, "fstat", lambda fd: trusted_info(original_fstat(fd)))
    monkeypatch.setattr(manifest, "DEFAULT_PATH", path)
    policy, metadata = manifest.load()
    assert policy == example()
    assert metadata["source"] == "default_path"
    assert metadata["manifest_version"] == 1
    assert len(metadata["sha256"]) == 64


def test_symlink_ancestor_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "real"
    directory.mkdir()
    (directory / "manifest.json").write_text(json.dumps(example()))
    link = tmp_path / "alias"
    link.symlink_to(directory, target_is_directory=True)
    with pytest.raises(manifest.ManifestError):
        manifest.load(link / "manifest.json")


def test_fifo_rejected_without_open(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    os.mkfifo(path)
    with pytest.raises(manifest.ManifestError, match="regular file"):
        manifest.load(path)


def test_duplicate_valid_key_rejected(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    body = json.dumps(example())
    path.write_text('{"manifest_version": 1,' + body[1:])
    with pytest.raises(manifest.ManifestError):
        manifest.load(path)


def test_fixed_256kb_cap(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    body = json.dumps(example()).encode()
    path.write_bytes(body + b" " * (256 * 1024 + 1 - len(body)))
    with pytest.raises(manifest.ManifestError, match="byte cap"):
        manifest.load(path)


def test_validator_covers_every_schema_keyword() -> None:
    found: set[str] = set()

    def walk(node: Any, named: bool = False) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                if named:
                    walk(item)
                    continue
                found.add(key)
                walk(item, key in {"properties", "$defs"})
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(manifest.SCHEMA)
    assert found <= manifest.SUPPORTED_KEYWORDS


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("runtime.session_unit", "herdr.service\n"),
        ("checks.skip", [{"id": "host.no-sleep", "reason": "fixture\n"}]),
    ],
)
def test_control_characters_rejected(path: str, value: Any) -> None:
    with pytest.raises(manifest.ManifestError):
        manifest.validate(altered(path, value))


NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)


def attested_policy(
    check_id: str, read: str, *, days: float = 0, answer: str = "yes"
) -> dict[str, Any]:
    data = example()
    data["checks"]["attest"] = [
        {
            "id": check_id,
            "read": read,
            "answer": answer,
            "at": (NOW - timedelta(days=days)).isoformat().replace("+00:00", "Z"),
        }
    ]
    return data


@pytest.mark.parametrize(
    ("answer", "days", "state", "reason"),
    [
        (None, 0, "not_verified", "attestation_missing"),
        ("no", 0, "fail", None),
        ("yes", 0, "attested", "owner_attested"),
        ("yes", 181, "not_verified", "attestation_stale"),
        ("yes", -1, "not_verified", "attestation_stale"),
    ],
)
def test_attestation_table(answer: str | None, days: float, state: str, reason: str | None) -> None:
    data = attested_policy(
        "host.power-on-after-loss", "bios_power_on", days=days, answer=answer or "yes"
    )
    if answer is None:
        data["checks"] = {}
    read = doctor.attestation_reads(data, "host.power-on-after-loss", NOW)[0]
    assert (read.state, read.reason) == (state, reason)


@pytest.mark.parametrize("identity", list(manifest.ATTESTABLE))
def test_each_expiry(identity: tuple[str, str]) -> None:
    check_id, read = identity
    data = attested_policy(check_id, read)
    days = manifest.ATTESTABLE[identity]
    limit = (
        timedelta(days=days)
        if days
        else (
            timedelta(hours=data["backups"]["max_age_hours"])
            if check_id == "backups.fresh"
            else timedelta(days=data["backups"]["restore_test"]["max_age_days"])
        )
    )
    assert doctor.attestation_reads(data, check_id, NOW + limit)[0].state == "attested"
    expired = doctor.attestation_reads(data, check_id, NOW + limit + timedelta(microseconds=1))[0]
    assert expired.state == ("fail" if days is None else "not_verified")


@pytest.mark.parametrize(
    "kind", ["non_attestable", "duplicate", "calendar", "advanced_skip", "advanced_attest"]
)
def test_bad_attestation_stops_probes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    data = attested_policy("host.power-on-after-loss", "bios_power_on")
    entry = data["checks"]["attest"][0]
    if kind == "non_attestable":
        entry["read"] = "automatic_login"
    elif kind == "duplicate":
        data["checks"]["attest"].append({**entry, "answer": "no"})
    elif kind == "calendar":
        entry["at"] = "2026-02-30T00:00:00Z"
    elif kind == "advanced_skip":
        data["checks"] = {"skip": [{"id": "hardening.ipc-isolation", "reason": "fixture"}]}
    else:
        entry["id"] = "hardening.ipc-isolation"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    detect = Mock(side_effect=AssertionError("probe ran"))
    monkeypatch.setattr(doctor, "detect_platform", detect)
    assert doctor.doctor(path)["exit_code"] == 2
    detect.assert_not_called()


def test_skip_prevents_probe_and_preserves_other_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    data = example()
    data["checks"] = {"skip": [{"id": "host.no-sleep", "reason": "owner choice"}]}
    run = Mock(side_effect=AssertionError("skipped probe ran"))
    monkeypatch.setattr(
        doctor, "registry", lambda _: (doctor.CheckSpec("host.no-sleep", "fixture", run),)
    )
    monkeypatch.setattr(doctor, "account_checks", lambda *args: [])
    monkeypatch.setattr(doctor, "tool_checks", lambda *args: [])
    monkeypatch.setattr(doctor, "linux_checks", lambda *args: [])
    results = doctor.policy_checks(data, "ubuntu", 0)
    skipped = next(c for c in results if c["id"] == "host.no-sleep")
    assert skipped["state"] == "skipped"
    assert skipped["reads"][0]["observed"] == {"reason": "owner choice"}
    assert doctor.exit_code([skipped]) == 3
    run.assert_not_called()
    monkeypatch.setattr(manifest, "load", lambda _: (data, {"source": "caller_selected"}))
    monkeypatch.setattr(
        doctor,
        "detect_platform",
        lambda _: ({"id": "ubuntu", "family": "ubuntu"}, [doctor.ReadResult("os", "pass", {})]),
    )
    report = doctor.doctor(Path("fixture"))
    coverage = next(c for c in report["checks"] if c["id"] == "manifest.coverage")
    assert {r["name"] for r in coverage["reads"]} == set(data) - {
        "manifest_version",
        "checks",
        "owner",
        "runtime",
        "shared_tools",
        "heavy_work",
        "backups",
    }
    assert "Skipped: owner choice" in doctor.human_report(report)


def test_stale_age_attestation_table_row() -> None:
    data = attested_policy("backups.fresh", "last_backup", days=10)
    assert doctor.attestation_reads(data, "backups.fresh", NOW)[0].state == "fail"


def test_attested_output_is_never_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    data = attested_policy("host.power-on-after-loss", "bios_power_on")
    data["checks"]["attest"][0]["at"] = (
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    monkeypatch.setattr(doctor, "registry", lambda _: ())
    checks = doctor.policy_checks(data, "ubuntu", 0)
    check = next(c for c in checks if c["id"] == "host.power-on-after-loss")
    assert check["state"] == "attested"
    assert doctor.exit_code([check]) == 3
    report = {"checks": [check], "manifest": {"source": "caller_selected"}, "exit_code": 3}
    assert "NOT VERIFIED (owner attested)" in doctor.human_report(report)


def test_deferred_baseline_skip_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    data = example()
    data["checks"] = {"skip": [{"id": "shared_tools.pins-match", "reason": "fixture"}]}
    monkeypatch.setattr(doctor, "registry", lambda _: ())
    checks = doctor.policy_checks(data, "ubuntu", 0)
    assert next(c for c in checks if c["id"] == "shared_tools.pins-match")["state"] == "skipped"


@pytest.mark.parametrize("good", [True, False])
def test_d7_account_reads(monkeypatch: pytest.MonkeyPatch, good: bool) -> None:
    data = example()
    data["businesses"]["users"] = data["businesses"]["users"][:1]
    user = data["businesses"]["users"][0]
    name, uid = user["user"], user["uid"]
    owner = data["owner"]["user"]
    monkeypatch.setattr(os, "getuid", lambda: uid)
    accounts = {
        name: (uid, 2001, Path("/home/fixture-agent")),
        owner: (1000, 1000, Path("/home/fixture-owner")),
    }
    groups = {"sudo": (27, {owner} if good else {name}), owner: (1000, set())}
    monkeypatch.setattr(doctor, "_accounts", lambda: (accounts, groups, None))
    monkeypatch.setenv("TMPDIR", "/tmp/private-fixture")

    def directory(read: str, path: Path, expected: int) -> doctor.ReadResult:
        return doctor._verdict(read, good, private=good)

    monkeypatch.setattr(doctor, "_directory", directory)
    monkeypatch.setattr(
        Path, "lstat", lambda _: os.stat_result((0o40700, 0, 0, 1, uid, 2001, 0, 0, 0, 0))
    )

    def read_file(path: Path, **kwargs: Any) -> probe.ProbeResult:
        if str(path) == f"/proc/{os.getpid()}/status":
            return probe.ProbeResult(data=b"Umask:\t0077\n" if good else b"Umask:\t0022\n")
        return probe.ProbeResult() if good else probe.ProbeResult(reason="probe_missing")

    monkeypatch.setattr(probe, "read_file", read_file)

    def run_probe(os_id: str, argv: tuple[str, ...], **kwargs: Any) -> probe.ProbeResult:
        # The whole unit Environment can carry credentials: it is never requested.
        assert not any("Environment" in part for part in argv), argv
        body = (
            "UnitFileState="
            + ("enabled" if good else "disabled")
            + "\nActiveState="
            + ("active" if good else "inactive")
            + "\nSlice="
            + ("background.slice" if good else "app.slice")
        )
        return probe.ProbeResult(data=body.encode(), returncode=0)

    monkeypatch.setattr(probe, "run_probe", run_probe)
    results = doctor.account_checks(data, "ubuntu", 0)
    expected = "pass" if good else "fail"
    reads = {r["name"]: r for c in results for r in c["reads"]}
    for read in (
        "home_private",
        "unprivileged_groups",
        "private_tmpdir",
        "linger",
        "unit_enabled",
        "unit_active",
        "unit_slice",
    ):
        assert reads[read]["state"] == expected, read
    assert reads["autoupdater_disabled"]["state"] == "not_verified"
    assert reads["autoupdater_disabled"]["reason"] == "not_checked"
    if good:
        assert reads["umask"]["state"] == "pass"
    assert "private-fixture" not in json.dumps(results)


def test_s4_updater_never_reads_unit_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    data = example()
    user = data["businesses"]["users"][0]
    data["checks"] = {
        "skip": [
            {"id": s.id, "reason": "fixture"}
            for s in doctor.ACCOUNT_SPECS
            if s.id != "runtime.claude-autoupdate-off"
        ]
    }
    monkeypatch.setattr(os, "getuid", lambda: user["uid"])
    seen: list[tuple[str, ...]] = []

    def run_probe(os_id: str, argv: tuple[str, ...], **kwargs: Any) -> probe.ProbeResult:
        seen.append(argv)
        body = "Environment=SYNTHETIC_API_TOKEN=not-a-secret DISABLE_AUTOUPDATER=1"
        return probe.ProbeResult(data=body.encode(), returncode=0)

    monkeypatch.setattr(probe, "run_probe", run_probe)
    results = doctor.account_checks(data, "ubuntu", 0)
    row = next(c for c in results if c["id"] == "runtime.claude-autoupdate-off")
    assert row["state"] == "not_verified"
    assert not any("Environment" in part for argv in seen for part in argv)
    assert "not-a-secret" not in json.dumps(results) + repr(seen)


def test_d7_denied_and_other_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    data = example()
    monkeypatch.setattr(os, "getuid", lambda: 999)
    monkeypatch.setattr(doctor, "_accounts", lambda: ({}, {}, "probe_error"))
    monkeypatch.setattr(probe, "run_probe", lambda *a, **k: probe.ProbeResult(reason="probe_error"))
    monkeypatch.setattr(probe, "read_file", lambda *a, **k: probe.ProbeResult(reason="probe_error"))
    results = doctor.account_checks(data, "ubuntu", 0, "all")
    assert results
    by_id = {c["id"]: c for c in results}
    assert by_id["businesses.users-and-homes"]["reason"] == "probe_error"
    assert by_id["businesses.no-privileged-groups"]["reason"] == "probe_error"
    assert by_id["owner.no-sudo-into-business"]["reason"] == "attestation_missing"
    assert by_id["runtime.herdr-per-user"]["reason"] == "other_account"


@pytest.mark.parametrize(
    "mode,owner,expected",
    [
        (0o40700, 2001, "pass"),
        (0o40755, 2001, "fail"),
        (0o40700, 1000, "fail"),
        (0o120700, 2001, "not_verified"),
    ],
)
def test_d7_directory_protections(
    monkeypatch: pytest.MonkeyPatch, mode: int, owner: int, expected: str
) -> None:
    monkeypatch.setattr(
        Path, "lstat", lambda _: os.stat_result((mode, 0, 0, 1, owner, 0, 0, 0, 0, 0))
    )
    assert doctor._directory("home", Path("/home/fixture-agent"), 2001).state == expected


def test_d7_directory_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(_: Path) -> Any:
        raise PermissionError

    monkeypatch.setattr(Path, "lstat", denied)
    assert doctor._directory("home", Path("/home/fixture-agent"), 2001).reason == "probe_error"


@pytest.mark.parametrize(
    "text",
    ["bad", "a:x:1:1::relative:/bin/sh", "a:x:1:1::/home/a:/bin/sh\na:x:2:2::/home/b:/bin/sh"],
)
def test_d7b_account_parser_refuses_malformed(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr(doctor, "_text", lambda *a: (text, None))
    assert doctor._accounts() == ({}, {}, "ambiguous_config")


@pytest.mark.parametrize("group", ["bad", "a:x:1:\na:x:2:"])
def test_d7b_group_parser(monkeypatch: pytest.MonkeyPatch, group: str) -> None:
    monkeypatch.setattr(
        doctor,
        "_text",
        lambda path, prefix: ("a:x:1:1::/home/a:/bin/sh" if path.name == "passwd" else group, None),
    )
    assert doctor._accounts()[2] == "ambiguous_config"


def d7b_only(monkeypatch: pytest.MonkeyPatch, check_id: str) -> dict[str, Any]:
    data = example()
    data["businesses"]["users"] = data["businesses"]["users"][:1]
    data["checks"]["skip"] = [
        {"id": spec.id, "reason": "fixture"} for spec in doctor.ACCOUNT_SPECS if spec.id != check_id
    ]
    monkeypatch.setattr(os, "getuid", lambda: data["businesses"]["users"][0]["uid"])
    return data


def test_d7b_all_skipped_reads_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    data = d7b_only(monkeypatch, "none")

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("skipped check read local state")

    monkeypatch.setattr(doctor, "_accounts", forbidden)
    monkeypatch.setattr(probe, "run_probe", forbidden)
    monkeypatch.setattr(probe, "read_file", forbidden)
    monkeypatch.setattr(Path, "lstat", forbidden)
    results = doctor.account_checks(data, "ubuntu", 0, "all")
    assert len(results) == 10
    assert all(c["state"] == "skipped" for c in results)


@pytest.mark.parametrize("member", [True, False])
def test_d7b_owner_membership(monkeypatch: pytest.MonkeyPatch, member: bool) -> None:
    data = d7b_only(monkeypatch, "owner.sudo-needs-password")
    uid = os.getuid()
    owner = data["owner"]["user"]
    monkeypatch.setattr(
        doctor,
        "_accounts",
        lambda: (
            {owner: (uid, 1000, Path("/home/fixture-owner"))},
            {"sudo": (27, {owner} if member else set())},
            None,
        ),
    )
    result = next(
        c
        for c in doctor.account_checks(data, "ubuntu", 0)
        if c["id"] == "owner.sudo-needs-password"
    )
    assert result["reads"][0]["state"] == ("pass" if member else "fail")


@pytest.mark.parametrize(
    "high,ram,state", [(4 * 1024**3, 32, "pass"), (1, 32, "fail"), (4 * 1024**3, 16, "warn")]
)
def test_d7b_slice_limits(monkeypatch: pytest.MonkeyPatch, high: int, ram: int, state: str) -> None:
    data = d7b_only(monkeypatch, "businesses.slice-limits")
    user = data["businesses"]["users"][0]
    limits = data["businesses"]["size_classes"][user["size_class"]]
    limits.update(memory_high="4G", memory_max="6G", tasks_max=4096)
    data["businesses"]["sizing_basis"]["host_ram_gb"] = 32

    def run(platform: str, argv: tuple[str, ...], **kwargs: Any) -> probe.ProbeResult:
        assert argv == (
            "/usr/bin/systemctl",
            "show",
            f"user-{user['uid']}.slice",
            "--property=MemoryHigh",
            "--property=MemoryMax",
            "--property=TasksMax",
        )
        return probe.ProbeResult(
            f"MemoryHigh={high}\nMemoryMax={6 * 1024**3}\nTasksMax=4096\n".encode(), 0
        )

    monkeypatch.setattr(probe, "run_probe", run)
    monkeypatch.setattr(doctor, "_text", lambda *a: (f"MemTotal: {ram * 1024**2} kB\n", None))
    result = next(
        c for c in doctor.account_checks(data, "ubuntu", 0) if c["id"] == "businesses.slice-limits"
    )
    assert result["state"] == state


@pytest.mark.parametrize("value", [None, "relative", "/tmp/../private", "/tmp/symlink/private"])
def test_d7b_tmpdir_boundaries(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    data = d7b_only(monkeypatch, "businesses.private-tmpdir")
    if value is None:
        monkeypatch.delenv("TMPDIR", raising=False)
    else:
        monkeypatch.setenv("TMPDIR", value)
    monkeypatch.setattr(
        Path, "lstat", lambda _: os.stat_result((0o120700, 0, 0, 1, os.getuid(), 0, 0, 0, 0, 0))
    )
    result = next(
        c
        for c in doctor.account_checks(data, "ubuntu", 0)
        if c["id"] == "businesses.private-tmpdir"
    )
    assert result["state"] == ("fail" if value is None else "not_verified")


@pytest.mark.parametrize(
    "body,reason",
    [
        (b"", "probe_error"),
        (
            b"UnitFileState=enabled\nUnitFileState=enabled\nActiveState=active\nSlice=background.slice",
            None,
        ),
    ],
)
def test_d7b_runtime_denied_duplicate(
    monkeypatch: pytest.MonkeyPatch, body: bytes, reason: Any
) -> None:
    data = d7b_only(monkeypatch, "runtime.herdr-per-user")
    monkeypatch.setattr(probe, "run_probe", lambda *a, **k: probe.ProbeResult(body, 0, reason))
    result = next(
        c for c in doctor.account_checks(data, "ubuntu", 0) if c["id"] == "runtime.herdr-per-user"
    )
    assert result["state"] == "not_verified"
    assert result["reason"] == (reason or "ambiguous_config")


def test_d7b_registry_metadata() -> None:
    specs = {s.id: s for s in doctor.registry("ubuntu", include_policy=True)}
    assert set(s.id for s in doctor.ACCOUNT_SPECS) <= manifest.CHECK_IDS
    assert len(specs) == len(doctor.registry("ubuntu", include_policy=True))
    guide = (Path(__file__).resolve().parents[2] / "docs/machine-setup.md").read_text()
    import re

    anchors = {
        re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-")
        for h in re.findall(r"^#{1,6} (.+)$", guide, re.M)
    }
    for spec in (*doctor.ACCOUNT_SPECS, *doctor.TOOL_SPECS):
        assert spec.section.split("#")[1] in anchors
        if spec.run_as == "owner-attests":
            assert spec.fix_text
    assert "Root" in (specs["owner.no-sudo-into-business"].does_not_prove or "")
    assert "sudoers" in (specs["businesses.no-privileged-groups"].does_not_prove or "")


@pytest.mark.parametrize("mismatch,listable", [(True, False), (False, True), (False, False)])
def test_d7b_home_uid_access(
    monkeypatch: pytest.MonkeyPatch, mismatch: bool, listable: bool
) -> None:
    data = d7b_only(monkeypatch, "businesses.users-and-homes")
    user = data["businesses"]["users"][0]
    uid = user["uid"]
    data["businesses"]["users"].append({**user, "user": "fixture-other", "uid": uid + 1})
    accounts = {
        user["user"]: (uid + int(mismatch), uid, Path("/home/fixture-a")),
        "fixture-other": (uid + 1, uid + 1, Path("/home/fixture-b")),
    }
    monkeypatch.setattr(doctor, "_accounts", lambda: (accounts, {}, None))
    monkeypatch.setattr(doctor, "_directory", lambda name, *a: doctor.ReadResult(name, "pass", {}))
    monkeypatch.setattr(doctor, "_text", lambda *a: ("Umask:\t0022\n", None))

    class Directory:
        def __enter__(self) -> None:
            if not listable:
                raise PermissionError

        def __exit__(self, *args: Any) -> None:
            pass

    monkeypatch.setattr(os, "scandir", lambda *a: Directory())
    result = next(
        c
        for c in doctor.account_checks(data, "ubuntu", 0)
        if c["id"] == "businesses.users-and-homes" and c["subject"] == user["user"]
    )
    reads = {r["name"]: r["state"] for r in result["reads"]}
    assert reads["declared_uid"] == ("fail" if mismatch else "pass")
    assert reads["umask"] == "fail"
    assert reads["other_home_unlistable"] == ("fail" if listable else "pass")


def test_d7b_cli_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    from mb import cli

    # Exercise Typer's option routing while keeping machine probes out of CLI fixtures.
    called = []

    def fake(manifest: Any = None, scope: str = "self") -> dict[str, Any]:
        called.append(scope)
        if scope not in {"self", "all"}:
            raise ValueError("Invalid scope")
        return {"exit_code": 3}

    monkeypatch.setattr(doctor, "doctor", fake)
    result = CliRunner().invoke(cli.app, ["machine", "doctor", "--scope", "all", "--json"])
    assert result.exit_code == 3
    assert called == ["all"]
    result = CliRunner().invoke(cli.app, ["machine", "doctor", "--scope", "invalid", "--json"])
    assert result.exit_code == 2


def test_d7b_startup_never_infers_reboot_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    data = d7b_only(monkeypatch, "sessions.started-without-login")
    monkeypatch.setattr(
        probe,
        "run_probe",
        lambda *a, **k: probe.ProbeResult(b"ActiveEnterTimestampMonotonic=123\n", 0),
    )
    result = next(
        c
        for c in doctor.account_checks(data, "ubuntu", 0)
        if c["id"] == "sessions.started-without-login"
    )
    assert result["state"] == "warn"


def d8_only(monkeypatch: pytest.MonkeyPatch, check_id: str) -> dict[str, Any]:
    data = example()
    data["checks"] = {
        "skip": [{"id": s.id, "reason": "fixture"} for s in doctor.TOOL_SPECS if s.id != check_id]
    }
    monkeypatch.setattr(os, "getuid", lambda: data["businesses"]["users"][0]["uid"])
    return data


def d8_result(data: dict[str, Any], check_id: str) -> dict[str, Any]:
    return next(c for c in doctor.tool_checks(data, "ubuntu") if c["id"] == check_id)


def d8_info(mode: int = 0o100755, uid: int = 0, gid: int = 0) -> os.stat_result:
    return os.stat_result((mode, 0, 0, 1, uid, gid, 0, 0, 0, 0))


@pytest.mark.parametrize(
    "mode,uid,gid,state",
    [
        (0o100755, 0, 0, "pass"),
        (0o100775, 0, 0, "fail"),
        (0o100755, 1234, 0, "fail"),
        (0o100755, 0, 1234, "fail"),
        (0o040755, 0, 0, "fail"),
    ],
)
def test_d8_tool_metadata(
    monkeypatch: pytest.MonkeyPatch, mode: int, uid: int, gid: int, state: str
) -> None:
    monkeypatch.setattr(doctor, "_metadata", lambda *a: (d8_info(mode, uid, gid), None))
    assert (
        doctor._tool_metadata("fixture", Path("/opt/tools/bin/x"), Path("/opt/tools")).state
        == state
    )


@pytest.mark.parametrize("error", ["probe_error", "probe_missing", "ambiguous_config"])
def test_d8_metadata_errors(monkeypatch: pytest.MonkeyPatch, error: doctor.Reason) -> None:
    monkeypatch.setattr(doctor, "_metadata", lambda *a: (None, error))
    assert (
        doctor._tool_metadata("fixture", Path("/opt/tools/x"), Path("/opt/tools")).reason == error
    )


def test_d8_metadata_confinement(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("private")
    alias = tmp_path / "alias"
    alias.symlink_to(target)
    assert doctor._metadata(alias, tmp_path)[1] == "ambiguous_config"
    assert doctor._metadata(tmp_path / ".." / "outside", tmp_path)[1] == "ambiguous_config"
    assert doctor._metadata(Path("/outside"), tmp_path)[1] == "ambiguous_config"
    assert doctor._metadata(target, tmp_path)[0] is not None
    parent = tmp_path / "parent"
    parent.symlink_to(tmp_path, target_is_directory=True)
    assert doctor._metadata(parent / "target", tmp_path)[0] is None


def test_d8_metadata_denied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "open", Mock(side_effect=PermissionError))
    assert doctor._metadata(tmp_path / "file", tmp_path)[1] == "probe_error"


@pytest.mark.parametrize("bad", [False, True])
def test_d8_tools_and_pins(monkeypatch: pytest.MonkeyPatch, bad: bool) -> None:
    data = d8_only(monkeypatch, "shared_tools.root-owned-readonly")
    monkeypatch.setattr(
        doctor,
        "_metadata",
        lambda path, *a: (
            d8_info(
                (0o040777 if bad else 0o040755)
                if path.name in ("box-tools", "bin")
                else (0o100777 if bad else 0o100755)
            ),
            None,
        ),
    )
    assert d8_result(data, "shared_tools.root-owned-readonly")["state"] == (
        "fail" if bad else "pass"
    )
    data = d8_only(monkeypatch, "shared_tools.pins-match")
    monkeypatch.setattr(doctor, "_metadata", lambda *a: (d8_info(0o040755), None))
    if bad:
        data["shared_tools"]["tools"][0]["version"] = "LATEST"
    assert d8_result(data, "shared_tools.pins-match")["state"] == ("fail" if bad else "pass")


@pytest.mark.parametrize("field,value", [("version", "../../outside"), ("bins", ["/outside"])])
def test_d8_data_paths_not_expanded(
    monkeypatch: pytest.MonkeyPatch, field: str, value: Any
) -> None:
    check = "shared_tools.pins-match" if field == "version" else "shared_tools.root-owned-readonly"
    data = d8_only(monkeypatch, check)
    data["shared_tools"]["tools"][0][field] = value
    seen = []

    def metadata(path: Path, *a: Any) -> tuple[os.stat_result, None]:
        seen.append(path)
        return d8_info(
            0o040755 if path.name in ("box-tools", "bin") or "installs" in path.parts else 0o100755
        ), None

    monkeypatch.setattr(doctor, "_metadata", metadata)
    assert d8_result(data, check)["state"] == "not_verified"
    assert all(
        ".." not in p.parts and p.is_relative_to(Path(data["labels"]["tool_root"])) for p in seen
    )


@pytest.mark.parametrize("matches", [True, False])
def test_d8_environment(monkeypatch: pytest.MonkeyPatch, matches: bool) -> None:
    for check, variable, expected in (
        ("shared_tools.path-order", "PATH", "/opt/box-tools/bin"),
        ("heavy_work.lock", "HEAVY_LOCK", "/run/box-users/heavy.lock"),
    ):
        data = d8_only(monkeypatch, check)
        monkeypatch.setenv(variable, expected if matches else "/wrong")
        monkeypatch.setattr(doctor, "_metadata", lambda *a: (d8_info(0o100660, gid=2222), None))
        monkeypatch.setattr(doctor, "_accounts", lambda: ({}, {"box-users": (2222, set())}, None))
        reads = d8_result(data, check)["reads"]
        assert reads[-1]["state"] == ("pass" if matches else "fail")
        monkeypatch.setattr(os, "getuid", lambda: 9999)
        assert d8_result(data, check)["reads"][-1]["reason"] == "other_account"


@pytest.mark.parametrize(
    "mode,gid,error,state",
    [
        (0o100660, 2222, None, "pass"),
        (0o100666, 2222, None, "fail"),
        (0o100660, 3333, None, "fail"),
        (0o100660, 2222, "probe_error", "not_verified"),
        (0o100660, 2222, "ambiguous_config", "not_verified"),
    ],
)
def test_d8_lock(
    monkeypatch: pytest.MonkeyPatch, mode: int, gid: int, error: doctor.Reason | None, state: str
) -> None:
    data = d8_only(monkeypatch, "heavy_work.lock")
    monkeypatch.setattr(doctor, "_metadata", lambda *a: (d8_info(mode, gid=gid), error))
    monkeypatch.setattr(doctor, "_accounts", lambda: ({}, {"box-users": (2222, set())}, None))
    assert d8_result(data, "heavy_work.lock")["reads"][0]["state"] == state


def test_d8_wrapper_never_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data = d8_only(monkeypatch, "heavy_work.capped-run")
    root = tmp_path / "tools"
    (root / "bin").mkdir(parents=True)
    marker = tmp_path / "executed"
    wrapper = root / "bin" / "capped-run"
    wrapper.write_text(f"#!/bin/sh\ntouch {marker}\n")
    wrapper.chmod(0o755)
    data["labels"]["tool_root"] = str(root)
    monkeypatch.setattr(probe, "run_probe", Mock(side_effect=AssertionError("execution forbidden")))
    result = d8_result(data, "heavy_work.capped-run")
    assert result["reads"][1]["state"] == "not_verified"
    assert not marker.exists()


@pytest.mark.parametrize(
    "body,state",
    [
        (b'{"date":"2026-11-01","result":"pass","extra":"SECRET_FIXTURE"}', "pass"),
        (b'{"date":"2020-01-01","result":"pass"}', "fail"),
        (b'{"date":"2026-11-01","result":"fail"}', "fail"),
        (b'{"date":"2099-01-01","result":"pass"}', "not_verified"),
        (b'{"date":"2026-02-30","result":"pass"}', "not_verified"),
        (b'{"date":"2026-11-01","result":"SECRET_FIXTURE"}', "not_verified"),
        (b'{"date":"2026-11-01","date":"2020-01-01","result":"pass"}', "not_verified"),
        (b"[]", "not_verified"),
        (b"bad", "not_verified"),
    ],
)
def test_d8_restore_fields(monkeypatch: pytest.MonkeyPatch, body: bytes, state: str) -> None:
    data = d8_only(monkeypatch, "backups.restore-tested")

    def read(path: Path, *, prefix: Path, byte_cap: int, root_owned: bool) -> probe.ProbeResult:
        assert path == Path(data["backups"]["restore_test"]["record"])
        assert prefix == Path("/var/lib") and byte_cap == 4096 and root_owned
        return probe.ProbeResult(body)

    monkeypatch.setattr(probe, "read_file", read)
    result = d8_result(data, "backups.restore-tested")
    assert result["state"] == state
    assert "SECRET_FIXTURE" not in json.dumps(result)
    assert set(result["reads"][0]["observed"]) <= {"date", "result"}


@pytest.mark.parametrize("error", ["probe_error", "probe_missing", "ambiguous_config"])
def test_d8_restore_fallback(monkeypatch: pytest.MonkeyPatch, error: probe.ProbeReason) -> None:
    data = d8_only(monkeypatch, "backups.restore-tested")
    data["checks"]["attest"] = [
        {
            "id": "backups.restore-tested",
            "read": "restore_test_attested",
            "answer": "yes",
            "at": "2026-11-01T00:00:00Z",
        }
    ]
    monkeypatch.setattr(probe, "read_file", lambda *a, **k: probe.ProbeResult(reason=error))
    result = d8_result(data, "backups.restore-tested")
    assert result["reads"][0]["reason"] == error
    assert result["reads"][1]["state"] == "attested"
    assert result["state"] != "pass"


def test_d8_all_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    data = d8_only(monkeypatch, "none")
    monkeypatch.setattr(doctor, "_metadata", Mock(side_effect=AssertionError("skipped read")))
    monkeypatch.setattr(probe, "read_file", Mock(side_effect=AssertionError("skipped read")))
    assert [c["state"] for c in doctor.tool_checks(data, "ubuntu")] == ["skipped"] * 7
    specs = {s.id: s for s in doctor.registry("ubuntu", include_policy=True)}
    for spec in doctor.TOOL_SPECS:
        assert spec.id in manifest.CHECK_IDS and specs[spec.id] == spec
        if spec.run_as == "owner-attests":
            assert spec.fix_text


@pytest.mark.parametrize(
    "check",
    ["shared_tools.root-owned-readonly", "shared_tools.pins-match", "heavy_work.capped-run"],
)
@pytest.mark.parametrize("error", ["probe_error", "ambiguous_config", "probe_missing"])
def test_d8_row_metadata_errors(
    monkeypatch: pytest.MonkeyPatch, check: str, error: doctor.Reason
) -> None:
    data = d8_only(monkeypatch, check)
    monkeypatch.setattr(doctor, "_metadata", lambda *a: (None, error))
    result = d8_result(data, check)
    assert result["state"] == "not_verified"
    assert result["reads"][0]["reason"] == error


@pytest.mark.parametrize(
    "uid,mode,state",
    [(0, 0o100644, None), (1234, 0o100644, "ambiguous_config"), (0, 0o100666, "ambiguous_config")],
)
def test_d8_restore_root_owned_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, uid: int, mode: int, state: str | None
) -> None:
    path = tmp_path / "record.json"
    path.write_text('{"date":"2026-11-01","result":"pass"}')
    monkeypatch.setattr(os, "fstat", lambda fd: d8_info(mode, uid))
    assert probe.read_file(path, prefix=tmp_path, root_owned=True).reason == state


@pytest.mark.parametrize("kind", ["symlink", "fifo", "large"])
def test_d8_restore_unsafe_file(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "record.json"
    if kind == "symlink":
        target = tmp_path / "target"
        target.write_text("SECRET_FIXTURE")
        path.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.write_bytes(b"x" * 4097)
    assert probe.read_file(path, prefix=tmp_path, byte_cap=4096).reason is not None


@pytest.mark.parametrize("missing", [True, False])
def test_d8_backup_age_missing_limit(monkeypatch: pytest.MonkeyPatch, missing: bool) -> None:
    data = d8_only(monkeypatch, "backups.fresh")
    if missing:
        del data["backups"]["max_age_hours"]
    else:
        data["checks"]["attest"] = [
            {
                "id": "backups.fresh",
                "read": "last_backup",
                "answer": "yes",
                "at": "2020-01-01T00:00:00Z",
            }
        ]
    result = d8_result(data, "backups.fresh")
    assert result["state"] == ("not_verified" if missing else "fail")


@pytest.mark.parametrize(
    "kind",
    [
        "good",
        "relative",
        "outside",
        "version",
        "chain",
        "parent-link",
        "writable",
        "owner",
        "target-owner",
        "link-owner",
        "parent-write",
        "denied",
    ],
)
def test_d9_bin_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    root = tmp_path / "tools"
    (root / "bin").mkdir(parents=True)
    install = root / "installs" / "demo" / "1.2.3"
    install.mkdir(parents=True)
    target = install / "demo"
    target.write_text("never executed")
    target.chmod(0o755)
    link = root / "bin" / "demo"
    destination = str(target)
    if kind == "relative":
        destination = "../installs/demo/1.2.3/demo"
    elif kind == "outside":
        destination = str(tmp_path / "outside")
    elif kind == "version":
        destination = str(root / "installs" / "demo" / "9.9.9" / "demo")
    elif kind == "chain":
        alias = install / "alias"
        alias.symlink_to(target)
        destination = str(alias)
    elif kind == "parent-link":
        alias = install / "alias"
        alias.symlink_to(install, target_is_directory=True)
        destination = str(alias / "demo")
    link.symlink_to(destination)
    real_fstat, real_stat = os.fstat, os.stat

    # Synthetic root ownership also makes this test independent of runner uid
    # and /tmp's world-writable mode. The descriptor traversal remains real.
    def trusted_fstat(fd: int) -> os.stat_result:
        info = real_fstat(fd)
        return d8_info(
            stat.S_IFMT(info.st_mode) | (0o777 if kind == "parent-write" else 0o755),
            1234 if kind == "owner" else 0,
        )

    def trusted_stat(*args: Any, **kwargs: Any) -> os.stat_result:
        info = real_stat(*args, **kwargs)
        mode = stat.S_IFMT(info.st_mode) | (0o777 if kind == "writable" else 0o755)
        uid = (
            1234
            if (kind == "target-owner" and stat.S_ISREG(info.st_mode))
            or (kind == "link-owner" and stat.S_ISLNK(info.st_mode))
            else 0
        )
        return d8_info(mode, uid)

    monkeypatch.setattr(os, "fstat", trusted_fstat)
    monkeypatch.setattr(os, "stat", trusted_stat)
    if kind == "denied":
        monkeypatch.setattr(os, "readlink", Mock(side_effect=PermissionError))
    monkeypatch.setattr(probe, "run_probe", Mock(side_effect=AssertionError("execution forbidden")))
    result = doctor._tool_bin("bin", link, root, {"name": "demo", "version": "1.2.3"})
    assert result.state == (
        "pass"
        if kind == "good"
        else "fail"
        if kind in {"chain", "writable", "target-owner"}
        else "not_verified"
    )


@pytest.mark.parametrize("kind", ["good", "owner", "writable", "file-owner", "file-writable"])
@pytest.mark.parametrize("target", ["bin", "root", "pin"])
def test_s4_regular_tool_ancestors_must_be_root_owned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, target: str
) -> None:
    # Only the installer's root ownership is modeled; descriptors, paths and modes are real.
    agent = tmp_path / "agent-dir"
    root = agent / "tools"
    pin = root / "installs" / "demo" / "1.2.3"
    for directory in (root / "bin", pin):
        directory.mkdir(parents=True)
    binary = root / "bin" / "demo"
    binary.write_text("synthetic")
    for item in (agent, *agent.rglob("*")):
        item.chmod(0o755)
    paths = {"bin": binary, "root": root, "pin": pin}
    path = paths[target]
    agent_inode = agent.stat().st_ino
    leaf_inode = path.stat().st_ino
    real_fstat, real_stat = os.fstat, os.stat

    def shaped(info: os.stat_result) -> os.stat_result:
        if kind in {"owner", "writable"} and info.st_ino == agent_inode:
            mode = stat.S_IMODE(info.st_mode) | (0o022 if kind == "writable" else 0)
            return d8_info(stat.S_IFMT(info.st_mode) | mode, 1234 if kind == "owner" else 0)
        if kind.startswith("file-") and info.st_ino == leaf_inode:
            mode = stat.S_IMODE(info.st_mode) | (0o022 if kind == "file-writable" else 0)
            return d8_info(
                stat.S_IFMT(info.st_mode) | mode, 1234 if kind == "file-owner" else 0
            )
        return d8_info(stat.S_IFMT(info.st_mode) | 0o755)

    monkeypatch.setattr(os, "fstat", lambda fd: shaped(real_fstat(fd)))
    monkeypatch.setattr(os, "stat", lambda *a, **k: shaped(real_stat(*a, **k)))
    monkeypatch.setattr(probe, "run_probe", Mock(side_effect=AssertionError("execution forbidden")))
    tool = {"name": "demo", "version": "1.2.3"}
    if target == "bin":
        result = doctor._tool_bin("fixture", path, root, tool, root / "installs")
    else:
        result = doctor._tool_metadata("fixture", path, root, directory=target != "bin")
    assert result.state == ("pass" if kind == "good" else "fail")


@pytest.mark.parametrize(
    "body,expected",
    [
        (b'{"blockdevices":[{"type":"crypt","mountpoints":["/"]}]}', True),
        (
            b'{"blockdevices":[{"type":"crypt","mountpoints":[null],"children":[{"type":"lvm","mountpoints":["/"]}]}]}',
            True,
        ),
        (
            b'{"blockdevices":[{"type":"part","mountpoints":["/"]},{"type":"crypt","mountpoints":["/data"]}]}',
            False,
        ),
        (b'{"blockdevices":[{"type":"crypt","mountpoints":["/data"]}]}', None),
        (b'{"blockdevices":[{"type":"crypt","mountpoints":"/"}]}', None),
        (b'{"blockdevices":null}', None),
        (b"[]", None),
        (b"bad", None),
    ],
)
def test_d9_root_chain(body: bytes, expected: bool | None) -> None:
    assert doctor._root_encrypted(body) is expected


def d9_row(data: dict[str, Any], check: str, os_id: str = "ubuntu") -> dict[str, Any]:
    data["checks"] = {
        "skip": [
            {"id": spec.id, "reason": "fixture"} for spec in doctor.LINUX_SPECS if spec.id != check
        ]
    }
    return next(c for c in doctor.linux_checks(data, os_id, 999999999) if c["id"] == check)


@pytest.mark.parametrize(
    "case,state",
    [("pass", "pass"), ("fail", "fail"), ("denied", "not_verified"), ("malformed", "not_verified")],
)
def test_d9_firewall(monkeypatch: pytest.MonkeyPatch, case: str, state: str) -> None:
    data = example()
    data["hardening"]["firewall"]["tool"] = "ufw"

    def text(path: Path, prefix: Path) -> tuple[str, doctor.Reason | None]:
        if case == "denied":
            return "", "probe_error"
        if case == "malformed":
            return (
                "ENABLED=yes\nENABLED=no\nDEFAULT_INPUT_POLICY=DROP\nDEFAULT_INPUT_POLICY=ACCEPT",
                None,
            )
        if path.name == "ufw.conf":
            return "ENABLED=" + ("no" if case == "fail" else "yes"), None
        return 'DEFAULT_INPUT_POLICY="DROP"', None

    monkeypatch.setattr(doctor, "_text", text)
    row = d9_row(data, "hardening.firewall-default-deny")
    assert row["state"] == state
    assert len(row["reads"]) == 2


@pytest.mark.parametrize(
    "case,state",
    [("pass", "pass"), ("fail", "fail"), ("denied", "not_verified"), ("malformed", "not_verified")],
)
def test_d9_aur(monkeypatch: pytest.MonkeyPatch, case: str, state: str) -> None:
    data = example("omarchy")
    data["hardening"]["updates"]["aur_packages_reviewed"] = ["demo"]

    def run(os_id: str, argv: tuple[str, ...], **kwargs: Any) -> probe.ProbeResult:
        assert os_id == "omarchy" and argv == ("/usr/bin/pacman", "-Qm")
        if case == "denied":
            return probe.ProbeResult(reason="probe_error")
        return probe.ProbeResult(
            {"pass": b"demo 1.2.3\n", "fail": b"unknown 1.2.3\n", "malformed": b"bad line extra"}[
                case
            ],
            0,
        )

    monkeypatch.setattr(probe, "run_probe", run)
    row = d9_row(data, "hardening.aur-reviewed", "omarchy")
    assert row["state"] == state
    assert "unknown" not in json.dumps(row)


@pytest.mark.parametrize(
    "case,state",
    [("pass", "pass"), ("fail", "fail"), ("denied", "not_verified"), ("malformed", "not_verified")],
)
def test_d9_disk_reads(monkeypatch: pytest.MonkeyPatch, case: str, state: str) -> None:
    data = example("omarchy")
    data["host"]["disk"].update(encryption="luks2-passphrase", unattended_boot=False)

    def run(os_id: str, argv: tuple[str, ...], **kwargs: Any) -> probe.ProbeResult:
        assert argv == ("/usr/bin/lsblk", "--json", "--output", "TYPE,MOUNTPOINTS")
        if case == "denied":
            return probe.ProbeResult(reason="probe_error")
        body = (
            b"bad"
            if case == "malformed"
            else json.dumps(
                {
                    "blockdevices": [
                        {"type": "part" if case == "fail" else "crypt", "mountpoints": ["/"]}
                    ]
                }
            ).encode()
        )
        return probe.ProbeResult(body, 0)

    monkeypatch.setattr(probe, "run_probe", run)
    row = d9_row(data, "host.disk-luks2-tpm-arch", "omarchy")
    assert row["reads"][0]["state"] == state
    assert row["state"] != "pass"
    assert row["reads"][-2]["reason"] == "needs_root"


def test_d9_skip_and_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    data = example()
    data["checks"] = {"skip": [{"id": spec.id, "reason": "fixture"} for spec in doctor.LINUX_SPECS]}
    monkeypatch.setattr(probe, "run_probe", Mock(side_effect=AssertionError("skipped probe")))
    monkeypatch.setattr(doctor, "_text", Mock(side_effect=AssertionError("skipped read")))
    for os_id in ("ubuntu", "omarchy"):
        assert all(c["state"] == "skipped" for c in doctor.linux_checks(data, os_id, 999999999))
        specs = doctor.registry(os_id, include_policy=True)
        assert len({s.id for s in specs}) == len(specs)
        for spec in doctor.LINUX_SPECS:
            assert spec.id in manifest.CHECK_IDS
            if spec.run_as == "owner-attests":
                assert spec.fix_text


@pytest.mark.parametrize("value", ['"DROP', "DROP extra", "DROP;true", "$(ignored)"])
def test_d9_firewall_values_are_data(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    data = example()
    data["hardening"]["firewall"]["tool"] = "ufw"
    monkeypatch.setattr(
        doctor,
        "_text",
        lambda path, prefix: (
            "ENABLED=yes" if path.name == "ufw.conf" else "DEFAULT_INPUT_POLICY=" + value,
            None,
        ),
    )
    assert d9_row(data, "hardening.firewall-default-deny")["state"] != "pass"


def test_d9_mise_install_layout(tmp_path: Path) -> None:
    root = tmp_path / "tools"
    policy = {"shared_tools": {"version_manager": "mise"}}
    assert doctor._install_base(root, policy) == root / "mise" / "installs"
    assert doctor._install_base(root, {"shared_tools": {}}) == root / "installs"


@pytest.mark.parametrize(
    "body,expected",
    [
        ({}, True),
        ({"TCP": {"443": {}}, "AllowFunnel": {"demo:443": False}}, True),
        ({"TCP": {"8443": {}}}, False),
        ({"AllowFunnel": {"demo:443": True}}, False),
        ({"AllowFunnel": {"demo:443": "false"}}, None),
        ({"TCP": []}, None),
        ({"unknown": {}}, None),
    ],
)
def test_d9b_serve_parser(body: Any, expected: bool | None) -> None:
    assert doctor._serve_allowed(json.dumps(body).encode(), [443]) is expected


@pytest.mark.parametrize(
    "address,uid,expected",
    [
        ("0100007F", "1000", True),
        ("00000000", "0", False),
        ("0100000A", "1000", False),
        ("garbage", "0", None),
    ],
)
def test_d9b_listener_uid_never_exempts(address: str, uid: str, expected: bool | None) -> None:
    body = (
        "sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid\n"
        f"0: {address}:0016 00000000:0000 0A 0:0 00:0 0 {uid} 0 1"
    )
    assert doctor._listeners_loopback(body, False) is expected


@pytest.mark.parametrize(
    "case,expected",
    [
        ("pass", "pass"),
        ("fail", "fail"),
        ("denied", "not_verified"),
        ("malformed", "not_verified"),
        ("unrelated", "not_verified"),
    ],
)
def test_d9b_ubuntu_tpm(monkeypatch: pytest.MonkeyPatch, case: str, expected: str) -> None:
    data = example()
    data["host"]["disk"]["encryption"] = "luks2-tpm2"
    body = json.dumps(
        {
            "blockdevices": [
                {
                    "type": "part",
                    "uuid": "root-volume",
                    "mountpoints": [None],
                    "children": [{"type": "crypt", "uuid": None, "mountpoints": ["/"]}],
                }
            ]
        }
    ).encode()

    def run(os_id: str, argv: tuple[str, ...], **kwargs: Any) -> probe.ProbeResult:
        assert argv in (
            ("/usr/bin/lsblk", "--json", "--output", "TYPE,MOUNTPOINTS"),
            ("/usr/bin/lsblk", "--json", "--output", "TYPE,MOUNTPOINTS,UUID"),
        )
        return probe.ProbeResult(body, 0)

    def text(path: Path, prefix: Path) -> tuple[str, doctor.Reason | None]:
        assert path == Path("/etc/crypttab")
        if case == "denied":
            return "", "probe_error"
        if case == "malformed":
            return "bad config", None
        uuid = "other-volume" if case == "unrelated" else "root-volume"
        return f"root UUID={uuid} none " + (
            "luks" if case == "fail" else "luks,tpm2-device=auto"
        ), None

    monkeypatch.setattr(probe, "run_probe", run)
    monkeypatch.setattr(doctor, "_text", text)
    row = d9_row(data, "host.disk-luks2-tpm")
    assert next(r for r in row["reads"] if r["name"] == "tpm_option")["state"] == expected
    assert row["state"] != "pass"


@pytest.mark.parametrize(
    "check,case,expected",
    [
        ("remote_access.tailscale-version", "pass", "pass"),
        ("remote_access.tailscale-version", "old", "fail"),
        ("remote_access.tailscale-version", "stopped", "fail"),
        ("remote_access.tailscale-version", "denied", "not_verified"),
        ("remote_access.tailscale-version", "malformed", "not_verified"),
        ("remote_access.tailscale-serve-named", "pass", "pass"),
        ("remote_access.tailscale-serve-named", "funnel", "fail"),
        ("remote_access.tailscale-serve-named", "denied", "not_verified"),
        ("remote_access.tailscale-serve-named", "malformed", "not_verified"),
    ],
)
def test_d9b_tailscale(
    monkeypatch: pytest.MonkeyPatch, check: str, case: str, expected: str
) -> None:
    def run(os_id: str, argv: tuple[str, ...], **kwargs: Any) -> probe.ProbeResult:
        assert argv in (
            ("/usr/bin/dpkg-query", "-W", "-f=${Version}", "tailscale"),
            ("/usr/bin/tailscale", "status", "--json"),
            ("/usr/bin/tailscale", "serve", "status", "--json"),
        )
        if case == "denied":
            return probe.ProbeResult(reason="probe_error")
        if case == "malformed":
            return probe.ProbeResult(b"bad", 0)
        if argv[0].endswith("dpkg-query"):
            return probe.ProbeResult(b"0.1.0" if case == "old" else b"99.0.0-1", 0)
        body = (
            {"BackendState": "Stopped" if case == "stopped" else "Running"}
            if argv[1] == "status"
            else {"AllowFunnel": {"demo:443": case == "funnel"}}
        )
        return probe.ProbeResult(json.dumps(body).encode(), 0)

    monkeypatch.setattr(probe, "run_probe", run)
    assert d9_row(example(), check)["state"] == expected


def effective_account(monkeypatch: pytest.MonkeyPatch, name: str, uid: int = 4242) -> None:
    """Resolve the account the way doctor must: from the effective uid, nothing else."""
    monkeypatch.setattr(os, "geteuid", lambda: uid)
    monkeypatch.setattr(
        pwd,
        "getpwuid",
        lambda number: pwd.struct_passwd((name, "x", number, number, "", "/nonexistent", "/bin/sh")),
    )


@pytest.mark.parametrize("variable", ["LOGNAME", "USER", "LNAME", "USERNAME"])
def test_s4_screen_ignores_spoofed_environment(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    data = example()
    effective_account(monkeypatch, "fixture-agent")
    monkeypatch.setenv(variable, data["owner"]["user"])
    probe_run = Mock(side_effect=AssertionError("owner settings must not be read"))
    monkeypatch.setattr(probe, "run_probe", probe_run)
    row = d9_row(data, "host.screen-lock")
    assert row["state"] == "not_verified" and row["reason"] == "other_account"
    probe_run.assert_not_called()


def test_s4_screen_unresolvable_account_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    data = example()
    monkeypatch.setenv("LOGNAME", data["owner"]["user"])
    monkeypatch.setattr(os, "geteuid", lambda: 4242)

    def missing(number: int) -> Any:
        raise KeyError(number)

    monkeypatch.setattr(pwd, "getpwuid", missing)
    monkeypatch.setattr(probe, "run_probe", Mock(side_effect=AssertionError("no probe")))
    assert d9_row(data, "host.screen-lock")["reason"] == "other_account"


@pytest.mark.parametrize(
    "case,expected",
    [
        ("pass", "pass"),
        ("off", "fail"),
        ("zero", "fail"),
        ("denied", "not_verified"),
        ("malformed", "not_verified"),
    ],
)
def test_d9b_screen(monkeypatch: pytest.MonkeyPatch, case: str, expected: str) -> None:
    data = example()
    effective_account(monkeypatch, data["owner"]["user"])

    def run(os_id: str, argv: tuple[str, ...], **kwargs: Any) -> probe.ProbeResult:
        assert argv[0:2] == ("/usr/bin/gsettings", "get")
        if case == "denied":
            return probe.ProbeResult(reason="probe_error")
        value = (
            b"bad"
            if case == "malformed"
            else (b"false" if case == "off" else b"true")
            if argv[-1] == "lock-enabled"
            else b"uint32 0"
            if case == "zero"
            else b"uint32 60"
        )
        return probe.ProbeResult(value, 0)

    monkeypatch.setattr(probe, "run_probe", run)
    assert d9_row(data, "host.screen-lock")["state"] == expected


@pytest.mark.parametrize(
    "case,expected",
    [
        ("recent", "pass"),
        ("old", "fail"),
        ("incomplete", "not_verified"),
        ("denied", "not_verified"),
        ("malformed", "not_verified"),
    ],
)
def test_d9b_update(monkeypatch: pytest.MonkeyPatch, case: str, expected: str) -> None:
    date = datetime.now(timezone.utc) - timedelta(days=90 if case == "old" else 1)
    text = f"[{date.isoformat()}] [PACMAN] starting full system upgrade\n"
    if case != "incomplete":
        text += f"[{date.isoformat()}] [ALPM] transaction completed\n"
    monkeypatch.setattr(
        doctor,
        "_text",
        lambda *args: (
            ("", "probe_error")
            if case == "denied"
            else ("bad" if case == "malformed" else text, None)
        ),
    )
    row = d9_row(example("omarchy"), "hardening.update-snapshot", "omarchy")
    assert row["reads"][0]["state"] == expected
    assert row["state"] == ("fail" if case == "old" else "not_verified")


@pytest.mark.parametrize(
    "case,state",
    [
        ("loopback", "pass"),
        ("root-ssh", "not_verified"),
        ("denied", "not_verified"),
        ("malformed", "not_verified"),
    ],
)
def test_d9b_listener_row(monkeypatch: pytest.MonkeyPatch, case: str, state: str) -> None:
    def text(path: Path, prefix: Path) -> tuple[str, doctor.Reason | None]:
        assert prefix == Path("/proc/net") and path.name in {"tcp", "tcp6"}
        if case == "denied":
            return "", "probe_error"
        if case == "malformed":
            return "bad", None
        address = "00000000" if case == "root-ssh" else "0100007F"
        if path.name == "tcp6":
            address = "00000000000000000000000001000000"
        return (
            "sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid\n"
            f"0: {address}:0016 0:0 0A 0:0 00:0 0 0 0 1"
        ), None

    monkeypatch.setattr(doctor, "_text", text)
    assert d9_row(example(), "remote_access.offbox-listeners")["state"] == state


def test_d9b_screen_refuses_other_account_and_omarchy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probe, "run_probe", Mock(side_effect=AssertionError("no session probe")))
    monkeypatch.setattr(doctor, "_text", Mock(side_effect=AssertionError("no user config read")))
    data = example()
    effective_account(monkeypatch, "different-owner")
    row = d9_row(data, "host.screen-lock")
    assert row["reason"] == "other_account"
    data = example("omarchy")
    effective_account(monkeypatch, data["owner"]["user"])
    assert d9_row(data, "host.screen-lock", "omarchy")["reason"] == "not_checked"
