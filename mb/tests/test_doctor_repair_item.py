"""``mb doctor repair --item``: apply named repair items only (#1362)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import codex as codex_mod
from mb.cli import app
from mb.init import run as init_run

runner = CliRunner()


@pytest.fixture(autouse=True)
def codex_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(codex_mod, "_which", lambda name: "" if name == "codex" else None)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fixture repo whose AGENTS.md and global Codex skills both need repair."""
    monkeypatch.setenv("MAINBRANCH_CODEX_PLUGIN_ROOT", str(tmp_path / "codex-global"))
    monkeypatch.setenv("MAINBRANCH_CODEX_SKILLS_ROOT", str(tmp_path / "codex-skills"))
    target = tmp_path / "biz"
    init_run(path=str(target), name="Acme")
    (target / "AGENTS.md").write_text("# stale\n\nNo facts here.\n", encoding="utf-8")
    return target


def _repair(repo: Path, *args: str) -> tuple[int, dict[str, Any]]:
    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), *args, "--json"])
    return result.exit_code, json.loads(result.stdout) if result.stdout.startswith("{") else {}


def _refused(repo: Path, *args: str) -> str:
    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), *args])
    assert result.exit_code == 2, result.output
    return result.output


def test_plan_json_lists_item_ids(repo: Path) -> None:
    code, plan = _repair(repo, "--plan", "--only", "codex")

    assert code in {0, 1}
    assert [action["id"] for action in plan["actions"]] == ["codex-agents-md", "codex-global-skill"]
    assert plan["items"] == []


def test_plan_human_names_item_ids(repo: Path) -> None:
    result = runner.invoke(app, ["doctor", "repair", "--repo", str(repo), "--plan"])

    assert "(item: codex-global-skill)" in " ".join(result.output.split())


def test_item_applies_global_skill_and_leaves_agents_md_byte_identical(
    repo: Path, tmp_path: Path
) -> None:
    before = (repo / "AGENTS.md").read_bytes()

    code, payload = _repair(repo, "--apply", "--only", "codex", "--item", "codex-global-skill")

    assert code in {0, 1}
    assert (repo / "AGENTS.md").read_bytes() == before
    assert [action["id"] for action in payload["applied_actions"]] == ["codex-global-skill"]
    assert payload["applied_actions"][0]["state"] == "ok"
    assert (tmp_path / "codex-skills" / "mb-start" / "SKILL.md").is_file()
    assert payload["items"] == ["codex-global-skill"]
    assert [action["id"] for action in payload["actions"]] == []


def test_item_plan_shows_only_the_named_item(repo: Path) -> None:
    code, plan = _repair(repo, "--plan", "--only", "codex", "--item", "codex-global-skill")

    assert code in {0, 1}
    assert [action["id"] for action in plan["actions"]] == ["codex-global-skill"]


def test_unknown_item_is_refused_with_valid_ids_and_nothing_changes(
    repo: Path, tmp_path: Path
) -> None:
    before = (repo / "AGENTS.md").read_bytes()

    output = _refused(repo, "--apply", "--only", "codex", "--item", "codex-everything")

    assert "unknown item `codex-everything`" in output
    assert "codex-agents-md, codex-global-skill" in output
    assert (repo / "AGENTS.md").read_bytes() == before
    assert not (tmp_path / "codex-skills").exists()


def test_tracked_file_item_still_needs_its_scope(repo: Path) -> None:
    before = (repo / "AGENTS.md").read_bytes()

    output = _refused(repo, "--apply", "--item", "codex-agents-md")

    assert "add --only codex" in output
    assert (repo / "AGENTS.md").read_bytes() == before

    code, payload = _repair(repo, "--apply", "--only", "codex", "--item", "codex-agents-md")

    assert code in {0, 1}
    assert [action["id"] for action in payload["applied_actions"]] == ["codex-agents-md"]
    assert (repo / "AGENTS.md").read_bytes() != before


def test_item_never_crosses_scopes(repo: Path) -> None:
    assert "add --only claude" in _refused(
        repo, "--apply", "--only", "codex", "--item", "skill-link"
    )
    assert "without --only or --all-agents" in _refused(
        repo, "--apply", "--only", "codex", "--item", "related-links-mirror"
    )
    assert "--include-migration" in _refused(
        repo, "--apply", "--include-migration", "--item", "related-links-mirror"
    )
    assert "requires an item id" in _refused(repo, "--apply", "--item")


def test_only_codex_without_item_still_applies_both(repo: Path) -> None:
    code, payload = _repair(repo, "--apply", "--only", "codex")

    assert code in {0, 1}
    assert {action["id"] for action in payload["applied_actions"]} == {
        "codex-agents-md",
        "codex-global-skill",
    }
    assert "## Codex Start Workflow" in (repo / "AGENTS.md").read_text(encoding="utf-8")
