"""``mb skill validate`` structural checks for bundled skills."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mb import engine as engine_mod
from mb import skill_validate as skill_validate_mod
from mb.cli import app

runner = CliRunner()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _skill(
    root: Path,
    name: str,
    body: str = "See [details](references/details.md).\n",
    frontmatter: str | None = None,
) -> Path:
    skill_root = root / ".claude" / "skills" / name
    if frontmatter is None:
        frontmatter = f"---\nname: {name}\ndescription: Test skill.\nloops: [sense]\n---\n"
    _write(skill_root / "SKILL.md", frontmatter + "\n# Test\n\n" + body)
    _write(skill_root / "references" / "details.md", "# Details\n")
    return skill_root


def _patch_engine(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    skills_root = root / ".claude" / "skills"

    def skill_path(name: str) -> Path | None:
        candidate = skills_root / name
        return candidate if candidate.is_dir() else None

    def bundled_skills() -> list[str]:
        return sorted(path.name for path in skills_root.iterdir() if path.is_dir())

    monkeypatch.setattr(engine_mod, "skill_path", skill_path)
    monkeypatch.setattr(engine_mod, "bundled_skills", bundled_skills)


def test_skill_validate_passes_frontmatter_references_and_line_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(tmp_path, "mb-alpha")
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is True
    assert report["summary"]["line_count"] < skill_validate_mod.MAX_SKILL_LINES


def test_skill_validate_flags_missing_description(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(tmp_path, "mb-alpha", frontmatter="---\nname: mb-alpha\nloops: [sense]\n---\n")
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is False
    assert "missing key: description" in report["files"][0]["errors"]


def test_skill_validate_flags_unprefixed_bundled_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(
        tmp_path,
        "alpha",
        frontmatter="---\nname: alpha\ndescription: Test skill.\nloops: [sense]\n---\n",
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("alpha")

    assert report is not None
    assert report["ok"] is False
    assert "must use the 'mb-' vendor prefix" in report["files"][0]["errors"][0]


def test_skill_validate_flags_missing_loops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(
        tmp_path,
        "mb-alpha",
        frontmatter="---\nname: mb-alpha\ndescription: Test skill.\n---\n",
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is False
    assert "missing key: loops" in report["files"][0]["errors"]


def test_skill_validate_flags_invalid_loops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(
        tmp_path,
        "mb-alpha",
        frontmatter=(
            "---\nname: mb-alpha\ndescription: Test skill.\nloops: [sense, narrate, sense]\n---\n"
        ),
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is False
    errors = report["files"][0]["errors"]
    assert any("invalid slugs ['narrate']" in error for error in errors)
    assert "loops must not contain duplicate slugs" in errors


def test_skill_validate_flags_missing_local_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_root = _skill(tmp_path, "mb-alpha", body="See [missing](references/missing.md).\n")
    (skill_root / "references" / "details.md").unlink()
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is False
    assert any("references/missing.md" in error for error in report["files"][0]["errors"])


def test_skill_validate_checks_reference_file_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(tmp_path, "mb-alpha")
    _write(
        tmp_path / ".claude" / "skills" / "mb-alpha" / "references" / "details.md",
        "See [missing](missing-detail.md).\n",
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is False
    reference_result = next(
        item for item in report["files"] if item["path"] == "references/details.md"
    )
    assert reference_result["ok"] is False
    assert "missing-detail.md" in reference_result["errors"][0]


def test_skill_validate_warns_on_legacy_reference_paths_without_fallback_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(
        tmp_path,
        "mb-alpha",
        body="Read reference/core, then write.\n",
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is True
    assert report["summary"]["warnings"] == 1
    assert "legacy business-repo reference/* path" in report["files"][0]["warnings"][0]
    assert "prefer canonical core/" in report["files"][0]["warnings"][0]


def test_skill_validate_allows_legacy_reference_paths_with_fallback_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(
        tmp_path,
        "mb-alpha",
        body=("Use `reference/core/offer.md` only as a legacy fallback when `core/` is absent.\n"),
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is True
    assert report["summary"]["warnings"] == 0


def test_skill_validate_warns_on_legacy_reference_paths_in_referenced_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_root = _skill(
        tmp_path,
        "mb-alpha",
        body="See [setup](references/setup.md).\n",
    )
    _write(skill_root / "references" / "setup.md", "Read reference/offers.\n")
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is True
    assert report["summary"]["warnings"] == 1
    reference_result = next(
        item for item in report["files"] if item["path"] == "references/setup.md"
    )
    assert len(reference_result["warnings"]) == 1
    assert "prefer canonical core/" in reference_result["warnings"][0]


def test_skill_validate_warns_on_retired_reference_subfolders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(
        tmp_path,
        "mb-alpha",
        body="Write new angles to reference/proof/angles/.\n",
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is True
    assert report["summary"]["warnings"] == 1
    assert "legacy business-repo reference/* path" in report["files"][0]["warnings"][0]


def test_skill_validate_warns_on_retired_domain_rubric_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(
        tmp_path,
        "mb-alpha",
        body="Load the domain rubric before setup.\n",
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is True
    assert report["summary"]["warnings"] == 1
    assert "retired LLM-facing 'domain rubric' language" in report["files"][0]["warnings"][0]


def test_skill_validate_allows_historical_domain_rubric_migration_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(
        tmp_path,
        "mb-alpha",
        body="Historical migration notes may mention old domain-rubrics paths.\n",
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is True
    assert report["summary"]["warnings"] == 0


def test_skill_validate_flags_unbundled_slash_command_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(tmp_path, "mb-alpha", body="Route email requests to /newsletter.\n")
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is False
    assert "/newsletter is not a bundled Main Branch skill" in report["files"][0]["errors"][0]


def test_skill_validate_allows_bundled_slash_command_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(tmp_path, "mb-alpha", body="Route setup work to /mb-start.\n")
    _skill(tmp_path, "mb-start")
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is True


def test_skill_validate_flags_missing_cli_first_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(tmp_path, "mb-start", body="Read the repo and ask what the user needs.\n")
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-start")

    assert report is not None
    assert report["ok"] is False
    errors = report["files"][0]["errors"]
    assert any("missing `CLI facts first` instruction" in error for error in errors)
    assert any("mb status --json --peek" in error for error in errors)


def test_skill_validate_accepts_cli_first_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(
        tmp_path,
        "mb-end",
        body=(
            "## CLI Facts First\n\n"
            "Run `mb status --json --peek` and `mb checkpoint --plan --json` "
            "before summarizing the session.\n"
        ),
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-end")

    assert report is not None
    assert report["ok"] is True


def test_skill_validate_flags_raw_git_before_cli_first_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(
        tmp_path,
        "mb-end",
        body=(
            "Run `git status --short` to inspect work.\n\n"
            "## CLI Facts First\n\n"
            "Run `mb status --json --peek` and `mb checkpoint --plan --json`.\n"
        ),
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-end")

    assert report is not None
    assert report["ok"] is False
    assert any(
        "raw git check appears before the CLI-first contract" in error
        for error in report["files"][0]["errors"]
    )
    assert any(error.startswith("line 9:") for error in report["files"][0]["errors"])


def test_skill_validate_does_not_allow_raw_git_because_context_says_not_optional(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(
        tmp_path,
        "mb-start",
        body=(
            "## CLI Facts First\n\n"
            "Run `mb status --json --peek` before routing.\n"
            "This is not optional.\n"
            "Run `git status --short` next.\n"
        ),
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-start")

    assert report is not None
    assert report["ok"] is False
    assert any(
        "raw git check appears before the CLI-first contract" in error
        for error in report["files"][0]["errors"]
    )


def test_skill_validate_allows_raw_git_fallback_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(
        tmp_path,
        "mb-start",
        body=(
            "## CLI Facts First\n\n"
            "Run `mb status --json --peek` before routing.\n"
            "Do not run raw `git log` unless status says journal facts are unavailable.\n"
        ),
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-start")

    assert report is not None
    assert report["ok"] is True


def test_skill_validate_flags_unshipped_mb_command_promises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(tmp_path, "mb-alpha", body="Save and then run `mb publish --plan`.\n")
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is False
    assert "not a shipped mb command" in report["files"][0]["errors"][0]


def test_skill_validate_allows_unshipped_command_boundary_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(
        tmp_path,
        "mb-alpha",
        body="The planned `mb publish --plan` command is not shipped yet; do not promise it.\n",
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is True


def test_skill_validate_ignores_non_command_slash_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(
        tmp_path,
        "mb-alpha",
        body=(
            "Use `~/Documents/GitHub/mb-vip`, `.claude/skills/mb-start`, "
            "`https://example.com/foo`, and `/start/thanks/` as path examples.\n"
        ),
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is True


def test_skill_validate_ignores_reference_paths_inside_code_fences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(
        tmp_path,
        "mb-alpha",
        body="```bash\ncat references/generated-at-runtime.md\n```\n",
    )
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is True


def test_skill_validate_flags_parent_directory_references(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(tmp_path, "mb-alpha", body="See [other](../beta/SKILL.md).\n")
    _skill(tmp_path, "mb-beta")
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is False
    assert any("outside the skill directory" in error for error in report["files"][0]["errors"])


def test_mb_ads_review_references_are_skill_local() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    skill_root = repo_root / ".claude" / "skills" / "mb-ads"
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            skill_root / "references" / "review-workflow.md",
            skill_root / "references" / "mode-static-ads.md",
            skill_root / "references" / "post-generation-pipeline.md",
        ]
    )

    assert "../../lenses" not in text
    assert "../../reference/compliance" not in text
    assert "engine's `lenses" not in text
    assert (skill_root / "references" / "lenses" / "ftc-compliance.md").is_file()
    assert (skill_root / "references" / "compliance" / "angle-playbook.md").is_file()


def test_skill_validate_flags_line_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = "\n".join(f"line {i}" for i in range(skill_validate_mod.MAX_SKILL_LINES + 1))
    _skill(tmp_path, "mb-alpha", body=body)
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run("mb-alpha")

    assert report is not None
    assert report["ok"] is False
    assert any("limit is 500" in error for error in report["files"][0]["errors"])


def test_skill_validate_all_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _skill(tmp_path, "mb-alpha")
    _skill(tmp_path, "mb-beta", body="See [missing](references/missing.md).\n")
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run_all()

    assert report["ok"] is False
    assert report["mode"] == "all"
    assert report["summary"]["skills"] == 2
    assert report["summary"]["passed"] == 1
    assert report["summary"]["failed"] == 1


def test_skill_validate_all_fails_when_no_bundled_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    _patch_engine(monkeypatch, tmp_path)

    report = skill_validate_mod.run_all()

    assert report["ok"] is False
    assert report["summary"]["skills"] == 0
    assert report["summary"]["errors"] == 1
    assert report["errors"] == ["no bundled skills found"]


def test_skill_validate_human_output_includes_top_level_errors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = {
        "ok": False,
        "command": "mb skill validate",
        "mode": "all",
        "skills": [],
        "errors": ["no bundled skills found"],
        "summary": {"skills": 0, "passed": 0, "failed": 0, "errors": 1, "warnings": 0},
    }

    skill_validate_mod.render_human(report)

    assert "no bundled skills found" in capsys.readouterr().out


def test_skill_validate_cli_json_and_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _skill(tmp_path, "mb-alpha")
    _skill(tmp_path, "mb-beta", body="See [missing](references/missing.md).\n")
    _patch_engine(monkeypatch, tmp_path)

    result = runner.invoke(app, ["skill", "validate", "mb-alpha", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["summary"]["passed"] == 1

    result = runner.invoke(app, ["skill", "validate", "mb-beta", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False

    result = runner.invoke(app, ["skill", "validate", "missing", "--json"])
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["errors"] == ["skill not found: missing"]

    result = runner.invoke(app, ["skill", "validate", "--all", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["mode"] == "all"
    assert payload["summary"]["failed"] == 1


def test_every_copy_of_the_update_result_table_handles_a_manual_upgrade() -> None:
    """`mb update` can report a manual path on every uv and wheel install.

    Six bundled files duplicate the `mb update --json` result table. When
    `new_version` reports what PyPI offers, a copy that only knows the
    `old_version != new_version` row tells the operator "Updated Main Branch"
    on a run that upgraded nothing (#963). Keyed on `manual_update_command`
    rather than `ok` so a failed surface refresh cannot hide the command.

    Collapsing these copies into one shared reference is tracked separately;
    until then this keeps them from drifting apart again.
    """
    repo_root = Path(__file__).resolve().parents[2]
    claimed_update = "Updated Main Branch and refreshed skill links."
    copies = sorted(
        path
        for path in repo_root.joinpath(".claude").rglob("*.md")
        if claimed_update in path.read_text(encoding="utf-8")
    )

    assert len(copies) == 6, [str(path.relative_to(repo_root)) for path in copies]
    missing = [
        str(path.relative_to(repo_root))
        for path in copies
        if "manual_update_command" not in path.read_text(encoding="utf-8")
    ]
    assert missing == [], missing

    # The row also has to branch on the version inside itself. A manual path
    # always sets `manual_update_command`, including when the operator is
    # current, so a row that only knows "did not upgrade" forbids the one true
    # answer on the common path.
    unbranched = []
    for path in copies:
        row = next(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("| `manual_update_command`")
        )
        if not ("old_version != new_version" in row and "old_version == new_version" in row):
            unbranched.append(str(path.relative_to(repo_root)))
    assert unbranched == [], unbranched
