"""Command implementations extracted from :mod:`mb.cli`."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, NoReturn

import typer

from mb import automation as automation_mod
from mb import canary as canary_mod
from mb import feedback as feedback_mod
from mb import leads as leads_mod
from mb import ledger as ledger_mod
from mb import production as production_mod
from mb import pulse as pulse_mod
from mb import spine as spine_mod
from mb.cli_common import (
    _json_error_payload,
    _json_payload,
)

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


FEEDBACK_WORDS_ARGUMENT = typer.Argument(
    None,
    help=(
        "What went wrong, in plain words. Or `rollup` / `list` / `clear` to read or "
        "prune the local feedback file."
    ),
)


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
