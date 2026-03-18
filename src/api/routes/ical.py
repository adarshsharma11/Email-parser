from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from ..services.property_service import PropertyService
from ..dependencies import get_property_service
import logging

router = APIRouter(tags=["iCal"])
public_router = APIRouter(tags=["iCal"])

# Initialize logger
logger = logging.getLogger(__name__)


class PropertyCreate(BaseModel):
    name: str
    address: str | None = None
    vrbo_id: str | None = None
    airbnb_id: str | None = None
    booking_id: str | None = None
    status: str | None = None
    base_price: float = 0.0
    bedrooms: int = 0
    owner_id: int | None = None

@router.post("/property")
async def create_property(property_data: PropertyCreate, service: PropertyService = Depends(get_property_service)):
    """
    Save property info and generate its iCal feed URL.
    """
    result = await service.create_property(
        name=property_data.name,
        address=property_data.address,
        vrbo_id=property_data.vrbo_id,
        airbnb_id=property_data.airbnb_id,
        booking_id=property_data.booking_id,
        status=property_data.status or "active",
        base_price=property_data.base_price,
        bedrooms=property_data.bedrooms,
        owner_id=property_data.owner_id
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])

    return result

@router.get("/property")
async def get_properties(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    service: PropertyService = Depends(get_property_service)
):
    """Fetch all properties with pagination (service-based)."""
    result = await service.get_properties(page, limit)

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])

    return result

@router.delete("/property/{property_id}")
async def delete_property(property_id: int, service: PropertyService = Depends(get_property_service)):
    """Delete a property by ID (service-based)."""
    result = await service.delete_property(property_id)

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])
    return result
   

async def generate_ical_feed(property_id: int, service: PropertyService = Depends(get_property_service)):
    """
    Generate iCal file for a given property.
    """
    prop = await service.get_property(property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    ical_content = await service.generate_ical_feed(prop)
    return Response(
        content=ical_content,
        media_type="text/calendar",
        headers={"Content-Disposition": f"attachment; filename=\"{property_id}.ics\""}
    )

# Expose ICS under versioned router and public router
# Original .ics routes
router.add_api_route("/property/{property_id}.ics", generate_ical_feed, methods=["GET"])
public_router.add_api_route("/property/{property_id}.ics", generate_ical_feed, methods=["GET"])

# New routes without .ics extension to avoid proxy interception of static file extensions
router.add_api_route("/property/{property_id}/ical", generate_ical_feed, methods=["GET"])
public_router.add_api_route("/property/{property_id}/ical", generate_ical_feed, methods=["GET"])
