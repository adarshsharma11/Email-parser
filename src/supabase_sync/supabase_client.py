"""
Supabase client helper for syncing vacation rental booking data.
"""
from datetime import datetime, date
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

            # Ensure we call get_auth_key() if it's a function
            auth_key = supabase_config.get_auth_key() if callable(supabase_config.get_auth_key) else supabase_config.get_auth_key

            if not supabase_config.url or not auth_key:
                self.logger.error("Supabase configuration missing", url=bool(supabase_config.url))
                return False

            if create_client is None:
                raise ImportError("supabase package not installed. Add 'supabase' to requirements.txt")

            self.client = create_client(supabase_config.url, auth_key)
            self.initialized = True
            self.logger.info("Supabase client initialized successfully", url=supabase_config.url)
            return True
        except Exception as e:
            self.logger.error("Failed to initialize Supabase client", error=str(e))
            self.initialized = False
            return False

    def _serialize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively convert datetimes and unsupported types to JSON-serializable values."""

        def serialize_value(value):
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, dict):
                return {k: serialize_value(v) for k, v in value.items()}
            if isinstance(value, list):
                return [serialize_value(v) for v in value]
            return value

        return {k: serialize_value(v) for k, v in payload.items()}

    # CRUD operations
    def sync_booking(self, booking_data: BookingData, dry_run: bool = False) -> SyncResult:
        try:
            if not self.initialized and not self.initialize():
                return SyncResult(
                    success=False,
                    error_message="Failed to initialize Supabase client",
                    reservation_id=booking_data.reservation_id,
                )

            # Check if exists by reservation_id
            existing = self.get_booking_by_reservation_id(booking_data.reservation_id)
            if existing is not None:
                self.logger.info("Booking already exists in Supabase", reservation_id=booking_data.reservation_id)
                return SyncResult(
                    success=True,
                    is_new=False,
                    booking_data=booking_data,
                    reservation_id=booking_data.reservation_id,
                )

            if dry_run:
                self.logger.info("DRY RUN: Would add new booking to Supabase", reservation_id=booking_data.reservation_id)
                return SyncResult(
                    success=True,
                    is_new=True,
                    booking_data=booking_data,
                    reservation_id=booking_data.reservation_id,
                )

            # Serialize payload
            payload = booking_data.to_dict()
            payload["updated_at"] = datetime.utcnow()
            payload = self._serialize_payload(payload)

            # Insert or upsert
            resp = (
                self.client.table(app_config.bookings_collection)
                .upsert(payload, on_conflict="reservation_id")
                .execute()
            )

            self.logger.info(
                "Successfully synced booking to Supabase",
                reservation_id=booking_data.reservation_id,
                platform=booking_data.platform.value,
            )
            is_new = existing is None
            return SyncResult(
                success=True,
                is_new=is_new,
                booking_data=booking_data,
                reservation_id=booking_data.reservation_id,
            )
        except Exception as e:
            self.logger.error(
                "Error syncing booking to Supabase",
                reservation_id=booking_data.reservation_id,
                error=str(e),
            )
            return SyncResult(success=False, error_message=str(e), reservation_id=booking_data.reservation_id)

    def sync_bookings(self, bookings: List[BookingData], dry_run: bool = False) -> List[SyncResult]:
        results: List[SyncResult] = []
        for b in bookings:
            results.append(self.sync_booking(b, dry_run))
        return results

    def list_active_crews(self, property_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return active cleaning crews (optionally filtered by property)."""
        try:
            if not self.initialized and not self.initialize():
                return []
                
            query = self.client.table(app_config.cleaning_crews_collection).select("*").eq("active", True)
            if property_id:
                query = query.eq("property_id", property_id)

            resp = query.execute()
            if resp.data:
                return resp.data
            return []
        except Exception as e:
            self.logger.error("Failed to fetch active crews", error=str(e))
            return []


    def create_cleaning_task(self, booking_id: str, property_id: str, scheduled_date: date, crew_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        try:
            if not self.initialized and not self.initialize():
                return None
                
            payload = {
                "reservation_id": booking_id,
                "property_id": property_id,
                "scheduled_date": scheduled_date.isoformat() if hasattr(scheduled_date, "isoformat") else str(scheduled_date),
                "crew_id": crew_id
            }
            resp = self.client.table(app_config.cleaning_tasks_collection).insert(payload).execute()
            # The Supabase client returns the response object; check for data presence
            if resp and getattr(resp, "data", None):
                return resp.data[0]
            return None
        except Exception as e:
            self.logger.error("Failed to create cleaning task", booking_id=booking_id, property_id=property_id, error=str(e))
            return None
    def get_booking_by_reservation_id(self, reservation_id: str) -> Optional[Dict[str, Any]]:
        try:
            if not self.initialized and not self.initialize():
                return None
            res = (
                self.client.table(app_config.bookings_collection)
                .select("*")
                .eq("reservation_id", reservation_id)
                .limit(1)
                .execute()
            )
            rows = getattr(res, "data", []) or getattr(res, "json", {}).get("data", [])
            return rows[0] if rows else None
        except Exception as e:
            self.logger.error("Error getting booking by reservation ID", reservation_id=reservation_id, error=str(e))
            return None

    def get_bookings_by_platform(self, platform: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        try:
            if not self.initialized and not self.initialize():
                return []
            query = (
                self.client.table(app_config.bookings_collection)
                .select("*")
                .eq("platform", platform)
                .order("created_at", desc=True)
            )
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
            updates["updated_at"] = datetime.utcnow()
            updates = self._serialize_payload(updates)
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
