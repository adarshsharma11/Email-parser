"""
RAG Data Layer - Load and cache constant data for retrieval.
"""
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import structlog

from ..utils.logger import get_logger
from config.settings import app_config, supabase_config
try:
    from supabase import create_client  # type: ignore
except Exception:  # pragma: no cover
    create_client = None  # type: ignore


@dataclass
class CacheEntry:
    """Cache entry with data and timestamp."""
    data: Dict
    timestamp: float
    ttl: int  # TTL in seconds


class RAGDataManager:
    """Manages loading and caching of constant data for RAG operations."""
    
    def __init__(self, cache_ttl_hours: int = 24):
        self.logger = get_logger("rag_data")
        self.cache_ttl_hours = cache_ttl_hours
        self.cache: Dict[str, CacheEntry] = {}
        self.supabase = None
        
        # Initialize Supabase client if available
        try:
            if not supabase_config.url or not supabase_config.get_auth_key():
                raise RuntimeError("Supabase configuration missing")
            if create_client is None:
                raise RuntimeError("supabase package not installed")
            self.supabase = create_client(supabase_config.url, supabase_config.get_auth_key())
        except Exception as e:
            self.logger.warning("Supabase client not available, using empty data", error=str(e))
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid."""
        if cache_key not in self.cache:
            return False
        
        entry = self.cache[cache_key]
        return (time.time() - entry.timestamp) < entry.ttl
    
    def _load_from_supabase(self, table_name: str) -> List[Dict]:
        """Load data from a Supabase table."""
        if not self.supabase:
            self.logger.warning(f"Supabase not available, returning empty {table_name}")
            return []
        try:
            res = self.supabase.table(table_name).select("*").execute()
            rows = getattr(res, "data", []) or getattr(res, "json", {}).get("data", [])
            # Ensure an _id exists for compatibility with downstream formatting
            for idx, row in enumerate(rows):
                row.setdefault("_id", row.get("id", str(idx)))
            self.logger.info(f"Loaded {len(rows)} records from {table_name}")
            return rows
        except Exception as e:
            self.logger.error(f"Error loading {table_name} from Supabase", error=str(e))
            return []
    
    def load_constants(self, force_refresh: bool = False) -> Dict[str, List[Dict]]:
        """
    Load and cache constant data from Supabase.
        
        Args:
            force_refresh: If True, bypass cache and reload from Firestore
            
        Returns:
            Dictionary with 'vendors', 'recs', 'rules' collections
        """
        collections = ['vendors', 'recs', 'rules']
        result = {}
        
        for collection in collections:
            cache_key = f"constants_{collection}"
            
            # Check cache first (unless force refresh)
            if not force_refresh and self._is_cache_valid(cache_key):
                result[collection] = self.cache[cache_key].data
                self.logger.debug(f"Using cached {collection} data")
                continue
            
            # Load from Supabase
            data = self._load_from_supabase(collection)
            
            # Cache the result
            self.cache[cache_key] = CacheEntry(
                data=data,
                timestamp=time.time(),
                ttl=self.cache_ttl_hours * 3600
            )
            
            result[collection] = data
        
        return result
    
    def get_context_sections(self, question: str, k: int = 6) -> List[Tuple[str, Dict]]:
        """
        Get relevant context sections for a question.
        
        Args:
            question: The question to find context for
            k: Maximum number of sections to return
            
        Returns:
            List of (source_tag, record_dict) tuples
        """
        constants = self.load_constants()
        relevant_sections = []
        
        # Simple keyword-based retrieval (can be enhanced with embeddings later)
        question_lower = question.lower()
        
        for collection_name, records in constants.items():
            for record in records:
                # Simple relevance scoring based on keyword matching
                relevance_score = 0
                
                # Check title/name fields
                for field in ['title', 'name', 'description', 'content']:
                    if field in record:
                        field_value = str(record[field]).lower()
                        if any(word in field_value for word in question_lower.split()):
                            relevance_score += 2
                
                # Check tags/categories if available
                if 'tags' in record:
                    tags = [str(tag).lower() for tag in record.get('tags', [])]
                    if any(word in tags for word in question_lower.split()):
                        relevance_score += 1
                
                if relevance_score > 0:
                    source_tag = f"{collection_name}:{record.get('_id', 'unknown')}"
                    relevant_sections.append((source_tag, record, relevance_score))
        
        # Sort by relevance and return top k
        relevant_sections.sort(key=lambda x: x[2], reverse=True)
        return [(tag, record) for tag, record, _ in relevant_sections[:k]]
    
    def build_prompt_context(self, question: str, k: int = 6) -> str:
        """
        Build prompt-ready context text from relevant sections.
        
        Args:
            question: The question to build context for
            k: Maximum number of sections to include
            
        Returns:
            Formatted context string for prompt building
        """
        sections = self.get_context_sections(question, k)
        
        if not sections:
            return "No relevant context found."
        
        context_parts = []
        for source_tag, record in sections:
            # Format each record as readable text
            record_text = f"[{source_tag}]\n"
            
            # Add key fields
            for field in ['title', 'name', 'description', 'content']:
                if field in record:
                    record_text += f"{field.title()}: {record[field]}\n"
            
            # Add any additional relevant fields
            for key, value in record.items():
                if key not in ['_id', 'title', 'name', 'description', 'content']:
                    record_text += f"{key.title()}: {value}\n"
            
            context_parts.append(record_text.strip())
        
        return "\n\n".join(context_parts)


# Global instance
_rag_manager = None


def get_rag_manager() -> RAGDataManager:
    """Get the global RAG data manager instance."""
    global _rag_manager
    if _rag_manager is None:
        cache_ttl = getattr(app_config, 'rag_cache_ttl_hours', 24)
        _rag_manager = RAGDataManager(cache_ttl_hours=cache_ttl)
    return _rag_manager


def load_constants(force_refresh: bool = False) -> Dict[str, List[Dict]]:
    """Load constant data from cache or Supabase."""
    return get_rag_manager().load_constants(force_refresh)


def get_context_sections(question: str, k: int = 6) -> List[Tuple[str, Dict]]:
    """Get relevant context sections for a question."""
    return get_rag_manager().get_context_sections(question, k)


def build_prompt_context(question: str, k: int = 6) -> str:
    """Build prompt-ready context text."""
    return get_rag_manager().build_prompt_context(question, k)
