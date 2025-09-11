# app/config.py
"""
Configuration management for AI MVP Evidence Assistant
"""
from __future__ import annotations
import os
import yaml
from typing import Dict, List, Any, Optional
from pathlib import Path
from dataclasses import dataclass

@dataclass
class DeduplicationConfig:
    """Configuration for record deduplication"""
    title_similarity_threshold: int = 96
    use_exact_matching: bool = True
    abstract_similarity_enabled: bool = False
    abstract_similarity_threshold: int = 85
    author_similarity_enabled: bool = False  
    author_similarity_threshold: int = 90

@dataclass
class MetadataConfig:
    """Configuration for metadata handling"""
    core_fields: List[str]
    extended_fields: List[str]

@dataclass
class SearchConfig:
    """Configuration for search behavior"""
    max_results_per_source: int = 25
    request_timeout: int = 30
    requests_per_second: int = 5
    burst_size: int = 10

@dataclass
class ScreeningConfig:
    """Configuration for screening behavior"""
    use_ai_screening: bool = True
    inclusion_threshold: float = 0.7
    screening_prompt_template: str = ""

@dataclass
class AppraisalConfig:
    """Configuration for appraisal behavior"""
    use_ai_rationale: bool = True
    rubric_file: str = "rubric.yaml"
    red_max: float = 0.54
    amber_min: float = 0.55
    green_min: float = 0.75

@dataclass
class ModelSpecificConfig:
    """Configuration for a specific model"""
    temperature: float = 0.3
    max_tokens: int = 2000
    max_retries: int = 3
    timeout: int = 60
    cost_per_1k_tokens: Dict[str, float] = None

@dataclass
class LLMConfig:
    """Configuration for LLM behavior"""
    default_model: str = "gpt-4"
    fallback_model: str = "gpt-3.5-turbo"
    fast_model: str = "gpt-3.5-turbo"
    models: Dict[str, ModelSpecificConfig] = None
    rate_limits: Dict[str, int] = None
    retries: Dict[str, Any] = None
    observability: Dict[str, Any] = None
    security: Dict[str, Any] = None
    environments: Dict[str, Dict[str, Any]] = None

@dataclass 
class AppConfig:
    """Main application configuration"""
    deduplication: DeduplicationConfig
    metadata: MetadataConfig
    search: SearchConfig
    screening: ScreeningConfig
    appraisal: AppraisalConfig
    llm: LLMConfig

class ConfigLoader:
    """Loads and manages application configuration"""
    
    _instance: Optional['ConfigLoader'] = None
    _config: Optional[AppConfig] = None
    
    def __new__(cls) -> 'ConfigLoader':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
            self._config = self._load_config()
    
    def _load_config(self) -> AppConfig:
        """Load configuration from YAML file"""
        config_path = self._find_config_file()
        
        if not config_path.exists():
            return self._get_default_config()
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                yaml_data = yaml.safe_load(f) or {}
            
            return self._parse_config(yaml_data)
        except Exception as e:
            print(f"Warning: Failed to load config from {config_path}: {e}")
            print("Using default configuration")
            return self._get_default_config()
    
    def _find_config_file(self) -> Path:
        """Find the configuration file"""
        # Look in multiple locations
        search_paths = [
            Path.cwd() / "config.yaml",
            Path.cwd() / "config.yml", 
            Path(__file__).parent.parent / "config.yaml",
            Path(__file__).parent.parent / "config.yml",
        ]
        
        for path in search_paths:
            if path.exists():
                return path
        
        # Return the preferred location even if it doesn't exist
        return Path.cwd() / "config.yaml"
    
    def _parse_config(self, yaml_data: Dict[str, Any]) -> AppConfig:
        """Parse YAML data into configuration objects"""
        
        # Deduplication config
        dedup_data = yaml_data.get("deduplication", {})
        strategies = dedup_data.get("strategies", {})
        
        deduplication = DeduplicationConfig(
            title_similarity_threshold=dedup_data.get("title_similarity_threshold", 96),
            use_exact_matching=dedup_data.get("use_exact_matching", True),
            abstract_similarity_enabled=strategies.get("abstract_similarity", {}).get("enabled", False),
            abstract_similarity_threshold=strategies.get("abstract_similarity", {}).get("threshold", 85),
            author_similarity_enabled=strategies.get("author_similarity", {}).get("enabled", False),
            author_similarity_threshold=strategies.get("author_similarity", {}).get("threshold", 90)
        )
        
        # Metadata config
        metadata_data = yaml_data.get("metadata", {})
        metadata = MetadataConfig(
            core_fields=metadata_data.get("core_fields", self._get_default_core_fields()),
            extended_fields=metadata_data.get("extended_fields", self._get_default_extended_fields())
        )
        
        # Search config
        search_data = yaml_data.get("search", {})
        rate_limit = search_data.get("rate_limit", {})
        search = SearchConfig(
            max_results_per_source=search_data.get("max_results_per_source", 25),
            request_timeout=search_data.get("request_timeout", 30),
            requests_per_second=rate_limit.get("requests_per_second", 5),
            burst_size=rate_limit.get("burst_size", 10)
        )
        
        # Screening config
        screening_data = yaml_data.get("screening", {})
        screening = ScreeningConfig(
            use_ai_screening=screening_data.get("use_ai_screening", True),
            inclusion_threshold=screening_data.get("inclusion_threshold", 0.7),
            screening_prompt_template=screening_data.get("screening_prompt_template", "")
        )
        
        # Appraisal config
        appraisal_data = yaml_data.get("appraisal", {})
        thresholds = appraisal_data.get("quality_thresholds", {})
        appraisal = AppraisalConfig(
            use_ai_rationale=appraisal_data.get("use_ai_rationale", True),
            rubric_file=appraisal_data.get("rubric_file", "rubric.yaml"),
            red_max=thresholds.get("red_max", 0.54),
            amber_min=thresholds.get("amber_min", 0.55),
            green_min=thresholds.get("green_min", 0.75)
        )
        
        # LLM config
        llm_data = yaml_data.get("llm", {})
        
        # Parse model-specific configurations
        models_data = llm_data.get("models", {})
        models = {}
        for model_name, model_config in models_data.items():
            models[model_name] = ModelSpecificConfig(
                temperature=model_config.get("temperature", 0.3),
                max_tokens=model_config.get("max_tokens", 2000),
                max_retries=model_config.get("max_retries", 3),
                timeout=model_config.get("timeout", 60),
                cost_per_1k_tokens=model_config.get("cost_per_1k_tokens", {})
            )
        
        llm = LLMConfig(
            default_model=llm_data.get("default_model", "gpt-4"),
            fallback_model=llm_data.get("fallback_model", "gpt-3.5-turbo"),
            fast_model=llm_data.get("fast_model", "gpt-3.5-turbo"),
            models=models,
            rate_limits=llm_data.get("rate_limits", {}),
            retries=llm_data.get("retries", {}),
            observability=llm_data.get("observability", {}),
            security=llm_data.get("security", {}),
            environments=llm_data.get("environments", {})
        )
        
        return AppConfig(
            deduplication=deduplication,
            metadata=metadata,
            search=search,
            screening=screening,
            appraisal=appraisal,
            llm=llm
        )
    
    def _get_default_config(self) -> AppConfig:
        """Get default configuration when file is not available"""
        return AppConfig(
            deduplication=DeduplicationConfig(),
            metadata=MetadataConfig(
                core_fields=self._get_default_core_fields(),
                extended_fields=self._get_default_extended_fields()
            ),
            search=SearchConfig(),
            screening=ScreeningConfig(),
            appraisal=AppraisalConfig(),
            llm=LLMConfig()
        )
    
    def _get_default_core_fields(self) -> List[str]:
        """Get default core metadata fields"""
        return [
            "record_id", "title", "abstract", "authors", "year",
            "doi", "url", "source", "publication_type"
        ]
    
    def _get_default_extended_fields(self) -> List[str]:
        """Get default extended metadata fields"""
        return [
            "journal", "conference", "publisher", "volume", "issue", "pages",
            "language", "country", "pmid", "arxiv_id", "issn", "isbn",
            "subjects", "mesh_terms", "pdf_url", "fulltext_url", "open_access",
            "cited_by_count", "reference_count"
        ]
    
    @property
    def config(self) -> AppConfig:
        """Get the current configuration"""
        return self._config
    
    def reload(self) -> None:
        """Reload configuration from file"""
        self._config = self._load_config()

# Global configuration instance
_config_loader = ConfigLoader()

def get_config() -> AppConfig:
    """Get the global configuration instance"""
    return _config_loader.config

def reload_config() -> None:
    """Reload configuration from file"""
    _config_loader.reload()