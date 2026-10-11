"""Commands that validate, migrate, books, skill repair and checkpoint print (#1083).

From another folder each suggestion names the business repo, so pasting it acts
on that repo; from inside the repo every line is byte-identical to before.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mb import validate as validate_mod
from mb.cli import app
from mb.init import run as init_run
from tests.test_migrate import _legacy_repo

runner = CliRunner()


@pytest.fixture
def business(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MAINBRANCH_HOME", str(home / "mb"))
    monkeypatch.setenv("COLUMNS", "2000")
    repo = tmp_path / "Acme's studio"
    init_run(path=str(repo), name="Acme")
    (repo / ".git" / "hooks" / "commit-msg").unlink(missing_ok=True)
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    return repo.resolve()


def _quoted(repo: Path) -> str:
    return shlex.quote(str(repo))


def _flag(repo: Path) -> str:
    return f"--repo {_quoted(repo)}"


def _missing_mirror(repo: Path) -> None:
    (repo / "decisions").mkdir(exist_ok=True)
    (repo / "research").mkdir(exist_ok=True)
    (repo / "decisions" / "2026-04-29-missing-mirror.md").write_text(
        "---\ndate: 2026-04-29\nstatus: accepted\nlinked_research:\n"
        "  - research/2026-04-29-topic-source.md\n---\n# Missing mirror\n",
        encoding="utf-8",
    )
    (repo / "research" / "2026-04-29-topic-source.md").write_text(
        "---\ndate: 2026-04-29\ntopic: topic\nsource: source\n---\n# Topic\n",
        encoding="utf-8",
    )


# --- mb validate ------------------------------------------------------------


def test_validate_human_names_the_business_in_its_suggestions(business: Path) -> None:
    _missing_mirror(business)
    result = runner.invoke(app, ["validate", "--repo", str(business), "--cross-refs"])
    flag = _flag(business)
    assert f"Run `mb doctor repair {flag} --plan`" in result.output
    assert f"`mb doctor repair {flag} --apply`" in result.output
    assert f"Run `mb validate {flag} --cross-refs -v` or `--json`" in result.output


def test_validate_json_names_the_business_in_its_repair_text(business: Path) -> None:
    _missing_mirror(business)
    result = runner.invoke(app, ["validate", "--repo", str(business), "--cross-refs", "--json"])
    categories = json.loads(result.stdout)["validation_categories"]
    flag = _flag(business)
    assert f"`mb doctor repair {flag} --plan`" in categories["top_repair"]
    assert f"`mb doctor repair {flag} --plan`" in categories["top_operator_summary"]


def test_validate_inside_the_repo_keeps_its_bare_suggestions(
    business: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _missing_mirror(business)
    monkeypatch.chdir(business)
    result = runner.invoke(app, ["validate", "--cross-refs"])
    assert "next: Run `mb doctor repair --plan`, review the Related links mirror action" in (
        result.output
    )
    assert "Run `mb validate --cross-refs -v` or `--json` for the full per-file list." in (
        result.output
    )
    as_json = runner.invoke(app, ["validate", "--cross-refs", "--json"])
    assert json.loads(as_json.stdout) == validate_mod.run(path=str(business), cross_refs=True)


# --- mb migrate -------------------------------------------------------------


def test_migrate_check_and_apply_name_the_business(business: Path, tmp_path: Path) -> None:
    legacy = _legacy_repo(tmp_path).resolve()
    flag = _flag(legacy)
    status = runner.invoke(app, ["migrate", "status", "--repo", str(legacy)])
    assert f"next: Run `mb migrate {flag} --check` to preview" in status.output
    check = runner.invoke(app, ["migrate", "--repo", str(legacy), "--check"])
    assert f"run `mb migrate {flag} --apply`." in check.output
    assert f"Run `mb migrate {flag} --check --diff` to print" in check.output
    as_json = runner.invoke(app, ["migrate", "--repo", str(legacy), "--check", "--json"])
    assert json.loads(as_json.stdout)["next"].endswith(f"run `mb migrate {flag} --apply`.")
    applied = runner.invoke(app, ["migrate", "--repo", str(legacy), "--apply"])
    assert applied.exit_code == 0, applied.output
    quoted = _quoted(legacy)
    assert (
        f"next: Run `mb doctor {quoted}`, `mb validate {flag}`, and `mb start --json {flag}`."
        in applied.output
    )


def test_migrate_inside_the_repo_keeps_its_bare_suggestions(
    business: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy = _legacy_repo(tmp_path).resolve()
    monkeypatch.chdir(legacy)
    status = runner.invoke(app, ["migrate", "status"])
    assert "next: Run `mb migrate --check` to preview the migration before applying it." in (
        status.output
    )
    check = runner.invoke(app, ["migrate", "--check"])
    assert "run `mb migrate --apply`." in check.output
    assert "Run `mb migrate --check --diff` to print the full unified diff locally." in (
        check.output
    )
    applied = runner.invoke(app, ["migrate", "--apply"])
    assert (
        "next: Run `mb doctor`, `mb validate`, and `mb start --json` from the migrated repo."
        in applied.output
    )


# --- mb books ---------------------------------------------------------------


def test_books_status_names_the_business_in_its_doctor_hint(business: Path) -> None:
    result = runner.invoke(app, ["books", "status", str(business)])
    assert f"Run `mb books doctor --plan {_quoted(business)}` for safe setup repair" in (
        result.output
    )


def test_books_status_inside_the_repo_keeps_the_bare_hint(
    business: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(business)
    result = runner.invoke(app, ["books", "status"])
    assert "Run `mb books doctor --plan` for safe setup repair guidance." in result.output


# --- mb skill repair --------------------------------------------------------


def _stale_personal_skill(home: Path) -> Path:
    personal = home / ".claude" / "skills"
    personal.mkdir(parents=True)
    (personal / "start").symlink_to(home / "missing-engine" / "start")
    return personal


def test_skill_repair_names_the_business_in_its_apply_command(
    business: Path, tmp_path: Path
) -> None:
    personal = _stale_personal_skill(tmp_path / "home")
    command = f"mb skill repair {_flag(business)} --apply"
    result = runner.invoke(app, ["skill", "repair", "--repo", str(business)])
    assert result.exit_code == 0, result.output
    assert f"safe repair: run `{command}`" in result.output
    assert f"\n  {command}\n" in result.output
    as_json = runner.invoke(app, ["skill", "repair", "--repo", str(business), "--json"])
    assert json.loads(as_json.stdout)["repair_command"] == command
    assert (personal / "start").is_symlink()  # a dry run changes nothing


def test_skill_repair_inside_the_repo_keeps_the_bare_command(
    business: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stale_personal_skill(tmp_path / "home")
    monkeypatch.chdir(business)
    result = runner.invoke(app, ["skill", "repair", "--repo", "."])
    assert "safe repair: run `mb skill repair --repo . --apply`" in result.output
    assert "\n  mb skill repair --repo . --apply\n" in result.output
    as_json = runner.invoke(app, ["skill", "repair", "--repo", ".", "--json"])
    assert json.loads(as_json.stdout)["repair_command"] == "mb skill repair --repo . --apply"


# --- mb checkpoint --hook-status -------------------------------------------


@pytest.fixture
def plain_folder(business: Path, tmp_path: Path) -> Path:
    folder = tmp_path / "not a repo"
    folder.mkdir()
    return folder.resolve()


def test_hook_status_outside_git_names_the_folder_to_initialise(
    business: Path, plain_folder: Path
) -> None:
    result = runner.invoke(
        app, ["checkpoint", "--repo", str(plain_folder), "--hook-status", "--json"]
    )
    assert json.loads(result.stdout)["repair_command"] == f"git init {_quoted(plain_folder)}"
    human = runner.invoke(app, ["checkpoint", "--repo", str(plain_folder), "--hook-status"])
    assert f"repair: git init {_quoted(plain_folder)}\n" in human.output


def test_hook_status_outside_git_inside_the_folder_keeps_bare_git_init(
    business: Path, plain_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(plain_folder)
    result = runner.invoke(app, ["checkpoint", "--repo", str(plain_folder), "--hook-status"])
    assert "repair: git init\n" in result.output
