"""
Service for managing Activity Rules using PostgreSQL.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
import structlog
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, insert, update, desc

from ..models import (
    CreateActivityRuleRequest,
    UpdateActivityRuleRequest,
    ActivityRuleResponse,
    ActivityRuleLog
)

class ActivityRuleService:
    """Service for Activity Rule operations."""

    def __init__(self, session: AsyncSession, logger=None):
        self.session = session
        self.logger = logger or structlog.get_logger()
        self.table_name = "activity_rule"
        self.log_table_name = "activity_rule_log"

    async def create_rule(self, request: CreateActivityRuleRequest) -> ActivityRuleResponse:
        """Create a new activity rule."""
        try:
            payload = request.model_dump(exclude_unset=True)
            
            # Using raw SQL for simplicity in migration
            columns = ", ".join(payload.keys())
            placeholders = ", ".join([f":{k}" for k in payload.keys()])
            query = text(f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders}) RETURNING *")
            
            result = await self.session.execute(query, payload)
            row = result.fetchone()
            
            if not row:
                raise Exception("Failed to create activity rule")
                
            return ActivityRuleResponse(**dict(row._mapping))
            
        except Exception as e:
            self.logger.error("Error creating activity rule", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))

    async def log_activity(self, rule_name: str, outcome: str) -> None:
        """Log activity rule execution."""
        try:
            payload = {
                "rule_name": rule_name,
                "outcome": outcome
            }
            query = text(f"INSERT INTO {self.log_table_name} (rule_name, outcome) VALUES (:rule_name, :outcome)")
            await self.session.execute(query, payload)
            # Commit is handled by the session dependency wrapper or explicit commit
            
        except Exception as e:
            self.logger.error("Error logging activity rule execution", error=str(e))

    async def get_logs(self) -> List[ActivityRuleLog]:
        """Get all activity rule logs."""
        try:
            query = text(f"SELECT * FROM {self.log_table_name} ORDER BY created_at DESC")
            result = await self.session.execute(query)
            rows = result.fetchall()
            return [ActivityRuleLog(**dict(row._mapping)) for row in rows]
        except Exception as e:
            self.logger.error("Error fetching activity rule logs", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))

    async def get_rules(self) -> List[ActivityRuleResponse]:
        """Get all activity rules."""
        try:
            query = text(f"SELECT * FROM {self.table_name} ORDER BY created_at DESC")
            result = await self.session.execute(query)
            rows = result.fetchall()
            return [ActivityRuleResponse(**dict(row._mapping)) for row in rows]
        except Exception as e:
            self.logger.error("Error fetching activity rules", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))

    async def get_rule_by_slug(self, slug_name: str) -> Optional[ActivityRuleResponse]:
        """Get a single activity rule by slug name."""
        try:
            query = text(f"SELECT * FROM {self.table_name} WHERE slug_name = :slug_name")
            result = await self.session.execute(query, {"slug_name": slug_name})
            row = result.fetchone()
            if not row:
                return None
            return ActivityRuleResponse(**dict(row._mapping))
        except Exception as e:
            self.logger.error(f"Error fetching activity rule by slug {slug_name}", error=str(e))
            return None

    async def get_rule(self, rule_id: int) -> ActivityRuleResponse:
        """Get a single activity rule by ID."""
        try:
            query = text(f"SELECT * FROM {self.table_name} WHERE id = :rule_id")
            result = await self.session.execute(query, {"rule_id": rule_id})
            row = result.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Activity rule {rule_id} not found")
            return ActivityRuleResponse(**dict(row._mapping))
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error fetching activity rule {rule_id}", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))

    async def update_rule(self, rule_id: int, request: UpdateActivityRuleRequest) -> ActivityRuleResponse:
        """Update an activity rule."""
        try:
            payload = request.model_dump(exclude_unset=True)
            if not payload:
                return await self.get_rule(rule_id)
                
            payload["updated_at"] = datetime.utcnow()
            payload["rule_id"] = rule_id
            
            set_clause = ", ".join([f"{k} = :{k}" for k in payload.keys() if k != "rule_id"])
            query = text(f"UPDATE {self.table_name} SET {set_clause} WHERE id = :rule_id RETURNING *")
            
            result = await self.session.execute(query, payload)
            row = result.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail=f"Activity rule {rule_id} not found")
                
            return ActivityRuleResponse(**dict(row._mapping))
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error updating activity rule {rule_id}", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))

    async def toggle_status(self, rule_id: int, status: bool) -> ActivityRuleResponse:
        """Enable or disable an activity rule."""
        try:
            payload = {
                "status": status,
                "updated_at": datetime.utcnow(),
                "rule_id": rule_id
            }
            query = text(f"UPDATE {self.table_name} SET status = :status, updated_at = :updated_at WHERE id = :rule_id RETURNING *")
            
            result = await self.session.execute(query, payload)
            row = result.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail=f"Activity rule {rule_id} not found")
                
            return ActivityRuleResponse(**dict(row._mapping))
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Error toggling status for rule {rule_id}", error=str(e))
            raise HTTPException(status_code=500, detail=str(e))
