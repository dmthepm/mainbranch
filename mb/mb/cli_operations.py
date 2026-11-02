"""Command implementations extracted from :mod:`mb.cli`."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, NoReturn

import typer

from mb import ads as ads_mod
from mb import dashboard as dashboard_mod
from mb import fleet as fleet_mod
from mb import fleet_checkin as fleet_checkin_mod
from mb import image_rail as image_rail_mod
from mb import launch as launch_mod
from mb import site as site_mod
from mb.cli_common import (
    _json_error_payload,
    _json_payload,
    _today_utc,
)
from mb.json_result import envelope


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
