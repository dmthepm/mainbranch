"""Acceptance checks for the support skill's case, channel and tracker rules."""

from __future__ import annotations

from pathlib import Path

from mb import skill_validate

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / ".claude/skills/mb-support"
SKILL = SKILL_DIR / "SKILL.md"
CASES = SKILL_DIR / "references/cases.md"
CHANNELS = SKILL_DIR / "references/channels.md"
SETUP = SKILL_DIR / "references/setup.md"


def _flat(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_skill_is_valid() -> None:
    assert len(SKILL.read_text(encoding="utf-8").splitlines()) <= 300
    report = skill_validate.run("mb-support")
    assert report is not None and report["ok"], report


def test_case_lists_every_conversation_as_provider_ids() -> None:
    cases = _flat(CASES)
    assert "| Case | Channel | Conversations |" in cases
    assert "provider ids only" in cases
    assert "No names or addresses" in cases


def test_match_by_reading_providers_before_opening_or_drafting() -> None:
    skill = _flat(SKILL)
    assert "Before opening a case or drafting a reply" in skill
    assert "same request" in skill
    assert "read the other linked conversations" in skill
    assert "ask the owner, never merge" in skill
    assert "the repo keeps only the link" in skill


def test_one_reply_per_case() -> None:
    assert "One reply per case unless the owner approves more" in _flat(SKILL)


def test_channels_register_exists_and_is_linked() -> None:
    assert "references/channels.md" in _flat(SKILL)
    channels = _flat(CHANNELS)
    for column in (
        "Channel",
        "Where it lives",
        "Who owns replies",
        "Read route",
        "Read or reply",
    ):
        assert column in channels
    assert "Each business names its own channels" in channels
    for example in ("voicemail", "text", "community chat"):
        assert example in channels
    assert "examples only" in channels


def test_no_read_route_is_logged_by_hand_and_stated() -> None:
    text = _flat(SKILL) + " " + _flat(CHANNELS)
    assert "no read route" in text
    assert "logged by hand" in text
    assert "never treated as no messages" in text


def test_tracker_cases_say_state_is_not_private() -> None:
    cases = _flat(CASES)
    assert "tracker" in cases
    assert "`state/` is neither durable nor private" in cases


def test_synced_tracker_comment_that_emails_is_a_send() -> None:
    skill = _flat(SKILL)
    assert "tracker comment" in skill
    assert "emails a customer" in skill
    assert "counts as a send" in skill


def test_setup_creates_the_channels_register() -> None:
    assert "channels.md" in _flat(SETUP)
