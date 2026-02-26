from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime

class ServiceCategoryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.table_name = "service_category"

    async def create_category(self, data: Dict[str, Any]) -> Dict[str, Any]:
        columns = ", ".join(data.keys())
        placeholders = ", ".join([f":{k}" for k in data.keys()])
        query = text(f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders}) RETURNING *")
        
        result = await self.session.execute(query, data)
        row = result.fetchone()
        
        if row:
            return dict(row._mapping)
        raise RuntimeError("Failed to create service category")

    async def get_category(self, category_id: int) -> Optional[Dict[str, Any]]:
        query = text(f"SELECT * FROM {self.table_name} WHERE id = :id")
        result = await self.session.execute(query, {"id": int(category_id)})
        row = result.fetchone()
        if row:
            return dict(row._mapping)
        return None

    async def list_categories(self) -> List[Dict[str, Any]]:
        query = text(f"SELECT * FROM {self.table_name}")
        result = await self.session.execute(query)
        rows = result.fetchall()
        return [dict(row._mapping) for row in rows]

    async def update_category(self, category_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        clean_data = {k: v for k, v in data.items() if v is not None}
        if not clean_data:
            return await self.get_category(category_id)

        clean_data["updated_at"] = datetime.utcnow()
        clean_data["id"] = int(category_id)
        
        set_clause = ", ".join([f"{k} = :{k}" for k in clean_data.keys() if k != "id"])
        query = text(f"UPDATE {self.table_name} SET {set_clause} WHERE id = :id RETURNING *")
        
        result = await self.session.execute(query, clean_data)
        row = result.fetchone()
        
        if row:
            return dict(row._mapping)
        raise RuntimeError("Failed to update service category")

    async def update_status(self, category_id: int, status: bool) -> Dict[str, Any]:
        return await self.update_category(int(category_id), {"status": status})
