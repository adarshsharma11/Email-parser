from fastapi import APIRouter, HTTPException,Query
from pydantic import BaseModel
from ...supabase_sync.supabase_client import SupabaseClient
from ..services.property_service import PropertyService
import logging

router = APIRouter(tags=["iCal"])

# Initialize logger and Supabase client
logger = logging.getLogger(__name__)
supabase_client = SupabaseClient()
property_service = PropertyService()


class PropertyCreate(BaseModel):
    name: str
    vrbo_id: str | None = None
    airbnb_id: str | None = None
    booking_id: str | None = None
    status: str | None = None

@router.post("/property")
async def create_property(property_data: PropertyCreate):
    """
    Save property info and generate its iCal feed URL.
    """
    result = property_service.create_property(
        name=property_data.name,
        vrbo_id=property_data.vrbo_id,
        airbnb_id=property_data.airbnb_id,
        booking_id=property_data.booking_id,
        status=property_data.status or "active"
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])

    return result

@router.get("/property")
async def get_properties(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100)
):
    """Fetch all properties with pagination (service-based)."""
    result = property_service.get_properties(page, limit)

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])

    return result

@router.get("/property/{property_id}.ics")
async def generate_ical_feed(property_id: str):
    """
    Generate iCal file for a given property.
    """
    prop = property_service.get_property_by_id(property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    ical_content = property_service.generate_ical_feed(prop)
    return ical_content
