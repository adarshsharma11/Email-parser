"""
Immutable data models for API responses and requests.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_serializer
from enum import Enum


class Platform(str, Enum):
    """Supported vacation rental platforms."""
    VRBO = "vrbo"
    AIRBNB = "airbnb"
    BOOKING = "booking"
    PLUMGUIDE = "plumguide"


class BookingStatus(str, Enum):
    """Booking status enumeration."""
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    PENDING = "pending"


class APIResponse(BaseModel):
    """Base API response model."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    success: bool = Field(..., description="Whether the request was successful")
    message: str = Field(..., description="Response message")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    
    @field_serializer('timestamp')
    def serialize_timestamp(self, timestamp: datetime) -> str:
        return timestamp.isoformat()


class BookingSummary(BaseModel):
    """Immutable booking summary model."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    total_bookings: int = Field(..., ge=0, description="Total number of bookings")
    by_platform: Dict[str, int] = Field(default_factory=dict, description="Bookings count by platform")
    last_updated: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    
    @field_serializer('last_updated')
    def serialize_last_updated(self, last_updated: datetime) -> str:
        return last_updated.isoformat()


class BookingStatsResponse(APIResponse):
    """Response model for booking statistics."""
    data: Optional[BookingSummary] = Field(None, description="Booking statistics data")


class ErrorResponse(APIResponse):
    """Error response model."""
    error_code: Optional[str] = Field(None, description="Error code for debugging")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")


class PaginatedBookingResponse(APIResponse):
    """Response model for paginated bookings."""
    data: Dict[str, Any] = Field(..., description="Paginated booking data including bookings array and pagination metadata")


class HealthResponse(BaseModel):
    """Health check response model."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Health check timestamp")
    version: str = Field(..., description="API version")
    dependencies: Dict[str, str] = Field(default_factory=dict, description="Dependency statuses")
    
    @field_serializer('timestamp')
    def serialize_timestamp(self, timestamp: datetime) -> str:
        return timestamp.isoformat()


class CrewResponse(APIResponse):
    """Response model for crew list."""
    data: List[Dict[str, Any]] = Field(..., description="List of active crew members")