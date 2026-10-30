"""Synthetic snapshot contracts and read-only usage behavior."""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import connect, ranker, status, usage
from mb.cli import app

FIXTURES = Path(__file__).parent / "fixtures" / "usage"
NOW = "2030-01-01T12:00:00Z"


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.chdir(tmp_path)


def collect(name: str = "fresh", **kwargs: Any) -> dict[str, Any]:
    return usage.collect(directory=str(FIXTURES / name), now=NOW, **kwargs)


@pytest.mark.parametrize(
    ("fixture", "exit_code", "reason"),
    [
        ("fresh", 0, None),
        ("stale-file", 3, "snapshot_stale"),
        ("stale-reading", 3, "reading_stale"),
        ("schema-2", 3, "schema_unknown"),
        ("no-schema", 3, "schema_unknown"),
        ("extra-field", 3, "unknown_field"),
        ("bad-pct", 3, "malformed"),
        ("email-key", 3, "bad_account_key"),
        ("future", 3, "clock_skew"),
        ("full-week", 1, None),
        ("full-no-credit", 1, None),
        ("almost-full", 0, None),
        ("past-window", 0, None),
        ("credits-mismatch", 1, None),
        ("missing", 3, None),
    ],
)
def test_fixture_verdicts(fixture, exit_code, reason):
    result = collect(fixture)
    assert result["exit_code"] == exit_code
    if reason:
        assert result["accounts"][0]["reason"] == reason
        assert result["accounts"][0]["state"] == "not_verified"
        assert result["actions"] == []


def test_pace_and_credit_question():
    result = collect()
    assert result["accounts"][0]["sustainable_pct_per_hour"] == 2.5
    codex = result["accounts"][2]
    assert codex["reset_credits"] == {
        "state": "fresh",
        "available": 1,
        "expires": ["2030-01-03T12:00:00Z"],
        "information_only": True,
    }
    full = collect("full-week")
    assert len(full["actions"]) == 1
    assert full["actions"][0]["kind"] == "owner_question"
    assert "command" not in full["actions"][0]
    assert full["actions"][0]["message"].endswith(usage.QUESTION)
    assert "mb " not in usage.QUESTION.replace("mb won't do it", "")
    for fixture in (
        "full-no-credit",
        "almost-full",
        "past-window",
        "stale-file",
        "credits-mismatch",
    ):
        assert collect(fixture)["actions"] == []
    for fixture in ("stale-file", "stale-reading", "future", "past-window"):
        assert all(a.get("sustainable_pct_per_hour") is None for a in collect(fixture)["accounts"])


def test_cli_envelope_and_privacy():
    result = CliRunner().invoke(
        app, ["usage", "--dir", str(FIXTURES / "fresh"), "--now", NOW, "--json"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["result_schema"] == {"name": "mainbranch.usage", "version": "1.0"}
    assert data["result_envelope_version"] == "1.0"
    assert data["mb_command"] == "mb usage"
    assert data["ok"] is True
    assert data["safe_to_share"] is False
    assert data["now_overridden"] is True
    assert str(FIXTURES) not in result.stdout
    assert "synthetic-writer" not in result.stdout
    human = CliRunner().invoke(app, ["usage", "--dir", str(FIXTURES / "full-week"), "--now", NOW])
    assert human.exit_code == 1
    assert usage.QUESTION in human.stdout
    assert "information only" in human.stdout


def test_config_and_bad_now(tmp_path, monkeypatch):
    assert usage.collect(now=NOW)["exit_code"] == 3
    assert usage.status_view(repo=tmp_path, now=usage.timestamp(NOW)) == {"configured": False}
    assert usage.collect(now="not-a-date")["exit_code"] == 2
    assert usage.collect(config={"dir": "relative"}, now=NOW)["exit_code"] == 2
    config_dir = tmp_path / "config" / "mainbranch"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(
        f'[usage]\ndir = "{FIXTURES / "fresh"}"\n[usage.accounts]\nexample-a = "Main account"\n'
    )
    result = usage.collect(now=NOW)
    assert result["exit_code"] == 0
    assert result["accounts"][0]["label"] == "Main account"
    assert usage.status_view(repo=tmp_path, now=usage.timestamp(NOW))["configured"] is True
    (config_dir / "config.toml").write_text("broken = [")
    cli_result = CliRunner().invoke(app, ["usage", "--json"])
    assert cli_result.exit_code == 2
    assert str(config_dir) not in cli_result.stdout


def test_roles_and_exit_precedence(tmp_path):
    team = tmp_path / "core" / "team"
    team.mkdir(parents=True)
    for name, cap in (("under", 90), ("near", 44), ("over", 35)):
        (team / f"{name}.md").write_text(f"---\nbudget:\n  stop_at_pct: {cap}\n---\n")
    config = {"role_accounts": {name: "example-a" for name in ("under", "near", "over")}}
    result = collect(config=config, repo=tmp_path)
    assert {r["id"]: r["state"] for r in result["roles"]} == {
        "under": "under",
        "near": "near",
        "over": "at_cap",
    }
    assert result["exit_code"] == 1
    (team / "text.md").write_text('---\nbudget_cap: "stop when tired"\n---\n')
    (team / "unmapped.md").write_text("---\nbudget:\n  stop_at_pct: 85\n---\n")
    result = collect(config=config, repo=tmp_path)
    assert result["exit_code"] == 1
    reasons = {r["id"]: r["reason"] for r in result["roles"]}
    assert reasons["text"] == "cap_not_structured"
    assert reasons["unmapped"] == "account_unknown"
    config["role_accounts"]["under"] = "unknown"
    assert collect(config=config, repo=tmp_path)["exit_code"] == 2
    (team / "over.md").write_text("---\nbudget:\n  stop_at_pct: true\n---\n")
    assert collect(repo=tmp_path)["exit_code"] == 2


def test_cap_beats_stale(tmp_path):
    shutil.copytree(FIXTURES / "full-week", tmp_path / "snapshots")
    (tmp_path / "snapshots" / "claude.json").write_text(
        (FIXTURES / "stale-reading" / "claude.json").read_text()
    )
    result = usage.collect(directory=str(tmp_path / "snapshots"), now=NOW)
    assert result["exit_code"] == 1
    assert result["summary"]["not_verified"] == 2


@pytest.mark.parametrize("kind", ["symlink", "world-writable", "oversize", "directory"])
def test_unsafe_files(tmp_path, kind):
    path = tmp_path / "codex.json"
    if kind == "symlink":
        path.symlink_to(FIXTURES / "fresh" / "codex.json")
    elif kind == "directory":
        path.mkdir()
    else:
        path.write_text(" " * 16385 if kind == "oversize" else "{}")
        if kind == "world-writable":
            path.chmod(0o666)
    result = usage.collect(directory=str(tmp_path), now=NOW)
    assert result["accounts"][0]["reason"] == "unsafe_file"


def test_read_only(tmp_path):
    folder = tmp_path / "snapshots"
    shutil.copytree(FIXTURES / "fresh", folder)
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    for p in folder.iterdir():
        p.chmod(0o400)
    folder.chmod(0o500)
    try:
        result = usage.collect(directory=str(folder), now=NOW)
        assert result["exit_code"] == 0
        assert {p.name: p.read_bytes() for p in folder.iterdir()} == before
    finally:
        folder.chmod(0o700)


def test_status_integration(tmp_path, monkeypatch):
    monkeypatch.setattr(usage, "load_config", lambda: {"dir": str(FIXTURES / "fresh")})
    view = usage.status_view(repo=tmp_path, now=usage.timestamp(NOW))
    assert view["summary"]["fresh"] == 3
    assert usage.status_line(view) == (
        "Usage: example-a 40% (resets in 24.0 h), "
        "example-b 20% (resets in 24.0 h), codex 30% (resets in 24.0 h)"
    )
    # Run the real status builder with costly external probes replaced by local facts.
    monkeypatch.setattr(status, "_github", lambda *a, **kw: {"available": False})
    monkeypatch.setattr(status, "package_update_status", lambda *a: {})
    monkeypatch.setattr(status, "_runtime", lambda *a: {})
    monkeypatch.setattr(connect, "status_all", lambda *a, **kw: {})
    monkeypatch.setattr(status, "_readiness", lambda *a: {"level": "ready", "score": 100})
    monkeypatch.setattr(ranker, "rank_status_report", lambda *a: [])
    monkeypatch.setattr(status, "_drift", lambda *a: {})
    for fixture in ("fresh", "full-week", "stale-file"):
        monkeypatch.setattr(
            usage, "load_config", lambda fixture=fixture: {"dir": str(FIXTURES / fixture)}
        )
        report = status.run(str(tmp_path), update_marker=False, now=usage.timestamp(NOW))
        assert report["ok"] is True
        assert report["usage"]["configured"] is True


def test_no_network_or_process_and_no_redemption_calls():
    package = Path(usage.__file__).parent
    blocked = {
        "urllib",
        "http",
        "socket",
        "requests",
        "httpx",
        "subprocess",
        "openai",
        "httpcore",
        "aiohttp",
    }
    reader_tree = ast.parse(Path(usage.__file__).read_text())
    for node in ast.walk(reader_tree):
        if isinstance(node, ast.Import):
            assert all(n.name.split(".")[0] not in blocked for n in node.names)
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in blocked
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"system", "popen", "urlopen"}
            assert not node.func.attr.startswith(("exec", "spawn"))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
        ):
            assert isinstance(node.args[0], ast.Constant) and node.args[0].value == "tomllib"
    for file in package.rglob("*.py"):
        for node in ast.walk(ast.parse(file.read_text())):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert not any(word in node.name.lower() for word in ("redeem", "consume"))
            if isinstance(node, ast.Call):
                name = (
                    node.func.id
                    if isinstance(node.func, ast.Name)
                    else node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else ""
                )
                assert not any(word in name.lower() for word in ("redeem", "consume"))
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "://" in node.value
            ):
                assert not ("reset" in node.value.lower() and "credit" in node.value.lower())


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("written_at", "2030-01-01T12:06:00Z", "clock_skew"),
        ("taken_at", "2030-01-01T12:00:01Z", "clock_skew"),
        ("used_pct", True, "malformed"),
        ("used_pct", float("nan"), "malformed"),
        ("used_pct", -1, "malformed"),
        ("schema_version", True, "schema_unknown"),
        ("written_at", "2030-01-01T11:55:00+00:00", "malformed"),
    ],
)
def test_strict_fields(tmp_path, field, value, expected):
    data = json.loads((FIXTURES / "fresh" / "codex.json").read_text())
    data[field] = value
    (tmp_path / "codex.json").write_text(json.dumps(data))
    result = usage.collect(directory=str(tmp_path), now=NOW)
    assert result["accounts"][0]["reason"] == expected
    assert result["exit_code"] == 3


@pytest.mark.parametrize("case", ["old", "future", "expired", "unknown"])
def test_unusable_credits_never_prompt(tmp_path, case):
    data = json.loads((FIXTURES / "full-week" / "codex.json").read_text())
    credits = data["reset_credits"]
    if case == "old":
        credits["read_at"] = "2030-01-01T08:00:00Z"
    if case == "future":
        credits["read_at"] = "2030-01-01T12:01:00Z"
    if case == "expired":
        credits["credits"][0]["expires_at"] = "2030-01-01T11:59:00Z"
    if case == "unknown":
        data["reset_credits"] = {"status": "UNKNOWN", "reason": "not_read"}
    (tmp_path / "codex.json").write_text(json.dumps(data))
    result = usage.collect(directory=str(tmp_path), now=NOW)
    assert result["actions"] == []
    assert result["accounts"][0]["reset_credits"]["state"] == "unknown"
    assert result["exit_code"] == 1


def test_missing_file_is_skipped_and_unknown_fields_refused(tmp_path):
    result = collect("missing")
    assert result["warnings"] == [
        {"file": "claude.json", "code": "missing_file"},
        {"file": "codex.json", "code": "missing_file"},
        {"code": "no_snapshot"},
    ]
    data = json.loads((FIXTURES / "fresh" / "codex.json").read_text())
    data["reset_credits"]["unexpected"] = "fake"
    (tmp_path / "codex.json").write_text(json.dumps(data))
    result = usage.collect(directory=str(tmp_path), now=NOW)
    assert result["accounts"][0]["reason"] == "unknown_field"
