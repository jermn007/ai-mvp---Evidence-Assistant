# app/publication_classifier.py
"""
AI-powered publication type classification for academic records.
Uses OpenAI to analyze titles, abstracts, and metadata to determine publication types.
"""

import os
import logging
from typing import Optional, Dict, Any
import openai

logger = logging.getLogger("ai_mvp.publication_classifier")

# Configure OpenAI client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def classify_publication_type(
    title: str,
    abstract: Optional[str] = None,
    source: Optional[str] = None,
    url: Optional[str] = None,
    doi: Optional[str] = None
) -> str:
    """
    Classify publication type using AI analysis of metadata.
    
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
    if source:
        source_lower = source.lower()
        if "arxiv" in source_lower:
            return "Preprint"
        elif "pubmed" in source_lower:
            return "Journal Article"
        elif source_lower in ["eric"]:
            # ERIC contains mixed types, need AI analysis
            pass
        elif "scholar" in source_lower:
            # Google Scholar contains mixed types, need AI analysis
            pass
    
    # URL-based hints
    if url:
        url_lower = url.lower()
        if "arxiv.org" in url_lower:
            return "Preprint"
        elif "pubmed" in url_lower:
            return "Journal Article"
        elif any(conf in url_lower for conf in ["proceedings", "conference", "acm.org", "ieee.org"]):
            return "Conference Paper"
    
    # DOI-based hints
    if doi and doi.startswith("10."):
        # Most DOIs are for journal articles, but let AI refine
        pass
    
    # If no clear indicators, use AI classification
    try:
        return _ai_classify_publication_type(title, abstract, source, url, doi)
    except Exception as e:
        logger.warning(f"AI classification failed: {e}. Using source-based fallback.")
        return _fallback_classification(source)

def _ai_classify_publication_type(
    title: str,
    abstract: Optional[str] = None,
    source: Optional[str] = None,
    url: Optional[str] = None,
    doi: Optional[str] = None
) -> str:
    """Use OpenAI to classify publication type based on content analysis."""
    
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
    
    prompt = f"""Analyze this academic publication and classify its type based on the content, source, and metadata.

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

Return only one of these exact classification labels."""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert librarian specializing in academic publication classification."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=50,
            temperature=0.1
        )
        
        classification = response.choices[0].message.content.strip()
        
        # Validate the response matches expected categories
        valid_types = {
            "Journal Article", "Conference Paper", "Preprint", "Book Chapter",
            "Thesis/Dissertation", "Technical Report", "Review Article", 
            "Editorial", "Case Study", "Unknown"
        }
        
        if classification in valid_types:
            return classification
        else:
            logger.warning(f"AI returned unexpected classification: {classification}")
            return "Unknown"
            
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
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

def batch_classify_publications(records: list[Dict[str, Any]]) -> Dict[str, str]:
    """
    Classify multiple publications in batch for efficiency.
    Returns mapping of record_id to publication_type.
    """
    classifications = {}
    
    for record in records:
        record_id = record.get("record_id", "")
        if not record_id:
            continue
            
        try:
            pub_type = classify_publication_type(
                title=record.get("title", ""),
                abstract=record.get("abstract"),
                source=record.get("source"),
                url=record.get("url"),
                doi=record.get("doi")
            )
            classifications[record_id] = pub_type
            
        except Exception as e:
            logger.error(f"Classification failed for {record_id}: {e}")
            classifications[record_id] = "Unknown"
    
    return classifications