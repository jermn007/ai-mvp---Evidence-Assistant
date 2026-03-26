"""
Extended database models for full-text processing and multi-method appraisals.
Extends the existing schema with new tables for document content and flexible assessment methods.
"""

from __future__ import annotations
import json
import uuid
import datetime as dt
from typing import Optional, Dict, Any, List, Union
from sqlalchemy import (
    create_engine, Column, String, Integer, Text, DateTime, ForeignKey,
    Float, Boolean, JSON, Enum as SQLEnum, UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from enum import Enum
from dataclasses import dataclass

try:
    from .db import Base, gen_id
except ImportError:
    from db import Base, gen_id


# Enums for document processing
class ContentType(Enum):
    """Types of document content."""
    FULL_TEXT = "full_text"
    ABSTRACT_ONLY = "abstract_only"
    SUMMARY = "summary"
    STRUCTURED_ABSTRACT = "structured_abstract"


class ExtractionMethod(Enum):
    """Methods used for content extraction."""
    PDF_EXTRACTION = "pdf_extraction"
    WEB_SCRAPING = "web_scraping"
    MANUAL_ENTRY = "manual_entry"
    API_IMPORT = "api_import"
    OCR = "ocr"


class SectionType(Enum):
    """Academic paper section types."""
    TITLE = "title"
    ABSTRACT = "abstract"
    KEYWORDS = "keywords"
    INTRODUCTION = "introduction"
    BACKGROUND = "background"
    LITERATURE_REVIEW = "literature_review"
    METHODS = "methods"
    METHODOLOGY = "methodology"
    MATERIALS_METHODS = "materials_methods"
    RESULTS = "results"
    FINDINGS = "findings"
    ANALYSIS = "analysis"
    DISCUSSION = "discussion"
    LIMITATIONS = "limitations"
    CONCLUSION = "conclusion"
    CONCLUSIONS = "conclusions"
    IMPLICATIONS = "implications"
    FUTURE_WORK = "future_work"
    REFERENCES = "references"
    ACKNOWLEDGMENTS = "acknowledgments"
    APPENDIX = "appendix"
    SUPPLEMENTARY = "supplementary"


class AppraisalMethodType(Enum):
    """Types of appraisal methodologies."""
    RAG_QUALITY = "rag_quality"  # RAG Quality Indices
    KIRKPATRICK = "kirkpatrick"  # Kirkpatrick's Levels
    TOWLE = "towle"  # Towle's Patient Involvement Levels
    STRENGTH_CONCLUSION = "strength_conclusion"  # Results & Strength of Conclusion
    CUSTOM = "custom"  # User-defined methodology


# Full-text content storage
class DocumentContent(Base):
    """
    Stores full-text content and processing metadata for academic documents.
    Links to existing Record entries to add full-text capabilities.
    """
    __tablename__ = "document_content"

    id = Column(String, primary_key=True, default=gen_id)
    record_id = Column(String, ForeignKey("records.id"), nullable=False, index=True)

    # Content information
    content_type = Column(SQLEnum(ContentType), nullable=False)
    extraction_method = Column(SQLEnum(ExtractionMethod), nullable=False)
    raw_text = Column(Text, nullable=False)

    # Processing metadata
    word_count = Column(Integer, nullable=False, default=0)
    confidence_score = Column(Float, nullable=False, default=0.0)  # 0-1 extraction confidence
    structure_confidence = Column(Float, nullable=False, default=0.0)  # 0-1 section parsing confidence
    processing_time = Column(Float, nullable=False, default=0.0)  # Processing time in seconds

    # Content identification
    content_hash = Column(String, nullable=False, index=True)  # For deduplication
    source_url = Column(Text, nullable=True)  # URL where content was obtained

    # Quality indicators
    has_structured_sections = Column(Boolean, default=False)
    has_citations = Column(Boolean, default=False)
    has_figures = Column(Boolean, default=False)
    has_tables = Column(Boolean, default=False)

    # Processing errors and warnings
    errors_json = Column(Text, nullable=True)  # JSON array of errors
    warnings_json = Column(Text, nullable=True)  # JSON array of warnings

    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    # Relationships
    record = relationship("Record", backref="document_content")
    sections = relationship("DocumentSection", back_populates="document", cascade="all, delete-orphan")

    # Constraints
    __table_args__ = (
        UniqueConstraint('record_id', 'content_type', name='uq_record_content_type'),
        Index('ix_document_content_hash', 'content_hash'),
        Index('ix_document_content_confidence', 'confidence_score'),
    )

    @property
    def errors(self) -> List[str]:
        """Get processing errors as list."""
        return json.loads(self.errors_json or "[]")

    @errors.setter
    def errors(self, value: List[str]):
        """Set processing errors."""
        self.errors_json = json.dumps(value)

    @property
    def warnings(self) -> List[str]:
        """Get processing warnings as list."""
        return json.loads(self.warnings_json or "[]")

    @warnings.setter
    def warnings(self, value: List[str]):
        """Set processing warnings."""
        self.warnings_json = json.dumps(value)


class DocumentSection(Base):
    """
    Stores parsed sections of academic documents.
    Enables section-specific analysis and appraisal.
    """
    __tablename__ = "document_sections"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("document_content.id"), nullable=False, index=True)

    # Section information
    section_type = Column(SQLEnum(SectionType), nullable=False)
    heading_text = Column(String, nullable=True)  # Original heading text
    content = Column(Text, nullable=False)

    # Position and structure
    start_position = Column(Integer, nullable=True)  # Character position in full text
    end_position = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=False, default=0)

    # Quality metrics
    confidence = Column(Float, nullable=False, default=0.0)  # Section identification confidence

    created_at = Column(DateTime, default=dt.datetime.utcnow)

    # Relationships
    document = relationship("DocumentContent", back_populates="sections")

    # Constraints
    __table_args__ = (
        UniqueConstraint('document_id', 'section_type', name='uq_document_section_type'),
        Index('ix_section_type', 'section_type'),
        Index('ix_section_confidence', 'confidence'),
    )


class AppraisalMethodology(Base):
    """
    Defines available appraisal methodologies and their configuration.
    Supports multiple assessment frameworks (RAG Quality, Kirkpatrick, Towle, etc.).
    """
    __tablename__ = "appraisal_methodologies"

    id = Column(String, primary_key=True, default=gen_id)

    # Methodology identification
    name = Column(String, nullable=False, unique=True)
    method_type = Column(SQLEnum(AppraisalMethodType), nullable=False)
    version = Column(String, nullable=False, default="1.0")

    # Configuration
    description = Column(Text, nullable=True)
    criteria_json = Column(Text, nullable=False)  # JSON structure defining criteria
    scoring_config_json = Column(Text, nullable=False)  # JSON scoring configuration

    # Metadata
    is_active = Column(Boolean, default=True)
    requires_full_text = Column(Boolean, default=False)
    created_by = Column(String, nullable=True)  # User who created custom methodology

    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    # Relationships
    appraisals = relationship("MultiMethodAppraisal", back_populates="methodology")

    @property
    def criteria(self) -> Dict[str, Any]:
        """Get criteria configuration as dict."""
        return json.loads(self.criteria_json)

    @criteria.setter
    def criteria(self, value: Dict[str, Any]):
        """Set criteria configuration."""
        self.criteria_json = json.dumps(value)

    @property
    def scoring_config(self) -> Dict[str, Any]:
        """Get scoring configuration as dict."""
        return json.loads(self.scoring_config_json)

    @scoring_config.setter
    def scoring_config(self, value: Dict[str, Any]):
        """Set scoring configuration."""
        self.scoring_config_json = json.dumps(value)


class MultiMethodAppraisal(Base):
    """
    Stores appraisals using different methodologies.
    Replaces/extends the original Appraisal table with multi-method support.
    """
    __tablename__ = "multi_method_appraisals"

    id = Column(String, primary_key=True, default=gen_id)
    run_id = Column(String, ForeignKey("search_runs.id"), nullable=False, index=True)
    record_id = Column(String, ForeignKey("records.id"), nullable=False, index=True)
    methodology_id = Column(String, ForeignKey("appraisal_methodologies.id"), nullable=False, index=True)

    # Appraisal results
    scores_json = Column(Text, nullable=False)  # Detailed scores for each criterion
    overall_score = Column(Float, nullable=False)  # Normalized 0-1 score
    rating = Column(String, nullable=False)  # High/Medium/Low or Red/Amber/Green

    # Supporting information
    rationale = Column(Text, nullable=True)
    evidence_citations = Column(Text, nullable=True)  # JSON array of citations
    confidence = Column(Float, nullable=False, default=0.5)  # Assessor confidence

    # Full-text analysis
    used_full_text = Column(Boolean, default=False)
    sections_analyzed_json = Column(Text, nullable=True)  # JSON array of section types

    # Assessment metadata
    assessed_by = Column(String, nullable=True)  # User/system that performed assessment
    assessment_time = Column(Float, nullable=True)  # Time taken for assessment

    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    # Relationships
    run = relationship("SearchRun")
    record = relationship("Record")
    methodology = relationship("AppraisalMethodology", back_populates="appraisals")

    # Constraints
    __table_args__ = (
        UniqueConstraint('record_id', 'methodology_id', name='uq_record_methodology'),
        Index('ix_appraisal_score', 'overall_score'),
        Index('ix_appraisal_rating', 'rating'),
        Index('ix_appraisal_method', 'methodology_id'),
    )

    @property
    def scores(self) -> Dict[str, Any]:
        """Get detailed scores as dict."""
        return json.loads(self.scores_json)

    @scores.setter
    def scores(self, value: Dict[str, Any]):
        """Set detailed scores."""
        self.scores_json = json.dumps(value)

    @property
    def evidence_citations_list(self) -> List[str]:
        """Get evidence citations as list."""
        return json.loads(self.evidence_citations or "[]")

    @evidence_citations_list.setter
    def evidence_citations_list(self, value: List[str]):
        """Set evidence citations."""
        self.evidence_citations = json.dumps(value)

    @property
    def sections_analyzed(self) -> List[str]:
        """Get analyzed sections as list."""
        return json.loads(self.sections_analyzed_json or "[]")

    @sections_analyzed.setter
    def sections_analyzed(self, value: List[str]):
        """Set analyzed sections."""
        self.sections_analyzed_json = json.dumps(value)


class ContentAcquisitionLog(Base):
    """
    Logs content acquisition attempts and results for tracking and optimization.
    """
    __tablename__ = "content_acquisition_logs"

    id = Column(String, primary_key=True, default=gen_id)
    record_id = Column(String, ForeignKey("records.id"), nullable=False, index=True)

    # Acquisition attempt details
    strategy_name = Column(String, nullable=False)
    source_url = Column(Text, nullable=False)
    success = Column(Boolean, nullable=False)

    # Results
    confidence_score = Column(Float, nullable=True)
    content_length = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    processing_time = Column(Float, nullable=False, default=0.0)

    # Metadata
    user_agent = Column(String, nullable=True)
    rate_limit_applied = Column(Float, nullable=True)

    created_at = Column(DateTime, default=dt.datetime.utcnow)

    # Relationships
    record = relationship("Record")

    # Constraints
    __table_args__ = (
        Index('ix_acquisition_success', 'success'),
        Index('ix_acquisition_strategy', 'strategy_name'),
        Index('ix_acquisition_time', 'created_at'),
    )


class FullTextAnalysis(Base):
    """
    Stores AI-enhanced analysis results for full-text documents.
    Used for automated extraction of research characteristics and quality indicators.
    """
    __tablename__ = "full_text_analyses"

    id = Column(String, primary_key=True, default=gen_id)
    document_id = Column(String, ForeignKey("document_content.id"), nullable=False, unique=True, index=True)

    # Study characteristics extracted from full text
    study_design = Column(String, nullable=True)
    sample_size = Column(Integer, nullable=True)
    population_description = Column(Text, nullable=True)
    intervention_description = Column(Text, nullable=True)
    outcome_measures = Column(Text, nullable=True)  # JSON array

    # Quality indicators
    has_control_group = Column(Boolean, nullable=True)
    randomization_method = Column(String, nullable=True)
    blinding_level = Column(String, nullable=True)
    follow_up_duration = Column(String, nullable=True)

    # Statistical analysis
    statistical_methods = Column(Text, nullable=True)  # JSON array
    effect_sizes_reported = Column(Boolean, nullable=True)
    confidence_intervals_reported = Column(Boolean, nullable=True)
    p_values_reported = Column(Boolean, nullable=True)

    # Bias assessment indicators
    selection_bias_risk = Column(String, nullable=True)  # Low/Moderate/High
    performance_bias_risk = Column(String, nullable=True)
    detection_bias_risk = Column(String, nullable=True)
    attrition_bias_risk = Column(String, nullable=True)
    reporting_bias_risk = Column(String, nullable=True)

    # Content richness metrics
    total_references = Column(Integer, nullable=True)
    figure_count = Column(Integer, nullable=True)
    table_count = Column(Integer, nullable=True)
    supplementary_materials = Column(Boolean, nullable=True)

    # AI analysis metadata
    analysis_model = Column(String, nullable=True)  # Model used for analysis
    analysis_confidence = Column(Float, nullable=False, default=0.0)
    analysis_time = Column(Float, nullable=False, default=0.0)

    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    # Relationships
    document = relationship("DocumentContent", backref="analysis")

    @property
    def outcome_measures_list(self) -> List[str]:
        """Get outcome measures as list."""
        return json.loads(self.outcome_measures or "[]")

    @outcome_measures_list.setter
    def outcome_measures_list(self, value: List[str]):
        """Set outcome measures."""
        self.outcome_measures = json.dumps(value)

    @property
    def statistical_methods_list(self) -> List[str]:
        """Get statistical methods as list."""
        return json.loads(self.statistical_methods or "[]")

    @statistical_methods_list.setter
    def statistical_methods_list(self, value: List[str]):
        """Set statistical methods."""
        self.statistical_methods = json.dumps(value)


# Data classes for configuration
@dataclass
class RAGQualityCriteria:
    """RAG Quality Indices criteria configuration."""
    underpinning: float = 0.15  # Theoretical underpinning
    curriculum: float = 0.15    # Curriculum content
    setting: float = 0.15       # Educational setting
    pedagogy: float = 0.15      # Pedagogical approach
    content: float = 0.20       # Content quality
    conclusion: float = 0.20    # Strength of conclusions


@dataclass
class KirkpatrickCriteria:
    """Kirkpatrick's Levels criteria configuration."""
    level_weights = {
        'L1': 0.25,   # Reaction
        'L2a': 0.50,  # Learning - Knowledge/Skills
        'L2b': 0.60,  # Learning - Attitudes
        'L3': 0.80,   # Behavior
        'L4a': 0.90,  # Results - Individual
        'L4b': 1.00   # Results - Organizational
    }


@dataclass
class TowleCriteria:
    """Towle's Patient Involvement Levels criteria configuration."""
    level_weights = {
        '1': 0.17,  # Information only
        '2': 0.33,  # Information and opinion sought
        '3': 0.50,  # Limited involvement in decision-making
        '4': 0.67,  # Partnership in decision-making
        '5': 0.83,  # Patient/consumer control
        '6': 1.00   # Patient/consumer control with support
    }


@dataclass
class StrengthConclusionCriteria:
    """Results & Strength of Conclusion criteria configuration."""
    result_clarity: float = 0.25     # Clarity of results presentation
    statistical_rigor: float = 0.25  # Statistical analysis quality
    effect_size: float = 0.25        # Clinical/practical significance
    conclusion_strength: float = 0.25 # Strength of conclusions drawn


def create_default_methodologies() -> List[AppraisalMethodology]:
    """Create default appraisal methodologies."""
    methodologies = []

    # RAG Quality Indices
    rag_criteria = RAGQualityCriteria()
    rag_method = AppraisalMethodology(
        name="RAG Quality Indices",
        method_type=AppraisalMethodType.RAG_QUALITY,
        description="Six-domain quality assessment for educational research",
        requires_full_text=True
    )
    rag_method.criteria = {
        "underpinning": {"weight": rag_criteria.underpinning, "description": "Theoretical underpinning"},
        "curriculum": {"weight": rag_criteria.curriculum, "description": "Curriculum content"},
        "setting": {"weight": rag_criteria.setting, "description": "Educational setting"},
        "pedagogy": {"weight": rag_criteria.pedagogy, "description": "Pedagogical approach"},
        "content": {"weight": rag_criteria.content, "description": "Content quality"},
        "conclusion": {"weight": rag_criteria.conclusion, "description": "Strength of conclusions"}
    }
    rag_method.scoring_config = {
        "scale": {"min": 0, "max": 5},
        "thresholds": {"high": 3.5, "medium": 2.5, "low": 0}
    }
    methodologies.append(rag_method)

    # Kirkpatrick's Levels
    kirk_criteria = KirkpatrickCriteria()
    kirk_method = AppraisalMethodology(
        name="Kirkpatrick's Levels",
        method_type=AppraisalMethodType.KIRKPATRICK,
        description="Four-level evaluation model for training effectiveness",
        requires_full_text=False
    )
    kirk_method.criteria = {
        "kirkpatrick_level": {
            "levels": kirk_criteria.level_weights,
            "description": "Highest level of evaluation achieved"
        }
    }
    kirk_method.scoring_config = {
        "scale": {"min": 0, "max": 1},
        "thresholds": {"high": 0.75, "medium": 0.50, "low": 0}
    }
    methodologies.append(kirk_method)

    # Towle's Patient Involvement Levels
    towle_criteria = TowleCriteria()
    towle_method = AppraisalMethodology(
        name="Towle's Patient Involvement",
        method_type=AppraisalMethodType.TOWLE,
        description="Six-level scale for patient involvement in medical education",
        requires_full_text=False
    )
    towle_method.criteria = {
        "involvement_level": {
            "levels": towle_criteria.level_weights,
            "description": "Level of patient involvement achieved"
        }
    }
    towle_method.scoring_config = {
        "scale": {"min": 0, "max": 1},
        "thresholds": {"high": 0.67, "medium": 0.33, "low": 0}
    }
    methodologies.append(towle_method)

    # Results & Strength of Conclusion
    strength_criteria = StrengthConclusionCriteria()
    strength_method = AppraisalMethodology(
        name="Results & Strength of Conclusion",
        method_type=AppraisalMethodType.STRENGTH_CONCLUSION,
        description="Assessment of results clarity and conclusion strength",
        requires_full_text=True
    )
    strength_method.criteria = {
        "result_clarity": {"weight": strength_criteria.result_clarity, "description": "Clarity of results presentation"},
        "statistical_rigor": {"weight": strength_criteria.statistical_rigor, "description": "Statistical analysis quality"},
        "effect_size": {"weight": strength_criteria.effect_size, "description": "Clinical/practical significance"},
        "conclusion_strength": {"weight": strength_criteria.conclusion_strength, "description": "Strength of conclusions drawn"}
    }
    strength_method.scoring_config = {
        "scale": {"min": 0, "max": 5},
        "thresholds": {"high": 3.5, "medium": 2.5, "low": 0}
    }
    methodologies.append(strength_method)

    return methodologies


# Extended database functions
def init_extended_db(engine) -> None:
    """Initialize extended database schema."""
    Base.metadata.create_all(engine)

    # Create default methodologies if they don't exist
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as session:
        # Check if methodologies already exist
        existing_count = session.query(AppraisalMethodology).count()

        if existing_count == 0:
            # Create default methodologies
            default_methodologies = create_default_methodologies()
            for methodology in default_methodologies:
                session.add(methodology)

            session.commit()


# Utility functions
def get_methodology_by_type(session, method_type: AppraisalMethodType) -> Optional[AppraisalMethodology]:
    """Get methodology by type."""
    return session.query(AppraisalMethodology).filter(
        AppraisalMethodology.method_type == method_type,
        AppraisalMethodology.is_active == True
    ).first()


def get_document_content_by_record(session, record_id: str, content_type: ContentType = None) -> Optional[DocumentContent]:
    """Get document content for a record."""
    query = session.query(DocumentContent).filter(DocumentContent.record_id == record_id)

    if content_type:
        query = query.filter(DocumentContent.content_type == content_type)

    return query.first()


def get_sections_by_document(session, document_id: str, section_types: List[SectionType] = None) -> List[DocumentSection]:
    """Get sections for a document."""
    query = session.query(DocumentSection).filter(DocumentSection.document_id == document_id)

    if section_types:
        query = query.filter(DocumentSection.section_type.in_(section_types))

    return query.all()


def get_appraisals_by_record(session, record_id: str, methodology_type: AppraisalMethodType = None) -> List[MultiMethodAppraisal]:
    """Get appraisals for a record."""
    query = session.query(MultiMethodAppraisal).filter(MultiMethodAppraisal.record_id == record_id)

    if methodology_type:
        query = query.join(AppraisalMethodology).filter(
            AppraisalMethodology.method_type == methodology_type
        )

    return query.all()