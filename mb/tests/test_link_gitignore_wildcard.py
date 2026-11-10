"""`mb skill link` keeps one wildcard ignore line for bundled skills (#1341).

The links are machine-local. Writing one `.gitignore` line per bundled skill made
every release that added a skill leave a tracked change in every hub and worktree.
Bundled skills are all named `mb-*`, so one wildcard covers them: link adds its
lines only when missing and never removes any, so a hub changes at most once.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mb import engine as engine_mod

WILDCARD = ".claude/skills/mb-*"


def _lines(repo: Path) -> list[str]:
    return (repo / ".gitignore").read_text(encoding="utf-8").splitlines()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(engine_mod, "bundled_skills", lambda: ["mb-start", "mb-help"])
    path = tmp_path / "biz"
    path.mkdir()
    return path


def test_every_bundled_skill_is_named_mb_so_the_wildcard_covers_it() -> None:
    names = engine_mod.bundled_skills()
    assert names, "no bundled skills found"
    outside = [name for name in names if not name.startswith("mb-")]
    assert outside == []


def test_a_fresh_repo_gets_the_wildcard_and_no_per_skill_lines(repo: Path) -> None:
    engine_mod.link_skills(repo)
    lines = _lines(repo)
    assert WILDCARD in lines
    assert ".claude/settings.local.json" in lines and ".claude/worktrees/" in lines
    assert ".claude/skills/mb-start" not in lines and ".claude/skills/mb-help" not in lines


def test_a_new_bundled_skill_changes_nothing(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine_mod.link_skills(repo)
    before = (repo / ".gitignore").read_bytes()
    monkeypatch.setattr(
        engine_mod, "bundled_skills", lambda: ["mb-start", "mb-help", "mb-brand-new"]
    )
    plan = engine_mod.plan_link_skills(repo)
    assert plan["gitignore_add"] == [] and plan["gitignore_remove"] == []
    engine_mod.link_skills(repo)
    assert (repo / ".gitignore").read_bytes() == before


def test_an_old_per_skill_block_gets_only_the_wildcard_and_keeps_every_line(repo: Path) -> None:
    old = [
        engine_mod.GITIGNORE_HEADER,
        ".claude/settings.local.json",
        ".claude/worktrees/",
        ".claude/skills/mb-start",
        ".claude/skills/mb-retired",
        ".claude/skills/start",
    ]
    (repo / ".gitignore").write_text("\n".join(old) + "\n", encoding="utf-8")
    plan = engine_mod.plan_link_skills(repo)
    assert plan["gitignore_add"] == [WILDCARD] and plan["gitignore_remove"] == []
    engine_mod.link_skills(repo)
    assert _lines(repo) == [*old, WILDCARD]


def test_a_second_link_is_a_no_op(repo: Path) -> None:
    engine_mod.link_skills(repo)
    before = (repo / ".gitignore").read_bytes()
    plan = engine_mod.plan_link_skills(repo)
    assert not any(op["path"].endswith(".gitignore") for op in plan["operations"])
    engine_mod.link_skills(repo)
    assert (repo / ".gitignore").read_bytes() == before


def test_a_bundled_skill_outside_the_prefix_still_gets_its_own_line(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(engine_mod, "bundled_skills", lambda: ["mb-start", "odd-one"])
    engine_mod.link_skills(repo)
    lines = _lines(repo)
    assert WILDCARD in lines and ".claude/skills/odd-one" in lines
    assert ".claude/skills/mb-start" not in lines
