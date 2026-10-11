"""``mb migrate`` schema migration contract tests."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from typer.testing import CliRunner

from mb import migrate as migrate_mod
from mb import migrations
from mb.cli import app

runner = CliRunner()


def _legacy_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "legacy"
    (repo / "reference" / "core").mkdir(parents=True)
    (repo / "reference" / "offers" / "flagship").mkdir(parents=True)
    (repo / "reference" / "proof" / "angles").mkdir(parents=True)
    (repo / "reference" / "brand").mkdir(parents=True)
    (repo / "reference" / "strategy").mkdir(parents=True)
    (repo / "reference" / "visual-identity").mkdir(parents=True)
    (repo / "reference" / "domain" / "funnel").mkdir(parents=True)
    (repo / "research").mkdir()
    (repo / "decisions").mkdir()
    (repo / "reference" / "core" / "offer.md").write_text("# Offer\n", encoding="utf-8")
    (repo / "reference" / "core" / "audience.md").write_text("# Audience\n", encoding="utf-8")
    (repo / "reference" / "offers" / "flagship" / "offer.md").write_text(
        "# Flagship\n",
        encoding="utf-8",
    )
    (repo / "reference" / "proof" / "testimonials.md").write_text(
        "# Testimonials\n",
        encoding="utf-8",
    )
    (repo / "reference" / "proof" / "angles" / "clarity.md").write_text(
        "# Clarity\n",
        encoding="utf-8",
    )
    (repo / "reference" / "visual-identity" / "visual-style.md").write_text(
        "# Visual Style\n",
        encoding="utf-8",
    )
    (repo / "reference" / "brand" / "voice-system.md").write_text(
        "# Voice System\n",
        encoding="utf-8",
    )
    (repo / "reference" / "strategy" / "market-position.md").write_text(
        "# Market Position\n",
        encoding="utf-8",
    )
    (repo / "reference" / "domain" / "content-strategy.md").write_text(
        "# Content Strategy\n",
        encoding="utf-8",
    )
    (repo / "reference" / "domain" / "product-ladder.md").write_text(
        "# Product Ladder\n",
        encoding="utf-8",
    )
    (repo / "reference" / "domain" / "funnel" / "skool-surfaces.md").write_text(
        "# Skool Surfaces\n",
        encoding="utf-8",
    )
    (repo / "CLAUDE.md").write_text(
        "Read `reference/core/*.md` and `reference/offers/flagship/offer.md`.\n",
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text(".env\n", encoding="utf-8")
    return repo


def test_migrate_status_reports_pending_legacy_schema(tmp_path: Path) -> None:
    repo = _legacy_repo(tmp_path)

    result = runner.invoke(app, ["migrate", "status", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema"] == "mb.migrate"
    assert payload["schema_version"] == 2
    assert payload["current_version"] == "0.1"
    assert payload["latest_version"] == "0.2"
    assert payload["pending"][0]["name"] == "001_v01_to_v02_path_config"


def test_migrate_status_blocks_future_schema(tmp_path: Path) -> None:
    repo = tmp_path / "future"
    (repo / ".mb").mkdir(parents=True)
    (repo / ".mb" / "schema_version").write_text("9.0\n", encoding="utf-8")

    result = runner.invoke(app, ["migrate", "status", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["current_version"] == "9.0"
    assert payload["pending"] == []
    assert "newer than this engine supports" in payload["errors"][0]


def test_migrate_check_blocks_future_schema_without_plan(tmp_path: Path) -> None:
    repo = tmp_path / "future"
    (repo / ".mb").mkdir(parents=True)
    (repo / ".mb" / "schema_version").write_text("9.0\n", encoding="utf-8")

    result = runner.invoke(app, ["migrate", "--repo", str(repo), "--check", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["plan"]["has_changes"] is False
    assert "newer than this engine supports" in payload["errors"][0]


def test_migrate_check_prints_privacy_safe_summary_when_pending(tmp_path: Path) -> None:
    repo = _legacy_repo(tmp_path)

    result = runner.invoke(app, ["migrate", "--repo", str(repo), "--check"])

    assert result.exit_code == 1
    assert "pending migration changes:" in result.stdout
    assert "move_file: reference/core/offer.md -> core/offer.md" in result.stdout
    assert (
        "move_file: reference/proof/testimonials.md -> core/proof/testimonials.md" in result.stdout
    )
    assert (
        "move_file: reference/domain/content-strategy.md -> core/content-strategy.md"
        in result.stdout
    )
    # Run from another folder, so the suggested command names the repo.
    assert (
        f"Run `mb migrate --repo {shlex.quote(str(repo.resolve()))} --check --diff`"
        in result.stdout
    )
    assert "--- a/reference/core/offer.md" not in result.stdout
    assert "# Offer" not in result.stdout


def test_migrate_check_diff_is_explicit(tmp_path: Path) -> None:
    repo = _legacy_repo(tmp_path)

    result = runner.invoke(app, ["migrate", "--repo", str(repo), "--check", "--diff"])

    assert result.exit_code == 1
    assert "--- a/reference/core/offer.md" in result.stdout
    assert "+++ b/core/offer.md" in result.stdout
    assert "+++ b/core/offers/flagship/offer.md" in result.stdout
    assert "+++ b/core/proof/testimonials.md" in result.stdout
    assert "+++ b/core/brand/visual-style.md" in result.stdout
    assert "+++ b/core/content-strategy.md" in result.stdout
    assert "+++ b/core/product-ladder.md" in result.stdout
    assert "+++ b/core/operations/funnel/skool-surfaces.md" in result.stdout
    assert "+++ b/campaigns/.gitkeep" not in result.stdout
    assert "+++ b/.gitignore" in result.stdout
    assert "+.mb/backups/" in result.stdout
    assert "+++ b/.mb/schema_version" in result.stdout
    assert "+++ b/decisions/2026-05-02-mainbranch-v02-path-migration.md" in result.stdout


def test_migrate_check_json_exposes_same_plan(tmp_path: Path) -> None:
    repo = _legacy_repo(tmp_path)

    result = runner.invoke(app, ["migrate", "--repo", str(repo), "--check", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["action"] == "check"
    assert payload["plan"]["has_changes"] is True
    assert payload["plan"]["diff_included"] is False
    assert payload["plan"]["diff"] == ""
    assert "Full file diffs are hidden by default" in payload["plan"]["privacy_note"]
    assert payload["plan"]["migrations"][0]["migration"]["id"] == "001"
    changes = payload["plan"]["migrations"][0]["changes"]
    assert {"kind": "mkdir", "path": "pushes", "source": "", "target": ""} in changes
    assert not any(change["path"] == "campaigns" for change in changes)
    assert payload["backup"]["will_create"] is True
    assert payload["backup"]["directory"] == ".mb/backups/"
    assert payload["next"] == (
        "Review this dry-run. If it matches the move you want, run "
        f"`mb migrate --repo {shlex.quote(str(repo.resolve()))} --apply`."
    )


def test_migrate_check_json_diff_is_explicit(tmp_path: Path) -> None:
    repo = _legacy_repo(tmp_path)

    result = runner.invoke(
        app,
        ["migrate", "--repo", str(repo), "--check", "--diff", "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["plan"]["diff_included"] is True
    assert "b/core/offer.md" in payload["plan"]["diff"]


def test_migrate_status_honors_root_repo_option(tmp_path: Path) -> None:
    repo = _legacy_repo(tmp_path)
    current = tmp_path / "current"
    (current / "core").mkdir(parents=True)
    (current / ".mb").mkdir()
    (current / ".mb" / "schema_version").write_text("0.2\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["migrate", "--repo", str(repo), "status", "--json"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["repo"] == str(repo.resolve())
    assert payload["current_version"] == "0.1"


def test_migrate_apply_moves_files_backs_up_and_is_idempotent(tmp_path: Path) -> None:
    repo = _legacy_repo(tmp_path)

    result = runner.invoke(app, ["migrate", "--repo", str(repo), "--apply", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["current_version"] == "0.2"
    assert payload["applied"][0]["id"] == "001"
    backup = Path(payload["backup"]["path"])
    assert backup.is_dir()
    assert (backup / "reference" / "core" / "offer.md").exists()
    assert (backup / ".gitignore").exists()
    assert (repo / ".mb" / "schema_version").read_text(encoding="utf-8") == "0.2\n"
    assert ".mb/backups/" in (repo / ".gitignore").read_text(encoding="utf-8")
    assert (repo / "core" / "offer.md").read_text(encoding="utf-8") == "# Offer\n"
    assert (repo / "core" / "offers" / "flagship" / "offer.md").exists()
    assert (repo / "core" / "proof" / "testimonials.md").exists()
    assert (repo / "core" / "proof" / "angles" / "clarity.md").exists()
    assert (repo / "core" / "brand" / "visual-style.md").exists()
    assert (repo / "core" / "brand" / "voice-system.md").exists()
    assert (repo / "core" / "strategy" / "market-position.md").exists()
    assert (repo / "core" / "content-strategy.md").exists()
    assert (repo / "core" / "product-ladder.md").exists()
    assert (repo / "core" / "operations" / "funnel" / "skool-surfaces.md").exists()
    assert (repo / "pushes" / ".gitkeep").exists()
    assert not (repo / "campaigns").exists()
    assert (repo / "reference" / "core").is_symlink()
    assert (repo / "reference" / "offers").is_symlink()
    assert not (repo / "reference" / "proof").exists()
    assert not (repo / "reference" / "brand").exists()
    assert not (repo / "reference" / "strategy").exists()
    assert not (repo / "reference" / "visual-identity").exists()
    assert not (repo / "reference" / "domain").exists()
    assert "core/*.md" in (repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert (repo / "decisions" / "2026-05-02-mainbranch-v02-path-migration.md").exists()

    rerun = runner.invoke(app, ["migrate", "--repo", str(repo), "--apply", "--json"])
    assert rerun.exit_code == 0
    rerun_payload = json.loads(rerun.stdout)
    assert rerun_payload["applied"] == []
    assert rerun_payload["pending"] == []


def test_migrate_ignores_os_metadata_files(tmp_path: Path) -> None:
    repo = _legacy_repo(tmp_path)
    (repo / "reference" / "offers" / ".DS_Store").write_text("metadata", encoding="utf-8")
    (repo / "reference" / "core" / "._offer.md").write_text("metadata", encoding="utf-8")
    (repo / "reference" / "offers" / "flagship" / "assets").mkdir()
    (repo / "reference" / "offers" / "flagship" / "assets" / ".DS_Store").write_text(
        "metadata",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["migrate", "--repo", str(repo), "--check", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    changes = payload["plan"]["migrations"][0]["changes"]
    assert not any(".DS_Store" in str(change) for change in changes)
    assert not any("._offer.md" in str(change) for change in changes)

    applied = runner.invoke(app, ["migrate", "--repo", str(repo), "--apply", "--json"])
    assert applied.exit_code == 0
    applied_payload = json.loads(applied.stdout)
    assert applied_payload["ok"] is True
    assert (repo / "reference" / "core").is_symlink()
    assert (repo / "reference" / "offers").is_symlink()
    backup = Path(applied_payload["backup"]["path"])
    assert (backup / "reference" / "offers" / ".DS_Store").exists()
    assert (backup / "reference" / "core" / "._offer.md").exists()
    assert (backup / "reference" / "offers" / "flagship" / "assets" / ".DS_Store").exists()


def test_migrate_diff_rejects_status_subcommand(tmp_path: Path) -> None:
    repo = _legacy_repo(tmp_path)

    result = runner.invoke(app, ["migrate", "--repo", str(repo), "--diff", "status"])

    assert result.exit_code == 2
    assert "--diff can only be used with --check" in result.stderr


def test_migrate_apply_aborts_before_writes_on_conflict(tmp_path: Path) -> None:
    repo = _legacy_repo(tmp_path)
    (repo / "core").mkdir()
    (repo / "core" / "offer.md").write_text("# Different\n", encoding="utf-8")

    result = runner.invoke(app, ["migrate", "--repo", str(repo), "--apply", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(
        "core/offer.md already exists with different contents" in error
        for error in payload["errors"]
    )
    assert any("from reference/core/offer.md" in error for error in payload["errors"])
    assert (
        f"rerun `mb migrate --repo {shlex.quote(str(repo.resolve()))} --check`" in payload["next"]
    )
    assert not (repo / ".mb" / "backups").exists()
    assert (repo / "reference" / "core" / "offer.md").exists()


def test_migrate_check_conflict_renders_plan_and_safe_next_command(tmp_path: Path) -> None:
    repo = _legacy_repo(tmp_path)
    (repo / "core").mkdir()
    (repo / "core" / "offer.md").write_text("# Different\n", encoding="utf-8")

    result = runner.invoke(app, ["migrate", "--repo", str(repo), "--check"])

    assert result.exit_code == 1
    assert "migration blocked; no files changed." in result.stdout
    assert (
        "error: core/offer.md already exists with different contents "
        "(from reference/core/offer.md); manual reconciliation required"
    ) in result.stdout
    assert "pending migration changes:" in result.stdout
    assert "move_file: reference/core/audience.md -> core/audience.md" in result.stdout
    assert "next: Do not apply yet." in result.stdout


def test_migrate_apply_reports_structured_error_when_legacy_dir_is_not_empty(
    tmp_path: Path,
) -> None:
    repo = _legacy_repo(tmp_path)
    (repo / "reference" / "core" / "linked").symlink_to(repo / "outside")

    result = runner.invoke(app, ["migrate", "--repo", str(repo), "--apply", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "reference/core is not empty" in payload["errors"][0]
    assert payload["backup"]["path"]


def test_migrate_status_clean_current_repo(tmp_path: Path) -> None:
    repo = tmp_path / "current"
    (repo / "core").mkdir(parents=True)
    (repo / ".mb").mkdir()
    (repo / ".mb" / "schema_version").write_text("0.2\n", encoding="utf-8")

    result = migrate_mod.status(repo)

    assert result["current_version"] == "0.2"
    assert result["pending"] == []


def test_migration_version_map_is_derived_from_registered_metadata() -> None:
    assert migrations.version_map()["0.1"] == "mb.migrations.001_v01_to_v02_path_config"


# ---------------------------------------------------------------------------
# campaigns -> pushes plan-only migration (MAIN-249)
# ---------------------------------------------------------------------------


def test_plan_campaigns_no_legacy_folder_is_a_clean_noop(tmp_path: Path) -> None:
    result = migrate_mod.plan_campaigns_to_pushes(tmp_path)

    assert result["schema"] == migrate_mod.CAMPAIGNS_PLAN_SCHEMA
    assert result["ok"] is True
    assert result["summary"] == {"moves": 0, "ambiguous": 0, "blockers": 0}
    assert "no legacy campaigns/" in result["next"]


def test_plan_campaigns_classifies_dated_folder_as_move(tmp_path: Path) -> None:
    folder = tmp_path / "campaigns" / "2026-04-15-spring-launch"
    folder.mkdir(parents=True)
    (folder / "campaign.md").write_text(
        "---\n"
        "type: campaign\n"
        "slug: spring-launch\n"
        "status: active\n"
        "started: 2026-04-15\n"
        "linked_campaigns: []\n"
        "provider_refs:\n"
        "  meta_ads:\n"
        "    campaign_id: '123'\n"
        "---\n"
        "# Spring Launch\n",
        encoding="utf-8",
    )
    (folder / "ads.md").write_text("# ads\n", encoding="utf-8")
    (folder / "review-log.md").write_text("# review log\n", encoding="utf-8")

    result = migrate_mod.plan_campaigns_to_pushes(tmp_path)

    assert result["summary"] == {"moves": 1, "ambiguous": 0, "blockers": 0}
    move = result["moves"][0]
    assert move["from"] == "campaigns/2026-04-15-spring-launch"
    assert move["to"] == "pushes/2026-04-15-spring-launch/push.md"
    assert move["date"] == "2026-04-15"
    assert move["date_source"] == "folder.day-prefix"
    assert "type: campaign -> type: push" in move["frontmatter_changes"]
    assert "linked_campaigns -> linked_pushes (rename)" in move["frontmatter_changes"]
    assert any("provider_refs.meta_ads.campaign_id" in note for note in move["notes"])
    # ads.md and review-log.md are recognized push artifacts and auto-move with the push.
    assert "campaigns/2026-04-15-spring-launch/ads.md" in move["move_with_push"]
    assert "campaigns/2026-04-15-spring-launch/review-log.md" in move["move_with_push"]
    assert move["review_inside_folder"] == []


def test_plan_campaigns_flags_unrecognized_files_inside_a_move_for_review(
    tmp_path: Path,
) -> None:
    """Per the rubric, only recognized push artifacts auto-move with the push.

    Unrecognized files inside the campaign folder (e.g. random notes, non-push
    subfolders) should NOT be auto-promoted; they surface for operator review.
    """
    folder = tmp_path / "campaigns" / "2026-04-15-spring-launch"
    folder.mkdir(parents=True)
    (folder / "campaign.md").write_text(
        "---\nslug: spring-launch\nstatus: active\nstarted: 2026-04-15\n---\n# spring\n",
        encoding="utf-8",
    )
    (folder / "ads.md").write_text("# ads\n", encoding="utf-8")  # recognized
    (folder / "random-notes.md").write_text("# random\n", encoding="utf-8")  # unrecognized
    (folder / "weird-subdir").mkdir()  # unrecognized folder
    (folder / "weird-subdir" / "thing.md").write_text("# thing\n", encoding="utf-8")

    result = migrate_mod.plan_campaigns_to_pushes(tmp_path)

    move = result["moves"][0]
    assert "campaigns/2026-04-15-spring-launch/ads.md" in move["move_with_push"]
    assert "campaigns/2026-04-15-spring-launch/random-notes.md" in move["review_inside_folder"]
    assert "campaigns/2026-04-15-spring-launch/weird-subdir" in move["review_inside_folder"]
    assert any(
        "unrecognized files inside this folder will NOT auto-move" in note for note in move["notes"]
    )


def test_plan_campaigns_classifies_loose_top_level_file_as_ambiguous(tmp_path: Path) -> None:
    """A file directly under campaigns/ (not inside a push folder) is ambiguous.

    Doctor flags these as ambiguous_files; migrate must agree, not silently
    skip them by walking only directories.
    """
    (tmp_path / "campaigns").mkdir()
    (tmp_path / "campaigns" / "loose.md").write_text("# loose\n", encoding="utf-8")

    result = migrate_mod.plan_campaigns_to_pushes(tmp_path)

    assert result["summary"] == {"moves": 0, "ambiguous": 1, "blockers": 0}
    ambiguous = result["ambiguous"][0]
    assert ambiguous["from"] == "campaigns/loose.md"
    assert "loose file at the top of campaigns/" in ambiguous["reason"]


def test_plan_campaigns_uses_git_first_added_date_when_other_signals_are_missing(
    tmp_path: Path,
) -> None:
    """Migration Rubric: folder prefix > frontmatter > git first-added.

    A repo with a real git history exposes the file's first-added date; the
    planner uses it when no other signal is available.
    """
    repo = tmp_path / "biz"
    repo.mkdir()
    folder = repo / "campaigns" / "spring-launch"
    folder.mkdir(parents=True)
    record = folder / "campaign.md"
    record.write_text(
        "---\nslug: spring-launch\nstatus: active\n---\n# spring\n",
        encoding="utf-8",
    )

    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "initial",
            "--date",
            "2026-04-10T00:00:00",
        ],
        cwd=repo,
        check=True,
        env={
            "GIT_AUTHOR_DATE": "2026-04-10T00:00:00",
            "GIT_COMMITTER_DATE": "2026-04-10T00:00:00",
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )

    result = migrate_mod.plan_campaigns_to_pushes(repo)

    assert result["summary"]["moves"] == 1
    move = result["moves"][0]
    assert move["date"] == "2026-04-10"
    assert move["date_source"] == "git.first-added"


def test_plan_campaigns_uses_month_prefix_when_only_month_is_present(tmp_path: Path) -> None:
    folder = tmp_path / "campaigns" / "2026-04-spring"
    folder.mkdir(parents=True)
    (folder / "campaign.md").write_text(
        "---\nslug: spring\nstatus: active\n---\n# spring\n",
        encoding="utf-8",
    )

    result = migrate_mod.plan_campaigns_to_pushes(tmp_path)

    assert result["summary"]["moves"] == 1
    move = result["moves"][0]
    assert move["date"] == "2026-04-01"
    assert move["date_source"] == "folder.month-prefix"
    assert move["to"] == "pushes/2026-04-01-spring/push.md"


def test_plan_campaigns_uses_frontmatter_date_when_folder_has_no_prefix(tmp_path: Path) -> None:
    folder = tmp_path / "campaigns" / "spring-launch"
    folder.mkdir(parents=True)
    (folder / "campaign.md").write_text(
        "---\nslug: spring-launch\nstatus: active\nstarted: 2026-04-15\n---\n# spring\n",
        encoding="utf-8",
    )

    result = migrate_mod.plan_campaigns_to_pushes(tmp_path)

    assert result["summary"]["moves"] == 1
    move = result["moves"][0]
    assert move["date"] == "2026-04-15"
    assert move["date_source"] == "frontmatter.started"


def test_plan_campaigns_blocks_when_no_date_is_inferable(tmp_path: Path) -> None:
    folder = tmp_path / "campaigns" / "spring-launch"
    folder.mkdir(parents=True)
    (folder / "campaign.md").write_text(
        "---\nslug: spring-launch\nstatus: active\n---\n# spring\n",
        encoding="utf-8",
    )

    result = migrate_mod.plan_campaigns_to_pushes(tmp_path)

    assert result["summary"]["blockers"] == 1
    assert result["ok"] is False
    blocker = result["blockers"][0]
    assert "cannot infer a date" in blocker["reason"]


def test_plan_campaigns_routes_subfolder_without_campaign_md_to_ambiguous(tmp_path: Path) -> None:
    # Per the rubric, ambiguous generated folders (e.g. campaigns/organic-scripts/)
    # should not be auto-promoted to pushes. They surface for operator review.
    folder = tmp_path / "campaigns" / "organic-scripts"
    folder.mkdir(parents=True)
    (folder / "post-1.md").write_text("# post 1\n", encoding="utf-8")
    (folder / "post-2.md").write_text("# post 2\n", encoding="utf-8")

    result = migrate_mod.plan_campaigns_to_pushes(tmp_path)

    assert result["summary"] == {"moves": 0, "ambiguous": 1, "blockers": 0}
    ambiguous = result["ambiguous"][0]
    assert ambiguous["from"] == "campaigns/organic-scripts"
    assert "no campaign.md" in ambiguous["reason"]


def test_migrate_campaigns_cli_plan_emits_machine_readable_json(tmp_path: Path) -> None:
    folder = tmp_path / "campaigns" / "2026-04-15-spring-launch"
    folder.mkdir(parents=True)
    (folder / "campaign.md").write_text(
        "---\nslug: spring-launch\nstatus: active\n---\n# spring\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["migrate", "--repo", str(tmp_path), "campaigns", "--plan", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema"] == migrate_mod.CAMPAIGNS_PLAN_SCHEMA
    assert payload["summary"]["moves"] == 1
    assert payload["moves"][0]["to"] == "pushes/2026-04-15-spring-launch/push.md"


def test_migrate_campaigns_cli_plan_renders_move_children_for_humans(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "campaigns" / "2026-04-15-spring-launch"
    folder.mkdir(parents=True)
    (folder / "campaign.md").write_text(
        "---\nslug: spring-launch\nstatus: active\n---\n# spring\n",
        encoding="utf-8",
    )
    (folder / "ads.md").write_text("# ads\n", encoding="utf-8")
    (folder / "random-notes.md").write_text("# random\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["migrate", "--repo", str(tmp_path), "campaigns", "--plan"],
    )

    assert result.exit_code == 0
    assert "move with push: 1 item(s)" in result.stdout
    assert "campaigns/2026-04-15-spring-launch/ads.md" in result.stdout
    assert "review before apply: 1 item(s)" in result.stdout
    assert "campaigns/2026-04-15-spring-launch/random-notes.md" in result.stdout


def test_migrate_campaigns_cli_without_plan_flag_refuses(tmp_path: Path) -> None:
    """Apply is not yet implemented; the command refuses without --plan."""
    result = runner.invoke(
        app,
        ["migrate", "--repo", str(tmp_path), "campaigns"],
    )

    assert result.exit_code == 2
    assert "--plan is required" in result.stderr or "--plan is required" in (result.output or "")
