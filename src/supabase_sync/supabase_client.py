"""
Supabase client helper for syncing vacation rental booking data.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List

import structlog

try:
    from supabase import create_client  # type: ignore
except Exception:  # pragma: no cover - allow importing tests without package
    create_client = None  # type: ignore

from ..utils.models import BookingData, SyncResult
from ..utils.logger import get_logger
from config.settings import supabase_config, app_config


class SupabaseClient:
    """Supabase client for booking data synchronization."""

    def __init__(self):
        self.logger = get_logger("supabase_client")
        self.client = None
        self.initialized = False

    def initialize(self) -> bool:
        """Initialize Supabase client from environment configuration."""
        try:
            if self.initialized:
                return True

            if not supabase_config.url or not supabase_config.get_auth_key():
                self.logger.error("Supabase configuration missing", url=bool(supabase_config.url))
                return False

            if create_client is None:
                raise ImportError("supabase package not installed. Add 'supabase' to requirements.txt")

            self.client = create_client(supabase_config.url, supabase_config.get_auth_key())
            self.initialized = True
            self.logger.info("Supabase client initialized successfully", url=supabase_config.url)
            return True
        except Exception as e:
            self.logger.error("Failed to initialize Supabase client", error=str(e))
            self.initialized = False
            return False

    # CRUD operations
    def sync_booking(self, booking_data: BookingData, dry_run: bool = False) -> SyncResult:
        try:
            if not self.initialized and not self.initialize():
                return SyncResult(success=False, error_message="Failed to initialize Supabase client", reservation_id=booking_data.reservation_id)

            # Check if exists by reservation_id
            existing = self.get_booking_by_reservation_id(booking_data.reservation_id)
            if existing is not None:
                self.logger.info("Booking already exists in Supabase", reservation_id=booking_data.reservation_id)
                return SyncResult(success=True, is_new=False, booking_data=booking_data, reservation_id=booking_data.reservation_id)

            if dry_run:
                self.logger.info("DRY RUN: Would add new booking to Supabase", reservation_id=booking_data.reservation_id)
                return SyncResult(success=True, is_new=True, booking_data=booking_data, reservation_id=booking_data.reservation_id)

            payload = booking_data.to_dict()
            payload["updated_at"] = datetime.utcnow().isoformat()

            # Use upsert with reservation_id unique constraint if defined, else insert
            resp = self.client.table(app_config.bookings_collection).upsert(payload, on_conflict="reservation_id").execute()
            self.logger.info("Successfully synced booking to Supabase", reservation_id=booking_data.reservation_id, platform=booking_data.platform.value)
            # Determine if new by checking returned rows length; upsert returns the row
            is_new = existing is None
            return SyncResult(success=True, is_new=is_new, booking_data=booking_data, reservation_id=booking_data.reservation_id)
        except Exception as e:
            self.logger.error("Error syncing booking to Supabase", reservation_id=booking_data.reservation_id, error=str(e))
            return SyncResult(success=False, error_message=str(e), reservation_id=booking_data.reservation_id)

    def sync_bookings(self, bookings: List[BookingData], dry_run: bool = False) -> List[SyncResult]:
        results: List[SyncResult] = []
        for b in bookings:
            results.append(self.sync_booking(b, dry_run))
        return results

    def get_booking_by_reservation_id(self, reservation_id: str) -> Optional[Dict[str, Any]]:
        try:
            if not self.initialized and not self.initialize():
                return None
            res = self.client.table(app_config.bookings_collection).select("*").eq("reservation_id", reservation_id).limit(1).execute()
            rows = getattr(res, "data", []) or getattr(res, "json", {}).get("data", [])
            return rows[0] if rows else None
        except Exception as e:
            self.logger.error("Error getting booking by reservation ID", reservation_id=reservation_id, error=str(e))
            return None

    def get_bookings_by_platform(self, platform: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        try:
            if not self.initialized and not self.initialize():
                return []
            query = self.client.table(app_config.bookings_collection).select("*").eq("platform", platform).order("created_at", desc=True)
            if limit:
                query = query.limit(limit)
            res = query.execute()
            rows = getattr(res, "data", []) or getattr(res, "json", {}).get("data", [])
            self.logger.info("Retrieved bookings by platform", platform=platform, count=len(rows))
            return rows
        except Exception as e:
            self.logger.error("Error getting bookings by platform", platform=platform, error=str(e))
            return []

    def get_bookings_by_date_range(self, start_date: datetime, end_date: datetime, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        try:
            if not self.initialized and not self.initialize():
                return []
            query = (
                self.client.table(app_config.bookings_collection)
                .select("*")
                .gte("check_in_date", start_date.isoformat())
                .lte("check_in_date", end_date.isoformat())
                .order("check_in_date")
            )
            if limit:
                query = query.limit(limit)
            res = query.execute()
            rows = getattr(res, "data", []) or getattr(res, "json", {}).get("data", [])
            self.logger.info("Retrieved bookings by date range", start_date=start_date.isoformat(), end_date=end_date.isoformat(), count=len(rows))
            return rows
        except Exception as e:
            self.logger.error("Error getting bookings by date range", start_date=start_date.isoformat(), end_date=end_date.isoformat(), error=str(e))
            return []

    def update_booking(self, reservation_id: str, updates: Dict[str, Any]) -> bool:
        try:
            if not self.initialized and not self.initialize():
                return False
            updates["updated_at"] = datetime.utcnow().isoformat()
            self.client.table(app_config.bookings_collection).update(updates).eq("reservation_id", reservation_id).execute()
            self.logger.info("Successfully updated booking", reservation_id=reservation_id)
            return True
        except Exception as e:
            self.logger.error("Error updating booking", reservation_id=reservation_id, error=str(e))
            return False

    def delete_booking(self, reservation_id: str) -> bool:
        try:
            if not self.initialized and not self.initialize():
                return False
            self.client.table(app_config.bookings_collection).delete().eq("reservation_id", reservation_id).execute()
            self.logger.info("Successfully deleted booking", reservation_id=reservation_id)
            return True
        except Exception as e:
            self.logger.error("Error deleting booking", reservation_id=reservation_id, error=str(e))
            return False

    def get_booking_stats(self) -> Dict[str, Any]:
        try:
            if not self.initialized and not self.initialize():
                return {}
            # Total
            res_total = self.client.table(app_config.bookings_collection).select("reservation_id", count="exact").execute()
            total = getattr(res_total, "count", None)
            if total is None:
                rows = getattr(res_total, "data", []) or getattr(res_total, "json", {}).get("data", [])
                total = len(rows)
            stats = {"total_bookings": int(total)}
            # by platform
            by_platform = {}
            for platform in ["vrbo", "airbnb", "booking"]:
                res = (
                    self.client.table(app_config.bookings_collection)
                    .select("reservation_id", count="exact")
                    .eq("platform", platform)
                    .execute()
                )
                count = getattr(res, "count", None)
                if count is None:
                    rows = getattr(res, "data", []) or getattr(res, "json", {}).get("data", [])
                    count = len(rows)
                by_platform[platform] = int(count)
            stats["by_platform"] = by_platform
            self.logger.info("Retrieved booking statistics", stats=stats)
            return stats
        except Exception as e:
            self.logger.error("Error getting booking statistics", error=str(e))
            return {}

    # Context manager helpers
    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
