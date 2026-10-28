"""Privacy-safe GitHub issue draft tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mb import issue as issue_mod
from mb.cli import app

runner = CliRunner()


def test_scrub_text_redacts_paths_tokens_env_and_email() -> None:
    raw = """
API_TOKEN=super-secret
Traceback File "/Users/alex/business/core/offer.md", line 4
Authorization: Bearer abcdefghijklmnop
https://example.com/callback?token=abc123
customer@example.com
--token=plain-secret
"""

    scrubbed = issue_mod.scrub_text(raw)

    assert "super-secret" not in scrubbed.text
    assert "/Users/alex" not in scrubbed.text
    assert "abcdefghijklmnop" not in scrubbed.text
    assert "abc123" not in scrubbed.text
    assert "customer@example.com" not in scrubbed.text
    assert "plain-secret" not in scrubbed.text
    assert scrubbed.redactions["sensitive_env"] == 2
    assert scrubbed.redactions["local_path"] == 1
    assert scrubbed.redactions["token"] == 1
    assert scrubbed.redactions["url_secret"] == 1
    assert scrubbed.redactions["email"] == 1


def test_issue_draft_bug_creates_local_gitignored_scrubbed_draft(tmp_path: Path) -> None:
    repo = tmp_path / "biz"
    (repo / "core" / "finance").mkdir(parents=True)
    secret_path = tmp_path / "biz" / "core" / "offer.md"

    result = runner.invoke(
        app,
        [
            "issue",
            "draft",
            "bug",
            "--repo",
            str(repo),
            "--title",
            "bug: checkout failure for customer@example.com",
            "--command",
            "mb status",
            "--what-happened",
            f"failed at {secret_path} with API_KEY=abc123",
            "--expected",
            "status should render",
            "--diagnostics",
            "Bearer abcdefghijklmnop",
            "--no-doctor",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    draft = Path(payload["path"])
    body = draft.read_text(encoding="utf-8")
    assert draft.exists()
    assert ".mb/issue-drafts/" in (repo / ".gitignore").read_text(encoding="utf-8")
    assert "customer@example.com" not in body
    assert str(secret_path) not in body
    assert "API_KEY=abc123" not in body
    assert "abcdefghijklmnop" not in body
    assert "<local-path>" in body
    assert payload["privacy"]["requires_operator_review"] is True
    assert payload["redactions"]["email"] == 1
    assert payload["redactions"]["local_path"] >= 1
    assert payload["next_command"].startswith("mb issue open .mb/issue-drafts/")


def test_issue_draft_supports_feature_and_question_shapes(tmp_path: Path) -> None:
    feature_repo = tmp_path / "feature-repo"
    question_repo = tmp_path / "question-repo"
    feature_repo.mkdir()
    question_repo.mkdir()

    feature = issue_mod.create_draft(
        repo=str(feature_repo),
        kind="feature",
        title="feat: make update clearer",
        fields={
            "problem": "I cannot tell what changed.",
            "surface": "CLI subcommand",
            "proposal": "Add a summary.",
            "alternatives": "Read the changelog manually.",
        },
        include_doctor=False,
    )
    question = issue_mod.create_draft(
        repo=str(question_repo),
        kind="question",
        title="question: when should I use status?",
        fields={
            "question": "When should I run mb status?",
            "context": "I am starting the day.",
            "tried": "I read the README.",
        },
        include_doctor=False,
    )

    assert feature["kind"] == "feature"
    assert feature["labels"] == ["enhancement", "triage"]
    assert "## Problem statement" in Path(feature["path"]).read_text(encoding="utf-8")
    assert question["kind"] == "question"
    assert question["labels"] == ["question", "triage"]
    assert "## What you've tried" in Path(question["path"]).read_text(encoding="utf-8")


def test_issue_draft_requires_existing_repo(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="repo not found"):
        issue_mod.create_draft(
            repo=str(tmp_path / "missing"),
            kind="bug",
            title="bug: missing repo",
            fields={"command": "mb status"},
            include_doctor=False,
        )


def test_issue_draft_degrades_when_doctor_fails(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def fail_doctor(path: str) -> dict[str, object]:
        raise RuntimeError("failed at /Users/alex/business with token=secret")

    monkeypatch.setattr(issue_mod.doctor_mod, "run", fail_doctor)  # type: ignore[attr-defined]

    result = issue_mod.create_draft(
        repo=str(repo),
        kind="bug",
        title="bug: doctor failure",
        fields={"command": "mb doctor", "happened": "doctor crashed"},
    )

    body = Path(result["path"]).read_text(encoding="utf-8")
    assert result["ok"] is True
    assert "mb doctor --json could not run" in body
    assert "/Users/alex" not in body
    assert "token=secret" not in body
    assert "`mb issue draft bug --no-doctor`" in body


def test_issue_open_requires_yes_and_returns_manual_fallback(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    draft = issue_mod.create_draft(
        repo=str(repo),
        kind="bug",
        title="bug: fallback",
        fields={"command": "mb doctor", "happened": "failed", "expected": "pass"},
        include_doctor=False,
    )

    result = issue_mod.open_draft(draft["path"], yes=False)

    assert result["ok"] is True
    assert result["submitted"] is False
    assert "pass --yes" in result["reason"]
    assert "manual_url" in result


def test_issue_open_submits_with_gh_when_reviewed(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    draft = issue_mod.create_draft(
        repo=str(repo),
        kind="question",
        title="question: submit",
        fields={"question": "How?", "context": "Testing.", "tried": "A draft."},
        include_doctor=False,
    )
    calls: list[list[str]] = []

    def fake_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[:3] == ["gh", "auth", "status"]:
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            args,
            0,
            stdout="https://github.com/dmthepm/mainbranch/issues/999\n",
            stderr="",
        )

    monkeypatch.setattr(issue_mod.shutil, "which", lambda name: "/usr/bin/gh")  # type: ignore[attr-defined]

    result = issue_mod.open_draft(draft["path"], yes=True, runner=fake_runner)

    assert result["submitted"] is True
    assert result["url"].endswith("/999")
    create_call = calls[-1]
    assert create_call[:3] == ["gh", "issue", "create"]
    assert "--label" in create_call
    assert "question" in create_call


def test_issue_open_gh_create_failure_keeps_manual_fallback(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    draft = issue_mod.create_draft(
        repo=str(repo),
        kind="bug",
        title="bug: submit failure",
        fields={"command": "mb doctor", "happened": "failed", "expected": "pass"},
        include_doctor=False,
    )

    def fake_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "auth", "status"]:
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="label not found")

    monkeypatch.setattr(issue_mod.shutil, "which", lambda name: "/usr/bin/gh")  # type: ignore[attr-defined]

    result = issue_mod.open_draft(draft["path"], yes=True, runner=fake_runner)

    assert result["ok"] is False
    assert result["submitted"] is False
    assert result["fallback"] is True
    assert result["reason"] == "label not found"
    assert result["manual_steps"]
