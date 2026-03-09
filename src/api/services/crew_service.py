"""
Crew service for handling crew-related business logic using PostgreSQL.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..config import settings
from config.settings import app_config


class CrewService:
    """Service for managing crew operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self._cache = {}
        self._cache_ttl = settings.cache_ttl_seconds
    
    async def get_single_crew_by_category(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Get a single active crew member by category ID."""
        try:
            query = text(f"""
                SELECT id, name, email, phone, category_id, active, property_id 
                FROM {app_config.cleaning_crews_collection} 
                WHERE active = True AND category_id = :cat_id 
                LIMIT 1
            """)
            result = await self.session.execute(query, {"cat_id": category_id})
            row = result.fetchone()
            
            if row:
                crew = dict(row._mapping)
                # Enrich with category
                cat_query = text(f"SELECT id, name, parent_id FROM {app_config.categories_collection} WHERE id = :id")
                cat_result = await self.session.execute(cat_query, {"id": crew["category_id"]})
                cat_row = cat_result.fetchone()
                if cat_row:
                    crew["category"] = dict(cat_row._mapping)
                return crew
            return None
        except Exception as e:
            # Handle error
            return None

    async def get_active_crews(self, property_id: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            query_str = f"SELECT * FROM {app_config.cleaning_crews_collection} WHERE active = True"
            params = {}
            if property_id:
                query_str += " AND property_id = :pid"
                params["pid"] = property_id
            
            result = await self.session.execute(text(query_str), params)
            rows = result.fetchall()
            crews = [dict(row._mapping) for row in rows]
            
            # Enrich with categories
            for crew in crews:
                if crew.get("category_id"):
                    cat_query = text(f"SELECT * FROM {app_config.categories_collection} WHERE id = :id")
                    cat_res = await self.session.execute(cat_query, {"id": crew["category_id"]})
                    cat_row = cat_res.fetchone()
                    if cat_row:
                        crew["category"] = dict(cat_row._mapping)
            
            return crews
        except Exception:
            return []

    async def update_crew(self, crew_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        try:
            updates["updated_at"] = datetime.utcnow()
            set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
            query = text(f"UPDATE {app_config.cleaning_crews_collection} SET {set_clause} WHERE id = :id RETURNING *")
            params = {**updates, "id": crew_id}
            result = await self.session.execute(query, params)
            row = result.fetchone()
            if not row:
                raise Exception("Crew not found")
            return dict(row._mapping)
        except Exception as e:
            raise e
            
    async def create_crew(self, crew_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            columns = ", ".join(crew_data.keys())
            placeholders = ", ".join([f":{k}" for k in crew_data.keys()])
            query = text(f"INSERT INTO {app_config.cleaning_crews_collection} ({columns}) VALUES ({placeholders}) RETURNING *")
            result = await self.session.execute(query, crew_data)
            row = result.fetchone()
            return dict(row._mapping)
        except Exception as e:
            raise e

    async def delete_crew(self, crew_id: int) -> bool:
        try:
            query = text(f"DELETE FROM {app_config.cleaning_crews_collection} WHERE id = :id")
            await self.session.execute(query, {"id": crew_id})
            return True
        except Exception:
            return False
