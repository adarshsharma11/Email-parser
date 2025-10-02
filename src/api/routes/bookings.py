"""
Booking API endpoints.
"""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from ..models import BookingStatsResponse, ErrorResponse, Platform, BookingSummary, PaginatedBookingResponse
from ..dependencies import get_booking_service
from ..services.booking_service import BookingService


router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get(
    "",
    response_model=PaginatedBookingResponse,
    summary="Get paginated bookings",
    description="Retrieve paginated booking records with optional platform filtering",
    responses={
        200: {"description": "Bookings retrieved successfully"},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def get_bookings(
    platform: Optional[Platform] = Query(None, description="Filter by specific platform"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    limit: int = Query(10, ge=1, le=100, description="Number of bookings per page"),
    booking_service: BookingService = Depends(get_booking_service)
):
    """
    Get paginated booking records from the database.
    
    Args:
        platform: Optional platform filter
        page: Page number (starts at 1)
        limit: Number of bookings per page (max 100)
        booking_service: Injected booking service
        
    Returns:
        Paginated list of bookings
        
    Raises:
        HTTPException: If service returns an error
    """
    try:
        bookings = booking_service.get_bookings_paginated(
            platform=platform.value if platform else None,
            page=page,
            limit=limit
        )
        
        return {
            "success": True,
            "message": f"Bookings retrieved for page {page}",
            "data": bookings
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


@router.get(
    "/stats",
    response_model=BookingStatsResponse,
    summary="Get detailed booking statistics",
    description="Get comprehensive booking statistics with caching",
    responses={
        200: {"description": "Statistics retrieved successfully"},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def get_booking_stats(
    booking_service: BookingService = Depends(get_booking_service)
) -> BookingStatsResponse:
    """
    Get detailed booking statistics with caching.
    
    Args:
        booking_service: Injected booking service
        
    Returns:
        Detailed booking statistics
    """
    try:
        stats_response = booking_service.get_booking_statistics()
        
        if not stats_response.success:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": stats_response.message,
                    "error_code": getattr(stats_response, 'error_code', 'UNKNOWN_ERROR'),
                    "details": getattr(stats_response, 'details', None)
                }
            )
        
        return stats_response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Internal server error",
                "error_code": "INTERNAL_ERROR",
                "details": {"error": str(e)}
            }
        )