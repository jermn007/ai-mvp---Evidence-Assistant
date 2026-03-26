# Enhanced Database Schema for Full-Text Processing and Multi-Method Appraisals

## Overview

The Evidence Assistant database has been extended to support comprehensive full-text document processing and flexible multi-method appraisal systems. This enhancement enables the platform to perform sophisticated content analysis and assessment using various methodological frameworks.

## Architecture Changes

### Core Principles

1. **Backward Compatibility**: All existing functionality remains intact
2. **Modular Design**: New features are implemented as separate, interlinked modules
3. **Flexibility**: Support for user-defined appraisal methodologies
4. **Performance**: Optimized indexing and query patterns for large-scale analysis

### Schema Extensions

The enhanced schema adds 6 new tables to support advanced functionality:

## New Tables

### 1. DocumentContent
**Purpose**: Stores full-text content and processing metadata for academic documents.

```sql
CREATE TABLE document_content (
    id VARCHAR PRIMARY KEY,
    record_id VARCHAR NOT NULL,  -- FK to records.id
    content_type ENUM,           -- full_text, abstract_only, summary, structured_abstract
    extraction_method ENUM,      -- pdf_extraction, web_scraping, manual_entry, api_import, ocr
    raw_text TEXT NOT NULL,
    word_count INTEGER DEFAULT 0,
    confidence_score FLOAT DEFAULT 0.0,      -- 0-1 extraction confidence
    structure_confidence FLOAT DEFAULT 0.0,  -- 0-1 section parsing confidence
    processing_time FLOAT DEFAULT 0.0,       -- Processing time in seconds
    content_hash VARCHAR,                     -- For deduplication
    source_url TEXT,                          -- URL where content was obtained
    has_structured_sections BOOLEAN DEFAULT FALSE,
    has_citations BOOLEAN DEFAULT FALSE,
    has_figures BOOLEAN DEFAULT FALSE,
    has_tables BOOLEAN DEFAULT FALSE,
    errors_json TEXT,                         -- JSON array of errors
    warnings_json TEXT,                       -- JSON array of warnings
    created_at DATETIME,
    updated_at DATETIME
);
```

**Key Features**:
- Links to existing `Record` entries
- Multiple extraction methods supported
- Quality metrics and confidence scoring
- Content identification for deduplication
- Processing metadata tracking

### 2. DocumentSection
**Purpose**: Stores parsed sections of academic documents for section-specific analysis.

```sql
CREATE TABLE document_sections (
    id VARCHAR PRIMARY KEY,
    document_id VARCHAR NOT NULL,  -- FK to document_content.id
    section_type ENUM,             -- title, abstract, introduction, methods, results, etc.
    heading_text VARCHAR,          -- Original heading text
    content TEXT NOT NULL,
    start_position INTEGER,        -- Character position in full text
    end_position INTEGER,
    word_count INTEGER DEFAULT 0,
    confidence FLOAT DEFAULT 0.0,  -- Section identification confidence
    created_at DATETIME
);
```

**Supported Section Types**:
- Title, Abstract, Keywords
- Introduction, Background, Literature Review
- Methods, Methodology, Materials & Methods
- Results, Findings, Analysis
- Discussion, Limitations
- Conclusion, Implications, Future Work
- References, Acknowledgments, Appendix, Supplementary

### 3. AppraisalMethodology
**Purpose**: Defines available appraisal methodologies and their configuration.

```sql
CREATE TABLE appraisal_methodologies (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL UNIQUE,
    method_type ENUM,              -- rag_quality, kirkpatrick, towle, strength_conclusion, custom
    version VARCHAR DEFAULT '1.0',
    description TEXT,
    criteria_json TEXT NOT NULL,   -- JSON structure defining criteria
    scoring_config_json TEXT NOT NULL,  -- JSON scoring configuration
    is_active BOOLEAN DEFAULT TRUE,
    requires_full_text BOOLEAN DEFAULT FALSE,
    created_by VARCHAR,            -- User who created custom methodology
    created_at DATETIME,
    updated_at DATETIME
);
```

**Default Methodologies Included**:

#### RAG Quality Indices
- **Type**: `rag_quality`
- **Criteria**: Underpinning (15%), Curriculum (15%), Setting (15%), Pedagogy (15%), Content (20%), Conclusion (20%)
- **Scale**: 0-5 per criterion
- **Requires Full Text**: Yes

#### Kirkpatrick's Levels
- **Type**: `kirkpatrick`
- **Levels**: L1 (0.25), L2a (0.50), L2b (0.60), L3 (0.80), L4a (0.90), L4b (1.00)
- **Scale**: 0-1 normalized
- **Requires Full Text**: No

#### Towle's Patient Involvement
- **Type**: `towle`
- **Levels**: 1 (0.17) through 6 (1.00)
- **Scale**: 0-1 normalized
- **Requires Full Text**: No

#### Results & Strength of Conclusion
- **Type**: `strength_conclusion`
- **Criteria**: Result Clarity (25%), Statistical Rigor (25%), Effect Size (25%), Conclusion Strength (25%)
- **Scale**: 0-5 per criterion
- **Requires Full Text**: Yes

### 4. MultiMethodAppraisal
**Purpose**: Stores appraisals using different methodologies, replacing/extending the original Appraisal table.

```sql
CREATE TABLE multi_method_appraisals (
    id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL,         -- FK to search_runs.id
    record_id VARCHAR NOT NULL,      -- FK to records.id
    methodology_id VARCHAR NOT NULL, -- FK to appraisal_methodologies.id
    scores_json TEXT NOT NULL,       -- Detailed scores for each criterion
    overall_score FLOAT NOT NULL,    -- Normalized 0-1 score
    rating VARCHAR NOT NULL,         -- High/Medium/Low or Red/Amber/Green
    rationale TEXT,
    evidence_citations TEXT,         -- JSON array of citations
    confidence FLOAT DEFAULT 0.5,   -- Assessor confidence
    used_full_text BOOLEAN DEFAULT FALSE,
    sections_analyzed_json TEXT,     -- JSON array of section types
    assessed_by VARCHAR,             -- User/system that performed assessment
    assessment_time FLOAT,           -- Time taken for assessment
    created_at DATETIME,
    updated_at DATETIME
);
```

**Key Features**:
- Multiple methodologies per record
- Detailed scoring with rationale
- Full-text analysis tracking
- Assessment metadata

### 5. ContentAcquisitionLog
**Purpose**: Logs content acquisition attempts and results for tracking and optimization.

```sql
CREATE TABLE content_acquisition_logs (
    id VARCHAR PRIMARY KEY,
    record_id VARCHAR NOT NULL,      -- FK to records.id
    strategy_name VARCHAR NOT NULL,
    source_url TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    confidence_score FLOAT,
    content_length INTEGER,
    error_message TEXT,
    processing_time FLOAT DEFAULT 0.0,
    user_agent VARCHAR,
    rate_limit_applied FLOAT,
    created_at DATETIME
);
```

**Tracked Strategies**:
- PMC_Open_Access
- DOI_Resolver
- ArXiv_Preprint
- PLOS_Open_Access
- Semantic_Scholar
- Publisher_Direct
- Generic_URL

### 6. FullTextAnalysis
**Purpose**: Stores AI-enhanced analysis results for full-text documents.

```sql
CREATE TABLE full_text_analyses (
    id VARCHAR PRIMARY KEY,
    document_id VARCHAR NOT NULL UNIQUE,  -- FK to document_content.id

    -- Study characteristics extracted from full text
    study_design VARCHAR,
    sample_size INTEGER,
    population_description TEXT,
    intervention_description TEXT,
    outcome_measures TEXT,               -- JSON array

    -- Quality indicators
    has_control_group BOOLEAN,
    randomization_method VARCHAR,
    blinding_level VARCHAR,
    follow_up_duration VARCHAR,

    -- Statistical analysis
    statistical_methods TEXT,            -- JSON array
    effect_sizes_reported BOOLEAN,
    confidence_intervals_reported BOOLEAN,
    p_values_reported BOOLEAN,

    -- Bias assessment indicators
    selection_bias_risk VARCHAR,         -- Low/Moderate/High
    performance_bias_risk VARCHAR,
    detection_bias_risk VARCHAR,
    attrition_bias_risk VARCHAR,
    reporting_bias_risk VARCHAR,

    -- Content richness metrics
    total_references INTEGER,
    figure_count INTEGER,
    table_count INTEGER,
    supplementary_materials BOOLEAN,

    -- AI analysis metadata
    analysis_model VARCHAR,              -- Model used for analysis
    analysis_confidence FLOAT DEFAULT 0.0,
    analysis_time FLOAT DEFAULT 0.0,

    created_at DATETIME,
    updated_at DATETIME
);
```

## Relationships and Constraints

### Primary Relationships
```
Record (1) → DocumentContent (0..n)
DocumentContent (1) → DocumentSection (0..n)
DocumentContent (1) → FullTextAnalysis (0..1)
Record (1) → MultiMethodAppraisal (0..n)
AppraisalMethodology (1) → MultiMethodAppraisal (0..n)
Record (1) → ContentAcquisitionLog (0..n)
```

### Key Constraints
- **Unique Constraints**:
  - `(record_id, content_type)` in DocumentContent
  - `(document_id, section_type)` in DocumentSection
  - `(record_id, methodology_id)` in MultiMethodAppraisal
  - `document_id` in FullTextAnalysis

- **Indexes**:
  - Content hash for deduplication
  - Confidence scores for quality filtering
  - Section types for analysis
  - Overall scores for ranking
  - Success rates for optimization

## Integration with Existing Schema

### Existing Tables Enhanced
The new schema integrates seamlessly with existing tables:

- **Record**: Extended with document content capabilities
- **SearchRun**: Can now include multi-method appraisals
- **Appraisal**: Legacy table maintained for backward compatibility

### Migration Strategy
1. **Phase 1**: Add new tables alongside existing schema
2. **Phase 2**: Populate default appraisal methodologies
3. **Phase 3**: Gradual migration of existing appraisals to new system
4. **Phase 4**: Optional deprecation of legacy tables

## Performance Optimizations

### Indexing Strategy
```sql
-- Content identification and quality
CREATE INDEX ix_document_content_hash ON document_content(content_hash);
CREATE INDEX ix_document_content_confidence ON document_content(confidence_score);

-- Section analysis
CREATE INDEX ix_section_type ON document_sections(section_type);
CREATE INDEX ix_section_confidence ON document_sections(confidence);

-- Appraisal performance
CREATE INDEX ix_appraisal_score ON multi_method_appraisals(overall_score);
CREATE INDEX ix_appraisal_rating ON multi_method_appraisals(rating);
CREATE INDEX ix_appraisal_method ON multi_method_appraisals(methodology_id);

-- Acquisition tracking
CREATE INDEX ix_acquisition_success ON content_acquisition_logs(success);
CREATE INDEX ix_acquisition_strategy ON content_acquisition_logs(strategy_name);
CREATE INDEX ix_acquisition_time ON content_acquisition_logs(created_at);
```

### Query Patterns
- **Content Deduplication**: Fast hash-based lookups
- **Quality Filtering**: Confidence score ranges
- **Multi-method Comparison**: Cross-methodology analysis
- **Performance Tracking**: Acquisition success rates

## Usage Examples

### 1. Store Full-Text Content
```python
from app.models_extended import DocumentContent, ContentType, ExtractionMethod

content = DocumentContent(
    record_id="record_123",
    content_type=ContentType.FULL_TEXT,
    extraction_method=ExtractionMethod.PDF_EXTRACTION,
    raw_text="...",
    word_count=5000,
    confidence_score=0.92,
    structure_confidence=0.85,
    content_hash="sha256_hash"
)
session.add(content)
```

### 2. Parse Document Sections
```python
from app.models_extended import DocumentSection, SectionType

sections = [
    DocumentSection(
        document_id=content.id,
        section_type=SectionType.ABSTRACT,
        content="Study abstract...",
        confidence=0.95
    ),
    DocumentSection(
        document_id=content.id,
        section_type=SectionType.METHODS,
        content="Methodology description...",
        confidence=0.88
    )
]
```

### 3. Multi-Method Appraisal
```python
from app.models_extended import MultiMethodAppraisal, AppraisalMethodType

# RAG Quality assessment
rag_appraisal = MultiMethodAppraisal(
    record_id="record_123",
    methodology_id=rag_methodology.id,
    scores={"underpinning": 4, "curriculum": 3, "setting": 4, "pedagogy": 3, "content": 4, "conclusion": 3},
    overall_score=0.72,
    rating="Medium",
    used_full_text=True
)

# Kirkpatrick assessment
kirk_appraisal = MultiMethodAppraisal(
    record_id="record_123",
    methodology_id=kirkpatrick_methodology.id,
    scores={"kirkpatrick_level": "L3"},
    overall_score=0.80,
    rating="High",
    used_full_text=False
)
```

### 4. Content Acquisition Tracking
```python
from app.models_extended import ContentAcquisitionLog

log = ContentAcquisitionLog(
    record_id="record_123",
    strategy_name="PMC_Open_Access",
    source_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC12345/",
    success=True,
    confidence_score=0.89,
    content_length=8500,
    processing_time=2.3
)
```

## Benefits of Enhanced Schema

### 1. Comprehensive Content Analysis
- **Full-Text Processing**: Complete document analysis beyond abstracts
- **Section-Specific Analysis**: Targeted evaluation of methodology, results, etc.
- **Quality Metrics**: Confidence scoring for all processing steps

### 2. Flexible Assessment Framework
- **Multiple Methodologies**: RAG Quality, Kirkpatrick, Towle, Custom frameworks
- **User-Defined Criteria**: Configurable assessment criteria
- **Comparative Analysis**: Cross-methodology comparison and validation

### 3. Enhanced Research Capabilities
- **Bias Detection**: Automated risk assessment across multiple domains
- **Statistical Analysis**: Extract and evaluate statistical rigor
- **Content Richness**: Assess supplementary materials and supporting evidence

### 4. Operational Intelligence
- **Acquisition Optimization**: Track and improve content harvesting success
- **Processing Performance**: Monitor and optimize extraction pipelines
- **Quality Assurance**: Confidence-based filtering and validation

## Migration and Deployment

### Database Migration
```bash
# Apply new schema
alembic upgrade head

# Initialize default methodologies
python app/scripts/init_extended_db.py
```

### Validation
```bash
# Verify schema
python app/scripts/init_extended_db.py

# Test content processing
python -m app.document_processing.full_text_processor

# Test multi-method appraisal
python -m app.appraisal.multi_method_assessor
```

## Future Enhancements

### Planned Extensions
1. **AI Model Integration**: Automated content analysis and scoring
2. **User Interface**: Multi-method appraisal management dashboard
3. **Export Capabilities**: Cross-methodology comparison reports
4. **API Extensions**: RESTful endpoints for new functionality

### Scalability Considerations
- **Partitioning**: Large content tables by date/source
- **Caching**: Frequently accessed methodology configurations
- **Archiving**: Historical appraisal versions and methodology evolution

## Conclusion

The enhanced database schema provides a robust foundation for advanced academic literature analysis. It maintains backward compatibility while enabling sophisticated multi-method assessment capabilities and comprehensive full-text processing. The modular design ensures extensibility for future research methodologies and analysis techniques.

This implementation directly supports the user's requirements for:
- ✅ **Full-text ingestion** from PDFs and websites
- ✅ **RAG Quality Indices** assessment framework
- ✅ **Kirkpatrick's Levels** evaluation methodology
- ✅ **Towle's Patient Involvement** levels for medical studies
- ✅ **Results & Strength of Conclusion** assessment
- ✅ **Flexible methodology selection** and custom frameworks
- ✅ **Comprehensive tracking** and optimization capabilities