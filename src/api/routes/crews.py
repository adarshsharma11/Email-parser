"""
Crew API endpoints.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from ..models import CrewResponse, ErrorResponse, CreateCrewRequest, CreateCrewResponse, DeleteCrewResponse
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


@router.post(
    "",
    response_model=CreateCrewResponse,
    summary="Create a new crew member",
    description="Add a new crew member to the system",
    responses={
        201: {"description": "Crew member created successfully"},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def create_crew(
    crew_data: CreateCrewRequest,
    crew_service: CrewService = Depends(get_crew_service)
):
    """
    Create a new crew member.
    
    Args:
        crew_data: Crew member data to create
        crew_service: Injected crew service
        
    Returns:
        Created crew member details
        
    Raises:
        HTTPException: If service returns an error
    """
    try:
        crew = crew_service.add_crew(crew_data.model_dump())
        
        return {
            "success": True,
            "message": "Crew member created successfully",
            "data": crew
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


@router.delete(
    "/{crew_id}",
    response_model=DeleteCrewResponse,
    summary="Delete a crew member",
    description="Remove a crew member from the system",
    responses={
        200: {"description": "Crew member deleted successfully"},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def delete_crew(
    crew_id: str = Path(..., description="ID of the crew member to delete"),
    crew_service: CrewService = Depends(get_crew_service)
):
    """
    Delete a crew member.
    
    Args:
        crew_id: ID of the crew member to delete
        crew_service: Injected crew service
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If service returns an error
    """
    try:
        success = crew_service.delete_crew(crew_id)
        
        return {
            "success": True,
            "message": "Crew member deleted successfully",
            "data": {"deleted": success}
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