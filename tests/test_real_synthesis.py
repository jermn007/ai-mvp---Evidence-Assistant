"""Regression tests for synthesis parsing and fallback behavior."""

from app.fulltext_retriever import SupportingQuote
from app.research_synthesizer import (
    StudyFindings,
    _generate_fallback_synthesis,
    _parse_synthesis_response,
)


def _make_finding(
    *,
    score: float,
    rating: str,
    title: str,
    doi: str,
    key_findings: str,
    learner: str,
    intervention: str,
    context: str,
    outcome: str,
    quote_text: str,
) -> StudyFindings:
    """Helper to build a StudyFindings instance with consistent metadata."""

    quote = SupportingQuote(
        quote_text=quote_text,
        context="Excerpt from results section.",
        relevance_score=0.85,
        page_number=3,
        section="Results",
    )

    return StudyFindings(
        record_id=f"record-{doi}",
        title=title,
        authors="Smith, J.; Johnson, M.",
        year=2022,
        publication_type="Journal Article",
        quality_score=score,
        quality_rating=rating,
        key_findings=key_findings,
        lico_relevance={
            "learner": learner,
            "intervention": intervention,
            "context": context,
            "outcome": outcome,
        },
        methodology="Randomized Controlled Trial",
        sample_size="n = 120",
        limitations="Follow-up limited to one semester.",
        doi=doi,
        url=f"https://example.org/{doi.replace('/', '-')}",
        source="PubMed",
        full_text_content=None,
        supporting_quotes=[quote],
    )


def test_parse_response_prioritizes_high_quality_studies():
    """Top quality studies should anchor executive summary and evidence."""

    top_finding = _make_finding(
        score=0.9,
        rating="Green",
        title="Adaptive simulations improve diagnostic skills",
        doi="10.1234/top-study",
        key_findings="Learners using adaptive simulations achieved significantly higher diagnostic accuracy than controls.",
        learner="Third-year medical students",
        intervention="Adaptive simulation platform",
        context="Clinical skills lab",
        outcome="Diagnostic accuracy improved by 18%",
        quote_text="Adaptive cohorts demonstrated markedly higher accuracy gains (p < 0.01).",
    )

    moderate_finding = _make_finding(
        score=0.68,
        rating="Amber",
        title="Peer feedback enhances reflective practice",
        doi="10.2345/mid-study",
        key_findings="Structured peer feedback improved reflective writing scores across two assignments.",
        learner="Undergraduate nursing students",
        intervention="Structured peer feedback rubric",
        context="Blended learning course",
        outcome="Reflection rubric scores increased by 12%",
        quote_text="Students valued actionable peer insights to guide revisions.",
    )

    lower_finding = _make_finding(
        score=0.4,
        rating="Red",
        title="Unguided video review shows mixed effects",
        doi="10.3456/low-study",
        key_findings="Unguided video review produced inconsistent engagement and learning outcomes.",
        learner="First-year residents",
        intervention="Unguided video review",
        context="On-ward training",
        outcome="Mixed engagement metrics",
        quote_text="Participation varied widely across cohorts, limiting firm conclusions.",
    )

    findings = [moderate_finding, top_finding, lower_finding]
    quotes = [quote for finding in findings for quote in (finding.supporting_quotes or [])]

    synthesis = _parse_synthesis_response("Mock response", findings, quotes)

    assert synthesis.supporting_evidence, "Expected supporting evidence entries"
    top_evidence = synthesis.supporting_evidence[0]
    assert top_evidence.citation_keys == ["S01"], "Highest quality study should appear first"
    assert top_evidence.citations[0].doi == "10.1234/top-study"
    assert "[S01]" in synthesis.executive_summary
    assert synthesis.study_citations["S01"].title == top_finding.title


def test_fallback_synthesis_includes_citation_metadata():
    """Fallback generation should preserve citation metadata for UI rendering."""

    findings = [
        _make_finding(
            score=0.82,
            rating="Green",
            title="Adaptive spaced repetition boosts retention",
            doi="10.4567/spaced",
            key_findings="Adaptive spaced repetition led to sustained gains on delayed assessments.",
            learner="Preclinical students",
            intervention="Adaptive spaced repetition platform",
            context="Online study module",
            outcome="Delayed test scores improved by 15%",
            quote_text="Delayed post-tests revealed meaningful retention advantages (d = 0.65).",
        ),
        _make_finding(
            score=0.55,
            rating="Amber",
            title="Case-based workshops support transfer",
            doi="10.5678/case",
            key_findings="Case-based workshops encouraged transfer of diagnostic reasoning skills to new scenarios.",
            learner="Internal medicine residents",
            intervention="Facilitated case-based workshop",
            context="Weekly residency seminars",
            outcome="Transfer tasks showed 10% improvement",
            quote_text="Participants reported clearer diagnostic heuristics after workshops.",
        ),
    ]

    fallback = _generate_fallback_synthesis(findings, "How effective are adaptive learning tools?")

    assert fallback.study_citations, "Fallback should expose citation metadata"
    assert "S01" in fallback.study_citations
    assert fallback.supporting_evidence[0].citation_keys == ["S01"]
    assert fallback.supporting_evidence[0].citations[0].title.startswith("Adaptive spaced repetition")
