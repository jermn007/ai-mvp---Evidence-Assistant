# app/db.py
from __future__ import annotations
import os, json, uuid, datetime as dt
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    create_engine, Column, String, Integer, Text, DateTime, ForeignKey, Float
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DB_URL = os.getenv("DATABASE_URL", "sqlite:///app.db")
engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()

def gen_id() -> str:
    return str(uuid.uuid4())

class SearchRun(Base):
    __tablename__ = "search_runs"
    id = Column(String, primary_key=True, default=gen_id)
    query = Column(Text, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    records = relationship("Record", back_populates="run", cascade="all, delete-orphan")
    appraisals = relationship("Appraisal", back_populates="run", cascade="all, delete-orphan")
    prisma = relationship("PrismaCounts", back_populates="run", uselist=False, cascade="all, delete-orphan")

class Record(Base):
    __tablename__ = "records"
    id = Column(String, primary_key=True, default=gen_id)
    run_id = Column(String, ForeignKey("search_runs.id"), nullable=False, index=True)
    title = Column(Text, nullable=False)
    abstract = Column(Text, nullable=True)
    authors = Column(Text, nullable=True)  # Comma-separated author names
    year = Column(Integer, nullable=True)
    doi = Column(String, nullable=True, index=True)
    url = Column(Text, nullable=True)
    source = Column(String, nullable=True)
    publication_type = Column(String, nullable=True)  # Journal Article, Conference Paper, Preprint, etc.
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    run = relationship("SearchRun", back_populates="records")

class Appraisal(Base):
    __tablename__ = "appraisals"
    id = Column(String, primary_key=True, default=gen_id)
    run_id = Column(String, ForeignKey("search_runs.id"), nullable=False, index=True)
    record_id = Column(String, ForeignKey("records.id"), nullable=False, index=True)
    rating = Column(String, nullable=False)          # Red / Amber / Green (label)
    scores_json = Column(Text, nullable=False)       # dict as json
    rationale = Column(Text, nullable=True)
    citations_json = Column(Text, nullable=True)     # list[str] as json
    # NEW: numeric score for filtering/sorting (nullable for back-compat)
    score_final = Column(Float, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    run = relationship("SearchRun", back_populates="appraisals")
    record = relationship("Record")

    @property
    def scores(self) -> Dict[str, Any]:
        return json.loads(self.scores_json)

    @property
    def citations(self) -> List[str]:
        return json.loads(self.citations_json or "[]")

class Screening(Base):
    __tablename__ = "screenings"
    id = Column(String, primary_key=True, default=gen_id)
    run_id = Column(String, ForeignKey("search_runs.id"), nullable=False, index=True)
    record_id = Column(String, ForeignKey("records.id"), nullable=False, index=True)
    decision = Column(String, nullable=False)   # "include" | "exclude"
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

class PrismaCounts(Base):
    __tablename__ = "prisma_counts"
    id = Column(String, primary_key=True, default=gen_id)
    run_id = Column(String, ForeignKey("search_runs.id"), nullable=False, unique=True, index=True)
    identified = Column(Integer, default=0)
    deduped = Column(Integer, default=0)
    screened = Column(Integer, default=0)
    excluded = Column(Integer, default=0)
    eligible = Column(Integer, default=0)
    included = Column(Integer, default=0)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    run = relationship("SearchRun", back_populates="prisma")
    

def init_db() -> None:
    Base.metadata.create_all(engine)

def get_session():
    return SessionLocal()
