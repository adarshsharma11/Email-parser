from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from ...supabase_sync.supabase_client import SupabaseClient
from config.settings import app_config


class CategoryService:
    """Service for managing hierarchical categories."""

    def __init__(self):
        self.supabase = SupabaseClient()

    def _ensure(self) -> None:
        if not self.supabase.initialized:
            if not self.supabase.initialize():
                raise RuntimeError("Supabase initialization failed")

    def create_category(
        self,
        name: str,
        parent_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create a category. If parent_id is provided, ensure it exists.
        Returns inserted category.
        """
        self._ensure()

        if parent_id is not None:
            parent = (
                self.supabase.client
                .table(app_config.categories_collection)
                .select("id")
                .eq("id", parent_id)
                .limit(1)
                .execute()
            )
            if not parent.data:
                raise ValueError("PARENT_NOT_FOUND")

        payload = {
            "name": name,
            "parent_id": parent_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        result = (
            self.supabase.client
            .table(app_config.categories_collection)
            .insert(payload)
            .execute()
        )

        data = result.data[0] if result.data else payload
        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "parent_id": data.get("parent_id"),
        }

    def get_category(self, category_id: str) -> Optional[Dict[str, Any]]:
        self._ensure()
        result = (
            self.supabase.client
            .table(app_config.categories_collection)
            .select("*")
            .eq("id", category_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def list_children(
        self,
        parent_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        List children under a given parent_id; if None, list root categories.
        """
        self._ensure()
        query = (
            self.supabase.client
            .table(app_config.categories_collection)
            .select("id,name,parent_id")
        )
        if parent_id is None:
            query = query.is_("parent_id", None)
        else:
            query = query.eq("parent_id", parent_id)
        result = query.execute()
        return result.data or []

    def get_category_tree(self) -> List[Dict[str, Any]]:
        """
        Get the full category tree with associated crews.
        """
        self._ensure()
        # Fetch all categories
        result = (
            self.supabase.client
            .table(app_config.categories_collection)
            .select("id,name,parent_id")
            .execute()
        )
        categories = result.data or []

        # Fetch all crews
        crews_result = (
            self.supabase.client
            .table(app_config.cleaning_crews_collection)
            .select("*")
            .execute()
        )
        crews = crews_result.data or []

        # Group crews by category
        crews_by_category = {}
        for crew in crews:
            cat_id = crew.get('category_id')
            if cat_id is not None:
                if cat_id not in crews_by_category:
                    crews_by_category[cat_id] = []
                crews_by_category[cat_id].append(crew)

        # Build tree
        category_map = {c['id']: {**c, 'children': [], 'crews': []} for c in categories}
        roots = []

        for cat in categories:
            cat_id = cat['id']
            parent_id = cat['parent_id']
            node = category_map[cat_id]

            # Attach crews
            node['crews'] = crews_by_category.get(cat_id, [])

            if parent_id is None:
                roots.append(node)
            elif parent_id in category_map:
                category_map[parent_id]['children'].append(node)

        return roots
