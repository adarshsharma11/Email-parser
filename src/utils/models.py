"""
Data models for the Vacation Rental Booking Automation system.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum


class Platform(Enum):
    """Supported vacation rental platforms."""
    VRBO = "vrbo"
    AIRBNB = "airbnb"
    BOOKING = "booking"
    PLUMGUIDE = "plumguide"


@dataclass
class EmailData:
    """Email data structure."""
    email_id: str
    subject: str
    sender: str
    date: datetime
    body_text: str
    body_html: str
    platform: Optional[Platform] = None
    folder: str = "INBOX"
    
    def __post_init__(self):
        if isinstance(self.platform, str):
            self.platform = Platform(self.platform.lower())


@dataclass
class BookingData:
    """Booking information extracted from emails."""
    reservation_id: str
    platform: Platform
    guest_name: str
    guest_phone: Optional[str] = None
    guest_email: Optional[str] = None
    check_in_date: Optional[datetime] = None
    check_out_date: Optional[datetime] = None
    property_id: Optional[str] = None
    property_name: Optional[str] = None
    number_of_guests: Optional[int] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    booking_date: Optional[datetime] = None
    email_id: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if isinstance(self.platform, str):
            self.platform = Platform(self.platform.lower())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert booking data to dictionary for Firestore storage."""
        return {
            'reservation_id': self.reservation_id,
            'platform': self.platform.value if self.platform else None,
            'guest_name': self.guest_name,
            'guest_phone': self.guest_phone,
            'guest_email': self.guest_email,
            'check_in_date': self.check_in_date.isoformat() if self.check_in_date else None,
            'check_out_date': self.check_out_date.isoformat() if self.check_out_date else None,
            'property_id': self.property_id,
            'property_name': self.property_name,
            'number_of_guests': self.number_of_guests,
            'total_amount': self.total_amount,
            'currency': self.currency,
            'booking_date': self.booking_date.isoformat() if self.booking_date else None,
            'email_id': self.email_id,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'raw_data': self.raw_data
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BookingData':
        """Create BookingData from dictionary."""
        # Convert string dates back to datetime objects
        if data.get('check_in_date'):
            data['check_in_date'] = datetime.fromisoformat(data['check_in_date'])
        if data.get('check_out_date'):
            data['check_out_date'] = datetime.fromisoformat(data['check_out_date'])
        if data.get('booking_date'):
            data['booking_date'] = datetime.fromisoformat(data['booking_date'])
        
        return cls(**data)
    
    def __str__(self) -> str:
        """String representation of booking data."""
        return (f"Booking(reservation_id='{self.reservation_id}', "
                f"platform='{self.platform.value}', "
                f"guest='{self.guest_name}', "
                f"check_in='{self.check_in_date}', "
                f"check_out='{self.check_out_date}')")


@dataclass
class ProcessingResult:
    """Result of email processing operation."""
    success: bool
    booking_data: Optional[BookingData] = None
    error_message: Optional[str] = None
    email_id: Optional[str] = None
    platform: Optional[Platform] = None
    
    def __post_init__(self):
        if isinstance(self.platform, str):
            self.platform = Platform(self.platform.lower())


@dataclass
class SyncResult:
    """Result of Firestore sync operation."""
    success: bool
    is_new: bool = False
    booking_data: Optional[BookingData] = None
    error_message: Optional[str] = None
    reservation_id: Optional[str] = None


@dataclass
class ProcessingStats:
    """Statistics for processing operations."""
    emails_processed: int = 0
    bookings_parsed: int = 0
    new_bookings: int = 0
    duplicate_bookings: int = 0
    errors: int = 0
    platforms: Dict[str, int] = field(default_factory=dict)
    
    def reset(self):
        """Reset all statistics."""
        self.emails_processed = 0
        self.bookings_parsed = 0
        self.new_bookings = 0
        self.duplicate_bookings = 0
        self.errors = 0
        self.platforms.clear()
    
    def add_platform_count(self, platform: str):
        """Add count for a platform."""
        if platform not in self.platforms:
            self.platforms[platform] = 0
        self.platforms[platform] += 1
