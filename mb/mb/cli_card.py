"""`mb card` command implementations. Registered in :mod:`mb.cli`."""

from __future__ import annotations

from pathlib import Path

import typer

from mb import card

CARD_HELP = (
    "Render a phone decision card (JPG) from a JSON spec. Needs the optional "
    "Pillow install: pip install 'mainbranch[cards]'."
)


_SPEC_ARGUMENT = typer.Argument(..., help="JSON spec: title, sub, sections, footer.")
_OUT_ARGUMENT = typer.Argument(..., help="Where to write the JPG.")


def card_render_cmd(spec: Path = _SPEC_ARGUMENT, out: Path = _OUT_ARGUMENT) -> None:
    """Render SPEC to OUT: 1320 px wide, numbered sections, lettered options, under 2 MB."""
    try:
        width, height, size = card.render(spec, out)
    except card.CardError as exc:
        typer.echo(f"mb card: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"{out} {width}x{height} {size} bytes")
