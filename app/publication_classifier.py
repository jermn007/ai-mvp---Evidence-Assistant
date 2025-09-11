# app/publication_classifier.py
"""
AI-powered publication type classification for academic records.
Uses LangChain and centralized LLM factory to analyze titles, abstracts, and metadata.
"""

import logging
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.language_models import BaseChatModel

logger = logging.getLogger("ai_mvp.publication_classifier")

class PublicationClassification(BaseModel):
    """Structured publication classification result"""
    publication_type: str = Field(description="The classified publication type")
    confidence: float = Field(description="Confidence score from 0.0 to 1.0")
    reasoning: str = Field(description="Brief explanation for the classification")

async def classify_publication_type(
    title: str,
    abstract: Optional[str] = None,
    source: Optional[str] = None,
    url: Optional[str] = None,
    doi: Optional[str] = None,
    use_ai: bool = True
) -> str:
    """
    Classify publication type using rule-based and AI analysis.
    
    Returns one of:
    - Journal Article
    - Conference Paper  
    - Preprint
    - Book Chapter
    - Thesis/Dissertation
    - Technical Report
    - Review Article
    - Editorial
    - Case Study
    - Unknown
    """
    
    # Quick rule-based classification for obvious cases
    rule_based_result = _rule_based_classification(title, source, url, doi)
    if rule_based_result != "Unknown":
        return rule_based_result
    
    # Use AI classification if enabled and available
    if use_ai:
        try:
            ai_result = await _ai_classify_publication_type(title, abstract, source, url, doi)
            if ai_result and ai_result.publication_type != "Unknown":
                logger.debug(f"AI classified as {ai_result.publication_type} with confidence {ai_result.confidence}")
                return ai_result.publication_type
        except Exception as e:
            logger.warning(f"AI classification failed: {e}. Using fallback.")
    
    # Fallback to source-based classification
    return _fallback_classification(source)

def _rule_based_classification(
    title: str,
    source: Optional[str] = None,
    url: Optional[str] = None,
    doi: Optional[str] = None
) -> str:
    """Apply rule-based classification for obvious cases"""
    
    # Source-based classification
    if source:
        source_lower = (source or "").lower()
        if "arxiv" in source_lower:
            return "Preprint"
        elif "pubmed" in source_lower:
            return "Journal Article"
    
    # URL-based classification
    if url:
        url_lower = (url or "").lower()
        if "arxiv.org" in url_lower:
            return "Preprint"
        elif "pubmed" in url_lower:
            return "Journal Article"
        elif any(conf in url_lower for conf in ["proceedings", "conference", "acm.org", "ieee.org"]):
            return "Conference Paper"
    
    # Title-based patterns
    title_lower = (title or "").lower()
    if any(pattern in title_lower for pattern in ["proceedings of", "conference on", "workshop on"]):
        return "Conference Paper"
    elif any(pattern in title_lower for pattern in ["review of", "systematic review", "meta-analysis"]):
        return "Review Article"
    elif any(pattern in title_lower for pattern in ["editorial", "letter to"]):
        return "Editorial"
    
    return "Unknown"

async def _ai_classify_publication_type(
    title: str,
    abstract: Optional[str] = None,
    source: Optional[str] = None,
    url: Optional[str] = None,
    doi: Optional[str] = None
) -> Optional[PublicationClassification]:
    """Use LangChain to classify publication type based on content analysis."""
    from app.llm_factory import get_fast_model, is_llm_available
    
    if not is_llm_available():
        logger.warning("LLM not available for publication classification")
        return None
    
    # Prepare context for AI
    context_parts = [f"Title: {title}"]
    
    if abstract:
        # Limit abstract length to avoid token limits
        abstract_snippet = abstract[:500] + "..." if len(abstract) > 500 else abstract
        context_parts.append(f"Abstract: {abstract_snippet}")
    
    if source:
        context_parts.append(f"Source: {source}")
    
    if url:
        context_parts.append(f"URL: {url}")
    
    if doi:
        context_parts.append(f"DOI: {doi}")
    
    context = "\n".join(context_parts)
    
    # Create LangChain prompt template
    system_prompt = """You are an expert librarian specializing in academic publication classification.
    Analyze the provided publication metadata and classify its type with confidence and reasoning."""
    
    human_prompt = """Analyze this academic publication and classify its type:

{context}

Classification Guidelines:
- Journal Article: Peer-reviewed research published in academic journals
- Conference Paper: Research presented at academic conferences or symposiums  
- Preprint: Draft manuscripts not yet peer-reviewed (e.g., arXiv, bioRxiv)
- Book Chapter: Section of an academic book or edited volume
- Thesis/Dissertation: Graduate student research work
- Technical Report: Government, industry, or institutional research reports
- Review Article: Systematic reviews, meta-analyses, literature surveys
- Editorial: Opinion pieces, commentaries, letters to editors
- Case Study: Detailed analysis of specific cases or examples
- Unknown: If type cannot be determined from available information

Provide your response as JSON with:
- publication_type: One of the exact classification labels above
- confidence: A score from 0.0 to 1.0 indicating your confidence
- reasoning: Brief explanation for your classification decision"""

    try:
        # Get fast model for simple classification
        model = get_fast_model(temperature=0.1, max_tokens=200)
        
        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", human_prompt)
        ])
        
        # Create output parser
        parser = JsonOutputParser(pydantic_object=PublicationClassification)
        
        # Create chain
        chain = prompt | model | parser
        
        # Execute classification
        result = await chain.ainvoke({"context": context})
        
        # Validate result
        if isinstance(result, dict):
            classification = PublicationClassification(**result)
        else:
            classification = result
            
        # Validate publication type
        valid_types = {
            "Journal Article", "Conference Paper", "Preprint", "Book Chapter",
            "Thesis/Dissertation", "Technical Report", "Review Article", 
            "Editorial", "Case Study", "Unknown"
        }
        
        if classification.publication_type not in valid_types:
            logger.warning(f"AI returned unexpected classification: {classification.publication_type}")
            classification.publication_type = "Unknown"
            classification.confidence = 0.0
            
        return classification
        
    except Exception as e:
        logger.error(f"LangChain classification failed: {e}")
        raise

def _fallback_classification(source: Optional[str] = None) -> str:
    """Fallback classification based on source when AI fails."""
    if not source:
        return "Unknown"
    
    source_lower = source.lower()
    if "pubmed" in source_lower:
        return "Journal Article"
    elif "arxiv" in source_lower:
        return "Preprint"
    elif "crossref" in source_lower:
        return "Journal Article"  # Most crossref content is journal articles
    elif "eric" in source_lower:
        return "Journal Article"  # ERIC is primarily education journals
    elif "scholar" in source_lower:
        return "Journal Article"  # Default assumption for Scholar results
    else:
        return "Unknown"

async def batch_classify_publications(records: List[Dict[str, Any]], use_ai: bool = True) -> Dict[str, str]:
    """
    Classify multiple publications in batch for efficiency.
    Returns mapping of record_id to publication_type.
    """
    import asyncio
    
    classifications = {}
    
    # Create classification tasks
    tasks = []
    record_ids = []
    
    for record in records:
        record_id = record.get("record_id", "")
        if not record_id:
            continue
            
        record_ids.append(record_id)
        task = classify_publication_type(
            title=record.get("title", ""),
            abstract=record.get("abstract"),
            source=record.get("source"),
            url=record.get("url"),
            doi=record.get("doi"),
            use_ai=use_ai
        )
        tasks.append(task)
    
    # Execute all classifications concurrently
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for record_id, result in zip(record_ids, results):
            if isinstance(result, Exception):
                logger.error(f"Classification failed for {record_id}: {result}")
                classifications[record_id] = "Unknown"
            else:
                classifications[record_id] = result
                
    except Exception as e:
        logger.error(f"Batch classification failed: {e}")
        # Fallback to sequential processing
        for record_id in record_ids:
            classifications[record_id] = "Unknown"
    
    return classifications

# Synchronous wrapper for backward compatibility
def batch_classify_publications_sync(records: List[Dict[str, Any]], use_ai: bool = True) -> Dict[str, str]:
    """
    Synchronous wrapper for batch classification.
    Use this when calling from non-async contexts.
    """
    import asyncio
    
    try:
        # Create new event loop if none exists
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        return loop.run_until_complete(batch_classify_publications(records, use_ai))
    except RuntimeError:
        # If we're already in an async context, create a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                lambda: asyncio.run(batch_classify_publications(records, use_ai))
            )
            return future.result()