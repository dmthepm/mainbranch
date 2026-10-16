"""Old business records left on another Git branch."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from mb import fleet_checkin, ranker, status
from mb.cli import app
from mb.init import run as init_run

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def git(repo: Path, *args: str, days_ago: int | None = None) -> str:
    env = os.environ.copy()
    if days_ago is not None:
        stamp = (NOW - timedelta(days=days_ago)).isoformat()
        env["GIT_AUTHOR_DATE"] = stamp
        env["GIT_COMMITTER_DATE"] = stamp
    result = subprocess.run(
        ["git", *args], cwd=repo, env=env, text=True, capture_output=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def repo_with_branch(tmp_path: Path, *, path: str = "bets/x.md", days_ago: int = 4) -> Path:
    repo = tmp_path / "business"
    repo.mkdir(parents=True)
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("Business\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "-m", "start", days_ago=10)
    git(repo, "checkout", "-b", "feature/record")
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("record\n")
    git(repo, "add", path)
    git(repo, "commit", "-m", "record", days_ago=days_ago)
    git(repo, "checkout", "main")
    return repo


def gap(repo: Path) -> dict[str, Any] | None:
    return status._stranded_record_gap(repo, status._git_info(repo), now=NOW)


def test_old_record_on_side_branch_reaches_status_json_and_consumers(tmp_path: Path) -> None:
    repo = repo_with_branch(tmp_path)
    found = gap(repo)
    assert found is not None
    assert found["id"] == "records_stranded_on_branches"
    assert found["severity"] == "warn"
    assert found["records"] == [
        {
            "branch": "feature/record",
            "current": False,
            "files": ["bets/x.md"],
            "files_total": 1,
            "age_days": 4,
            "commits_capped": False,
        }
    ]
    report = status.run(path=str(repo), now=NOW, update_marker=False)
    encoded = json.loads(json.dumps(report))
    assert encoded["relationship_health"]["gaps"][0] == found
    assert encoded["relationship_health"]["summary"]["warnings"] >= 1
    ranked = ranker.rank_status_report(encoded, limit=10)
    relationship_action = next(
        item for item in ranked if item["id"] == "review_relationship_health"
    )
    assert relationship_action["severity"] == "warn"
    assert relationship_action["reason"] == found["summary"]
    assert relationship_action["score"] >= 85
    assert found["repair"] in encoded["readiness"]["next_actions"]
    loop = fleet_checkin._loop_section(encoded, NOW.date().isoformat())
    assert loop["top_gap"]["id"] == "records_stranded_on_branches"
    assert isinstance(encoded["git"], dict)
    cli = CliRunner().invoke(app, ["status", str(repo), "--json", "--peek"])
    assert cli.exit_code == 0
    cli_report = json.loads(cli.stdout)
    assert cli_report["relationship_health"]["gaps"][0]["id"] == found["id"]
    assert cli_report["git"]["branch"] == "main"


def test_recent_merged_and_non_record_branches_do_not_warn(tmp_path: Path) -> None:
    recent = repo_with_branch(tmp_path / "recent", days_ago=1)
    assert gap(recent) is None
    merged = repo_with_branch(tmp_path / "merged")
    git(merged, "merge", "--no-ff", "feature/record", "-m", "merge")
    assert gap(merged) is None
    other = repo_with_branch(tmp_path / "other", path="notes/x.md")
    assert gap(other) is None


def test_remote_tracking_ref_deduplicates_local_branch(tmp_path: Path) -> None:
    repo = repo_with_branch(tmp_path)
    git(repo, "update-ref", "refs/remotes/origin/feature/record", "refs/heads/feature/record")
    found = gap(repo)
    assert found is not None
    assert found["count"] == 1
    assert found["evidence"] == ["feature/record"]


def test_remote_changes_are_included_in_deduplicated_branch(tmp_path: Path) -> None:
    repo = repo_with_branch(tmp_path)
    old_head = git(repo, "rev-parse", "feature/record")
    git(repo, "checkout", "feature/record")
    target = repo / "research" / "remote.md"
    target.parent.mkdir()
    target.write_text("remote record\n")
    git(repo, "add", "research/remote.md")
    git(repo, "commit", "-m", "remote record", days_ago=4)
    git(repo, "update-ref", "refs/remotes/origin/feature/record", "HEAD")
    git(repo, "checkout", "main")
    git(repo, "update-ref", "refs/heads/feature/record", old_head)
    found = gap(repo)
    assert found is not None
    assert found["count"] == 1
    assert found["records"][0]["files"] == ["bets/x.md", "research/remote.md"]


def test_default_remote_already_contains_record(tmp_path: Path) -> None:
    repo = repo_with_branch(tmp_path)
    git(repo, "update-ref", "refs/remotes/origin/main", "refs/heads/feature/record")
    assert gap(repo) is None


def test_current_branch_is_included(tmp_path: Path) -> None:
    repo = repo_with_branch(tmp_path)
    git(repo, "checkout", "feature/record")
    found = gap(repo)
    assert found is not None
    assert found["records"][0]["current"] is True
    assert "current branch" in str(found["summary"])


def test_non_git_and_detached_head_do_not_warn(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert gap(empty) is None
    repo = repo_with_branch(tmp_path / "detached")
    git(repo, "checkout", "--detach", "main")
    assert gap(repo) is None


def test_scan_marks_branch_and_commit_limits(tmp_path: Path, monkeypatch) -> None:
    repo = repo_with_branch(tmp_path)
    git(repo, "checkout", "feature/record")
    target = repo / "decisions" / "y.md"
    target.parent.mkdir()
    target.write_text("decision\n")
    git(repo, "add", "decisions/y.md")
    git(repo, "commit", "-m", "decision", days_ago=4)
    git(repo, "checkout", "main")
    git(repo, "branch", "another", "feature/record")
    monkeypatch.setattr(status, "STRANDED_BRANCH_LIMIT", 1)
    monkeypatch.setattr(status, "STRANDED_COMMIT_LIMIT", 1)
    found = gap(repo)
    assert found is not None
    assert found["branches_capped"] is True
    assert found["commits_capped"] is True


def test_git_scan_failure_drops_warning(tmp_path: Path, monkeypatch) -> None:
    repo = repo_with_branch(tmp_path)
    info = status._git_info(repo)
    real_run = status._run_command

    def fail_log(args: list[str], **kwargs):
        if args[:2] == ["git", "log"]:
            return {"ok": False, "stdout": "", "stderr": "timed out"}
        return real_run(args, **kwargs)

    monkeypatch.setattr(status, "_run_command", fail_log)
    assert status._stranded_record_gap(repo, info, now=NOW) is None


def test_existing_gap_output_matches_base_when_no_stranded_branch(tmp_path: Path) -> None:
    """Expected values captured from the 260039fe implementation."""
    repo = tmp_path / "business"
    init_run(path=str(repo), name="Test")
    (repo / "bets" / "x.md").write_text(
        "---\nstatus: open\nopened: 2026-10-10\ndeadline: 2027-10-15\n---\n# X\n"
    )
    report = status.run(path=str(repo), now=NOW, update_marker=False)
    assert [item["id"] for item in report["relationship_health"]["gaps"]] == [
        "active_bets_without_push"
    ]
    action = next(
        item for item in report["ranked_actions"] if item["id"] == "review_relationship_health"
    )
    assert (action["score"], action["reason"]) == (85, "1 active bet(s) need a linked push.")
    assert (
        "Link each active bet to the push that supports it, or add the reverse "
        "`linked_bets` field on that push."
    ) in report["readiness"]["next_actions"]
    assert fleet_checkin._loop_section(report, NOW.date().isoformat())["text"] == (
        "Ready to work. Links: 1 active bet needs a linked push."
    )
