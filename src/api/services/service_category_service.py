from typing import List, Dict, Any, Optional
from ...supabase_sync.supabase_client import SupabaseClient

class ServiceCategoryService:
    def __init__(self):
        self.supabase = SupabaseClient()
        self.table_name = "service_category"

    def _ensure_initialized(self):
        if not self.supabase.initialized:
            if not self.supabase.initialize():
                raise RuntimeError("Supabase initialization failed")

    def create_category(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        
        result = (
            self.supabase.client
            .table(self.table_name)
            .insert(data)
            .execute()
        )
        
        if result.data:
            return result.data[0]
        raise RuntimeError("Failed to create service category")

    def get_category(self, category_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_initialized()
        
        result = (
            self.supabase.client
            .table(self.table_name)
            .select("*")
            .eq("id", category_id)
            .execute()
        )
        
        if result.data:
            return result.data[0]
        return None

    def list_categories(self) -> List[Dict[str, Any]]:
        self._ensure_initialized()
        
        result = (
            self.supabase.client
            .table(self.table_name)
            .select("*")
            .execute()
        )
        
        return result.data or []

    def update_category(self, category_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        
        # Remove None values
        clean_data = {k: v for k, v in data.items() if v is not None}
        
        if not clean_data:
            return self.get_category(category_id)

        result = (
            self.supabase.client
            .table(self.table_name)
            .update(clean_data)
            .eq("id", category_id)
            .execute()
        )
        
        if result.data:
            return result.data[0]
        raise RuntimeError("Failed to update service category")

    def update_status(self, category_id: str, status: bool) -> Dict[str, Any]:
        return self.update_category(category_id, {"status": status})
