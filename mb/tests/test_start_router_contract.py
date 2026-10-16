"""Product-contract guards for the `/mb-start` business router."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
START_SKILL = REPO_ROOT / ".claude" / "skills" / "mb-start" / "SKILL.md"
ROUTER_REF = REPO_ROOT / ".claude" / "skills" / "mb-start" / "references" / "router-and-language.md"
UPDATE_REF = REPO_ROOT / ".claude" / "skills" / "mb-start" / "references" / "pull-engine-updates.md"
ADS_SKILL = REPO_ROOT / ".claude" / "skills" / "mb-ads" / "SKILL.md"
SITE_CONTEXT_REF = REPO_ROOT / ".claude" / "skills" / "mb-site" / "references" / "site-context.md"
THINK_SKILL = REPO_ROOT / ".claude" / "skills" / "mb-think" / "SKILL.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    lines = [line.removeprefix("> ").strip() for line in text.splitlines()]
    return " ".join(" ".join(lines).split())


def test_sales_video_clips_and_paid_ads_have_distinct_routes() -> None:
    router = _read(ROUTER_REF).lower()
    ads = _read(ADS_SKILL).lower()

    assert "short clips or social cuts from a sales video or vsl: `/mb-organic`" in router
    assert "make an ad from this video, compliance: `/mb-ads`" in router
    assert '"make short clips from this sales video"' in ads
    assert "organic clips | route to `/mb-organic`" in ads
    assert '"make an ad from this video"' in ads
    assert "| video repurpose |" in ads


def test_mb_start_delegates_router_detail_without_bloating_skill_body() -> None:
    start = _read(START_SKILL)

    assert len(start.splitlines()) <= 500
    assert "references/router-and-language.md" in start
    assert "bookkeeping setup runs `mb books check`" in start
    assert "private admin repo" not in start.lower()


def test_router_contract_covers_books_save_sync_and_updates() -> None:
    router = _read(ROUTER_REF)

    required_phrases = [
        "saved checkpoint",
        "unsaved local work",
        "catch up with the shared repo",
        "reconcile local saved work",
        "proposal/review path",
        "ad hoc PR-instruction attachments",
        "Update strongly recommended",
        'Run `mb books check "$REPO_PATH" --json`',
        "`storage_mode`",
        "hub registry",
        "child descriptor `.mainbranch/repo.json`",
        "topology role `finance` with visibility `restricted` or `local_only`",
        'generic "set up"',
    ]
    for phrase in required_phrases:
        assert phrase in router

    assert "noontide-admin" not in router.lower()


def test_router_contract_translates_visible_git_language_before_owner_answer() -> None:
    router = _read(ROUTER_REF)

    required_translations = {
        (
            "`git is clean`, `repo is clean`, `working tree clean`, "
            "`working tree: clean`, `clean on main`"
        ): "nothing unsaved locally",
        (
            "`on main`, `branch main`, `branch: main`, `current branch: main`"
        ): "current business folder or current workspace",
        "`one commit`, `only commit so far`": "setup baseline saved or last saved checkpoint",
        "`staged files`": "files queued for save",
        "`No GitHub origin remote`, `No origin remote`": (
            "local-only folder or no connected GitHub backup"
        ),
        "`origin remote`": "connected GitHub backup or shared task source",
        "`PR/issue facts`, `PR and issue facts`": "GitHub task and proposal context",
        "`before this goes to a remote`": "before anything is shared outside your machine",
    }
    for tool_phrase, owner_phrase in required_translations.items():
        assert tool_phrase in router
        assert owner_phrase in router


def test_start_router_routes_money_intent_from_moneypath_facts() -> None:
    start = _read(START_SKILL)
    router = _read(ROUTER_REF)
    normalized_start = _normalize(start)
    normalized_router = _normalize(router)

    assert "Parse the full JSON once" in normalized_start
    assert "do not slice status output with `head` or `sed`" in normalized_start

    required_phrases = [
        "Path to money, revenue, offer readiness",
        "path to money",
        "next dollar",
        "offer readiness",
        "Keep hard gates first",
        "Required update, broken install/runtime/wiring, repair blockers, validation "
        "blockers, relationship health blockers, playbook health blockers, and unsafe "
        "provider/private-data blockers all win before MoneyPath routing.",
        "`money_path.overall_level`",
        "`money_path.overall_label`",
        "`money_path.objects.offer`",
        "`money_path.objects.proof`",
        "`money_path.objects.proof.quality.public_marketing.status`",
        "permission collection",
        "`money_path.objects.product_ladder`",
        "`money_path.objects.cta_path`",
        "`money_path.objects.channel_strategy`",
        "`money_path.objects.active_push`",
        "`money_path.objects.outcome_feedback_loop`",
        "`money_path.ranked_actions`",
        "without conversion judgment",
        "Explain whether top-level `ranked_actions` agree with the MoneyPath bottleneck",
        "include a MoneyPath snapshot in the handoff",
        "Product ladder is stated but has no clear paid entry step",
        "Channel strategy exists, but no active push is attached",
        "Outcome feedback loop is missing",
        "Recommended route: use `/mb-think`",
    ]
    for phrase in required_phrases:
        assert phrase in normalized_router

    assert "Your offer is bad." in normalized_router
    assert "This will not convert." in normalized_router
    assert "This will convert." in normalized_router
    assert "The business is weak." in normalized_router
    assert "This is ready to win." in normalized_router


def test_start_router_no_longer_blindly_pulls_business_repo() -> None:
    start = _read(START_SKILL)
    update = _read(UPDATE_REF)

    combined = f"{start}\n{update}"
    assert 'git -C "$REPO_PATH" pull origin main' not in combined
    assert "blindly pull or rebase the business repo" in start


def test_public_marketing_proof_permission_guidance_is_shared() -> None:
    combined = "\n".join(
        _read(path) for path in [START_SKILL, ROUTER_REF, ADS_SKILL, SITE_CONTEXT_REF, THINK_SKILL]
    )

    assert "quality.public_marketing.status" in combined
    assert "permission collection" in combined
    assert "ads, pages, or public claims" in combined
    assert "do not draft proof-backed public ad claims" in combined
    assert "do not use those\ntestimonials in public page copy" in combined
    assert "`permissioned_public: false`" in combined
