"""Refresh the small managed entry rule in a business repo's CLAUDE.md."""

from __future__ import annotations

from pathlib import Path

from mb.durable import atomic_write_text
from mb.init import _read_template

BEGIN = "<!-- mainbranch:entry-rules:begin -->"
END = "<!-- mainbranch:entry-rules:end -->"
_OLD_ANCHOR = "## First-run setup intent"
_OLD_SIGNATURE = "Main Branch CLI facts are the source of truth for repo health"
APPEND_NOTICE = (
    "CLAUDE.md has no managed entry rule markers or known 0.6.9 anchor; "
    "mb update can append the marked entry rules after the operator's text with approval."
)


def _current_block() -> str:
    template = _read_template("CLAUDE.md.tmpl")
    start = template.index(BEGIN)
    end = template.index(END, start) + len(END)
    return template[start:end]


def plan(repo: Path) -> tuple[str | None, str | None]:
    """Return the proposed whole file and a refusal, if its boundaries are broken.

    A 0.6.9 file has no markers. Insert beside its known operating contract;
    append to other hand-edited files. Other text is kept.
    """
    path = repo / "CLAUDE.md"
    if not path.is_file():
        return None, None
    with path.open("r", encoding="utf-8", newline="") as handle:
        existing = handle.read()
    begins, ends = existing.count(BEGIN), existing.count(END)
    if begins != ends or begins > 1 or (begins and existing.index(BEGIN) > existing.index(END)):
        return (
            None,
            "CLAUDE.md entry rule markers are incomplete; restore both markers before refresh.",
        )
    crlf_count = existing.count("\r\n")
    newline = "\r\n" if crlf_count > existing.count("\n") - crlf_count else "\n"
    block = _current_block().replace("\n", newline)
    if begins:
        start = existing.index(BEGIN)
        end = existing.index(END, start) + len(END)
        updated = existing[:start] + block + existing[end:]
    elif _OLD_SIGNATURE in existing and _OLD_ANCHOR in existing:
        start = existing.index(_OLD_ANCHOR)
        updated = existing[:start] + block + newline * 2 + existing[start:]
    else:
        updated = existing + (newline if existing.endswith("\n") else newline * 2) + block + newline
        return updated, APPEND_NOTICE
    return (updated if updated != existing else None), None


def apply(repo: Path, content: str) -> None:
    atomic_write_text(repo / "CLAUDE.md", content, newline="")
