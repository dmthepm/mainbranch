"""Guards for sales-video/VSL workflow routing."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("prompt", "skill_path", "expected_route"),
    [
        ("write a VSL", ".claude/skills/mb-site/SKILL.md", "/mb-site"),
        ("about page video", ".claude/skills/mb-site/SKILL.md", "/mb-site"),
        ("video ad script", ".claude/skills/mb-ads/SKILL.md", "/mb-ads"),
        ("analyze this VSL", ".claude/skills/mb-think/SKILL.md", "/mb-think"),
        (
            "short clips from sales video",
            ".claude/skills/mb-organic/SKILL.md",
            "/mb-organic",
        ),
    ],
)
def test_natural_sales_video_prompts_route_to_broader_skills(
    prompt: str, skill_path: str, expected_route: str
) -> None:
    start = _read(".claude/skills/mb-start/SKILL.md").lower()
    skill = _read(skill_path).lower()

    assert prompt.lower() in start or prompt.lower() in skill
    assert expected_route in start
    assert "not a standalone skill" in start


def test_vsl_framework_references_are_shared_and_reachable_from_broader_skills() -> None:
    shared_refs = [
        ".claude/reference/conversion/vsl-routing.md",
        ".claude/reference/conversion/vsl/skool-18-section.md",
        ".claude/reference/conversion/vsl/b2b-haynes.md",
        ".claude/reference/conversion/vsl/examples/b2b-ijanitorial.md",
    ]
    for ref in shared_refs:
        assert (REPO_ROOT / ref).is_file()

    consumers = [
        ".claude/skills/mb-think/references/sales-video-research.md",
        ".claude/skills/mb-site/references/sales-video.md",
        ".claude/skills/mb-ads/references/long-form-video-ads.md",
        ".claude/skills/mb-organic/references/sales-video-repurpose.md",
    ]
    for consumer in consumers:
        text = _read(consumer)
        assert ".claude/reference/conversion/vsl-routing.md" in text
        assert ".claude/skills/mb-vsl/references" not in text

    assert not (REPO_ROOT / ".claude/skills/mb-vsl").exists()


def test_operator_help_avoids_retired_data_repo_and_public_conductor_framing() -> None:
    scanned = [
        ".claude/skills/mb-help/SKILL.md",
        ".claude/skills/mb-help/references/system-model.md",
        ".claude/skills/mb-help/references/workspace-setup.md",
        ".claude/skills/mb-help/references/troubleshooting.md",
        ".claude/skills/mb-setup/references/engine-path-resolution.md",
        ".claude/reference/conversion/vsl-routing.md",
        ".claude/reference/business-primitives/setup-patterns.md",
        ".claude/skills/mb-start/SKILL.md",
        ".claude/skills/mb-start/references/config-system.md",
        ".claude/skills/mb-start/references/repo-detection.md",
        ".claude/skills/mb-start/references/triage-menu.md",
        ".claude/skills/mb-ads/references/preflight-algorithm.md",
        ".claude/skills/mb-site/references/concept-variations.md",
        ".claude/skills/mb-skill-concept/references/concept-variations.md",
        ".claude/skills/mb-setup/SKILL.md",
        ".claude/skills/mb-setup/references/templates.md",
        "README.md",
        "docs/beginner-setup.md",
        "docs/operator-loops.md",
    ]
    retired_terms = [
        "data repo",
        "engine + data",
        "your data",
        "two-repo model",
        "data (this repo)",
        "shared with all members",
        "<vip_path>",
        "save forever",
        "save to ~/.config/vip/local.yaml",
        "if yes, update `~/.config/vip/local.yaml`",
        "if yes, merge-update `default_repo`",
        "canonical",
        "ground truth",
        "vip-path-resolution",
        "vip path",
        "Conductor",
        "PA config",
        "Pre-Agent",
    ]

    failures: list[str] = []
    for relative in scanned:
        text = _read(relative).lower()
        for term in retired_terms:
            if term.lower() in text:
                failures.append(f"{relative}: contains retired phrase {term!r}")

    assert failures == []


def test_conversion_mechanism_gate_present_on_every_rail() -> None:
    """#840: page copy must wait on a recorded conversion mechanism, all rails.

    A real business lost a day when an agent invented a call-booking model the
    operator never chose. The gate must live where copy is drafted (brief-draft),
    in the Claude router (mb-site), and on the Codex workflow source.
    """
    brief = _read(".claude/skills/mb-skill-brief-draft/SKILL.md")
    site = _read(".claude/skills/mb-site/SKILL.md")
    workflow = _read("workflows/mb-site/workflow.md")

    # Brief-draft records the mechanism as gated, operator-stated facts.
    assert "conversion_mechanism" in brief
    assert "takes_calls" in brief
    assert "before any copy" in brief.lower()

    for surface in (brief, site, workflow):
        lowered = surface.lower()
        # The visitor-action choices the operator must pin.
        assert "book a call" in lowered or "book_call" in lowered
        assert "lead form" in lowered or "lead_form" in lowered
        # Stop-and-ask, never-assume intent.
        assert "never assume" in lowered
        assert (
            "page copy" in lowered or "before drafting" in lowered or "before any copy" in lowered
        )


def test_click_id_capture_invariant_present_on_both_rails() -> None:
    """#887: lead-capturing scaffolds snapshot click IDs + UTMs by default.

    A real business captured fbclid + 5 UTMs but zero Google click IDs, so its
    first Google clicks were permanently unattributable. The capture set must
    be a scaffold default on both the Claude lead-capture reference and the
    Codex workflow — not an audit-time retrofit.
    """
    conversion = _read(".claude/skills/mb-site/references/minisite-conversion.md")
    workflow = _read("workflows/mb-site/workflow.md")

    required = ["gclid", "gbraid", "wbraid", "fbclid"]
    utms = [
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
    ]
    for surface in (conversion, workflow):
        lowered = surface.lower()
        for param in required + utms:
            assert param in lowered, f"missing {param}"
        # Tied to the own-the-form principle and a scaffold default, not audit.
        assert "§6" in surface or "principles" in lowered
        assert "default" in lowered
