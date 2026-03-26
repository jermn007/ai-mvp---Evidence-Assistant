"""
Comprehensive tests for the LLM factory and related infrastructure
"""
from __future__ import annotations
import os
import sys
import pytest
from unittest.mock import Mock, patch, MagicMock

# Add the parent directory to Python path to enable app imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.llm_factory import (
    LLMFactory, LLMSettings, ModelType, ModelConfig,
    OpenAIProvider, MockProvider, get_llm_factory, reset_llm_factory
)


class TestModelTypes:
    """Test model type enumeration"""
    
    def test_model_types(self):
        """Test that model types are properly defined"""
        assert ModelType.GPT4.value == "gpt-4"
        assert ModelType.GPT35_TURBO.value == "gpt-3.5-turbo"
        assert ModelType.GPT4_TURBO.value == "gpt-4-turbo-preview"


class TestModelConfig:
    """Test model configuration"""
    
    def test_default_config(self):
        """Test default model configuration"""
        config = ModelConfig(model_type=ModelType.GPT4)
        
        assert config.model_type == ModelType.GPT4
        assert config.temperature == 0.3
        assert config.max_tokens == 2000
        assert config.max_retries == 3
        assert config.request_timeout == 60
        assert config.streaming == False
        assert config.callbacks is None
    
    def test_custom_config(self):
        """Test custom model configuration"""
        config = ModelConfig(
            model_type=ModelType.GPT35_TURBO,
            temperature=0.1,
            max_tokens=1000,
            streaming=True
        )
        
        assert config.model_type == ModelType.GPT35_TURBO
        assert config.temperature == 0.1
        assert config.max_tokens == 1000
        assert config.streaming == True


class TestLLMSettings:
    """Test LLM settings"""
    
    def test_default_settings(self):
        """Test default LLM settings"""
        settings = LLMSettings()
        
        assert settings.default_model == ModelType.GPT4
        assert settings.fallback_model == ModelType.GPT35_TURBO
        assert settings.enable_callbacks == True
        assert settings.enable_langsmith == False
        assert settings.rate_limit_rpm == 60
        assert settings.mock_mode == False
    
    def test_custom_settings(self):
        """Test custom LLM settings"""
        settings = LLMSettings(
            default_model=ModelType.GPT35_TURBO,
            enable_langsmith=True,
            langsmith_project="test-project",
            mock_mode=True
        )
        
        assert settings.default_model == ModelType.GPT35_TURBO
        assert settings.enable_langsmith == True
        assert settings.langsmith_project == "test-project"
        assert settings.mock_mode == True


class TestOpenAIProvider:
    """Test OpenAI provider"""
    
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_provider_available_with_key(self):
        """Test provider availability with API key"""
        provider = OpenAIProvider()
        assert provider.is_available() == True
    
    @patch.dict(os.environ, {}, clear=True)
    def test_provider_unavailable_without_key(self):
        """Test provider unavailability without API key"""
        provider = OpenAIProvider()
        assert provider.is_available() == False
    
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch('app.llm_factory.ChatOpenAI')
    def test_get_model(self, mock_chat_openai):
        """Test getting a model from provider"""
        mock_model = Mock()
        mock_chat_openai.return_value = mock_model
        
        provider = OpenAIProvider()
        config = ModelConfig(model_type=ModelType.GPT4)
        
        model = provider.get_model(config)
        
        mock_chat_openai.assert_called_once()
        assert model == mock_model
    
    @patch.dict(os.environ, {}, clear=True)
    def test_get_model_without_key_raises_error(self):
        """Test that getting model without API key raises error"""
        provider = OpenAIProvider()
        config = ModelConfig(model_type=ModelType.GPT4)
        
        with pytest.raises(ValueError, match="OpenAI API key not available"):
            provider.get_model(config)


class TestMockProvider:
    """Test mock provider for testing"""
    
    def test_mock_provider_always_available(self):
        """Test that mock provider is always available"""
        provider = MockProvider()
        assert provider.is_available() == True
    
    def test_get_mock_model(self):
        """Test getting a mock model"""
        provider = MockProvider()
        config = ModelConfig(model_type=ModelType.GPT4)
        
        model = provider.get_model(config)
        
        # Should return a mock object
        assert hasattr(model, 'ainvoke')
        assert hasattr(model, 'invoke')


class TestLLMFactory:
    """Test LLM factory"""
    
    def setup_method(self):
        """Setup for each test"""
        # Reset global factory state
        reset_llm_factory()
    
    def test_factory_initialization_mock_mode(self):
        """Test factory initialization in mock mode"""
        settings = LLMSettings(mock_mode=True)
        factory = LLMFactory(settings)
        
        assert factory.is_available() == True
        assert "mock" in factory._providers
    
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_factory_initialization_normal_mode(self):
        """Test factory initialization in normal mode"""
        settings = LLMSettings(mock_mode=False)
        factory = LLMFactory(settings)
        
        assert factory.is_available() == True
        assert "openai" in factory._providers
    
    @patch.dict(os.environ, {}, clear=True)
    def test_factory_initialization_no_providers(self):
        """Test factory initialization with no available providers"""
        settings = LLMSettings(mock_mode=False)
        factory = LLMFactory(settings)
        
        assert factory.is_available() == False
        assert len(factory._providers) == 0
    
    def test_get_model_mock_mode(self):
        """Test getting model in mock mode"""
        settings = LLMSettings(mock_mode=True)
        factory = LLMFactory(settings)
        
        model = factory.get_model()
        
        assert model is not None
        assert hasattr(model, 'ainvoke')
    
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch('app.llm_factory.ChatOpenAI')
    def test_get_model_normal_mode(self, mock_chat_openai):
        """Test getting model in normal mode"""
        mock_model = Mock()
        mock_chat_openai.return_value = mock_model
        
        settings = LLMSettings(mock_mode=False)
        factory = LLMFactory(settings)
        
        model = factory.get_model()
        
        assert model == mock_model
        mock_chat_openai.assert_called_once()
    
    def test_get_fast_model(self):
        """Test getting fast model"""
        settings = LLMSettings(mock_mode=True)
        factory = LLMFactory(settings)
        
        model = factory.get_fast_model()
        
        assert model is not None
    
    def test_get_smart_model(self):
        """Test getting smart model"""
        settings = LLMSettings(mock_mode=True)
        factory = LLMFactory(settings)
        
        model = factory.get_smart_model()
        
        assert model is not None
    
    def test_fallback_model_usage(self):
        """Test fallback to different model on failure"""
        settings = LLMSettings(mock_mode=True)
        factory = LLMFactory(settings)
        
        # Mock the primary model to fail
        with patch.object(factory._providers["mock"], "get_model") as mock_get_model:
            # First call fails, second call (fallback) succeeds
            mock_get_model.side_effect = [Exception("Primary failed"), Mock()]
            
            # This should succeed using fallback
            model = factory.get_model(model_type=ModelType.GPT4)
            
            assert model is not None
            assert mock_get_model.call_count == 2
    
    def test_usage_stats_tracking(self):
        """Test usage statistics tracking"""
        settings = LLMSettings(mock_mode=True)
        factory = LLMFactory(settings)
        
        # Initial stats should be empty
        stats = factory.get_usage_stats()
        assert stats["total_tokens"] == 0
        assert stats["estimated_cost_usd"] == 0.0
        
        # Reset stats
        factory.reset_usage_stats()
        stats = factory.get_usage_stats()
        assert stats["total_tokens"] == 0


class TestLangSmithIntegration:
    """Test LangSmith integration"""
    
    def setup_method(self):
        """Setup for each test"""
        reset_llm_factory()
        # Clear any existing LangSmith environment variables
        langsmith_vars = [k for k in os.environ.keys() if k.startswith("LANGCHAIN_")]
        for var in langsmith_vars:
            os.environ.pop(var, None)
    
    @patch.dict(os.environ, {"LANGSMITH_API_KEY": "test-langsmith-key"})
    def test_langsmith_setup(self):
        """Test LangSmith setup"""
        settings = LLMSettings(mock_mode=True)
        factory = LLMFactory(settings)
        
        factory.setup_langsmith("test-project", "test-key")
        
        assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
        assert os.environ.get("LANGCHAIN_PROJECT") == "test-project"
        assert os.environ.get("LANGCHAIN_API_KEY") == "test-key"
        assert factory.settings.enable_langsmith == True
        assert factory.settings.langsmith_project == "test-project"
    
    def test_langsmith_setup_without_key(self):
        """Test LangSmith setup without API key"""
        settings = LLMSettings(mock_mode=True)
        factory = LLMFactory(settings)
        
        factory.setup_langsmith("test-project")
        
        # Should not enable LangSmith without API key
        assert factory.settings.enable_langsmith == False
    
    def test_custom_tags(self):
        """Test adding custom tags for observability"""
        settings = LLMSettings(mock_mode=True)
        factory = LLMFactory(settings)
        
        tags = {"experiment": "test", "version": "1.0"}
        factory.add_custom_tags(tags)
        
        assert os.environ.get("LANGCHAIN_TAG_EXPERIMENT") == "test"
        assert os.environ.get("LANGCHAIN_TAG_VERSION") == "1.0"
    
    def test_observability_summary(self):
        """Test observability summary"""
        settings = LLMSettings(mock_mode=True, enable_langsmith=True)
        factory = LLMFactory(settings)
        
        summary = factory.get_observability_summary()
        
        assert "factory_status" in summary
        assert "usage_stats" in summary
        assert "configuration" in summary
        assert summary["factory_status"]["providers_available"] == ["mock"]
        assert summary["factory_status"]["langsmith_enabled"] == True


class TestGlobalFactoryFunctions:
    """Test global factory functions"""
    
    def setup_method(self):
        """Setup for each test"""
        reset_llm_factory()
    
    @patch.dict(os.environ, {"LLM_MOCK_MODE": "true"})
    def test_get_llm_factory_singleton(self):
        """Test that get_llm_factory returns singleton instance"""
        factory1 = get_llm_factory()
        factory2 = get_llm_factory()
        
        assert factory1 is factory2
    
    def test_convenience_functions(self):
        """Test convenience functions"""
        from app.llm_factory import get_chat_model, get_fast_model, get_smart_model, is_llm_available
        
        # Set mock mode for testing
        with patch('app.llm_factory.os.getenv') as mock_getenv:
            mock_getenv.side_effect = lambda key, default=None: "true" if key == "LLM_MOCK_MODE" else default
            
            # Reset factory to use new environment
            reset_llm_factory()
            
            # Test availability
            assert is_llm_available() == True
            
            # Test convenience functions
            chat_model = get_chat_model()
            fast_model = get_fast_model()
            smart_model = get_smart_model()
            
            assert chat_model is not None
            assert fast_model is not None
            assert smart_model is not None


class TestErrorHandling:
    """Test error handling scenarios"""
    
    def setup_method(self):
        """Setup for each test"""
        reset_llm_factory()
    
    def test_no_providers_available_error(self):
        """Test error when no providers are available"""
        settings = LLMSettings(mock_mode=False)
        factory = LLMFactory(settings)
        
        # Clear providers to simulate no availability
        factory._providers.clear()
        
        with pytest.raises(ValueError, match="No LLM providers available"):
            factory.get_model()
    
    def test_model_creation_failure_with_fallback(self):
        """Test model creation failure with successful fallback"""
        settings = LLMSettings(mock_mode=True)
        factory = LLMFactory(settings)
        
        # Mock provider to fail on first model, succeed on fallback
        with patch.object(factory._providers["mock"], "get_model") as mock_get_model:
            mock_get_model.side_effect = [Exception("Primary failed"), Mock()]
            
            # Should succeed with fallback
            model = factory.get_model(model_type=ModelType.GPT4)
            assert model is not None
    
    def test_langsmith_setup_failure(self):
        """Test LangSmith setup failure handling"""
        settings = LLMSettings(mock_mode=True)
        factory = LLMFactory(settings)
        
        # Mock the entire os module to raise exception when accessing environ
        with patch('app.llm_factory.os.environ') as mock_environ:
            mock_environ.__setitem__.side_effect = Exception("Environment error")
            
            # Should not raise, just log warning
            factory.setup_langsmith("test-project", "test-key")
            
            # LangSmith should not be enabled
            assert factory.settings.enable_langsmith == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])