"""Static checks for the always-on machine skill; nothing here inspects this host."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from mb import codex, skill_validate

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".claude" / "skills" / "mb-homelab-machine"
GUIDE = ROOT / "docs" / "machine-setup.md"
REFERENCES = ("setup.md", "maintenance.md", "extension.md", "hardening.md")
MARKDOWN = [SKILL / "SKILL.md", *(SKILL / "references" / name for name in REFERENCES)]


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def code_spans(source: str) -> list[str]:
    return re.findall(r"`([^`\n]+)`", source)


def github_slug(heading: str) -> str:
    slug = heading.strip().lower()
    slug = re.sub(r"[^\w\- ]", "", slug)
    return slug.replace(" ", "-")


def guide_anchors() -> set[str]:
    return {
        github_slug(match)
        for match in re.findall(r"^#{1,6} (.+)$", text(GUIDE), flags=re.MULTILINE)
    }


def test_frontmatter_validation_and_line_gate() -> None:
    report = skill_validate.run(SKILL.name)
    assert report is not None and report["ok"], report
    skill = text(SKILL / "SKILL.md")
    assert skill.startswith("---\nname: mb-homelab-machine\n")
    assert "loops: [sense, decide, ship]" in skill
    assert len(skill.splitlines()) < skill_validate.MAX_SKILL_LINES


def test_references_exist_and_are_routed() -> None:
    skill = text(SKILL / "SKILL.md")
    for name in REFERENCES:
        assert (SKILL / "references" / name).is_file()
        assert f"(references/{name})" in skill
    for path in MARKDOWN:
        for target in re.findall(r"\]\(([^)#:]+)\)", text(path)):
            assert (path.parent / target).is_file(), (path.name, target)


def test_guide_headings_named_by_the_skill_still_exist() -> None:
    anchors = guide_anchors()
    linked: set[str] = set()
    for path in MARKDOWN:
        for anchor in re.findall(r"machine-setup\.md#([\w-]+)", text(path)):
            assert anchor in anchors, f"{path.name} links to missing guide heading #{anchor}"
            linked.add(anchor)
    # Each reference points into the guide instead of copying it.
    for name in REFERENCES:
        assert "machine-setup.md#" in text(SKILL / "references" / name)
    assert {"part-4-first-week", "backup-storage", "one-user-account-per-business"} <= linked


def test_guide_drift_check_catches_a_renamed_heading() -> None:
    assert github_slug("Ubuntu LTS (recommended default)") == "ubuntu-lts-recommended-default"
    assert github_slug("Part 2: Picking a machine") == "part-2-picking-a-machine"
    assert "a-heading-that-was-renamed" not in guide_anchors()


def test_guide_points_to_the_skill_once() -> None:
    assert text(GUIDE).count("mb-homelab-machine") == 1


FORBIDDEN_IN_CODE = [
    # Isolation controls are requirements only; their commands come from security review.
    r"\b(?:nft|iptables|ip6tables|ufw|firewall-cmd|bwrap|bubblewrap|apparmor_parser|aa-\w+)\b",
    r"hidepid|landlock|setfacl|busctl|dbus-send|socat|systemd-run",
    # Done-checks are read-only and never elevate or evaluate strings.
    r"^sudo\s|\beval\b|\b(?:ba)?sh -c\b|\|\s*(?:ba)?sh\b",
    r"\b(?:chmod|chown|chgrp|usermod|useradd|groupadd|passwd|mkfs\S*|rm)\b|\bmount\s+-",
    r"\bsystemctl\b.*\b(?:enable|disable|start|stop|restart|mask|edit|set-property)\b",
    r"\bloginctl\s+(?:enable|disable|terminate|kill)",
    r"\b(?:apt|apt-get|pacman|brew|pip|npm|uv)\s+(?:install|remove|upgrade|-S|-R)",
    r"\b(?:restic|tailscale)\s+(?!--help)\w",
]


@pytest.mark.parametrize("path", MARKDOWN, ids=lambda p: p.name)
def test_no_isolation_recipes_or_mutating_commands(path: Path) -> None:
    for span in code_spans(text(path)):
        for pattern in FORBIDDEN_IN_CODE:
            assert not re.search(pattern, span, flags=re.IGNORECASE), (path.name, span)
    # No fenced shell blocks: checks are single read-only commands in the tables.
    assert "```" not in text(path)


PRIVATE_PATTERNS = [
    r"/home/(?!<)",
    r"/Users/",
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    r"[\w.+-]+@[\w-]+\.[\w.]+",
    r"\.ts\.net\b",
    r"tskey-",
    r"\b(?:ghp|gho|sk|pk|rk)_[A-Za-z0-9]{8,}",
]


def test_no_private_details() -> None:
    files = [*MARKDOWN, SKILL / "evals" / "trigger-evals.json"]
    for path in files:
        source = text(path)
        for pattern in PRIVATE_PATTERNS:
            assert not re.search(pattern, source), (path.name, pattern)
        assert "../" not in source


def test_unknown_is_never_a_pass() -> None:
    for path in MARKDOWN:
        assert "NOT VERIFIED" in text(path), path.name
    skill = text(SKILL / "SKILL.md")
    assert "Unknown is never a pass" in skill
    assert "Start at Checkpoint 1; graduate only on a recorded trigger." in skill
    assert "Requirements, not commands, for isolation controls" in skill


def test_clipboard_history_is_a_requirement_never_read() -> None:
    setup = text(SKILL / "references" / "setup.md")
    assert "clipboard history is off completely" in setup
    paragraphs = [p for p in setup.split("\n\n") if "clipboard*" in p]
    assert paragraphs and all("Never open" in p for p in paragraphs)


def test_homelab_maintenance_inputs_are_covered() -> None:
    maintenance = text(SKILL / "references" / "maintenance.md")
    for phrase in (
        "minimum release age",
        "audited override",
        "`<tool> --help` exits 0",
        "Stale means unknown, never available",
        "restart table",
        "Backups count only after a restore drill",
        "A same-user hook is advisory, not a boundary",
        "CVE inventory",
        "source-health record",
    ):
        assert phrase in maintenance, phrase
    # Banked quota resets are information only; the skill never redeems them.
    assert "never redeem or spend one" in maintenance


def test_checkpoint_one_and_graduation_tables() -> None:
    hardening = text(SKILL / "references" / "hardening.md")
    rows = re.findall(r"^\| (\d+) \|", hardening, flags=re.MULTILINE)
    assert rows == [str(n) for n in range(1, 15)]
    unlocks = re.findall(
        r"\| (Container per tenant|VM for [^|]+|Separate machine[^|]*) \|$",
        hardening,
        flags=re.MULTILINE,
    )
    assert len(unlocks) == 8
    assert "No recorded trigger, no graduation." in hardening


def test_trigger_evals_are_balanced() -> None:
    evals = json.loads(text(SKILL / "evals" / "trigger-evals.json"))
    queries = [item["query"] for item in evals]
    assert len(queries) == len(set(queries)) == 20
    assert sum(item["should_trigger"] for item in evals) == 10


def test_claude_only_like_other_machine_skills() -> None:
    assert SKILL.name not in codex.CLAUDE_SKILL_SOURCE_NAMES
    assert SKILL.name not in codex.CODEX_GLOBAL_SKILL_NAMES
    paths = [
        ROOT / "mb/mb/start.py",
        ROOT / ".claude/skills/mb-start/SKILL.md",
        ROOT / "mb/mb/_data/release_simulations/manifest.json",
    ]
    paths.extend((ROOT / "workflows").rglob("*.md"))
    assert all(SKILL.name not in text(path) for path in paths)


def test_account_rule_uses_the_guides_business_language() -> None:
    for path in MARKDOWN:
        assert "trust domain" not in text(path).lower(), path.name
    assert "One business per Unix user" in text(SKILL / "SKILL.md")
    assert "no two businesses\nsharing an account" in text(SKILL / "references/maintenance.md")


def test_version_manager_rule_has_no_placeholder() -> None:
    maintenance = text(SKILL / "references/maintenance.md")
    assert "<version manager>" not in maintenance
    assert "minimum release age" in maintenance
    assert "audited override" in maintenance


@pytest.mark.parametrize(
    "relative",
    [
        ".claude/skills/mb-help/references/skills-guide.md",
        "docs/compatibility.md",
    ],
)
def test_machine_skill_is_discoverable(relative: str) -> None:
    source = text(ROOT / relative)
    assert "/mb-homelab-machine" in source
    assert "Claude Code only" in source
