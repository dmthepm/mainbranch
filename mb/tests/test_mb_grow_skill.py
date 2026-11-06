"""The growth loop ships in the plugin and does not break the hub's entry rule."""

from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from mb import skill_validate
from mb.cli import app
from mb.codex_data import CLAUDE_SKILL_SOURCE_NAMES, CODEX_GLOBAL_SKILL_NAMES
from mb.init import _DEFAULT_CLAUDE, _read_template

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / ".claude/skills/mb-grow"
SKILL = SKILL_DIR / "SKILL.md"
LOG_HOME = "`log/growth.md`"


def test_mb_grow_is_listed_where_installed_skills_are_listed() -> None:
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert plugin["skills"] == "./.claude/skills/"
    assert SKILL.is_file()
    body = SKILL.read_text(encoding="utf-8")
    assert body.startswith("---\nname: mb-grow\n")
    assert "mb-grow" in CliRunner().invoke(app, ["skill", "list"]).output.split()
    assert "mb-grow" in CLAUDE_SKILL_SOURCE_NAMES
    assert "mb-grow" in CODEX_GLOBAL_SKILL_NAMES
    report = skill_validate.run("mb-grow")
    assert report is not None and report["ok"], report


def test_every_bundled_skill_folder_is_in_the_plugin_listing() -> None:
    folders = {p.parent.name for p in (ROOT / ".claude/skills").glob("*/SKILL.md")}
    listed = set(CliRunner().invoke(app, ["skill", "list"]).output.split())
    assert folders <= listed, sorted(folders - listed)


def test_growth_log_has_one_home_that_the_hub_rule_allows() -> None:
    for text in (
        _read_template("CLAUDE.md.tmpl"),
        _read_template("AGENTS.md.tmpl"),
        _DEFAULT_CLAUDE,
    ):
        rule = text.split("## Trials and readouts", 1)[1].split("## Where data lives", 1)[0]
        assert "Do not file the readout in `log/`." in rule
        assert LOG_HOME in rule
        assert "core/growth/autonomy.md" in rule

    skill = "\n".join(p.read_text(encoding="utf-8") for p in SKILL_DIR.rglob("*.md"))
    assert LOG_HOME in skill
    assert not re.search(r"state/growth", skill)


def test_loop_reads_the_owners_latest_before_picking_a_move() -> None:
    body = SKILL.read_text(encoding="utf-8")
    read_latest = body.index("**Read the owner's latest.**")
    assert read_latest < body.index("**Pick one move.**")
    assert "`decisions/`" in body[read_latest : body.index("**Pick one move.**")]


def test_private_state_home_has_an_adoption_path() -> None:
    body = SKILL.read_text(encoding="utf-8")
    assert "private state" in body
    assert "`core/growth/`" in body and "`log/growth.md`" in body
    assert "Use one home at a time" in body
