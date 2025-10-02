"""
Crew service for handling crew-related business logic.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
import time

from ...supabase_sync.supabase_client import SupabaseClient
from ..models import APIResponse, ErrorResponse
from ..config import settings


class CrewService:
    """Service for managing crew operations."""
    
    def __init__(self):
        """Initialize crew service with Supabase client."""
        self.supabase_client = SupabaseClient()
        self._cache = {}
        self._cache_ttl = settings.cache_ttl_seconds
    
    def _get_cache_key(self, property_id: Optional[str] = None) -> str:
        """Generate cache key for crew list."""
        return f"crews_{property_id or 'all'}"
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache is still valid."""
        if cache_key not in self._cache:
            return False
        
        timestamp, _ = self._cache[cache_key]
        return (time.time() - timestamp) < self._cache_ttl
    
    def get_active_crews(self, property_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get active cleaning crews, optionally filtered by property.
        
        Args:
            property_id: Optional property ID to filter crews
            
        Returns:
            List of active crew members
        """
        cache_key = self._get_cache_key(property_id)
        
        # Check cache first
        if self._is_cache_valid(cache_key):
            _, crews = self._cache[cache_key]
            return crews
        
        # Fetch from Supabase
        crews = self.supabase_client.list_active_crews(property_id)
        
        # Cache the result
        self._cache[cache_key] = (time.time(), crews)
        
        return crews