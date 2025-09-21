"""
LLM Skeleton - Provider-agnostic Q&A interface with RAG context.
"""
import os
from typing import Dict, Optional, Any
from abc import ABC, abstractmethod
import structlog

from ..utils.logger import get_logger
from ..rag.rag_data import build_prompt_context
from config.settings import app_config


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def generate_response(self, prompt: str, system_hint: Optional[str] = None) -> Dict[str, Any]:
        """Generate response from the LLM."""
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the provider name."""
        pass


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing and local development."""
    
    def __init__(self, model_name: str = "mock-model"):
        self.model_name = model_name
        self.logger = get_logger("mock_llm")
    
    def generate_response(self, prompt: str, system_hint: Optional[str] = None) -> Dict[str, Any]:
        """Generate a mock response."""
        self.logger.info("Generating mock response", prompt_length=len(prompt))
        
        # Simple mock response based on prompt content
        if "vendor" in prompt.lower():
            answer = "Based on the vendor information provided, I can help you with vendor-related questions."
        elif "rule" in prompt.lower():
            answer = "According to the rules and guidelines, here's what you need to know."
        elif "recommendation" in prompt.lower() or "rec" in prompt.lower():
            answer = "Based on the recommendations, here's my advice."
        else:
            answer = "I understand your question. Here's a helpful response based on the available context."
        
        return {
            "answer": answer,
            "model": self.model_name,
            "provider": "mock",
            "tokens_used": len(prompt.split()) + len(answer.split()),
            "response_time": 0.1
        }
    
    def get_provider_name(self) -> str:
        return "mock"


class OpenAIProvider(LLMProvider):
    """OpenAI provider implementation."""
    
    def __init__(self, api_key: str, model_name: str = "gpt-3.5-turbo"):
        self.api_key = api_key
        self.model_name = model_name
        self.logger = get_logger("openai_llm")
        
        # We'll use direct HTTP requests since the client library has compatibility issues
        try:
            import requests
            self.requests = requests
        except ImportError:
            raise ImportError("requests package required for OpenAI API calls. Run: pip install requests")
    
    def generate_response(self, prompt: str, system_hint: Optional[str] = None) -> Dict[str, Any]:
        """Generate response using OpenAI API via direct HTTP requests."""
        try:
            messages = []
            
            # Add system message if provided
            if system_hint:
                messages.append({"role": "system", "content": system_hint})
            
            # Add user message
            messages.append({"role": "user", "content": prompt})
            
            # Make direct API call
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model_name,
                "messages": messages,
                "max_tokens": 1000,
                "temperature": 0.7
            }
            
            response = self.requests.post(
                "https://api.openai.com/v1/chat/completions", 
                json=payload, 
                headers=headers, 
                timeout=30
            )
            
            self.logger.info("OpenAI API request", 
                           status_code=response.status_code,
                           model=self.model_name)
            
            response.raise_for_status()
            
            data = response.json()
            answer = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            
            return {
                "answer": answer,
                "model": self.model_name,
                "provider": "openai",
                "tokens_used": usage.get("total_tokens", 0),
                "response_time": usage.get("total_tokens", 0) / 1000
            }
            
        except Exception as e:
            self.logger.error("OpenAI API error", error=str(e))
            return {
                "answer": f"Error generating response: {str(e)}",
                "model": self.model_name,
                "provider": "openai",
                "error": str(e)
            }
    
    def get_provider_name(self) -> str:
        return "openai"


class GeminiProvider(LLMProvider):
    """Google Gemini provider implementation."""
    
    def __init__(self, api_key: str, model_name: str = "gemini-pro"):
        self.api_key = api_key
        self.model_name = model_name
        self.logger = get_logger("gemini_llm")
        
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(model_name)
        except ImportError:
            raise ImportError("Google Generative AI package not installed. Run: pip install google-generativeai")
    
    def generate_response(self, prompt: str, system_hint: Optional[str] = None) -> Dict[str, Any]:
        """Generate response using Gemini API."""
        try:
            # Combine system hint and prompt
            full_prompt = prompt
            if system_hint:
                full_prompt = f"{system_hint}\n\n{prompt}"
            
            response = self.model.generate_content(full_prompt)
            
            return {
                "answer": response.text,
                "model": self.model_name,
                "provider": "gemini",
                "tokens_used": response.usage_metadata.total_token_count if hasattr(response, 'usage_metadata') else 0,
                "response_time": 0.5  # Rough estimate
            }
            
        except Exception as e:
            self.logger.error("Gemini API error", error=str(e))
            return {
                "answer": f"Error generating response: {str(e)}",
                "model": self.model_name,
                "provider": "gemini",
                "error": str(e)
            }
    
    def get_provider_name(self) -> str:
        return "gemini"


class LLMManager:
    """Manages LLM providers and handles Q&A operations."""
    
    def __init__(self):
        self.logger = get_logger("llm_manager")
        self.provider: Optional[LLMProvider] = None
        self._initialize_provider()
    
    def _initialize_provider(self):
        """Initialize the configured LLM provider."""
        provider_name = os.getenv("LLM_PROVIDER", "local").lower()
        model_name = os.getenv("LLM_MODEL", "mock-model")
        
        try:
            if provider_name == "openai":
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OPENAI_API_KEY not found in environment")
                self.provider = OpenAIProvider(api_key, model_name)
                
            elif provider_name == "gemini":
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise ValueError("GOOGLE_API_KEY not found in environment")
                self.provider = GeminiProvider(api_key, model_name)
                
            else:  # local/mock
                self.provider = MockLLMProvider(model_name)
                
            self.logger.info(f"Initialized {provider_name} provider", model=model_name)
            
        except Exception as e:
            self.logger.warning(f"Failed to initialize {provider_name}, falling back to mock", error=str(e))
            self.provider = MockLLMProvider("fallback-model")
    
    def answer_question(self, question: str, k: int = 6, system_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Answer a question using RAG context and the configured LLM.
        
        Args:
            question: The question to answer
            k: Number of context sections to include
            system_hint: Optional system prompt to guide the LLM
            
        Returns:
            Dictionary with answer and metadata
        """
        try:
            # Build context from RAG
            context = build_prompt_context(question, k)
            
            # Construct the full prompt
            if context and context != "No relevant context found.":
                full_prompt = f"""Context Information:
{context}

Question: {question}

Please answer the question based on the context provided above. If the context doesn't contain enough information to answer the question, say so."""
            else:
                full_prompt = f"Question: {question}\n\nPlease answer this question based on your general knowledge."
            
            # Generate response
            response = self.provider.generate_response(full_prompt, system_hint)
            
            # Add metadata
            response.update({
                "question": question,
                "context_sections_used": k,
                "has_context": context != "No relevant context found."
            })
            
            self.logger.info("Generated answer", 
                           provider=self.provider.get_provider_name(),
                           question_length=len(question),
                           answer_length=len(response.get("answer", "")))
            
            return response
            
        except Exception as e:
            self.logger.error("Error answering question", error=str(e))
            return {
                "answer": f"Error processing question: {str(e)}",
                "question": question,
                "error": str(e),
                "provider": self.provider.get_provider_name() if self.provider else "unknown"
            }


# Global instance
_llm_manager = None


def get_llm_manager() -> LLMManager:
    """Get the global LLM manager instance."""
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LLMManager()
    return _llm_manager


def answer_question(question: str, k: int = 6, system_hint: Optional[str] = None) -> Dict[str, Any]:
    """
    Answer a question using RAG context and configured LLM.
    
    Args:
        question: The question to answer
        k: Number of context sections to include
        system_hint: Optional system prompt
        
    Returns:
        Dictionary with answer and metadata
    """
    return get_llm_manager().answer_question(question, k, system_hint)
