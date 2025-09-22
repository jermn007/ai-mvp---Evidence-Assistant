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
    full_text_content: Optional[FullTextContent] = None
    supporting_quotes: List[SupportingQuote] = None

class LICOInsights(BaseModel):
    """Structured insights for each LICO component"""
    learner_insights: str = Field(description="Evidence about target learners")
    intervention_insights: str = Field(description="Evidence about intervention effectiveness")
    context_insights: str = Field(description="Evidence about contextual factors")
    outcome_insights: str = Field(description="Evidence about learning outcomes")

class EvidenceSupport(BaseModel):
    """Supporting evidence with direct quotes"""
    finding: str = Field(description="The specific finding or claim")
    supporting_quotes: List[str] = Field(description="Direct quotes from literature")
    source_studies: List[str] = Field(description="Studies providing this evidence")
    strength_rating: str = Field(description="Strength of supporting evidence")

class ResearchSynthesis(BaseModel):
    """Comprehensive research synthesis response"""
    executive_summary: str = Field(description="High-level synthesis of all findings")
    research_question_answer: str = Field(description="Direct answer to the original research question")
    lico_insights: LICOInsights = Field(description="Detailed insights for each LICO component")
    evidence_strength: str = Field(description="Overall strength of evidence: Strong, Moderate, Limited, Insufficient")
    confidence_level: str = Field(description="Confidence in conclusions: High, Medium, Low")
    key_recommendations: List[str] = Field(description="Actionable recommendations for instructional designers")
    knowledge_gaps: List[str] = Field(description="Identified gaps in current research")
    methodological_quality: str = Field(description="Overall assessment of study quality")
    future_research_directions: List[str] = Field(description="Suggested areas for future investigation")
    supporting_evidence: List[EvidenceSupport] = Field(description="Key findings with direct quotes and citations")
    full_text_availability: Dict[str, bool] = Field(description="Which studies had full text available")

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
            record_id=record.get('record_id'),
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
            full_text_availability={}
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

def _parse_synthesis_response(response_text: str, findings: List[StudyFindings], supporting_quotes: List[SupportingQuote]) -> ResearchSynthesis:
    """Parse AI response into structured ResearchSynthesis object"""
    
    # Create supporting evidence with quotes
    supporting_evidence = []
    if supporting_quotes:
        # Group quotes by theme
        for quote in supporting_quotes[:5]:  # Top 5 quotes
            evidence = EvidenceSupport(
                finding=quote.quote_text[:100] + "...",
                supporting_quotes=[quote.quote_text],
                source_studies=[f.title for f in findings if f.supporting_quotes and quote in f.supporting_quotes][:3],
                strength_rating="Strong" if quote.relevance_score > 0.7 else "Moderate" if quote.relevance_score > 0.4 else "Limited"
            )
            supporting_evidence.append(evidence)
    
    # Track which studies had full text
    fulltext_availability = {}
    for finding in findings:
        key = finding.record_id or finding.title
        fulltext_availability[key] = (
            finding.full_text_content is not None and
            finding.full_text_content.extraction_success
        )
    
    # Default structured response with enhanced evidence support
    return ResearchSynthesis(
        executive_summary=response_text[:500] + "..." if len(response_text) > 500 else response_text,
        research_question_answer="Based on the available evidence, " + response_text[500:1000] if len(response_text) > 1000 else response_text,
        lico_insights=LICOInsights(
            learner_insights="Evidence suggests diverse learner populations were studied with varying characteristics and needs.",
            intervention_insights="Multiple intervention approaches were evaluated, showing varied effectiveness across contexts.",
            context_insights="Various educational contexts were examined, from traditional classrooms to online environments.",
            outcome_insights="Positive learning outcomes were generally reported, including knowledge gains and skill development."
        ),
        evidence_strength="Strong" if len([f for f in findings if f.quality_rating == 'Green']) >= 5 else "Moderate",
        confidence_level="High" if len(supporting_quotes) > 10 else "Medium",
        key_recommendations=[
            "Base instructional design decisions on evidence from high-quality studies",
            "Consider learner characteristics when designing interventions",
            "Adapt interventions to specific educational contexts",
            "Measure multiple outcome indicators for comprehensive assessment",
            "Use evidence-based instructional strategies with proven effectiveness"
        ],
        knowledge_gaps=["More diverse populations needed", "Long-term outcomes unclear", "Implementation fidelity measures lacking"],
        methodological_quality=f"Mixed quality: {len([f for f in findings if f.quality_rating == 'Green'])} high-quality studies",
        future_research_directions=[
            "Longitudinal studies to assess lasting impact",
            "More rigorous experimental designs",
            "Cross-cultural validation studies",
            "Implementation research in authentic settings"
        ],
        supporting_evidence=supporting_evidence,
        full_text_availability=fulltext_availability
    )

def _generate_fallback_synthesis(findings: List[StudyFindings], research_question: str) -> ResearchSynthesis:
    """Generate basic synthesis when AI fails"""
    high_quality = [f for f in findings if f.quality_rating == 'Green']
    medium_quality = [f for f in findings if f.quality_rating == 'Amber']
    fulltext_availability = {
        (f.record_id or f.title): (
            f.full_text_content is not None and getattr(f.full_text_content, "extraction_success", False)
        )
        for f in findings
    }

    return ResearchSynthesis(
        executive_summary=f"Analysis of {len(findings)} studies reveals mixed evidence on the research question. {len(high_quality)} high-quality and {len(medium_quality)} medium-quality studies provide relevant insights.",
        research_question_answer="The current evidence provides preliminary insights but requires more high-quality research for definitive conclusions.",
        lico_insights=LICOInsights(
            learner_insights="Multiple learner populations represented in the literature.",
            intervention_insights="Various intervention approaches have been studied.",
            context_insights="Different educational contexts examined.",
            outcome_insights="Positive outcomes generally reported."
        ),
        evidence_strength="Limited" if len(high_quality) < 3 else "Moderate",
        confidence_level="Medium",
        key_recommendations=[
            "Base decisions on highest quality evidence available",
            "Consider context-specific factors",
            "Monitor outcomes carefully"
        ],
        knowledge_gaps=["More high-quality studies needed"],
        methodological_quality=f"Mixed ({len(high_quality)} high-quality studies)",
        future_research_directions=["Rigorous experimental studies needed"],
        supporting_evidence=[],
        full_text_availability=fulltext_availability
    )
