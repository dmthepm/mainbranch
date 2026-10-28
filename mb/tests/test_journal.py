"""Business-readable git journal tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from mb import journal as journal_mod
from mb.init import run as init_run


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )


def _business_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "add", ".")
    result = _git(repo, "commit", "--no-verify", "-m", "[added] business scaffold")
    assert result.returncode == 0, result.stderr
    return repo


def _commit(repo: Path, relative_path: str, content: str, subject: str, body: str = "") -> None:
    target = repo / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    result = _git(repo, "add", relative_path)
    assert result.returncode == 0, result.stderr
    args = ["commit", "--no-verify", "-m", subject]
    if body:
        args.extend(["-m", body])
    result = _git(repo, *args)
    assert result.returncode == 0, result.stderr


def test_parse_refs_supports_business_objects_and_github_issues() -> None:
    refs = journal_mod.parse_refs(
        "\n".join(
            [
                "Changed:",
                "- pushes/workshop/push.md",
                "",
                "Refs:",
                "- bets/2026-05-06-workshop.md",
                "- pushes/workshop/push.md",
                "- decisions/2026-05-05-price.md",
                "- campaigns/legacy/campaign.md",
                "- https://github.com/dmthepm/mainbranch/issues/303",
            ]
        )
    )

    assert [item["kind"] for item in refs] == [
        "bet",
        "push",
        "decision",
        "legacy_campaign",
        "github_issue",
    ]
    assert refs[0]["slug"] == "2026-05-06-workshop"
    assert refs[1]["slug"] == "workshop"
    assert refs[3]["legacy"] is True
    assert refs[4]["number"] == 303


def test_parse_refs_stops_at_lowercase_body_header() -> None:
    refs = journal_mod.parse_refs("Refs:\n- pushes/workshop/push.md\nnotes:\n- not a ref\n")

    assert len(refs) == 1
    assert refs[0]["kind"] == "push"
    assert refs[0]["path"] == "pushes/workshop/push.md"


def test_event_from_commit_does_not_recognize_conventional_commit_type() -> None:
    event = journal_mod.event_from_commit(
        {
            "sha": "abc123",
            "commit": "abc123",
            "date": "2026-05-22",
            "authored_at": "2026-05-22",
            "subject": "docs: setup guide",
            "body": "",
        },
        ["core/offer.md"],
    )

    assert event["recognized_as"] == "unrecognized"
    assert event["verb"] is None
    assert event["loop"] is None
    assert event["loops"] == []
    assert event["channel"] is None
    assert event["target_kind"] == "work"


def test_collect_groups_business_commits_and_preserves_legacy_checkpoints(tmp_path: Path) -> None:
    repo = _business_repo(tmp_path)
    _commit(
        repo,
        "bets/2026-05-06-workshop.md",
        "# Workshop bet\n",
        "[opened] bet workshop -- target 40 signups",
        "Refs:\n- bets/2026-05-06-workshop.md\n- #303",
    )
    _commit(
        repo,
        "pushes/workshop/push.md",
        "# Workshop push\n",
        "[shipped] workshop lander",
        "Refs:\n- pushes/workshop/push.md\n- decisions/2026-05-05-price.md",
    )
    _commit(
        repo,
        "core/offer.md",
        "# Offer\nUpdated\n",
        "[checkpoint] Update offer",
    )

    report = journal_mod.collect(repo, limit=5, since=None)

    assert report["ok"] is True
    assert report["schema_version"] == "0.current"
    assert report["summary"]["recognized_events"] >= 3
    assert report["summary"]["legacy_checkpoints"] == 1
    legacy = next(
        event for event in report["events"] if event["recognized_as"] == "legacy_checkpoint"
    )
    assert legacy["summary"] == "Saved checkpoint: Update offer"
    shipped = next(event for event in report["events"] if event["verb"] == "shipped")
    assert shipped["loop"] == "ship"
    assert shipped["target_kind"] == "push"
    assert any(ref["kind"] == "push" for ref in shipped["refs"])
    assert any(group["loop"] == "decide" for group in report["groups"])
    assert any(group["loop"] == "ship" for group in report["groups"])
