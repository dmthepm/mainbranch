"""Typer CLI for ``mb``.

Thin dispatcher. Each subcommand lives in its own module so we can
unit-test in isolation. The shape echoes ``companyctx`` (Typer + sub-apps)
because that's the working pattern.
"""

from __future__ import annotations

import functools
import json
import math
import os
import shlex
import sys
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, TypeVar, cast

import typer
from typer.core import TyperGroup

from mb import __version__
from mb import ads as ads_mod
from mb import automation as automation_mod
from mb import books as books_mod
from mb import canary as canary_mod
from mb import checkpoint as checkpoint_mod
from mb import codex as codex_mod
from mb import connect as connect_mod
from mb import dashboard as dashboard_mod
from mb import doctor as doctor_mod
from mb import educational as educational_mod
from mb import feedback as feedback_mod
from mb import fleet as fleet_mod
from mb import fleet_checkin as fleet_checkin_mod
from mb import graph as graph_mod
from mb import image_rail as image_rail_mod
from mb import init as init_mod
from mb import issue as issue_mod
from mb import launch as launch_mod
from mb import leads as leads_mod
from mb import ledger as ledger_mod
from mb import migrate as migrate_mod
from mb import onboard as onboard_mod
from mb import production as production_mod
from mb import pulse as pulse_mod
from mb import resolve as resolve_mod
from mb import similar_bets as similar_bets_mod
from mb import site as site_mod
from mb import skill_validate as skill_validate_mod
from mb import spine as spine_mod
from mb import start as start_mod
from mb import status as status_mod
from mb import suggest as suggest_mod
from mb import think as think_mod
from mb import unreadable as unreadable_mod
from mb import update as update_mod
from mb import usage as usage_mod
from mb import validate as validate_mod
from mb.engine import repo_flag
from mb.freshness import format_update_alert, looks_like_business_repo, package_update_status
from mb.json_result import envelope, json_default

# Click's own usage error, from whichever Click this Typer ships with.
_CLICK_USAGE_ERROR = cast(
    "type[Exception]",
    next(cls for cls in typer.BadParameter.__mro__ if cls.__name__ == "UsageError"),
)


def _hide_credential_input(exc: Exception, argv: list[str]) -> None:
    """Replace credential-shaped command-line input in a Click usage error.

    Click repeats what it could not parse ("No such option: --<text>", an
    unexpected extra argument, an invalid value). Input that could be a
    credential is replaced with the same marker `mb connect` failures use; an
    ordinary typo such as ``--jsno`` still shows so it can be fixed.
    """
    message = getattr(exc, "message", None)
    if not isinstance(message, str):
        return
    hidden: set[str] = set()
    for token in argv:
        for piece in {token, *token.split("=", 1)}:
            core = piece.strip().lstrip("-")
            if len(core) >= 8 and not connect_mod.echoable_input(core):
                hidden.update({piece, core})
    for text in sorted(hidden, key=len, reverse=True):
        message = message.replace(text, connect_mod.HIDDEN_INPUT)
    exc.message = message  # type: ignore[attr-defined]


class _UsageErrorRedactingGroup(TyperGroup):
    """The `mb` root group: Click usage errors never repeat credential-shaped input.

    Every subcommand is parsed inside the root's ``invoke``, so catching here
    covers `mb`, `mb connect` and their subcommands. Exit code 2 and the
    usage line are Click's own.
    """

    def make_context(self, info_name: Any, args: list[str], *rest: Any, **extra: Any) -> Any:
        argv = list(args)
        try:
            ctx = super().make_context(info_name, args, *rest, **extra)
        except _CLICK_USAGE_ERROR as exc:
            _hide_credential_input(exc, argv)
            raise
        ctx.meta["mb.argv"] = argv
        return ctx

    def invoke(self, ctx: Any) -> Any:
        try:
            return super().invoke(ctx)
        except _CLICK_USAGE_ERROR as exc:
            _hide_credential_input(exc, list(ctx.meta.get("mb.argv") or []))
            raise


app = typer.Typer(
    name="mb",
    cls=_UsageErrorRedactingGroup,
    help=(
        "Run your business as files in git. Main Branch scaffolds your repo, "
        "checks it, graphs it, and wires it into Claude Code."
    ),
    no_args_is_help=False,
    invoke_without_command=True,
    add_completion=False,
    # Some supported Typer versions print every frame's local variables in a
    # crash traceback, which for `mb connect` includes stored credentials.
    pretty_exceptions_show_locals=False,
)

skill_app = typer.Typer(
    name="skill",
    help="Look at the bundled skills.",
    no_args_is_help=True,
)
app.add_typer(skill_app, name="skill")

migrate_app = typer.Typer(
    name="migrate",
    help="Inspect and apply repo schema migrations.",
    no_args_is_help=False,
    invoke_without_command=True,
)
app.add_typer(migrate_app, name="migrate")

onboard_app = typer.Typer(
    name="onboard",
    help="Create, connect, and resume business repo onboarding.",
    no_args_is_help=False,
    invoke_without_command=True,
)
app.add_typer(onboard_app, name="onboard")

issue_app = typer.Typer(
    name="issue",
    help="Draft and open privacy-safe GitHub issues.",
    no_args_is_help=True,
)
app.add_typer(issue_app, name="issue")

site_app = typer.Typer(
    name="site",
    help="Inspect site readiness for launch-adjacent workflows.",
    no_args_is_help=True,
)
app.add_typer(site_app, name="site")

fleet_app = typer.Typer(
    name="fleet",
    help="Read-only status of every site across your hubs.",
    no_args_is_help=True,
)
app.add_typer(fleet_app, name="fleet")
fleet_hubs_app = typer.Typer(
    name="hubs",
    help="Show the hub list mb fleet reads.",
    no_args_is_help=True,
)
fleet_app.add_typer(fleet_hubs_app, name="hubs")

launch_app = typer.Typer(
    name="launch",
    help="Summarize read-only launch readiness facts.",
    no_args_is_help=True,
)
app.add_typer(launch_app, name="launch")

books_app = typer.Typer(
    name="books",
    help="Check bookkeeping safety and the private books vault contract.",
    no_args_is_help=True,
)
app.add_typer(books_app, name="books")

books_report_app = typer.Typer(
    name="report",
    help="Generate privacy-bounded bookkeeping reports.",
    no_args_is_help=True,
)
books_app.add_typer(books_report_app, name="report")

google_app = typer.Typer(
    name="google",
    help="Read Search Console and GA4 with this repo's Google sign-in (read-only).",
    no_args_is_help=True,
)
app.add_typer(google_app, name="google")

google_sc_app = typer.Typer(
    name="sc",
    help="Read the recorded Search Console site (read-only).",
    no_args_is_help=True,
)
google_app.add_typer(google_sc_app, name="sc")

google_sc_sitemaps_app = typer.Typer(
    name="sitemaps",
    help="Read the recorded site's submitted sitemaps (read-only).",
    no_args_is_help=True,
)
google_sc_app.add_typer(google_sc_sitemaps_app, name="sitemaps")

google_ga4_app = typer.Typer(
    name="ga4",
    help="Read the recorded GA4 property (read-only).",
    no_args_is_help=True,
)
google_app.add_typer(google_ga4_app, name="ga4")

ads_app = typer.Typer(
    name="ads",
    help="Read paid-channel account summaries.",
    no_args_is_help=True,
)
app.add_typer(ads_app, name="ads")

ads_meta_app = typer.Typer(
    name="meta",
    help="Read privacy-bounded Meta Ads account summaries.",
    no_args_is_help=True,
)
ads_app.add_typer(ads_meta_app, name="meta")

image_app = typer.Typer(
    name="image",
    help="Smoke fixture-safe creative image rails.",
    no_args_is_help=True,
)
app.add_typer(image_app, name="image")

dashboard_app = typer.Typer(
    name="dashboard",
    help="Build or open the local read-only business dashboard.",
    no_args_is_help=True,
)
app.add_typer(dashboard_app, name="dashboard")

canary_app = typer.Typer(
    name="canary",
    help="Golden-path canary scaffold for the business money path.",
    no_args_is_help=True,
)
app.add_typer(canary_app, name="canary")

spine_app = typer.Typer(
    name="spine",
    help="Declare and inspect the business's contact+event spine position.",
    no_args_is_help=True,
)
app.add_typer(spine_app, name="spine")

SPINE_LENS_OPTION = typer.Option(
    [],
    "--lens",
    help="Fan-out lens as <store> or <store>:<domain> (repeatable).",
)
SPINE_GAP_OPTION = typer.Option(
    [],
    "--gap",
    help="Known event/timeline gap the spine does not hold (repeatable).",
)


@spine_app.command("declare")
def spine_declare_cmd(
    store: str = typer.Option(
        ...,
        "--store",
        help="System of record for people (a provider id), or `none`.",
    ),
    repo: str = typer.Option(".", "--repo", help="Business repo to declare in."),
    intentional: bool = typer.Option(
        False,
        "--intentional",
        help="With --store none: declare the no-spine position as deliberate.",
    ),
    lenses: list[str] = SPINE_LENS_OPTION,
    gaps: list[str] = SPINE_GAP_OPTION,
    revisit: str = typer.Option(
        "", "--revisit", help="The trigger that should reopen this declaration."
    ),
    force: bool = typer.Option(False, "--force", help="Replace an existing declaration."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Record which system plays the contact+event spine role (a repo fact)."""
    try:
        result = spine_mod.declare(
            repo,
            store=store,
            intentional_none=intentional,
            lenses=list(lenses),
            gaps=list(gaps),
            revisit=revisit,
            force=force,
        )
    except ValueError as exc:
        typer.echo(f"mb spine declare: {exc}", err=True)
        raise typer.Exit(2) from exc
    if json_out:
        typer.echo(
            _json_payload(result, command="mb spine declare", schema_name="mainbranch.spine.v1")
        )
    else:
        typer.echo(result["summary"])
        typer.echo(f"fact: {result['path']}")
    raise typer.Exit(0 if result["ok"] else 1)


@spine_app.command("init")
def spine_init_cmd(
    owned: bool = typer.Option(
        False,
        "--owned",
        help="Scaffold the owned contact+event schema (the triggered build path).",
    ),
    repo: str = typer.Option(".", "--repo", help="Business repo to scaffold."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing spine files."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Scaffold the owned spine (schema + instructions). Requires --owned."""
    if not owned:
        typer.echo(
            "mb spine init: pass --owned to scaffold the owned contact+event "
            "schema. Building an owned spine is the TRIGGERED path — declare "
            "your current position first (`mb spine declare`) and see "
            "decisions/2026-06-12-spine-levels.md for when a trigger fires.",
            err=True,
        )
        raise typer.Exit(2)
    result = spine_mod.init_owned(repo, force=force)
    if json_out:
        typer.echo(
            _json_payload(result, command="mb spine init", schema_name="mainbranch.spine.v1")
        )
    else:
        typer.echo(result["summary"])
        for path in result["written"]:
            typer.echo(f"  wrote {path}")
        for path in result["skipped"]:
            typer.echo(f"  kept  {path}")
    raise typer.Exit(0 if result["ok"] else 1)


@spine_app.command("show")
def spine_show_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo to inspect."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Read the declared spine position back as facts."""
    result = spine_mod.show(repo)
    if json_out:
        typer.echo(
            _json_payload(result, command="mb spine show", schema_name="mainbranch.spine.v1")
        )
    else:
        typer.echo(result["summary"])
        if result.get("declared"):
            declaration = result["declaration"]
            for lens in declaration.get("lenses", []):
                domain = f" ({lens['domain']})" if lens.get("domain") else ""
                typer.echo(f"  lens: {lens['store']}{domain}")
            for gap in declaration.get("known_gaps", []):
                typer.echo(f"  gap:  {gap}")
            if declaration.get("revisit_trigger"):
                typer.echo(f"  revisit when: {declaration['revisit_trigger']}")
    raise typer.Exit(0 if result["ok"] else 1)


@canary_app.command("init")
def canary_init_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo to scaffold."),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing canary files (loses your checks)."
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Scaffold canary/smoke.mjs + canary/README.md (harness + alert doctrine)."""
    result = canary_mod.init(repo, force=force)
    if json_out:
        typer.echo(
            _json_payload(result, command="mb canary init", schema_name="mainbranch.canary.v1")
        )
    else:
        typer.echo(result["summary"])
        for path in result["written"]:
            typer.echo(f"  wrote {path}")
        for path in result["skipped"]:
            typer.echo(f"  kept  {path}")
    raise typer.Exit(0 if result["ok"] else 1)


pulse_app = typer.Typer(
    name="pulse",
    help="Daily business pulse: deterministic collectors + a judgment skill.",
    no_args_is_help=True,
)
app.add_typer(pulse_app, name="pulse")


@pulse_app.command("init")
def pulse_init_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo to scaffold."),
    slug: str = typer.Option(
        "", "--slug", help="Short business slug for pulse log filenames (defaults to repo name)."
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing pulse scaffold files."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Scaffold pulse collectors + the repo-local /mb-pulse judgment skill."""
    result = pulse_mod.init(repo, slug=slug, force=force)
    if json_out:
        typer.echo(
            _json_payload(result, command="mb pulse init", schema_name="mainbranch.pulse.v1")
        )
    else:
        typer.echo(result["summary"])
        for path in result["written"]:
            typer.echo(f"  wrote {path}")
        for path in result["skipped"]:
            typer.echo(f"  kept  {path}")
    raise typer.Exit(0 if result["ok"] else 1)


@pulse_app.command("install")
def pulse_install_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo to scaffold."),
    at: str = typer.Option("08:00", "--at", help="Daily run time, HH:MM (24-hour, local)."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing run-pulse.sh."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Emit an operator-owned daily pulse wrapper + the cron line to activate it."""
    result = pulse_mod.install(repo, at=at, force=force)
    if json_out:
        typer.echo(
            _json_payload(result, command="mb pulse install", schema_name="mainbranch.pulse.v1")
        )
    else:
        typer.echo(result["summary"])
        for path in result.get("written", []):
            typer.echo(f"  wrote {path}")
        for path in result.get("skipped", []):
            typer.echo(f"  kept  {path}")
        for line in result.get("activation", []):
            typer.echo(f"  {line}")
    raise typer.Exit(0 if result["ok"] else 1)


automation_app = typer.Typer(
    name="automation",
    help="Scaffold the steered-loop contract (inspectable loop/cron state).",
    no_args_is_help=True,
)
app.add_typer(automation_app, name="automation")


@automation_app.command("init")
def automation_init_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo to scaffold."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing loop-state."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Scaffold core/operations/loop-state.md (the steered-loop contract)."""
    result = automation_mod.init(repo, force=force)
    if json_out:
        typer.echo(
            _json_payload(
                result, command="mb automation init", schema_name="mainbranch.automation.v1"
            )
        )
    else:
        automation_mod.render_init(result)
    raise typer.Exit(0 if result["ok"] else 1)


ledger_app = typer.Typer(
    name="ledger",
    help="Scaffold the what's-working creative ledger (KEEP/KILL on eligible CPL).",
    no_args_is_help=True,
)
app.add_typer(ledger_app, name="ledger")


@ledger_app.command("init")
def ledger_init_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo to scaffold."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing ledger."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Scaffold core/operations/creative-ledger.md (the v1 markdown table)."""
    result = ledger_mod.init(repo, force=force)
    if json_out:
        typer.echo(
            _json_payload(result, command="mb ledger init", schema_name="mainbranch.ledger.v1")
        )
    else:
        ledger_mod.render_init(result)
    raise typer.Exit(0 if result["ok"] else 1)


FEEDBACK_WORDS_ARGUMENT = typer.Argument(
    None,
    help=(
        "What went wrong, in plain words. Or `rollup` / `list` / `clear` to read or "
        "prune the local feedback file."
    ),
)


@app.command("feedback")
def feedback_cmd(
    words: list[str] = FEEDBACK_WORDS_ARGUMENT,
    about: str = typer.Option(
        "",
        "--command",
        help="The mb command the feedback is about, for example 'mb connect test'.",
    ),
    since: str = typer.Option(
        "",
        "--since",
        help="Window for rollup and list: 7d, 12h, 2w or a date. Rollup defaults to 7d.",
    ),
    before: str = typer.Option(
        "", "--before", help="With `clear`, remove entries older than this date."
    ),
    kind: str = typer.Option("", "--kind", help="With `list`, show only feedback or refusal."),
    limit: int = typer.Option(
        50, "--limit", help="With `list`, newest entries to show; 0 for all."
    ),
    repo: str = typer.Option(".", "--repo", help="Repo the feedback was written from."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Log mb friction to a local file and roll it up for the maintainer. Nothing is sent."""
    args = list(words or [])
    target = args[0] if args and args[0] in feedback_mod.SUBCOMMANDS else ""
    command = f"mb feedback {target}".strip()
    schema_name = "mainbranch.feedback.v1"

    def usage_error(code: str, message: str) -> NoReturn:
        if json_out:
            typer.echo(
                _json_error_payload(
                    command=command, schema_name=schema_name, code=code, message=message
                )
            )
        else:
            typer.echo(f"{command}: {message}", err=True)
        raise typer.Exit(2)

    if target and len(args) > 1:
        usage_error("unexpected_argument", f"unexpected argument {args[1]!r}")
    try:
        if target == "rollup":
            result = feedback_mod.rollup(since=since or feedback_mod.DEFAULT_SINCE)
        elif target == "list":
            if kind and kind not in feedback_mod.KINDS:
                usage_error("invalid_kind", "--kind must be feedback or refusal")
            result = feedback_mod.list_entries(since=since or None, kind=kind or None, limit=limit)
        elif target == "clear":
            if not before:
                usage_error("missing_before", "--before <date> is required, for example 2026-10-01")
            result = feedback_mod.clear(before=before)
        else:
            if not args:
                usage_error(
                    "empty_feedback",
                    'say what went wrong, for example: mb feedback "status said X, expected Y"',
                )
            result = feedback_mod.record(" ".join(args), command=about or None, repo=repo)
    except ValueError as exc:
        code = "invalid_date" if target == "clear" else "invalid_since"
        usage_error(code, feedback_mod.scrub(str(exc)))
    if json_out:
        typer.echo(_json_payload(result, command=command, schema_name=schema_name))
    elif not result["ok"]:
        for error in result.get("errors", []):
            typer.echo(f"{command}: {error['message']}", err=True)
    elif target == "rollup":
        typer.echo(result["markdown"], nl=False)
    elif target == "list":
        feedback_mod.render_list(result)
    elif target == "clear":
        feedback_mod.render_clear(result)
    else:
        feedback_mod.render_record(result)
    if not result["ok"]:
        codes = {error.get("code") for error in result.get("errors", [])}
        raise typer.Exit(2 if "empty_feedback" in codes else 1)
    raise typer.Exit(0)


leads_app = typer.Typer(
    name="leads",
    help="Grade lead eligibility and pair raw CPL with ELIGIBLE-lead CPL.",
    no_args_is_help=True,
)
app.add_typer(leads_app, name="leads")


@leads_app.command("grade")
def leads_grade_cmd(
    file: str = typer.Option(..., "--file", help="JSON array of lead records to grade."),
    spend: float = typer.Option(
        None, "--spend", help="Ad spend for this set; pairs raw CPL with eligible CPL."
    ),
    require_url: bool = typer.Option(
        False, "--require-url", help="Treat a missing/invalid site URL as ineligible."
    ),
    no_owner_answer: bool = typer.Option(
        False, "--no-owner-answer", help="Do not require an owner/qualifying answer."
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Grade a leads JSON for eligibility; honest CPL beside raw CPL."""
    path = Path(file).expanduser()
    if not path.exists():
        typer.echo(f"mb leads grade: file not found: {file}", err=True)
        raise typer.Exit(2)
    try:
        leads = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        typer.echo(f"mb leads grade: {file} is not valid JSON ({exc})", err=True)
        raise typer.Exit(2) from exc
    if not isinstance(leads, list):
        typer.echo("mb leads grade: expected a JSON array of lead records", err=True)
        raise typer.Exit(2)
    if not all(isinstance(item, dict) for item in leads):
        typer.echo("mb leads grade: each lead must be a JSON object", err=True)
        raise typer.Exit(2)
    if spend is not None and (not math.isfinite(spend) or spend < 0):
        typer.echo("mb leads grade: --spend must be a finite, zero-or-positive number", err=True)
        raise typer.Exit(2)
    result = leads_mod.grade_batch(
        leads,
        spend=spend,
        require_url=require_url,
        require_owner_answer=not no_owner_answer,
    )
    if json_out:
        typer.echo(
            _json_payload(result, command="mb leads grade", schema_name="mainbranch.leads.v1")
        )
    else:
        leads_mod.render_batch(result)
    raise typer.Exit(0)


production_app = typer.Typer(
    name="production",
    help="Plan the money-taking branch-protection posture (read-only).",
    no_args_is_help=True,
)
app.add_typer(production_app, name="production")


def _gh_protection(branch: str) -> tuple[str, dict[str, Any] | None]:
    """Resolve repo slug + current branch protection via gh (best-effort)."""
    import shutil
    import subprocess

    if not shutil.which("gh"):
        return "", None
    slug = ""
    try:
        nwo = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if nwo.returncode == 0:
            slug = nwo.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        return "", None
    if not slug:
        return "", None
    try:
        prot = subprocess.run(
            ["gh", "api", f"repos/{slug}/branches/{branch}/protection"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.SubprocessError:
        return slug, None
    if prot.returncode != 0:
        return slug, None  # 404 = unprotected
    try:
        return slug, json.loads(prot.stdout)
    except json.JSONDecodeError:
        return slug, None


@production_app.command("plan")
def production_plan_cmd(
    branch: str = typer.Option("main", "--branch", help="Default branch to inspect."),
    solo: bool = typer.Option(
        False, "--solo", help="Solo-on-main: record protection as a deliberate skip."
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Report the money-taking protection gap and the operator-applies commands."""
    if solo:
        result = production_mod.plan("", branch=branch, solo=True)
    else:
        slug, protection = _gh_protection(branch)
        result = production_mod.plan(slug, branch=branch, current_protection=protection)
    if json_out:
        typer.echo(
            _json_payload(
                result, command="mb production plan", schema_name="mainbranch.production.v1"
            )
        )
    else:
        production_mod.render_plan(result)
    raise typer.Exit(0 if result["ok"] else 1)


suggest_app = typer.Typer(
    name="suggest",
    help="Suggest read-only business repo improvements.",
    no_args_is_help=True,
)
app.add_typer(suggest_app, name="suggest")

workflow_app = typer.Typer(
    name="workflow",
    help="List Main Branch workflow support across runtimes.",
    no_args_is_help=True,
)
app.add_typer(workflow_app, name="workflow")

CONNECT_EXEC_COMMAND_ARGUMENT = typer.Argument(
    None,
    help="With `mb connect exec <provider> --`, the command to run and its arguments.",
    show_default=False,
)
CONNECT_KEEP_ENV_OPTION = typer.Option(
    None,
    "--keep-env",
    help="With exec, retain a named parent variable. Repeatable.",
)

CONNECT_METADATA_OPTION = typer.Option(
    [],
    "--metadata",
    "-m",
    help="Non-sensitive provider metadata as key=value. Repeat as needed.",
)

VALIDATE_PATHS_OPTION = typer.Option(
    [],
    "--paths",
    help=(
        "Scope the report to repo-relative file or directory prefixes "
        "(repeatable) — validate only what you touched."
    ),
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"mb {__version__}")
        raise typer.Exit()


def _json_payload(payload: dict[str, Any], *, command: str, schema_name: str) -> str:
    return json.dumps(
        envelope(payload, command=command, schema_name=schema_name),
        indent=2,
        default=json_default,
    )


def _unreadable_guard(
    repo: str,
    *,
    command: str,
    schema_name: str,
    json_out: bool,
    read: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Run a read-only report; a file it cannot read is named, not a traceback (#1106).

    The JSON envelope carries one `unreadable_file` error naming the path and
    its fix; the human form prints the same sentence. Both exit 1.
    """
    try:
        return read()
    except (OSError, ValueError, RuntimeError) as exc:
        if not unreadable_mod.is_unreadable_error(exc):
            raise
        message = unreadable_mod.message(exc, Path(repo).expanduser().resolve())
    if json_out:
        typer.echo(
            _json_error_payload(
                command=command,
                schema_name=schema_name,
                code=unreadable_mod.JSON_ERROR_CODE,
                message=message,
            )
        )
    else:
        typer.echo(f"{command}: {message}", err=True)
    raise typer.Exit(1)


def _json_error_payload(
    *,
    command: str,
    schema_name: str,
    code: str,
    message: str,
) -> str:
    return _json_payload(
        {
            "ok": False,
            "errors": [{"code": code, "message": message}],
            "safe_to_share": True,
        },
        command=command,
        schema_name=schema_name,
    )


def _is_interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


CONNECT_JSON_SCHEMA = "mainbranch.connect"
# `mb connect google --oauth --timeout`; kept here so the CLI does not import
# the OAuth modules until --oauth is used. Matches google_connect.
GOOGLE_OAUTH_TIMEOUT_DEFAULT = 300


def _connect_failure(
    command: str,
    message: str,
    *,
    json_out: bool,
    exit_code: int,
    state: str,
    rule: str = "",
    backend_state: str = "",
    repair: str = "",
    repair_command: str = "",
    secrets: tuple[str, ...] = (),
) -> NoReturn:
    """Report one `mb connect` failure and exit with ``exit_code``.

    The human text always goes to stderr. With ``--json`` the same failure is
    also written to stdout as one envelope (#973), so a script never reads an
    empty stdout; ``state`` is its stable machine code. Neither stream carries
    a secret: messages never quote secret-shaped input, and both streams get
    the same redaction, including any value in ``secrets``.
    """
    safe_message = connect_mod._redact_sensitive_text(message, secrets)
    typer.echo(f"{command}: {safe_message}", err=True)
    if json_out:
        payload: dict[str, Any] = {
            "ok": False,
            "state": state,
            "summary": safe_message,
            "repair": repair,
            "repair_command": repair_command,
            "exit_code": exit_code,
            "safe_to_share": True,
            "errors": [{"code": state, "message": safe_message}],
        }
        if rule:
            payload["rule"] = rule
        if backend_state:
            payload["backend_state"] = backend_state
        typer.echo(_json_payload(payload, command=command, schema_name=CONNECT_JSON_SCHEMA))
    raise typer.Exit(exit_code)


def _connect_usage_exit(command: str, message: str, *, json_out: bool) -> NoReturn:
    """Exit 2 for a usage error, with a JSON envelope under ``--json``."""
    _connect_failure(command, message, json_out=json_out, exit_code=2, state="usage_error")


def _connect_error_exit(
    command: str,
    exc: ValueError,
    *,
    code: int = 2,
    json_out: bool = False,
    secrets: tuple[str, ...] = (),
) -> NoReturn:
    """Exit ``code`` (2 unless a refusal has its own) for a connect error.

    The one place connect refusals are logged. A ``ConnectRefusal`` or a
    config-boundary error records one refusal line (rule and command only);
    any other ``ValueError`` records nothing. Library callers that catch
    refusals themselves never log.
    """
    rule = ""
    if isinstance(exc, connect_mod.ConnectRefusal):
        feedback_mod.record_refusal(f"connect.{exc.rule}", command)
        state, rule = "refused", exc.rule
    elif isinstance(exc, connect_mod.ConfigBoundaryError):
        feedback_mod.record_refusal("connect.config_boundary", command)
        state = "config_boundary"
    elif isinstance(exc, connect_mod.ConfigCorruptError):
        state = "config_corrupt"
    else:
        state = "invalid_request"
    try:
        _connect_failure(
            command,
            str(exc),
            json_out=json_out,
            exit_code=code,
            state=state,
            rule=rule,
            secrets=secrets,
        )
    except typer.Exit as exit_exc:
        raise exit_exc from exc


def _connect_runtime_exit(
    command: str,
    exc: RuntimeError,
    *,
    json_out: bool,
    secrets: tuple[str, ...] = (),
) -> NoReturn:
    """Exit 1 for a credential-backend or other runtime failure."""
    if isinstance(exc, connect_mod.KeychainError):
        detail = connect_mod._backend_repair(exc.reason)
        state = connect_mod.BACKEND_FAILURE_STATE
        backend_state = exc.reason
        repair, repair_command = detail["repair"], detail["repair_command"]
    elif isinstance(exc, connect_mod.MetadataWriteError):
        state, backend_state, repair, repair_command = "metadata_write_failed", "", "", ""
    elif isinstance(exc, connect_mod.CredentialBusyError):
        state, backend_state, repair, repair_command = exc.state, "", "", ""
    else:
        state, backend_state, repair, repair_command = "connect_failed", "", "", ""
    try:
        _connect_failure(
            command,
            str(exc),
            json_out=json_out,
            exit_code=1,
            state=state,
            backend_state=backend_state,
            repair=repair,
            repair_command=repair_command,
            secrets=secrets,
        )
    except typer.Exit as exit_exc:
        raise exit_exc from exc


def _render_launch_screen() -> None:
    cwd = Path.cwd().resolve()
    repo = cwd if looks_like_business_repo(cwd) else None
    alert = format_update_alert(package_update_status(repo))
    lines = [""]
    if alert:
        lines.extend([alert, ""])
    lines.extend(
        [
            "Main Branch",
            "Stay connected to the business while agents handle execution.",
            "",
            "Choose a trail:",
            "  New here      mb onboard       guided setup",
            "  Daily work    mb start         check handoff / open Claude Code",
            "  Briefing      mb status        terminal-only status facts",
            "  Broken setup  mb doctor        check git, GitHub, Claude Code, and skills",
            "  Power user    mb --help        full command list",
            "",
            "Plain command reference: mb --plain",
            "",
        ]
    )
    typer.echo("\n".join(lines))


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@app.callback()
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
    plain: bool = typer.Option(
        False,
        "--plain",
        help="Show the plain command reference instead of the launch screen.",
    ),
) -> None:
    """Root callback — version flag and bare launch routing."""
    if ctx.invoked_subcommand is not None:
        return
    if plain or not _is_interactive_terminal():
        typer.echo(ctx.get_help())
        return
    _render_launch_screen()


@app.command("init")
def init_cmd(
    path: str = typer.Argument(".", help="Where to scaffold (default: current dir)."),
    name: str = typer.Option("", "--name", help="Business name (skips prompt if given)."),
    owner_name: str = typer.Option("", "--owner-name", help="Business name for the owner file."),
    owner_github: str = typer.Option(
        "",
        "--owner-github",
        help="GitHub handle for the owner file, without @.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Set up a fresh business repo (business folders, CLAUDE.md, git init)."""
    result = init_mod.run(path=path, name=name, owner_name=owner_name, owner_github=owner_github)
    if json_out:
        typer.echo(json.dumps(result, indent=2))
    else:
        if result["status"] == "already-initialized":
            typer.echo(f"already set up at {result['path']} — nothing to do.")
        elif result["status"] == "ok":
            typer.echo(f"set up {result['business_name']}.")
            typer.echo("")
            for line in result["created"]:
                typer.echo(f"  + {line}")
            typer.echo("")
            for warning in result.get("warnings", []):
                typer.echo(f"warning: {warning}", err=True)
            for item in result.get("operator_actions", []):
                typer.echo(f"  run after the manual step: {item['command']}", err=True)
            if result.get("warnings"):
                typer.echo("")
            typer.echo("next:")
            typer.echo(f"  cd {result['path']}")
            typer.echo("  claude")
            typer.echo("  /mb-start")
            typer.echo("")
            typer.echo("connected accounts:")
            typer.echo(
                "  See CLAUDE.md -> Connected accounts before wiring tools that "
                "spend, publish, or mutate customer accounts."
            )
        else:
            typer.echo(f"could not set up: {result.get('error')}", err=True)
            raise typer.Exit(1)


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


@workflow_app.command("list")
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


@onboard_app.callback()
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


@onboard_app.command("status")
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


@onboard_app.command("plan")
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


def _doctor_repair_from_args(args: list[str], *, json_out: bool) -> None:
    repo = "."
    plan = False
    apply_changes = False
    include_migration = False
    only = ""
    all_agents = False
    local_json = json_out
    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg == "--help":
            typer.echo(
                "Usage: mb doctor repair [--repo PATH] [--plan | --apply] "
                "[--only claude|codex | --all-agents] [--include-migration] [--json]"
            )
            typer.echo("")
            typer.echo("Plan or apply guided business-repo reconciliation repairs.")
            typer.echo("")
            typer.echo(
                "Migration apply is opt-in: use `--include-migration` only with `--apply` "
                "after reviewing the plan."
            )
            raise typer.Exit(0)
        if arg == "--repo":
            idx += 1
            if idx >= len(args):
                typer.echo("mb doctor repair: --repo requires a path", err=True)
                raise typer.Exit(2)
            repo = args[idx]
        elif arg == "--plan":
            plan = True
        elif arg == "--apply":
            apply_changes = True
        elif arg == "--include-migration":
            include_migration = True
        elif arg == "--all-agents":
            all_agents = True
        elif arg == "--only":
            idx += 1
            if idx >= len(args):
                typer.echo("mb doctor repair: --only requires a scope", err=True)
                raise typer.Exit(2)
            only = args[idx]
        elif arg == "--json":
            local_json = True
        else:
            typer.echo(f"mb doctor repair: unknown option {arg}", err=True)
            raise typer.Exit(2)
        idx += 1

    if plan and apply_changes:
        typer.echo("mb doctor repair: choose only one of --plan or --apply", err=True)
        raise typer.Exit(2)
    if include_migration and not apply_changes:
        typer.echo(
            "mb doctor repair: --include-migration requires --apply. "
            "First run `mb doctor repair --plan`; after review, rerun "
            "`mb doctor repair --apply --include-migration`.",
            err=True,
        )
        raise typer.Exit(2)
    if only and only not in {"claude", "codex"}:
        typer.echo("mb doctor repair: --only supports `claude` or `codex`", err=True)
        raise typer.Exit(2)
    if only and all_agents:
        typer.echo("mb doctor repair: --only cannot be combined with --all-agents", err=True)
        raise typer.Exit(2)
    if only and include_migration:
        typer.echo("mb doctor repair: --only cannot be combined with --include-migration", err=True)
        raise typer.Exit(2)
    if all_agents and include_migration:
        typer.echo(
            "mb doctor repair: --all-agents cannot be combined with --include-migration",
            err=True,
        )
        raise typer.Exit(2)

    if not apply_changes:
        # #1106: a file the plan cannot read is named, not a traceback.
        report = _unreadable_guard(
            repo,
            command="mb doctor repair",
            schema_name="mainbranch.doctor.repair.result",
            json_out=local_json,
            read=lambda: (
                doctor_mod.repair_plan(repo=repo, only=only, all_agents=all_agents)
                if only or all_agents
                else doctor_mod.repair_plan(repo=repo)
            ),
        )
    elif only or all_agents:
        report = doctor_mod.repair_apply(
            repo=repo,
            include_migration=include_migration,
            only=only,
            all_agents=all_agents,
        )
    else:
        report = doctor_mod.repair_apply(
            repo=repo,
            include_migration=include_migration,
        )

    if local_json:
        typer.echo(
            _json_payload(
                report,
                command="mb doctor repair",
                schema_name="mainbranch.doctor.repair.result",
            )
        )
    else:
        doctor_mod.render_repair(report)
    raise typer.Exit(0 if report["ok"] else 1)


def _doctor_help() -> None:
    typer.echo("Usage: mb doctor [OPTIONS] [PATH]")
    typer.echo("")
    typer.echo("Check the health of a Main Branch repo. Exits 1 on red checks.")
    typer.echo("")
    typer.echo("Options:")
    typer.echo("  --json   Machine-readable output.")
    typer.echo("  --help   Show this message and exit.")
    typer.echo("")
    typer.echo("Repair:")
    typer.echo(
        "  mb doctor repair [--repo PATH] [--plan | --apply] "
        "[--only claude|codex | --all-agents] [--include-migration] [--json]"
    )
    typer.echo("  Note: --include-migration is valid only with --apply after plan review.")


@app.command(
    "doctor",
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
        "help_option_names": [],
    },
)
def doctor_cmd(
    ctx: typer.Context,
    path: str = typer.Argument(".", help="Repo to diagnose."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Check the health of a Main Branch repo. Exits 1 on red checks."""
    if path == "--help":
        _doctor_help()
        raise typer.Exit(0)
    if path == "repair":
        _doctor_repair_from_args(list(ctx.args), json_out=json_out)
        return
    if path.startswith("-"):
        typer.echo(f"mb doctor: unknown option {path}", err=True)
        raise typer.Exit(2)
    if ctx.args:
        typer.echo(f"mb doctor: unknown option(s): {' '.join(ctx.args)}", err=True)
        raise typer.Exit(2)
    report = _unreadable_guard(
        path,
        command="mb doctor",
        schema_name="mainbranch.doctor.result",
        json_out=json_out,
        read=lambda: doctor_mod.run(path=path),
    )
    if json_out:
        typer.echo(
            _json_payload(report, command="mb doctor", schema_name="mainbranch.doctor.result")
        )
    else:
        doctor_mod.render_human(report)
        if not report["ok"]:
            typer.echo(
                "\nIf this should become a public task, run "
                "`mb issue draft bug --command 'mb doctor' --what-happened '<summary>'` "
                "after removing private details."
            )
    raise typer.Exit(0 if report["ok"] else 1)


@issue_app.command("draft")
def issue_draft_cmd(
    kind: str = typer.Argument("bug", help="Issue shape: bug, feature, or question."),
    repo: str = typer.Option(".", "--repo", help="Business repo where the draft is stored."),
    title: str = typer.Option("", "--title", help="Issue title. Prefix is added by template."),
    command: str = typer.Option("", "--command", help="Command or skill that failed."),
    what_happened: str = typer.Option(
        "",
        "--what-happened",
        "--happened",
        help="Actual behavior or error output.",
    ),
    expected: str = typer.Option("", "--expected", help="Expected behavior."),
    diagnostics: str = typer.Option("", "--diagnostics", help="Extra diagnostic text to scrub."),
    diagnostics_file: str = typer.Option(
        "",
        "--diagnostics-file",
        help="Read extra diagnostics from a local file, then scrub them.",
    ),
    problem: str = typer.Option("", "--problem", help="Feature request problem statement."),
    surface: str = typer.Option(
        "Other / not sure",
        "--surface",
        help="Feature surface: CLI subcommand, Skill, Both, or Other / not sure.",
    ),
    proposal: str = typer.Option("", "--proposal", help="Feature request proposal."),
    alternatives: str = typer.Option("", "--alternatives", help="Alternatives considered."),
    related: str = typer.Option("", "--related", help="Related issues or PRs."),
    question: str = typer.Option("", "--question", help="Question to ask."),
    context: str = typer.Option("", "--context", help="Context for a question."),
    tried: str = typer.Option("", "--tried", help="What you have tried."),
    include_doctor: bool = typer.Option(
        True,
        "--doctor/--no-doctor",
        help="For bug drafts, include scrubbed `mb doctor --json` output.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Create a local, scrubbed issue draft under .mb/issue-drafts/."""
    diagnostics_text = diagnostics
    if diagnostics_file:
        try:
            diagnostics_text = Path(diagnostics_file).read_text(encoding="utf-8")
        except OSError as exc:
            typer.echo(f"mb issue draft: could not read diagnostics file: {exc}", err=True)
            raise typer.Exit(2) from exc
    fields = {
        "command": command,
        "happened": what_happened,
        "expected": expected,
        "diagnostics": diagnostics_text,
        "problem": problem,
        "surface": surface,
        "proposal": proposal,
        "alternatives": alternatives,
        "related": related,
        "question": question,
        "context": context,
        "tried": tried,
    }
    try:
        result = issue_mod.create_draft(
            repo=repo,
            kind=kind,
            title=title,
            fields=fields,
            include_doctor=include_doctor,
        )
    except ValueError as exc:
        typer.echo(f"mb issue draft: {exc}", err=True)
        raise typer.Exit(2) from exc
    if json_out:
        typer.echo(
            _json_payload(
                result,
                command="mb issue draft",
                schema_name="mainbranch.issue.draft.result",
            )
        )
    else:
        typer.echo(f"drafted {result['kind']} issue: {result['relative_path']}")
        typer.echo("review it before submitting; drafts are local and gitignored by default.")
        if result["redactions"]:
            summary = ", ".join(f"{key}={value}" for key, value in result["redactions"].items())
            typer.echo(f"redactions: {summary}")
        typer.echo("next:")
        typer.echo(f"  {result['next_command']} --yes")


@issue_app.command("open")
def issue_open_cmd(
    draft: str = typer.Argument(..., help="Draft markdown file from `mb issue draft`."),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Submit with gh after you have reviewed the draft.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Open a reviewed issue draft through gh, or print a manual fallback."""
    try:
        result = issue_mod.open_draft(draft, yes=yes)
    except ValueError as exc:
        typer.echo(f"mb issue open: {exc}", err=True)
        raise typer.Exit(2) from exc
    if json_out:
        typer.echo(
            _json_payload(
                result,
                command="mb issue open",
                schema_name="mainbranch.issue.open.result",
            )
        )
    elif result.get("submitted"):
        typer.echo(f"opened issue: {result['url']}")
    else:
        typer.echo("issue not submitted.")
        typer.echo(result["reason"])
        typer.echo("manual fallback:")
        for step in result["manual_steps"]:
            typer.echo(f"  - {step}")
    raise typer.Exit(0 if result["ok"] else 1)


_F = TypeVar("_F", bound=Callable[..., Any])


_CONNECT_SUBCOMMANDS = frozenset(
    {
        "list",
        "plan",
        "status",
        "doctor",
        "hygiene",
        "identity",
        "test",
        "exec",
        "rotate",
        "token",
        "hydrate",
        "repair",
    }
)


def _no_secret_traceback(func: _F) -> _F:
    """Turn an unexpected error into a one-line message with no traceback.

    Credential-bearing commands hold secrets in local variables. Whether a
    crash traceback prints them depends on the installed Typer, Click and
    Rich, so these commands never let one reach the excepthook.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (typer.Exit, typer.Abort):
            raise
        except Exception as exc:
            label = f"mb {func.__name__.removesuffix('_cmd').replace('_', ' ')}"
            # `mb connect token` (and the other subcommands) name themselves;
            # only a fixed subcommand name is used, never other input.
            if kwargs.get("target") in _CONNECT_SUBCOMMANDS:
                label = f"{label} {kwargs['target']}"
            try:
                _connect_failure(
                    label,
                    f"unexpected error ({type(exc).__name__}); details are hidden because "
                    "they may hold a secret",
                    json_out=bool(kwargs.get("json_out")),
                    exit_code=1,
                    state="unexpected_error",
                )
            except typer.Exit as exit_exc:
                raise typer.Exit(exit_exc.exit_code) from None

    return wrapper  # type: ignore[return-value]


def _connect_google_oauth(
    *,
    target: str,
    provider: str,
    repo: str,
    account_label: str,
    scope: str,
    metadata: list[str],
    client_file: str,
    client_stdin: bool,
    reauth: bool,
    paste: bool,
    no_browser: bool,
    port: int,
    timeout: int,
    replace_access_token: bool,
    conflicts: list[str],
    json_out: bool,
) -> NoReturn:
    """`mb connect google --oauth`: the one-time Google sign-in (#1004).

    Runs inside `connect_cmd`, so `_no_secret_traceback` covers it; Ctrl-C
    gets a fixed line here too, naming what the sign-in had already stored.
    Every message below is fixed text.
    """
    from mb import google_connect as google_connect_mod
    from mb import google_oauth as google_oauth_mod

    command = "mb connect google"
    if target != "google" or provider:
        _connect_usage_exit(
            "mb connect", "--oauth is only for `mb connect google`", json_out=json_out
        )
    if conflicts:
        _connect_usage_exit(
            command, f"--oauth cannot be combined with {', '.join(conflicts)}", json_out=json_out
        )
    if client_file and client_stdin:
        _connect_usage_exit(
            command, "choose one of --client-file and --client-stdin", json_out=json_out
        )
    if paste and client_stdin:
        _connect_usage_exit(
            command,
            "--paste reads the redirect from the terminal; pass the client with --client-file",
            json_out=json_out,
        )
    progress = google_connect_mod.Progress()
    try:
        if client_file:
            client_json: str | None = google_connect_mod.read_client_file(client_file)
        elif client_stdin:
            client_json = sys.stdin.read(google_connect_mod.CLIENT_JSON_MAX_BYTES + 1)
        else:
            client_json = None
        result = google_connect_mod.bootstrap(
            repo,
            client_json=client_json,
            metadata_pairs=metadata,
            reauth=reauth,
            paste=paste,
            no_browser=no_browser,
            port=port,
            timeout=float(timeout),
            replace_access_token=replace_access_token,
            account_label=account_label,
            scope=scope,
            emit=lambda line: typer.echo(line, err=True),
            progress=progress,
        )
    except KeyboardInterrupt:
        _connect_failure(
            command,
            google_connect_mod.cancelled_message(progress),
            json_out=json_out,
            exit_code=130,
            state="cancelled",
        )
    except google_oauth_mod.GoogleOAuthError as exc:
        _connect_failure(
            command,
            f"{exc} Nothing was stored.",
            json_out=json_out,
            exit_code=2 if exc.rule == "paste_needs_tty" else 1,
            state=exc.state,
            rule=exc.rule,
            repair=exc.repair,
            repair_command=exc.repair if exc.repair.startswith("mb ") else "",
        )
    except google_connect_mod.GoogleConnectError as exc:
        _connect_failure(
            command,
            str(exc),
            json_out=json_out,
            exit_code=1,
            state=exc.state,
            rule=exc.rule,
            backend_state=exc.backend_state,
        )
    except (
        connect_mod.ConnectRefusal,
        connect_mod.ConfigBoundaryError,
        connect_mod.ConfigCorruptError,
    ) as exc:
        _connect_error_exit(command, exc, json_out=json_out)
    except connect_mod.KeychainError as exc:
        _connect_runtime_exit(command, exc, json_out=json_out)
    except Exception as exc:
        # Before the first write, `_no_secret_traceback` reports it. After
        # it, say what is stored; the exception's text is never shown.
        if not google_connect_mod.wrote_anything(progress):
            raise
        _connect_failure(
            command,
            google_connect_mod.cancelled_message(
                progress,
                lead=f"Google sign-in stopped on an unexpected error ({type(exc).__name__}; "
                "details are hidden because they may hold a secret)",
            ),
            json_out=json_out,
            exit_code=1,
            state="unexpected_error",
        )
    if json_out:
        typer.echo(json.dumps(result, indent=2))
    else:
        google_connect_mod.render_result(result)
    raise typer.Exit(0 if result["ok"] else 1)


@app.command("connect")
@_no_secret_traceback
def connect_cmd(
    target: str = typer.Argument(
        "",
        help=(
            "Provider to connect, or `list` / `plan` / `status` / `doctor` / `hygiene` / "
            "`identity` / `test` / `exec` / `rotate` / `token` / `audit` / `policy` / "
            "`hydrate` / `repair`."
        ),
    ),
    provider: str = typer.Argument(
        "",
        help="Provider for subcommands such as `mb connect test <provider>`.",
    ),
    command: list[str] = CONNECT_EXEC_COMMAND_ARGUMENT,
    repo: str = typer.Option(".", "--repo", help="Business repo whose metadata is updated."),
    account_label: str | None = typer.Option(
        None,
        "--account",
        "--label",
        help=(
            "Human account label. Storing a secret again keeps the recorded label; "
            '`--account ""` clears it.'
        ),
    ),
    scope: str = typer.Option(
        "",
        "--scope",
        help="Connection metadata scope: repo or user (default repo).",
    ),
    token: str = typer.Option(
        "",
        "--token",
        help="Deprecated: token is visible in process arguments. Use --token-stdin.",
    ),
    token_stdin: bool = typer.Option(
        False,
        "--token-stdin",
        help="Read the secret token or key from stdin.",
    ),
    from_env: bool = typer.Option(
        False,
        "--from-env",
        help="Read the provider credential from a known environment variable.",
    ),
    custom: bool = typer.Option(
        False,
        "--custom",
        help=(
            "Register an operator-defined provider id (lowercase letters, "
            "digits, hyphens) with an api_key secret slot."
        ),
    ),
    metadata: list[str] = CONNECT_METADATA_OPTION,
    oauth: bool = typer.Option(
        False,
        "--oauth",
        help=(
            "With `mb connect google`: sign in to Google in a browser for read-only Search "
            "Console and GA4. A person runs this, never an agent."
        ),
    ),
    client_file: str = typer.Option(
        "",
        "--client-file",
        help="With --oauth, path to the Desktop app OAuth client JSON from Google Cloud.",
    ),
    client_stdin: bool = typer.Option(
        False,
        "--client-stdin",
        help="With --oauth, read the OAuth client JSON from stdin.",
    ),
    reauth: bool = typer.Option(
        False,
        "--reauth",
        help="With --oauth, renew this repo's Google sign-in (only when status says so).",
    ),
    paste: bool = typer.Option(
        False,
        "--paste",
        help=(
            "With --oauth, no local browser: open the printed URL anywhere, then paste the "
            "127.0.0.1 address it lands on. Needs a real terminal."
        ),
    ),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="With --oauth, print the sign-in URL instead of opening a browser.",
    ),
    port: int = typer.Option(
        0,
        "--port",
        min=0,
        max=65535,
        help="With --oauth, fixed 127.0.0.1 port for the sign-in redirect (0 picks one).",
    ),
    oauth_timeout: int | None = typer.Option(
        None,
        "--timeout",
        min=10,
        max=3600,
        help="With --oauth, seconds to wait for the browser sign-in (default 300).",
    ),
    replace_access_token: bool = typer.Option(
        False,
        "--replace-access-token",
        help=(
            "With --oauth, replace a stored Google access token; its Drive, Docs and Sheets "
            "use stops working."
        ),
    ),
    all_providers: bool = typer.Option(
        False,
        "--all",
        help=(
            "With `mb connect status`, include providers not connected yet. With "
            "`mb connect repair --keychain`, repair every Main Branch keychain item on this "
            "machine, not only this repo's."
        ),
    ),
    env_name: str = typer.Option(
        "",
        "--env",
        help="With `mb connect exec`, the variable that carries the secret into the command.",
    ),
    keep_env: list[str] | None = CONNECT_KEEP_ENV_OPTION,
    inherit_env: bool = typer.Option(
        False,
        "--inherit-env",
        help="With exec, retain the whole parent environment.",
    ),
    limit: int = typer.Option(20, "--limit", min=1, help="With audit, show the last N entries."),
    audit_provider: str = typer.Option("", "--provider", help="With audit, filter by provider."),
    source: str = typer.Option(
        "",
        "--source",
        help=(
            "Non-secret reference to where the credential lives, such as "
            "op://vault/item/field. Stored as metadata so `mb connect rotate` can re-read it."
        ),
    ),
    print_token: bool = typer.Option(
        False,
        "--print",
        help="With token, explicitly allow raw output. Noninteractive use is deprecated.",
    ),
    keychain: bool = typer.Option(
        False,
        "--keychain",
        help=(
            "With `mb connect repair`, let macOS ask once whether this mb install may read "
            "each stored credential. Needs a terminal."
        ),
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Connect provider credentials without committing secrets."""
    command = command or []
    if command and target != "exec":
        _connect_usage_exit(
            "mb connect",
            f"unexpected extra argument {connect_mod.quoted_input(command[0])}",
            json_out=json_out,
        )
    oauth_only = {
        "--client-file": bool(client_file),
        "--client-stdin": client_stdin,
        "--reauth": reauth,
        "--paste": paste,
        "--no-browser": no_browser,
        "--port": port != 0,
        # None unless given, so `--timeout 300` without --oauth is caught too.
        "--timeout": oauth_timeout is not None,
        "--replace-access-token": replace_access_token,
    }
    if oauth or any(oauth_only.values()):
        if not oauth:
            used = next(name for name, on in oauth_only.items() if on)
            _connect_failure(
                "mb connect",
                f"{used} needs --oauth",
                json_out=json_out,
                exit_code=2,
                state="usage_error",
                rule="oauth_option_without_oauth",
            )
        conflicts = {
            "--token": bool(token),
            "--token-stdin": token_stdin,
            "--from-env": from_env,
            "--source": bool(source),
            "--custom": custom,
        }
        _connect_google_oauth(
            target=target,
            provider=provider,
            repo=repo,
            account_label=account_label or "",
            scope=scope,
            metadata=metadata,
            client_file=client_file,
            client_stdin=client_stdin,
            reauth=reauth,
            paste=paste,
            no_browser=no_browser,
            port=port,
            timeout=GOOGLE_OAUTH_TIMEOUT_DEFAULT if oauth_timeout is None else oauth_timeout,
            replace_access_token=replace_access_token,
            conflicts=[name for name, on in conflicts.items() if on],
            json_out=json_out,
        )
    if not target:
        try:
            result = connect_mod.list_providers(repo)
        except ValueError as exc:
            _connect_error_exit("mb connect", exc, json_out=json_out)
        if json_out:
            typer.echo(json.dumps(result, indent=2))
        else:
            connect_mod.render_list(result)
        raise typer.Exit(0)
    if target == "list":
        try:
            result = connect_mod.list_providers(repo)
        except ValueError as exc:
            _connect_error_exit("mb connect list", exc, json_out=json_out)
        if json_out:
            typer.echo(json.dumps(result, indent=2))
        else:
            connect_mod.render_list(result)
        raise typer.Exit(0)
    if target == "plan":
        try:
            result = connect_mod.provider_plan(repo)
        except ValueError as exc:
            _connect_error_exit("mb connect plan", exc, json_out=json_out)
        if json_out:
            typer.echo(json.dumps(result, indent=2))
        else:
            connect_mod.render_plan(result)
        raise typer.Exit(0)
    if target == "status":
        try:
            if provider:
                result = connect_mod.status_provider(provider, repo)
            else:
                result = connect_mod.status_all(repo, include_all=all_providers)
        except ValueError as exc:
            _connect_error_exit("mb connect status", exc, json_out=json_out)
        if json_out:
            typer.echo(json.dumps(result, indent=2))
        elif provider:
            connect_mod.render_provider_status(result)
        else:
            connect_mod.render_status(result)
        if provider:
            needs_action = connect_mod.provider_needs_action(result)
        else:
            # Scoped to configured providers: with `--all`, the list includes
            # every built-in provider the business never connected, and a
            # provider nobody asked for is not something to act on.
            needs_action = any(
                connect_mod.provider_needs_action(item)
                for item in result["providers"]
                if item.get("configured", item.get("connected"))
            )
        raise typer.Exit(1 if needs_action else 0)
    if target == "doctor":
        try:
            result = connect_mod.doctor(repo)
        except ValueError as exc:
            _connect_error_exit("mb connect doctor", exc, json_out=json_out)
        if json_out:
            typer.echo(json.dumps(result, indent=2))
        else:
            connect_mod.render_doctor(result)
        raise typer.Exit(1 if result["needs_action"] else 0)
    if target == "hygiene":
        result = connect_mod.scan_credential_hygiene(repo)
        if json_out:
            typer.echo(json.dumps(result, indent=2))
        else:
            connect_mod.render_credential_hygiene(result)
        raise typer.Exit(0 if result["ok"] else 1)
    if target == "identity":
        try:
            result = connect_mod.business_identity(repo)
        except connect_mod.ConfigBoundaryError as exc:
            _connect_error_exit("mb connect identity", exc, json_out=json_out)
        if json_out:
            typer.echo(json.dumps(result, indent=2))
        else:
            connect_mod.render_identity(result)
        raise typer.Exit(0)
    if target == "hydrate":
        try:
            result = connect_mod.hydrate(repo, provider_id=provider)
        except ValueError as exc:
            _connect_error_exit("mb connect hydrate", exc, json_out=json_out)
        if json_out:
            typer.echo(json.dumps(result, indent=2))
        else:
            connect_mod.render_hydrate_result(result)
        raise typer.Exit(0 if result["ok"] else 1)
    if target == "policy":
        result = connect_mod.caller_policy_status(repo)
        if json_out:
            typer.echo(json.dumps(result, indent=2))
        else:
            state = (
                "invalid" if not result["valid"] else "present" if result["exists"] else "absent"
            )
            typer.echo(f"Caller policy: {state}")
            if result["error"]:
                typer.echo(result["error"])
            if result["policy"] is not None:
                typer.echo(json.dumps(result["policy"], indent=2))
            typer.echo(f"Caller: {result['caller']}")
            typer.echo(result["advisory"])
        raise typer.Exit(0 if result["valid"] else 1)
    if target == "audit":
        try:
            entries = connect_mod.read_release_audit(limit=limit, provider=audit_provider)
        except (OSError, ValueError):
            _connect_failure(
                "mb connect audit",
                "cannot read audit log",
                json_out=json_out,
                exit_code=1,
                state="audit_unavailable",
            )
        if json_out:
            typer.echo(json.dumps(entries, indent=2))
        elif not entries:
            typer.echo("No audit entries.")
        else:
            typer.echo("TIME  VERB  PROVIDER  RESULT  REASON  EXIT")
            for entry in entries:
                typer.echo(
                    "  ".join(
                        str(entry.get(key, ""))
                        for key in ("ts", "verb", "provider", "result", "reason", "exit_code")
                    )
                )
        raise typer.Exit(0)
    if target == "exec":
        if not provider or json_out:
            flags = (["inherit_env"] if inherit_env else []) + (["keep_env"] if keep_env else [])
            with suppress(connect_mod.ConnectRefusal):
                connect_mod.write_release_audit(
                    "exec",
                    provider,
                    repo,
                    result="refused",
                    reason="provider_required" if not provider else "json_not_supported",
                    exit_code=2,
                    flags=flags,
                )
        if not provider:
            _connect_usage_exit("mb connect exec", "provider required", json_out=json_out)
        if json_out:
            _connect_failure(
                "mb connect exec",
                "--json is not supported; the command's own output is passed through",
                json_out=json_out,
                exit_code=2,
                state="json_not_supported",
            )
        try:
            outcome = connect_mod.exec_with_secret(
                provider,
                command,
                repo,
                env_name=env_name,
                keep_env=keep_env,
                inherit_env=inherit_env,
            )
        except ValueError as exc:
            code = connect_mod.release_refusal_exit_code(exc)
            _connect_error_exit("mb connect exec", exc, code=code, json_out=json_out)
        if outcome["error"]:
            typer.echo(f"mb connect exec: {outcome['error']}", err=True)
            if outcome["repair_command"]:
                typer.echo(f"repair: {outcome['repair_command']}", err=True)
        if outcome.get("not_recorded_note"):
            note_line = connect_mod.not_recorded_line(outcome["not_recorded_note"])
            typer.echo(f"mb connect exec: {note_line}", err=True)
        raise typer.Exit(outcome["returncode"])
    if target == "rotate":
        if not provider:
            _connect_usage_exit("mb connect rotate", "provider required", json_out=json_out)
        try:
            result = connect_mod.rotate_provider(provider, repo)
        except ValueError as exc:
            _connect_error_exit("mb connect rotate", exc, json_out=json_out)
        except RuntimeError as exc:
            _connect_runtime_exit("mb connect rotate", exc, json_out=json_out)
        if json_out:
            typer.echo(json.dumps(result, indent=2))
        else:
            connect_mod.render_rotate_result(result)
        if not result["stored"]:
            raise typer.Exit(1)
        raise typer.Exit(1 if connect_mod.provider_needs_action(result["status"]) else 0)
    if target == "token":
        if not provider or json_out:
            flags = ["print"] if print_token else []
            if print_token and not sys.stdin.isatty():
                flags.append("print_noninteractive")
            with suppress(connect_mod.ConnectRefusal):
                connect_mod.write_release_audit(
                    "token",
                    provider,
                    repo,
                    result="refused",
                    reason="provider_required" if not provider else "json_not_supported",
                    exit_code=2,
                    flags=flags,
                )
        if not provider:
            _connect_usage_exit("mb connect token", "provider required", json_out=json_out)
        if json_out:
            # A JSON error envelope only: the token itself is never in JSON.
            _connect_failure(
                "mb connect token",
                "--json is not supported; the token is printed raw to stdout",
                json_out=json_out,
                exit_code=2,
                state="json_not_supported",
            )
        try:
            result = connect_mod.token_for_output(provider, repo, print_token=print_token)
        except connect_mod.ConnectRefusal as exc:
            code = connect_mod.release_refusal_exit_code(exc)
            _connect_error_exit("mb connect token", exc, code=code, json_out=json_out)
        except ValueError as exc:
            _connect_error_exit("mb connect token", exc, json_out=json_out)
        if not result["ok"]:
            typer.echo(f"mb connect token: {result['error']}", err=True)
            if result["repair_command"]:
                typer.echo(f"repair: {result['repair_command']}", err=True)
        if result.get("not_recorded_note"):
            note_line = connect_mod.not_recorded_line(result["not_recorded_note"])
            typer.echo(f"mb connect token: {note_line}", err=True)
        if not result["ok"]:
            raise typer.Exit(1)
        # The token is the entire stdout contract; nothing else may print here.
        typer.echo(result["token"], nl=False)
        raise typer.Exit(0)
    if target == "repair":
        if provider:
            _connect_usage_exit(
                "mb connect repair",
                f"unexpected extra argument {connect_mod.quoted_input(provider)}",
                json_out=json_out,
            )
        if not keychain:
            _connect_usage_exit(
                "mb connect repair", "choose what to repair: --keychain", json_out=json_out
            )
        if not sys.stdin.isatty():
            # The only command that may show a keychain dialog. Without a
            # terminal there is nobody to answer it, so refuse rather than wait.
            _connect_failure(
                "mb connect repair --keychain",
                "run this from a terminal; macOS may ask you to allow access",
                json_out=json_out,
                exit_code=2,
                state="needs_terminal",
            )
        typer.echo(
            "macOS may ask once per credential. Choose Always Allow; Allow lets only this "
            "read through.",
            err=True,
        )
        try:
            if all_providers:
                result = connect_mod.repair_keychain_all(repo, interactive=True)
            else:
                result = connect_mod.repair_keychain(repo, interactive=True)
        except ValueError as exc:
            _connect_error_exit("mb connect repair", exc, json_out=json_out)
        except connect_mod.KeychainError as exc:
            _connect_runtime_exit("mb connect repair --keychain --all", exc, json_out=json_out)
        if json_out:
            typer.echo(json.dumps(result, indent=2))
        else:
            connect_mod.render_keychain_repair(result)
        raise typer.Exit(0 if result["ok"] else 1)
    if target == "test":
        if not provider:
            _connect_usage_exit("mb connect test", "provider required", json_out=json_out)
        try:
            result = connect_mod.test_provider(provider, repo)
        except ValueError as exc:
            _connect_error_exit("mb connect test", exc, json_out=json_out)
        if json_out:
            typer.echo(json.dumps(result, indent=2))
        else:
            connect_mod.render_test_result(result)
        # `needs_action` is set only by checks that can fail without changing
        # the recorded status (a Google sign-in on a network blip). A check
        # left out of a git-tracked .mb/connect.yaml exits on its own outcome.
        # A check not recorded because the user-scope file is unreadable does the same.
        if result.get("not_recorded_reason") == "connect_yaml_tracked" or result.get(
            "exit_follows_check"
        ):
            needs_action = bool(result.get("needs_action"))
        else:
            needs_action = connect_mod.provider_needs_action(result["status"]) or bool(
                result.get("needs_action")
            )
        raise typer.Exit(1 if needs_action else 0)
    if provider:
        _connect_usage_exit(
            "mb connect",
            f"unexpected extra argument {connect_mod.quoted_input(provider)}",
            json_out=json_out,
        )

    try:
        if custom:
            provider_info = connect_mod.normalize_provider(target, allow_custom=True)
        else:
            provider_info = connect_mod.resolve_provider(target, repo)
    except ValueError as exc:
        _connect_error_exit("mb connect", exc, json_out=json_out)

    secret_value = token
    if token_stdin:
        secret_value = connect_mod.read_stdin_token()
    credential_source = "prompt" if not secret_value else "token"
    consumed_env_var = ""
    if token_stdin:
        credential_source = "stdin"
    if from_env and not secret_value and provider_info.required_secrets:
        for env_var in provider_info.env_vars:
            value = os.environ.get(env_var, "")
            if value != "":
                secret_value = value
                credential_source = "env"
                consumed_env_var = env_var
                break
        if not secret_value:
            names = ", ".join(provider_info.env_vars) or "(none registered)"
            _connect_failure(
                "mb connect",
                f"no credential found in env vars: {names}",
                json_out=json_out,
                exit_code=1,
                state="missing_env_credential",
            )
    if not secret_value and provider_info.required_secrets and sys.stdin.isatty():
        secret_value = typer.prompt(
            f"{provider_info.name} {provider_info.required_secrets[0]}",
            hide_input=True,
            default="",
            show_default=False,
        )

    try:
        result = connect_mod.connect_provider(
            provider_info.id,
            repo=repo,
            token=secret_value,
            account_label=account_label,
            metadata_pairs=metadata,
            scope=scope,
            custom=custom,
            source=source,
        )
        result["credential_source"] = {
            "type": credential_source if secret_value else "missing",
            "env_var": consumed_env_var,
        }
    except ValueError as exc:
        _connect_error_exit("mb connect", exc, json_out=json_out, secrets=(secret_value,))
    except RuntimeError as exc:
        _connect_runtime_exit("mb connect", exc, json_out=json_out, secrets=(secret_value,))
    if json_out:
        typer.echo(json.dumps(result, indent=2))
    else:
        connect_mod.render_connect_result(result)
    raise typer.Exit(0 if result["ok"] else 1)


@app.command("usage")
def usage_cmd(
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
    directory: str | None = typer.Option(None, "--dir", help="Override usage.dir locally."),
    now: str | None = typer.Option(None, "--now", help="UTC evaluation time for fixtures."),
) -> None:
    """Show local agent usage and weekly role caps, without contacting providers."""
    result = usage_mod.collect(directory=directory, now=now)
    if json_out:
        typer.echo(_json_payload(result, command="mb usage", schema_name="mainbranch.usage"))
    else:
        typer.echo(usage_mod.render(result))
    raise typer.Exit(result["exit_code"])


@app.command("status")
def status_cmd(
    path: str = typer.Argument(".", help="Business repo to brief."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed briefing sections."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable ANSI color in human output."),
    peek: bool = typer.Option(
        False,
        "--peek",
        help="Read status without updating the last-status-seen marker.",
    ),
) -> None:
    """Show a cheap daily briefing for a Main Branch repo."""
    try:
        report = status_mod.run(path=path, update_marker=not peek, validation_cross_refs=not peek)
    except Exception as exc:
        message = status_mod._safe_exception_message(exc)
        if json_out:
            typer.echo(
                _json_error_payload(
                    command="mb status",
                    schema_name="mainbranch.status",
                    code="status_unavailable",
                    message=message,
                )
            )
        else:
            typer.echo(f"mb status: {message}", err=True)
        raise typer.Exit(1) from exc
    status_mod.qualify_commands(report, Path(path))
    if json_out:
        try:
            typer.echo(_json_payload(report, command="mb status", schema_name="mainbranch.status"))
        except TypeError as exc:
            typer.echo(
                _json_error_payload(
                    command="mb status",
                    schema_name="mainbranch.status",
                    code="status_json_serialization_failed",
                    message=status_mod._safe_exception_message(exc),
                )
            )
            raise typer.Exit(1) from exc
    else:
        status_mod.render_human(report, verbose=verbose, no_color=no_color)


@app.command("start")
def start_cmd(
    repo: str = typer.Option(
        ".",
        "--repo",
        help="Business repo to hand off to the configured runtime.",
    ),
    launch: bool = typer.Option(
        False,
        "--launch",
        help="Launch Claude Code after readiness checks pass. Cannot be combined with --json.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Check runtime handoff readiness and print or launch the Claude Code command."""

    def read_report(*, launching: bool) -> dict[str, Any]:
        if launching:
            # The guard names a file that could not be read; a launch error
            # (claude not executable) is not one, so a launch is left as it was.
            return start_mod.run(repo=repo, launch=True)
        # A connect file it cannot read is named, not a traceback (#1129).
        return _unreadable_guard(
            repo,
            command="mb start",
            schema_name="mainbranch.start.result",
            json_out=json_out,
            read=lambda: start_mod.run(repo=repo, launch=False),
        )

    if json_out and launch:
        report = read_report(launching=False)
        message = "`--json` cannot be combined with `--launch`; run without `--json` to launch."
        report["ok"] = False
        report["errors"] = [message]
        report["launch"]["requested"] = True
        report["launch"]["safe"] = False
        report["launch"]["attempted"] = False
        report["launch"]["blocked_reason"] = message
        status_mod.qualify_start_commands(report, Path(repo).expanduser())
        typer.echo(_json_payload(report, command="mb start", schema_name="mainbranch.start.result"))
        raise typer.Exit(2)

    report = read_report(launching=launch)
    status_mod.qualify_start_commands(report, Path(repo).expanduser())
    if json_out:
        typer.echo(_json_payload(report, command="mb start", schema_name="mainbranch.start.result"))
    else:
        start_mod.render_human(report)
    raise typer.Exit(0 if report["ok"] else 1)


@books_app.command("check")
def books_check_cmd(
    repo: str = typer.Argument(".", help="Business repo to check."),
    validate_fixture: bool = typer.Option(
        False,
        "--fixture/--no-fixture",
        help=(
            "Validate a fake hledger journal fixture. Uses the bundled "
            "sample unless --fixture-path is given."
        ),
    ),
    fixture_path: str = typer.Option(
        "",
        "--fixture-path",
        help="Path to a fake hledger journal fixture to validate.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Check books safety: policy file, vault ignore rules, unsafe paths."""
    report = books_mod.run(
        repo=repo,
        validate_fixture=validate_fixture or bool(fixture_path),
        fixture=fixture_path or None,
    )
    books_mod.add_check_next_step(report)
    if json_out:
        typer.echo(
            _json_payload(
                report,
                command="mb books check",
                schema_name="mainbranch.books.check.result",
            )
        )
    else:
        books_mod.render_human(report)
    raise typer.Exit(0 if report["ok"] else 1)


@books_app.command("status")
def books_status_cmd(
    repo: str = typer.Argument(".", help="Business repo to inspect."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Show hledger/private-books-vault setup and storage health."""
    report = books_mod.status(repo=repo)
    if json_out:
        typer.echo(
            _json_payload(
                report,
                command="mb books status",
                schema_name="mainbranch.books.status.result",
            )
        )
    else:
        books_mod.render_status(report)
    raise typer.Exit(0 if report["ok"] else 1)


@books_app.command("doctor")
def books_doctor_cmd(
    repo: str = typer.Argument(".", help="Business repo to inspect."),
    plan: bool = typer.Option(
        False,
        "--plan",
        help="Print a non-mutating repair plan. Required; apply is not implemented.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
    books_repo: str = typer.Option("", "--repo", help="Books repo to inspect."),
    doctor_timeout: int = typer.Option(
        600, "--doctor-timeout", help="Declared doctor timeout in seconds."
    ),
) -> None:
    """Plan safe books setup repairs without touching real ledger contents."""
    from mb import books_repo as books_repo_mod

    if books_repo and plan:
        typer.echo("mb books doctor: choose --repo or --plan", err=True)
        raise typer.Exit(2)
    if doctor_timeout < 1 or (doctor_timeout != 600 and not books_repo):
        typer.echo(
            "mb books doctor: --doctor-timeout requires --repo and a positive number", err=True
        )
        raise typer.Exit(2)
    if not plan and not books_repo:
        policy = Path(repo) / "core/finance/books.md"
        if policy.is_file():
            fm, _ = books_mod._read_frontmatter(policy)
            configured = fm.get("books_repo") or fm.get("vault_location")
            if isinstance(configured, str) and configured.strip():
                candidate = Path(configured.strip()).expanduser()
                books_repo = str(candidate if candidate.is_absolute() else Path(repo) / candidate)
    if books_repo:
        target = Path(books_repo).expanduser()
        if not target.is_dir():
            typer.echo("mb books doctor: books repo is unavailable", err=True)
            raise typer.Exit(2)
        report = books_repo_mod.inspect(target.resolve(), doctor_timeout)
        if json_out:
            typer.echo(
                _json_payload(
                    report,
                    command="mb books doctor --repo",
                    schema_name="mainbranch.books.doctor.repo.result",
                )
            )
        else:
            books_repo_mod.render(report)
        raise typer.Exit(0 if report["ok"] else 1)
    if not plan:
        message = "mb books doctor: --plan is required; apply is not implemented"
        if json_out:
            typer.echo(
                _json_payload(
                    {
                        "ok": False,
                        "state": "error",
                        "summary": message,
                        "errors": [message],
                        "safe_to_share": True,
                    },
                    command="mb books doctor",
                    schema_name="mainbranch.books.doctor.plan.result",
                )
            )
        else:
            typer.echo(message, err=True)
        raise typer.Exit(2)

    report = books_mod.doctor_plan(repo=repo)
    if json_out:
        typer.echo(
            _json_payload(
                report,
                command="mb books doctor --plan",
                schema_name="mainbranch.books.doctor.plan.result",
            )
        )
    else:
        books_mod.render_doctor_plan(report)
    raise typer.Exit(0)


@books_app.command("exposure")
def books_exposure_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo to inspect."),
    bet: str = typer.Option("", "--bet", help="Repo-relative bet file to check."),
    active: bool = typer.Option(False, "--active", help="Check all active bets."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Check privacy-bounded hledger exposure totals for bet anchors."""
    if bool(bet) == active:
        message = "mb books exposure: choose exactly one of --bet or --active"
        payload = {
            "ok": False,
            "state": "error",
            "schema_version": books_mod.BOOKS_EXPOSURE_SCHEMA,
            "safe_to_share": True,
            "summary": message,
            "exposures": [],
            "errors": [message],
            "warnings": [],
            "findings": [],
        }
        if json_out:
            typer.echo(
                _json_payload(
                    payload,
                    command="mb books exposure",
                    schema_name="mainbranch.books.exposure.result",
                )
            )
        else:
            typer.echo(message, err=True)
        raise typer.Exit(2)

    report = books_mod.exposure(repo=repo, bet=bet or None, active=active)
    if json_out:
        typer.echo(
            _json_payload(
                report,
                command="mb books exposure",
                schema_name="mainbranch.books.exposure.result",
            )
        )
    else:
        books_mod.render_exposure(report)
    raise typer.Exit(0 if report["ok"] else 1)


@books_report_app.command("monthly")
def books_report_monthly_cmd(
    sample: bool = typer.Option(
        False,
        "--sample",
        help="Use the fake packaged sample journal. Required in this release.",
    ),
    month: str = typer.Option("", "--month", help="Report month as YYYY-MM."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Generate a sample monthly books report through hledger."""
    month = month.strip()
    command_parts = ["mb books report monthly"]
    if sample:
        command_parts.append("--sample")
    if month:
        command_parts.extend(["--month", month])
    command = " ".join(command_parts)
    if not sample:
        message = (
            "mb books report monthly: only --sample reports are implemented; "
            "private books reporting is out of scope for this release"
        )
        payload = books_mod.sample_monthly_rejection(
            month=month,
            finding_id="sample-required",
            title="Sample flag required",
            message=message,
            repair=(
                "Run `mb books report monthly --sample --month 2026-01` to view fake sample data."
            ),
        )
        if json_out:
            typer.echo(
                _json_payload(
                    payload,
                    command=command,
                    schema_name="mainbranch.books.report.v1",
                )
            )
        else:
            typer.echo(message, err=True)
        raise typer.Exit(2)

    if not month:
        message = "mb books report monthly: --month is required; use YYYY-MM, for example 2026-01"
        payload = books_mod.sample_monthly_rejection(
            month=month,
            finding_id="month-required",
            title="Report month required",
            message=message,
            repair="Run `mb books report monthly --sample --month 2026-01`.",
        )
        if json_out:
            typer.echo(
                _json_payload(
                    payload,
                    command=command,
                    schema_name="mainbranch.books.report.v1",
                )
            )
        else:
            books_mod.render_sample_monthly_report(payload)
        raise typer.Exit(2)

    try:
        report = books_mod.sample_monthly_report(month)
    except ValueError as exc:
        message = f"mb books report monthly: {exc}"
        payload = books_mod.sample_monthly_rejection(
            month=month,
            finding_id="month-invalid",
            title="Report month invalid",
            message=message,
            repair="Use YYYY-MM with a real calendar month, for example 2026-01.",
        )
        if json_out:
            typer.echo(
                _json_payload(
                    payload,
                    command=command,
                    schema_name="mainbranch.books.report.v1",
                )
            )
        else:
            books_mod.render_sample_monthly_report(payload)
        raise typer.Exit(2) from exc

    if json_out:
        typer.echo(
            _json_payload(
                report,
                command=command,
                schema_name="mainbranch.books.report.v1",
            )
        )
    else:
        books_mod.render_sample_monthly_report(report)
    raise typer.Exit(0 if report["ok"] else 1)


@ads_meta_app.command("summary")
def ads_meta_summary_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo with Meta readiness metadata."),
    window: str = typer.Option("7d", "--window", help="Recent bounded window, such as 7d."),
    since: str = typer.Option("", "--since", help="Start date as YYYY-MM-DD."),
    until: str = typer.Option("", "--until", help="End date as YYYY-MM-DD."),
    include_campaign_names: bool = typer.Option(
        False,
        "--include-campaign-names",
        help="Include campaign names for this run only.",
    ),
    include_exact_spend: bool = typer.Option(
        False,
        "--include-exact-spend",
        help="Include exact spend for this run only.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Pull a compact read-only Meta Ads account summary."""
    command_parts = ["mb ads meta summary"]
    if window:
        command_parts.extend(["--window", window])
    if since:
        command_parts.extend(["--since", since])
    if until:
        command_parts.extend(["--until", until])
    if include_campaign_names:
        command_parts.append("--include-campaign-names")
    if include_exact_spend:
        command_parts.append("--include-exact-spend")
    command = " ".join(command_parts)
    try:
        result = ads_mod.meta_summary(
            repo=repo,
            window=window,
            since=since,
            until=until,
            include_campaign_names=include_campaign_names,
            include_exact_spend=include_exact_spend,
        )
    except ads_mod.AdsSummaryError as exc:
        message = f"mb ads meta summary: {exc}"
        payload = {
            "ok": False,
            "schema_version": ads_mod.SUMMARY_SCHEMA_VERSION,
            "safe_to_share": False,
            "provider": "meta",
            "command": "mb ads meta summary",
            "state": "invalid_arguments",
            "summary": message,
            "errors": [message],
            "actions": [],
        }
        if json_out:
            typer.echo(
                _json_payload(
                    payload,
                    command=command,
                    schema_name="mainbranch.ads.meta.summary.v1",
                )
            )
        else:
            typer.echo(message, err=True)
        raise typer.Exit(2) from exc

    if json_out:
        typer.echo(
            _json_payload(
                result,
                command=command,
                schema_name="mainbranch.ads.meta.summary.v1",
            )
        )
    else:
        ads_mod.render_meta_summary_human(result)
    raise typer.Exit(0 if result["ok"] else 1)


@site_app.command("check")
def site_check_cmd(
    site_repo: str = typer.Argument(".", help="Site repo or built static site to inspect."),
    business_repo: str = typer.Option(
        "",
        "--business-repo",
        "--repo",
        help="Business repo with offer and provider metadata.",
    ),
    site: str = typer.Option(
        "",
        "--site",
        help="Check one site from the repo's .mainbranch/repo.json sites list.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Check paid-traffic measurement readiness without mutating provider accounts."""
    try:
        result = site_mod.check(site_repo, business_repo=business_repo or None, site_slug=site)
    except site_mod.UnknownSiteError as exc:
        typer.echo(f"mb site check: {exc}", err=True)
        raise typer.Exit(2) from exc
    if json_out:
        typer.echo(json.dumps(result, indent=2))
    else:
        site_mod.render_check(result)
    raise typer.Exit(0 if result["ok"] else 1)


def _fleet_config_exit(
    command: str, exc: fleet_mod.FleetConfigError, json_out: bool, error: str | None = None
) -> NoReturn:
    message = str(exc) if error is None else error
    if json_out:
        typer.echo(
            json.dumps(
                envelope(
                    {"ok": False, "errors": [message], "actions": ["edit the hub list"]},
                    command=command,
                    schema_name=f"mainbranch.{command.replace('mb ', '').replace(' ', '_')}",
                ),
                indent=2,
            )
        )
    else:
        typer.echo(f"{command}: {message}", err=True)
    raise typer.Exit(2) from exc


@fleet_app.command("refresh")
def fleet_refresh_cmd(
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Read every hub, child repo and site, then cache one snapshot. Read-only."""
    try:
        result = fleet_mod.refresh()
    except fleet_mod.FleetConfigError as exc:
        _fleet_config_exit("mb fleet refresh", exc, json_out)
    if json_out:
        typer.echo(
            json.dumps(
                envelope(
                    result, command="mb fleet refresh", schema_name="mainbranch.fleet_refresh"
                ),
                indent=2,
            )
        )
    else:
        fleet_mod.render_refresh(result)
    raise typer.Exit(0 if result["ok"] else 1)


@fleet_app.command("status")
def fleet_status_cmd(
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Show the cached fleet snapshot: one row per site. Never reads the network."""
    result = fleet_mod.status()
    if json_out:
        typer.echo(
            json.dumps(
                envelope(result, command="mb fleet status", schema_name="mainbranch.fleet_status"),
                indent=2,
            )
        )
    else:
        fleet_mod.render_status(result)
    raise typer.Exit(0 if result["ok"] else 1)


@fleet_app.command("checkin")
def fleet_checkin_cmd(
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
    hub: str = typer.Option("", "--hub", help="Check in on one hub from the hub list."),
    timeout: int = typer.Option(
        fleet_checkin_mod.DEFAULT_TIMEOUT_SECONDS,
        "--timeout",
        min=1,
        help="Seconds to wait for each business before marking it unavailable.",
    ),
) -> None:
    """One read-only card per business: loop, bets, exposure, checkpoint, GitHub, sites."""
    try:
        result, code = fleet_checkin_mod.checkin(hub=hub, timeout=timeout)
    except fleet_mod.FleetConfigError as exc:
        _fleet_config_exit(
            "mb fleet checkin", exc, json_out, fleet_checkin_mod.scrub_home(str(exc))
        )
    if json_out:
        typer.echo(
            _json_payload(
                result, command="mb fleet checkin", schema_name="mainbranch.fleet_checkin"
            )
        )
    else:
        fleet_checkin_mod.render_text(result)
    raise typer.Exit(code)


@fleet_hubs_app.command("list")
def fleet_hubs_list_cmd(
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """List the hubs in the user-level fleet.toml."""
    try:
        result = fleet_mod.hubs_list()
    except fleet_mod.FleetConfigError as exc:
        _fleet_config_exit("mb fleet hubs list", exc, json_out)
    if json_out:
        typer.echo(
            json.dumps(
                envelope(result, command="mb fleet hubs list", schema_name="mainbranch.fleet_hubs"),
                indent=2,
            )
        )
    else:
        fleet_mod.render_hubs(result)
    raise typer.Exit(0)


@launch_app.command("check")
def launch_check_cmd(
    site_repo: str = typer.Argument(".", help="Site/app repo to inspect."),
    business_repo: str = typer.Option(
        "",
        "--business-repo",
        "--repo",
        help="Business repo with offer and provider metadata.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Summarize launch readiness from local files without provider mutation."""
    result = launch_mod.check(site_repo, business_repo=business_repo or None)
    if json_out:
        typer.echo(json.dumps(result, indent=2))
    else:
        launch_mod.render_check(result)
    raise typer.Exit(0 if result["ok"] else 1)


@image_app.command("smoke-openai")
def image_smoke_openai_cmd(
    repo: str = typer.Option(
        ".",
        "--repo",
        help="Business repo where the fake push-local image-index.md should be written.",
    ),
    push_slug: str = typer.Option(
        image_rail_mod.DEFAULT_PUSH_SLUG,
        "--push-slug",
        help="Fake push slug for the fixture-safe smoke record.",
    ),
    docs_checked: str = typer.Option(
        "",
        "--docs-checked",
        help="Provider docs checked date. Defaults to today in UTC.",
    ),
    media_root: str = typer.Option(
        ".mb/media",
        "--media-root",
        help=(
            "Private media storage root for the review board and any approved "
            "9-candidate --generate batch binaries."
        ),
    ),
    generate: bool = typer.Option(
        False,
        "--generate",
        help="Call OpenAI only when local credentials exist and the operator approved generation.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Smoke the narrow OpenAI GPT Image 2 rail with fake fixture context."""
    result = image_rail_mod.smoke_openai(
        repo=repo,
        push_slug=push_slug,
        docs_checked=docs_checked or _today_utc(),
        media_root=media_root,
        generate=generate,
    )
    if json_out:
        typer.echo(
            _json_payload(
                result,
                command="image smoke-openai",
                schema_name="mainbranch.image.smoke_openai.v1",
            )
        )
    elif result["state"] == "generated":
        typer.echo("OpenAI image rail smoke generated a fixture-safe asset.")
        typer.echo(f"record: {result['record_path']}")
        typer.echo(f"review board: {result['review_board_path']}")
        typer.echo(f"media:  {result['output_reference']}")
        typer.echo("binary committed: false")
    else:
        typer.echo("OpenAI image rail smoke blocked safely.")
        typer.echo(f"record: {result['record_path']}")
        typer.echo(f"review board: {result['review_board_path']}")
        typer.echo(f"reason: {result['blocker_code']}")
        typer.echo("I will not ask you to paste provider keys into chat or repo files.")
    raise typer.Exit(0)


@image_app.command("smoke-fal")
def image_smoke_fal_cmd(
    repo: str = typer.Option(
        ".",
        "--repo",
        help="Business repo where the fake push-local image-index.md should be written.",
    ),
    push_slug: str = typer.Option(
        image_rail_mod.DEFAULT_FAL_PUSH_SLUG,
        "--push-slug",
        help="Fake push slug for the fixture-safe smoke record.",
    ),
    docs_checked: str = typer.Option(
        "",
        "--docs-checked",
        help="Provider docs checked date. Defaults to today in UTC.",
    ),
    media_root: str = typer.Option(
        ".mb/media",
        "--media-root",
        help=(
            "Private media storage root for the review board and any approved "
            "9-candidate --generate batch binaries."
        ),
    ),
    generate: bool = typer.Option(
        False,
        "--generate",
        help=("Call fal.ai only when a local FAL_KEY exists and the operator approved generation."),
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Smoke the explicitly selected fal.ai FLUX rail with fake fixture context."""
    result = image_rail_mod.smoke_fal(
        repo=repo,
        push_slug=push_slug,
        docs_checked=docs_checked or _today_utc(),
        media_root=media_root,
        generate=generate,
    )
    if json_out:
        typer.echo(
            _json_payload(
                result,
                command="image smoke-fal",
                schema_name="mainbranch.image.smoke_fal.v1",
            )
        )
    elif result["state"] == "generated":
        typer.echo("fal.ai image rail smoke generated a fixture-safe asset.")
        typer.echo(f"record: {result['record_path']}")
        typer.echo(f"review board: {result['review_board_path']}")
        typer.echo(f"media:  {result['output_reference']}")
        typer.echo("binary committed: false")
    else:
        typer.echo("fal.ai image rail smoke blocked safely.")
        typer.echo(f"record: {result['record_path']}")
        typer.echo(f"review board: {result['review_board_path']}")
        typer.echo(f"reason: {result['blocker_code']}")
        typer.echo("I will not ask you to paste provider keys into chat or repo files.")
    raise typer.Exit(0)


def _dashboard_result(
    action: Callable[..., dict[str, Any]],
    *,
    repo: str,
    output: str | None,
    command: str,
    json_out: bool,
) -> dict[str, Any]:
    """Run a dashboard write; an unsafe output path is named, not a traceback."""
    try:
        return action(repo=repo, output=output)
    except dashboard_mod.DashboardOutputError as exc:
        if json_out:
            typer.echo(
                _json_error_payload(
                    command=command,
                    schema_name="mainbranch.dashboard.v1",
                    code="unsafe_output_path",
                    message=str(exc),
                )
            )
        else:
            typer.echo(f"{command}: {exc}", err=True)
        raise typer.Exit(1) from exc


@dashboard_app.command("build")
def dashboard_build_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo to visualize."),
    output: str = typer.Option(
        "",
        "--output",
        "-o",
        help="Dashboard HTML output path. Defaults to .mb/dashboard/index.html in the repo.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Build a local read-only dashboard HTML file."""
    result = _dashboard_result(
        dashboard_mod.build,
        repo=repo,
        output=output or None,
        command="mb dashboard build",
        json_out=json_out,
    )
    if json_out:
        typer.echo(
            _json_payload(
                result,
                command="mb dashboard build",
                schema_name="mainbranch.dashboard.v1",
            )
        )
    else:
        typer.echo("Built local read-only Main Branch dashboard.")
        typer.echo(f"output: {result['output']['path']}")
        typer.echo("generated file is local output; do not commit it unless explicitly approved.")
    raise typer.Exit(0)


@dashboard_app.command("open")
def dashboard_open_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo to visualize."),
    output: str = typer.Option(
        "",
        "--output",
        "-o",
        help="Dashboard HTML output path. Defaults to .mb/dashboard/index.html in the repo.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Build and open the local read-only dashboard in the default browser."""
    result = _dashboard_result(
        dashboard_mod.open_dashboard,
        repo=repo,
        output=output or None,
        command="mb dashboard open",
        json_out=json_out,
    )
    if json_out:
        typer.echo(
            _json_payload(
                result,
                command="mb dashboard open",
                schema_name="mainbranch.dashboard.v1",
            )
        )
    else:
        typer.echo("Opened local read-only Main Branch dashboard.")
        typer.echo(f"output: {result['output']['path']}")
    raise typer.Exit(0)


@app.command("validate")
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


@app.command("graph")
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


@suggest_app.command("links")
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


@app.command("similar-bets")
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


@app.command("think")
def think_cmd(
    topic: str = typer.Argument(..., help="Topic to think about."),
) -> None:
    """Print the /mb-think invocation hint (run inside Claude Code for full flow)."""
    think_mod.run(topic=topic)


@app.command("resolve")
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


@app.command("educational")
def educational_cmd(
    topic: str = typer.Argument(..., help="Educational topic slug."),
) -> None:
    """Print a beginner education topic for Main Branch rails and defaults."""
    educational_mod.run(topic=topic)


@app.command("update")
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


@app.command("checkpoint")
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


@migrate_app.callback()
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


@migrate_app.command("campaigns")
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


@migrate_app.command("status")
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


@skill_app.command("path")
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


@skill_app.command("list")
def skill_list_cmd() -> None:
    """List bundled skills."""
    from mb.resolve import bundled_skills

    for s in bundled_skills():
        typer.echo(s)


@skill_app.command("validate")
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


@skill_app.command("link")
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


@skill_app.command("repair")
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


# --- mb google: typed read-only reads (#1004) ---------------------------------


def _google_read_exit(
    command: str,
    schema_name: str,
    result: dict[str, Any],
    code: int,
    json_out: bool,
    out: Any = None,
) -> NoReturn:
    """Print one `mb google` result and exit. Failures also go to stderr.

    With ``out`` (a checked ``--out`` target) a successful result goes to that
    private file and only a short summary is printed.
    """
    from mb import google_out as google_out_mod
    from mb import google_reads as google_reads_mod

    if out is not None and not code:
        try:
            leftover = google_out_mod.write_out(
                out, _json_payload(result, command=command, schema_name=schema_name) + "\n"
            )
        except google_out_mod.OutWriteError as exc:
            if exc.existing_temp:
                detail = (
                    f"{google_out_mod.show_temp(exc.existing_temp)} is already there (an earlier "
                    "or concurrent run); it was left as it is. Remove it and run again."
                )
            elif exc.leftover_temp:
                detail = (
                    f"the temporary file {google_out_mod.show_temp(exc.leftover_temp)} "
                    "could not be removed and is still there; remove it yourself."
                )
            else:
                detail = "nothing was left behind."
            reason = f"the answer was read but the --out file could not be written; {detail}"
            if json_out:
                failed, _ = google_reads_mod.failure_result(
                    google_reads_mod.ReadFailure("out_write_failed", reason)
                )
                typer.echo(_json_payload(failed, command=command, schema_name=schema_name))
            typer.echo(f"{command}: {reason} (out_write_failed)", err=True)
            raise typer.Exit(1) from None
        info = google_out_mod.summary(command, out, result, leftover)
        if json_out:
            typer.echo(_json_payload(info, command=command, schema_name=google_out_mod.SCHEMA_OUT))
        else:
            for line in google_out_mod.render_summary(info):
                typer.echo(line)
        raise typer.Exit(0)
    if json_out:
        typer.echo(_json_payload(result, command=command, schema_name=schema_name))
    if code:
        google_reads_mod.render_failure(command, result, lambda line: typer.echo(line, err=True))
    elif not json_out:
        renderers = {
            google_reads_mod.SCHEMA_SC_QUERY: google_reads_mod.render_sc_query,
            google_reads_mod.SCHEMA_SC_SITEMAPS: google_reads_mod.render_sc_sitemaps,
            google_reads_mod.SCHEMA_SC_INSPECT: google_reads_mod.render_sc_inspect,
            google_reads_mod.SCHEMA_GA4_REPORT: google_reads_mod.render_ga4_report,
        }
        for line in renderers[schema_name](result):
            typer.echo(line)
    raise typer.Exit(code)


def _google_out_target(
    command: str, schema_name: str, out: str | None, force: bool, json_out: bool
) -> Any:
    """Judge ``--out`` before any read; exit 2 with a stable rule when it is refused."""
    from mb import google_out as google_out_mod
    from mb import google_reads as google_reads_mod

    try:
        if out is None:
            if force:
                raise google_reads_mod.ReadRefusal(
                    "out_force_without_out", "--force only goes with --out; nothing was read."
                )
            return None
        return google_out_mod.check_out(out, force=force)
    except google_reads_mod.ReadRefusal as exc:
        result, code = google_reads_mod.failure_result(exc)
        _google_read_exit(command, schema_name, result, code, json_out)


GOOGLE_OUT_OPTION = typer.Option(
    None,
    "--out",
    help=(
        "Write the JSON result to this new private file (mode 0600) and print a short "
        "summary. Refused inside a git checkout unless git ignores both the file and its "
        "temporary file (.NAME.mb-out.tmp). Safe places: a folder outside the repo, or "
        ".mb/private/pulls/."
    ),
)
GOOGLE_FORCE_OPTION = typer.Option(False, "--force", help="With --out: replace an existing file.")


GOOGLE_SC_DIMENSIONS_OPTION = typer.Option(
    [],
    "--dimensions",
    help="Group by: query, page, date, country, device, searchAppearance (comma-separated).",
)
GOOGLE_SC_FILTER_OPTION = typer.Option(
    [],
    "--filter",
    help=("dimension:operator:expression, e.g. query:contains:shoes (repeatable; all must match)."),
)
GOOGLE_GA4_METRICS_OPTION = typer.Option(
    ..., "--metrics", help="Metric names, e.g. activeUsers,sessions (comma-separated)."
)
GOOGLE_GA4_DIMENSIONS_OPTION = typer.Option(
    [], "--dimensions", help="Dimension names, e.g. date,sessionDefaultChannelGroup."
)


@google_sc_app.command("query")
@_no_secret_traceback
def google_sc_query_cmd(
    start: str = typer.Option(..., "--start", help="First day, YYYY-MM-DD (Pacific Time)."),
    end: str = typer.Option(..., "--end", help="Last day, YYYY-MM-DD (Pacific Time)."),
    dimensions: list[str] = GOOGLE_SC_DIMENSIONS_OPTION,
    search_type: str = typer.Option(
        "web", "--type", help="web, image, video, news, discover or googleNews."
    ),
    filters: list[str] = GOOGLE_SC_FILTER_OPTION,
    row_limit: int = typer.Option(1000, "--row-limit", help="Rows to return, 1-25,000."),
    start_row: int = typer.Option(0, "--start-row", help="Zero-based first row, for paging."),
    fresh: bool = typer.Option(
        False, "--fresh", help="Include fresh, not yet final data (dataState: all)."
    ),
    repo: str = typer.Option(".", "--repo", help="Business repo with the Google sign-in."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
    out: str | None = GOOGLE_OUT_OPTION,
    force: bool = GOOGLE_FORCE_OPTION,
) -> None:
    """Search performance for the recorded site (searchAnalytics.query, read-only)."""
    from mb import google_reads as google_reads_mod

    target = _google_out_target(
        google_reads_mod.SC_QUERY_COMMAND, google_reads_mod.SCHEMA_SC_QUERY, out, force, json_out
    )
    result, code = google_reads_mod.sc_query(
        repo,
        start=start,
        end=end,
        dimensions=dimensions,
        search_type=search_type,
        filters=filters,
        row_limit=row_limit,
        start_row=start_row,
        fresh=fresh,
    )
    _google_read_exit(
        google_reads_mod.SC_QUERY_COMMAND,
        google_reads_mod.SCHEMA_SC_QUERY,
        result,
        code,
        json_out,
        target,
    )


@google_sc_sitemaps_app.command("list")
@_no_secret_traceback
def google_sc_sitemaps_list_cmd(
    sitemap_index: str = typer.Option(
        "", "--sitemap-index", help="List the sitemaps inside this sitemap index URL instead."
    ),
    repo: str = typer.Option(".", "--repo", help="Business repo with the Google sign-in."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
    out: str | None = GOOGLE_OUT_OPTION,
    force: bool = GOOGLE_FORCE_OPTION,
) -> None:
    """Sitemaps submitted for the recorded site (sitemaps.list, read-only)."""
    from mb import google_reads as google_reads_mod

    target = _google_out_target(
        google_reads_mod.SC_SITEMAPS_COMMAND,
        google_reads_mod.SCHEMA_SC_SITEMAPS,
        out,
        force,
        json_out,
    )
    result, code = google_reads_mod.sc_sitemaps_list(repo, sitemap_index=sitemap_index)
    _google_read_exit(
        google_reads_mod.SC_SITEMAPS_COMMAND,
        google_reads_mod.SCHEMA_SC_SITEMAPS,
        result,
        code,
        json_out,
        target,
    )


@google_sc_app.command("inspect")
@_no_secret_traceback
def google_sc_inspect_cmd(
    url: str = typer.Option(
        ..., "--url", help="A page of the recorded site, e.g. https://www.example.com/page."
    ),
    repo: str = typer.Option(".", "--repo", help="Business repo with the Google sign-in."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
    out: str | None = GOOGLE_OUT_OPTION,
    force: bool = GOOGLE_FORCE_OPTION,
) -> None:
    """Index status of one URL of the recorded site (urlInspection.index.inspect, read-only).

    Shows the version in Google's index only; there is no live test. Quota: 2,000
    inspections a day and 600 a minute per site.
    """
    from mb import google_reads as google_reads_mod

    target = _google_out_target(
        google_reads_mod.SC_INSPECT_COMMAND,
        google_reads_mod.SCHEMA_SC_INSPECT,
        out,
        force,
        json_out,
    )
    result, code = google_reads_mod.sc_inspect(repo, url=url)
    _google_read_exit(
        google_reads_mod.SC_INSPECT_COMMAND,
        google_reads_mod.SCHEMA_SC_INSPECT,
        result,
        code,
        json_out,
        target,
    )


@google_ga4_app.command("report")
@_no_secret_traceback
def google_ga4_report_cmd(
    metrics: list[str] = GOOGLE_GA4_METRICS_OPTION,
    start: str = typer.Option(..., "--start", help="First day, YYYY-MM-DD."),
    end: str = typer.Option(..., "--end", help="Last day, YYYY-MM-DD."),
    dimensions: list[str] = GOOGLE_GA4_DIMENSIONS_OPTION,
    limit: int = typer.Option(1000, "--limit", help="Rows to return, 1-250,000."),
    offset: int = typer.Option(0, "--offset", help="Zero-based first row, for paging."),
    order_by: str = typer.Option(
        "", "--order-by", help="A requested metric or dimension, NAME or NAME:desc."
    ),
    repo: str = typer.Option(".", "--repo", help="Business repo with the Google sign-in."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
    out: str | None = GOOGLE_OUT_OPTION,
    force: bool = GOOGLE_FORCE_OPTION,
) -> None:
    """A GA4 report for the recorded property (runReport, read-only)."""
    from mb import google_reads as google_reads_mod

    target = _google_out_target(
        google_reads_mod.GA4_REPORT_COMMAND,
        google_reads_mod.SCHEMA_GA4_REPORT,
        out,
        force,
        json_out,
    )
    result, code = google_reads_mod.ga4_report(
        repo,
        start=start,
        end=end,
        metrics=metrics,
        dimensions=dimensions,
        limit=limit,
        offset=offset,
        order_by=order_by,
    )
    _google_read_exit(
        google_reads_mod.GA4_REPORT_COMMAND,
        google_reads_mod.SCHEMA_GA4_REPORT,
        result,
        code,
        json_out,
        target,
    )


def _entry() -> None:
    """Defensive entrypoint used by ``python -m mb`` and tests."""
    try:
        app()
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"mb: error: {exc}", err=True)
        sys.exit(2)
