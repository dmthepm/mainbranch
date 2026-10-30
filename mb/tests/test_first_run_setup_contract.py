"""Regression guards for first-run setup intent guidance."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _setup_section(text: str) -> str:
    start = text.index("setup intent")
    return text[start : start + 1400]


def test_beginner_setup_uses_owner_friendly_setup_prompt() -> None:
    text = _read("docs/beginner-setup.md")
    normalized = _normalize(text)

    required = [
        "## Setup with an agent",
        # The canonical paste-prompt lives only here; the README links to it.
        "Help me set up Main Branch using the current README and setup guide",
        "Ask briefly about my business, offer, and audience",
        "Inside the business folder, run mb doctor and explain any findings",
        "Preview the first checkpoint and ask before saving or syncing it",
        "then install Main Branch and run mb onboard with my approval",
        "Local-only setup is valid if I decline GitHub",
        # Safety rails stay documented around the prompt.
        "Ask me to review assumptions before writing",
        "gh auth status",
        "GitHub is recommended, and it does not need to cost anything",
        "the business brain has cloud backup and readable saved history",
        "AI tools with GitHub connectors can read the business brain",
        "Do not save that prompt as a markdown document.",
        "A checkpoint is an approved saved point in the business history.",
        "Main Branch updates change the engine and skills",
        "system-architecture.md#repo-topology",
    ]
    for phrase in required:
        assert phrase in normalized
    assert "mb onboard --github --push" not in normalized


def test_setup_prompt_has_one_home() -> None:
    """One canonical prompt: it lives in beginner setup and the README links
    to it, so the two doors never drift."""
    marker = "Help me set up Main Branch using the current README"
    assert marker in _normalize(_read("docs/beginner-setup.md"))
    readme = _read("README.md")
    assert marker not in _normalize(readme)
    assert "(docs/beginner-setup.md#setup-with-an-agent)" in readme


def test_runtime_guidance_routes_pasted_setup_to_onboarding() -> None:
    for relative in (
        "mb/mb/_data/templates/CLAUDE.md.tmpl",
        "mb/mb/_data/templates/AGENTS.md.tmpl",
    ):
        text = _read(relative)
        normalized = _normalize(text)
        assert "setup intent" in normalized
        assert "not as a document to save" in normalized
        assert "mb --version" in normalized
        assert "pipx install mainbranch" in normalized
        assert "mb onboard --help" in normalized
        assert "mb onboard plan" not in _normalize(_setup_section(text))
        assert "gh auth status" in normalized
        assert "gh api user --jq .login" in normalized
        assert "GitHub is strongly recommended" in normalized
        assert "connector-friendly copy of the business brain" in normalized
        assert "mb onboard --github <owner/repo> --push" in normalized
        assert "mb onboard --github --push" not in normalized


def test_setup_skill_keeps_onboard_plan_after_approval() -> None:
    text = _read(".claude/skills/mb-setup/SKILL.md")
    normalized = _normalize(text)

    assert "setup intent" in normalized
    assert "not as a document to save" in normalized
    assert "mb onboard --help" in normalized
    assert "Use `mb onboard plan` only after the operator approves" in normalized
    assert "After the operator approves saving setup progress" in normalized
    assert "mb onboard --github <owner/repo> --push" in normalized
    assert "mb onboard --github --push" not in normalized


def test_readme_points_empty_folder_users_to_bootstrap() -> None:
    text = _read("README.md")
    normalized = _normalize(text)

    assert "paste the [setup prompt](docs/beginner-setup.md#setup-with-an-agent)" in normalized
    assert "Local-only setup is valid" in normalized
    assert "GitHub backup is recommended" in normalized
    assert "Keep this business folder separate" in normalized
    assert "mb onboard --github --push" not in normalized
