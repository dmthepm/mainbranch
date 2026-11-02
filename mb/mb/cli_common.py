"""Shared CLI rendering and read-error helpers."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer

from mb import unreadable as unreadable_mod
from mb.json_result import envelope, json_default


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


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


VALIDATE_PATHS_OPTION = typer.Option(
    [],
    "--paths",
    help=(
        "Scope the report to repo-relative file or directory prefixes "
        "(repeatable) — validate only what you touched."
    ),
)
