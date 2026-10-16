"""Shared relationship registry for graph and validation surfaces."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

REGISTRY_VERSION = "0.1"
INFO_GAPS_WITHOUT_DAILY_ACTIONS = frozenset(
    {"accepted_decisions_without_links", "research_without_links"}
)

LOCAL_REF_ROOTS = {
    "bets",
    "campaigns",
    "core",
    "data",
    "decisions",
    "docs",
    "documents",
    "log",
    "outputs",
    "pushes",
    "reference",
    "reports",
    "research",
}

WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]\n]+)\]\]")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


@dataclass(frozen=True)
class Relationship:
    """A frontmatter field that represents a typed relationship."""

    canonical_type: str
    fields: tuple[str, ...]
    description: str
    source_globs: tuple[str, ...] = ()
    legacy: bool = False

    @property
    def canonical_field(self) -> str:
        return self.fields[0]


RELATIONSHIPS: tuple[Relationship, ...] = (
    Relationship(
        canonical_type="bet",
        fields=("linked_bets",),
        description="Connects a file to a bet that frames or is affected by the work.",
    ),
    Relationship(
        canonical_type="research",
        fields=("linked_research",),
        description="Connects a file to research that supports or informs it.",
    ),
    Relationship(
        canonical_type="decision",
        fields=("linked_decisions", "linked_decision"),
        description="Connects a file to a decision that shaped it.",
        legacy=True,
    ),
    Relationship(
        canonical_type="push",
        fields=("linked_pushes", "linked_campaigns"),
        description="Connects a file to a coordinated push; linked_campaigns is legacy.",
        legacy=True,
    ),
    Relationship(
        canonical_type="outcome",
        fields=("linked_outcomes",),
        description="Connects a file to a result, review, log, or outcome artifact.",
    ),
    Relationship(
        canonical_type="document",
        fields=("linked_docs", "linked_documents"),
        description="Connects a file to supporting docs or documents.",
    ),
    Relationship(
        canonical_type="issue",
        fields=("linked_issues",),
        description="Connects a file to durable GitHub issue work threads.",
    ),
    Relationship(
        canonical_type="offer",
        fields=("linked_offers",),
        description="Connects a file to one or more business offers.",
    ),
    Relationship(
        canonical_type="offer",
        fields=("offer",),
        description="Connects a push to the offer it promotes.",
        source_globs=("pushes/*/push.md", "campaigns/*/campaign.md"),
    ),
    Relationship(
        canonical_type="playbook",
        fields=("linked_playbooks", "playbook"),
        description="Connects a file to a reusable playbook.",
        legacy=True,
    ),
    Relationship(
        canonical_type="strategy",
        fields=("linked_strategy", "linked_strategies"),
        description="Connects a file to strategy context.",
        legacy=True,
    ),
    Relationship(
        canonical_type="prd",
        fields=("linked_prds", "linked_prd", "related_prds"),
        description="Connects a file to PRDs or product direction docs.",
        legacy=True,
    ),
    Relationship(
        canonical_type="data_source",
        fields=("linked_data_sources",),
        description=(
            "Connects a file to a data-source record (data/<provider>/source.md) "
            "that describes provider, owner, privacy, cadence, storage, and reports."
        ),
    ),
    Relationship(
        canonical_type="supersedes",
        fields=("supersedes",),
        description="Connects a newer artifact to the prior artifact it replaces.",
    ),
)

FIELD_TO_RELATIONSHIP: dict[str, Relationship] = {
    field: relationship for relationship in RELATIONSHIPS for field in relationship.fields
}
RELATIONSHIP_FIELDS: tuple[str, ...] = tuple(FIELD_TO_RELATIONSHIP)

BODY_LINK_REL_TYPE = "reference"
BODY_LINK_ORIGINAL_FIELDS = {"wikilink", "markdown_link"}
PROVIDER_REL_TYPE = "provider"
PROVIDER_ORIGINAL_FIELD = "provider_refs"


def relationship_for_field(field: str, *, source_path: str | None = None) -> Relationship | None:
    """Return the registry entry for a field when it applies to the source file."""

    relationship = FIELD_TO_RELATIONSHIP.get(field)
    if relationship is None:
        return None
    if not relationship.source_globs:
        return relationship
    if source_path is None:
        return None
    path = PurePosixPath(source_path)
    if any(path.match(pattern) for pattern in relationship.source_globs):
        return relationship
    return None


def relationship_fields_for_source(source_path: str | None = None) -> tuple[str, ...]:
    """Return relationship fields that should be read for a source file."""

    return tuple(
        field
        for field in RELATIONSHIP_FIELDS
        if relationship_for_field(field, source_path=source_path) is not None
    )


def normalize_relationship(
    original_field: str, *, source_path: str | None = None, fallback: str = BODY_LINK_REL_TYPE
) -> str:
    """Map an edge's source field to a canonical relationship type."""

    if original_field in BODY_LINK_ORIGINAL_FIELDS:
        return BODY_LINK_REL_TYPE
    if original_field == PROVIDER_ORIGINAL_FIELD:
        return PROVIDER_REL_TYPE
    relationship = relationship_for_field(original_field, source_path=source_path)
    if relationship is None:
        return fallback
    return relationship.canonical_type


def clean_ref(ref: str) -> str:
    """Strip anchors and query strings from a path-like reference."""

    without_anchor = ref.split("#", 1)[0]
    return without_anchor.split("?", 1)[0].strip()


def is_external_ref(ref: str) -> bool:
    """Return true for URLs, anchors, and explicit cross-repo references."""

    parsed = urlparse(ref)
    if bool(parsed.scheme) or ref.startswith("#"):
        return True
    parts = Path(clean_ref(ref)).parts
    return (
        len(parts) > 1
        and parts[0] not in {".", ".."}
        and parts[0] not in LOCAL_REF_ROOTS
        and parts[1] in LOCAL_REF_ROOTS
    )


def strip_fenced_code_blocks(markdown: str) -> str:
    """Remove fenced code block contents while preserving line boundaries."""

    lines: list[str] = []
    in_fence = False
    for line in markdown.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            lines.append("\n")
            continue
        if not in_fence:
            lines.append(line)
    return "".join(lines)


def strip_markdown_code(markdown: str) -> str:
    """Remove fenced and inline code before relationship link parsing."""

    return INLINE_CODE_RE.sub("", strip_fenced_code_blocks(markdown))


def wikilink_target(raw_target: str) -> str:
    """Return the path/title component from an Obsidian-style wikilink."""

    target = raw_target.split("|", 1)[0].strip()
    target = target.split("#", 1)[0].strip()
    return target


def markdown_link_target(raw_target: str) -> str:
    """Return the target component from a standard Markdown link destination."""

    target = raw_target.strip()
    if not target:
        # Empty destinations (`[text]()`) are real in operator repos; they
        # must surface as findings downstream, never crash the run.
        return ""
    target = target.split(None, 1)[0].strip()
    if (target.startswith('"') and target.endswith('"')) or (
        target.startswith("'") and target.endswith("'")
    ):
        target = target[1:-1]
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return clean_ref(target)


def iter_markdown_links(markdown: str) -> Iterator[tuple[str, str]]:
    """Yield standard Markdown links, preserving balanced parens in targets."""

    index = 0
    while index < len(markdown):
        start = markdown.find("[", index)
        if start == -1:
            return
        if start > 0 and markdown[start - 1] == "!":
            index = start + 1
            continue
        label_end = markdown.find("]", start + 1)
        if label_end == -1:
            return
        target_start = label_end + 1
        if target_start >= len(markdown) or markdown[target_start] != "(":
            index = label_end + 1
            continue
        pos = target_start + 1
        depth = 0
        target: list[str] = []
        while pos < len(markdown):
            char = markdown[pos]
            if char == "(":
                depth += 1
                target.append(char)
            elif char == ")":
                if depth == 0:
                    yield markdown[start + 1 : label_end], "".join(target).strip()
                    index = pos + 1
                    break
                depth -= 1
                target.append(char)
            else:
                target.append(char)
            pos += 1
        else:
            index = label_end + 1


def is_local_markdown_ref(ref: str) -> bool:
    """Return true for local Markdown file references that should be validated."""

    clean = markdown_link_target(ref)
    if not clean or is_external_ref(clean):
        return False
    suffix = Path(clean).suffix
    return suffix in {"", ".md"}


def resolve_markdown_link(repo: Path, source: Path, ref: str) -> Path | None:
    """Resolve a standard Markdown link relative to source, then repo root."""

    clean = markdown_link_target(ref)
    if not clean:
        return None
    if clean.startswith("/"):
        candidates = [repo / clean.lstrip("/")]
    else:
        candidates = [source.parent / clean, repo / clean]
    if not clean.endswith(".md"):
        candidates.extend(candidate.with_suffix(".md") for candidate in list(candidates))
    for candidate in candidates:
        target = candidate.resolve()
        try:
            target.relative_to(repo)
        except ValueError:
            continue
        if target.is_file() and target.suffix == ".md":
            return target
    return None


def registry_payload() -> dict[str, Any]:
    """Return the public registry contract embedded in graph and validation JSON."""

    return {
        "version": REGISTRY_VERSION,
        "relationships": [
            {
                "canonical_type": relationship.canonical_type,
                "canonical_field": relationship.canonical_field,
                "fields": list(relationship.fields),
                "description": relationship.description,
                "source_globs": list(relationship.source_globs),
                "legacy": relationship.legacy,
            }
            for relationship in RELATIONSHIPS
        ],
        "body_links": {
            "canonical_type": BODY_LINK_REL_TYPE,
            "fields": sorted(BODY_LINK_ORIGINAL_FIELDS),
        },
        "provider_refs": {
            "canonical_type": PROVIDER_REL_TYPE,
            "field": PROVIDER_ORIGINAL_FIELD,
            "exposes_raw_values": False,
        },
    }
