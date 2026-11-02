"""Command implementations extracted from :mod:`mb.cli`."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import typer

from mb import checkpoint as checkpoint_mod
from mb import doctor as doctor_mod
from mb import educational as educational_mod
from mb import graph as graph_mod
from mb import migrate as migrate_mod
from mb import resolve as resolve_mod
from mb import similar_bets as similar_bets_mod
from mb import suggest as suggest_mod
from mb import think as think_mod
from mb import update as update_mod
from mb import validate as validate_mod
from mb.cli_common import (
    VALIDATE_PATHS_OPTION,
    _json_payload,
)
from mb.engine import repo_flag


def validate_cmd(
    path: str = typer.Argument(".", help="Repo to validate."),
    repo: str | None = typer.Option(
        None,
        "--repo",
        help="Repo to validate. Alias for the positional PATH used by older scripts.",
    ),
    verbose: bool = typer.Option(
        False,
        "-v",
        "--verbose",
        help="Show full per-file detail; by default warnings-only files collapse into the summary.",
    ),
    cross_refs: bool = typer.Option(
        False,
        "--cross-refs",
        help="Check known frontmatter links and offer directory references.",
    ),
    strict: bool = typer.Option(False, "--strict", help="Fail on warnings."),
    paths: list[str] = VALIDATE_PATHS_OPTION,
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Check frontmatter shape and optional cross-references."""
    target = repo or path
    try:
        report = validate_mod.run(
            path=target,
            verbose=verbose,
            cross_refs=cross_refs,
            strict=strict,
            paths=list(paths),
        )
    except ValueError as exc:
        typer.echo(f"mb validate: {exc}", err=True)
        raise typer.Exit(2) from exc
    except Exception as exc:  # noqa: BLE001 - --json must stay parseable on any failure.
        # Agents consume this output programmatically; an unhandled traceback
        # on stdout makes the enforcement plane untrustworthy (operators
        # route around it). Emit a valid error envelope instead.
        if json_out:
            typer.echo(
                json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "type": exc.__class__.__name__,
                            "message": str(exc),
                        },
                        "repo": target,
                        "files": [],
                        "summary": {"errors": 1, "warnings": 0},
                    },
                    indent=2,
                )
            )
        else:
            typer.echo(
                f"mb validate: internal error ({exc.__class__.__name__}: {exc}). "
                "Please report this with the repo shape that triggered it.",
                err=True,
            )
        raise typer.Exit(2) from exc
    if repo_flag(target):
        # Only from another folder; the copy leaves the report `run` built alone.
        report = doctor_mod._qualify_validation_report(report, Path(target).expanduser())
    if json_out:
        typer.echo(json.dumps(report, indent=2))
    else:
        validate_mod.render_human(report, verbose=verbose, repo=Path(target))
    raise typer.Exit(0 if report["ok"] else 1)


def graph_cmd(
    path: str = typer.Argument(".", help="Repo to graph."),
    open_after: bool = typer.Option(False, "--open", help="Render to PNG and open."),
    json_out: bool = typer.Option(False, "--json", help="Emit the machine-readable graph index."),
) -> None:
    """Build the repo graph index; emit DOT by default or JSON with --json."""
    if json_out and open_after:
        raise typer.BadParameter("--open cannot be combined with --json")
    index = graph_mod.build_index(path=path)
    if json_out:
        typer.echo(json.dumps(index, indent=2))
        return
    dot = graph_mod.index_to_dot(index)
    if open_after:
        graph_mod.open_dot(dot)
    else:
        typer.echo(dot)


def suggest_links_cmd(
    file: str = typer.Argument(..., help="Markdown file to inspect."),
    repo: str = typer.Option(".", "--repo", help="Business repo to query."),
    limit: int = typer.Option(10, "--limit", min=0, help="Maximum suggestions to return."),
    include_ignored: bool = typer.Option(
        False,
        "--include-ignored",
        help="Include candidates classified as ignore.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Suggest likely business connections without editing files."""
    try:
        report = suggest_mod.suggest_links(
            source_file=file,
            repo=repo,
            limit=limit,
            include_ignored=include_ignored,
        )
    except ValueError as exc:
        typer.echo(f"mb suggest links: {exc}", err=True)
        raise typer.Exit(2) from exc
    if json_out:
        typer.echo(json.dumps(report, indent=2))
    else:
        suggest_mod.render_human(report)
    raise typer.Exit(0 if report["ok"] else 1)


def similar_bets_cmd(
    thesis: str = typer.Argument(..., help="Current bet thesis to compare against repo memory."),
    path: str = typer.Option(".", "--repo", help="Business repo to query."),
    limit: int = typer.Option(5, "--limit", min=1, help="Maximum matches to return."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Find similar past bets and offer outcomes from repo truth."""
    report = similar_bets_mod.run(path=path, thesis=thesis, limit=limit)
    if json_out:
        typer.echo(json.dumps(report, indent=2))
    else:
        similar_bets_mod.render_human(report)


def think_cmd(
    topic: str = typer.Argument(..., help="Topic to think about."),
) -> None:
    """Print the /mb-think invocation hint (run inside Claude Code for full flow)."""
    think_mod.run(topic=topic)


def resolve_cmd(
    key: str = typer.Argument(..., help="Reference key (e.g. 'voice')."),
    repo: str = typer.Option(".", "--repo"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Resolve a reference path (checks free first, then paid)."""
    result = resolve_mod.run(key=key, repo=repo)
    if json_out:
        typer.echo(json.dumps(result, indent=2))
    else:
        if result["resolved"]:
            typer.echo(result["path"])
            if result.get("is_stub"):
                typer.echo(
                    f"# stub — for the curated {key}, subscribe at mainbranch.io/run",
                    err=True,
                )
        else:
            typer.echo(f"unresolved: {key}", err=True)
            raise typer.Exit(1)


def educational_cmd(
    topic: str = typer.Argument(..., help="Educational topic slug."),
) -> None:
    """Print a beginner education topic for Main Branch rails and defaults."""
    educational_mod.run(topic=topic)


def update_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo whose skill links refresh."),
    check: bool = typer.Option(False, "--check", help="Dry-run only; do not upgrade or relink."),
    refresh_surfaces: bool = typer.Option(
        True,
        "--refresh-surfaces/--no-refresh-surfaces",
        help="Refresh Claude links/guidance, Codex global skills, and AGENTS.md after update.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Refresh Main Branch according to its install mode.

    Upgraded automatically: pipx installs and git clones. A uv tool install is
    upgraded only after you answer yes to an interactive prompt. Any other wheel
    install (for example `pip install mainbranch`) prints the upgrade command to
    run yourself. `--check` and `--json` never run an installer.
    """
    result = update_mod.run(
        repo=repo,
        check=check,
        refresh_surfaces=refresh_surfaces,
        interactive=False if json_out else None,
    )
    if json_out:
        typer.echo(json.dumps(result, indent=2))
    else:
        update_mod.render_human(result)
    raise typer.Exit(0 if result["ok"] else 1)


def checkpoint_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo to inspect."),
    plan: bool = typer.Option(
        False,
        "--plan",
        help="Preview checkpointable changes without committing.",
    ),
    status_check: bool = typer.Option(
        False,
        "--status",
        help="Show recent checkpoint commits plus pending checkpoint state.",
    ),
    message: str = typer.Option("", "--message", "-m", help="Commit message for --yes."),
    validate: str = typer.Option(
        "",
        "--validate",
        help="Validate a checkpoint message. Pass '-' to read the message from stdin.",
    ),
    hook_status: bool = typer.Option(
        False,
        "--hook-status",
        help="Inspect the repo-local checkpoint commit-message hook.",
    ),
    install_hook: bool = typer.Option(
        False,
        "--install-hook",
        help="Install or repair the repo-local checkpoint commit-message hook.",
    ),
    uninstall_hook: bool = typer.Option(
        False,
        "--uninstall-hook",
        help="Remove the Main Branch checkpoint commit-message hook.",
    ),
    yes: bool = typer.Option(False, "--yes", help="Save the checkpoint after safety gates pass."),
    include_review_required: bool = typer.Option(
        False,
        "--include-review-required",
        help="Intentionally include files that checkpoint planning marked for review.",
    ),
    mode: str = typer.Option(
        "beginner",
        "--mode",
        help="Checkpoint grouping mode: beginner or concern.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Plan or save a git checkpoint."""
    hook_operations = sum(1 for item in (hook_status, install_hook, uninstall_hook) if item)
    if hook_operations > 1:
        typer.echo("mb checkpoint: choose only one hook operation", err=True)
        raise typer.Exit(2)
    if validate and hook_operations:
        typer.echo("mb checkpoint: --validate cannot be combined with hook operations", err=True)
        raise typer.Exit(2)
    if install_hook:
        result = checkpoint_mod.install_commit_hook(repo=repo)
    elif uninstall_hook:
        result = checkpoint_mod.uninstall_commit_hook(repo=repo)
    elif hook_status:
        result = checkpoint_mod.hook_status(repo=repo)
        # The report is shared with doctor and onboarding, which name the repo themselves.
        if isinstance(result.get("repair_command"), str):
            result["repair_command"] = doctor_mod._qualify_field(
                result["repair_command"], Path(repo).expanduser()
            )
            if result["repair_command"] == "git init" and repo_flag(repo):
                # Not a git repo yet: `git -C` needs the folder to exist, `git init <dir>` makes it.
                result["repair_command"] = f"git init {shlex.quote(str(result['repo']))}"
    elif validate:
        validation_message = sys.stdin.read() if validate == "-" else validate
        result = checkpoint_mod.validate_message(validation_message)
    elif yes or message or include_review_required:
        result = checkpoint_mod.commit(
            repo=repo,
            message=message,
            mode=mode,
            yes=yes,
            include_review_required=include_review_required,
        )
    elif status_check:
        result = checkpoint_mod.status(repo=repo, mode=mode)
    else:
        _ = plan
        result = checkpoint_mod.plan(repo=repo, mode=mode)
    if json_out:
        typer.echo(
            _json_payload(
                result,
                command="mb checkpoint",
                schema_name="mainbranch.checkpoint.result",
            )
        )
    else:
        checkpoint_mod.render_human(result)
    raise typer.Exit(0 if result["ok"] else 1)


def migrate_cmd(
    ctx: typer.Context,
    repo: str = typer.Option(".", "--repo", help="Business repo to migrate."),
    check: bool = typer.Option(False, "--check", help="Dry-run pending migrations."),
    apply_changes: bool = typer.Option(False, "--apply", help="Apply pending migrations."),
    diff: bool = typer.Option(
        False,
        "--diff",
        help="With --check, include the full unified diff. May print private repo content.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Run `mb migrate --check` or `mb migrate --apply`; defaults to status."""
    ctx.obj = {"repo": repo}
    if ctx.invoked_subcommand is not None:
        if diff:
            typer.echo("mb migrate: --diff can only be used with --check", err=True)
            raise typer.Exit(2)
        return
    if check and apply_changes:
        typer.echo("mb migrate: choose only one of --check or --apply", err=True)
        raise typer.Exit(2)
    if diff and not check:
        typer.echo("mb migrate: --diff can only be used with --check", err=True)
        raise typer.Exit(2)
    if apply_changes:
        result = migrate_mod.apply(repo)
        result["next"] = migrate_mod.name_repo(result["next"], repo)
        if json_out:
            typer.echo(json.dumps(result, indent=2))
        else:
            migrate_mod.render_apply(result)
        raise typer.Exit(0 if result["ok"] else 1)
    if check:
        result = migrate_mod.check(repo, include_diff=diff)
        result["next"] = migrate_mod.name_repo(result["next"], repo)
        if json_out:
            typer.echo(json.dumps(result, indent=2))
        else:
            migrate_mod.render_check(result)
        pending = bool(result.get("pending"))
        raise typer.Exit(1 if pending or not result["ok"] else 0)

    result = migrate_mod.status(repo)
    result["next"] = migrate_mod.name_repo(result["next"], repo)
    if json_out:
        typer.echo(json.dumps(result, indent=2))
    else:
        migrate_mod.render_status(result)


def migrate_campaigns_cmd(
    ctx: typer.Context,
    plan: bool = typer.Option(
        False,
        "--plan",
        help=(
            "Print a read-only plan classifying campaigns/ records as moves, "
            "ambiguous, or blockers."
        ),
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Preview the legacy ``campaigns/`` -> canonical ``pushes/`` migration.

    Plan-only in this release. The apply path lands in a follow-up PR with
    backups and explicit operator approval; running without ``--plan`` exits
    with the same plan output and a notice that apply is not yet implemented.
    """
    repo_value = ctx.obj.get("repo", ".") if ctx.obj else "."
    if not plan:
        typer.echo(
            "mb migrate campaigns: --plan is required (apply is not yet implemented)",
            err=True,
        )
        raise typer.Exit(2)
    result = migrate_mod.plan_campaigns_to_pushes(repo_value)
    if json_out:
        typer.echo(json.dumps(result, indent=2))
    else:
        migrate_mod.render_campaigns_plan(result)
    summary = result["summary"]
    has_blockers = summary.get("blockers", 0) > 0
    has_anything = sum(summary.values()) > 0
    raise typer.Exit(1 if has_blockers else (0 if has_anything else 0))


def migrate_status_cmd(
    ctx: typer.Context,
    repo: str | None = typer.Option(None, "--repo", help="Business repo to inspect."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Show current schema version and pending migrations."""
    root_repo = (ctx.obj or {}).get("repo", ".") if isinstance(ctx.obj, dict) else "."
    result = migrate_mod.status(repo or root_repo)
    result["next"] = migrate_mod.name_repo(result["next"], repo or root_repo)
    if json_out:
        typer.echo(json.dumps(result, indent=2))
    else:
        migrate_mod.render_status(result)
