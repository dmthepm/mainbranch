"""Acceptance checks for the books agent layer."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from mb import skill_validate
from mb.cli import app
from tests.test_books_workflow import (
    test_a2_books_template_is_fixture_marked_and_not_a_leak,
    test_a3_books_workflow_docs_are_linked_and_clean,
)

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".claude/skills/mb-books/SKILL.md"
TEMPLATE = ROOT / "mb/mb/_data/books/repo-template"
MANIFEST = ROOT / "mb/mb/_data/release_simulations/manifest.json"
ROUTER = ROOT / ".claude/skills/mb-start/references/router-and-language.md"
SHAPE_RULES = {
    "entrypoint_missing",
    "accounts_untyped",
    "rules_status_missing",
    "rules_status_invalid",
    "evidence_tracked",
    "manifest_sha_missing",
    "commodity_extra",
}
# First 16 hex of sha256(json.dumps(simulation, sort_keys=True)) per simulation at 681b4fd1.
BASE_SIMULATIONS = {
    "fresh_first_day": "c95387af67581d8d",
    "messy_morning_thought_dump": "12c88919808a4e28",
    "ambiguous_mb_start_offer_choice": "ed6be5d75f1f2c8f",
    "rich_migration_triage_map": "d4df434dd4110112",
    "ask_before_writing_decision": "1485ebd1b8eaf4ab",
    "writing_skill_without_silent_saves": "64dd2e93cf736545",
    "offer_launch_orchestration": "8896c20e02cf5746",
    "conversion_video_natural_prompt_routing": "3a49461bc9dca579",
    "bookkeeping_safety_handoff": "d8a47a44bb4e430b",
    "checkpoint_discipline": "efd0108579712a57",
    "broken_runtime_wiring_shadow_repair": "3ac29cdb887f5700",
    "private_data_refusal": "d755e5acf730ca11",
    "legacy_repo_drift": "15f19ee21fffee30",
    "keychain_prompt_pending_repair": "a7c414f672a39854",
    "channel_trial_new_bet": "97a5325fb1c2d5b2",
    "channel_trial_existing_bet": "624e461512086193",
    "routine_channel_task_no_bet": "ec0f3d202bedd0ac",
    "observation_readout_only": "81a7cb87f2306e5d",
    "observation_changed_course": "e92618a46118cdd5",
    "status_only_no_record": "bbab3bcdb183f0ba",
}


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
    assert not [finding for finding in report["findings"] if finding["rule"] in SHAPE_RULES]
    # The slice A deny-list and leak checks cover every template file, AGENTS.md included.
    (tmp_path / "a2").mkdir()
    test_a2_books_template_is_fixture_marked_and_not_a_leak(tmp_path / "a2")
    test_a3_books_workflow_docs_are_linked_and_clean()


def test_c5_books_close_simulation_registered() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sims = manifest["simulations"]
    ids = [sim["id"] for sim in sims]
    assert len(ids) == len(set(ids))
    assert set(ids) - set(BASE_SIMULATIONS) == {"books-close"}
    assert set(BASE_SIMULATIONS) <= set(ids)
    for sim in sims:
        if sim["id"] in BASE_SIMULATIONS:
            digest = hashlib.sha256(json.dumps(sim, sort_keys=True).encode()).hexdigest()[:16]
            assert digest == BASE_SIMULATIONS[sim["id"]], sim["id"]
    matches = [sim for sim in sims if sim["id"] == "books-close"]
    assert len(matches) == 1
    sim = matches[0]
    assert sim["label"] == "books-close"
    assert sim["fixture_profile"] == "books_repo_fixture"
    assert sim["tiers"] == ["prerelease_candidate", "release_acceptance"]
    assert "/mb-books" in " ".join(sim["must_observe"])
    assert "mb books check" in " ".join(sim["must_observe"])
    assert "entries" in " ".join(sim["must_not"])
    assert "evidence" in " ".join(sim["must_not"])
