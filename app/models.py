# app/models.py
from __future__ import annotations
from typing import List, Dict, Optional, Literal
from pydantic import BaseModel

class PressPlan(BaseModel):
    concepts: List[str]
    boolean: str
    sources: List[str]         # ["PubMed","ERIC","Crossref","arXiv", ...]
    years: str                 # e.g., "2019-"

class RecordModel(BaseModel):
    # Core fields (always required)
    record_id: str
    title: str
    abstract: Optional[str] = None
    authors: Optional[str] = None  # Comma-separated author names
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    source: str
    publication_type: Optional[str] = None  # Journal Article, Conference Paper, etc.
    
    # Extended metadata fields (optional)
    journal: Optional[str] = None
    conference: Optional[str] = None
    publisher: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    
    # Language and location
    language: Optional[str] = None
    country: Optional[str] = None
    
    # Additional identifiers
    pmid: Optional[str] = None         # PubMed ID
    arxiv_id: Optional[str] = None     # arXiv identifier  
    issn: Optional[str] = None         # Journal ISSN
    isbn: Optional[str] = None         # Book ISBN
    
    # Subject classification
    subjects: Optional[str] = None     # Subject headings/keywords (comma-separated)
    mesh_terms: Optional[str] = None   # Medical Subject Headings (comma-separated)
    
    # Full-text availability
    pdf_url: Optional[str] = None      # Direct PDF URL
    fulltext_url: Optional[str] = None # Full-text HTML URL
    open_access: Optional[bool] = None # Open access status
    
    # Citation information
    cited_by_count: Optional[int] = None
    reference_count: Optional[int] = None

class Criteria(BaseModel):
    include: List[str] = []
    exclude: List[str] = []

class ScreeningModel(BaseModel):
    record_id: str
    decision: Literal["include","exclude"]
    reason: Optional[str] = ""

class AppraisalModel(BaseModel):
    record_id: str
    rating: Literal["Red","Amber","Green"]
    scores: Dict[str, float]
    rationale: str
    citations: List[str] = []

class PrismaCountsModel(BaseModel):
    identified:int=0
    deduped:int=0
    screened:int=0
    excluded:int=0
    eligible:int=0
    included:int=0

class PrismaReport(BaseModel):
    counts: PrismaCountsModel
    exclude_reason_counts: Dict[str,int] = {}
