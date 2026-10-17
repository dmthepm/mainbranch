"""Refresh the small managed entry rule in a business repo's CLAUDE.md."""

from __future__ import annotations

import re
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
_OLD_RUNTIME_SECTION = (
    "If `/mb-start` is not discoverable or Claude Code reports `Unknown command:\n"
    "/mb-start`, do not improvise from memory. The most common cause is that the\n"
    "Main Branch plugin is not installed or enabled — install it with\n"
    "`claude plugin marketplace add noontide-co/mainbranch` and enable it (this\n"
    "works in the Claude Desktop app and the terminal). If you need to prove the\n"
    "plugin itself loaded, use the namespaced `/mainbranch:mb-start` command. If you\n"
    "are in a cloud/web session, plugins are unavailable there — use the Claude\n"
    "Desktop app or the `claude` CLI. From this business repo, check `mb --version`,\n"
    "run `mb start --json` and `mb status --json --peek`, inspect repair options\n"
    "with `mb doctor repair --plan`, then ask before running any write/apply command\n"
    "such as `mb skill link --repo .`, `mb skill repair --repo . --apply`,\n"
    "`mb doctor repair --apply`, or `mb update`. " + _OLD_REPAIR_CLAIM
)
_OLD_GENERATED_SECTION = (
    "## First-run setup intent\n\n"
    "When the operator pastes a setup guide, bootstrap prompt, or business/folder\n"
    "description into an empty or uninitialized folder, treat it as setup intent,\n"
    "not as a document to save. Do not ask what file format to save the prompt in. First\n"
    "check `mb --version`. If `mb` is missing, stop and give the exact install step:\n"
    "`pipx install mainbranch`. If `mb` is available, inspect the setup path with\n"
    "`mb onboard --help`, then explain which folder will become the business brain\n"
    "and ask before running any command that writes files.\n\n"
    "If the operator asks for GitHub backup, sync, collaboration, or\n"
    "`mb onboard --github <owner/repo> --push`, check GitHub CLI before any setup write:\n"
    "`gh auth status` and `gh api user --jq .login`. Confirm the signed-in account\n"
    "matches the operator's expected account. GitHub is strongly recommended because\n"
    "it gives Main Branch a free cloud backup, shared history, task/proposal layer,\n"
    "and connector-friendly copy of the business brain. Main Branch can start\n"
    "locally without GitHub; GitHub is needed for sync, collaboration, and the\n"
    "GitHub-backed onboarding path.\n\n"
    "After setup, run `mb status --json --peek` and `mb start --json`. Summarize the\n"
    "outcome in business language first: folder created, business brain ready,\n"
    "baseline saved, GitHub backup connected when requested, checkpoint state, and\n"
    "next safe action. Put commands and git/GitHub details second.\n\n" + _OLD_RUNTIME_SECTION
)
_OLD_069_0610_REPAIR_CLAIM = (
    "After repairing skill wiring, tell\n"
    'the operator: "I repaired missing Main Branch start wiring in this business\n'
    'folder; restart Claude Code from this repo and try `/mb-start` again."'
)
_OLD_069_0610_GENERATED_SECTION = _OLD_GENERATED_SECTION.replace(
    _OLD_REPAIR_CLAIM, _OLD_069_0610_REPAIR_CLAIM
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


def _outside_fences(content: str, positions: list[int]) -> list[int]:
    """Keep line-start positions outside Markdown backtick and tilde fences."""
    outside: list[int] = []
    fence: tuple[str, int] | None = None
    wanted = set(positions)
    offset = 0
    for line in content.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if offset in wanted and fence is None:
            outside.append(offset)
        if marker:
            run, rest = marker.groups()
            if fence is None:
                fence = (run[0], len(run))
            elif run[0] == fence[0] and len(run) >= fence[1] and not rest.strip():
                fence = None
        offset += len(line)
    return outside


def _replace_known_repair_paragraph(content: str, newline: str) -> tuple[str, str | None]:
    targets = (
        (_OLD_GENERATED_SECTION, _OLD_REPAIR_CLAIM),
        (_OLD_069_0610_GENERATED_SECTION, _OLD_069_0610_REPAIR_CLAIM),
    )
    matches: list[tuple[int, str, str]] = []
    for section, claim in targets:
        old_section = section.replace("\n", newline)
        old_claim = claim.replace("\n", newline)
        at = 0
        while (at := content.find(old_section, at)) != -1:
            after = at + len(old_section)
            if (at == 0 or content[at - 1] == "\n") and (
                after == len(content) or content.startswith(newline, after)
            ):
                matches.append((at, old_section, old_claim))
            at += len(old_section)
    outside = _outside_fences(content, [at for at, _, _ in matches])
    if len(outside) == 1:
        start, old_section, old_claim = next(match for match in matches if match[0] == outside[0])
        at = start + old_section.index(old_claim)
        content = (
            content[:at]
            + _NEW_REPAIR_GUIDANCE.replace("\n", newline)
            + content[at + len(old_claim) :]
        )
    if any(claim.replace("\n", newline) in content for _, claim in targets) or (
        "Until a repair command succeeds" in content
    ):
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
