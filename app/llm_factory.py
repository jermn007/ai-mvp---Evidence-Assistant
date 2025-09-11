# app/llm_factory.py
"""
Centralized LLM Factory for consistent language model management
Provides dependency injection, lazy initialization, and testing hooks
"""
from __future__ import annotations

import os
import logging
from typing import Optional, Dict, Any, Protocol, runtime_checkable
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from langchain_core.callbacks import CallbackManager, BaseCallbackHandler
from langchain_core.outputs import LLMResult

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False

logger = logging.getLogger(__name__)

class ModelType(Enum):
    """Supported model types with their identifiers"""
    GPT4 = "gpt-4"
    GPT4_TURBO = "gpt-4-turbo-preview"
    GPT35_TURBO = "gpt-3.5-turbo"
    GPT35_TURBO_16K = "gpt-3.5-turbo-16k"

@dataclass
class ModelConfig:
    """Configuration for a specific model"""
    model_type: ModelType
    temperature: float = 0.3
    max_tokens: int = 2000
    max_retries: int = 3
    request_timeout: int = 60
    streaming: bool = False
    callbacks: Optional[list] = None

@dataclass
class LLMSettings:
    """Global LLM settings from configuration"""
    default_model: ModelType = ModelType.GPT4
    fallback_model: ModelType = ModelType.GPT35_TURBO
    enable_callbacks: bool = True
    enable_langsmith: bool = False
    langsmith_project: Optional[str] = None
    rate_limit_rpm: int = 60  # requests per minute
    enable_retries: bool = True
    mock_mode: bool = False  # for testing

class TokenUsageCallback(BaseCallbackHandler):
    """Callback to track token usage and costs"""
    
    def __init__(self):
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_cost = 0.0
        
    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Track token usage from LLM response"""
        if response.llm_output and "token_usage" in response.llm_output:
            usage = response.llm_output["token_usage"]
            self.total_tokens += usage.get("total_tokens", 0)
            self.prompt_tokens += usage.get("prompt_tokens", 0) 
            self.completion_tokens += usage.get("completion_tokens", 0)
            
            # Estimate cost (rough estimates for GPT models)
            model_name = response.llm_output.get("model_name", "")
            if "gpt-4" in model_name.lower():
                cost = (usage.get("prompt_tokens", 0) * 0.03 + 
                       usage.get("completion_tokens", 0) * 0.06) / 1000
            elif "gpt-3.5" in model_name.lower():
                cost = (usage.get("prompt_tokens", 0) * 0.0015 + 
                       usage.get("completion_tokens", 0) * 0.002) / 1000
            else:
                cost = 0.0
            
            self.total_cost += cost
            
    def get_usage_summary(self) -> Dict[str, Any]:
        """Get summary of token usage and costs"""
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "estimated_cost_usd": round(self.total_cost, 4)
        }

@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers"""
    
    def get_model(self, config: ModelConfig) -> BaseChatModel:
        """Get a configured language model instance"""
        ...
    
    def is_available(self) -> bool:
        """Check if the provider is available (API keys, etc.)"""
        ...

class OpenAIProvider:
    """OpenAI model provider using LangChain"""
    
    def __init__(self):
        self._api_key = os.getenv("OPENAI_API_KEY")
        self._models_cache: Dict[str, BaseChatModel] = {}
    
    def is_available(self) -> bool:
        """Check if OpenAI API key is available"""
        return self._api_key is not None and len(self._api_key.strip()) > 0
    
    def get_model(self, config: ModelConfig) -> BaseChatModel:
        """Get configured OpenAI model via LangChain"""
        if not self.is_available():
            raise ValueError("OpenAI API key not available")
        
        # Create cache key
        cache_key = f"{config.model_type.value}_{config.temperature}_{config.max_tokens}"
        
        if cache_key not in self._models_cache:
            # Setup callbacks
            callbacks = []
            if config.callbacks:
                callbacks.extend(config.callbacks)
                
            callback_manager = CallbackManager(callbacks) if callbacks else None
            
            # Configure retry settings
            max_retries = config.max_retries if TENACITY_AVAILABLE else 1
            
            # Create model instance with enhanced configuration
            model = ChatOpenAI(
                model=config.model_type.value,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                max_retries=max_retries,
                timeout=config.request_timeout,
                streaming=config.streaming,
                api_key=self._api_key,
                callback_manager=callback_manager
            )
            
            # Note: Retry logic is handled at the chain level in LangChain
            # to avoid Pydantic field validation issues with direct model wrapping
            
            self._models_cache[cache_key] = model
            
        return self._models_cache[cache_key]
    
    def _wrap_model_with_retry(self, model: BaseChatModel, config: ModelConfig) -> BaseChatModel:
        """Wrap model with retry logic"""
        # Skip retry wrapping for now to avoid Pydantic field validation issues
        # The retry logic is handled at the chain level in LangChain
        logger.debug(f"Skipping retry wrapper for {type(model)} to avoid Pydantic validation issues")
        return model

class MockProvider:
    """Mock provider for testing"""
    
    def is_available(self) -> bool:
        return True
    
    def get_model(self, config: ModelConfig) -> BaseChatModel:
        """Return a mock model for testing"""
        from unittest.mock import MagicMock
        mock_model = MagicMock(spec=BaseChatModel)
        
        # Configure mock responses
        mock_model.ainvoke = MagicMock(return_value=MagicMock(content="Mock response"))
        mock_model.invoke = MagicMock(return_value=MagicMock(content="Mock response"))
        
        return mock_model

class LLMFactory:
    """
    Centralized factory for language model management
    Provides consistent access patterns and configuration
    """
    
    def __init__(self, settings: Optional[LLMSettings] = None):
        self.settings = settings or LLMSettings()
        self._providers: Dict[str, LLMProvider] = {}
        self._token_callback = TokenUsageCallback()
        
        # Initialize providers
        self._setup_providers()
        
    def _setup_providers(self):
        """Initialize available providers"""
        if self.settings.mock_mode:
            self._providers["mock"] = MockProvider()
            logger.info("LLM Factory initialized in mock mode")
        else:
            # Setup OpenAI provider
            openai_provider = OpenAIProvider()
            if openai_provider.is_available():
                self._providers["openai"] = openai_provider
                logger.info("OpenAI provider initialized successfully")
            else:
                logger.warning("OpenAI provider not available - missing API key")
    
    def get_model(
        self, 
        model_type: Optional[ModelType] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        streaming: bool = False,
        enable_callbacks: bool = True
    ) -> BaseChatModel:
        """
        Get a configured language model
        
        Args:
            model_type: Type of model to use (defaults to configured default)
            temperature: Temperature setting (overrides default)
            max_tokens: Max tokens (overrides default)
            streaming: Enable streaming responses
            enable_callbacks: Enable usage tracking callbacks
            
        Returns:
            Configured BaseChatModel instance
            
        Raises:
            ValueError: If no providers are available
        """
        # Use default model if not specified
        if model_type is None:
            model_type = self.settings.default_model
        
        # Build configuration
        config = ModelConfig(
            model_type=model_type,
            temperature=temperature or 0.3,
            max_tokens=max_tokens or 2000,
            max_retries=self.settings.enable_retries and 3 or 0,
            streaming=streaming
        )
        
        # Add callbacks if enabled
        if enable_callbacks and self.settings.enable_callbacks:
            config.callbacks = [self._token_callback]
        
        # Try to get model from available providers
        if self.settings.mock_mode and "mock" in self._providers:
            try:
                return self._providers["mock"].get_model(config)
            except Exception as e:
                logger.error(f"Failed to get {model_type.value} model: {e}")
                
                # Try fallback model if different
                if model_type != self.settings.fallback_model:
                    logger.info(f"Trying fallback model: {self.settings.fallback_model.value}")
                    config.model_type = self.settings.fallback_model
                    return self._providers["mock"].get_model(config)
                raise
        
        if "openai" in self._providers:
            try:
                return self._providers["openai"].get_model(config)
            except Exception as e:
                logger.error(f"Failed to get {model_type.value} model: {e}")
                
                # Try fallback model if different
                if model_type != self.settings.fallback_model:
                    logger.info(f"Trying fallback model: {self.settings.fallback_model.value}")
                    config.model_type = self.settings.fallback_model
                    return self._providers["openai"].get_model(config)
                raise
        
        raise ValueError("No LLM providers available")
    
    def get_chat_model(self, **kwargs) -> BaseChatModel:
        """Convenience method for getting chat models"""
        return self.get_model(**kwargs)
    
    def get_fast_model(self, **kwargs) -> BaseChatModel:
        """Get a fast, cost-effective model for simple tasks"""
        return self.get_model(
            model_type=ModelType.GPT35_TURBO,
            temperature=kwargs.get('temperature', 0.1),
            max_tokens=kwargs.get('max_tokens', 500),
            **{k: v for k, v in kwargs.items() if k not in ['temperature', 'max_tokens']}
        )
    
    def get_smart_model(self, **kwargs) -> BaseChatModel:
        """Get a high-capability model for complex tasks"""
        return self.get_model(
            model_type=ModelType.GPT4,
            temperature=kwargs.get('temperature', 0.3),
            max_tokens=kwargs.get('max_tokens', 2000),
            **{k: v for k, v in kwargs.items() if k not in ['temperature', 'max_tokens']}
        )
    
    def is_available(self) -> bool:
        """Check if any LLM providers are available"""
        return len(self._providers) > 0
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get token usage statistics"""
        return self._token_callback.get_usage_summary()
    
    def reset_usage_stats(self):
        """Reset token usage statistics"""
        self._token_callback = TokenUsageCallback()
        
    def setup_langsmith(self, project_name: str, api_key: Optional[str] = None):
        """Setup LangSmith integration for observability"""
        try:
            langsmith_api_key = api_key or os.getenv("LANGSMITH_API_KEY")
            if langsmith_api_key:
                # Try to set environment variables
                os.environ["LANGCHAIN_TRACING_V2"] = "true"
                os.environ["LANGCHAIN_PROJECT"] = project_name
                os.environ["LANGCHAIN_API_KEY"] = langsmith_api_key
                
                # Optional: Enable additional tracing features
                os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
                
                # Only enable if all environment setup succeeded
                self.settings.enable_langsmith = True
                self.settings.langsmith_project = project_name
                logger.info(f"LangSmith integration enabled for project: {project_name}")
                
                # Log configuration for debugging
                logger.debug(f"LangSmith configuration: project={project_name}, endpoint={os.environ.get('LANGCHAIN_ENDPOINT')}")
            else:
                logger.warning("LangSmith API key not found - observability features disabled")
                self.settings.enable_langsmith = False
        except Exception as e:
            logger.error(f"Failed to setup LangSmith: {e}")
            self.settings.enable_langsmith = False
    
    def add_custom_tags(self, tags: Dict[str, str]):
        """Add custom tags to all LLM operations for better observability"""
        try:
            # Set custom tags as environment variables for LangSmith
            for key, value in tags.items():
                env_key = f"LANGCHAIN_TAG_{key.upper()}"
                os.environ[env_key] = str(value)
            logger.debug(f"Added custom tags for observability: {tags}")
        except Exception as e:
            logger.warning(f"Failed to add custom tags: {e}")
    
    def get_observability_summary(self) -> Dict[str, Any]:
        """Get comprehensive observability summary"""
        summary = {
            "factory_status": {
                "providers_available": list(self._providers.keys()),
                "langsmith_enabled": self.settings.enable_langsmith,
                "langsmith_project": self.settings.langsmith_project,
                "callbacks_enabled": self.settings.enable_callbacks
            },
            "usage_stats": self.get_usage_stats(),
            "configuration": {
                "default_model": self.settings.default_model.value,
                "fallback_model": self.settings.fallback_model.value,
                "rate_limit_rpm": self.settings.rate_limit_rpm,
                "retries_enabled": self.settings.enable_retries
            }
        }
        
        # Add environment info for debugging
        langsmith_vars = {k: v for k, v in os.environ.items() if k.startswith("LANGCHAIN_")}
        if langsmith_vars:
            summary["langsmith_environment"] = langsmith_vars
            
        return summary

# Global factory instance
_factory: Optional[LLMFactory] = None

def get_llm_factory(settings: Optional[LLMSettings] = None) -> LLMFactory:
    """Get the global LLM factory instance"""
    global _factory
    if _factory is None:
        from app.config import get_config
        
        # Load settings from configuration
        config = get_config()
        llm_config = getattr(config, 'llm', None)
        if llm_config:
            llm_settings = LLMSettings(
                enable_callbacks=getattr(llm_config, 'enable_callbacks', True),
                enable_langsmith=getattr(llm_config, 'enable_langsmith', False),
                mock_mode=os.getenv("LLM_MOCK_MODE", "false").lower() == "true"
            )
        else:
            llm_settings = LLMSettings(
                mock_mode=os.getenv("LLM_MOCK_MODE", "false").lower() == "true"
            )
        
        _factory = LLMFactory(settings or llm_settings)
        
        # Setup LangSmith if configured
        if _factory.settings.enable_langsmith:
            llm_config = getattr(config, 'llm', None)
            if llm_config and hasattr(llm_config, 'langsmith_project'):
                project_name = llm_config.langsmith_project
            else:
                project_name = 'ai-mvp-evidence-assistant'
            _factory.setup_langsmith(project_name)
    
    return _factory

def get_chat_model(**kwargs) -> BaseChatModel:
    """Convenience function to get a chat model"""
    return get_llm_factory().get_chat_model(**kwargs)

def get_fast_model(**kwargs) -> BaseChatModel:
    """Convenience function to get a fast model"""
    return get_llm_factory().get_fast_model(**kwargs)

def get_smart_model(**kwargs) -> BaseChatModel:
    """Convenience function to get a smart model"""
    return get_llm_factory().get_smart_model(**kwargs)

def is_llm_available() -> bool:
    """Check if LLM services are available"""
    return get_llm_factory().is_available()

def reset_llm_factory():
    """Reset the global factory (useful for testing)"""
    global _factory
    _factory = None