"""
Crew API endpoints.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from ..models import CrewResponse, ErrorResponse
from ..dependencies import get_crew_service
from ..services.crew_service import CrewService


router = APIRouter(prefix="/crews", tags=["crews"])


@router.get(
    "",
    response_model=CrewResponse,
    summary="Get active crew members",
    description="Retrieve list of active cleaning crews, optionally filtered by property",
    responses={
        200: {"description": "Crews retrieved successfully"},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def get_crews(
    property_id: Optional[str] = Query(None, description="Filter by specific property ID"),
    crew_service: CrewService = Depends(get_crew_service)
):
    """
    Get active crew members from the database.
    
    Args:
        property_id: Optional property ID filter
        crew_service: Injected crew service
        
    Returns:
        List of active crew members
        
    Raises:
        HTTPException: If service returns an error
    """
    try:
        crews = crew_service.get_active_crews(property_id)
        
        return {
            "success": True,
            "message": f"Retrieved {len(crews)} active crew members",
            "data": crews
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Internal server error",
                "error_code": "INTERNAL_ERROR",
                "details": {"error": str(e)}
            }
        )