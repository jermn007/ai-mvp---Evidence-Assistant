from __future__ import annotations
from typing import TypedDict, List, Dict
from app.models import (
    PressPlan, RecordModel, ScreeningModel, AppraisalModel, PrismaCountsModel
)

class AgentState(TypedDict, total=False):
    run_id: str
    query: str
    press: PressPlan
    records: List[RecordModel]
    screenings: List[ScreeningModel]
    appraisals: List[AppraisalModel]
    prisma: PrismaCountsModel
    seen_external_ids: List[str]          # thread-level memory
    source_counts: Dict[str, int]         # <-- NEW
    timings: Dict[str, float]             # <-- NEW (seconds)
    max_results_per_source: int
    search_mode: str
