"""
Unit tests for the RAG data module.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.rag.rag_data import (
    RAGDataManager,
    load_constants,
    get_context_sections,
    build_prompt_context
)


class TestRAGDataManager:
    """Test cases for RAGDataManager class."""
    
    @pytest.fixture
    def mock_supabase(self):
        """Mock Supabase client creation and instance."""
        with patch('src.rag.rag_data.create_client') as mock_create:
            mock_instance = Mock()
            mock_create.return_value = mock_instance
            # Ensure supabase_config has values so initialization succeeds
            from src.rag.rag_data import supabase_config
            supabase_config.url = 'http://localhost'
            supabase_config.service_role_key = 'service-role'
            supabase_config.anon_key = 'anon'
            yield mock_instance
    
    @pytest.fixture
    def rag_manager(self, mock_supabase):
        """Create RAGDataManager instance for testing."""
        return RAGDataManager(cache_ttl_hours=1)
    
    def test_initialization_with_supabase(self, mock_supabase):
        """Test RAGDataManager initialization with Supabase available."""
        manager = RAGDataManager()
        assert manager.supabase is not None
    
    def test_initialization_without_supabase(self):
        """Test RAGDataManager initialization without Supabase."""
        with patch('src.rag.rag_data.create_client', side_effect=Exception("No Supabase")):
            manager = RAGDataManager()
            assert manager.supabase is None
    
    def test_load_constants_empty(self, rag_manager, mock_supabase):
        """Test loading constants when Supabase returns empty tables."""
        mock_supabase.table.return_value.select.return_value.execute.return_value = Mock(data=[])
        
        result = rag_manager.load_constants()
        
        assert result['vendors'] == []
        assert result['recs'] == []
        assert result['rules'] == []
    
    def test_load_constants_with_data(self, rag_manager, mock_supabase):
        """Test loading constants with actual data from Supabase."""
        # Mock responses for 3 tables
        def make_resp(data):
            m = Mock()
            m.data = data
            return m
        mock_supabase.table.return_value.select.return_value.execute.side_effect = [
            make_resp([{"id": "doc1", "name": "Vendor 1", "type": "cleaning"}, {"id": "doc2", "title": "Rule 1", "content": "Always clean"}]),
            make_resp([{"id": "doc1", "name": "Vendor 1", "type": "cleaning"}, {"id": "doc2", "title": "Rule 1", "content": "Always clean"}]),
            make_resp([{"id": "doc1", "name": "Vendor 1", "type": "cleaning"}, {"id": "doc2", "title": "Rule 1", "content": "Always clean"}]),
        ]
        
        result = rag_manager.load_constants()
        
        assert len(result['vendors']) == 2
        assert len(result['recs']) == 2
        assert len(result['rules']) == 2
    
    def test_cache_functionality(self, rag_manager, mock_supabase):
        """Test that caching works correctly."""
        # Mock empty collections
        mock_supabase.table.return_value.select.return_value.execute.return_value = Mock(data=[])
        
    # First call should hit Supabase
        result1 = rag_manager.load_constants()
        
        # Second call should use cache
        result2 = rag_manager.load_constants()
        
        # Both should be the same
        assert result1 == result2
        
    # Supabase should only be called once per collection
        assert mock_supabase.table.return_value.select.return_value.execute.call_count == 3
    
    def test_force_refresh_bypasses_cache(self, rag_manager, mock_supabase):
        """Test that force_refresh bypasses cache."""
        mock_supabase.table.return_value.select.return_value.execute.return_value = Mock(data=[])
        
        # First call
        rag_manager.load_constants()
        
        # Second call with force refresh
        rag_manager.load_constants(force_refresh=True)
        
    # Should be called twice per collection (6 total calls)
        assert mock_supabase.table.return_value.select.return_value.execute.call_count == 6
    
    def test_get_context_sections(self, rag_manager):
        """Test context section retrieval."""
        # Mock some data in cache for all collections
        rag_manager.cache['constants_vendors'] = Mock()
        rag_manager.cache['constants_vendors'].data = [
            {"_id": "v1", "name": "Cleaning Service", "description": "Professional cleaning"},
            {"_id": "v2", "name": "Maintenance", "description": "Repair services"}
        ]
        rag_manager.cache['constants_recs'] = Mock()
        rag_manager.cache['constants_recs'].data = [
            {"_id": "r1", "title": "Cleaning Recommendation", "content": "Use professional cleaners"}
        ]
        rag_manager.cache['constants_rules'] = Mock()
        rag_manager.cache['constants_rules'].data = [
            {"_id": "r1", "title": "Cleaning Rules", "content": "Always clean after checkout"}
        ]
        
        # Mock cache validity
        rag_manager._is_cache_valid = lambda x: True
        
        sections = rag_manager.get_context_sections("cleaning", k=3)
        
        assert len(sections) > 0
        assert any("cleaning" in str(section).lower() for section in sections)
    
    def test_build_prompt_context(self, rag_manager):
        """Test prompt context building."""
        # Mock context sections
        sections = [
            ("vendors:v1", {"name": "Test Vendor", "description": "Test description"}),
            ("rules:r1", {"title": "Test Rule", "content": "Test content"})
        ]
        
        rag_manager.get_context_sections = Mock(return_value=sections)
        
        context = rag_manager.build_prompt_context("test question")
        
        assert "Test Vendor" in context
        assert "Test Rule" in context
        assert "[vendors:v1]" in context
        assert "[rules:r1]" in context


class TestRAGFunctions:
    """Test cases for module-level functions."""
    
    @patch('src.rag.rag_data.get_rag_manager')
    def test_load_constants_function(self, mock_get_manager):
        """Test load_constants function."""
        mock_manager = Mock()
        mock_get_manager.return_value = mock_manager
        mock_manager.load_constants.return_value = {"vendors": [], "recs": [], "rules": []}
        
        result = load_constants(force_refresh=True)
        
        mock_manager.load_constants.assert_called_with(True)
        assert result == {"vendors": [], "recs": [], "rules": []}
    
    @patch('src.rag.rag_data.get_rag_manager')
    def test_get_context_sections_function(self, mock_get_manager):
        """Test get_context_sections function."""
        mock_manager = Mock()
        mock_get_manager.return_value = mock_manager
        mock_manager.get_context_sections.return_value = [("test", {"data": "value"})]
        
        result = get_context_sections("test question", k=5)
        
        mock_manager.get_context_sections.assert_called_with("test question", 5)
        assert result == [("test", {"data": "value"})]
    
    @patch('src.rag.rag_data.get_rag_manager')
    def test_build_prompt_context_function(self, mock_get_manager):
        """Test build_prompt_context function."""
        mock_manager = Mock()
        mock_get_manager.return_value = mock_manager
        mock_manager.build_prompt_context.return_value = "Test context"
        
        result = build_prompt_context("test question", k=3)
        
        mock_manager.build_prompt_context.assert_called_with("test question", 3)
        assert result == "Test context"
