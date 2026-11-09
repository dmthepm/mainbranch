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
PIN = "7d89cfb3ca30b2819356c57c5b746a1048b9743f"
HARDENING = SKILL_DIR / "references/access-hardening.md"


def _flat(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _skill_markdown() -> list[Path]:
    return sorted(SKILL_DIR.rglob("*.md"))


def _all_skill_text() -> str:
    """Every Markdown file under the skill: references and playbooks included."""
    paths = _skill_markdown()
    assert {SKILL, SETUP, DAILY, UPGRADES, HARDENING} <= set(paths)
    assert any(path.parent.name == "playbooks" for path in paths)
    return " ".join(_flat(path) for path in paths)


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
        "Use password mode with a separate expiring key for each agent",
        "Deploy only a reviewed release SHA",
        "Never run `alchemy destroy`",
        "Never print a secret",
        "Owner-run steps stay with the owner",
    ):
        assert rule in body, rule


def test_setup_writes_password_mode_on_purpose() -> None:
    body = _flat(SETUP)
    assert "AUTH_MODE=password" in SETUP.read_text(encoding="utf-8")
    assert "grep -q '^AUTH_MODE=password$' .env.selfhost" in body
    # Password mode is written only at the switch, after the owner exists.
    assert body.index("AUTH_MODE=cloudflare_access") < body.index("grep -q '^AUTH_MODE=password$'")
    assert "Do not recopy the example env file" in _flat(UPGRADES)


def test_setup_pins_and_writes_access_as_requirements() -> None:
    text = SETUP.read_text(encoding="utf-8")
    assert text.count(PIN) >= 3
    assert "| Requirement | How to check | Expected result |" in text
    assert "**Expected:**" in text
    assert "NOT VERIFIED" in text
    flat = _flat(SETUP)
    assert "| 304 |" in flat
    assert "mb connect openseo-<AGENT> --custom --token-stdin --scope repo" in flat
    assert "Claude Code refuses an agent writing its own MCP config" in flat
    assert '`mb connect test` says "stored, unverified"' in flat
    assert "A password reset does not revoke keys." in flat
    assert "Self-hosting has no meter or cap." in flat
    assert "Do not run keyword, rank, prompt, or AI checks as tests." in flat


def test_hardening_covers_password_mode_lessons() -> None:
    flat = _flat(SKILL_DIR / "references/access-hardening.md")
    for text in (
        "`AUTH_MODE=password`",
        "workers.dev and previews off",
        "`MCP_RATE_LIMIT`",
        "its own `oseo_` key",
        "The minimum is one day",
        "`mb connect test` cannot check a custom provider",
        "A redeploy does not remove a Worker secret.",
        "has no sign-out-all control",
        "Self-hosting has no meter and no cap.",
        "Same-uid processes can read a stored key",
        "Cloudflare Access for a human-only app",
    ):
        assert text in flat, text


def test_playbooks_are_linked_from_the_skill_and_handoffs() -> None:
    playbooks = SKILL_DIR / "references/playbooks"
    names = sorted(path.name for path in playbooks.glob("*.md"))
    assert len(names) == 14 and "costs.md" in names
    handoffs = (SKILL_DIR / "references/upstream-skills.md").read_text(encoding="utf-8")
    assert "references/playbooks/" in SKILL.read_text(encoding="utf-8")
    for name in names:
        assert f"playbooks/{name}" in handoffs, name
    link = re.compile(r"\]\(([^)#\s]+)\)")
    for path in playbooks.glob("*.md"):
        for target in link.findall(path.read_text(encoding="utf-8")):
            if "://" not in target:
                assert (path.parent / target).resolve().exists(), (path.name, target)


def test_setup_uses_connect_and_keeps_logs_private() -> None:
    flat = _flat(SETUP)
    assert "mb connect cloudflare-openseo --custom --scope repo" in flat
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


def test_standing_words_have_one_home_and_cannot_loosen_rules() -> None:
    daily = _flat(DAILY)
    assert "`Standing words`" in daily
    assert "never loosen them" in daily
    assert "A standing approval counts only as written" in daily
    assert "## Standing words" in SETUP.read_text(encoding="utf-8")


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


UPSTREAM_SKILLS = (
    "seo-coach",
    "seo-project-setup",
    "keyword-research",
    "keyword-clustering",
    "seo-audit",
    "competitor-analysis",
    "competitive-landscape",
    "link-prospecting",
    "ai-prompt-research",
    "ai-visibility-audit",
    "local-seo",
    "seo-report",
)


def test_mb_seo_names_every_upstream_skill_with_a_handoff() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    handoffs = (SKILL_DIR / "references/upstream-skills.md").read_text(encoding="utf-8")
    for name in UPSTREAM_SKILLS:
        assert f"`{name}`" in skill
        assert f"| `{name}` |" in handoffs


def test_mb_seo_install_is_skills_only_at_a_verified_ref() -> None:
    setup = SETUP.read_text(encoding="utf-8")
    assert "Install the skills only" in setup
    assert "Do not install the upstream OpenSEO plugin" not in setup
    assert PIN in setup
    assert "beca5c1" not in _all_skill_text()


def test_no_command_puts_a_literal_key_in_a_header() -> None:
    """Every `--header` carries an environment reference, never a key."""
    header = re.compile(r"--header\s+('[^']*'|\"[^\"]*\"|\S+)")
    seen = 0
    for path in _skill_markdown():
        text = path.read_text(encoding="utf-8")
        for match in header.finditer(text):
            seen += 1
            value = match.group(1)
            assert value == "'Authorization: Bearer ${OPENSEO_MCP_KEY}'", (path.name, value)
        assert not re.search(r"oseo_[A-Za-z0-9]{8,}", text), path.name
        assert "Bearer <KEY>" not in text, path.name
    assert seen >= 2, "both client-wiring places must show the env-reference header"
    for path in (SETUP, HARDENING):
        flat = _flat(path)
        assert "unset OPENSEO_MCP_KEY" in flat, path.name
        assert "`claude mcp get" in flat and "literal `${OPENSEO_MCP_KEY}`" in flat, path.name
        assert "--env OPENSEO_MCP_KEY -- claude" in flat, path.name
        assert "missing, empty, invalid and revoked" in flat.lower(), path.name
    flat = _flat(SETUP)
    for text in (
        "same operating-system user can read it",
        "Rotation.",
        "Custody.",
        "`headersHelper` is a documented alternative",
    ):
        assert text in flat, text
    assert flat.index("unset OPENSEO_MCP_KEY") < flat.index("claude mcp add --transport http")
    assert flat.index("claude mcp add --transport http") < flat.index("claude mcp get")
    assert flat.index("claude mcp get") < flat.index("--env OPENSEO_MCP_KEY -- claude")


def test_first_owner_is_created_behind_protection_in_order() -> None:
    flat = _flat(HARDENING)
    assert "## First owner: protected bootstrap" in HARDENING.read_text(encoding="utf-8")
    for cite in (
        "src/server/standalone/sign-up.ts:13-22",
        "src/lib/auth-mode.ts:7-11",
    ):
        assert cite in flat, cite
    order = [
        "Deploy in Access mode with a one-address allow-list",
        "Prove it is protected before anyone signs in",
        "The intended owner signs in once through Access",
        "Verify the owner's identity",
        "Switch to password login and remove Access",
        "Prove an uninvited sign-up creates no user",
        "Give the owner a password and the owner role",
        "Verify owner membership",
    ]
    positions = [flat.index(step) for step in order]
    assert positions == sorted(positions), "bootstrap steps are out of order"
    assert flat.index("AUTH_MODE=cloudflare_access") < flat.index("AUTH_MODE=password")
    setup = _flat(SETUP)
    assert "AUTH_MODE=cloudflare_access" in setup
    first_deploy = setup.index("## 4. Owner: fill in `.env.selfhost`")
    assert "AUTH_MODE=password" not in setup[first_deploy : setup.index("## 5. Agent: deploy")]
    assert "never start there" in setup
    assert "do not expose the app" in setup.lower()


def test_app_oauth_policy_is_stated_and_probed() -> None:
    text = HARDENING.read_text(encoding="utf-8")
    flat = _flat(HARDENING)
    assert "## App OAuth in password mode" in text
    for required in (
        "app OAuth is kept, because it cannot be turned off by configuration",
        "src/server.ts:224-229",
        "does **not** cover OAuth registration",
        "inventory of clients and grants",
        "Revoke with readback",
        "Rejected-token check",
        "/api/auth/oauth2/register",
        "/api/auth/oauth2/authorize",
        "/api/auth/oauth2/token",
        "/api/oauth/consent",
    ):
        assert required in flat, required
    probe_table = flat[flat.index("## Signed-out probes") : flat.index("## App OAuth")]
    for endpoint in ("/api/auth/oauth2/register", "/api/auth/oauth2/token", "/.well-known/"):
        assert endpoint in probe_table, endpoint
    assert "#app-oauth-in-password-mode" in _flat(SETUP)


def test_pin_is_the_exact_release_sha_everywhere() -> None:
    text = _all_skill_text()
    assert text.count(PIN) >= 3
    stale = _all_skill_text().replace("older v0.1.21", "")
    assert "v0.1.21" not in stale
