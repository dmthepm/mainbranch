"""Acceptance checks for where data lives in inherited guidance."""

from pathlib import Path

import pytest

from mb import claude_guidance, codex

ROOT = Path(__file__).resolve().parents[2]
OLD_ENTRY_BLOCK = """<!-- mainbranch:entry-rules:begin -->
## Trials and readouts

Only when the operator states both a measurable target and a review or cut point
for a current experiment, check existing bets first and reuse the matching bet.
If none covers that experiment, offer to open one with `/mb-bet` before the work.
Otherwise, route to the requested work, or to `/mb-think` if the operator is
unsure what to do.
For an observation or readout, such as "the numbers show" or "this week's read",
offer a short `research/` readout with summarized numbers, source, timeframe,
caveat, and next question. Do not file the readout in `log/`.
If the observation changes the plan, also offer a `decisions/` record. Link the
readout and decision both ways with `linked_decisions` and `linked_research`,
and link the bet or push that changes. For a status-only question, answer it
without proposing records. Ask for approval before any write. Never copy raw
provider rows, account IDs, or exported tables into the repo. See `/mb-start`,
`/mb-bet`, and `/mb-think` for the full routes.
<!-- mainbranch:entry-rules:end -->"""
PHRASES = (
    "product code only",
    "invented values in the real case's shape",
    "never deleted",
    "tracker issue they explain",
    "encrypted",
    "never down into a code repo",
)


def test_g1_both_templates_carry_the_section(tmp_path: Path) -> None:
    claude = (ROOT / "mb/mb/_data/templates/CLAUDE.md.tmpl").read_text()
    agents = (ROOT / "mb/mb/_data/templates/AGENTS.md.tmpl").read_text()
    for template in (claude, agents):
        assert template.count("## Where data lives") == 1
        assert all(phrase in template for phrase in PHRASES)
        assert "customers vs" not in template
        assert "customers' customers' data vs" not in template
    assert (
        claude.index(claude_guidance.BEGIN)
        < claude.index("## Where data lives")
        < claude.index(claude_guidance.END)
    )
    assert "## Where data lives" in claude_guidance._current_block()
    rendered = codex._managed_agents_block(
        codex.render_agents_md(tmp_path, name="Example", gh_username="example")
    )
    assert (
        rendered.index(codex.AGENTS_MANAGED_BEGIN)
        < rendered.index("## Where data lives")
        < rendered.index(codex.AGENTS_MANAGED_END)
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_g2_update_carries_the_section_into_an_existing_hub(tmp_path: Path, newline: str) -> None:
    path = tmp_path / "CLAUDE.md"
    before = "# Example\n\nOperator preface.\n\n".replace("\n", newline)
    after = "\n\n## Operator notes\nKeep this.\n".replace("\n", newline)
    path.write_bytes((before + OLD_ENTRY_BLOCK.replace("\n", newline) + after).encode())
    planned, warning = claude_guidance.plan(tmp_path)
    assert warning is None and planned is not None
    block = claude_guidance._current_block().replace("\n", newline)
    assert planned == before + block + after
    assert "## Where data lives" in planned
    claude_guidance.apply(tmp_path, planned)
    assert claude_guidance.plan(tmp_path) == (None, None)

    legacy = (
        "# Example\nMain Branch CLI facts are the source of truth for repo health.\n"
        "## First-run setup intent\nOperator notes.\n"
    ).replace("\n", newline)
    path.write_bytes(legacy.encode())
    planned, warning = claude_guidance.plan(tmp_path)
    assert warning is None and planned is not None
    assert planned.count("## Where data lives") == 1
    assert planned.count(claude_guidance.BEGIN) == 1
    assert planned.count(claude_guidance.END) == 1
    assert planned.startswith(legacy.split("## First-run setup intent")[0])
    assert planned.endswith(
        "## First-run setup intent" + legacy.split("## First-run setup intent")[1]
    )
    claude_guidance.apply(tmp_path, planned)
    assert claude_guidance.plan(tmp_path) == (None, None)


def test_g3_reference_and_pointers_exist() -> None:
    reference = ROOT / ".claude/skills/mb-setup/references/where-data-lives.md"
    text = reference.read_text()
    assert all(
        word in text
        for word in ("Code repos", "business repo", "tracker", "Production", "flows up")
    )
    assert "customers vs" not in text
    assert len(text.splitlines()) < 120
    pointers = (
        ".claude/skills/mb-setup/SKILL.md",
        ".claude/skills/mb-site/SKILL.md",
        ".claude/skills/mb-help/SKILL.md",
        ".claude/skills/mb-think/references/templates/research-template.md",
    )
    for pointer in pointers:
        assert "references/where-data-lives.md" in (ROOT / pointer).read_text()
    for skill in (ROOT / ".claude/skills").glob("*/SKILL.md"):
        assert len(skill.read_text().splitlines()) <= 500, skill


def test_g4_engine_doc_names_the_rule() -> None:
    doc = (ROOT / "docs/repo-visibility-rubric.md").read_text()
    assert "## Where data lives" in doc
    assert all(
        word in doc
        for word in (
            "Code repos",
            "business repo",
            "tracker",
            "Production",
            "never down into a code repo",
        )
    )
    # A release moves the entry out of [Unreleased], so look in the whole file.
    assert "#1231" in (ROOT / "CHANGELOG.md").read_text()
