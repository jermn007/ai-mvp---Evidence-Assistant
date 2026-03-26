# app/press_contract.py
from __future__ import annotations
from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field

class LICO(BaseModel):
    learner: str
    intervention: str
    context: str
    outcome: str

class DatabaseSpec(BaseModel):
    name: str            # e.g., "MEDLINE"
    interface: str       # e.g., "PubMed"

class StrategyLine(BaseModel):
    n: int
    type: Literal["Learner","Intervention","Context","Outcome","Combine","Limits","MeSH","Text"]
    text: str
    hits: Optional[int] = None   # filled later by a runner if you want

class PressStrategy(BaseModel):
    database: str
    interface: str
    lines: List[StrategyLine]

class PressChecklist(BaseModel):
    translation: Literal["pass","suggest","revise"]
    subject_headings: Literal["pass","suggest","revise"]
    text_words: Literal["pass","suggest","revise"]
    spelling_syntax_lines: Literal["pass","suggest","revise"]
    limits_filters: Literal["pass","suggest","revise"]
    notes: Optional[str] = None

class PressPlanResponse(BaseModel):
    question_lico: LICO
    strategies: Dict[str, PressStrategy]  # keyed by db name
    checklist: Dict[str, PressChecklist]  # keyed by db name
