# app/research_synthesizer.py
"""
AI Research Synthesis Engine for Literature Review Analysis
Generates comprehensive evidence-based answers to LICO research questions
"""

import os
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.language_models import BaseChatModel

from app.fulltext_retriever import FullTextRetriever, FullTextContent, extract_supporting_quotes, SupportingQuote

logger = logging.getLogger("ai_mvp.research_synthesizer")

@dataclass
class StudyFindings:
    """Structured representation of a study's key findings"""
    record_id: Optional[str]
    title: str
    authors: str
    year: int
    publication_type: str
    quality_score: float
    quality_rating: str
    key_findings: str
    lico_relevance: Dict[str, str]  # Maps LICO components to relevant content
    methodology: str
    sample_size: Optional[str]
    limitations: str
    doi: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    full_text_content: Optional[FullTextContent] = None
    supporting_quotes: List[SupportingQuote] = None


class CitationMetadata(BaseModel):
    """Citable study metadata that can be rendered in the UI"""

    citation_key: str = Field(description="Short identifier for referencing the study, e.g., S01")
    title: str = Field(description="Study title")
    authors: str = Field(description="Author list as provided in the record")
    year: Optional[int] = Field(default=None, description="Publication year")
    doi: Optional[str] = Field(default=None, description="Digital object identifier if available")
    url: Optional[str] = Field(default=None, description="Direct URL to the study")
    appraisal_score: Optional[float] = Field(default=None, description="Final appraisal score")
    appraisal_rating: Optional[str] = Field(default=None, description="Color-coded quality rating")
    record_id: Optional[str] = Field(default=None, description="Internal record identifier")

class LICOInsights(BaseModel):
    """Structured insights for each LICO component"""
    learner_insights: str = Field(description="Evidence about target learners")
    intervention_insights: str = Field(description="Evidence about intervention effectiveness")
    context_insights: str = Field(description="Evidence about contextual factors")
    outcome_insights: str = Field(description="Evidence about learning outcomes")

class EvidenceSupport(BaseModel):
    """Supporting evidence with direct quotes"""

    finding: str = Field(description="The specific finding or claim")
    supporting_quotes: List[str] = Field(default_factory=list, description="Direct quotes from literature")
    source_studies: List[str] = Field(default_factory=list, description="Studies providing this evidence")
    strength_rating: str = Field(description="Strength of supporting evidence")
    citation_keys: List[str] = Field(default_factory=list, description="Reference keys for the cited studies")
    citations: List[CitationMetadata] = Field(
        default_factory=list,
        description="Metadata for each cited study so the UI can render hoverable references",
    )

class ResearchSynthesis(BaseModel):
    """Comprehensive research synthesis response"""

    executive_summary: str = Field(description="High-level synthesis of all findings")
    research_question_answer: str = Field(description="Direct answer to the original research question")
    lico_insights: LICOInsights = Field(description="Detailed insights for each LICO component")
    evidence_strength: str = Field(description="Overall strength of evidence: Strong, Moderate, Limited, Insufficient")
    confidence_level: str = Field(description="Confidence in conclusions: High, Medium, Low")
    key_recommendations: List[str] = Field(default_factory=list, description="Actionable recommendations for instructional designers")
    knowledge_gaps: List[str] = Field(default_factory=list, description="Identified gaps in current research")
    methodological_quality: str = Field(description="Overall assessment of study quality")
    future_research_directions: List[str] = Field(default_factory=list, description="Suggested areas for future investigation")
    supporting_evidence: List[EvidenceSupport] = Field(default_factory=list, description="Key findings with direct quotes and citations")
    full_text_availability: Dict[str, bool] = Field(default_factory=dict, description="Which studies had full text available")
    study_citations: Dict[str, CitationMetadata] = Field(
        default_factory=dict,
        description="Map of citation keys to metadata for all studies referenced in the synthesis",
    )

class StatisticalSummary(BaseModel):
    """Statistical summary of the literature"""
    total_studies: int
    date_range: str
    quality_distribution: Dict[str, int]
    methodology_distribution: Dict[str, int]
    geographic_distribution: Dict[str, int]

async def extract_study_findings(records: List[Dict[str, Any]], retrieve_fulltext: bool = True) -> List[StudyFindings]:
    """Extract structured findings from literature records with optional full-text retrieval"""
    findings = []
    fulltext_retriever = FullTextRetriever() if retrieve_fulltext else None
    
    logger.info(f"Processing {len(records)} records with full-text retrieval: {retrieve_fulltext}")
    
    for i, record in enumerate(records):
        logger.info(f"Processing record {i+1}/{len(records)}: {record.get('title', 'Unknown')[:50]}...")
        
        # Extract LICO relevance using AI
        lico_relevance = {}
        abstract = record.get('abstract', '') or ''
        title = record.get('title', '') or ''
        
        # Attempt full-text retrieval first
        full_text_content = None
        if fulltext_retriever and (record.get('quality_rating') in ['Green', 'Amber']):
            # Only attempt full-text for higher quality studies to save time
            try:
                logger.info(f"Attempting full-text retrieval for: {title[:50]}...")
                full_text_content = fulltext_retriever.retrieve_fulltext(record)
                if full_text_content.extraction_success:
                    logger.info(f"Successfully retrieved {full_text_content.word_count} words")
                    # Use full text for LICO extraction if available
                    abstract = full_text_content.full_text[:1000]  # Use first 1000 chars for LICO extraction
                else:
                    logger.info(f"Full-text retrieval failed: {full_text_content.error_message}")
            except Exception as e:
                logger.warning(f"Full-text retrieval error for {record.get('record_id', 'unknown')}: {e}")
        
        if abstract and title:
            try:
                lico_relevance = await _extract_lico_relevance(title, abstract)
            except Exception as e:
                logger.warning(f"Failed to extract LICO relevance for {record.get('record_id', 'unknown')}: {e}")
        
        # Use full text for key findings if available
        key_text = abstract if not full_text_content else full_text_content.full_text
        key_findings = key_text[:500] + "..." if len(key_text) > 500 else key_text
        
        # Extract supporting quotes if we have full text
        supporting_quotes = []
        if full_text_content and full_text_content.extraction_success:
            try:
                # Extract quotes that support key research themes
                themes_to_support = [
                    "learning outcomes",
                    "intervention effectiveness", 
                    "instructional design",
                    "student engagement",
                    "educational technology"
                ]
                supporting_quotes = extract_supporting_quotes(full_text_content, themes_to_support)
                logger.info(f"Extracted {len(supporting_quotes)} supporting quotes")
            except Exception as e:
                logger.warning(f"Failed to extract supporting quotes: {e}")
        
        finding = StudyFindings(
            record_id=str(record.get('record_id')) if record.get('record_id') is not None else None,
            title=title,
            authors=record.get('authors', 'Not specified'),
            year=record.get('year', 0) or 0,
            publication_type=record.get('publication_type', 'Unknown'),
            quality_score=record.get('appraisal_score', 0) or 0,
            quality_rating=record.get('appraisal_color', 'Unknown'),
            key_findings=key_findings,
            lico_relevance=lico_relevance,
            methodology=_infer_methodology(title, key_text),
            sample_size=_extract_sample_size(key_text),
            limitations=_extract_limitations(key_text),
            doi=record.get('doi'),
            url=record.get('url'),
            source=record.get('source'),
            full_text_content=full_text_content,
            supporting_quotes=supporting_quotes
        )
        findings.append(finding)
    
    # Log full-text retrieval summary
    fulltext_success = sum(1 for f in findings if f.full_text_content and f.full_text_content.extraction_success)
    logger.info(f"Full-text retrieval summary: {fulltext_success}/{len(findings)} successful")
    
    return findings

# Synchronous wrappers for backward compatibility
def extract_study_findings_sync(records: List[Dict[str, Any]], retrieve_fulltext: bool = True) -> List[StudyFindings]:
    """Synchronous wrapper for extract_study_findings"""
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        return loop.run_until_complete(extract_study_findings(records, retrieve_fulltext))
    except RuntimeError:
        # If we're already in an async context, create a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                lambda: asyncio.run(extract_study_findings(records, retrieve_fulltext))
            )
            return future.result()

def synthesize_research_sync(
    findings: List[StudyFindings],
    original_question: str,
    lico_components: Optional[Dict[str, str]] = None
) -> ResearchSynthesis:
    """Synchronous wrapper for synthesize_research"""
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        return loop.run_until_complete(synthesize_research(findings, original_question, lico_components))
    except RuntimeError:
        # If we're already in an async context, create a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                lambda: asyncio.run(synthesize_research(findings, original_question, lico_components))
            )
            return future.result()

async def _extract_lico_relevance(title: str, abstract: str) -> Dict[str, str]:
    """Extract LICO-relevant content using AI via LangChain"""
    from app.llm_factory import get_smart_model, is_llm_available
    
    if not is_llm_available():
        logger.warning("LLM not available for LICO extraction")
        return {
            "learner": "Not specified",
            "intervention": "Not specified", 
            "context": "Not specified",
            "outcome": "Not specified"
        }
    
    class LICOExtraction(BaseModel):
        """LICO component extraction result"""
        learner: str = Field(description="Target learners information")
        intervention: str = Field(description="Educational intervention details")
        context: str = Field(description="Learning context information")
        outcome: str = Field(description="Learning outcomes described")
    
    system_prompt = """You are an expert in instructional design research analysis. 
    Extract LICO components concisely and accurately from academic study metadata."""
    
    human_prompt = """Analyze this study and extract content relevant to each LICO component:

Title: {title}
Abstract: {abstract}

Extract specific content for each component:
- Learner: Who are the target learners? (demographics, characteristics, prior knowledge)
- Intervention: What is the educational intervention? (teaching methods, tools, strategies) 
- Context: What is the learning context? (setting, environment, constraints)
- Outcome: What are the learning outcomes? (knowledge, skills, behaviors, performance)

Return a JSON object with keys: learner, intervention, context, outcome.
If no relevant content found for a component, return "Not specified"."""

    try:
        # Get smart model for complex extraction
        model = get_smart_model(temperature=0.3, max_tokens=500)
        
        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", human_prompt)
        ])
        
        # Create output parser
        parser = JsonOutputParser(pydantic_object=LICOExtraction)
        
        # Create chain
        chain = prompt | model | parser
        
        # Execute extraction
        result = await chain.ainvoke({"title": title, "abstract": abstract})
        
        # Convert to dict format
        if isinstance(result, dict):
            return result
        else:
            return result.model_dump()
            
    except Exception as e:
        logger.warning(f"LICO extraction failed: {e}")
        return {
            "learner": "Not specified",
            "intervention": "Not specified", 
            "context": "Not specified",
            "outcome": "Not specified"
        }

def _infer_methodology(title: str, abstract: str) -> str:
    """Infer research methodology from title and abstract"""
    text = (title + " " + abstract).lower()
    
    if any(term in text for term in ["randomized", "rct", "controlled trial"]):
        return "Randomized Controlled Trial"
    elif any(term in text for term in ["quasi-experimental", "pre-post", "before-after"]):
        return "Quasi-experimental"
    elif any(term in text for term in ["qualitative", "interview", "focus group", "ethnographic"]):
        return "Qualitative"
    elif any(term in text for term in ["survey", "questionnaire", "cross-sectional"]):
        return "Survey"
    elif any(term in text for term in ["case study", "case series"]):
        return "Case Study"
    elif any(term in text for term in ["systematic review", "meta-analysis"]):
        return "Systematic Review"
    else:
        return "Not specified"

def _extract_sample_size(abstract: str) -> Optional[str]:
    """Extract sample size from abstract using regex"""
    import re
    if not abstract:
        return None
        
    # Look for patterns like "n=50", "N = 100", "50 participants", etc.
    patterns = [
        r'[nN]\s*=\s*(\d+)',
        r'(\d+)\s+participants?',
        r'sample\s+of\s+(\d+)',
        r'(\d+)\s+students?',
        r'(\d+)\s+subjects?'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, abstract)
        if match:
            return f"n = {match.group(1)}"
    
    return None

def _extract_limitations(abstract: str) -> str:
    """Extract study limitations from abstract"""
    if not abstract:
        return "Not specified"
    
    # Look for limitation indicators
    limitation_indicators = ["limitation", "constraint", "weakness", "bias", "confound"]
    text = (abstract or "").lower()
    
    for indicator in limitation_indicators:
        if indicator in text:
            # Find sentence containing the limitation
            sentences = (abstract or "").split('.')
            for sentence in sentences:
                if indicator in (sentence or "").lower():
                    return (sentence or "").strip()
    
    return "Not specified"

def generate_statistical_summary(findings: List[StudyFindings]) -> StatisticalSummary:
    """Generate statistical summary of the literature"""
    if not findings:
        return StatisticalSummary(
            total_studies=0,
            date_range="No studies",
            quality_distribution={},
            methodology_distribution={},
            geographic_distribution={}
        )
    
    years = [f.year for f in findings if f.year > 0]
    date_range = f"{min(years)}-{max(years)}" if years else "Unknown"
    
    quality_dist = {}
    methodology_dist = {}
    
    for finding in findings:
        # Quality distribution
        rating = finding.quality_rating
        quality_dist[rating] = quality_dist.get(rating, 0) + 1
        
        # Methodology distribution
        method = finding.methodology
        methodology_dist[method] = methodology_dist.get(method, 0) + 1
    
    return StatisticalSummary(
        total_studies=len(findings),
        date_range=date_range,
        quality_distribution=quality_dist,
        methodology_distribution=methodology_dist,
        geographic_distribution={"Various": len(findings)}  # Simplified for now
    )

async def synthesize_research(
    findings: List[StudyFindings],
    original_question: str,
    lico_components: Optional[Dict[str, str]] = None
) -> ResearchSynthesis:
    """Generate comprehensive research synthesis using AI"""
    
    if not findings:
        return ResearchSynthesis(
            executive_summary="No studies available for synthesis.",
            research_question_answer="Cannot answer research question without literature evidence.",
            lico_insights=LICOInsights(
                learner_insights="No evidence available.",
                intervention_insights="No evidence available.",
                context_insights="No evidence available.",
                outcome_insights="No evidence available."
            ),
            evidence_strength="Insufficient",
            confidence_level="Low",
            key_recommendations=[],
            knowledge_gaps=["Lack of research literature on this topic"],
            methodological_quality="Cannot assess",
            future_research_directions=["Initial studies needed on this topic"],
            supporting_evidence=[],
            full_text_availability={},
            study_citations={},
        )
    
    # Prepare comprehensive context for AI synthesis
    literature_summary = _prepare_literature_context(findings, original_question)
    
    # Collect supporting quotes from full-text studies
    all_supporting_quotes = []
    fulltext_studies = []
    for finding in findings:
        if finding.full_text_content and finding.full_text_content.extraction_success:
            fulltext_studies.append(finding.title)
            all_supporting_quotes.extend(finding.supporting_quotes or [])
    
    quotes_summary = _prepare_quotes_context(all_supporting_quotes, findings)
    
    synthesis_prompt = f"""As an expert instructional design researcher, synthesize the following literature to answer the research question comprehensively.

RESEARCH QUESTION: {original_question}

LICO COMPONENTS:
{_format_lico_components(lico_components) if lico_components else "Not specified"}

FULL-TEXT AVAILABILITY:
{len(fulltext_studies)} of {len(findings)} studies had full text retrieved: {', '.join(fulltext_studies[:5])}{'...' if len(fulltext_studies) > 5 else ''}

LITERATURE EVIDENCE:
{literature_summary}

SUPPORTING QUOTES FROM FULL-TEXT STUDIES:
{quotes_summary}

Provide a comprehensive research synthesis that:

1. EXECUTIVE SUMMARY: Synthesize the key findings across all studies (2-3 paragraphs)

2. RESEARCH QUESTION ANSWER: Directly answer the original research question based on evidence

3. LICO INSIGHTS:
   - Learner insights: What does the evidence tell us about target learners?
   - Intervention insights: What interventions were most effective and why?
   - Context insights: What contextual factors influenced outcomes?
   - Outcome insights: What learning outcomes were achieved?

4. EVIDENCE STRENGTH: Assess overall evidence (Strong/Moderate/Limited/Insufficient)

5. CONFIDENCE LEVEL: Your confidence in conclusions (High/Medium/Low)

6. KEY RECOMMENDATIONS: 3-5 actionable recommendations for instructional designers

7. KNOWLEDGE GAPS: Key areas where evidence is lacking

8. METHODOLOGICAL QUALITY: Overall assessment of study quality

9. FUTURE RESEARCH DIRECTIONS: 2-4 suggested research priorities

Focus on practical implications for instructional design practice. Be specific about what the evidence supports and where uncertainty remains.
"""

    try:
        from app.llm_factory import get_smart_model, is_llm_available
        
        if not is_llm_available():
            logger.warning("LLM not available for research synthesis")
            return _generate_fallback_synthesis(findings, original_question)
        
        # Get smart model for complex synthesis
        model = get_smart_model(temperature=0.3, max_tokens=2000)
        
        # Create prompt template
        system_prompt = """You are a world-class instructional design researcher with expertise in evidence synthesis and educational technology. 
        Provide thorough, evidence-based analysis while being honest about limitations."""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", synthesis_prompt)
        ])
        
        # Create chain and execute synthesis
        chain = prompt | model
        response = await chain.ainvoke({})
        
        # Parse AI response into structured format
        return _parse_synthesis_response(response.content, findings, all_supporting_quotes)
        
    except Exception as e:
        logger.error(f"AI synthesis failed: {e}")
        return _generate_fallback_synthesis(findings, original_question)

def _prepare_literature_context(findings: List[StudyFindings], research_question: str) -> str:
    """Prepare formatted literature context for AI synthesis"""
    context_parts = []
    
    for i, finding in enumerate(findings, 1):
        study_context = f"""
STUDY {i}:
Title: {finding.title}
Authors: {finding.authors}
Year: {finding.year}
Publication Type: {finding.publication_type}
Quality Score: {finding.quality_score:.2f} ({finding.quality_rating})
Methodology: {finding.methodology}
Sample Size: {finding.sample_size or 'Not specified'}

LICO Relevance:
- Learner: {finding.lico_relevance.get('learner', 'Not specified')}
- Intervention: {finding.lico_relevance.get('intervention', 'Not specified')}
- Context: {finding.lico_relevance.get('context', 'Not specified')}
- Outcome: {finding.lico_relevance.get('outcome', 'Not specified')}

Key Findings: {finding.key_findings}
Limitations: {finding.limitations}
"""
        context_parts.append(study_context)
    
    return "\n".join(context_parts)

def _format_lico_components(lico: Dict[str, str]) -> str:
    """Format LICO components for prompt"""
    return f"""
- Learner: {lico.get('learner', 'Not specified')}
- Intervention: {lico.get('intervention', 'Not specified')}
- Context: {lico.get('context', 'Not specified')}
- Outcome: {lico.get('outcome', 'Not specified')}
"""

def _prepare_quotes_context(quotes: List[SupportingQuote], findings: List[StudyFindings]) -> str:
    """Prepare formatted quotes context for AI synthesis"""
    if not quotes:
        return "No direct quotes available - analysis based on abstracts only."

    quote_contexts = []
    for i, quote in enumerate(quotes[:10]):  # Limit to top 10 quotes
        quote_context = f"""
QUOTE {i+1} (Relevance: {quote.relevance_score:.2f}):
"{quote.quote_text}"
Context: {quote.context[:200]}...
"""
        quote_contexts.append(quote_context)

    return "\n".join(quote_contexts)


def _rank_findings_by_quality(findings: List[StudyFindings]) -> List[StudyFindings]:
    """Order studies by quality score, rating, then recency."""

    rating_priority = {"Green": 3, "Amber": 2, "Red": 1}
    return sorted(
        findings,
        key=lambda f: (
            f.quality_score or 0.0,
            rating_priority.get(f.quality_rating, 0),
            f.year or 0,
        ),
        reverse=True,
    )


def _build_citation_map(findings: List[StudyFindings]) -> Dict[str, CitationMetadata]:
    """Create citation metadata keyed by short reference identifiers."""

    citations: Dict[str, CitationMetadata] = {}
    for idx, finding in enumerate(findings):
        key = f"S{idx + 1:02d}"
        citations[key] = CitationMetadata(
            citation_key=key,
            title=finding.title,
            authors=finding.authors,
            year=finding.year if finding.year else None,
            doi=finding.doi,
            url=finding.url,
            appraisal_score=finding.quality_score if finding.quality_score else None,
            appraisal_rating=finding.quality_rating,
            record_id=finding.record_id,
        )
    return citations


def _clean_text(text: Optional[str], max_length: int = 280) -> str:
    """Normalize whitespace and trim to a readable length."""

    if not text:
        return "Not specified"

    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_length:
        return cleaned

    truncated = cleaned[:max_length].rsplit(" ", 1)[0].strip()
    return truncated + "..."


def _strength_from_quality(finding: StudyFindings) -> str:
    """Derive an evidence strength label from appraisal data."""

    score = finding.quality_score or 0.0
    if score >= 0.75:
        return "Strong"
    if score >= 0.5:
        return "Moderate"
    return "Limited"


def _compose_top_quality_sentence(findings: List[StudyFindings], citations: Dict[str, CitationMetadata]) -> str:
    """Describe which studies provide the strongest evidence."""

    if not findings:
        return "No appraised studies were available to summarize."

    highlights = []
    for finding, key in zip(findings[:3], list(citations.keys())[:3]):
        citation = citations[key]
        descriptor = f"[{key}] {citation.title}"
        if citation.appraisal_score is not None:
            descriptor += f" (score {citation.appraisal_score:.2f}"
            if citation.appraisal_rating:
                descriptor += f", {citation.appraisal_rating}"
            descriptor += ")"
        elif citation.appraisal_rating:
            descriptor += f" ({citation.appraisal_rating})"
        highlights.append(descriptor)

    return "Top-rated evidence includes " + "; ".join(highlights) + "."


def _summarize_findings(findings: List[StudyFindings], citations: Dict[str, CitationMetadata]) -> str:
    """Provide a concise synthesis referencing citation keys."""

    if not findings:
        return "Insufficient evidence to address the research question."

    summaries = []
    for finding, key in zip(findings[:3], list(citations.keys())[:3]):
        snippet = _clean_text(finding.key_findings, 260)
        summaries.append(f"[{key}] {snippet}")

    return " ".join(summaries)


def _overall_evidence_strength(findings: List[StudyFindings]) -> str:
    """Compute overall evidence strength from quality ratings."""

    if not findings:
        return "Insufficient"

    high_quality = sum(1 for f in findings if (f.quality_score or 0) >= 0.75 or f.quality_rating == "Green")
    moderate_quality = sum(1 for f in findings if 0.5 <= (f.quality_score or 0) < 0.75 or f.quality_rating == "Amber")

    if high_quality >= 3:
        return "Strong"
    if high_quality >= 1 or moderate_quality >= 3:
        return "Moderate"
    if high_quality + moderate_quality > 0:
        return "Limited"
    return "Insufficient"


def _estimate_confidence_level(findings: List[StudyFindings]) -> str:
    """Estimate confidence in conclusions based on evidence mix."""

    if not findings:
        return "Low"

    strength = _overall_evidence_strength(findings)
    if strength == "Strong":
        return "High"
    if strength == "Moderate":
        return "Medium"
    return "Low"


def _describe_methodological_quality(findings: List[StudyFindings]) -> str:
    """Generate a short description of study quality distribution."""

    if not findings:
        return "No studies appraised."

    rating_counts: Dict[str, int] = {}
    for finding in findings:
        rating_counts[finding.quality_rating] = rating_counts.get(finding.quality_rating, 0) + 1

    parts = [f"{count} {rating}" for rating, count in sorted(rating_counts.items(), key=lambda x: x[0])]
    avg_score = [f.quality_score for f in findings if f.quality_score]
    avg_text = f"average appraisal score {sum(avg_score)/len(avg_score):.2f}" if avg_score else "no appraisal scores recorded"
    return "; ".join(parts) + f"; {avg_text}"


def _build_supporting_evidence(
    findings: List[StudyFindings],
    citations: Dict[str, CitationMetadata],
) -> List[EvidenceSupport]:
    """Create structured supporting evidence entries from high-quality studies."""

    evidence: List[EvidenceSupport] = []
    citation_keys = list(citations.keys())

    for finding, key in zip(findings[:5], citation_keys[:5]):
        quotes = [q.quote_text for q in (finding.supporting_quotes or []) if getattr(q, "quote_text", None)]
        if not quotes and finding.key_findings:
            quotes = [_clean_text(finding.key_findings, 220)]

        evidence.append(
            EvidenceSupport(
                finding=_clean_text(finding.key_findings, 320),
                supporting_quotes=quotes[:3],
                source_studies=[finding.title] if finding.title else [],
                strength_rating=_strength_from_quality(finding),
                citation_keys=[key],
                citations=[citations[key]],
            )
        )

    return evidence


def _build_fulltext_availability(
    findings: List[StudyFindings],
    citations: Dict[str, CitationMetadata],
) -> Dict[str, bool]:
    """Map citation keys and titles to full-text retrieval success."""

    availability: Dict[str, bool] = {}
    for finding, key in zip(findings, citations.keys()):
        has_fulltext = (
            finding.full_text_content is not None
            and finding.full_text_content.extraction_success
        )
        availability[f"[{key}] {finding.title}"] = has_fulltext

    return availability


def _derive_recommendations(findings: List[StudyFindings], citations: Dict[str, CitationMetadata]) -> List[str]:
    """Create actionable recommendations referencing strong studies."""

    recs: List[str] = []
    top_keys = list(citations.keys())[:3]
    if top_keys:
        recs.append(
            "Ground instructional design updates in the interventions tested in "
            + ", ".join(f"[{key}]" for key in top_keys)
            + " to mirror high-quality evidence."
        )

    if any(not finding.sample_size for finding in findings[:5]):
        recs.append("Report detailed learner characteristics and sample sizes to strengthen future appraisals.")

    if any((finding.supporting_quotes or []) for finding in findings[:5]):
        recs.append("Use direct participant quotes from high-quality studies to illustrate persuasive evidence in stakeholder communications.")

    while len(recs) < 3:
        defaults = [
            "Align interventions with learner needs and contextual factors documented across the literature.",
            "Monitor implementation fidelity when translating research-backed strategies into practice.",
            "Combine quantitative outcomes with qualitative feedback to capture comprehensive impact.",
        ]
        for item in defaults:
            if item not in recs:
                recs.append(item)
            if len(recs) >= 3:
                break

    return recs[:5]


def _derive_knowledge_gaps(findings: List[StudyFindings], citations: Dict[str, CitationMetadata]) -> List[str]:
    """Highlight gaps surfaced in the appraised literature."""

    gaps: List[str] = []
    contexts_missing = [
        (finding, key)
        for finding, key in zip(findings, citations.keys())
        if finding.lico_relevance.get("context", "Not specified") == "Not specified"
    ]
    if contexts_missing:
        keys = [f"[{key}]" for _, key in contexts_missing[:3]]
        gaps.append("Limited reporting on implementation contexts in " + ", ".join(keys) + ".")

    long_term_unknown = [
        (finding, key)
        for finding, key in zip(findings, citations.keys())
        if "long" in (finding.limitations or "").lower()
    ]
    if long_term_unknown:
        keys = [f"[{key}]" for _, key in long_term_unknown[:3]]
        gaps.append("Long-term outcome data remains sparse in " + ", ".join(keys) + ".")

    if not gaps:
        gaps = [
            "Need more diverse populations and settings to broaden generalizability.",
            "Few studies track sustained outcomes beyond immediate post-tests.",
        ]

    return gaps[:3]


def _derive_future_research(findings: List[StudyFindings], citations: Dict[str, CitationMetadata]) -> List[str]:
    """Suggest future research directions informed by limitations."""

    directions: List[str] = []
    if any(f.methodology == "Randomized Controlled Trial" for f in findings):
        directions.append("Replicate high-quality trials in varied educational settings to confirm effectiveness.")

    if any(not f.supporting_quotes for f in findings[:5]):
        directions.append("Pair quantitative outcomes with qualitative analyses to capture learner experience depth.")

    if not directions:
        directions = [
            "Conduct longitudinal studies to observe persistence of learning gains.",
            "Explore implementation factors that facilitate scaling of successful interventions.",
        ]

    return directions[:4]

def _parse_synthesis_response(
    response_text: str,
    findings: List[StudyFindings],
    supporting_quotes: List[SupportingQuote],
) -> ResearchSynthesis:
    """Parse AI response into structured ResearchSynthesis object."""

    ranked_findings = _rank_findings_by_quality(findings)
    citations = _build_citation_map(ranked_findings)

    cleaned_response = response_text.strip() if response_text else ""
    if cleaned_response.lower() == "mock response":
        cleaned_response = ""

    executive_summary_parts = []
    if cleaned_response:
        executive_summary_parts.append(_clean_text(cleaned_response, 1200))
    executive_summary_parts.append(_compose_top_quality_sentence(ranked_findings, citations))
    executive_summary = " ".join(part for part in executive_summary_parts if part)

    research_answer = _summarize_findings(ranked_findings, citations)

    supporting_evidence = _build_supporting_evidence(ranked_findings, citations)
    if not supporting_evidence and supporting_quotes:
        for quote, key in zip(supporting_quotes[:3], citations.keys()):
            supporting_evidence.append(
                EvidenceSupport(
                    finding=_clean_text(quote.quote_text, 200),
                    supporting_quotes=[quote.quote_text],
                    source_studies=[citations[key].title],
                    strength_rating="Moderate",
                    citation_keys=[key],
                    citations=[citations[key]],
                )
            )

    lico_insights = LICOInsights(
        learner_insights="; ".join(
            _clean_text(f.lico_relevance.get("learner"), 160) for f in ranked_findings[:3]
        ) or "Learner characteristics were variably reported.",
        intervention_insights="; ".join(
            _clean_text(f.lico_relevance.get("intervention"), 160) for f in ranked_findings[:3]
        ) or "Intervention details were limited across studies.",
        context_insights="; ".join(
            _clean_text(f.lico_relevance.get("context"), 160) for f in ranked_findings[:3]
        ) or "Contextual information was seldom provided.",
        outcome_insights="; ".join(
            _clean_text(f.lico_relevance.get("outcome"), 160) for f in ranked_findings[:3]
        ) or "Outcome reporting focused on immediate learning metrics.",
    )

    return ResearchSynthesis(
        executive_summary=executive_summary,
        research_question_answer=research_answer,
        lico_insights=lico_insights,
        evidence_strength=_overall_evidence_strength(ranked_findings),
        confidence_level=_estimate_confidence_level(ranked_findings),
        key_recommendations=_derive_recommendations(ranked_findings, citations),
        knowledge_gaps=_derive_knowledge_gaps(ranked_findings, citations),
        methodological_quality=_describe_methodological_quality(ranked_findings),
        future_research_directions=_derive_future_research(ranked_findings, citations),
        supporting_evidence=supporting_evidence,
        full_text_availability=_build_fulltext_availability(ranked_findings, citations),
        study_citations=citations,
    )

def _generate_fallback_synthesis(findings: List[StudyFindings], research_question: str) -> ResearchSynthesis:
    """Generate basic synthesis when AI fails"""
    ranked_findings = _rank_findings_by_quality(findings)
    citations = _build_citation_map(ranked_findings)

    executive_summary = (
        f"Analysis of {len(findings)} appraised studies informs the research question. "
        + _compose_top_quality_sentence(ranked_findings, citations)
    )

    return ResearchSynthesis(
        executive_summary=executive_summary,
        research_question_answer=_summarize_findings(ranked_findings, citations),
        lico_insights=LICOInsights(
            learner_insights="; ".join(
                _clean_text(f.lico_relevance.get("learner"), 160) for f in ranked_findings[:3]
            ) or "Learner characteristics were variably reported.",
            intervention_insights="; ".join(
                _clean_text(f.lico_relevance.get("intervention"), 160) for f in ranked_findings[:3]
            ) or "Intervention details were limited across studies.",
            context_insights="; ".join(
                _clean_text(f.lico_relevance.get("context"), 160) for f in ranked_findings[:3]
            ) or "Contextual information was seldom provided.",
            outcome_insights="; ".join(
                _clean_text(f.lico_relevance.get("outcome"), 160) for f in ranked_findings[:3]
            ) or "Outcome reporting focused on immediate learning metrics.",
        ),
        evidence_strength=_overall_evidence_strength(ranked_findings),
        confidence_level=_estimate_confidence_level(ranked_findings),
        key_recommendations=_derive_recommendations(ranked_findings, citations),
        knowledge_gaps=_derive_knowledge_gaps(ranked_findings, citations),
        methodological_quality=_describe_methodological_quality(ranked_findings),
        future_research_directions=_derive_future_research(ranked_findings, citations),
        supporting_evidence=_build_supporting_evidence(ranked_findings, citations),
        full_text_availability=_build_fulltext_availability(ranked_findings, citations),
        study_citations=citations,
    )
