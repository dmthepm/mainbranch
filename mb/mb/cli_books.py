"""Command implementations extracted from :mod:`mb.cli`."""

from __future__ import annotations

from pathlib import Path

import typer

from mb import books as books_mod
from mb.cli_common import (
    _json_payload,
)


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
