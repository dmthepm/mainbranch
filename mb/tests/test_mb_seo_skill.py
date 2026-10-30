"""Acceptance checks for the SEO agent layer."""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from mb import codex as codex_mod
from mb import skill_validate
from mb.cli import app

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / ".claude/skills/mb-seo"
SKILL = SKILL_DIR / "SKILL.md"
SETUP = SKILL_DIR / "references/setup.md"
DAILY = SKILL_DIR / "references/daily-use.md"
UPGRADES = SKILL_DIR / "references/upgrades-and-backups.md"
DECISION = ROOT / "decisions/2026-10-30-openseo-chosen-optional-seo-tool.md"
DEPENDENCIES = ROOT / "docs/dependency-choices.md"
PIN = "beca5c1f5c728acfb243249107dbfaded0ef552e"


def _flat(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _all_skill_text() -> str:
    return " ".join(_flat(path) for path in (SKILL, SETUP, DAILY, UPGRADES))


def test_skill_is_bundled_and_valid() -> None:
    body = SKILL.read_text(encoding="utf-8")
    assert body.startswith("---\nname: mb-seo\n")
    assert len(body.splitlines()) <= 300
    assert "mb-seo" in CliRunner().invoke(app, ["skill", "list"]).output
    report = skill_validate.run("mb-seo")
    assert report is not None and report["ok"], report


def test_first_response_offers_useful_work_before_setup() -> None:
    body = " ".join(SKILL.read_text(encoding="utf-8").replace("> ", "").split())
    assert (
        "Give me your site and what you want SEO to improve. I'll review the public "
        "pages and suggest the first useful changes. For keyword and competitor data, "
        "we can set up OpenSEO, our chosen optional SEO tool. That needs accounts and "
        "may incur data charges."
    ) in body
    assert "Do not hold the review until setup." in body
    assert "They do not show rankings, search volume, traffic" in body


def test_hard_rules_stay_in_the_skill() -> None:
    body = _flat(SKILL)
    for rule in (
        "One OpenSEO copy per business",
        "No shared keys",
        "no binding to any existing service",
        "MCP read-only hints are not a spend limit",
        "`mb` cannot enforce this",
        "Keep rank and AI-visibility schedules off unless the owner approves them",
        "Keep Cloudflare Access on",
        "Deploy only a reviewed release SHA",
        "Never run `alchemy destroy`",
        "Never print a secret",
        "Owner-run steps stay with the owner",
    ):
        assert rule in body, rule


def test_setup_forces_access_over_the_password_template() -> None:
    body = _flat(SETUP)
    assert "The template turns on password accounts" in body
    assert "AUTH_MODE=cloudflare_access" in SETUP.read_text(encoding="utf-8")
    assert "grep -q '^AUTH_MODE=cloudflare_access$' .env.selfhost" in body
    assert "Do not recopy the example env file" in _flat(UPGRADES)


def test_setup_pins_and_writes_access_as_requirements() -> None:
    text = SETUP.read_text(encoding="utf-8")
    assert text.count(PIN) >= 3
    assert "| Requirement | How to check | Expected result |" in text
    assert "**Expected:**" in text
    assert "NOT VERIFIED" in text
    flat = _flat(SETUP)
    assert "issue 304" in flat
    assert "&resource=<URL-encoded MCP URL>" in flat
    assert "cut it at the first BEL" in flat
    assert "A 401 alone proves nothing." in flat
    assert "It does not authorize a user" in flat
    assert "never a broad wildcard" in flat
    assert "no Bypass rule, no Everyone rule" in flat
    assert "Do not run keyword, rank, prompt, or AI checks as tests." in flat


def test_setup_uses_connect_and_keeps_logs_private() -> None:
    flat = _flat(SETUP)
    assert "mb connect cloudflare-openseo --custom --token-stdin" in flat
    assert "mb connect exec cloudflare-openseo" in flat
    assert '--profile "$PROFILE" >"<PRIVATE_LOGS>/deploy.log" 2>&1' in flat
    assert "ALCHEMY_PROFILE=" not in flat
    assert "--print" not in flat
    assert "cat .env" not in flat


def test_google_is_later_and_per_business() -> None:
    text = _flat(SETUP)
    later = text.index("## Later: Google")
    assert "GOOGLE_CLIENT_ID" in text[later:]
    assert "GOOGLE_CLIENT_ID" not in text[:later]
    assert "Each business needs its own Google client" in text
    assert "do not, because each deploy replaces dashboard values" in text


def test_daily_use_covers_paid_approval_and_default_schedule() -> None:
    body = _flat(DAILY)
    assert "Wait for a yes." in body
    assert "`research_ai_visibility_prompts` is marked read-only and still spends" in body
    assert "New AI-visibility trackers start on a weekly schedule." in body


def test_backup_limits_are_stated() -> None:
    body = _flat(UPGRADES)
    assert "A D1 export is not a full backup" in body
    assert "No restore drill has passed" in body
    assert "Never run `alchemy destroy`" in body
    assert "<DEPLOYED_D1_UUID>" in body


def test_no_private_or_internal_details() -> None:
    text = _all_skill_text() + _flat(DECISION)
    assert not re.search(r"(/home/|/Users/|\.ts\.net|tskey-)", text), "machine detail"
    assert not re.search(r"\b[0-9a-f]{32}\b", text), "account or resource ID"
    assert not re.search(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-", text), "resource UUID"
    emails = set(re.findall(r"[\w.+-]+@[\w.-]+\.\w+", text))
    assert emails <= {"owner@example.com"}, emails


def test_support_stays_experimental_and_codex_unsupported() -> None:
    assert "**experimental**" in SKILL.read_text(encoding="utf-8")
    assert "Codex is not supported" in _flat(SKILL)
    assert codex_mod.CODEX_GLOBAL_SKILL_SUPPORT["mb-seo"] == "intentionally_unsupported"
    decision = _flat(DECISION)
    assert "**Support is experimental.**" in decision
    assert "one copy per business" in decision.lower()
    assert "Exit Path" in decision
    dependencies = _flat(DEPENDENCIES)
    assert "Chosen SEO tool for `/mb-seo`; optional; experimental" in dependencies
    assert "| Chosen; optional; one copy per business; experimental |" in dependencies


def test_router_reaches_the_skill() -> None:
    router = (ROOT / ".claude/skills/mb-start/references/router-and-language.md").read_text(
        encoding="utf-8"
    )
    assert "OpenSEO: `/mb-seo`" in router
    assert "OpenSEO | Route to `/mb-seo`" in (ROOT / ".claude/skills/mb-help/SKILL.md").read_text(
        encoding="utf-8"
    )


def test_setup_never_copies_the_password_template() -> None:
    flat = _flat(SETUP)
    assert "cp deploy/.env.selfhost.example" not in flat
    assert "Do not copy `deploy/.env.selfhost.example`." in flat
    assert flat.index("Owner: prepare DataForSEO") < flat.index("Owner: prepare Cloudflare")


def test_weekly_review_is_free_and_read_only() -> None:
    weekly = SETUP.with_name("search-review.md")
    flat = _flat(weekly)
    assert "mb google sc query" in flat
    assert "No paid calls." in flat
    assert "Five actions at most." in flat


def test_ai_agents_reference_is_routed_and_makes_no_promises() -> None:
    reference = SETUP.with_name("ai-agents.md")
    skill = SETUP.parents[1] / "SKILL.md"
    assert "[references/ai-agents.md](references/ai-agents.md)" in skill.read_text(encoding="utf-8")
    assert "Never promise citations or AI traffic." in _flat(skill)
    flat = _flat(reference)
    assert "Never promise citations or AI traffic." in flat
    assert "The owner approves every site edit." in flat
