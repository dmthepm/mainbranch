"""Command implementations extracted from :mod:`mb.cli`."""

from __future__ import annotations

from typing import Any

import typer

from mb import codex as codex_mod
from mb import onboard as onboard_mod
from mb.cli_common import (
    _json_error_payload,
    _json_payload,
)
from mb.engine import repo_flag


def _onboard_target_path(path_arg: str, path_opt: str, name: str) -> str:
    explicit = path_opt.strip() or path_arg.strip()
    if explicit:
        return explicit
    return onboard_mod._slug(name) if name.strip() else "."


def _render_onboard_intro(level: str) -> None:
    if level == "power":
        typer.echo("Main Branch keeps the business in local files, git history, and GitHub work.")
        return
    typer.echo("")
    typer.echo("Main Branch works because the business lives somewhere durable:")
    typer.echo("  local files  - readable, portable business memory")
    typer.echo("  git          - the evolution story and rollback layer")
    typer.echo("  GitHub       - tasks, proposals, reviews, and shipped history")
    typer.echo("  Claude Code  - the first execution runtime for judgment-heavy work")


def _render_onboard_human(result: dict[str, Any]) -> None:
    from rich.console import Console

    console = Console()
    mark = "[green]ready[/green]" if result["ok"] else "[red]needs repair[/red]"
    console.print(f"\n[bold]mb onboard[/bold]  {mark}")
    console.print(f"repo: {result['path']}")
    console.print(f"level / action: {result['level']} / {result['action']}\n")
    setup_complete = result.get("setup_complete") or {}
    if setup_complete:
        console.print(f"[bold]Outcome[/bold] {setup_complete.get('owner_outcome')}")
        console.print()

    if result["level"] != "power":
        console.print("[bold]Why this stack[/bold]")
        console.print("  Local files are the business brain.")
        console.print("  Git remembers how the business changed.")
        console.print("  GitHub turns tasks and proposals into a team surface.")
        console.print("  Claude Code is the first runtime that can act on the repo.\n")
    console.print("[bold]Save model[/bold]")
    console.print("  Files save locally first.")
    console.print("  Checkpoints are approved saved points in the business history.")
    console.print(
        "  GitHub backup/sync is strongly recommended for cloud backup, "
        "collaboration, and AI connector access.\n"
    )

    tools = result["tools"]
    skill_wiring = result["skill_wiring"]
    checkpoint_hook = result.get("checkpoint_hook") or {}
    raw_github = result.get("github")
    github_result: dict[str, Any] = raw_github if isinstance(raw_github, dict) else {}
    raw_github_preflight = github_result.get("preflight")
    github_preflight: dict[str, Any] = (
        raw_github_preflight if isinstance(raw_github_preflight, dict) else {}
    )
    git = tools["git"]
    github = tools["github_cli"]
    claude = tools["claude_code"]
    console.print("[bold]Checks[/bold]")
    console.print(f"  {'ok' if git['found'] else 'warn'}  git")
    github_state = "ok" if github["found"] and github["authenticated"] else "warn"
    github_label = "GitHub CLI"
    account = str(github_preflight.get("authenticated_account") or "")
    expected_owner = str(github_preflight.get("expected_owner") or "")
    if account and expected_owner:
        github_label = f"GitHub CLI signed in as {account}; backup target {expected_owner}"
    elif account:
        github_label = f"GitHub CLI signed in as {account}"
    console.print(f"  {github_state}  {github_label}")
    console.print(f"  {'ok' if claude['found'] else 'warn'}  Claude Code")
    console.print(f"  {'ok' if skill_wiring['ok'] else 'fail'}  Claude Code skill discovery")
    if checkpoint_hook:
        console.print(f"  {'ok' if checkpoint_hook.get('ok') else 'warn'}  checkpoint save hook")
    if setup_complete:
        console.print(
            f"  {'ok' if setup_complete.get('committed_with_durable_files') else 'warn'}  "
            "saved baseline"
        )
        if setup_complete.get("github_requested"):
            console.print(
                f"  {'ok' if setup_complete.get('pushed_tracking_remote') else 'warn'}  GitHub sync"
            )

    warnings = result["warnings"]
    errors = result["errors"]
    if warnings:
        console.print("\n[yellow]Repair notes[/yellow]")
        for warning in warnings:
            console.print(f"  - {warning}")
    if errors:
        console.print("\n[red]Could not finish setup[/red]")
        for error in errors:
            console.print(f"  - {error}")
        console.print(f"\nRun `{result['doctor_command']}` for repair steps.")
        return

    console.print("\n[bold]Next[/bold]")
    for step in result["next_steps"]:
        console.print(f"  {step}")
    console.print(
        "\n[bold]Connected accounts[/bold]\n"
        "  See CLAUDE.md -> Connected accounts before wiring tools that spend, "
        "publish, or mutate customer accounts."
    )
    if warnings:
        console.print(f"\nFor a full setup check, run `{result['doctor_command']}`.")
    console.print()


def _render_workflow_inventory_human(result: dict[str, Any]) -> None:
    from rich.console import Console

    console = Console()
    console.print("\n[bold]Main Branch workflow support[/bold]")
    console.print(f"runtime: {result['runtime']}")
    console.print(f"entrypoint: {result['entrypoint']}")
    console.print()
    for item in result["items"]:
        commands = ", ".join(item.get("commands") or [])
        suffix = f"  facts: {commands}" if commands else ""
        console.print(
            f"- {item['label']}  status: {item['codex_status']}\n"
            f"  Codex: {item['codex_surface']}{suffix}"
        )
    console.print()


def workflow_list_cmd(
    runtime: str = typer.Option("codex", "--runtime", help="Runtime inventory to show."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """List supported and pending workflow surfaces for a runtime."""
    normalized_runtime = runtime.strip().lower().replace("-", "_")
    if normalized_runtime not in {"codex", "codex_cli"}:
        message = "mb workflow list: only --runtime codex is available today"
        if json_out:
            typer.echo(
                _json_error_payload(
                    command="mb workflow list",
                    schema_name="mainbranch.workflow.inventory.result",
                    code="unsupported_runtime",
                    message=message,
                )
            )
        else:
            typer.echo(message, err=True)
        raise typer.Exit(2)
    result = codex_mod.workflow_inventory(runtime="codex")
    if json_out:
        typer.echo(
            _json_payload(
                result,
                command="mb workflow list",
                schema_name="mainbranch.workflow.inventory.result",
            )
        )
    else:
        _render_workflow_inventory_human(result)


def onboard_cmd(
    ctx: typer.Context,
    path_opt: str = typer.Option("", "--path", help="Repo path to create or connect."),
    name: str = typer.Option("", "--name", help="Business name."),
    owner_name: str = typer.Option("", "--owner-name", help="Business name for the owner file."),
    owner_github: str = typer.Option(
        "",
        "--owner-github",
        help="GitHub handle for the owner file, without @.",
    ),
    mode: str = typer.Option(
        "auto",
        "--mode",
        help="Setup mode: auto, new, or connect.",
    ),
    level: str = typer.Option(
        "auto",
        "--level",
        help="Experience level: auto, beginner, intermediate, or power.",
    ),
    team_size: str = typer.Option(
        "unknown",
        "--team-size",
        help="Onboarding persona: solo, small-team, larger-team, or unknown.",
    ),
    business_type: str = typer.Option(
        "",
        "--business-type",
        help="Short business category for onboarding progress.",
    ),
    success_stage: str = typer.Option(
        "unknown",
        "--success-stage",
        help="Current success stage: prelaunch, working, successful, scaling, or unknown.",
    ),
    desired_outcome: str = typer.Option(
        "",
        "--desired-outcome",
        help="Short target outcome for onboarding progress.",
    ),
    operating_currency: str = typer.Option(
        "",
        "--operating-currency",
        help="Safe MoneyPath currency code, such as USD.",
    ),
    books_storage_mode: str = typer.Option(
        "",
        "--books-storage-mode",
        help="Books storage mode: solo-local, team-private-repo, advanced-vault.",
    ),
    monthly_experiment_budget_band: str = typer.Option(
        "",
        "--monthly-experiment-budget-band",
        help="Safe budget band: under-500, 500-2k, 2k-10k, over-10k, private.",
    ),
    threshold_privacy: str = typer.Option(
        "",
        "--threshold-privacy",
        help="Threshold posture: declared, private, unknown, or blank.",
    ),
    trivial_max_amount: str = typer.Option(
        "",
        "--trivial-max-amount",
        help="Optional safe max amount for trivial bets.",
    ),
    small_max_amount: str = typer.Option(
        "",
        "--small-max-amount",
        help="Optional safe max amount for small bets.",
    ),
    material_max_amount: str = typer.Option(
        "",
        "--material-max-amount",
        help="Optional safe max amount for material bets.",
    ),
    strategic_min_amount: str = typer.Option(
        "",
        "--strategic-min-amount",
        help="Optional safe min amount for strategic bets.",
    ),
    approval_required_for_material: str = typer.Option(
        "",
        "--approval-required-for-material",
        help="Whether material bets need accepted-decision approval: yes/no.",
    ),
    ledger_anchor_default: str = typer.Option(
        "",
        "--ledger-anchor-default",
        help="Whether non-trivial bets need ledger anchors by default: yes/no.",
    ),
    github_repo: str = typer.Option(
        "",
        "--github",
        help="Create/connect a GitHub repo such as owner/name or name.",
    ),
    github_visibility: str = typer.Option(
        "private",
        "--github-visibility",
        help="GitHub repo visibility when --github is used: private or public.",
    ),
    github_push: bool = typer.Option(
        False,
        "--push",
        help="Push main and set origin tracking after creating the GitHub repo.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Use defaults and never prompt."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Guide a human through first setup or reconnect an existing repo."""
    if ctx.invoked_subcommand is not None:
        return
    interactive = onboard_mod.is_interactive()
    if not yes and not interactive:
        typer.echo(
            "mb onboard needs a terminal prompt. Use `mb onboard --yes` for scripts.", err=True
        )
        raise typer.Exit(2)

    selected_level = level
    selected_mode = mode
    target = _onboard_target_path("", path_opt, name)
    business_name = name
    selected_owner_name = owner_name
    selected_owner_github = owner_github

    if not yes:
        typer.echo("Main Branch setup")
        selected_level = typer.prompt(
            "Comfort level (beginner/intermediate/power)",
            default="beginner" if level == "auto" else level,
        )
        if selected_level != "power":
            _render_onboard_intro(selected_level)
        selected_mode = typer.prompt(
            "Create a new repo, connect an existing one, or auto-detect? (new/connect/auto)",
            default="auto" if mode == "auto" else mode,
        )
        if not business_name and selected_mode != "connect":
            business_name = typer.prompt("Business name")
        default_path = target
        if target == "." and business_name:
            default_path = onboard_mod._slug(business_name)
        target = typer.prompt("Repo path", default=default_path)
        if selected_mode != "connect":
            selected_owner_name = typer.prompt("Owner name", default=owner_name or "Business Owner")
            selected_owner_github = typer.prompt(
                "Owner GitHub handle (without @)",
                default=owner_github or "",
            )

    try:
        result = onboard_mod.run(
            path=target,
            name=business_name,
            owner_name=selected_owner_name,
            owner_github=selected_owner_github,
            mode=selected_mode,
            level=selected_level,
            team_size=team_size,
            business_type=business_type,
            success_stage=success_stage,
            desired_outcome=desired_outcome,
            operating_currency=operating_currency,
            books_storage_mode=books_storage_mode,
            monthly_experiment_budget_band=monthly_experiment_budget_band,
            threshold_privacy=threshold_privacy,
            trivial_max_amount=trivial_max_amount,
            small_max_amount=small_max_amount,
            material_max_amount=material_max_amount,
            strategic_min_amount=strategic_min_amount,
            approval_required_for_material=approval_required_for_material,
            ledger_anchor_default=ledger_anchor_default,
            github_repo=github_repo,
            github_visibility=github_visibility,
            github_push=github_push,
        )
    except ValueError as exc:
        typer.echo(f"mb onboard: {exc}", err=True)
        raise typer.Exit(2) from exc
    if json_out:
        typer.echo(
            _json_payload(result, command="mb onboard", schema_name="mainbranch.onboard.result")
        )
    else:
        _render_onboard_human(result)
    raise typer.Exit(0 if result["ok"] else 1)


def _render_onboard_status_human(result: dict[str, Any]) -> None:
    from rich.console import Console
    from rich.markup import escape

    console = Console()
    summary = result["summary"]
    console.print(f"\n[bold]mb onboard status[/bold]  {result['repo']}")
    console.print(
        f"{summary['status'].replace('_', ' ')}  "
        f"{summary['completed_required']}/{summary['total_required']} required steps complete"
    )
    if not result["state_exists"]:
        console.print(
            "[yellow]No saved onboarding plan yet.[/yellow] "
            f"Run `mb onboard plan{escape(repo_flag(result['repo']))}`."
        )
    profile = result["profile"]
    console.print(
        "\n[bold]Profile[/bold] "
        f"team: {profile.get('team_size', 'unknown')}  "
        f"type: {profile.get('business_type') or 'unknown'}  "
        f"stage: {profile.get('success_stage', 'unknown')}"
    )
    console.print("\n[bold]Checklist[/bold]")
    for step in result["checklist"]:
        mark = "ok" if step["status"] == "complete" else "todo"
        missing = ", ".join(step["missing_inputs"])
        suffix = f" ({missing})" if missing else ""
        console.print(f"  {mark:<4} {step['title']}{suffix}")
    console.print("\n[bold]Next[/bold]")
    console.print(f"  {summary['next_recommended_action']}")
    console.print()


def onboard_status_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo to inspect."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Show saved onboarding progress and inferred missing core inputs."""
    result = onboard_mod.onboarding_status(repo)
    if json_out:
        typer.echo(
            _json_payload(
                result,
                command="mb onboard status",
                schema_name="mainbranch.onboard.status.result",
            )
        )
    else:
        _render_onboard_status_human(result)
    raise typer.Exit(0 if result["ok"] else 1)


def onboard_plan_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo whose plan is updated."),
    name: str = typer.Option("", "--name", help="Business name."),
    team_size: str = typer.Option(
        "unknown",
        "--team-size",
        help="Onboarding persona: solo, small-team, larger-team, or unknown.",
    ),
    business_type: str = typer.Option("", "--business-type", help="Short business category."),
    success_stage: str = typer.Option(
        "unknown",
        "--success-stage",
        help="Current success stage: prelaunch, working, successful, scaling, or unknown.",
    ),
    desired_outcome: str = typer.Option("", "--desired-outcome", help="Short target outcome."),
    operating_currency: str = typer.Option(
        "",
        "--operating-currency",
        help="Safe MoneyPath currency code, such as USD.",
    ),
    books_storage_mode: str = typer.Option(
        "",
        "--books-storage-mode",
        help="Books storage mode: solo-local, team-private-repo, advanced-vault.",
    ),
    monthly_experiment_budget_band: str = typer.Option(
        "",
        "--monthly-experiment-budget-band",
        help="Safe budget band: under-500, 500-2k, 2k-10k, over-10k, private.",
    ),
    threshold_privacy: str = typer.Option(
        "",
        "--threshold-privacy",
        help="Threshold posture: declared, private, unknown, or blank.",
    ),
    trivial_max_amount: str = typer.Option("", "--trivial-max-amount"),
    small_max_amount: str = typer.Option("", "--small-max-amount"),
    material_max_amount: str = typer.Option("", "--material-max-amount"),
    strategic_min_amount: str = typer.Option("", "--strategic-min-amount"),
    approval_required_for_material: str = typer.Option(
        "",
        "--approval-required-for-material",
        help="Whether material bets need accepted-decision approval: yes/no.",
    ),
    ledger_anchor_default: str = typer.Option(
        "",
        "--ledger-anchor-default",
        help="Whether non-trivial bets need ledger anchors by default: yes/no.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Create or update the lightweight onboarding progress plan."""
    try:
        result = onboard_mod.write_plan(
            repo,
            business_name=name,
            team_size=team_size,
            business_type=business_type,
            success_stage=success_stage,
            desired_outcome=desired_outcome,
            operating_currency=operating_currency,
            books_storage_mode=books_storage_mode,
            monthly_experiment_budget_band=monthly_experiment_budget_band,
            threshold_privacy=threshold_privacy,
            trivial_max_amount=trivial_max_amount,
            small_max_amount=small_max_amount,
            material_max_amount=material_max_amount,
            strategic_min_amount=strategic_min_amount,
            approval_required_for_material=approval_required_for_material,
            ledger_anchor_default=ledger_anchor_default,
        )
    except ValueError as exc:
        typer.echo(f"mb onboard plan: {exc}", err=True)
        raise typer.Exit(2) from exc
    if json_out:
        typer.echo(
            _json_payload(
                result,
                command="mb onboard plan",
                schema_name="mainbranch.onboard.plan.result",
            )
        )
    else:
        _render_onboard_status_human(result)
    raise typer.Exit(0 if result["ok"] else 1)
