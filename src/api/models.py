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


class CreateCrewRequest(BaseModel):
    """Request model for creating a crew member."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    name: str = Field(..., description="Crew member name")
    email: str = Field(..., description="Crew member email")
    phone: str = Field(..., description="Crew member phone number")
    property_id: Optional[str] = Field(None, description="Assigned property ID")
    role: Optional[str] = Field(None, description="Crew member role (e.g., cleaner, manager)")
    category_id: Optional[int] = Field(None, description="Assigned category ID")
    active: bool = Field(default=True, description="Whether the crew member is active")


class CreateCrewResponse(APIResponse):
    """Response model for creating a crew member."""
    data: Dict[str, Any] = Field(..., description="Created crew member data")


class BookingServiceItem(BaseModel):
    """Model for a service added to a booking."""
    service_id: int = Field(..., description="Service Category ID")
    service_date: datetime = Field(..., description="Date of the service")
    time: str = Field(..., description="Time of the service")


class CreateBookingRequest(BaseModel):
    """Request model for creating a booking with services."""
    reservation_id: str = Field(..., description="Reservation ID")
    platform: Platform = Field(..., description="Booking platform")
    guest_name: str = Field(..., description="Guest name")
    guest_phone: Optional[str] = Field(None, description="Guest phone number")
    guest_email: Optional[str] = Field(None, description="Guest email")
    check_in_date: datetime = Field(..., description="Check-in date")
    check_out_date: datetime = Field(..., description="Check-out date")
    property_id: Optional[str] = Field(None, description="Property ID")
    property_name: Optional[str] = Field(None, description="Property name")
    number_of_guests: Optional[int] = Field(None, description="Number of guests")
    total_amount: Optional[float] = Field(None, description="Total amount")
    currency: Optional[str] = Field(None, description="Currency")
    booking_date: Optional[datetime] = Field(None, description="Booking date")
    email_id: Optional[str] = Field(None, description="Email ID")
    raw_data: Optional[Dict[str, Any] | str] = Field(None, description="Raw booking data")
    services: Optional[List[BookingServiceItem]] = Field(default_factory=list, description="List of services to add")


class CreateBookingResponse(APIResponse):
    """Response model for creating a booking."""
    data: Dict[str, Any] = Field(..., description="Created booking details")


class DeleteCrewResponse(APIResponse):
    """Response model for deleting a crew member."""
    data: Dict[str, Any] = Field(..., description="Deletion result")

class UpdateCrewRequest(BaseModel):
    """Request model for updating a crew member (partial update)."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    name: Optional[str] = Field(None, description="Crew member name")
    email: Optional[str] = Field(None, description="Crew member email")
    phone: Optional[str] = Field(None, description="Crew member phone number")
    property_id: Optional[str] = Field(None, description="Assigned property ID")
    role: Optional[str] = Field(None, description="Crew member role (e.g., cleaner, manager)")
    category_id: Optional[int] = Field(None, description="Assigned category ID")
    active: Optional[bool] = Field(None, description="Whether the crew member is active")

class UserRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    email: str = Field(..., description="User email")
    password: str = Field(..., description="User password")

class UserUpdateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    password: str = Field(..., description="User password")

class UserResponse(APIResponse):
    data: Dict[str, Any] = Field(..., description="User data")

class UserListResponse(APIResponse):
    data: List[Dict[str, Any]] = Field(..., description="List of users")

class ConnectionResponse(APIResponse):
    data: Dict[str, Any] = Field(..., description="Connection result")

class RegisterRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    first_name: str = Field(..., description="User first name")
    last_name: str = Field(..., description="User last name")
    email: str = Field(..., description="User email")
    password: str = Field(..., description="User password")

class LoginRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    email: str = Field(..., description="User email")
    password: str = Field(..., description="User password")

class AuthResponse(APIResponse):
    data: Dict[str, Any] = Field(..., description="Auth data including token")

class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    first_name: str = Field(..., description="User first name")
    last_name: str = Field(..., description="User last name")

class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    email: str = Field(..., description="User email for password reset")

class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(..., description="New password")

class MetricTrend(BaseModel):
    """Model for a metric with trend data."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    value: float | int = Field(..., description="Current value")
    percentage_change: float = Field(..., description="Percentage change vs previous period")
    trend_direction: str = Field(..., description="Direction of change (up/down/neutral)")
    label: str = Field(..., description="Label for the trend (e.g., 'vs last month')")

class DashboardMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    # Top Cards with Trends
    total_revenue: MetricTrend = Field(..., description="Total revenue with trend")
    property_revenue: MetricTrend = Field(..., description="Revenue from properties with trend")
    service_revenue: MetricTrend = Field(..., description="Revenue from services with trend")
    active_bookings: MetricTrend = Field(..., description="Number of active bookings with trend")
    
    # Lists
    top_performing_properties: List[Dict[str, Any]] = Field(default_factory=list, description="Top properties with revenue and booking count")
    luxury_services_revenue: List[Dict[str, Any]] = Field(default_factory=list, description="Luxury services with revenue and booking count")
    guest_origins: List[Dict[str, Any]] = Field(default_factory=list, description="Guest origins statistics")
    priority_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="Priority tasks with status and due date")

class DashboardResponse(APIResponse):
    data: DashboardMetrics | Dict[str, Any] = Field(..., description="Dashboard metrics")


# Activity Rule Models

class ActivityRuleBase(BaseModel):
    """Base model for Activity Rule."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    rule_name: Optional[str] = Field(None, description="Name of the rule")
    slug_name: Optional[str] = Field(None, description="Slug name of the rule")
    condition: Optional[Dict[str, Any]] = Field(None, description="Rule conditions in JSON format")
    priority: Optional[str] = Field(None, description="Priority level")
    description: Optional[str] = Field(None, description="Description of the rule")
    status: Optional[bool] = Field(None, description="Status of the rule (enabled/disabled)")

class CreateActivityRuleRequest(ActivityRuleBase):
    """Request model for creating an activity rule."""
    rule_name: str = Field(..., description="Name of the rule")
    # Other fields remain optional as per the schema, but usually creation requires some valid data.
    # The SQL schema says columns are nullable.

class UpdateActivityRuleRequest(ActivityRuleBase):
    """Request model for updating an activity rule."""
    pass

class ActivityRuleResponse(ActivityRuleBase):
    """Response model for activity rule."""
    id: int = Field(..., description="Unique identifier")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Update timestamp")

    @field_serializer('created_at')
    def serialize_created_at(self, created_at: datetime) -> str:
        return created_at.isoformat()

    @field_serializer('updated_at')
    def serialize_updated_at(self, updated_at: Optional[datetime]) -> Optional[str]:
        return updated_at.isoformat() if updated_at else None

class ActivityRuleListResponse(APIResponse):
    """Response model for list of activity rules."""
    data: List[ActivityRuleResponse] = Field(..., description="List of activity rules")

class ActivityRuleDetailResponse(APIResponse):
    """Response model for a single activity rule."""
    data: ActivityRuleResponse = Field(..., description="Activity rule details")


class ActivityRuleLog(BaseModel):
    """Model for activity rule execution log."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int = Field(..., description="Unique identifier of the log")
    rule_name: str = Field(..., description="Name of the rule")
    outcome: str = Field(..., description="Outcome of the rule execution (success/failed)")
    created_at: datetime = Field(..., description="Timestamp of the log")
    updated_at: Optional[datetime] = Field(None, description="Update timestamp of the log")

    @field_serializer('created_at')
    def serialize_created_at(self, created_at: datetime) -> str:
        # Format: 27/01/2025, 10:00:00
        return created_at.strftime("%d/%m/%Y, %H:%M:%S")

    @field_serializer('updated_at')
    def serialize_updated_at(self, updated_at: Optional[datetime]) -> Optional[str]:
        return updated_at.strftime("%d/%m/%Y, %H:%M:%S") if updated_at else None


class ActivityRuleLogListResponse(APIResponse):
    """Response model for list of activity rule logs."""
    data: List[ActivityRuleLog] = Field(..., description="List of activity rule logs")

