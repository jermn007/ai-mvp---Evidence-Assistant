"""
Test the configuration system and extended metadata support
"""
from __future__ import annotations
import os
import sys

# Add the parent directory to Python path to enable app imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.config import get_config, ConfigLoader
from app.models import RecordModel


def test_config_loading():
    """Test that configuration loads correctly"""
    config = get_config()
    
    # Test deduplication config
    assert hasattr(config, 'deduplication')
    assert config.deduplication.title_similarity_threshold == 96
    assert config.deduplication.use_exact_matching == True
    
    # Test metadata config
    assert hasattr(config, 'metadata')
    assert len(config.metadata.core_fields) > 0
    assert len(config.metadata.extended_fields) > 0
    assert "record_id" in config.metadata.core_fields
    assert "journal" in config.metadata.extended_fields
    
    # Test search config
    assert hasattr(config, 'search')
    assert config.search.max_results_per_source == 25
    assert config.search.request_timeout == 30
    assert isinstance(config.search.modes, dict)
    assert config.search.modes.get('standard') == config.search.max_results_per_source
    
    print("Configuration loading test passed")


def test_extended_record_model():
    """Test that RecordModel supports extended metadata"""
    # Test with core fields only
    core_record = RecordModel(
        record_id="test_001",
        title="Test Article",
        source="test_source"
    )
    
    assert core_record.record_id == "test_001"
    assert core_record.title == "Test Article"
    assert core_record.journal is None  # Extended field should be None by default
    
    # Test with extended fields
    extended_record = RecordModel(
        record_id="test_002",
        title="Extended Test Article",
        abstract="This is a test abstract for validation.",
        authors="Smith, J., Doe, A.",
        year=2023,
        doi="10.1234/test",
        url="https://example.com/test",
        source="pubmed",
        publication_type="Journal Article",
        
        # Extended metadata
        journal="Test Journal",
        publisher="Test Publisher",
        volume="42",
        issue="3",
        pages="123-145",
        language="English",
        country="United States",
        pmid="12345678",
        issn="1234-5678",
        subjects="machine learning, education",
        mesh_terms="Education, Computer-Assisted; Machine Learning",
        pdf_url="https://example.com/test.pdf",
        open_access=True,
        cited_by_count=15,
        reference_count=45
    )
    
    # Verify core fields
    assert extended_record.record_id == "test_002"
    assert extended_record.title == "Extended Test Article"
    assert extended_record.year == 2023
    
    # Verify extended fields
    assert extended_record.journal == "Test Journal"
    assert extended_record.publisher == "Test Publisher"
    assert extended_record.volume == "42"
    assert extended_record.language == "English"
    assert extended_record.pmid == "12345678"
    assert extended_record.subjects == "machine learning, education"
    assert extended_record.open_access == True
    assert extended_record.cited_by_count == 15
    
    print("Extended RecordModel test passed")


def test_deduplication_config():
    """Test that deduplication uses configurable thresholds"""
    config = get_config()
    
    # Test that we can read the threshold
    threshold = config.deduplication.title_similarity_threshold
    assert isinstance(threshold, int)
    assert 0 <= threshold <= 100
    
    # Test exact matching config
    assert isinstance(config.deduplication.use_exact_matching, bool)
    
    # Test optional strategies
    assert isinstance(config.deduplication.abstract_similarity_enabled, bool)
    assert isinstance(config.deduplication.author_similarity_enabled, bool)
    
    if config.deduplication.abstract_similarity_enabled:
        assert isinstance(config.deduplication.abstract_similarity_threshold, int)
        assert 0 <= config.deduplication.abstract_similarity_threshold <= 100
    
    print("Deduplication configuration test passed")


def test_metadata_fields_config():
    """Test metadata field configuration"""
    config = get_config()
    
    # Test core fields
    core_fields = config.metadata.core_fields
    assert isinstance(core_fields, list)
    assert len(core_fields) > 0
    
    # Check that expected core fields are present
    expected_core = ["record_id", "title", "source"]
    for field in expected_core:
        assert field in core_fields, f"Core field '{field}' missing"
    
    # Test extended fields
    extended_fields = config.metadata.extended_fields
    assert isinstance(extended_fields, list)
    assert len(extended_fields) > 0
    
    # Check that expected extended fields are present
    expected_extended = ["journal", "publisher", "pmid", "open_access"]
    for field in expected_extended:
        assert field in extended_fields, f"Extended field '{field}' missing"
    
    print("Metadata fields configuration test passed")


def test_config_reload():
    """Test configuration reloading"""
    from app.config import reload_config
    
    # Get initial config
    config1 = get_config()
    initial_threshold = config1.deduplication.title_similarity_threshold
    
    # Reload configuration  
    reload_config()
    
    # Get config after reload
    config2 = get_config()
    reloaded_threshold = config2.deduplication.title_similarity_threshold
    
    # Should be the same (since we didn't change the file)
    assert initial_threshold == reloaded_threshold
    
    print("Configuration reload test passed")


def test_model_serialization():
    """Test that enhanced RecordModel can be serialized/deserialized"""
    # Create a record with extended metadata
    original = RecordModel(
        record_id="serialize_test",
        title="Serialization Test Article",
        source="test",
        journal="Test Journal",
        pmid="98765432",
        open_access=True,
        cited_by_count=10
    )
    
    # Convert to dict and back
    record_dict = original.model_dump()
    restored = RecordModel(**record_dict)
    
    # Verify core fields
    assert restored.record_id == original.record_id
    assert restored.title == original.title
    assert restored.source == original.source
    
    # Verify extended fields
    assert restored.journal == original.journal
    assert restored.pmid == original.pmid
    assert restored.open_access == original.open_access
    assert restored.cited_by_count == original.cited_by_count
    
    print("Model serialization test passed")


if __name__ == "__main__":
    print("Running configuration and extended metadata tests...")
    
    test_config_loading()
    print("[PASS] Configuration loading")
    
    test_extended_record_model()
    print("[PASS] Extended RecordModel")
    
    test_deduplication_config()
    print("[PASS] Deduplication configuration")
    
    test_metadata_fields_config()
    print("[PASS] Metadata fields configuration")
    
    test_config_reload()
    print("[PASS] Configuration reload")
    
    test_model_serialization()
    print("[PASS] Model serialization")
    
    print("\nAll configuration and metadata tests completed successfully!")