# AI Literature Review Workflow Diagrams

## Overview

This document provides visual representations and detailed explanations of the Evidence Assistant's 5-step systematic literature review workflow.

## Core 5-Step Workflow

```mermaid
graph TD
    A[Start: Research Question] --> B[1. PRESS Planning]
    B --> C[2. Harvest Sources]
    C --> D[3. Dedupe & Screen]
    D --> E[4. Appraise Quality]
    E --> F[5. PRISMA Report]
    F --> G[End: Evidence Summary]

    B --> B1[Generate LICO Framework]
    B --> B2[Create Search Strategies]
    B --> B3[Validate with Checklist]

    C --> C1[Search 6 Databases]
    C --> C2[Collect Metadata]
    C --> C3[Apply Date Filters]

    D --> D1[Fuzzy Deduplication 96%]
    D --> D2[Inclusion/Exclusion Screening]
    D --> D3[Apply Study Selection Criteria]

    E --> E1[8-Criteria Rubric Scoring]
    E --> E2[Red/Amber/Green Classification]
    E --> E3[Quality Assurance Validation]

    F --> F1[Generate PRISMA Flow Chart]
    F --> F2[Calculate Statistics]
    F --> F3[Export Results]
```

## LICO Framework Detail

```mermaid
graph LR
    A[Research Question] --> B[LICO Analysis]
    B --> C[Learner: Who is learning?]
    B --> D[Intervention: What educational method?]
    B --> E[Context: Where/when does learning occur?]
    B --> F[Outcome: What is measured?]

    C --> G[Search Term Expansion]
    D --> G
    E --> G
    F --> G

    G --> H[Boolean Query Construction]
    H --> I[Database-Specific Formatting]
```

## Database Harvesting Process

```mermaid
graph TD
    A[Query Generated] --> B[Parallel Database Search]

    B --> C1[PubMed<br/>Medical Literature]
    B --> C2[Crossref<br/>Academic Publications]
    B --> C3[arXiv<br/>Preprints]
    B --> C4[ERIC<br/>Education Research]
    B --> C5[Semantic Scholar<br/>AI-Enhanced Search]
    B --> C6[Google Scholar<br/>Broad Academic Coverage]

    C1 --> D[Metadata Collection]
    C2 --> D
    C3 --> D
    C4 --> D
    C5 --> D
    C6 --> D

    D --> E[Rate Limiting & Error Handling]
    E --> F[Standardized Record Format]
    F --> G[Database Storage]
```

## Deduplication & Screening Workflow

```mermaid
graph TD
    A[Raw Records] --> B[Fuzzy Matching Engine]
    B --> C{Similarity >= 96%?}
    C -->|Yes| D[Mark as Duplicate]
    C -->|No| E[Keep Record]

    D --> F[Deduplicated Set]
    E --> F

    F --> G[Inclusion/Exclusion Screening]
    G --> H{Meets Criteria?}
    H -->|Yes| I[Include for Appraisal]
    H -->|No| J[Exclude with Reason]

    I --> K[Eligible Records]
    J --> L[Exclusion Report]
```

## Quality Appraisal Rubric

```mermaid
graph TD
    A[Eligible Record] --> B[8-Criteria Assessment]

    B --> C1[Design Strength<br/>Weight: 20%]
    B --> C2[Risk of Bias<br/>Weight: 15%]
    B --> C3[Sample Size<br/>Weight: 10%]
    B --> C4[Kirkpatrick Level<br/>Weight: 15%]
    B --> C5[Follow-up Duration<br/>Weight: 10%]
    B --> C6[Statistical Rigor<br/>Weight: 15%]
    B --> C7[Recency<br/>Weight: 10%]
    B --> C8[Relevance<br/>Weight: 5%]

    C1 --> D[Weighted Score Calculation]
    C2 --> D
    C3 --> D
    C4 --> D
    C5 --> D
    C6 --> D
    C7 --> D
    C8 --> D

    D --> E{Score >= 0.7?}
    E -->|Yes| F[Green: High Quality]
    E -->|No| G{Score >= 0.4?}
    G -->|Yes| H[Amber: Moderate Quality]
    G -->|No| I[Red: Low Quality]
```

## PRISMA Flow Generation

```mermaid
graph TD
    A[All Database Results] --> B[Records Identified<br/>n = X]
    B --> C[Records After Deduplication<br/>n = Y]
    C --> D[Records Screened<br/>n = Y]
    D --> E[Records Excluded<br/>n = Z]
    D --> F[Full-text Articles Assessed<br/>n = W]
    F --> G[Studies Excluded with Reasons<br/>n = V]
    F --> H[Studies Included in Review<br/>n = U]

    E --> E1[Exclusion Reasons:<br/>• Not relevant<br/>• Non-English<br/>• Pre-2018<br/>• Not primary research<br/>• Animal study<br/>• Study type]

    H --> I[Quality Assessment Results<br/>• Green: High Quality<br/>• Amber: Moderate Quality<br/>• Red: Low Quality]
```

## API Integration Points

```mermaid
graph LR
    A[Frontend UI] --> B[FastAPI Server]
    B --> C[LangGraph Orchestrator]

    C --> D[PRESS Planning Node]
    C --> E[Harvest Node]
    C --> F[Dedupe/Screen Node]
    C --> G[Appraise Node]
    C --> H[Report Node]

    D --> I[OpenAI GPT-4]
    E --> J[Academic APIs]
    F --> K[SQLAlchemy Database]
    G --> L[Rubric Engine]
    H --> M[Export Services]

    B --> N[Real-time Progress Updates]
    B --> O[Result Caching]
    B --> P[Error Handling]
```

## Error Handling & Recovery

```mermaid
graph TD
    A[Workflow Step] --> B{Success?}
    B -->|Yes| C[Continue to Next Step]
    B -->|No| D[Error Captured]

    D --> E[Log Error Details]
    E --> F{Retryable?}
    F -->|Yes| G[Retry with Backoff]
    F -->|No| H[Graceful Degradation]

    G --> I{Retry Success?}
    I -->|Yes| C
    I -->|No| H

    H --> J[Partial Results Available?]
    J -->|Yes| K[Return Partial Results]
    J -->|No| L[Return Error Response]
```

## Performance Monitoring

```mermaid
graph TD
    A[Request Received] --> B[Start Timer]
    B --> C[Execute Workflow]
    C --> D[Track Step Duration]
    D --> E[Monitor Memory Usage]
    E --> F[Log Database Queries]
    F --> G[Measure API Response Times]
    G --> H[Complete Workflow]
    H --> I[Generate Performance Report]

    I --> J[Response Time < 300s?]
    J -->|Yes| K[Performance OK]
    J -->|No| L[Performance Warning]

    L --> M[Trigger Optimization]
    M --> N[Scale Resources]
    M --> O[Optimize Queries]
    M --> P[Cache Results]
```

## Data Flow Architecture

```mermaid
graph LR
    A[User Input] --> B[PRESS Planning]
    B --> C[Query Generation]
    C --> D[Database Searches]
    D --> E[Raw Records]
    E --> F[Deduplication]
    F --> G[Screening]
    G --> H[Quality Appraisal]
    H --> I[PRISMA Report]
    I --> J[Export Formats]

    E --> DB[(PostgreSQL/SQLite)]
    F --> DB
    G --> DB
    H --> DB
    I --> DB

    DB --> K[JSON Export]
    DB --> L[CSV Export]
    DB --> M[Summary Reports]
```

## Integration Testing Flow

```mermaid
graph TD
    A[Test Suite Start] --> B[API Health Check]
    B --> C[Database Connection Test]
    C --> D[Source Integration Test]
    D --> E[PRESS Planning Test]
    E --> F[Complete Workflow Test]
    F --> G[Export Validation Test]
    G --> H[Performance Benchmark]
    H --> I[Error Handling Test]
    I --> J[Generate Test Report]

    F --> F1[LICO Workflow]
    F --> F2[Simple Query Workflow]
    F --> F3[AI-Enhanced Workflow]

    J --> K{All Tests Pass?}
    K -->|Yes| L[✅ Suite Success]
    K -->|No| M[❌ Investigation Required]
```