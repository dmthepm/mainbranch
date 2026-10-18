"""Acceptance checks for the read-only books repository doctor."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from mb.cli import app

TEMPLATE = Path(__file__).resolve().parents[1] / "mb/_data/books/repo-template"
RUNNER = CliRunner()


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "books"
    shutil.copytree(TEMPLATE, repo)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "fixture")
    return repo


def _fake_hledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / "hledger"
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")


def _invoke(repo: Path, *args: str) -> tuple[int, dict[str, object]]:
    result = RUNNER.invoke(app, ["books", "doctor", "--repo", str(repo), *args, "--json"])
    return result.exit_code, json.loads(result.output)


def _rules(payload: dict[str, object]) -> list[str]:
    findings = cast(list[dict[str, str]], payload["findings"])
    return [finding["rule"] for finding in findings]


def test_b1_doctor_repo_passes_on_template(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path)
    _fake_hledger(tmp_path, monkeypatch)
    code, payload = _invoke(repo)
    assert code == 0
    assert payload["safe_to_share"] is True
    assert not _rules(payload)
    assert payload["doctor"]["ran"] is True  # type: ignore[index]
    assert payload["doctor"]["exit_code"] == 0  # type: ignore[index]
    business = tmp_path / "business"
    (business / "core/finance").mkdir(parents=True)
    (business / "core/finance/books.md").write_text(
        f"---\nbooks_repo: {repo}\n---\n", encoding="utf-8"
    )
    discovered = RUNNER.invoke(app, ["books", "doctor", str(business), "--json"])
    assert discovered.exit_code == 0
    assert str(repo) not in discovered.output


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        ("status_missing", "rules_status_missing"),
        ("status_invalid", "rules_status_invalid"),
        ("evidence", "evidence_tracked"),
        ("manifest", "manifest_sha_missing"),
        ("commodity", "commodity_extra"),
        ("entrypoint", "entrypoint_missing"),
        ("accounts", "accounts_untyped"),
    ],
)
def test_b2_doctor_repo_names_each_broken_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str, rule: str
) -> None:
    repo = _repo(tmp_path)
    _fake_hledger(tmp_path, monkeypatch)
    rules = repo / "rules/sample-bank.csv.rules"
    accounts = repo / "2026-accounts.journal"
    if change == "status_missing":
        rules.write_text(
            rules.read_text().replace("Status: template/fallback", "State: template/fallback")
        )
    elif change == "status_invalid":
        rules.write_text(rules.read_text().replace("Status: template/fallback", "Status: unknown"))
    elif change == "evidence":
        (repo / "statement.pdf").write_bytes(b"statement")
        _git(repo, "add", "statement.pdf")
    elif change == "manifest":
        manifest = repo / "manifests/sources.csv"
        manifest.write_text(manifest.read_text().replace("a" * 64, "missing"))
    elif change == "commodity":
        accounts.write_text(accounts.read_text() + "commodity EUR\n")
    elif change == "entrypoint":
        (repo / "2026.journal").unlink()
    elif change == "accounts":
        accounts.write_text(accounts.read_text().replace("; type: A", ""))
    code, payload = _invoke(repo)
    assert code == 1
    assert _rules(payload) == [rule]


def test_b3_doctor_output_never_leaks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path)
    _fake_hledger(tmp_path, monkeypatch)
    doctor = repo / "bin/books"
    doctor.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' SECRET_PAYEE 123456789012\n"
        "printf '%s\\n' SECRET_PAYEE 123456789012 >&2\n"
        "exit 3\n"
    )
    for args in (("--json",), ()):
        result = RUNNER.invoke(app, ["books", "doctor", "--repo", str(repo), *args])
        assert result.exit_code == 1
        assert "SECRET_PAYEE" not in result.output
        assert "123456789012" not in result.output
    code, payload = _invoke(repo)
    assert code == 1
    assert payload["doctor"]["ran"] is True  # type: ignore[index]
    assert payload["doctor"]["exit_code"] == 3  # type: ignore[index]
    findings = cast(list[dict[str, str]], payload["findings"])
    assert [(item["rule"], item["level"]) for item in findings] == [("doctor_failed", "error")]
    human = RUNNER.invoke(app, ["books", "doctor", "--repo", str(repo)])
    assert "[error] doctor_failed" in human.output
    assert "exit 3" in human.output
    doctor.write_text("#!/bin/sh\nsleep 2\n")
    code, payload = _invoke(repo, "--doctor-timeout", "1")
    assert code == 1
    assert payload["doctor"]["timed_out"] is True  # type: ignore[index]


def test_b4_doctor_repo_is_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path)
    log = tmp_path / "commands.log"
    shims = tmp_path / "shims"
    shims.mkdir()
    real_git = shutil.which("git")
    assert real_git
    (shims / "git").write_text(f'#!/bin/sh\necho "git $*" >> "{log}"\nexec "{real_git}" "$@"\n')
    (shims / "hledger").write_text(f'#!/bin/sh\necho "hledger $*" >> "{log}"\nexit 0\n')
    for shim in shims.iterdir():
        shim.chmod(0o755)
    (repo / "bin/books").write_text(f'#!/bin/sh\necho "doctor $*" >> "{log}"\nexit 0\n')
    _git(repo, "commit", "-qam", "logging doctor")
    before = {
        str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in repo.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    status = _git(repo, "status", "--porcelain")
    original_run = subprocess.run
    commands: list[list[str]] = []

    def record_run(args: list[str], **kwargs: Any) -> Any:
        commands.append(args)
        return original_run(args, **kwargs)

    monkeypatch.setattr("mb.books_repo.subprocess.run", record_run)
    with monkeypatch.context() as path_env:
        path_env.setenv("PATH", f"{shims}:{os.environ['PATH']}")
        code, _ = _invoke(repo)
    monkeypatch.setattr("mb.books_repo.subprocess.run", original_run)
    after = {
        str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in repo.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    assert code == 0
    assert before == after
    assert status == _git(repo, "status", "--porcelain")
    assert commands == [
        ["git", "ls-files"],
        ["git", "rev-parse", "HEAD"],
        ["bin/books", "doctor"],
    ]
    ran = log.read_text().splitlines()
    assert "doctor doctor" in ran
    others = [line for line in ran if line != "doctor doctor"]
    assert others
    assert all(line.startswith(("git rev-parse", "git ls-files")) for line in others), others


def test_b5_no_hledger_host_reads_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(
        "mb.books.shutil.which", lambda name: None if name == "hledger" else shutil.which(name)
    )
    code, payload = _invoke(repo)
    assert code == 0
    assert payload["doctor"]["ran"] is False  # type: ignore[index]
    assert payload["doctor"]["status"] == "not_run"  # type: ignore[index]
    assert payload["doctor"]["level"] == "info"  # type: ignore[index]
    assert payload["doctor"]["reason"] == "hledger unavailable here"  # type: ignore[index]
    assert not [item for item in _rules(payload)]
    receipt = repo / "reports/doctor-receipt.json"
    data = json.loads(receipt.read_text())
    data["commit"] = _git(repo, "rev-parse", "HEAD")
    receipt.write_text(json.dumps(data))
    code, payload = _invoke(repo)
    assert code == 0 and payload["receipt"]["stale"] is False  # type: ignore[index]
    data["commit"] = "0" * 40
    receipt.write_text(json.dumps(data))
    code, payload = _invoke(repo)
    assert code == 0 and payload["receipt"]["stale"] is True  # type: ignore[index]
    data["private_secret"] = "SECRET_PAYEE"
    receipt.write_text(json.dumps(data))
    result = RUNNER.invoke(app, ["books", "doctor", "--repo", str(repo), "--json"])
    assert result.exit_code == 1
    assert "SECRET_PAYEE" not in result.output
    assert _rules(json.loads(result.output)) == ["receipt_invalid"]
