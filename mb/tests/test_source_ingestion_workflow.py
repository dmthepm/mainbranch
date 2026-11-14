"""Contract checks for source-ingestion privacy guidance."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_README = REPO_ROOT / "docs" / "README.md"
SOURCE_DOC = REPO_ROOT / "docs" / "source-ingestion.md"
SESSION_EXCAVATION = REPO_ROOT / "docs" / "session-excavation.md"
THINK_SKILL = REPO_ROOT / ".claude" / "skills" / "mb-think" / "SKILL.md"
THINK_WORKFLOW = REPO_ROOT / "workflows" / "mb-think" / "workflow.md"
THINK_REF = REPO_ROOT / ".claude" / "skills" / "mb-think" / "references" / "source-ingestion.md"
RESEARCH_PHASE = REPO_ROOT / ".claude" / "skills" / "mb-think" / "references" / "research-phase.md"
LOCAL_TRANSCRIPTION = (
    REPO_ROOT / ".claude" / "skills" / "mb-think" / "references" / "local-transcription.md"
)
DOCUMENT_INGESTION = (
    REPO_ROOT / ".claude" / "skills" / "mb-think" / "references" / "document-ingestion.md"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_source_ingestion_doc_defines_manifest_skip_and_routing_contract() -> None:
    text = _read(SOURCE_DOC)

    required = [
        "Inventory Before Content",
        "Manifest-First Review",
        "Allow And Skip Filters",
        "Read The Smallest Useful Slice",
        "Route Durable Output",
        "Proof Permission Gate",
        "Stale-Source Handoff",
        "Provider Boundary",
        "full chat exports, provider payloads, scrape dumps",
        "No approval lets credentials, sensitive",
        "gated-community content",
        "permissioned_public: false",
        "This rail does not make a provider supported",
    ]
    for phrase in required:
        assert phrase in text


def test_source_ingestion_is_indexed_and_session_excavation_routes_to_it() -> None:
    docs_readme = _read(DOCS_README)
    session = _read(SESSION_EXCAVATION)

    assert "source-ingestion.md" in docs_readme
    assert "use [`source-ingestion.md`](source-ingestion.md)" in session
    assert "Session excavation turns a session into public" in session
    assert "source ingestion controls whether and how source material" in session


def test_think_skill_routes_authenticated_sources_to_self_contained_reference() -> None:
    skill = _read(THINK_SKILL)
    workflow = _read(THINK_WORKFLOW)
    ref = _read(THINK_REF)

    assert "Source ingestion privacy rail" in skill
    assert "[source-ingestion.md](references/source-ingestion.md)" in skill
    assert "Authenticated community, calls, Drive/provider exports" in skill
    assert "no_raw_transcripts" in workflow
    assert "route through the source-ingestion privacy" in workflow
    assert "Inventory before content" in ref
    assert "Connector availability is not" in ref
    assert "provider mutation, bulk" in ref


def test_transcription_and_document_guidance_keep_raw_outputs_out_of_git() -> None:
    research = _read(RESEARCH_PHASE)
    transcription = _read(LOCAL_TRANSCRIPTION)
    documents = _read(DOCUMENT_INGESTION)

    for text in (research, transcription, documents):
        assert "source-ingestion.md" in text

    assert "Commit synthesized findings, not raw provider" in research
    assert "Save raw transcripts to OS temp or ignored local scratch first" in transcription
    assert "Do not commit full transcripts" in transcription
    assert "Raw conversions should stay in OS temp or ignored local scratch" in documents
