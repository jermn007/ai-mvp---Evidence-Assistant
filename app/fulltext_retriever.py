# app/fulltext_retriever.py
"""
Full-text article retrieval and quote extraction system
Downloads PDFs and extracts key passages to support AI-generated findings
"""

import os
import logging
import requests
import tempfile
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
import re
from urllib.parse import urlparse

# PDF processing
try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logging.warning("PyPDF2 not available - PDF processing disabled")

# Additional text extraction libraries
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

logger = logging.getLogger("ai_mvp.fulltext_retriever")

@dataclass
class FullTextContent:
    """Container for full-text article content"""
    record_id: str
    title: str
    full_text: str
    source_type: str  # 'pdf', 'html', 'api'
    key_passages: List[str]
    word_count: int
    extraction_success: bool
    error_message: Optional[str] = None

@dataclass 
class SupportingQuote:
    """A direct quote with context"""
    quote_text: str
    context: str  # Surrounding context
    page_number: Optional[int] = None
    section: Optional[str] = None  # Methods, Results, etc.
    relevance_score: float = 0.0

class FullTextRetriever:
    """Retrieves and processes full-text articles"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
    def retrieve_fulltext(self, record: Dict[str, any]) -> FullTextContent:
        """Attempt to retrieve full text for a record"""
        record_id = record.get('record_id', 'unknown')
        title = record.get('title', 'Unknown')
        doi = record.get('doi')
        url = record.get('url')
        
        logger.info(f"Attempting full-text retrieval for: {title}")
        
        # Try multiple retrieval strategies in order of preference
        strategies = [
            self._try_doi_resolution,
            self._try_direct_pdf_download,
            self._try_open_access_repositories,
            self._try_publisher_api
        ]
        
        for strategy in strategies:
            try:
                result = strategy(record_id, title, doi, url)
                if result and result.extraction_success:
                    logger.info(f"Successfully retrieved full text via {strategy.__name__}")
                    return result
            except Exception as e:
                logger.warning(f"{strategy.__name__} failed for {record_id}: {e}")
                continue
        
        # Return failed result with abstract fallback
        abstract = record.get('abstract', '')
        return FullTextContent(
            record_id=record_id,
            title=title,
            full_text=abstract,
            source_type='abstract_only',
            key_passages=[abstract] if abstract else [],
            word_count=len(abstract.split()) if abstract else 0,
            extraction_success=False,
            error_message="Could not retrieve full text - using abstract only"
        )
    
    def _try_doi_resolution(self, record_id: str, title: str, doi: str, url: str) -> Optional[FullTextContent]:
        """Try to get full text via DOI resolution"""
        if not doi:
            return None
            
        # Try Unpaywall API for open access PDFs
        unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email=research@example.org"
        
        try:
            response = self.session.get(unpaywall_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('is_oa') and data.get('best_oa_location'):
                    pdf_url = data['best_oa_location'].get('url_for_pdf')
                    if pdf_url:
                        return self._download_and_extract_pdf(record_id, title, pdf_url)
        except Exception as e:
            logger.warning(f"Unpaywall API failed for {doi}: {e}")
        
        return None
    
    def _try_direct_pdf_download(self, record_id: str, title: str, doi: str, url: str) -> Optional[FullTextContent]:
        """Try direct PDF download from URL"""
        if not url:
            return None
            
        # Check if URL might be a PDF
        if url.lower().endswith('.pdf') or 'pdf' in url.lower():
            return self._download_and_extract_pdf(record_id, title, url)
        
        # Try adding .pdf to certain repository URLs
        pdf_variants = [
            url + '.pdf',
            url.replace('/abs/', '/pdf/') + '.pdf',  # arXiv pattern
        ]
        
        for pdf_url in pdf_variants:
            try:
                result = self._download_and_extract_pdf(record_id, title, pdf_url)
                if result and result.extraction_success:
                    return result
            except:
                continue
                
        return None
    
    def _try_open_access_repositories(self, record_id: str, title: str, doi: str, url: str) -> Optional[FullTextContent]:
        """Try open access repositories like PMC, arXiv"""
        
        # PubMed Central
        if 'pubmed' in (url or '').lower():
            pmc_id = self._extract_pmc_id(url)
            if pmc_id:
                return self._fetch_pmc_fulltext(record_id, title, pmc_id)
        
        # arXiv
        if 'arxiv' in (url or '').lower():
            return self._fetch_arxiv_fulltext(record_id, title, url)
        
        return None
    
    def _try_publisher_api(self, record_id: str, title: str, doi: str, url: str) -> Optional[FullTextContent]:
        """Try publisher APIs (limited without subscriptions)"""
        # This would require API keys for various publishers
        # For now, return None - can be expanded later
        return None
    
    def _download_and_extract_pdf(self, record_id: str, title: str, pdf_url: str) -> Optional[FullTextContent]:
        """Download PDF and extract text"""
        if not PDF_AVAILABLE and not PDFPLUMBER_AVAILABLE:
            logger.warning("No PDF processing libraries available")
            return None
        
        try:
            # Download PDF
            response = self.session.get(pdf_url, timeout=30)
            response.raise_for_status()
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                tmp_file.write(response.content)
                tmp_path = tmp_file.name
            
            try:
                # Extract text using best available method
                if PDFPLUMBER_AVAILABLE:
                    full_text = self._extract_text_pdfplumber(tmp_path)
                else:
                    full_text = self._extract_text_pypdf2(tmp_path)
                
                if full_text and len(full_text.strip()) > 100:
                    key_passages = self._extract_key_passages(full_text)
                    
                    return FullTextContent(
                        record_id=record_id,
                        title=title,
                        full_text=full_text,
                        source_type='pdf',
                        key_passages=key_passages,
                        word_count=len(full_text.split()),
                        extraction_success=True
                    )
            finally:
                # Clean up temp file
                try:
                    os.unlink(tmp_path)
                except:
                    pass
                    
        except Exception as e:
            logger.warning(f"PDF download/extraction failed for {pdf_url}: {e}")
        
        return None
    
    def _extract_text_pdfplumber(self, pdf_path: str) -> str:
        """Extract text using pdfplumber (more accurate)"""
        import pdfplumber
        
        text_content = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_content.append(text)
        
        return '\n\n'.join(text_content)
    
    def _extract_text_pypdf2(self, pdf_path: str) -> str:
        """Extract text using PyPDF2 (fallback)"""
        import PyPDF2
        
        text_content = []
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    text_content.append(text)
        
        return '\n\n'.join(text_content)
    
    def _extract_key_passages(self, full_text: str) -> List[str]:
        """Extract key passages from full text"""
        # Split into sections
        sections = self._identify_sections(full_text)
        
        key_passages = []
        
        # Prioritize certain sections
        priority_sections = ['abstract', 'results', 'conclusion', 'discussion', 'findings']
        
        for section_name in priority_sections:
            if section_name in sections:
                section_text = sections[section_name]
                # Extract meaningful paragraphs (> 50 words)
                paragraphs = [p.strip() for p in section_text.split('\n\n') if len(p.split()) > 50]
                key_passages.extend(paragraphs[:3])  # Top 3 paragraphs per section
        
        # If no key passages found, extract from beginning
        if not key_passages:
            paragraphs = [p.strip() for p in full_text.split('\n\n') if len(p.split()) > 50]
            key_passages = paragraphs[:5]  # First 5 meaningful paragraphs
        
        return key_passages[:10]  # Limit to 10 passages
    
    def _identify_sections(self, text: str) -> Dict[str, str]:
        """Identify paper sections using headers"""
        sections = {}
        
        # Common section headers
        headers = [
            (r'\b(?:abstract|summary)\b', 'abstract'),
            (r'\b(?:introduction|background)\b', 'introduction'),
            (r'\b(?:methods?|methodology)\b', 'methods'),
            (r'\b(?:results?|findings)\b', 'results'),
            (r'\b(?:discussion|interpretation)\b', 'discussion'),
            (r'\b(?:conclusions?|summary)\b', 'conclusion'),
            (r'\b(?:limitations|constraints)\b', 'limitations')
        ]
        
        text_lower = text.lower()
        lines = text.split('\n')
        
        current_section = 'body'
        current_content = []
        
        for line in lines:
            line_lower = line.lower().strip()
            
            # Check if this line is a section header
            section_found = None
            for pattern, section_name in headers:
                if re.search(pattern, line_lower) and len(line.strip()) < 50:
                    section_found = section_name
                    break
            
            if section_found:
                # Save previous section
                if current_content:
                    sections[current_section] = '\n'.join(current_content)
                # Start new section
                current_section = section_found
                current_content = []
            else:
                current_content.append(line)
        
        # Save last section
        if current_content:
            sections[current_section] = '\n'.join(current_content)
        
        return sections
    
    def _extract_pmc_id(self, url: str) -> Optional[str]:
        """Extract PMC ID from PubMed URL"""
        if not url:
            return None
        
        # Look for PMC pattern
        match = re.search(r'PMC(\d+)', url)
        if match:
            return f"PMC{match.group(1)}"
        
        return None
    
    def _fetch_pmc_fulltext(self, record_id: str, title: str, pmc_id: str) -> Optional[FullTextContent]:
        """Fetch full text from PMC"""
        try:
            # PMC provides XML and PDF access
            pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/"
            return self._download_and_extract_pdf(record_id, title, pdf_url)
        except Exception as e:
            logger.warning(f"PMC retrieval failed for {pmc_id}: {e}")
        
        return None
    
    def _fetch_arxiv_fulltext(self, record_id: str, title: str, url: str) -> Optional[FullTextContent]:
        """Fetch full text from arXiv"""
        try:
            # Convert arXiv URL to PDF URL
            if '/abs/' in url:
                pdf_url = url.replace('/abs/', '/pdf/') + '.pdf'
            else:
                # Extract arXiv ID and construct PDF URL
                match = re.search(r'(\d{4}\.\d{4})', url)
                if match:
                    arxiv_id = match.group(1)
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                else:
                    return None
            
            return self._download_and_extract_pdf(record_id, title, pdf_url)
        except Exception as e:
            logger.warning(f"arXiv retrieval failed for {url}: {e}")
        
        return None

def extract_supporting_quotes(full_text_content: FullTextContent, findings_to_support: List[str]) -> List[SupportingQuote]:
    """Extract direct quotes that support specific findings"""
    if not full_text_content.extraction_success:
        return []
    
    quotes = []
    text = full_text_content.full_text
    
    for finding in findings_to_support:
        # Find passages that relate to this finding
        supporting_passages = find_relevant_passages(text, finding)
        
        for passage, score in supporting_passages:
            quote = SupportingQuote(
                quote_text=passage,
                context=get_surrounding_context(text, passage),
                relevance_score=score
            )
            quotes.append(quote)
    
    # Sort by relevance and return top quotes
    quotes.sort(key=lambda x: x.relevance_score, reverse=True)
    return quotes[:5]  # Top 5 most relevant quotes

def find_relevant_passages(text: str, finding: str) -> List[Tuple[str, float]]:
    """Find text passages relevant to a specific finding"""
    import difflib
    
    sentences = re.split(r'[.!?]+', text)
    relevant_passages = []
    
    finding_words = set(finding.lower().split())
    
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence.split()) < 10:  # Skip very short sentences
            continue
        
        sentence_words = set(sentence.lower().split())
        
        # Calculate word overlap
        overlap = len(finding_words.intersection(sentence_words))
        if overlap >= 2:  # At least 2 words in common
            similarity_score = overlap / len(finding_words)
            
            # Boost score for certain keywords
            if any(word in sentence.lower() for word in ['significant', 'effective', 'improved', 'increased', 'decreased']):
                similarity_score += 0.2
            
            relevant_passages.append((sentence, similarity_score))
    
    return sorted(relevant_passages, key=lambda x: x[1], reverse=True)[:3]

def get_surrounding_context(text: str, passage: str, context_window: int = 100) -> str:
    """Get surrounding context for a passage"""
    passage_start = text.find(passage)
    if passage_start == -1:
        return passage
    
    start = max(0, passage_start - context_window)
    end = min(len(text), passage_start + len(passage) + context_window)
    
    context = text[start:end]
    
    # Clean up context boundaries
    if start > 0:
        context = '...' + context
    if end < len(text):
        context = context + '...'
    
    return context