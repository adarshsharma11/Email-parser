"""
Booking service for handling booking-related business logic.
"""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import time

from ...supabase_sync.supabase_client import SupabaseClient
from ..models import BookingSummary, BookingStatsResponse, ErrorResponse
from ..config import settings


class BookingService:
    """Service for handling booking operations."""
    
    def __init__(self, supabase_client: SupabaseClient, logger):
        self.supabase_client = supabase_client
        self.logger = logger
        self._cache = {}
        self._cache_ttl = settings.cache_ttl_seconds
    
    def get_booking_statistics(self) -> BookingStatsResponse:
        """
        Get booking statistics from Supabase with caching.
        
        Returns:
            BookingStatsResponse with total bookings and platform breakdown
        """
        try:
            # Check cache first
            cache_key = "booking_stats"
            current_time = time.time()
            
            if cache_key in self._cache:
                cached_data, timestamp = self._cache[cache_key]
                if current_time - timestamp < self._cache_ttl:
                    self.logger.info("Returning cached booking statistics")
                    return cached_data
            
            self.logger.info("Fetching booking statistics from Supabase")
            
            # Get raw stats from Supabase client
            raw_stats = self.supabase_client.get_booking_stats()
            
            if not raw_stats:
                error_msg = "Failed to fetch booking statistics: Empty response from database"
                self.logger.error(error_msg)
                return ErrorResponse(
                    success=False,
                    message=error_msg,
                    error_code="DATABASE_ERROR",
                    details={"error": "Empty response"}
                )
            
            # Transform to immutable model
            booking_summary = BookingSummary(
                total_bookings=raw_stats.get('total_bookings', 0),
                by_platform=raw_stats.get('by_platform', {}),
                last_updated=datetime.utcnow()
            )
            
            response = BookingStatsResponse(
                success=True,
                message="Booking statistics retrieved successfully",
                data=booking_summary
            )
            
            # Cache the response
            self._cache[cache_key] = (response, current_time)
            
            self.logger.info(
                "Booking statistics fetched successfully",
                total_bookings=booking_summary.total_bookings,
                platforms_count=len(booking_summary.by_platform)
            )
            
            return response
            
        except Exception as e:
            error_msg = f"Unexpected error fetching booking statistics: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return ErrorResponse(
                success=False,
                message="Internal server error",
                error_code="INTERNAL_ERROR",
                details={"error": str(e)}
            )
    
    def get_bookings_paginated(self, platform: Optional[str] = None, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        """
        Get paginated booking records from Supabase.
        
        Args:
            platform: Optional platform filter
            page: Page number (starts at 1)
            limit: Number of bookings per page
            
        Returns:
            Dictionary with paginated booking data
        """
        try:
            self.logger.info(f"Fetching paginated bookings: platform={platform}, page={page}, limit={limit}")
            
            # Calculate offset for pagination
            offset = (page - 1) * limit
            
            # Get bookings based on platform filter
            if platform:
                # Use existing platform-specific method
                all_bookings = self.supabase_client.get_bookings_by_platform(platform)
                # Manual pagination since the existing method doesn't support offset
                total_count = len(all_bookings)
                bookings_data = all_bookings[offset:offset + limit]
            else:
                # Get all bookings - we'll need to implement a generic method or use date range
                # For now, let's use a reasonable date range to get recent bookings
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=365)  # Last year
                all_bookings = self.supabase_client.get_bookings_by_date_range(start_date, end_date)
                total_count = len(all_bookings)
                bookings_data = all_bookings[offset:offset + limit]
            
            total_pages = (total_count + limit - 1) // limit if total_count > 0 else 0
            
            return {
                "bookings": bookings_data,
                "total": total_count,
                "page": page,
                "limit": limit,
                "total_pages": total_pages
            }
            
        except Exception as e:
            error_msg = f"Error fetching paginated bookings: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            raise Exception(error_msg)

    def get_platform_statistics(self, platform: str) -> Dict[str, Any]:
        """
        Get statistics for a specific platform.
        
        Args:
            platform: Platform name (vrbo, airbnb, booking, plumguide)
            
        Returns:
            Dictionary with platform-specific statistics
        """
        try:
            self.logger.info(f"Fetching statistics for platform: {platform}")
            
            # Get all statistics first
            all_stats = self.get_booking_statistics()
            
            if not all_stats.success or not all_stats.data:
                return {
                    "platform": platform,
                    "count": 0,
                    "error": "Failed to fetch statistics"
                }
            
            platform_count = all_stats.data.by_platform.get(platform, 0)
            
            return {
                "platform": platform,
                "count": platform_count,
                "percentage": round((platform_count / all_stats.data.total_bookings * 100), 2) if all_stats.data.total_bookings > 0 else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error fetching platform statistics for {platform}: {str(e)}")
            return {
                "platform": platform,
                "count": 0,
                "error": str(e)
            }