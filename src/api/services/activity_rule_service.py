"""
Service for managing Activity Rules.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
import structlog
from fastapi import HTTPException

from ..models import (
    CreateActivityRuleRequest,
    UpdateActivityRuleRequest,
    ActivityRuleResponse
)
from src.supabase_sync.supabase_client import SupabaseClient


class ActivityRuleService:
    """Service for Activity Rule operations."""

    def __init__(self, supabase_client: SupabaseClient, logger=None):
        self.supabase = supabase_client
        self.logger = logger or structlog.get_logger()
        self.table_name = "activity_rule"

    def _ensure_initialized(self):
        """Ensure Supabase client is initialized."""
        if not self.supabase.initialized:
            if not self.supabase.initialize():
                raise HTTPException(status_code=500, detail="Database connection failed")

    def create_rule(self, request: CreateActivityRuleRequest) -> ActivityRuleResponse:
        """Create a new activity rule."""
        self._ensure_initialized()
        
        try:
            payload = request.model_dump(exclude_unset=True)
            # created_at is default now() in DB
            
            res = (
                self.supabase.client
                .table(self.table_name)
                .insert(payload)
                .execute()
            )
            
            data = getattr(res, "data", [])
            if not data:
                raise Exception("Failed to create activity rule")
                
            return ActivityRuleResponse(**data[0])
            
        except Exception as e:
            self.logger.error("Error creating activity rule", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))

    def get_rules(self) -> List[ActivityRuleResponse]:
        """Get all activity rules."""
        self._ensure_initialized()
        
        try:
            res = (
                self.supabase.client
                .table(self.table_name)
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            
            data = getattr(res, "data", [])
            return [ActivityRuleResponse(**item) for item in data]
            
        except Exception as e:
            self.logger.error("Error fetching activity rules", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))

    def get_rule_by_slug(self, slug_name: str) -> Optional[ActivityRuleResponse]:
        """Get a single activity rule by slug name."""
        self._ensure_initialized()
        
        try:
            res = (
                self.supabase.client
                .table(self.table_name)
                .select("*")
                .eq("slug_name", slug_name)
                .execute()
            )
            
            data = getattr(res, "data", [])
            if not data:
                return None
                
            return ActivityRuleResponse(**data[0])
            
        except Exception as e:
            self.logger.error(f"Error fetching activity rule by slug {slug_name}", error=str(e))
            # Don't raise, just return None to allow safe checks
            return None

    def get_rule(self, rule_id: int) -> ActivityRuleResponse:
        """Get a single activity rule by ID."""
        self._ensure_initialized()
        
        try:
            res = (
                self.supabase.client
                .table(self.table_name)
                .select("*")
                .eq("id", rule_id)
                .execute()
            )
            
            data = getattr(res, "data", [])
            if not data:
                raise HTTPException(status_code=404, detail=f"Activity rule {rule_id} not found")
                
            return ActivityRuleResponse(**data[0])
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error fetching activity rule {rule_id}", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))

    def update_rule(self, rule_id: int, request: UpdateActivityRuleRequest) -> ActivityRuleResponse:
        """Update an activity rule."""
        self._ensure_initialized()
        
        try:
            payload = request.model_dump(exclude_unset=True)
            if not payload:
                # If nothing to update, return existing
                return self.get_rule(rule_id)
                
            payload["updated_at"] = datetime.utcnow().isoformat()
            
            res = (
                self.supabase.client
                .table(self.table_name)
                .update(payload)
                .eq("id", rule_id)
                .execute()
            )
            
            data = getattr(res, "data", [])
            if not data:
                raise HTTPException(status_code=404, detail=f"Activity rule {rule_id} not found or update failed")
                
            return ActivityRuleResponse(**data[0])
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error updating activity rule {rule_id}", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))

    def toggle_status(self, rule_id: int, status: bool) -> ActivityRuleResponse:
        """Enable or disable an activity rule."""
        self._ensure_initialized()
        
        try:
            payload = {
                "status": status,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            res = (
                self.supabase.client
                .table(self.table_name)
                .update(payload)
                .eq("id", rule_id)
                .execute()
            )
            
            data = getattr(res, "data", [])
            if not data:
                raise HTTPException(status_code=404, detail=f"Activity rule {rule_id} not found")
                
            return ActivityRuleResponse(**data[0])
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error toggling status for rule {rule_id}", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))
