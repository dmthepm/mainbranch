"""Acceptance checks for the configured books doctor path."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from mb.cli import app

RUNNER = CliRunner()
TEMPLATE = Path(__file__).resolve().parents[1] / "mb/_data/books/repo-template"


def _business(tmp_path: Path, *, configured: bool = True) -> Path:
    repo = tmp_path / "business"
    repo.mkdir(parents=True)
    if configured:
        policy = repo / "core/finance/books.md"
        policy.parent.mkdir(parents=True)
        policy.write_text(
            "---\nstorage_mode: team-private-repo\nbooks_repo: ../books\n---\n",
            encoding="utf-8",
        )
    return repo


def _findings(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in payload["findings"]}


def _check(repo: Path) -> tuple[int, dict[str, Any]]:
    result = RUNNER.invoke(app, ["books", "check", str(repo), "--json"])
    return result.exit_code, json.loads(result.output)


def test_g1_books_check_names_configured_doctor_command(tmp_path: Path) -> None:
    repo = _business(tmp_path)
    command = "mb books doctor --repo ../books"
    human = RUNNER.invoke(app, ["books", "check", str(repo)])
    code, payload = _check(repo)
    pointer = _findings(payload)["books-skill-next-step"]
    assert code == human.exit_code == 0
    assert command in human.output
    assert command in pointer["operator_summary"]
    assert pointer["doctor_command"] == command
    assert "/mb-books" in pointer["operator_summary"]

    empty = _business(tmp_path / "empty", configured=False)
    _, empty_payload = _check(empty)
    assert _findings(empty_payload)["books-skill-next-step"] == {
        "id": "books-skill-next-step",
        "title": "Books next step",
        "state": "info",
        "detail": "Use /mb-books for the next books workflow.",
        "audience": "informational",
        "operator_summary": "Use /mb-books for bookkeeping setup.",
        "repair": "",
        "evidence": [],
    }

    books = tmp_path / "books"
    books.mkdir()
    (repo / "core/finance/books.md").write_text(
        "---\nstorage_mode: team-private-repo\nvault_location: ../books\n---\n",
        encoding="utf-8",
    )
    _, vault_payload = _check(repo)
    assert _findings(vault_payload)["books-skill-next-step"]["doctor_command"] == command


def test_g2_doctor_on_business_repo_points_to_books_repo(tmp_path: Path) -> None:
    repo = _business(tmp_path)
    books = tmp_path / "books"
    shutil.copytree(TEMPLATE, books)
    subprocess.run(["git", "init", "-q", str(books)], check=True)
    subprocess.run(["git", "-C", str(books), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(books),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    result = RUNNER.invoke(app, ["books", "doctor", "--repo", str(repo), "--json"])
    payload = json.loads(result.output)
    assert result.exit_code == 1
    assert [(item["rule"], item["level"]) for item in payload["findings"]] == [
        ("business_repo_not_books_repo", "warn")
    ]
    assert "../books" in payload["findings"][0]["operator_summary"]
    assert "mb books doctor --repo ../books" in payload["findings"][0]["operator_summary"]

    books_result = RUNNER.invoke(app, ["books", "doctor", "--repo", str(books), "--json"])
    assert books_result.exit_code == 0
    assert json.loads(books_result.output)["findings"] == []

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    (workspace / "README.md").write_text("# Workspace\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(workspace), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    workspace_result = RUNNER.invoke(app, ["books", "doctor", "--repo", str(workspace), "--json"])
    assert workspace_result.exit_code == 0
    assert [item["rule"] for item in json.loads(workspace_result.output)["findings"]] == [
        "workspace_repo"
    ]


def test_g3_no_vault_label_warning_when_books_repo_set(tmp_path: Path) -> None:
    repo = _business(tmp_path)
    _, payload = _check(repo)
    assert "books-vault-location-missing" not in _findings(payload)
    assert "set vault_location" not in json.dumps(payload).lower()
    status = RUNNER.invoke(app, ["books", "status", str(repo), "--json"])
    assert status.exit_code == 0
    status_payload = json.loads(status.output)
    assert status_payload["vault"]["configured"] is True
    assert "books-vault-location-missing" not in _findings(status_payload)

    policy = repo / "core/finance/books.md"
    policy.write_text("---\nstorage_mode: team-private-repo\n---\n", encoding="utf-8")
    _, missing = _check(repo)
    warning = _findings(missing)["books-vault-location-missing"]
    assert warning["state"] == "warn"
    assert "books_repo" in " ".join(
        str(warning[key]) for key in ("detail", "operator_summary", "repair")
    )


def test_g4_missing_thresholds_is_info(tmp_path: Path) -> None:
    repo = _business(tmp_path)
    code, payload = _check(repo)
    finding = _findings(payload)["books-money-path-thresholds-missing"]
    assert finding["state"] == "info"
    assert finding["title"] == "MoneyPath appetite thresholds are missing"
    assert finding["detail"] == (
        "core/finance/books.md does not declare money_path.appetite_thresholds. "
        "Main Branch can still run, but material bets should ask for thresholds before "
        "execution spend."
    )
    assert finding["operator_summary"] == (
        "Declare MoneyPath appetite thresholds before treating material spend as routed."
    )
    assert finding["repair"] == "Add money_path.appetite_thresholds to core/finance/books.md."
    assert code == 0

    policy = repo / "core/finance/books.md"
    policy.write_text("---\nstorage_mode: team-private-repo\n---\n", encoding="utf-8")
    missing_code, _ = _check(repo)
    assert missing_code == 0
