"""MoneyPath scoring and proof assessment for the status briefing."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from mb import books as books_mod
from mb.json_result import json_default
from mb.status_records import (
    ACTIVE_PUSH_STATUSES,
    COMPLETED_PUSH_STATUSES,
    LIVE_OFFER_STATUSES,
    _coerce_string_list,
    _frontmatter_status,
    _is_stub_content,
    _money_amount,
    _playbook_summaries,
    _read_frontmatter,
    _read_markdown_text,
    _relative_existing_paths,
    _relative_markdown_files,
)

MONEY_PATH_SCHEMA_VERSION = "1.0"
MONEY_PATH_LEVEL_LABELS = {
    0: "missing",
    1: "stated",
    2: "structured",
    3: "evidence_backed",
    4: "field_tested",
    5: "instrumented",
}
MONEY_PATH_COMPONENTS = (
    "customer_progress",
    "offer",
    "audience",
    "proof",
    "product_ladder",
    "cta_path",
    "channel_strategy",
    "active_push",
    "playbook",
    "page_readiness",
    "outcome_feedback_loop",
)
OFFER_GUARDRAIL_KEYWORDS = {
    "audience": ("audience", "who this is for", "who they are", "buyer", "customer"),
    "transformation": ("transformation", "outcome", "before", "after", "result"),
    "mechanism": ("mechanism", "method", "how it works", "process"),
    "price_value": ("pricing", "price", "value", "$", "investment"),
    "proof": ("proof", "testimonial", "case study", "typicality", "evidence"),
    "risk_reversal": ("risk reversal", "guarantee", "refund", "trial", "pilot"),
    "objections": ("objection", "concern", "blocker", "why not"),
    "reason_to_act": ("urgency", "reason to act", "timing", "capacity", "deadline"),
    "next_step": ("next step", "cta", "call", "apply", "buy", "checkout", "join", "book"),
}
AUDIENCE_SIGNAL_KEYWORDS = {
    "customer_progress": ("progress", "job", "trying to", "desired outcome", "what they want"),
    "buyer_language": ("what they say", "language", "phrases", "interviews", "reviews", "dms"),
    "pain_or_gain": ("pain", "gain", "escaping", "status quo", "problem"),
    "objections": ("objection", "concern", "trust", "time", "price", "fit"),
}
CUSTOMER_PROGRESS_KEYWORDS = {
    "job_to_be_done": ("job", "trying to", "progress", "switching", "hire"),
    "pain": ("pain", "problem", "stuck", "struggle", "escaping", "status quo"),
    "gain": ("gain", "desired outcome", "result", "better", "wants"),
    "language": ("what they say", "language", "phrases", "interviews", "reviews", "dms"),
}
CTA_KEYWORDS = (
    "next step",
    "cta",
    "call to action",
    "book",
    "apply",
    "buy",
    "checkout",
    "join",
    "subscribe",
    "download",
    "waitlist",
    "sign up",
    "schedule",
)
PRODUCT_LADDER_REQUIREMENTS = {
    "entry_step": ("entry", "first step", "front end", "lead magnet"),
    "ascension_path": ("ascension", "cross-sell", "upgrade", "feeds from", "feeds into"),
    "retention_offer": ("retention", "renewal", "continuity", "membership", "community"),
}
CHANNEL_KEYWORDS = (
    "paid",
    "organic",
    "email",
    "site",
    "community",
    "partner",
    "outreach",
    "content",
    "ads",
    "search",
)
PROOF_BEFORE_KEYWORDS = (
    "before",
    "previously",
    "used to",
    "started with",
    "came in",
    "stuck",
)
PROOF_OUTCOME_KEYWORDS = (
    "after",
    "outcome",
    "result",
    "shipped",
    "booked",
    "won",
    "increased",
    "reduced",
    "saved",
)
PROOF_TIMEFRAME_KEYWORDS = (
    "time to outcome",
    "within",
    "deadline",
    "review period",
)
PROOF_METRIC_KEYWORDS = (
    "%",
    "$",
    "revenue",
    "calls",
    "signups",
    "leads",
    "conversion",
    "sales",
    "hours",
)
PROOF_MECHANISM_KEYWORDS = (
    "mechanism",
    "method",
    "process",
    "because",
    "using",
    "through",
    "workflow",
)
PROOF_OBJECTION_KEYWORDS = (
    "objection",
    "concern",
    "skeptical",
    "worried",
    "hesitated",
    "trust",
    "time",
    "price",
)
PROOF_PERMISSION_KEYWORDS = (
    "permissioned",
    "approved for public",
    "public: true",
    "safe to share",
)
PROOF_PERMISSION_NEGATIVE_RE = re.compile(
    r"\b(?:not|no|without|pending|needs?|awaiting|unapproved)\b.{0,40}"
    r"\b(?:permission|permissioned|approved|public|share|sharing)\b"
    r"|\b(?:permission|permissioned|approved|public|share|sharing)\b.{0,40}"
    r"\b(?:not|no|without|pending|needed|awaiting|unapproved|false)\b"
)
PROOF_AVERAGE_CASE_KEYWORDS = (
    "average",
    "median",
    "typical",
    "most users",
    "usual",
    "common case",
)
PROOF_CAVEAT_KEYWORDS = ("caveat", "constraint", "not guaranteed", "depends", "varies")
PROOF_FAILURE_CONTEXT_KEYWORDS = (
    "failure",
    "fails",
    "does not work",
    "doesn't work",
    "when this breaks",
    "poor fit",
)
PROOF_SOURCE_KEYWORDS = (
    "source",
    "customer language",
    "sales call",
    "interview",
    "conversion",
    "outcome log",
    "recorded",
)


def _money_path_label(level: int) -> str:
    return MONEY_PATH_LEVEL_LABELS.get(level, "missing")


def _money_path_evidence(
    *,
    kind: str,
    path: str,
    summary: str,
    field: str = "",
) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": path,
        "field": field,
        "summary": summary,
    }


def _money_path_object(
    *,
    level: int,
    status: str,
    summary: str,
    paths: list[str],
    missing: list[str],
    evidence: list[dict[str, Any]] | None = None,
    references: list[str] | None = None,
    recommended_route: str = "/mb-think",
    confidence: str = "high",
) -> dict[str, Any]:
    resolved_level = max(0, min(5, int(level)))
    return {
        "level": resolved_level,
        "label": _money_path_label(resolved_level),
        "status": status,
        "summary": summary,
        "paths": paths[:10],
        "missing": missing[:10],
        "evidence": (evidence or [])[:10],
        "references": references or [],
        "recommended_route": recommended_route,
        "confidence": confidence,
        "safe_to_share": True,
    }


def _keyword_hits(text: str, groups: dict[str, tuple[str, ...]]) -> list[str]:
    lowered = text.lower()
    return [
        group
        for group, keywords in groups.items()
        if any(keyword in lowered for keyword in keywords)
    ]


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _markdown_body_without_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return "\n".join(lines[index + 1 :]).strip()
    return text.strip()


def _offer_slug_from_path(path: str) -> str:
    match = re.match(r"core/offers/([^/]+)/offer\.md$", path)
    return match.group(1) if match else ""


TestimonialEntry = str | dict[str, Any]


def _known_offer_refs(offer_paths: list[str]) -> dict[str, str]:
    refs: dict[str, str] = {}
    for path in offer_paths:
        refs[path] = path
        slug = _offer_slug_from_path(path)
        if slug:
            refs[slug] = path
            refs[f"core/offers/{slug}"] = path
            refs[f"core/offers/{slug}/"] = path
            refs[f"core/offers/{slug}/offer.md"] = path
    return refs


def _normalize_offer_ref(value: Any, offer_paths: list[str]) -> str:
    if not isinstance(value, str):
        return ""
    clean = value.strip().strip("\"'")
    if not clean:
        return ""
    clean = clean.removeprefix("./")
    return _known_offer_refs(offer_paths).get(clean, "")


def _proof_linked_offer_refs(repo: Path, proof_path: str, offer_paths: list[str]) -> set[str]:
    meta = _read_frontmatter(repo / proof_path)
    raw_refs = set(_coerce_string_list(meta.get("offer")))
    raw_refs.update(_coerce_string_list(meta.get("linked_offers")))
    refs = {
        normalized for ref in raw_refs if (normalized := _normalize_offer_ref(ref, offer_paths))
    }
    match = re.match(r"core/offers/([^/]+)/proof/", proof_path)
    if match and (
        normalized := _normalize_offer_ref(f"core/offers/{match.group(1)}/offer.md", offer_paths)
    ):
        refs.add(normalized)
    return {ref for ref in refs if ref}


def _testimonial_entries(text: str, meta: dict[str, Any]) -> list[TestimonialEntry]:
    entries: list[TestimonialEntry] = []
    frontmatter_entries = meta.get("testimonials")
    if isinstance(frontmatter_entries, list):
        for item in frontmatter_entries:
            if isinstance(item, dict):
                entries.append(item)
            elif isinstance(item, str) and item.strip():
                entries.append(item.strip())
    body = _markdown_body_without_frontmatter(text)
    sections = [
        section.strip()
        for section in re.split(r"(?m)^#{2,6}\s+", body)
        if section.strip() and len(section.strip()) >= 20
    ]
    if len(sections) > 1:
        entries.extend(sections)
    else:
        list_entries = [
            line.strip(" >-*")
            for line in body.splitlines()
            if re.match(r"^\s*(?:[-*]\s+|>\s*)", line) and len(line.strip(" >-*")) >= 20
        ]
        if list_entries:
            entries.extend(list_entries)
        else:
            cleaned = "\n".join(
                line for line in body.splitlines() if not line.strip().startswith("#")
            ).strip()
            if len(cleaned) >= 20:
                entries.append(cleaned)
    deduped: list[TestimonialEntry] = []
    seen: set[str] = set()
    for entry in entries:
        key = (
            json.dumps(entry, sort_keys=True, default=json_default)
            if isinstance(entry, dict)
            else entry.strip()
        )
        if key and key not in seen:
            deduped.append(entry)
            seen.add(key)
    return deduped


def _testimonial_text(entry: TestimonialEntry) -> str:
    if isinstance(entry, str):
        return entry
    values: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, str):
            values.append(value)
        elif isinstance(value, (int, float)):
            values.append(str(value))

    collect(entry)
    return " ".join(values)


def _truthy_structured_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "approved", "public", "permissioned"}
    return False


def _falsey_structured_value(value: Any) -> bool:
    if isinstance(value, bool):
        return not value
    if isinstance(value, str):
        return value.strip().lower() in {
            "false",
            "no",
            "not approved",
            "not permissioned",
            "pending",
            "private",
            "internal",
        }
    return False


def _testimonial_structured_permission_signal(entry: TestimonialEntry) -> bool | None:
    if not isinstance(entry, dict):
        return None
    permission_fields = {
        "public",
        "permissioned_public",
        "approved_for_public",
        "safe_to_share",
        "public_approved",
    }
    explicit_false = False
    for key, value in entry.items():
        normalized = str(key).strip().lower().replace("-", "_")
        if normalized not in permission_fields:
            continue
        if _truthy_structured_value(value):
            return True
        explicit_false = explicit_false or _falsey_structured_value(value)
    if explicit_false:
        return False
    return None


def _testimonial_text_permission_signal(text: str) -> bool:
    lowered = text.lower()
    if PROOF_PERMISSION_NEGATIVE_RE.search(lowered):
        return False
    return _contains_any(lowered, PROOF_PERMISSION_KEYWORDS)


def _testimonial_structured_offer_refs(entry: TestimonialEntry) -> list[str]:
    if not isinstance(entry, dict):
        return []
    refs: list[str] = []
    for key in ("offer", "linked_offer", "linked_offers"):
        refs.extend(_coerce_string_list(entry.get(key)))
    return refs


def _testimonial_explicit_offer_refs(text: str) -> list[str]:
    refs: list[str] = []
    for match in re.finditer(
        r"(?im)(?:^|\b)(?:offer|linked_offer|linked_offers)\s*:\s*(?:-\s*)?([^\n,;#]+)",
        text,
    ):
        refs.append(match.group(1).strip().strip("\"'`"))
    return refs


def _proof_text_has_timeframe(text: str) -> bool:
    lowered = text.lower()
    return bool(re.search(r"\b\d+\s+(?:day|days|week|weeks|month|months)\b", lowered)) or any(
        keyword in lowered for keyword in PROOF_TIMEFRAME_KEYWORDS
    )


def _proof_text_has_metric(text: str) -> bool:
    lowered = text.lower()
    return bool(
        re.search(r"(?:\d+%|\$\d+|\b\d+\s+(?:calls|signups|leads|sales|hours)\b)", lowered)
    ) or any(keyword in lowered for keyword in PROOF_METRIC_KEYWORDS)


def _testimonial_signal_counts(
    entries: list[TestimonialEntry],
    *,
    linked_offer_refs: set[str],
    offer_paths: list[str],
) -> dict[str, int]:
    counts = {
        "total": len(entries),
        "generic": 0,
        "specific": 0,
        "permissioned_public": 0,
        "specific_permissioned_public": 0,
        "linked_to_offer": 0,
        "with_before_state": 0,
        "with_outcome": 0,
        "with_timeframe": 0,
        "with_metric": 0,
        "with_mechanism": 0,
        "with_objection": 0,
    }
    has_path_offer_link = bool(linked_offer_refs & set(offer_paths))
    for entry in entries:
        entry_text = _testimonial_text(entry)
        lowered = entry_text.lower()
        has_before = _contains_any(lowered, PROOF_BEFORE_KEYWORDS)
        has_outcome = _contains_any(lowered, PROOF_OUTCOME_KEYWORDS)
        has_timeframe = _proof_text_has_timeframe(lowered)
        has_metric = _proof_text_has_metric(lowered)
        has_mechanism = _contains_any(lowered, PROOF_MECHANISM_KEYWORDS)
        has_objection = _contains_any(lowered, PROOF_OBJECTION_KEYWORDS)
        structured_permission = _testimonial_structured_permission_signal(entry)
        has_permission = (
            structured_permission
            if structured_permission is not None
            else _testimonial_text_permission_signal(entry_text)
        )
        explicit_offer_refs = _testimonial_structured_offer_refs(entry)
        explicit_offer_refs.extend(_testimonial_explicit_offer_refs(entry_text))
        has_entry_offer_link = any(
            _normalize_offer_ref(ref, offer_paths) for ref in explicit_offer_refs
        )
        has_offer_link = has_path_offer_link or has_entry_offer_link
        signals = [
            has_before,
            has_outcome,
            has_timeframe,
            has_metric,
            has_mechanism,
            has_objection,
        ]
        counts["with_before_state"] += int(has_before)
        counts["with_outcome"] += int(has_outcome)
        counts["with_timeframe"] += int(has_timeframe)
        counts["with_metric"] += int(has_metric)
        counts["with_mechanism"] += int(has_mechanism)
        counts["with_objection"] += int(has_objection)
        counts["permissioned_public"] += int(has_permission)
        counts["specific_permissioned_public"] += int(has_permission and any(signals))
        counts["linked_to_offer"] += int(has_offer_link)
        if any(signals):
            counts["specific"] += 1
        else:
            counts["generic"] += 1
    return counts


def _empty_proof_quality() -> dict[str, Any]:
    return {
        "testimonials": {
            "total": 0,
            "generic": 0,
            "specific": 0,
            "permissioned_public": 0,
            "specific_permissioned_public": 0,
            "linked_to_offer": 0,
            "with_before_state": 0,
            "with_outcome": 0,
            "with_timeframe": 0,
            "with_metric": 0,
            "with_mechanism": 0,
            "with_objection": 0,
        },
        "typicality": {
            "exists": False,
            "has_average_case": False,
            "has_caveats": False,
            "has_common_failure_context": False,
            "has_time_to_outcome": False,
        },
        "claim_links": {
            "linked_offers": [],
            "unsupported_offer_claims": [],
        },
        "public_marketing": {
            "ready": False,
            "status": "missing",
            "summary": "No testimonial proof is available for public marketing.",
            "missing": ["testimonials"],
            "next_action": "collect_testimonials",
        },
    }


def _proof_public_marketing_readiness(quality: dict[str, Any]) -> dict[str, Any]:
    testimonial_quality = quality.get("testimonials") or {}
    total = int(testimonial_quality.get("total") or 0)
    specific = int(testimonial_quality.get("specific") or 0)
    permissioned = int(testimonial_quality.get("permissioned_public") or 0)
    specific_permissioned = int(testimonial_quality.get("specific_permissioned_public") or 0)
    if total == 0:
        return {
            "ready": False,
            "status": "missing",
            "summary": "No testimonial proof is available for public marketing.",
            "missing": ["testimonials"],
            "next_action": "collect_testimonials",
        }
    if specific > 0 and specific_permissioned == 0:
        return {
            "ready": False,
            "status": "blocked",
            "summary": (
                "Specific proof exists for internal strategy, but no specific "
                "testimonial is permissioned for public marketing."
            ),
            "missing": ["permissioned_public_testimonials"],
            "next_action": "collect_public_permission",
        }
    if specific == 0:
        missing = ["specific_testimonials"]
        if permissioned == 0:
            missing.append("permissioned_public_testimonials")
        return {
            "ready": False,
            "status": "incomplete",
            "summary": (
                "Testimonials exist, but public marketing proof needs "
                "specific permissioned evidence."
            ),
            "missing": missing,
            "next_action": "strengthen_testimonials",
        }
    return {
        "ready": True,
        "status": "ready",
        "summary": "At least one specific testimonial is permissioned for public marketing.",
        "missing": [],
        "next_action": None,
    }


def _money_path_offer(
    repo: Path,
    *,
    proof_paths: list[str],
    proof_quality: dict[str, Any],
) -> dict[str, Any]:
    per_offer_paths = sorted(
        path.relative_to(repo).as_posix()
        for path in repo.glob("core/offers/*/offer.md")
        if path.is_file()
    )
    paths = per_offer_paths + _relative_existing_paths(
        repo,
        ["core/offer.md", "reference/core/offer.md"],
    )
    if not paths:
        return _money_path_object(
            level=0,
            status="missing",
            summary="No offer file was found.",
            paths=["core/offer.md"],
            missing=["offer"],
            references=["docs/offer-sharpening.md"],
        )

    texts_by_path = {path: _read_markdown_text(repo / path) for path in paths}
    texts = list(texts_by_path.values())
    combined = "\n".join(texts)
    guardrails = _keyword_hits(combined, OFFER_GUARDRAIL_KEYWORDS)
    missing = [key for key in OFFER_GUARDRAIL_KEYWORDS if key not in guardrails]
    guardrail_checks: dict[str, dict[str, Any]] = {}
    for field, keywords in OFFER_GUARDRAIL_KEYWORDS.items():
        hit_paths = [path for path, text in texts_by_path.items() if _contains_any(text, keywords)]
        guardrail_checks[field] = {
            "present": bool(hit_paths),
            "paths": hit_paths[:5],
            "keywords": [keyword for keyword in keywords if keyword in combined.lower()][:5],
        }
    stubs = [path for path in paths if _is_stub_content(repo, path)]
    evidence = [
        _money_path_evidence(
            kind="file",
            path=path,
            field="offer",
            summary="Offer file exists.",
        )
        for path in paths[:5]
    ]
    evidence.extend(
        _money_path_evidence(
            kind="section",
            path=paths[0],
            field=field,
            summary=f"{field.replace('_', ' ')} signal appears in offer text.",
        )
        for field in guardrails[:5]
    )
    live_offer_paths = [
        path for path in per_offer_paths if _frontmatter_status(repo, path) in LIVE_OFFER_STATUSES
    ]
    testimonial_quality = proof_quality.get("testimonials") or {}
    claim_links = proof_quality.get("claim_links") or {}
    proof_boundary_warnings: list[str] = []
    if "proof" in guardrails and not proof_paths:
        proof_boundary_warnings.append("proof_claim_without_proof_file")
    if (
        int(testimonial_quality.get("total") or 0) > 0
        and int(testimonial_quality.get("permissioned_public") or 0) == 0
    ):
        proof_boundary_warnings.append("testimonials_without_permissioned_public_signal")
    if claim_links.get("unsupported_offer_claims"):
        proof_boundary_warnings.append("offer_claims_without_offer_linked_proof")

    level = 1
    status = "stated"
    summary = "Offer exists as durable repo text."
    if len(guardrails) >= 4 and not stubs:
        level = 2
        status = "structured"
        summary = "Offer has several expected guardrail signals."
    if proof_paths and level >= 2:
        level = 3
        status = "evidence_backed"
        summary = "Offer is structured and proof files exist."
    if stubs:
        missing = sorted(set(missing + ["replace_stub_offer"]))
        summary = "Offer file is still a public stub."
    if len(live_offer_paths) > 1:
        level = min(level, 1)
        status = "ambiguous_multi_offer"
        missing = sorted(set(missing + ["active_offer_selection"]))
        summary = (
            "Multiple live offer files exist and no active offer selection is "
            "available in status facts."
        )

    item = _money_path_object(
        level=level,
        status=status,
        summary=summary,
        paths=paths,
        missing=missing,
        evidence=evidence,
        references=["docs/offer-sharpening.md"],
        recommended_route="/mb-think",
    )
    item["guardrails"] = {
        "answered": guardrails,
        "missing": missing,
        "checks": guardrail_checks,
        "proof_boundary_warnings": proof_boundary_warnings,
        "reference": "docs/offer-sharpening.md",
    }
    return item


def _money_path_audience(repo: Path) -> dict[str, Any]:
    paths = sorted(
        path.relative_to(repo).as_posix()
        for path in repo.glob("core/offers/*/audience.md")
        if path.is_file()
    )
    paths.extend(_relative_existing_paths(repo, ["core/audience.md", "reference/core/audience.md"]))
    if not paths:
        return _money_path_object(
            level=0,
            status="missing",
            summary="No audience file was found.",
            paths=["core/audience.md"],
            missing=["audience", "customer_progress", "buyer_language"],
            references=["docs/offer-sharpening.md"],
        )

    combined = "\n".join(_read_markdown_text(repo / path) for path in paths)
    hits = _keyword_hits(combined, AUDIENCE_SIGNAL_KEYWORDS)
    missing = [key for key in AUDIENCE_SIGNAL_KEYWORDS if key not in hits]
    stubs = [path for path in paths if _is_stub_content(repo, path)]
    level = 1
    status = "stated"
    summary = "Audience exists as durable repo text."
    if len(hits) >= 2 and not stubs:
        level = 2
        status = "structured"
        summary = "Audience includes buyer language, progress, pain, or objection signals."
    if "buyer_language" in hits and "objections" in hits and not stubs:
        level = 3
        status = "evidence_backed"
        summary = "Audience includes source-language and objection signals."
    if stubs:
        missing = sorted(set(missing + ["replace_stub_audience"]))
        summary = "Audience file is still a public stub."

    return _money_path_object(
        level=level,
        status=status,
        summary=summary,
        paths=paths,
        missing=missing,
        evidence=[
            _money_path_evidence(
                kind="file", path=path, field="audience", summary="Audience file exists."
            )
            for path in paths[:5]
        ]
        + [
            _money_path_evidence(
                kind="section",
                path=paths[0],
                field=field,
                summary=f"{field.replace('_', ' ')} signal appears in audience text.",
            )
            for field in hits[:5]
        ],
        references=["docs/offer-sharpening.md"],
        recommended_route="/mb-think",
        confidence="medium" if level >= 2 else "high",
    )


def _money_path_customer_progress(repo: Path) -> dict[str, Any]:
    paths = _relative_existing_paths(repo, ["core/audience.md", "reference/core/audience.md"])
    paths.extend(
        sorted(
            path.relative_to(repo).as_posix()
            for path in repo.glob("core/offers/*/audience.md")
            if path.is_file()
        )
    )
    research_paths = [
        path.relative_to(repo).as_posix()
        for path in _relative_markdown_files(repo, "research")[:8]
        if _contains_any(
            _read_markdown_text(path), tuple(sum(CUSTOMER_PROGRESS_KEYWORDS.values(), ()))
        )
    ]
    paths.extend(research_paths[:5])
    if not paths:
        return _money_path_object(
            level=0,
            status="missing",
            summary="No customer-progress, job, pain, gain, or buyer-language source was found.",
            paths=["core/audience.md", "research/"],
            missing=["customer_progress", "buyer_language"],
            references=["docs/offer-sharpening.md"],
            recommended_route="/mb-think",
        )

    combined = "\n".join(
        _read_markdown_text(repo / path) for path in paths if (repo / path).is_file()
    )
    hits = _keyword_hits(combined, CUSTOMER_PROGRESS_KEYWORDS)
    missing = [key for key in CUSTOMER_PROGRESS_KEYWORDS if key not in hits]
    stubs = [path for path in paths if (repo / path).is_file() and _is_stub_content(repo, path)]
    level = 1
    status = "stated"
    summary = "Customer progress exists as loose audience or research text."
    if len(hits) >= 2 and not stubs:
        level = 2
        status = "structured"
        summary = "Customer progress includes job, pain, gain, or language signals."
    if "language" in hits and ("job_to_be_done" in hits or "pain" in hits) and not stubs:
        level = 3
        status = "evidence_backed"
        summary = "Customer progress includes buyer language tied to a job, pain, or gain."
    if stubs:
        missing = sorted(set(missing + ["replace_stub_customer_progress"]))
        summary = "Customer-progress source is still a public audience stub."

    return _money_path_object(
        level=level,
        status=status,
        summary=summary,
        paths=sorted(set(paths)),
        missing=missing,
        evidence=[
            _money_path_evidence(
                kind="text",
                path=paths[0],
                field=field,
                summary=f"{field.replace('_', ' ')} signal appears in repo text.",
            )
            for field in hits[:5]
        ],
        references=["docs/offer-sharpening.md"],
        recommended_route="/mb-think",
        confidence="medium" if level >= 2 else "high",
    )


def _proof_quality(
    repo: Path,
    *,
    paths: list[str],
    offer_paths: list[str],
    pushes: list[dict[str, Any]],
    playbooks: list[dict[str, Any]],
    measurement: dict[str, Any],
    relationship_health: dict[str, Any],
) -> dict[str, Any]:
    quality = _empty_proof_quality()
    testimonial_counts = quality["testimonials"]
    linked_offers: set[str] = set()
    any_structured_entry = False
    proof_texts: list[str] = []
    for path in paths:
        text = _read_markdown_text(repo / path)
        proof_texts.append(text)
        linked_refs = _proof_linked_offer_refs(repo, path, offer_paths)
        linked_offers.update(linked_refs)
        if path.endswith("testimonials.md"):
            meta = _read_frontmatter(repo / path)
            entries = _testimonial_entries(text, meta)
            any_structured_entry = any_structured_entry or len(entries) > 1 or bool(meta)
            counts = _testimonial_signal_counts(
                entries,
                linked_offer_refs=linked_refs,
                offer_paths=offer_paths,
            )
            for key, value in counts.items():
                testimonial_counts[key] += value
        if path.endswith("typicality.md"):
            lowered = text.lower()
            typicality = quality["typicality"]
            typicality["exists"] = True
            typicality["has_average_case"] = _contains_any(lowered, PROOF_AVERAGE_CASE_KEYWORDS)
            typicality["has_caveats"] = _contains_any(lowered, PROOF_CAVEAT_KEYWORDS)
            typicality["has_common_failure_context"] = _contains_any(
                lowered,
                PROOF_FAILURE_CONTEXT_KEYWORDS,
            )
            typicality["has_time_to_outcome"] = _proof_text_has_timeframe(lowered)
    quality["claim_links"]["linked_offers"] = sorted(linked_offers)
    unsupported_claims: list[str] = []
    if offer_paths and paths and not (linked_offers & set(offer_paths)):
        unsupported_claims.extend(
            f"{path}: no offer-linked proof detected" for path in offer_paths[:5]
        )
    quality["claim_links"]["unsupported_offer_claims"] = unsupported_claims
    quality["structured_entries"] = any_structured_entry
    quality["source_backed"] = _contains_any("\n".join(proof_texts), PROOF_SOURCE_KEYWORDS)
    quality["instrumentation"] = {
        "active_push": bool(
            [
                push
                for push in pushes
                if str(push.get("status") or "").lower() in ACTIVE_PUSH_STATUSES
            ]
        ),
        "playbook": bool(playbooks),
        "page_readiness": bool(measurement.get("available")),
        "outcome_feedback": bool(
            (relationship_health.get("sections") or {}).get("outcomes", {}).get("linked_count")
        )
        or any(playbook.get("linked_outcomes") for playbook in playbooks),
    }
    quality["public_marketing"] = _proof_public_marketing_readiness(quality)
    return quality


def _money_path_proof(
    repo: Path,
    *,
    offer_paths: list[str],
    pushes: list[dict[str, Any]],
    playbooks: list[dict[str, Any]],
    measurement: dict[str, Any],
    relationship_health: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    proof_files = [
        path
        for root in [repo / "core" / "proof", *repo.glob("core/offers/*/proof")]
        if root.exists()
        for path in sorted(root.rglob("*.md"))
        if path.is_file()
    ]
    legacy_proof = [
        path
        for path in repo.glob("core/offers/*/*.md")
        if path.name in {"testimonials.md", "typicality.md"}
    ]
    proof_files.extend(legacy_proof)
    paths = sorted({path.relative_to(repo).as_posix() for path in proof_files})
    if not paths:
        quality = _empty_proof_quality()
        return (
            _money_path_object(
                level=0,
                status="missing",
                summary="No reusable proof files were found.",
                paths=["core/proof/"],
                missing=["testimonials", "typicality", "proof_angles"],
                references=["docs/offer-sharpening.md"],
                recommended_route="/mb-think",
            )
            | {"quality": quality},
            [],
        )

    quality = _proof_quality(
        repo,
        paths=paths,
        offer_paths=offer_paths,
        pushes=pushes,
        playbooks=playbooks,
        measurement=measurement,
        relationship_health=relationship_health,
    )
    has_testimonials = any(path.endswith("testimonials.md") for path in paths)
    has_typicality = any(path.endswith("typicality.md") for path in paths)
    has_angles = any("/angles/" in path for path in paths)
    missing = [
        name
        for name, present in {
            "testimonials": has_testimonials,
            "typicality": has_typicality,
            "proof_angles": has_angles,
        }.items()
        if not present
    ]
    level = 1
    status = "stated"
    summary = "Proof files exist."
    testimonial_quality = quality["testimonials"]
    typicality_quality = quality["typicality"]
    instrumentation = quality["instrumentation"]
    if has_testimonials or has_typicality or quality["structured_entries"]:
        level = 2
        status = "structured"
        summary = "Proof includes standard files, entries, or frontmatter."
    if int(testimonial_quality["specific"]) > 0 and (
        has_typicality or int(testimonial_quality["linked_to_offer"]) > 0
    ):
        level = 3
        status = "evidence_backed"
        summary = "Proof includes specific outcomes tied to typicality or an offer."
    if (
        level >= 3
        and int(testimonial_quality["specific"]) >= 2
        and (
            quality["source_backed"]
            or int(testimonial_quality["permissioned_public"]) > 0
            or int(testimonial_quality["with_metric"]) > 0
            or int(testimonial_quality["with_timeframe"]) > 0
        )
    ):
        level = 4
        status = "field_tested"
        summary = "Proof includes multiple specific, source or outcome-backed entries."
    has_active_path = bool(instrumentation["active_push"]) or bool(instrumentation["playbook"])
    if (
        level >= 3
        and int(testimonial_quality["linked_to_offer"]) > 0
        and bool(typicality_quality["exists"])
        and has_active_path
        and bool(instrumentation["outcome_feedback"])
    ):
        level = 5
        status = "instrumented"
        summary = "Proof is linked to an offer and connected to outcome feedback."
    return (
        _money_path_object(
            level=level,
            status=status,
            summary=summary,
            paths=paths,
            missing=missing,
            evidence=[
                _money_path_evidence(
                    kind="file", path=path, field="proof", summary="Proof file exists."
                )
                for path in paths[:5]
            ],
            references=["docs/offer-sharpening.md"],
            recommended_route="/mb-think",
        )
        | {"quality": quality},
        paths,
    )


def _money_path_product_ladder(repo: Path, *, multi_offer: bool) -> dict[str, Any]:
    paths = _relative_existing_paths(
        repo, ["core/product-ladder.md", "reference/core/product-ladder.md"]
    )
    if not paths and not multi_offer:
        return _money_path_object(
            level=1,
            status="single_offer_mode",
            summary=(
                "Single-offer repo; product ladder is optional until offers need "
                "relationship logic."
            ),
            paths=["core/product-ladder.md"],
            missing=[],
            evidence=[],
            references=[".claude/reference/business-primitives/setup-patterns.md"],
            recommended_route="/mb-think",
        )
    if not paths:
        return _money_path_object(
            level=0,
            status="missing",
            summary="Multiple offer files exist, but no product ladder explains how they relate.",
            paths=["core/product-ladder.md"],
            missing=["entry_step", "ascension_path", "retention_offer"],
            references=[".claude/reference/business-primitives/setup-patterns.md"],
            recommended_route="/mb-think",
        )
    text = "\n".join(_read_markdown_text(repo / path) for path in paths)
    hits = _keyword_hits(text, PRODUCT_LADDER_REQUIREMENTS)
    level = 2 if len(hits) >= 3 else 1
    return _money_path_object(
        level=level,
        status="structured" if level >= 2 else "stated",
        summary="Product ladder explains offer relationships."
        if level >= 2
        else "Product ladder exists as loose text.",
        paths=paths,
        missing=[
            item for item in ("entry_step", "ascension_path", "retention_offer") if item not in hits
        ],
        evidence=[
            _money_path_evidence(
                kind="file",
                path=paths[0],
                field="product_ladder",
                summary="Product ladder file exists.",
            )
        ],
        references=[".claude/reference/business-primitives/setup-patterns.md"],
        recommended_route="/mb-think",
    )


def _money_path_cta(
    repo: Path,
    *,
    offer_paths: list[str],
    playbooks: list[dict[str, Any]],
    pushes: list[dict[str, Any]],
    measurement: dict[str, Any],
) -> dict[str, Any]:
    paths: list[str] = []
    evidence: list[dict[str, Any]] = []
    text_only_paths: list[str] = []
    for rel in offer_paths:
        if _contains_any(_read_markdown_text(repo / rel), CTA_KEYWORDS):
            paths.append(rel)
            text_only_paths.append(rel)
            evidence.append(
                _money_path_evidence(
                    kind="text",
                    path=rel,
                    field="cta",
                    summary="CTA or next-step language appears in offer text.",
                )
            )
    push_goal_paths = [
        str(push.get("path") or "") for push in pushes if push.get("path") and push.get("goal")
    ]
    if push_goal_paths:
        paths.extend(push_goal_paths[:5])
        evidence.append(
            _money_path_evidence(
                kind="frontmatter",
                path=push_goal_paths[0],
                field="goal",
                summary="Push goal can anchor the entry or conversion step.",
            )
        )
    playbook_paths = [str(item.get("path") or "") for item in playbooks if item.get("path")]
    if playbook_paths:
        paths.extend(playbook_paths[:5])
        evidence.append(
            _money_path_evidence(
                kind="frontmatter",
                path=playbook_paths[0],
                field="resource",
                summary="A playbook resource or trigger can carry the next step.",
            )
        )
    if measurement.get("available"):
        source = str(
            measurement.get("source_record")
            or measurement.get("site_repo")
            or ".mainbranch/conversion.json"
        )
        paths.append(source)
        evidence.append(
            _money_path_evidence(
                kind="measurement",
                path=source,
                field="conversion",
                summary=str(measurement.get("summary") or "Conversion plan found."),
            )
        )

    if not paths:
        return _money_path_object(
            level=0,
            status="missing",
            summary="No CTA path, resource handoff, or conversion endpoint was found.",
            paths=["core/offer.md"],
            missing=["next_step", "conversion_endpoint"],
            references=["docs/offer-sharpening.md"],
            recommended_route="/mb-think",
        )
    level = 2 if measurement.get("available") or playbook_paths or push_goal_paths else 1
    return _money_path_object(
        level=level,
        status="structured" if level >= 2 else "stated",
        summary=(
            "CTA path is connected to a playbook, push goal, or conversion plan."
            if level >= 2
            else "CTA language exists, but no connected page, push goal, or playbook was found."
        ),
        paths=sorted(set(paths)),
        missing=[] if level >= 2 else ["conversion_endpoint"],
        evidence=evidence,
        references=["docs/offer-sharpening.md"],
        recommended_route="/mb-site" if level >= 1 else "/mb-think",
        confidence="high" if level >= 2 else ("medium" if text_only_paths else "high"),
    )


def _money_path_channel_strategy(repo: Path, *, pushes: list[dict[str, Any]]) -> dict[str, Any]:
    paths = _relative_existing_paths(
        repo,
        [
            "core/content-strategy.md",
            "core/marketing/distribution-strategy.md",
            "reference/core/content-strategy.md",
        ],
    )
    paths.extend(
        sorted(
            path.relative_to(repo).as_posix()
            for root in [
                repo / "core" / "marketing" / "channels",
                repo / "core" / "marketing" / "accounts",
            ]
            if root.exists()
            for path in root.glob("*.md")
            if path.is_file()
        )
    )
    active_channels = sorted(
        {
            str(channel)
            for push in pushes
            if str(push.get("status") or "").lower()
            in ACTIVE_PUSH_STATUSES | COMPLETED_PUSH_STATUSES
            for channel in (push.get("channels") or [])
            if isinstance(channel, str) and channel.strip()
        }
    )
    evidence = [
        _money_path_evidence(
            kind="file",
            path=path,
            field="channel_strategy",
            summary="Content strategy file exists.",
        )
        for path in paths
    ]
    if active_channels and pushes:
        evidence.append(
            _money_path_evidence(
                kind="frontmatter",
                path=str(pushes[0].get("path") or "pushes/"),
                field="channels",
                summary=f"Push channel(s) recorded: {', '.join(active_channels[:5])}.",
            )
        )
    if not paths and not active_channels:
        return _money_path_object(
            level=0,
            status="missing",
            summary="No channel strategy or push channels were found.",
            paths=["core/content-strategy.md"],
            missing=["active_channel", "distribution_strategy"],
            references=["docs/content-strategy.md", "docs/operator-loops.md"],
            recommended_route="/mb-think",
        )
    level = 2 if active_channels else 1
    return _money_path_object(
        level=level,
        status="structured" if level >= 2 else "stated",
        summary="Channel strategy has active channel facts."
        if active_channels
        else "Channel strategy exists as durable text.",
        paths=paths + [str(push.get("path")) for push in pushes[:5] if push.get("path")],
        missing=[] if active_channels else ["active_channel"],
        evidence=evidence,
        references=["docs/content-strategy.md", "docs/operator-loops.md"],
        recommended_route="/mb-think",
    )


def _money_path_active_push(pushes: list[dict[str, Any]]) -> dict[str, Any]:
    active = [
        push for push in pushes if str(push.get("status") or "").lower() in ACTIVE_PUSH_STATUSES
    ]
    if not active:
        return _money_path_object(
            level=0,
            status="missing",
            summary="No active or planned push is moving the money path forward.",
            paths=["pushes/"],
            missing=["active_push"],
            references=["docs/system-architecture.md"],
            recommended_route="/mb-start",
        )
    first = active[0]
    required = ("goal", "audience", "offer", "promise", "channels")
    missing = [key for key in required if not first.get(key)]
    level = 2 if not missing else 1
    return _money_path_object(
        level=level,
        status="structured" if level >= 2 else "stated",
        summary="Active push has goal, audience, offer, promise, and channels."
        if level >= 2
        else "Active push exists but is missing route fields.",
        paths=[str(push.get("path") or "") for push in active[:5] if push.get("path")],
        missing=missing,
        evidence=[
            _money_path_evidence(
                kind="frontmatter",
                path=str(first.get("path") or "pushes/"),
                field="status",
                summary=f"Push status is {first.get('status')}.",
            )
        ],
        references=["docs/system-architecture.md"],
        recommended_route="/mb-start",
    )


def _money_path_playbook(
    playbooks: list[dict[str, Any]], playbook_health: dict[str, Any]
) -> dict[str, Any]:
    if not playbooks:
        return _money_path_object(
            level=0,
            status="missing",
            summary="No push playbook run record was found.",
            paths=["pushes/<push>/playbooks/"],
            missing=["playbook_run"],
            references=["docs/playbooks.md"],
            recommended_route="/mb-start",
        )
    approved = [
        item
        for item in playbooks
        if str((item.get("approval") or {}).get("status") or "").lower() == "approved"
    ]
    active_or_completed = [
        item
        for item in playbooks
        if str(item.get("status") or "").lower() in {"active", "completed"}
    ]
    missing = []
    if not approved:
        missing.append("approval")
    if not active_or_completed:
        missing.append("active_or_completed_run")
    level = 1
    if active_or_completed:
        level = 2
    if approved and active_or_completed and not (playbook_health.get("gaps") or []):
        level = 3
    first = playbooks[0]
    return _money_path_object(
        level=level,
        status="evidence_backed" if level >= 3 else ("structured" if level >= 2 else "stated"),
        summary="Push playbook is approved, active/completed, and has no status health gaps."
        if level >= 3
        else "Push playbook exists but still needs approval, activation, or review.",
        paths=[str(item.get("path") or "") for item in playbooks[:5] if item.get("path")],
        missing=missing,
        evidence=[
            _money_path_evidence(
                kind="frontmatter",
                path=str(first.get("path") or ""),
                field="provider_boundary",
                summary=f"Provider boundary is {first.get('provider_boundary') or 'unspecified'}.",
            )
        ],
        references=["docs/playbooks.md"],
        recommended_route="/mb-start",
    )


def _money_path_page_readiness(measurement: dict[str, Any]) -> dict[str, Any]:
    if not measurement.get("available"):
        return _money_path_object(
            level=0,
            status="missing",
            summary="No paid-traffic site conversion plan was found.",
            paths=[".mainbranch/conversion.json"],
            missing=["page_or_lander", "conversion_plan"],
            references=["docs/google-ads-gtm-conversion-rubric.md"],
            recommended_route="/mb-site",
        )
    state = str(measurement.get("state") or "missing")
    state_levels = {
        "missing": 0,
        "blocked": 1,
        "ready_for_preview": 2,
        "ready_for_operator_review": 3,
        "ready": 5,
    }
    level = state_levels.get(state, 1)
    source = str(
        measurement.get("source_record")
        or measurement.get("site_repo")
        or ".mainbranch/conversion.json"
    )
    return _money_path_object(
        level=level,
        status=state,
        summary=str(measurement.get("summary") or f"Site measurement state is {state}."),
        paths=[source],
        missing=[] if level >= 2 else ["conversion_plan_ready"],
        evidence=[
            _money_path_evidence(
                kind="measurement",
                path=source,
                field="state",
                summary=f"Site readiness state is {state}.",
            )
        ],
        references=["docs/google-ads-gtm-conversion-rubric.md"],
        recommended_route="/mb-site",
    )


def _money_path_outcome_feedback(
    relationship_health: dict[str, Any],
    playbook_health: dict[str, Any],
    playbooks: list[dict[str, Any]],
) -> dict[str, Any]:
    relationship_outcomes = (relationship_health.get("sections") or {}).get("outcomes") or {}
    linked_count = int(relationship_outcomes.get("linked_count") or 0)
    playbooks_with_outcomes = [item for item in playbooks if item.get("linked_outcomes")]
    playbook_summary = playbook_health.get("summary") or {}
    missing_count = int(playbook_summary.get("completed_playbooks_without_outcome") or 0) + int(
        (relationship_health.get("summary") or {}).get("completed_pushes_without_outcome") or 0
    )
    if linked_count or playbooks_with_outcomes:
        evidence = (
            [
                _money_path_evidence(
                    kind="relationship",
                    path="",
                    field="linked_outcomes",
                    summary=f"{linked_count} linked outcome relationship(s) found.",
                )
            ]
            if linked_count
            else []
        )
        if playbooks_with_outcomes:
            evidence.append(
                _money_path_evidence(
                    kind="frontmatter",
                    path=str(playbooks_with_outcomes[0].get("path") or ""),
                    field="linked_outcomes",
                    summary=f"{len(playbooks_with_outcomes)} playbook(s) link outcomes.",
                )
            )
        return _money_path_object(
            level=3,
            status="evidence_backed",
            summary=("Outcome links feed learning back into the repo."),
            paths=[
                str(item.get("path") or "")
                for item in playbooks_with_outcomes[:5]
                if item.get("path")
            ],
            missing=[] if not missing_count else ["some_completed_runs_missing_outcomes"],
            evidence=evidence,
            references=["docs/business-connections.md"],
            recommended_route="/mb-end",
        )
    return _money_path_object(
        level=0,
        status="missing",
        summary="No outcome feedback link was found.",
        paths=["pushes/", "bets/", "log/"],
        missing=["linked_outcomes", "review_or_outcome_note"],
        evidence=[],
        references=["docs/business-connections.md"],
        recommended_route="/mb-end",
    )


def _money_path_ranked_actions(
    objects: dict[str, dict[str, Any]], overall_level: int
) -> list[dict[str, Any]]:
    candidates = [
        (
            "define-customer-progress",
            "Define the customer progress",
            "customer_progress",
            (
                "The money path needs the buyer's job, pain, gain, or language before "
                "offer routing can be trusted."
            ),
            "/mb-think",
        ),
        (
            "clarify-offer",
            "Clarify the offer",
            "offer",
            "The money path needs a legible offer before downstream routing can help.",
            "/mb-think",
        ),
        (
            "define-audience-progress",
            "Define the buyer progress",
            "audience",
            "The money path needs a clear audience and customer-progress signal.",
            "/mb-think",
        ),
        (
            "attach-proof",
            "Attach proof to the promise",
            "proof",
            "The path needs proof, typicality, or evidence before scaling traffic.",
            "/mb-think",
        ),
        (
            "define-cta-path",
            "Define the CTA path",
            "cta_path",
            "Offer and audience facts need a next step or conversion endpoint.",
            "/mb-think",
        ),
        (
            "connect-channel-strategy",
            "Connect an active channel",
            "channel_strategy",
            "The path needs a demand source or distribution channel.",
            "/mb-think",
        ),
        (
            "open-or-select-push",
            "Open or select the active push",
            "active_push",
            "The path needs coordinated work moving it forward.",
            "/mb-start",
        ),
        (
            "record-playbook-run",
            "Record the push playbook",
            "playbook",
            "The path needs a run record for approval, provider boundary, and outcome hooks.",
            "/mb-start",
        ),
        (
            "prepare-page-readiness",
            "Prepare page readiness",
            "page_readiness",
            "Demand needs somewhere measurable to land before launch advice is useful.",
            "/mb-site",
        ),
        (
            "close-outcome-loop",
            "Close the outcome feedback loop",
            "outcome_feedback_loop",
            "Completed or active work needs outcome evidence feeding back into durable memory.",
            "/mb-end",
        ),
    ]
    actions: list[dict[str, Any]] = []
    # Strong proof (level >= 4) with only quality nits should not outrank
    # packaging/channel/push moves. Hold its strengthen action and re-insert it
    # below those moves, just above the page-readiness/outcome tail.
    deferred_strong_proof: dict[str, Any] | None = None
    for action_id, title, key, fallback_reason, route in candidates:
        component = objects.get(key) or {}
        level = int(component.get("level") or 0)
        missing = component.get("missing") or []
        if key == "outcome_feedback_loop":
            if level != 0:
                continue
        elif key == "proof" and level >= 2:
            quality = component.get("quality") or {}
            testimonial_quality = quality.get("testimonials") or {}
            typicality_quality = quality.get("typicality") or {}
            claim_links = quality.get("claim_links") or {}
            instrumentation = quality.get("instrumentation") or {}
            public_marketing = quality.get("public_marketing") or {}
            if public_marketing.get("status") == "blocked":
                actions.append(
                    {
                        "id": "collect-proof-permission",
                        "title": "Collect proof permission",
                        "reason": str(
                            public_marketing.get("summary")
                            or "Specific proof exists, but public marketing permission is missing."
                        ),
                        "route": "/mb-think",
                        "source": "money_path.objects.proof.quality.public_marketing",
                        "component": "proof",
                        "confidence": "high",
                        "effort_hint": "low",
                        "missing": [
                            str(item) for item in (public_marketing.get("missing") or [])[:5]
                        ],
                        "safe_to_share": True,
                    }
                )
                continue
            proof_quality_gaps: list[str] = []
            if int(testimonial_quality.get("generic") or 0) > 0:
                proof_quality_gaps.append("specific_testimonials")
            if int(testimonial_quality.get("linked_to_offer") or 0) == 0:
                proof_quality_gaps.append("offer_linked_proof")
            if not bool(typicality_quality.get("exists")):
                proof_quality_gaps.append("typicality")
            if claim_links.get("unsupported_offer_claims"):
                proof_quality_gaps.append("supported_offer_claims")
            if not bool(instrumentation.get("outcome_feedback")):
                proof_quality_gaps.append("outcome_feedback")
            if not proof_quality_gaps:
                continue
            strengthen_proof = {
                "id": "strengthen-proof-quality",
                "title": "Strengthen proof quality",
                "reason": (
                    "Proof exists, but testimonials are generic or not linked to an "
                    "offer, outcome, typicality, or claim."
                ),
                "route": "/mb-think",
                "source": "money_path.objects.proof.quality",
                "component": "proof",
                "confidence": "medium",
                "effort_hint": "medium",
                "missing": proof_quality_gaps[:5],
                "safe_to_share": True,
            }
            if level >= 4:
                # Proof is already field-tested. Polishing it ranks below
                # packaging/channel/push moves; hold it for the tail.
                deferred_strong_proof = strengthen_proof
            else:
                actions.append(strengthen_proof)
            continue
        elif level >= 2:
            continue
        actions.append(
            {
                "id": action_id,
                "title": title,
                "reason": str(component.get("summary") or fallback_reason),
                "route": route,
                "source": f"money_path.objects.{key}",
                "component": key,
                "confidence": "high" if level == 0 else "medium",
                "effort_hint": "medium",
                "missing": [str(item) for item in missing[:5]],
                "safe_to_share": True,
            }
        )
    if deferred_strong_proof is not None:
        # Re-insert just above the page-readiness/outcome tail. With 5+ higher
        # priority moves ahead of it (and no tail action to anchor against), the
        # final [:5] cut can drop strong-proof polish entirely -- by design, it is
        # the lowest-urgency move once proof is already field-tested.
        tail_components = {"page_readiness", "outcome_feedback_loop"}
        insert_at = next(
            (
                index
                for index, action in enumerate(actions)
                if action.get("component") in tail_components
            ),
            len(actions),
        )
        actions.insert(insert_at, deferred_strong_proof)
    return actions[:5]


def _money_path_overall_level(objects: dict[str, dict[str, Any]]) -> int:
    customer_progress = int((objects.get("customer_progress") or {}).get("level") or 0)
    offer = int((objects.get("offer") or {}).get("level") or 0)
    audience = int((objects.get("audience") or {}).get("level") or 0)
    proof = int((objects.get("proof") or {}).get("level") or 0)
    cta = int((objects.get("cta_path") or {}).get("level") or 0)
    channel = int((objects.get("channel_strategy") or {}).get("level") or 0)
    active_push = int((objects.get("active_push") or {}).get("level") or 0)
    playbook = int((objects.get("playbook") or {}).get("level") or 0)
    page = int((objects.get("page_readiness") or {}).get("level") or 0)
    outcome = int((objects.get("outcome_feedback_loop") or {}).get("level") or 0)
    if offer == 0:
        return 0
    if customer_progress == 0 or audience == 0 or offer < 2 or audience < 2:
        return 1
    if proof == 0 or cta == 0:
        return 2
    if min(channel, active_push, playbook) == 0:
        return 3
    if outcome == 0:
        return 4
    if page >= 5 and outcome >= 3 and min(proof, cta, channel, active_push, playbook) >= 2:
        return 5
    return 4


def _money_path_active_bet_exposure(repo: Path, report: dict[str, Any]) -> dict[str, Any]:
    raw_brain = report.get("brain")
    brain = raw_brain if isinstance(raw_brain, dict) else {}
    raw_bets = brain.get("bets")
    bets = raw_bets if isinstance(raw_bets, dict) else {}
    active = [item for item in bets.get("active", []) if isinstance(item, dict)]
    books = report.get("books") if isinstance(report.get("books"), dict) else {}
    policy = (
        ((books.get("policy") or {}).get("money_path") or {}) if isinstance(books, dict) else {}
    )
    currency = str(policy.get("currency") or "USD")
    exposure_window_days = int(policy.get("exposure_window_days") or 7)
    # A bet that declares MoneyPath anchoring as required has committed (or is
    # about to commit) execution spend. Exploratory pricing/product bets that
    # have not done so should not trigger eager ledger-repair nudges.
    requires_anchor = any(
        isinstance(item.get("money_path"), dict) and bool(item["money_path"].get("required"))
        for item in active
    )
    summary: dict[str, Any] = {
        "count": len(active),
        "anchored": 0,
        "unanchored": 0,
        "requires_anchor": requires_anchor,
        "gross_exposure": _money_amount(commodity=currency),
        "this_week_at_risk": _money_amount(commodity=currency),
        "over_cap": [],
        "ledger_unavailable": False,
        "checked": False,
    }
    if not active:
        return summary
    try:
        exposure_report = books_mod.exposure(repo=repo, active=True)
    except Exception:
        return {**summary, "ledger_unavailable": True}
    if not exposure_report.get("ok") and not exposure_report.get("exposures"):
        return {**summary, "ledger_unavailable": True}
    exposures = [item for item in exposure_report.get("exposures", []) if isinstance(item, dict)]
    total_mantissa = 0
    total_places = 2
    week_mantissa = 0
    today = date.today()
    for item in exposures:
        raw_anchor = item.get("anchor")
        anchor = raw_anchor if isinstance(raw_anchor, dict) else {}
        if anchor.get("present"):
            summary["anchored"] += 1
        raw_money_path = item.get("money_path")
        money_path = raw_money_path if isinstance(raw_money_path, dict) else {}
        if not anchor.get("present") and money_path.get("required"):
            summary["unanchored"] += 1
        raw_totals = item.get("totals")
        totals = raw_totals if isinstance(raw_totals, dict) else {}
        raw_gross = totals.get("gross_outflow")
        gross = raw_gross if isinstance(raw_gross, dict) else {}
        if gross.get("commodity") == currency:
            total_places = int(gross.get("decimal_places") or total_places)
            total_mantissa += int(gross.get("decimal_mantissa") or 0)
            deadline = str(
                next(
                    (bet.get("deadline") for bet in active if bet.get("path") == item.get("path")),
                    "",
                )
            )
            try:
                deadline_date = date.fromisoformat(deadline)
            except ValueError:
                deadline_date = None
            if (
                deadline_date is not None
                and 0 <= (deadline_date - today).days <= exposure_window_days
            ):
                week_mantissa += int(gross.get("decimal_mantissa") or 0)
        raw_scale_gate = item.get("scale_gate")
        scale_gate = raw_scale_gate if isinstance(raw_scale_gate, dict) else {}
        if scale_gate.get("over_cap"):
            summary["over_cap"].append(
                {
                    "path": str(item.get("path") or ""),
                    "title": str(item.get("title") or ""),
                    "appetite_tier": str(scale_gate.get("appetite_tier") or ""),
                    "gross_exposure": gross,
                    "threshold": scale_gate.get("threshold_amount"),
                    "safe_to_share": True,
                }
            )
    summary["checked"] = True
    summary["gross_exposure"] = _money_amount(
        commodity=currency, decimal_mantissa=total_mantissa, decimal_places=total_places
    )
    summary["this_week_at_risk"] = _money_amount(
        commodity=currency, decimal_mantissa=week_mantissa, decimal_places=total_places
    )
    return summary


def _money_path_finance_actions(
    *, policy: dict[str, Any], active_bets: dict[str, Any], policy_present: bool
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    active_count = int(active_bets.get("count") or 0)
    if (policy_present or active_count) and not policy.get("thresholds_declared"):
        actions.append(
            {
                "id": "declare-appetite-thresholds",
                "title": "Declare MoneyPath appetite thresholds",
                "reason": (
                    "MoneyPath cannot compare active bet exposure to your appetite until "
                    "core/finance/books.md declares thresholds."
                ),
                "route": "/mb-think",
                "component": "financial_exposure",
                "source": "money_path.policy.thresholds_declared",
                "confidence": "medium",
                "missing": ["core/finance/books.md money_path.appetite_thresholds"],
                "safe_to_share": True,
            }
        )
    if (
        active_bets.get("ledger_unavailable")
        and active_count
        and active_bets.get("requires_anchor")
    ):
        actions.append(
            {
                "id": "repair-books-exposure",
                "title": "Repair books exposure checks",
                "reason": (
                    "An active bet requires MoneyPath anchoring, but Main Branch "
                    "cannot check private ledger anchors."
                ),
                "route": "mb books doctor --plan --json",
                "component": "financial_exposure",
                "source": "money_path.active_bets.ledger_unavailable",
                "confidence": "medium",
                "missing": ["hledger exposure check"],
                "safe_to_share": True,
            }
        )
    if int(active_bets.get("unanchored") or 0):
        actions.append(
            {
                "id": "anchor-active-bet-exposure",
                "title": "Anchor active bet exposure",
                "reason": (
                    "One or more active bets require MoneyPath anchors before execution spend."
                ),
                "route": "/mb-bet",
                "component": "financial_exposure",
                "source": "money_path.active_bets.unanchored",
                "confidence": "high",
                "missing": ["ledger bet anchors"],
                "safe_to_share": True,
            }
        )
    if active_bets.get("over_cap"):
        actions.append(
            {
                "id": "review-over-cap-bets",
                "title": "Review bets over appetite",
                "reason": "One or more active bets are over the configured MoneyPath appetite cap.",
                "route": "/mb-bet",
                "component": "financial_exposure",
                "source": "money_path.active_bets.over_cap",
                "confidence": "high",
                "missing": [
                    str(item.get("path") or "") for item in active_bets.get("over_cap", [])
                ],
                "safe_to_share": True,
            }
        )
    return actions


def _money_path(repo: Path, report: dict[str, Any]) -> dict[str, Any]:
    brain = report.get("brain") or {}
    push_report = brain.get("pushes") or {}
    pushes = [item for item in push_report.get("records", []) if isinstance(item, dict)]
    playbook_health = report.get("playbook_health") or {}
    relationship_health = report.get("relationship_health") or {}
    measurement = report.get("measurement") or {}
    playbooks = _playbook_summaries(repo)
    candidate_offer_paths = sorted(
        path.relative_to(repo).as_posix()
        for path in repo.glob("core/offers/*/offer.md")
        if path.is_file()
    )
    candidate_offer_paths.extend(
        _relative_existing_paths(repo, ["core/offer.md", "reference/core/offer.md"])
    )
    proof, proof_paths = _money_path_proof(
        repo,
        offer_paths=candidate_offer_paths,
        pushes=pushes,
        playbooks=playbooks,
        measurement=measurement,
        relationship_health=relationship_health,
    )
    offer = _money_path_offer(
        repo,
        proof_paths=proof_paths,
        proof_quality=proof.get("quality") or _empty_proof_quality(),
    )
    offer_paths = [str(path) for path in offer.get("paths") or [] if (repo / str(path)).is_file()]
    multi_offer = bool(list(repo.glob("core/offers/*/offer.md")))
    collected_objects = {
        "customer_progress": _money_path_customer_progress(repo),
        "offer": offer,
        "audience": _money_path_audience(repo),
        "proof": proof,
        "product_ladder": _money_path_product_ladder(repo, multi_offer=multi_offer),
        "cta_path": _money_path_cta(
            repo,
            offer_paths=offer_paths,
            playbooks=playbooks,
            pushes=pushes,
            measurement=measurement,
        ),
        "channel_strategy": _money_path_channel_strategy(repo, pushes=pushes),
        "active_push": _money_path_active_push(pushes),
        "playbook": _money_path_playbook(playbooks, playbook_health),
        "page_readiness": _money_path_page_readiness(measurement),
        "outcome_feedback_loop": _money_path_outcome_feedback(
            relationship_health,
            playbook_health,
            playbooks,
        ),
    }
    objects = {component: collected_objects[component] for component in MONEY_PATH_COMPONENTS}
    overall_level = _money_path_overall_level(objects)
    books = report.get("books") if isinstance(report.get("books"), dict) else {}
    policy = (
        ((books.get("policy") or {}).get("money_path") or {}) if isinstance(books, dict) else {}
    )
    policy_present = (
        bool((books.get("policy") or {}).get("present")) if isinstance(books, dict) else False
    )
    active_bets = _money_path_active_bet_exposure(repo, report)
    finance_actions = _money_path_finance_actions(
        policy=policy,
        active_bets=active_bets,
        policy_present=policy_present,
    )
    return {
        "schema_version": MONEY_PATH_SCHEMA_VERSION,
        "overall_level": overall_level,
        "overall_label": _money_path_label(overall_level),
        "summary": (
            "MoneyPath reports legibility, support, connection, and instrumentation "
            "from repo facts."
        ),
        "policy": policy,
        "active_bets": active_bets,
        "objects": objects,
        "ranked_actions": [*finance_actions, *_money_path_ranked_actions(objects, overall_level)],
        "safe_to_share": True,
    }
