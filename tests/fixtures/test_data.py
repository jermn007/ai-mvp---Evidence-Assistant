# tests/fixtures/test_data.py
"""
Test data fixtures for E2E testing.
Provides sample data for PRESS plans, search results, and expected outputs.
"""
from app.models import PressPlan

# Sample PRESS plan for testing
SAMPLE_PRESS_PLAN = PressPlan(
    concepts=["instructional design", "learning effectiveness", "educational technology"],
    boolean='("instructional design"[Title/Abstract] OR "learning effectiveness"[Title/Abstract]) AND ("educational technology"[Title/Abstract] OR "e-learning"[Title/Abstract]) AND (study OR trial OR evaluation)',
    sources=["PubMed", "Crossref", "ERIC", "SemanticScholar"],
    years="2020-",
    limits="English language, peer-reviewed"
)

# Sample LICO (Learner, Intervention, Context, Outcome) data for testing
SAMPLE_LICO = {
    "learner": ["students", "learners", "trainees", "participants"],
    "intervention": ["instructional design", "teaching method", "educational intervention", "learning strategy"],
    "context": ["classroom", "online learning", "educational setting", "university"],
    "outcome": ["learning effectiveness", "academic performance", "knowledge retention", "skill acquisition"]
}

# Sample search query for testing
SAMPLE_QUERY = "effectiveness of instructional design in online learning environments"

# Mock search results for testing deduplication
MOCK_SEARCH_RESULTS = [
    {
        "title": "Effectiveness of Instructional Design in Online Learning",
        "abstract": "This study examines the impact of systematic instructional design on student learning outcomes in online environments.",
        "authors": ["Smith, J.", "Johnson, M."],
        "year": 2022,
        "source": "PubMed",
        "external_id": "pmid:12345",
        "url": "https://pubmed.ncbi.nlm.nih.gov/12345"
    },
    {
        "title": "Instructional Design Effectiveness in Online Learning", # Similar title for dedup testing
        "abstract": "An examination of how systematic instructional design impacts student learning in online settings.",
        "authors": ["Smith, J.", "Johnson, M."],
        "year": 2022,
        "source": "Crossref",
        "external_id": "doi:10.1000/test123",
        "url": "https://doi.org/10.1000/test123"
    },
    {
        "title": "Machine Learning Applications in Education",
        "abstract": "This paper explores various applications of machine learning in educational contexts.",
        "authors": ["Brown, A.", "Davis, K."],
        "year": 2023,
        "source": "arXiv",
        "external_id": "arxiv:2301.12345",
        "url": "https://arxiv.org/abs/2301.12345"
    }
]

# Expected PRISMA flow counts after processing
EXPECTED_PRISMA_COUNTS = {
    "records_identified": 3,
    "records_after_deduplication": 2,  # Should remove 1 duplicate
    "records_screened": 2,
    "records_excluded_screening": 0,
    "full_text_assessed": 2,
    "studies_included": 2
}

# Test rubric scores for appraisal testing
SAMPLE_RUBRIC_SCORES = {
    "design_strength": 0.8,
    "bias_risk": 0.7,
    "sample_size": 0.6,
    "recency": 0.9,
    "kirkpatrick_level": 0.7,
    "peer_review": 0.8,
    "methodology_clarity": 0.7,
    "generalizability": 0.6
}