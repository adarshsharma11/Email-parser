from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from config.settings import app_config


class CategoryService:
    """Service for managing hierarchical categories using PostgreSQL."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_category(
        self,
        name: str,
        parent_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a category."""
        if parent_id is not None:
            parent_query = text(f"SELECT id FROM {app_config.categories_collection} WHERE id = :pid")
            parent_result = await self.session.execute(parent_query, {"pid": parent_id})
            if not parent_result.fetchone():
                raise ValueError("PARENT_NOT_FOUND")

        payload = {
            "name": name,
            "parent_id": parent_id,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        columns = ", ".join(payload.keys())
        placeholders = ", ".join([f":{k}" for k in payload.keys()])
        query = text(f"INSERT INTO {app_config.categories_collection} ({columns}) VALUES ({placeholders}) RETURNING *")
        
        result = await self.session.execute(query, payload)
        row = result.fetchone()
        
        if not row:
            raise Exception("Failed to create category")
            
        data = dict(row._mapping)
        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "parent_id": data.get("parent_id"),
        }

    async def get_category(self, category_id: int) -> Optional[Dict[str, Any]]:
        query = text(f"SELECT * FROM {app_config.categories_collection} WHERE id = :id")
        result = await self.session.execute(query, {"id": int(category_id)})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def list_children(
        self,
        parent_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if parent_id is None:
            query = text(f"SELECT id, name, parent_id FROM {app_config.categories_collection} WHERE parent_id IS NULL")
            result = await self.session.execute(query)
        else:
            query = text(f"SELECT id, name, parent_id FROM {app_config.categories_collection} WHERE parent_id = :pid")
            result = await self.session.execute(query, {"pid": parent_id})
        
        rows = result.fetchall()
        return [dict(row._mapping) for row in rows]

    async def get_category_tree(self) -> List[Dict[str, Any]]:
        """Get the full category tree with associated crews."""
        # Fetch all categories
        query = text(f"SELECT * FROM {app_config.categories_collection}")
        result = await self.session.execute(query)
        all_cats = [dict(row._mapping) for row in result.fetchall()]
        
        # Fetch all crews
        crew_query = text(f"SELECT * FROM {app_config.cleaning_crews_collection}")
        crew_result = await self.session.execute(crew_query)
        all_crews = [dict(row._mapping) for row in crew_result.fetchall()]
        
        # Build map: category_id -> list of crews
        crews_by_cat = {}
        for crew in all_crews:
            cid = crew.get("category_id")
            if cid:
                if cid not in crews_by_cat:
                    crews_by_cat[cid] = []
                crews_by_cat[cid].append(crew)
        
        # Build map: parent_id -> list of children
        children_by_parent = {}
        roots = []
        for cat in all_cats:
            cat["crews"] = crews_by_cat.get(cat["id"], [])
            pid = cat.get("parent_id")
            if pid is None:
                roots.append(cat)
            else:
                if pid not in children_by_parent:
                    children_by_parent[pid] = []
                children_by_parent[pid].append(cat)
                
        def build_node(node):
            node["children"] = children_by_parent.get(node["id"], [])
            for child in node["children"]:
                build_node(child)
            return node
            
        return [build_node(root) for root in roots]
