"""Acceptance checks for the public, synthetic books workflow."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mb import books as books_mod
from mb.cli import app

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "mb/mb/_data/books/repo-template"
DECISION = ROOT / "decisions/2026-10-18-books-statement-anchored-workflow.md"
WORKFLOW = ROOT / "docs/books-workflow.md"
ENTRYPOINT = TEMPLATE / "2026.journal"
CHECK = TEMPLATE / "checks/2026-close.journal"


def test_a1_books_template_passes_hledger_strict(tmp_path: Path) -> None:
    assert ENTRYPOINT.is_file()
    assert CHECK.is_file()
    assert (TEMPLATE / "bin/books").is_file()
    if not shutil.which("hledger"):
        pytest.skip("hledger is not installed")

    for journal in (ENTRYPOINT, CHECK):
        for check in ("", "ordereddates"):
            command = ["hledger", "-f", str(journal), "check", "--strict"]
            if check:
                command.append(check)
            result = subprocess.run(
                command, cwd=TEMPLATE, capture_output=True, text=True, check=False
            )
            assert result.returncode == 0, f"{' '.join(command)}: {result.stderr}"

    doctor = subprocess.run(
        ["/bin/sh", "bin/books", "doctor"],
        cwd=TEMPLATE,
        capture_output=True,
        text=True,
        check=False,
    )
    assert doctor.returncode == 0, doctor.stderr

    sample_csv = tmp_path / "sample-bank-2026-01.csv"
    sample_csv.write_text(
        "2026-01-02,Sample sale,50,50\n2026-01-31,Sample supplies,-20,30\n",
        encoding="utf-8",
    )
    from_rules = subprocess.run(
        [
            "hledger",
            "-f",
            str(sample_csv),
            "--rules-file",
            str(TEMPLATE / "rules/sample-bank.csv.rules"),
            "print",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    from_journal = subprocess.run(
        ["hledger", "-f", str(TEMPLATE / "imports/sample-bank/2026-01.journal"), "print"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert from_rules.returncode == 0, from_rules.stderr
    assert from_journal.returncode == 0, from_journal.stderr
    assert from_rules.stdout == from_journal.stdout


def test_a2_books_template_is_fixture_marked_and_not_a_leak(tmp_path: Path) -> None:
    assert TEMPLATE.is_dir()
    files = [path for path in TEMPLATE.rglob("*") if path.is_file()]
    assert files
    assert all(b"MB-FIXTURE" in path.read_bytes()[:1024] for path in files)

    business = tmp_path / "business"
    business.mkdir()
    shutil.copytree(TEMPLATE, business / "sample-books")
    subprocess.run(["git", "init", "-q"], cwd=business, check=True)
    subprocess.run(["git", "add", "-A"], cwd=business, check=True)
    report = books_mod.run(repo=str(business))
    assert "unsafe-paths-detected" not in {finding["id"] for finding in report["findings"]}


def test_a3_books_workflow_docs_are_linked_and_clean() -> None:
    assert DECISION.is_file()
    assert WORKFLOW.is_file()
    assert "books-workflow.md" in (ROOT / "docs/books.md").read_text(encoding="utf-8")
    assert "2026-05-11-mb-books-foundation.md" in DECISION.read_text(encoding="utf-8")

    files = [DECISION, WORKFLOW, *(path for path in TEMPLATE.rglob("*") if path.is_file())]
    for path in files:
        body = path.read_text(encoding="utf-8")
        assert not re.search(r"\d{9,}", body), path
        assert not re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", body), path
        assert not re.search(r"(?<!\w)@[A-Za-z][\w-]+", body), path
        assert not re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", body), path
        assert not re.search(r"\.ts\.net\b|\.local\b|finance-archive", body, re.I), path
        assert not re.search(
            r"\b(?:1099|1120|1065|W-2|S-corp|C-corp|LLC|sole proprietor)\b", body, re.I
        ), path
        amounts = re.findall(r"\$\s*-?\d[\d,.]*", body)
        if path in (DECISION, WORKFLOW):
            assert not amounts, path
        else:
            assert all(
                re.fullmatch(r"\$\s*-?(?:0|[1-9]\d*0)(?:\.00)?", amount) for amount in amounts
            ), path


def test_a4_educational_books_close_topic() -> None:
    result = CliRunner().invoke(app, ["educational", "books-close"])
    assert result.exit_code == 0, result.output
    assert "docs/books-workflow.md" in result.output
    source = ROOT / ".claude/educational/books-close.md"
    fallback = ROOT / "mb/mb/_data/educational/books-close.md"
    assert source.read_bytes() == fallback.read_bytes()
