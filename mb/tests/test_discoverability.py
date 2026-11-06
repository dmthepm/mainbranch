"""Every CLI surface must be reachable from each first-class runtime rail.

Operators never browse the CLI. A surface is discoverable on a rail when
that rail's own teaching corpus names it: for Claude Code, the bundled
skills and docs; for Codex, the generated AGENTS.md template and the
shared workflow sources its global skills render from. Python string
literals are not a discovery rail — a surface mentioned only in engine
source is invisible to operators on both runtimes.

History: the first version of this gate pooled everything into one
corpus and passed when a surface was taught on ONE rail (or merely
appeared in .py source). A full cycle of new surfaces shipped Claude-only
before the 2026-06-12 Codex audit caught it. Per-rail assertion makes
that class of asymmetry a failing test.
"""

from __future__ import annotations

from pathlib import Path

from mb.cli import app

REPO_ROOT = Path(__file__).resolve().parents[2]

# Engine-internal surfaces, exempt on BOTH rails (justify every entry).
INTERNAL_ALLOWLIST = {
    # Invoked by mb-think's educational flow through the engine, not named
    # in operator prose; covered by the educational content itself.
    "educational",
    # Engine-internal resolution helper used by skills' path-resolution
    # reference, which documents the contract rather than the command name.
    "resolve",
}

# Claude-first surfaces the Codex rail intentionally does not teach yet
# (Codex support levels: supported daily loop / read_only_planning;
# justify every entry against docs/compatibility.md).
CODEX_EXEMPT = {
    # Fixture-safe creative rails are Claude-skill territory; Codex carries
    # them as read_only_planning per docs/compatibility.md.
    "image",
    "ads",
    # `mb think` is a redirect stub pointing the operator INTO Claude Code;
    # Codex has its own Think workflow section in generated AGENTS.md.
    "think",
    # `mb library` v1 is an operator-run CLI; no workflow or generated
    # AGENTS.md teaches agents to call it until a pilot shows it earns a route.
    "library",
}

MAX_EXEMPTIONS = 6


def _cli_surfaces() -> set[str]:
    names: set[str] = set()
    for command in app.registered_commands:
        if command.name:
            names.add(command.name)
        elif command.callback is not None:
            names.add(command.callback.__name__)
    for group in app.registered_groups:
        if group.typer_instance is not None and group.typer_instance.info.name:
            names.add(str(group.typer_instance.info.name))
    return names


def _read_all(patterns: list[str]) -> str:
    chunks: list[str] = []
    for pattern in patterns:
        for path in REPO_ROOT.glob(pattern):
            if path.is_file():
                chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def _claude_corpus() -> str:
    return _read_all([".claude/skills/**/*.md", "docs/*.md"])


def _codex_corpus() -> str:
    chunks = [_read_all(["workflows/**/*.md"])]
    template = REPO_ROOT / "mb" / "mb" / "_data" / "templates" / "AGENTS.md.tmpl"
    chunks.append(template.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _unreachable(corpus: str, exempt: set[str]) -> list[str]:
    return sorted(
        name
        for name in _cli_surfaces()
        if name not in INTERNAL_ALLOWLIST and name not in exempt and f"mb {name}" not in corpus
    )


def test_every_cli_surface_is_discoverable_on_claude_rail() -> None:
    unreachable = _unreachable(_claude_corpus(), set())
    assert unreachable == [], (
        "CLI surfaces unreachable from the Claude rail (no bundled skill or "
        f"doc names them): {unreachable}. Wire each into mb-start routing or "
        "mb-help's cli-surfaces map."
    )


def test_every_cli_surface_is_discoverable_on_codex_rail() -> None:
    unreachable = _unreachable(_codex_corpus(), CODEX_EXEMPT)
    assert unreachable == [], (
        "CLI surfaces unreachable from the Codex rail (neither the shared "
        "workflow sources nor AGENTS.md.tmpl name them): "
        f"{unreachable}. Teach them at the propagation layer (workflow "
        "Routing Rules + template), or add a justified CODEX_EXEMPT entry."
    )


def test_exemption_lists_stay_small_and_justified() -> None:
    # Growing allowlists silently would gut the gate.
    assert len(INTERNAL_ALLOWLIST) + len(CODEX_EXEMPT) <= MAX_EXEMPTIONS
