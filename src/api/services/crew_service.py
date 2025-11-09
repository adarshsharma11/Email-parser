"""
Crew service for handling crew-related business logic.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
import time

from ...supabase_sync.supabase_client import SupabaseClient
from ..models import APIResponse, ErrorResponse
from ..config import settings
from config.settings import app_config


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
    
    def add_crew(self, crew_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add a new crew member to the system.
        
        Args:
            crew_data: Crew member data including name, email, phone, role, etc.
            
        Returns:
            Created crew member data
            
        Raises:
            Exception: If creation fails or duplicate email/phone found
        """
        # Ensure client is initialized
        if not self.supabase_client.initialized:
            if not self.supabase_client.initialize():
                raise Exception("Failed to initialize Supabase client")
        
        # Check for duplicate email or phone
        email = crew_data.get('email')
        phone = crew_data.get('phone')
        
        if email or phone:
            # Query for existing crew members with same email or phone
            query = self.supabase_client.client.table(app_config.cleaning_crews_collection).select('id', 'email', 'phone')
            
            if email and phone:
                query = query.or_(f'email.eq.{email},phone.eq.{phone}')
            elif email:
                query = query.eq('email', email)
            elif phone:
                query = query.eq('phone', phone)
            
            existing_result = query.execute()
            
            if existing_result.data:
                existing = existing_result.data[0]
                if email and existing.get('email') == email:
                    raise Exception(f"A crew member with email '{email}' already exists")
                if phone and existing.get('phone') == phone:
                    raise Exception(f"A crew member with phone '{phone}' already exists")
        
        # Add timestamp
        crew_data["created_at"] = datetime.utcnow().isoformat()
        crew_data["updated_at"] = datetime.utcnow().isoformat()
        
        # Filter out None values to avoid database schema conflicts
        filtered_data = {k: v for k, v in crew_data.items() if v is not None}
        
        # Create crew member in Supabase
        result = self.supabase_client.client.table(app_config.cleaning_crews_collection).insert(filtered_data).execute()
        
        # Clear cache since we added a new crew member
        self._cache.clear()
        
        if result.data:
            return result.data[0]
        else:
            raise Exception("Failed to create crew member")
    
    def delete_crew(self, crew_id: str) -> bool:
        """
        Delete a crew member from the system.
        
        Args:
            crew_id: ID of the crew member to delete
            
        Returns:
            True if deletion was successful
            
        Raises:
            Exception: If deletion fails
        """
        # Ensure client is initialized
        if not self.supabase_client.initialized:
            if not self.supabase_client.initialize():
                raise Exception("Failed to initialize Supabase client")
        
        # Delete crew member from Supabase
        result = self.supabase_client.client.table(app_config.cleaning_crews_collection).delete().eq("id", crew_id).execute()
        
        # Clear cache since we deleted a crew member
        self._cache.clear()
        
        if result.data:
            return True
        else:
            raise Exception(f"Crew member with ID {crew_id} not found")