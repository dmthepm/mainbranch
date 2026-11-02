"""Command implementations extracted from :mod:`mb.cli`."""

from __future__ import annotations

import json
from typing import Any

import typer

from mb import skill_validate as skill_validate_mod
from mb.cli_common import (
    _unreadable_guard,
)
from mb.engine import repo_flag


def skill_path_cmd(
    name: str = typer.Argument(..., help="Skill name (e.g. 'mb-site')."),
) -> None:
    """Print the on-disk path to a bundled skill."""
    from mb.resolve import skill_path

    result = skill_path(name)
    if result is None:
        typer.echo(f"skill not found: {name}", err=True)
        raise typer.Exit(1)
    typer.echo(str(result))


def skill_list_cmd() -> None:
    """List bundled skills."""
    from mb.resolve import bundled_skills

    for s in bundled_skills():
        typer.echo(s)


def skill_validate_cmd(
    name: str | None = typer.Argument(None, help="Skill name (e.g. 'mb-site')."),
    all_skills: bool = typer.Option(False, "--all", help="Validate every bundled skill."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Validate bundled skill frontmatter and local references."""
    if all_skills and name is not None:
        payload = {
            "ok": False,
            "command": "mb skill validate",
            "mode": "invalid",
            "skills": [],
            "summary": {"skills": 0, "passed": 0, "failed": 0, "errors": 1, "warnings": 0},
            "errors": ["choose either a skill name or --all, not both"],
        }
        if json_out:
            typer.echo(json.dumps(payload, indent=2))
        else:
            typer.echo("mb skill validate: choose either a skill name or --all", err=True)
        raise typer.Exit(2)
    if not all_skills and name is None:
        payload = {
            "ok": False,
            "command": "mb skill validate",
            "mode": "invalid",
            "skills": [],
            "summary": {"skills": 0, "passed": 0, "failed": 0, "errors": 1, "warnings": 0},
            "errors": ["provide a skill name or --all"],
        }
        if json_out:
            typer.echo(json.dumps(payload, indent=2))
        else:
            typer.echo("mb skill validate: provide a skill name or --all", err=True)
        raise typer.Exit(2)

    if all_skills:
        report = skill_validate_mod.run_all()
    else:
        assert name is not None
        skill_report = skill_validate_mod.run(name)
        if skill_report is None:
            payload = {
                "ok": False,
                "command": "mb skill validate",
                "mode": "single",
                "skills": [],
                "summary": {
                    "skills": 0,
                    "passed": 0,
                    "failed": 0,
                    "errors": 1,
                    "warnings": 0,
                },
                "errors": [f"skill not found: {name}"],
            }
            if json_out:
                typer.echo(json.dumps(payload, indent=2))
            else:
                typer.echo(f"skill not found: {name}", err=True)
            raise typer.Exit(2)
        report = skill_validate_mod.envelope([skill_report], mode="single")

    if json_out:
        typer.echo(json.dumps(report, indent=2))
    else:
        skill_validate_mod.render_human(report)
    raise typer.Exit(0 if report["ok"] else 1)


def skill_link_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo to wire for Claude Code."),
    plugin: bool = typer.Option(
        False,
        "--plugin",
        help=(
            "Also write the worktree-durable plugin wiring into tracked "
            ".claude/settings.json (parallel rail; symlinks still written)."
        ),
    ),
    plan: bool = typer.Option(
        False,
        "--plan",
        help="Report what would change, including tracked files, and write nothing.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Wire bundled skills into a business repo for Claude Code discovery."""
    from mb.engine import link_skills, plan_link_skills, write_plugin_wiring

    if plan:
        if plugin:
            typer.echo("mb skill link: --plan cannot be combined with --plugin", err=True)
            raise typer.Exit(2)
        planned = _unreadable_guard(
            repo,
            command="mb skill link",
            schema_name="mainbranch.skill.link.result",
            json_out=json_out,
            read=lambda: plan_link_skills(repo),
        )
        if json_out:
            typer.echo(json.dumps(planned, indent=2))
        else:
            typer.echo(f"would link {len(planned['linked'])} skill(s) in {planned['repo']}")
            for path in planned["tracked_writes"]:
                typer.echo(f"  would change tracked file: {path}")
            for error in planned["errors"]:
                typer.echo(f"  - {error}", err=True)
        raise typer.Exit(0 if planned["ok"] else 1)

    result = link_skills(repo)
    plugin_result: dict[str, Any] | None = None
    if plugin:
        plugin_result = write_plugin_wiring(repo)
        result["plugin_wiring"] = plugin_result
    if json_out:
        typer.echo(json.dumps(result, indent=2))
    else:
        if result["ok"]:
            typer.echo(f"linked Main Branch: {result['engine_root']}")
            typer.echo(f"repo: {result['repo']}")
            if result["linked"]:
                typer.echo(f"  + linked {len(result['linked'])} skill(s)")
            if result["copied"]:
                typer.echo(f"  + copied {len(result['copied'])} skill(s)")
            if result["skipped"]:
                typer.echo(f"  · {len(result['skipped'])} already wired")
            if plugin_result is not None:
                typer.echo(f"  + {plugin_result['summary']}")
            typer.echo("")
            typer.echo("you're set — run `claude` and then /mb-start.")
        else:
            typer.echo("could not link Main Branch skills:", err=True)
            for error in result["errors"]:
                typer.echo(f"  - {error}", err=True)
            raise typer.Exit(1)


def skill_repair_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo to inspect."),
    apply_changes: bool = typer.Option(
        False,
        "--apply",
        help="Move stale or broken Main Branch personal skill links to a timestamped backup.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Inspect or repair personal Claude Code skills that shadow Main Branch."""
    from mb.engine import inspect_personal_skill_conflicts

    result = inspect_personal_skill_conflicts(repo, apply=apply_changes)
    # `--repo .` acts on the current folder, so name the business repo from another one (#1083).
    repair_command = f"mb skill repair{repo_flag(repo) or ' --repo .'} --apply"
    if "repair_command" in result:
        result["repair_command"] = repair_command
    if json_out:
        typer.echo(json.dumps(result, indent=2))
    else:
        summary = result["summary"]
        typer.echo(f"checked personal Claude Code skills: {result['personal_skills_dir']}")
        if summary["findings"] == 0:
            typer.echo("no personal skill shadows or legacy Main Branch skill traps found.")
        else:
            typer.echo(
                f"found {summary['findings']} issue(s): "
                f"{summary['active_shadows']} active shadow(s), "
                f"{summary['legacy_globals']} legacy command trap(s)."
            )
            for finding in result["findings"]:
                typer.echo("")
                typer.echo(f"- {finding['name']} ({finding['classification']})")
                typer.echo(f"  path: {finding['global_path']}")
                if finding["global_target"]:
                    typer.echo(f"  target: {finding['global_target']}")
                if finding["safe_to_repair"]:
                    if finding["repaired"]:
                        typer.echo(f"  moved to: {finding['backup_path']}")
                    else:
                        typer.echo(f"  safe repair: run `{repair_command}`")
                else:
                    typer.echo(
                        "  not changed: this is not a stale or broken Main Branch skill link"
                    )
        if not apply_changes and summary["repairable"]:
            typer.echo("")
            typer.echo("To move stale or broken Main Branch symlinks to backup:")
            typer.echo(f"  {repair_command}")
    raise typer.Exit(0 if result["ok"] else 1)
