"""Main Branch engine umbrella.

Public surface: ``mb.cli:app`` (Typer entry point installed as the ``mb``
console script). Submodules implement individual subcommands so the CLI
file stays a thin dispatcher.
"""

from __future__ import annotations

__version__ = "0.6.15"

__all__ = ["__version__"]
