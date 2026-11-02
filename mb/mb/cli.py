"""Typer CLI for ``mb``.

Thin dispatcher. Each subcommand lives in its own module so we can
unit-test in isolation. The shape echoes ``companyctx`` (Typer + sub-apps)
because that's the working pattern.
"""

from __future__ import annotations

import functools
import json
import os
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any, NoReturn, TypeVar, cast

import typer
from typer.core import TyperGroup

from mb import __version__
from mb import connect as connect_mod
from mb import doctor as doctor_mod
from mb import feedback as feedback_mod
from mb import init as init_mod
from mb import issue as issue_mod
from mb import machine_doctor as machine_doctor_mod
from mb import roles as roles_mod
from mb import start as start_mod
from mb import status as status_mod
from mb import usage as usage_mod
from mb.cli_books import books_check_cmd as books_check_cmd
from mb.cli_books import books_doctor_cmd as books_doctor_cmd
from mb.cli_books import books_exposure_cmd as books_exposure_cmd
from mb.cli_books import books_report_monthly_cmd as books_report_monthly_cmd
from mb.cli_books import books_status_cmd as books_status_cmd
from mb.cli_bootstrap import FEEDBACK_WORDS_ARGUMENT as FEEDBACK_WORDS_ARGUMENT
from mb.cli_bootstrap import SPINE_GAP_OPTION as SPINE_GAP_OPTION
from mb.cli_bootstrap import SPINE_LENS_OPTION as SPINE_LENS_OPTION
from mb.cli_bootstrap import _gh_protection as _gh_protection
from mb.cli_bootstrap import automation_init_cmd as automation_init_cmd
from mb.cli_bootstrap import canary_init_cmd as canary_init_cmd
from mb.cli_bootstrap import feedback_cmd as feedback_cmd
from mb.cli_bootstrap import leads_grade_cmd as leads_grade_cmd
from mb.cli_bootstrap import ledger_init_cmd as ledger_init_cmd
from mb.cli_bootstrap import production_plan_cmd as production_plan_cmd
from mb.cli_bootstrap import pulse_init_cmd as pulse_init_cmd
from mb.cli_bootstrap import pulse_install_cmd as pulse_install_cmd
from mb.cli_bootstrap import spine_declare_cmd as spine_declare_cmd
from mb.cli_bootstrap import spine_init_cmd as spine_init_cmd
from mb.cli_bootstrap import spine_show_cmd as spine_show_cmd
from mb.cli_common import VALIDATE_PATHS_OPTION as VALIDATE_PATHS_OPTION
from mb.cli_common import _json_error_payload as _json_error_payload
from mb.cli_common import _json_payload as _json_payload
from mb.cli_common import _today_utc as _today_utc
from mb.cli_common import _unreadable_guard as _unreadable_guard
from mb.cli_onboarding import _onboard_target_path as _onboard_target_path
from mb.cli_onboarding import _render_onboard_human as _render_onboard_human
from mb.cli_onboarding import _render_onboard_intro as _render_onboard_intro
from mb.cli_onboarding import _render_onboard_status_human as _render_onboard_status_human
from mb.cli_onboarding import _render_workflow_inventory_human as _render_workflow_inventory_human
from mb.cli_onboarding import onboard_cmd as onboard_cmd
from mb.cli_onboarding import onboard_plan_cmd as onboard_plan_cmd
from mb.cli_onboarding import onboard_status_cmd as onboard_status_cmd
from mb.cli_onboarding import workflow_list_cmd as workflow_list_cmd
from mb.cli_operations import _dashboard_result as _dashboard_result
from mb.cli_operations import _fleet_config_exit as _fleet_config_exit
from mb.cli_operations import ads_meta_summary_cmd as ads_meta_summary_cmd
from mb.cli_operations import dashboard_build_cmd as dashboard_build_cmd
from mb.cli_operations import dashboard_open_cmd as dashboard_open_cmd
from mb.cli_operations import fleet_checkin_cmd as fleet_checkin_cmd
from mb.cli_operations import fleet_hubs_list_cmd as fleet_hubs_list_cmd
from mb.cli_operations import fleet_refresh_cmd as fleet_refresh_cmd
from mb.cli_operations import fleet_status_cmd as fleet_status_cmd
from mb.cli_operations import image_smoke_fal_cmd as image_smoke_fal_cmd
from mb.cli_operations import image_smoke_openai_cmd as image_smoke_openai_cmd
from mb.cli_operations import launch_check_cmd as launch_check_cmd
from mb.cli_operations import site_check_cmd as site_check_cmd
from mb.cli_repo import checkpoint_cmd as checkpoint_cmd
from mb.cli_repo import educational_cmd as educational_cmd
from mb.cli_repo import graph_cmd as graph_cmd
from mb.cli_repo import migrate_campaigns_cmd as migrate_campaigns_cmd
from mb.cli_repo import migrate_cmd as migrate_cmd
from mb.cli_repo import migrate_status_cmd as migrate_status_cmd
from mb.cli_repo import resolve_cmd as resolve_cmd
from mb.cli_repo import similar_bets_cmd as similar_bets_cmd
from mb.cli_repo import suggest_links_cmd as suggest_links_cmd
from mb.cli_repo import think_cmd as think_cmd
from mb.cli_repo import update_cmd as update_cmd
from mb.cli_repo import validate_cmd as validate_cmd
from mb.cli_skills import skill_link_cmd as skill_link_cmd
from mb.cli_skills import skill_list_cmd as skill_list_cmd
from mb.cli_skills import skill_path_cmd as skill_path_cmd
from mb.cli_skills import skill_repair_cmd as skill_repair_cmd
from mb.cli_skills import skill_validate_cmd as skill_validate_cmd
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


spine_app.command("declare")(spine_declare_cmd)


spine_app.command("init")(spine_init_cmd)


spine_app.command("show")(spine_show_cmd)


canary_app.command("init")(canary_init_cmd)


pulse_app = typer.Typer(
    name="pulse",
    help="Daily business pulse: deterministic collectors + a judgment skill.",
    no_args_is_help=True,
)
app.add_typer(pulse_app, name="pulse")


pulse_app.command("init")(pulse_init_cmd)


pulse_app.command("install")(pulse_install_cmd)


automation_app = typer.Typer(
    name="automation",
    help="Scaffold the steered-loop contract (inspectable loop/cron state).",
    no_args_is_help=True,
)
app.add_typer(automation_app, name="automation")


automation_app.command("init")(automation_init_cmd)


ledger_app = typer.Typer(
    name="ledger",
    help="Scaffold the what's-working creative ledger (KEEP/KILL on eligible CPL).",
    no_args_is_help=True,
)
app.add_typer(ledger_app, name="ledger")


ledger_app.command("init")(ledger_init_cmd)


app.command("feedback")(feedback_cmd)


leads_app = typer.Typer(
    name="leads",
    help="Grade lead eligibility and pair raw CPL with ELIGIBLE-lead CPL.",
    no_args_is_help=True,
)
app.add_typer(leads_app, name="leads")


leads_app.command("grade")(leads_grade_cmd)


production_app = typer.Typer(
    name="production",
    help="Plan the money-taking branch-protection posture (read-only).",
    no_args_is_help=True,
)
app.add_typer(production_app, name="production")


production_app.command("plan")(production_plan_cmd)


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


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"mb {__version__}")
        raise typer.Exit()


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


workflow_app.command("list")(workflow_list_cmd)


onboard_app.callback()(onboard_cmd)


onboard_app.command("status")(onboard_status_cmd)


onboard_app.command("plan")(onboard_plan_cmd)


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
        except connect_mod.CredentialBusyError as exc:
            _connect_runtime_exit("mb connect hydrate", exc, json_out=json_out)
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


books_app.command("check")(books_check_cmd)


books_app.command("status")(books_status_cmd)


books_app.command("doctor")(books_doctor_cmd)


books_app.command("exposure")(books_exposure_cmd)


books_report_app.command("monthly")(books_report_monthly_cmd)


ads_meta_app.command("summary")(ads_meta_summary_cmd)


site_app.command("check")(site_check_cmd)


fleet_app.command("refresh")(fleet_refresh_cmd)


fleet_app.command("status")(fleet_status_cmd)


fleet_app.command("checkin")(fleet_checkin_cmd)


fleet_hubs_app.command("list")(fleet_hubs_list_cmd)


launch_app.command("check")(launch_check_cmd)


image_app.command("smoke-openai")(image_smoke_openai_cmd)


image_app.command("smoke-fal")(image_smoke_fal_cmd)


dashboard_app.command("build")(dashboard_build_cmd)


dashboard_app.command("open")(dashboard_open_cmd)


app.command("validate")(validate_cmd)


app.command("graph")(graph_cmd)


suggest_app.command("links")(suggest_links_cmd)


app.command("similar-bets")(similar_bets_cmd)


app.command("think")(think_cmd)


app.command("resolve")(resolve_cmd)


app.command("educational")(educational_cmd)


app.command("update")(update_cmd)


app.command("checkpoint")(checkpoint_cmd)


migrate_app.callback()(migrate_cmd)


migrate_app.command("campaigns")(migrate_campaigns_cmd)


migrate_app.command("status")(migrate_status_cmd)


skill_app.command("path")(skill_path_cmd)


skill_app.command("list")(skill_list_cmd)


skill_app.command("validate")(skill_validate_cmd)


skill_app.command("link")(skill_link_cmd)


skill_app.command("repair")(skill_repair_cmd)


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


machine_app = typer.Typer(help="Inspect machine configuration without changing it.")
app.add_typer(machine_app, name="machine")


@machine_app.command("doctor")
def machine_doctor_cmd(json_out: bool = typer.Option(False, "--json")) -> None:
    """Check the current account's machine configuration."""
    try:
        report = machine_doctor_mod.doctor()
    except Exception:
        report = {
            "schema": "mb.machine.doctor",
            "schema_version": 1,
            "safe_to_share": False,
            "ok": False,
            "exit_code": 2,
            "scope": "self",
            "checks": [],
            "errors": [{"code": "machine.internal"}],
        }
    if json_out:
        payload = envelope(
            report, command="mb machine doctor", schema_name="mainbranch.machine.doctor.result"
        )
        payload["result_status"] = "error" if report["exit_code"] == 2 else "ok"
        typer.echo(json.dumps(payload, indent=2, default=json_default))
    else:
        typer.echo(
            "Machine doctor: scope self. No verdict: internal error."
            if report["exit_code"] == 2
            else machine_doctor_mod.human_report(report)
        )
    raise typer.Exit(report["exit_code"])


role_app = typer.Typer(help="Agent role cards: list, show, check, and the session hook.")
app.add_typer(role_app, name="role")


@role_app.command("list")
def role_list_cmd(
    repo: str = typer.Option(".", "--repo", help="Business repo."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List the role cards in core/roles/."""
    cards = roles_mod.list_cards(repo)
    if json_out:
        typer.echo(
            _json_payload(
                {"ok": all(c["valid"] for c in cards), "roles": cards},
                command="mb role list",
                schema_name="mainbranch.role.list",
            )
        )
        return
    if not cards:
        typer.echo("No role cards. Add one at core/roles/<name>.md (see docs/role-cards.md).")
        return
    for card in cards:
        mark = "ok     " if card["valid"] else "INVALID"
        typer.echo(f"{mark} {card['name']}  {card['role'] or '; '.join(card['errors'])}")


@role_app.command("show")
def role_show_cmd(
    name: str = typer.Argument(..., help="Role name, exactly as the card file is named."),
    repo: str = typer.Option(".", "--repo", help="Business repo."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show one role card. Exits 1 if it is missing or invalid."""
    card = roles_mod.load_card(repo, name)
    if json_out:
        typer.echo(
            _json_payload(
                {"ok": card["valid"], "role": card, "errors": card["errors"]},
                command="mb role show",
                schema_name="mainbranch.role.show",
            )
        )
    elif card["valid"]:
        typer.echo(f"{card['name']}: {card['role']}")
        for field in roles_mod.LIST_FIELDS:
            typer.echo(f"{field}: {', '.join(card[field]) or 'none'}")
        typer.echo(f"first_action: {card['first_action'].strip()}")
        typer.echo(f"checkpoint: {card['checkpoint']}")
    else:
        for error in card["errors"]:
            typer.echo(f"mb role show: {error}", err=True)
    raise typer.Exit(0 if card["valid"] else 1)


@role_app.command("check")
def role_check_cmd(
    name: str = typer.Argument(None, help="One role to check; default is every card."),
    repo: str = typer.Option(".", "--repo", help="Business repo."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Validate role cards. Exits 1 if any checked card is invalid."""
    report = roles_mod.check(repo, name)
    if json_out:
        typer.echo(
            _json_payload(report, command="mb role check", schema_name="mainbranch.role.check")
        )
    else:
        for result in report["cards"]:
            typer.echo(f"{'ok     ' if result['valid'] else 'INVALID'} {result['name']}")
            for error in result["errors"]:
                typer.echo(f"  - {error}")
        if not report["cards"]:
            typer.echo("No role cards.")
    raise typer.Exit(0 if report["ok"] else 1)


@role_app.command("hook")
def role_hook_cmd(
    source: str = typer.Option("startup", "--source", help="startup, resume, clear, or compact."),
) -> None:
    """SessionStart hook entry: print the selected role card, or a refusal.

    Prints nothing when the repo has no role cards. Always exits 0: a hook
    cannot block a session, so the refusal is text the agent must obey.
    """
    repo = os.environ.get("CLAUDE_PROJECT_DIR") or "."
    safe_source = source if source in roles_mod.HOOK_SOURCES else "unknown"
    try:
        text = roles_mod.hook_text(repo, safe_source)
    except Exception:
        text = roles_mod.refusal(
            "The role check hit an internal error and could not read the role card."
        )
    if text:
        typer.echo(text)
