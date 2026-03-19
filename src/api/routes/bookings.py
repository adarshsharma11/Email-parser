"""
Booking API endpoints.
"""
from typing import Optional, Union
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from ..models import (
    BookingStatsResponse, ErrorResponse, Platform, BookingSummary, 
    PaginatedBookingResponse, CreateBookingRequest, CreateBookingResponse,
    SendWelcomeEmailRequest, APIResponse
)
from ..dependencies import get_booking_service
from ..services.booking_service import BookingService


router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post(
    "",
    response_model=Union[CreateBookingResponse, None],
    summary="Create a new booking",
    description="Create a new booking with optional services. Use stream=true for real-time progress updates.",
    responses={
        200: {"description": "Booking created successfully"},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def create_booking(
    request: CreateBookingRequest,
    stream: bool = Query(False, description="Stream progress updates via NDJSON"),
    booking_service: BookingService = Depends(get_booking_service)
):
    """
    Create a new booking.
    
    Args:
        request: Booking creation request
        stream: Whether to stream progress updates (default: False)
        booking_service: Injected booking service
        
    Returns:
        Created booking response or StreamingResponse
    """
    # Force boolean conversion if string "true" is passed
    if str(stream).lower() == 'true':
        stream = True
        
    if stream:
        return StreamingResponse(
            booking_service.create_booking_process(request),
            media_type="application/x-ndjson"
        )
        
    response = await booking_service.create_booking(request)
    if not response.success:
        raise HTTPException(
            status_code=500,
            detail={
                "message": response.message,
                "error_code": "CREATION_FAILED",
                "details": {}
            }
        )
    return response


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
    platform: Optional[str] = Query(None, description="Filter by specific platform"),
    search: Optional[str] = Query(None, description="Search by guest name or reservation ID"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    limit: int = Query(10, ge=1, le=10000, description="Number of bookings per page"),
    booking_service: BookingService = Depends(get_booking_service)
):
    """
    Get paginated booking records from the database.
    
    Args:
        platform: Optional platform filter
        search: Optional search term
        page: Page number (starts at 1)
        limit: Number of bookings per page (max 10000)
        booking_service: Injected booking service
        
    Returns:
        Paginated list of bookings
        
    Raises:
        HTTPException: If service returns an error
    """
    try:
        platform_value = None
        if platform:
            try:
                platform_value = Platform(platform.lower()).value
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid platform: {platform}. Allowed values: {[p.value for p in Platform]}"
                )

        bookings = await booking_service.get_bookings_paginated(
            platform=platform_value,
            search=search,
            page=page,
            limit=limit
        )
        
        return {
            "success": True,
            "message": f"Bookings retrieved for page {page}",
            "data": bookings
        }
        
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
        stats_response = await booking_service.get_booking_statistics()
        
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
        
class UpdateGuestPhoneRequest(BaseModel):
    guest_phone: str = Field(..., min_length=1, description="Updated guest phone number")


@router.post(
    "/send-welcome",
    response_model=APIResponse,
    summary="Send manual welcome email",
    description="Update guest email and send a welcome email via SendGrid",
    responses={
        200: {"description": "Email sent successfully"},
        404: {"description": "Booking not found"},
        500: {"description": "Internal server error"}
    }
)
async def send_manual_welcome_email(
    request: SendWelcomeEmailRequest,
    booking_service: BookingService = Depends(get_booking_service)
):
    """
    Send a manual welcome email to a guest and update their record.
    """
    response = await booking_service.send_welcome_email(request)
    if not response.success:
        if "not found" in response.message:
            raise HTTPException(status_code=404, detail=response.message)
        raise HTTPException(status_code=500, detail=response.message)
    return response


@router.patch(
    "/{reservation_id}",
    summary="Update guest phone number for a booking",
    responses={
        200: {"description": "Guest phone updated successfully"},
        404: {"description": "Booking not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    },
)
async def update_booking_guest_phone(
    reservation_id: str,
    payload: UpdateGuestPhoneRequest,
    booking_service: BookingService = Depends(get_booking_service),
):
    """
    Update the `guest_phone` field for a booking identified by reservation id.
    """
    try:
        ok = await booking_service.update_guest_phone(reservation_id, payload.guest_phone)
        if not ok:
            raise HTTPException(status_code=404, detail={
                "message": "Booking not found or update failed",
                "error_code": "UPDATE_FAILED",
                "details": {"reservation_id": reservation_id}
            })
        return {"success": True, "message": "Guest phone updated", "data": {"reservation_id": reservation_id, "guest_phone": payload.guest_phone}}
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
        
@router.get(
    "/propertyData/{platform}",
    summary="Get booking reservation-property map for a specific platform",
    description="Returns a dictionary mapping reservation_id to property_name for the given platform",
    responses={
        200: {"description": "Reservation map retrieved successfully"},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def get_booking_reservation_map(
    platform: str,
    booking_service: BookingService = Depends(get_booking_service)
):
    """
    Example: /api/v1/bookings/propertyData/airbnb
    """
    try:
        # Fetch bookings filtered by platform
        bookings_response = await booking_service.get_bookings_paginated(
            page=1, limit=1000, platform=platform, search=None
        )

        if not bookings_response or "bookings" not in bookings_response:
            raise HTTPException(status_code=404, detail=f"No bookings found for platform '{platform}'")

        # Filter data for the given platform (in case service returns all)
        bookings = [
            b for b in bookings_response["bookings"]
            if b.get("platform") == platform
        ]

        reservation_map = {
            b["reservation_id"]: b["property_name"]
            for b in bookings
            if b.get("reservation_id") and b.get("property_name")
        }

        return {
            "success": True,
            "message": f"Reservation map for '{platform}' retrieved successfully",
            "data": reservation_map
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
    "/{reservation_id}",
    response_model=APIResponse,
    summary="Delete a booking",
    description="Delete a booking along with related services and tasks",
    responses={
        200: {"description": "Booking deleted successfully"},
        404: {"description": "Booking not found"},
        500: {"description": "Internal server error"},
    },
)
async def delete_booking(
    reservation_id: str,
    booking_service: BookingService = Depends(get_booking_service),
):
    """
    Delete booking by reservation_id
    """
    response = await booking_service.delete_booking(reservation_id)

    if not response.get("success"):
        raise HTTPException(status_code=404, detail=response.get("message"))

    return response