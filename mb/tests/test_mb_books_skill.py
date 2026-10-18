"""Acceptance checks for the books agent layer."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from mb import skill_validate
from mb.cli import app

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".claude/skills/mb-books/SKILL.md"
TEMPLATE = ROOT / "mb/mb/_data/books/repo-template"
MANIFEST = ROOT / "mb/mb/_data/release_simulations/manifest.json"
ROUTER = ROOT / ".claude/skills/mb-start/references/router-and-language.md"


def test_c1_mb_books_skill_is_bundled_and_valid() -> None:
    body = SKILL.read_text(encoding="utf-8")
    assert body.startswith("---\nname: mb-books\n")
    assert re.search(r"^description:", body, re.M)
    assert len(body.splitlines()) <= 300
    assert "mb-books" in CliRunner().invoke(app, ["skill", "list"]).output
    report = skill_validate.run("mb-books")
    assert report is not None and report["ok"], report


def test_c2_mb_books_hard_rules() -> None:
    lines = SKILL.read_text(encoding="utf-8").splitlines()
    required = (
        "never post or edit journal entries",
        "never run `hledger import` or `hledger add`",
        "never open or read evidence bytes",
        "never print or quote doctor stdout/stderr, payees, account numbers, "
        "amounts or tax IDs into the hub or chat",
        "rules edits are proposed as a diff for the operator to apply in the books repo",
        "hub repo keeps only safe summaries, decisions and links",
    )
    for phrase in required:
        assert any(phrase.lower() in line.lower() for line in lines), phrase
    body = "\n".join(lines)
    assert "mb books check" in body
    assert "mb books doctor --repo" in body


def test_c3_mb_start_routes_books_to_mb_books() -> None:
    router = ROUTER.read_text(encoding="utf-8")
    section = router.split("### Bookkeeping, books, finance, accounting", 1)[1].split(
        "### Provider and tool setup", 1
    )[0]
    for token in (
        "/mb-books",
        "mb books check",
        "money_path",
        "/mb-bet",
        "restricted",
        "local_only",
        "storage_mode",
    ):
        assert token in section


def test_c4_books_template_has_cold_start_agents_md(tmp_path: Path) -> None:
    agents = TEMPLATE / "AGENTS.md"
    body = agents.read_text(encoding="utf-8")
    assert "MB-FIXTURE" in body[:1024]
    for token in (
        "pull --rebase",
        "one writer",
        "bin/books doctor",
        "SHA-256",
        "manifests/",
        "docs/blockers.md",
    ):
        assert token in body
    repo = tmp_path / "books"
    shutil.copytree(TEMPLATE, repo)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    result = CliRunner().invoke(app, ["books", "doctor", "--repo", str(repo), "--json"])
    report = json.loads(result.output)
    assert not [finding for finding in report["findings"] if finding["rule"].startswith("shape")]


def test_c5_books_close_simulation_registered() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    matches = [sim for sim in manifest["simulations"] if sim["id"] == "books-close"]
    assert len(matches) == 1
    sim = matches[0]
    assert sim["label"] == "books-close"
    assert sim["fixture_profile"] == "fresh_sanitized_business_repo"
    assert sim["tiers"] == ["prerelease_candidate", "release_acceptance"]
    assert "/mb-books" in " ".join(sim["must_observe"])
    assert "mb books check" in " ".join(sim["must_observe"])
    assert "entries" in " ".join(sim["must_not"])
    assert "evidence" in " ".join(sim["must_not"])
