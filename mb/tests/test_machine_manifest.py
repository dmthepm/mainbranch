"""Manifest syntax, trust, and policy assurance regressions."""

import copy
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from typer.testing import CliRunner

from mb import machine_doctor as doctor
from mb import machine_manifest as manifest
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
    assert {r["name"] for r in coverage["reads"]} == set(data) - {"manifest_version", "checks"}
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
