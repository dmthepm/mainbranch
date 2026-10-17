"""Refresh the small managed entry rule in a business repo's CLAUDE.md."""

from __future__ import annotations

from pathlib import Path

from mb.durable import atomic_write_text
from mb.init import _read_template

BEGIN = "<!-- mainbranch:entry-rules:begin -->"
END = "<!-- mainbranch:entry-rules:end -->"
_OLD_ANCHOR = "## First-run setup intent"
_OLD_SIGNATURE = "Main Branch CLI facts are the source of truth for repo health"
_OLD_REPAIR_CLAIM = (
    "Until a repair command succeeds,\n"
    "describe the repair as proposed. After applying it, tell the operator:\n"
    '"I repaired missing Main Branch start wiring in this business folder;\n'
    'restart Claude Code from this repo and try `/mb-start` again."'
)
_NEW_REPAIR_GUIDANCE = (
    "Before an apply command succeeds,\n"
    "describe the repair as a proposed step. After it succeeds, say which command\n"
    "ran, then ask the operator to restart Claude Code from this repo and try\n"
    "`/mb-start` again."
)
APPEND_NOTICE = (
    "CLAUDE.md has no managed entry rule markers or known 0.6.9 anchor; "
    "mb update can append the marked entry rules after the operator's text with approval."
)
REPAIR_NOTICE = (
    "CLAUDE.md has an edited or repeated 0.6.11 repair paragraph; "
    "mb update left that paragraph unchanged. Review it manually."
)


def _current_block() -> str:
    template = _read_template("CLAUDE.md.tmpl")
    start = template.index(BEGIN)
    end = template.index(END, start) + len(END)
    return template[start:end]


def _replace_known_repair_paragraph(content: str, newline: str) -> tuple[str, str | None]:
    template = _read_template("CLAUDE.md.tmpl")
    claim_at = template.index(_NEW_REPAIR_GUIDANCE)
    start = template.rfind("\n\n", 0, claim_at) + 2
    end = template.index("\n\n", claim_at)
    current = template[start:end].replace("\n", newline)
    old = current.replace(
        _NEW_REPAIR_GUIDANCE.replace("\n", newline),
        _OLD_REPAIR_CLAIM.replace("\n", newline),
    )
    positions: list[int] = []
    at = 0
    while (at := content.find(old, at)) != -1:
        before = at == 0 or content[max(0, at - 2 * len(newline)) : at] == newline * 2
        after_at = at + len(old)
        after = after_at == len(content) or content[after_at:].startswith(newline * 2)
        if before and after:
            positions.append(at)
        at += len(old)
    old_claim = _OLD_REPAIR_CLAIM.replace("\n", newline)
    if len(positions) == 1 and content.count(old_claim) == 1:
        at = positions[0]
        return content[:at] + current + content[at + len(old) :], None
    if old_claim in content or "Until a repair command succeeds" in content:
        return content, REPAIR_NOTICE
    return content, None


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
    notice = None
    if begins:
        start = existing.index(BEGIN)
        end = existing.index(END, start) + len(END)
        updated = existing[:start] + block + existing[end:]
    elif _OLD_SIGNATURE in existing and _OLD_ANCHOR in existing:
        start = existing.index(_OLD_ANCHOR)
        updated = existing[:start] + block + newline * 2 + existing[start:]
    else:
        updated = existing + (newline if existing.endswith("\n") else newline * 2) + block + newline
        notice = APPEND_NOTICE
    updated, repair_notice = _replace_known_repair_paragraph(updated, newline)
    return (updated if updated != existing else None), repair_notice or notice


def apply(repo: Path, content: str) -> None:
    atomic_write_text(repo / "CLAUDE.md", content, newline="")
