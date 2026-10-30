"""Synthetic snapshot contracts and read-only usage behavior."""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
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


def _forbidden_word(text: str) -> bool:
    words = re.findall(r"[a-z]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", text).lower())
    return "redeem" in text.lower() or "consume" in words


def redemption_hits(source: str) -> list[str]:
    """Bounded regression check: names and literals, not proof about arbitrary Python."""
    tree = ast.parse(source)
    documented = [
        node.body[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and ast.get_docstring(node) is not None
    ]
    prose = {id(stmt.value) for stmt in documented if isinstance(stmt, ast.Expr)}
    hits = []
    for node in ast.walk(tree):
        names = [getattr(node, field, None) for field in ("name", "attr", "id", "arg", "asname")]
        names.append(getattr(node, "module", None))
        hits += [name for name in names if isinstance(name, str) and _forbidden_word(name)]
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (str, bytes))
            and id(node) not in prose
        ):
            value = node.value
            text = value.decode("utf-8", "replace") if isinstance(value, bytes) else value
            lowered = text.lower()
            endpoint = "/" in text and "reset" in lowered and "credit" in lowered
            if _forbidden_word(text) or endpoint:
                hits.append(text)
    return hits


def skill_hits(text: str) -> list[str]:
    """Flag redeem wording outside a "never" sentence; a limited wording check."""
    hits = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        lowered = sentence.lower()
        consume = "consume" in lowered and ("reset" in lowered or "credit" in lowered)
        if ("redeem" in lowered or consume) and "never" not in lowered:
            hits.append(sentence.strip())
    return hits


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
    hits = {
        str(file.relative_to(package)): redemption_hits(file.read_text())
        for file in package.rglob("*.py")
    }
    assert {name: found for name, found in hits.items() if found} == {}


@pytest.mark.parametrize(
    "source",
    [
        'client.post("/redeem")',
        'client.post(b"/redeem")',
        'getattr(client, "redeem")()',
        "f = client.consume; f()",
        "client.redeem",
        "def redeem_credit(): pass",
        "class CreditRedeemer: pass",
        "call(redeem=True)",
        "from billing import consume",
        "import provider.redeem",
        "consumeCredit()",
        'client.post(f"/credits/{credit}/consume")',
        'client.post("/v1/credits/reset")',
        'client.get("https://example.test/reset-credits")',
        'client.get("https://example.test/redeem")',
    ],
)
def test_redemption_scan_catches(source):
    assert redemption_hits(source)


@pytest.mark.parametrize(
    "source",
    ["consumed = 1", 'text = "JSON consumers"', 'key = "reset_credits"', 'word = "redemption"'],
)
def test_redemption_scan_allows_unrelated_words(source):
    assert redemption_hits(source) == []


def test_bundled_skills_never_tell_an_agent_to_redeem():
    skills = Path(usage.__file__).parents[2] / ".claude" / "skills"
    files = [path for path in skills.rglob("*") if path.is_file()]
    assert any(path.name == "SKILL.md" for path in files)
    hits = {}
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        found = skill_hits(text) + (redemption_hits(text) if path.suffix == ".py" else [])
        if found:
            hits[str(path.relative_to(skills))] = found
    assert hits == {}


@pytest.mark.parametrize(
    "text",
    [
        "Redeem the banked reset now.",
        "Run this first.\nUse `client.redeem()` to restore capacity.",
        "Consume a reset credit when blocked.",
    ],
)
def test_skill_scan_catches(text):
    assert skill_hits(text)


@pytest.mark.parametrize(
    "text",
    ["Never redeem a banked reset.", "Skills consume this file.", "The redemption arc."],
)
def test_skill_scan_allows_refusals_and_unrelated_words(text):
    assert skill_hits(text) == []


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


def run_with_timeout(code: str, *args: str) -> dict[str, Any]:
    """Run a probe in a child process so a blocking read fails instead of hanging pytest."""
    env = {**os.environ, "PYTHONPATH": str(Path(usage.__file__).parents[1])}
    done = subprocess.run(
        [sys.executable, "-c", code, *args],
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
        check=True,
    )
    data: dict[str, Any] = json.loads(done.stdout)
    return data


COLLECT_PROBE = """
import json, sys
from pathlib import Path
from mb import usage
now = "2030-01-01T12:00:00Z"
result = usage.collect(directory=sys.argv[1], now=now, repo=Path(sys.argv[2]))
view = usage.status_view(repo=Path(sys.argv[2]), now=usage.timestamp(now))
print(json.dumps({"collect": result, "status": view}))
"""

STATUS_PROBE = """
import json, sys
from mb import connect, ranker, status, usage
status._github = lambda *a, **kw: {"available": False}
status.package_update_status = lambda *a: {}
status._runtime = lambda *a: {}
connect.status_all = lambda *a, **kw: {}
status._readiness = lambda *a: {"level": "ready", "score": 100}
ranker.rank_status_report = lambda *a: []
status._drift = lambda *a: {}
report = status.run(sys.argv[1], update_marker=False, now=usage.timestamp("2030-01-01T12:00:00Z"))
print(json.dumps({"usage": report["usage"]}))
"""


def _plant(path: Path, kind: str, limit: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "symlink-to-fifo":
        os.mkfifo(path.with_suffix(".pipe"))
        path.symlink_to(path.with_suffix(".pipe"))
    elif kind == "symlink":
        path.with_suffix(".real").write_text("---\nbudget_cap: x\n---\n")
        path.symlink_to(path.with_suffix(".real"))
    else:
        with path.open("wb") as stream:
            stream.truncate(limit + 1)


KINDS = ["fifo", "symlink-to-fifo", "symlink", "oversize"]


@pytest.mark.parametrize("kind", KINDS)
def test_bad_config_does_not_hang(tmp_path, kind):
    _plant(tmp_path / "config" / "mainbranch" / "config.toml", kind, usage.CONFIG_LIMIT)
    data = run_with_timeout(COLLECT_PROBE, str(FIXTURES / "fresh"), str(tmp_path))
    assert data["collect"]["errors"] == [{"code": "usage_config_unreadable"}]
    assert data["collect"]["exit_code"] == 2
    assert data["status"]["errors"] == [{"code": "usage_config_invalid"}]


@pytest.mark.parametrize("kind", KINDS)
def test_bad_role_file_does_not_hang(tmp_path, kind):
    _plant(tmp_path / "core" / "team" / "blocked.md", kind, usage.ROLE_LIMIT)
    data = run_with_timeout(COLLECT_PROBE, str(FIXTURES / "fresh"), str(tmp_path))
    assert data["collect"]["errors"] == [{"code": "role_profile_invalid"}]
    assert data["collect"]["exit_code"] == 2


def test_status_survives_fifo_config_and_team_file(tmp_path):
    _plant(tmp_path / "config" / "mainbranch" / "config.toml", "fifo", 0)
    _plant(tmp_path / "core" / "team" / "blocked.md", "fifo", 0)
    data = run_with_timeout(STATUS_PROBE, str(tmp_path))
    assert data["usage"]["errors"] == [{"code": "usage_config_invalid"}]


def test_role_text_is_escaped_for_terminals(tmp_path):
    team = tmp_path / "core" / "team"
    team.mkdir(parents=True)
    (team / "evil\x1b[2J.md").write_text("---\nbudget:\n  stop_at_pct: 44\n---\n")
    (team / "title\x1b]0;x\x07.md").write_text("---\nbudget_cap: tired\n---\n")
    (team / "text.md").write_text('---\nbudget_cap: "stop\\e[2J \\x9b1m \\u202e\\n fake"\n---\n')
    text = usage.render(collect(repo=tmp_path))
    assert all(char.isprintable() or char == "\n" for char in text)
    assert "evil\\x1b[2J: cap 44%" in text
    assert "title\\x1b]0;x\\x07: tired" in text
    assert "stop\\x1b[2J \\x9b1m \\u202e\\n fake" in text
    line = usage.status_line(
        {
            "accounts": [],
            "roles": [{"id": "evil\x1b[2J", "stop_at_pct": 44}],
            "evaluated_at": NOW,
        }
    )
    assert "\x1b" not in line
    assert "evil\\x1b[2J (44%)" in line
    cli = CliRunner().invoke(
        app, ["usage", "--dir", str(FIXTURES / "fresh"), "--now", NOW, "--json"]
    )
    assert "\x1b" not in cli.stdout


@pytest.mark.parametrize(
    ("field", "value", "status_value"),
    [
        ("granted_at", "2030-01-02T00:00:00Z", "available"),
        ("expires_at", "2030-01-01T10:00:00Z", "available"),
        ("granted_at", "2030-01-02T00:00:00Z", "used"),
    ],
)
def test_impossible_credit_chronology_is_unknown(tmp_path, field, value, status_value):
    data = json.loads((FIXTURES / "full-week" / "codex.json").read_text())
    credit = data["reset_credits"]["credits"][0]
    credit["granted_at"] = "2030-01-01T11:00:00Z"
    credit["expires_at"] = "2030-01-03T12:00:00Z"
    credit["status"] = status_value
    credit[field] = value
    data["reset_credits"]["available_count"] = 1 if status_value == "available" else 0
    (tmp_path / "codex.json").write_text(json.dumps(data))
    result = usage.collect(directory=str(tmp_path), now=NOW)
    assert result["accounts"][0]["reset_credits"]["state"] == "unknown"
    assert result["accounts"][0]["reset_credits"]["available"] is None
    assert result["actions"] == []


def _snapshots(folder: Path, mode: int) -> Path:
    shutil.copytree(FIXTURES / "fresh", folder)
    for path in folder.iterdir():
        path.chmod(0o644)
    folder.chmod(mode)
    return folder


@pytest.mark.parametrize("mode", [0o775, 0o757, 0o777, 0o1777])
def test_writable_directory_is_not_verified(tmp_path, mode):
    folder = _snapshots(tmp_path / "snapshots", mode)
    config = {"role_accounts": {"near": "example-a"}}
    team = tmp_path / "core" / "team"
    team.mkdir(parents=True)
    (team / "near.md").write_text("---\nbudget:\n  stop_at_pct: 44\n---\n")
    result = usage.collect(directory=str(folder), now=NOW, repo=tmp_path, config=config)
    assert [(a["key"], a["state"], a["reason"]) for a in result["accounts"]] == [
        ("claude", "not_verified", "unsafe_directory"),
        ("codex", "not_verified", "unsafe_directory"),
    ]
    assert result["errors"] == []
    assert result["roles"][0]["state"] == "not_verified"
    assert result["exit_code"] == 3


def test_group_writable_snapshot_file_is_refused(tmp_path):
    folder = _snapshots(tmp_path / "snapshots", 0o755)
    (folder / "codex.json").chmod(0o664)
    result = usage.collect(directory=str(folder), now=NOW)
    assert [a["reason"] for a in result["accounts"]][-1] == "unsafe_file"


def test_collector_owned_directory_stays_fresh(tmp_path, monkeypatch):
    folder = _snapshots(tmp_path / "snapshots", 0o755)
    monkeypatch.setattr(os, "getuid", lambda: os.stat(folder).st_uid + 1)
    monkeypatch.setattr(os, "geteuid", lambda: os.stat(folder).st_uid + 1)
    result = usage.collect(directory=str(folder), now=NOW)
    assert result["exit_code"] == 0
    assert result["summary"]["not_verified"] == 0


@pytest.mark.parametrize(("mode", "exit_code"), [(0o755, 0), (0o777, 3)])
def test_symlinked_directory_is_judged_by_its_target(tmp_path, mode, exit_code):
    folder = _snapshots(tmp_path / "snapshots", mode)
    (tmp_path / "link").symlink_to(folder)
    assert usage.collect(directory=str(tmp_path / "link"), now=NOW)["exit_code"] == exit_code


def test_deeply_nested_inputs_are_not_crashes(tmp_path, monkeypatch):
    folder = tmp_path / "snapshots"
    folder.mkdir(mode=0o755)
    snapshot = folder / "claude.json"
    snapshot.write_text("[" * 16000)
    snapshot.chmod(0o644)
    result = usage.collect(directory=str(folder), now=NOW)
    assert [account["reason"] for account in result["accounts"]] == ["malformed"]

    config = tmp_path / "config" / "mainbranch" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(f'[usage]\ndir = "{folder}"\n')
    config.chmod(0o600)
    data = run_with_timeout(STATUS_PROBE, str(tmp_path))
    assert data["usage"]["accounts"][0]["state"] == "not_verified"

    config.write_text("a = " + "[" * 16000)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    with pytest.raises(ValueError):
        usage.load_config()
