"""Acceptance checks for books doctor and CLI findability follow-ups."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb.cli import app
from mb.init import run as init_run

RUNNER = CliRunner()
TEMPLATE = Path(__file__).resolve().parents[1] / "mb/_data/books/repo-template"


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _commit(repo: Path) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "fixture")


def _repo(path: Path, *, template: bool = False) -> Path:
    if template:
        shutil.copytree(TEMPLATE, path)
    else:
        path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    return path


def _hledger(monkeypatch: pytest.MonkeyPatch, path: str | None) -> None:
    real = shutil.which
    monkeypatch.setattr(
        "mb.books_repo.shutil.which", lambda name: path if name == "hledger" else real(name)
    )


def _books_doctor(repo: Path) -> tuple[int, list[dict[str, str]]]:
    result = RUNNER.invoke(app, ["books", "doctor", "--repo", str(repo), "--json"])
    return result.exit_code, json.loads(result.output)["findings"]


def test_d1_workpapers_csv_is_not_evidence(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "books", template=True)
    workpapers = repo / "workpapers"
    workpapers.mkdir()
    (workpapers / "balances.csv").write_text("account,balance\nA,1\n")
    _commit(repo)
    code, findings = _books_doctor(repo)
    assert code == 0 and findings == []

    (workpapers / "statement.pdf").write_bytes(b"statement")
    _commit(repo)
    code, findings = _books_doctor(repo)
    assert code == 1 and [item["rule"] for item in findings] == ["evidence_tracked"]

    (workpapers / "statement.pdf").unlink()
    exports = repo / "exports"
    exports.mkdir()
    (exports / "raw.csv").write_text("raw\n1\n")
    _commit(repo)
    code, findings = _books_doctor(repo)
    assert code == 1 and [item["rule"] for item in findings] == ["evidence_tracked"]


def test_d2_workspace_is_ok_when_hledger_is_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _hledger(monkeypatch, "/usr/bin/hledger")
    repo = _repo(tmp_path / "workspace")
    (repo / "AGENTS.md").write_text("# Workspace\n")
    _commit(repo)
    code, findings = _books_doctor(repo)
    assert code == 0 and [(item["rule"], item["level"]) for item in findings] == [
        ("workspace_repo", "info")
    ]


def test_d2_docs_only_repo_is_a_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Shape rules only: keep the ledger doctor out whether or not hledger is installed.
    _hledger(monkeypatch, None)
    repo = _repo(tmp_path / "workspace")
    (repo / "AGENTS.md").write_text("# Workspace\n")
    (repo / "docs").mkdir()
    (repo / "docs/audit.md").write_text("# Audit\n")
    _commit(repo)
    code, findings = _books_doctor(repo)
    assert code == 0 and [(item["rule"], item["level"]) for item in findings] == [
        ("workspace_repo", "info")
    ]

    (repo / "statement.pdf").write_bytes(b"statement")
    _commit(repo)
    code, findings = _books_doctor(repo)
    assert code == 1 and [item["rule"] for item in findings] == [
        "workspace_repo",
        "evidence_tracked",
    ]

    ledger = _repo(tmp_path / "ledger", template=True)
    (ledger / "2026.journal").unlink()
    _commit(ledger)
    code, findings = _books_doctor(ledger)
    assert code == 1 and [item["rule"] for item in findings] == ["entrypoint_missing"]


def test_d3_status_line_may_carry_a_note(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "books", template=True)
    _commit(repo)
    rules = repo / "rules/sample-bank.csv.rules"
    original = rules.read_text()
    for status in ("active recurring", "migration generator", "template/fallback"):
        for delimiter in (".", ";", ",", " -", " ("):
            rules.write_text(
                original.replace("Status: template/fallback", f"Status: {status}{delimiter} note")
            )
            code, findings = _books_doctor(repo)
            assert code == 0 and findings == [], (status, delimiter, findings)
    for value in ("active recurringly", "unknown"):
        rules.write_text(original.replace("Status: template/fallback", f"Status: {value}"))
        code, findings = _books_doctor(repo)
        assert code == 1 and [item["rule"] for item in findings] == ["rules_status_invalid"]
    rules.write_text(original + "\n# Status: active recurring\n")
    code, findings = _books_doctor(repo)
    assert code == 1 and [item["rule"] for item in findings] == ["rules_status_invalid"]
    rules.write_text(original.replace("Status:", "State:"))
    code, findings = _books_doctor(repo)
    assert code == 1 and [item["rule"] for item in findings] == ["rules_status_missing"]


def test_d4_books_check_names_mb_books(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "business")
    # Baseline IDs and states from 3227fd76 for this exact fixture.
    baseline = {
        "books-policy-missing": "info",
        "chart-of-accounts-missing": "info",
        "vault-ignore-rule-missing": "warn",
        "unsafe-paths-clean": "ok",
    }
    for configured in (False, True):
        if configured:
            policy = repo / "core/finance/books.md"
            policy.parent.mkdir(parents=True)
            policy.write_text("---\nstorage_mode: team-private-repo\nbooks_repo: ../books\n---\n")
        human = RUNNER.invoke(app, ["books", "check", str(repo)])
        result = RUNNER.invoke(app, ["books", "check", str(repo), "--json"])
        assert human.exit_code == result.exit_code == 0
        payload = json.loads(result.output)
        findings = {item["id"]: item for item in payload["findings"]}
        pointers = [item for item in findings.values() if "/mb-books" in item["operator_summary"]]
        assert len(pointers) == 1 and pointers[0]["state"] == "info"
        assert "/mb-books" in human.output
        assert ("setup" if not configured else "monthly close") in pointers[0]["operator_summary"]
        other = {name: item["state"] for name, item in findings.items() if item not in pointers}
        if not configured:
            assert other == baseline
        else:
            assert other == {
                "books-policy-ok": "ok",
                "books-money-path-thresholds-missing": "info",
                "chart-of-accounts-missing": "info",
                "vault-ignore-rule-skipped": "info",
                "unsafe-paths-clean": "ok",
            }


def test_d5_doctor_names_missing_bundled_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(home / ".codex"))
    repo = tmp_path / "business"
    init_run(path=str(repo), name="Test Business")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    linked = RUNNER.invoke(app, ["skill", "link", "--repo", str(repo)])
    assert linked.exit_code == 0, linked.output
    _commit(repo)
    (repo / ".claude/skills/mb-books").unlink()
    before = _git(repo, "status", "--porcelain")

    doctor = RUNNER.invoke(app, ["doctor", str(repo), "--json"])
    status = RUNNER.invoke(app, ["status", str(repo), "--json", "--peek"])
    checks: dict[str, dict[str, Any]] = {
        item["name"]: item for item in json.loads(doctor.output)["checks"]
    }
    assert checks["skill-links-current"]["severity"] == "warn"
    assert "mb-books" in checks["skill-links-current"]["detail"]
    assert "mb skill link --repo" in checks["skill-links-current"]["detail"]
    assert json.loads(status.output)["runtime"]["skill_wiring"]["missing_bundled_links"] == [
        "mb-books"
    ]
    assert before == _git(repo, "status", "--porcelain")

    linked = RUNNER.invoke(app, ["skill", "link", "--repo", str(repo)])
    assert linked.exit_code == 0, linked.output
    before = _git(repo, "status", "--porcelain")
    doctor = RUNNER.invoke(app, ["doctor", str(repo), "--json"])
    status = RUNNER.invoke(app, ["status", str(repo), "--json", "--peek"])
    checks = {item["name"]: item for item in json.loads(doctor.output)["checks"]}
    assert checks["skill-links-current"]["severity"] == "ok"
    assert json.loads(status.output)["runtime"]["skill_wiring"]["missing_bundled_links"] == []
    assert before == _git(repo, "status", "--porcelain")
