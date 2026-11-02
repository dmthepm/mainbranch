"""Ownership markers and merge rules for generated Codex repository guidance."""

from __future__ import annotations

import hashlib
import re

from mb.codex_data import AGENTS_MANAGED_BEGIN, AGENTS_MANAGED_END, AGENTS_RELATIVE_PATH


def parse_guidance_metadata(text: str) -> dict[str, str]:
    match = re.search(r"<!--\s*mainbranch:codex-guidance\s+([^>]*)-->", text)
    if not match:
        return {}
    pairs: dict[str, str] = {}
    for item in match.group(1).split():
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        pairs[key.strip()] = value.strip().strip('"')
    return pairs


def _managed_agents_block(rendered: str) -> str:
    return f"{AGENTS_MANAGED_BEGIN}\n{rendered.rstrip()}\n{AGENTS_MANAGED_END}\n"


def _managed_agents_content(text: str) -> str:
    start = text.find(AGENTS_MANAGED_BEGIN)
    if start == -1:
        return ""
    body_start = text.find("\n", start)
    if body_start == -1:
        return ""
    end = text.find(AGENTS_MANAGED_END, body_start)
    if end == -1:
        return ""
    return text[body_start + 1 : end].strip() + "\n"


_GUIDANCE_METADATA_RE = re.compile(r"<!--\s*mainbranch:codex-guidance\s+[^>]*-->")


_OWNER_LINE_RE = re.compile(r"^`@[^`\s]*`$")


AGENTS_RERUN_STEP = "then run `mb doctor repair --plan --only codex` again."


def _agents_refusal(code: str, reason: str, manual_step: str) -> dict[str, str]:
    return {
        "path": AGENTS_RELATIVE_PATH,
        "code": code,
        "reason": reason,
        "manual_step": manual_step,
    }


def _marker_refusal(existing: str, rerun_step: str = AGENTS_RERUN_STEP) -> dict[str, str] | None:
    """Refuse any managed-marker layout other than one begin before one end (#1052).

    Without both markers in order, Main Branch cannot tell where its guidance
    ends and a person's notes begin, so it writes nothing.
    """

    begins = existing.count(AGENTS_MANAGED_BEGIN)
    ends = existing.count(AGENTS_MANAGED_END)
    if begins == 0 and ends == 0:
        return None
    if (
        begins == 1
        and ends == 1
        and existing.find(AGENTS_MANAGED_BEGIN) < existing.find(AGENTS_MANAGED_END)
    ):
        return None
    if begins == 1 and ends == 0:
        return _agents_refusal(
            "missing_end_marker",
            "AGENTS.md has the Main Branch begin marker but no end marker, so Main "
            "Branch cannot tell where its guidance ends and your own notes begin. "
            "It left the file unchanged.",
            f"Put `{AGENTS_MANAGED_END}` on its own line right after the Main Branch "
            f"guidance (above any notes of your own), {rerun_step}",
        )
    if begins == 0 and ends == 1:
        return _agents_refusal(
            "missing_begin_marker",
            "AGENTS.md has the Main Branch end marker but no begin marker, so Main "
            "Branch cannot tell where its guidance starts. It left the file unchanged.",
            f"Put `{AGENTS_MANAGED_BEGIN}` on its own line right before the Main "
            f"Branch guidance (below any notes of your own), {rerun_step}",
        )
    return _agents_refusal(
        "marker_mismatch",
        f"AGENTS.md has {begins} Main Branch begin marker(s) and {ends} end "
        "marker(s), not one of each in order, so Main Branch cannot tell which text "
        "is its guidance. It left the file unchanged.",
        f"Keep exactly one `{AGENTS_MANAGED_BEGIN}` above the Main Branch guidance "
        f"and one `{AGENTS_MANAGED_END}` below it, {rerun_step}",
    )


def _unrendered_template_hash(body: str) -> str:
    """The template hash of rendered guidance text, with its two fields put back.

    Every template that carried the metadata comment had one `# {{BUSINESS_NAME}}`
    heading as its first line and one `` `@{{GH_USERNAME}}` `` line as its last.
    """

    lines = body.replace("\r\n", "\n").strip().split("\n")
    if len(lines) < 2 or not lines[0].startswith("# ") or not _OWNER_LINE_RE.match(lines[-1]):
        return ""
    lines[0] = "# {{BUSINESS_NAME}}"
    lines[-1] = "`@{{GH_USERNAME}}`"
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()[:16]


def _old_generated_span(existing: str) -> tuple[int, int] | None:
    """Where an older generated AGENTS.md sits inside `existing`, or None (#1052).

    Before the managed markers, `mb` wrote the whole file from the template
    with the metadata comment on top. A span counts only when the text from
    that comment to an owner line, with the business name and owner put back,
    hashes to the `template_hash` the comment names: exactly the generated
    text, unedited. Anything before or after it was written by a person.
    """

    match = _GUIDANCE_METADATA_RE.search(existing)
    digest = parse_guidance_metadata(existing).get("template_hash", "")
    if not match or not digest:
        return None
    offset = match.end()
    for line in existing[match.end() :].splitlines(keepends=True):
        offset += len(line)
        if not _OWNER_LINE_RE.match(line.strip()):
            continue
        if _unrendered_template_hash(existing[match.end() : offset]) == digest:
            return match.start(), offset
    return None


def _merge_agents_md(
    existing: str, rendered: str, rerun_step: str = AGENTS_RERUN_STEP
) -> tuple[str, dict[str, str] | None]:
    """The new AGENTS.md text, or the unchanged text and why it was refused.

    Only Main Branch's own guidance is replaced: the text between the managed
    markers, or an older generated file recognised by its template hash.
    Everything else in the file is kept. When the guidance cannot be told apart
    from a person's notes, nothing is written (#1052).
    """

    block = _managed_agents_block(rendered)
    refusal = _marker_refusal(existing, rerun_step)
    if refusal is not None:
        return existing, refusal
    start = existing.find(AGENTS_MANAGED_BEGIN)
    if start != -1:
        end = existing.find(AGENTS_MANAGED_END, start)
        tail_start = end + len(AGENTS_MANAGED_END)
        return existing[:start] + block.rstrip("\n") + existing[tail_start:], None
    if not existing.strip():
        return block, None
    if not parse_guidance_metadata(existing):
        return block + "\n" + existing, None
    span = _old_generated_span(existing)
    if span is None:
        return existing, _agents_refusal(
            "unrecognised_generated_text",
            "AGENTS.md was written by an older Main Branch (it has the guidance "
            "metadata comment but no begin and end markers), and its text no longer "
            "matches the template that comment names, so Main Branch cannot separate "
            "its guidance from text you wrote. It left the file unchanged.",
            f"Put `{AGENTS_MANAGED_BEGIN}` on its own line above the Main Branch "
            f"guidance and `{AGENTS_MANAGED_END}` below it, keeping your own notes "
            f"outside the markers, {rerun_step}",
        )
    kept = (existing[: span[0]] + existing[span[1] :]).strip("\n")
    if not kept.strip():
        return block, None
    return block + "\n" + kept + "\n", None
