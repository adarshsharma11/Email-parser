"""
Unit tests for the LLM skeleton module.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import os

from src.llm.llm_skeleton import (
    MockLLMProvider,
    LLMManager,
    answer_question
)


class TestMockLLMProvider:
    """Test cases for MockLLMProvider class."""
    
    def test_initialization(self):
        """Test MockLLMProvider initialization."""
        provider = MockLLMProvider("test-model")
        assert provider.model_name == "test-model"
        assert provider.get_provider_name() == "mock"
    
    def test_generate_response_vendor_question(self):
        """Test response generation for vendor-related questions."""
        provider = MockLLMProvider()
        
        response = provider.generate_response("Tell me about vendors")
        
        assert "vendor" in response["answer"].lower()
        assert response["provider"] == "mock"
        assert response["model"] == "mock-model"
        assert "tokens_used" in response
        assert "response_time" in response
    
    def test_generate_response_rule_question(self):
        """Test response generation for rule-related questions."""
        provider = MockLLMProvider()
        
        response = provider.generate_response("What are the rules?")
        
        assert "rule" in response["answer"].lower()
        assert response["provider"] == "mock"
    
    def test_generate_response_general_question(self):
        """Test response generation for general questions."""
        provider = MockLLMProvider()
        
        response = provider.generate_response("How are you?")
        
        assert "helpful response" in response["answer"].lower()
        assert response["provider"] == "mock"


class TestLLMManager:
    """Test cases for LLMManager class."""
    
    @patch.dict(os.environ, {'LLM_PROVIDER': 'local'})
    def test_initialization_with_local_provider(self):
        """Test LLMManager initialization with local provider."""
        manager = LLMManager()
        assert manager.provider is not None
        assert isinstance(manager.provider, MockLLMProvider)
    
    @patch.dict(os.environ, {'LLM_PROVIDER': 'openai', 'OPENAI_API_KEY': 'test-key'})
    @patch('src.llm.llm_skeleton.OpenAIProvider')
    def test_initialization_with_openai_provider(self, mock_openai_provider):
        """Test LLMManager initialization with OpenAI provider."""
        mock_provider = Mock()
        mock_openai_provider.return_value = mock_provider
        
        manager = LLMManager()
        
        mock_openai_provider.assert_called_with('test-key', 'mock-model')
        assert manager.provider == mock_provider
    
    @patch.dict(os.environ, {'LLM_PROVIDER': 'openai'})
    def test_initialization_with_missing_api_key(self):
        """Test LLMManager initialization with missing API key."""
        manager = LLMManager()
        # Should fall back to mock provider
        assert isinstance(manager.provider, MockLLMProvider)
    
    @patch('src.llm.llm_skeleton.build_prompt_context')
    def test_answer_question_with_context(self, mock_build_context):
        """Test answering question with context."""
        # Mock context
        mock_build_context.return_value = "Context: Test vendor information"
        
        # Mock provider
        mock_provider = Mock()
        mock_provider.generate_response.return_value = {
            "answer": "Test answer",
            "model": "test-model",
            "provider": "test-provider"
        }
        mock_provider.get_provider_name.return_value = "test-provider"
        
        manager = LLMManager()
        manager.provider = mock_provider
        
        result = manager.answer_question("What vendors do you have?", k=3)
        
        assert result["answer"] == "Test answer"
        assert result["question"] == "What vendors do you have?"
        assert result["context_sections_used"] == 3
        assert result["has_context"] is True
        assert result["provider"] == "test-provider"
        
        # Verify context was built
        mock_build_context.assert_called_with("What vendors do you have?", 3)
    
    @patch('src.llm.llm_skeleton.build_prompt_context')
    def test_answer_question_without_context(self, mock_build_context):
        """Test answering question without context."""
        # Mock no context
        mock_build_context.return_value = "No relevant context found."
        
        mock_provider = Mock()
        mock_provider.generate_response.return_value = {
            "answer": "General answer",
            "model": "test-model",
            "provider": "test-provider"
        }
        mock_provider.get_provider_name.return_value = "test-provider"
        
        manager = LLMManager()
        manager.provider = mock_provider
        
        result = manager.answer_question("General question")
        
        assert result["has_context"] is False
        assert "general knowledge" in mock_provider.generate_response.call_args[0][0].lower()
    
    def test_answer_question_with_error(self):
        """Test answering question when provider fails."""
        mock_provider = Mock()
        mock_provider.generate_response.side_effect = Exception("Provider error")
        mock_provider.get_provider_name.return_value = "test-provider"
        
        manager = LLMManager()
        manager.provider = mock_provider
        
        result = manager.answer_question("Test question")
        
        assert "Error processing question" in result["answer"]
        assert result["error"] == "Provider error"
        assert result["provider"] == "test-provider"


class TestLLMFunctions:
    """Test cases for module-level functions."""
    
    @patch('src.llm.llm_skeleton.get_llm_manager')
    def test_answer_question_function(self, mock_get_manager):
        """Test answer_question function."""
        mock_manager = Mock()
        mock_get_manager.return_value = mock_manager
        mock_manager.answer_question.return_value = {
            "answer": "Test answer",
            "provider": "test-provider"
        }
        
        result = answer_question("Test question", k=5, system_hint="Test hint")
        
        mock_manager.answer_question.assert_called_with("Test question", 5, "Test hint")
        assert result["answer"] == "Test answer"
        assert result["provider"] == "test-provider"


class TestProviderIntegration:
    """Integration tests for different providers."""
    
    @patch.dict(os.environ, {'LLM_PROVIDER': 'local', 'LLM_MODEL': 'test-model'})
    def test_local_provider_works_without_network(self):
        """Test that local provider works without network access."""
        manager = LLMManager()
        
        result = manager.answer_question("What is a vendor?")
        
        assert result["answer"] is not None
        assert result["provider"] == "mock"
        assert "error" not in result
    
    @patch.dict(os.environ, {'LLM_PROVIDER': 'invalid'})
    def test_invalid_provider_falls_back_to_mock(self):
        """Test that invalid provider falls back to mock."""
        manager = LLMManager()
        
        assert isinstance(manager.provider, MockLLMProvider)
        assert manager.provider.get_provider_name() == "mock"
