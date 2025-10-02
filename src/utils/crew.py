# utils/crew.py
import itertools
from typing import Optional
from .logger import get_logger

logger = get_logger("crew_assigner")

def pick_crew_round_robin(supabase_client, property_id: Optional[str] = None) -> Optional[dict]:
    crews = supabase_client.list_active_crews(property_id)
    if not crews:
        # If no crews for specific property, try getting all active crews
        crews = supabase_client.list_active_crews()
        if not crews:
            logger.warning("No active crews available")
            return None
    
    # Simple approach: pick crew with least assigned pending tasks
    # Fallback: first crew
    try:
        counts = []
        for c in crews:
            q = supabase_client.client.table("cleaning_tasks").select("id", count="exact").eq("crew_id", c["id"]).in_("status", ["pending","confirmed"]).execute()
            counts.append((c, q.count if q and hasattr(q, "count") else 0))
        counts.sort(key=lambda x: x[1])
        selected = counts[0][0]
        return selected
    except Exception as e:
        logger.warning("Round-robin fallback, error fetching counts: %s", e)
        return crews[0]
