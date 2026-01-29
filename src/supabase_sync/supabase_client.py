"""
Supabase client helper for syncing vacation rental booking data.
"""
from datetime import datetime, date, timezone
from typing import Optional, Dict, Any, List
import structlog
import uuid

try:
    from supabase import create_client  # type: ignore
except Exception:  # pragma: no cover - allow importing tests without package
    create_client = None  # type: ignore

from src.utils.models import BookingData, SyncResult
from src.utils.logger import get_logger
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

            # Call get_auth_key() method to get the authentication key
            auth_key = supabase_config.get_auth_key()

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

            # STRICT Logic: Only update if Property + Dates match exactly.
            existing = None
            if booking_data.property_id and booking_data.check_in_date and booking_data.check_out_date:
                existing = self.get_booking_by_property_and_dates(
                    booking_data.property_id,
                    booking_data.check_in_date,
                    booking_data.check_out_date
                )

            if existing:
                # UPDATE
                self.logger.info("Booking exists (Property+Dates match) - Updating", 
                               reservation_id=existing.get("reservation_id"))
                
                # Use existing reservation_id to overwrite correct row
                booking_data.reservation_id = existing["reservation_id"]
                
                if dry_run:
                     self.logger.info("DRY RUN: Would update booking", reservation_id=booking_data.reservation_id)
                     return SyncResult(
                         success=True, 
                         is_new=False, 
                         booking_data=booking_data, 
                         reservation_id=booking_data.reservation_id
                     )

                payload = booking_data.to_dict()
                payload["updated_at"] = datetime.utcnow()
                # Ensure we use the ID from DB
                payload["reservation_id"] = existing["reservation_id"]
                payload = self._serialize_payload(payload)
                
                self.client.table(app_config.bookings_collection).upsert(payload, on_conflict="reservation_id").execute()
                is_new = False
                
            else:
                # INSERT (New Booking)
                # Check for reservation_id collision with DIFFERENT dates
                collision = self.get_booking_by_reservation_id(booking_data.reservation_id)
                
                if collision:
                    # If we are here, it means dates didn't match (existing is None), but ID exists.
                    # We must NOT overwrite the collision.
                    original_id = booking_data.reservation_id
                    booking_data.reservation_id = f"{original_id}_{uuid.uuid4().hex[:4]}"
                    self.logger.warning("Reservation ID collision with different dates. Generated new ID to avoid overwrite.", 
                                      original_id=original_id, new_id=booking_data.reservation_id)
                
                if dry_run:
                     self.logger.info("DRY RUN: Would insert new booking", reservation_id=booking_data.reservation_id)
                     return SyncResult(
                         success=True, 
                         is_new=True, 
                         booking_data=booking_data, 
                         reservation_id=booking_data.reservation_id
                     )

                payload = booking_data.to_dict()
                payload["updated_at"] = datetime.utcnow()
                payload = self._serialize_payload(payload)
                
                self.client.table(app_config.bookings_collection).insert(payload).execute()
                is_new = True

            self.logger.info(
                "Successfully synced booking to Supabase",
                reservation_id=booking_data.reservation_id,
                platform=booking_data.platform.value,
                action="update" if not is_new else "insert"
            )
            
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

    def create_booking_with_services(self, booking_payload: Dict[str, Any], services: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a booking and associated services."""
        try:
            if not self.initialized and not self.initialize():
                raise Exception("Supabase client not initialized")

            # Ensure timestamps
            if "created_at" not in booking_payload:
                booking_payload["created_at"] = datetime.utcnow().isoformat()
            booking_payload["updated_at"] = datetime.utcnow().isoformat()
            
            # Serialize payload
            serialized_payload = self._serialize_payload(booking_payload)
            
            # Upsert booking and get the result to obtain the ID
            res = (
                self.client.table(app_config.bookings_collection)
                .upsert(serialized_payload, on_conflict="reservation_id")
                .execute()
            )
            
            booking_data = getattr(res, "data", [])
            booking_record = booking_data[0] if booking_data else None
            
            # If we don't have the ID, fetch the booking
            if not booking_record or "id" not in booking_record:
                self.logger.info("Upsert didn't return ID, fetching booking...", reservation_id=booking_payload["reservation_id"])
                booking_record = self.get_booking_by_reservation_id(booking_payload["reservation_id"])
                
            if not booking_record:
                raise Exception("Failed to retrieve created/updated booking")
            
            booking_db_id = booking_record.get("id")
            # Fallback to reservation_id if id is missing
            if not booking_db_id:
                booking_db_id = booking_payload["reservation_id"]
            
            # Insert services if any
            if services:
                service_payloads = []
                for svc in services:
                    # serialize service date if needed
                    svc_date = svc["service_date"]
                    if isinstance(svc_date, datetime) or isinstance(svc_date, date):
                        svc_date = svc_date.isoformat()
                        
                    service_payloads.append({
                        "booking_id": booking_db_id if booking_db_id else booking_payload["reservation_id"],
                        "service_id": svc["service_id"],
                        "service_date": svc_date,
                        "time": svc["time"]
                    })
                
                if service_payloads:
                    self.client.table("booking_service").insert(service_payloads).execute()
            
            return booking_record

        except Exception as e:
            self.logger.error("Failed to create booking with services", error=str(e))
            raise e

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

    def get_single_crew_by_category(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Get a single active crew by category ID (global - ignores property_id)."""
        try:
            if not self.initialized and not self.initialize():
                return None
            
            # Build query: active crews with matching category_id (global, no property filtering)
            # Explicitly select all fields including email and phone for notifications
            query = self.client.table(app_config.cleaning_crews_collection).select("id,name,email,phone,category_id,active,property_id").eq("active", True).eq("category_id", category_id)

            resp = query.execute()
            
            if resp.data:
                crew = resp.data[0]
                # Ensure email and phone are present for notifications
                if not crew.get("email") or not crew.get("phone"):
                    self.logger.warning("Crew found but missing email or phone", crew_id=crew.get("id"), email=crew.get("email"), phone=crew.get("phone"))
                return crew
            return None
        except Exception as e:
            self.logger.error("Failed to fetch crew by category", category_id=category_id, error=str(e))
            return None


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
    
    def get_cleaning_tasks_by_reservation_id(self, reservation_id: str) -> List[Dict[str, Any]]:
        try:
            if not self.initialized and not self.initialize():
                return []
            res = (
                self.client.table(app_config.cleaning_tasks_collection)
                .select("*")
                .eq("reservation_id", reservation_id)
                .execute()
            )
            if hasattr(res, "data"):
                return res.data or []
            if hasattr(res, "json") and callable(res.json):
                return res.json().get("data", []) or []
            return getattr(res, "json", {}).get("data", []) or []
        except Exception as e:
            self.logger.error("Error fetching cleaning tasks by reservation", reservation_id=reservation_id, error=str(e))
            return []
    
    def exists_cleaning_task_for_reservation(self, reservation_id: str) -> bool:
        tasks = self.get_cleaning_tasks_by_reservation_id(reservation_id)
        return bool(tasks)
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

    def get_booking_by_email_id(self, email_id: str) -> Optional[Dict[str, Any]]:
        try:
            if not self.initialized and not self.initialize():
                return None
            res = (
                self.client.table(app_config.bookings_collection)
                .select("*")
                .eq("email_id", email_id)
                .limit(1)
                .execute()
            )
            rows = getattr(res, "data", []) or getattr(res, "json", {}).get("data", [])
            return rows[0] if rows else None
        except Exception as e:
            self.logger.error("Error getting booking by email ID", email_id=email_id, error=str(e))
            return None

    def get_bookings_paginated(self, platform: Optional[str], offset: int, limit: int) -> Dict[str, Any]:
        """Paginated bookings without date filtering; includes records with null check_in_date."""
        try:
            if not self.initialized and not self.initialize():
                return {"rows": [], "total": 0}
            base = self.client.table(app_config.bookings_collection)
            # total count query (without range)
            count_query = base.select("reservation_id", count="exact")
            if platform:
                count_query = count_query.eq("platform", platform)
            count_res = count_query.execute()
            total = getattr(count_res, "count", None)
            if total is None:
                total_rows = getattr(count_res, "data", []) or getattr(count_res, "json", {}).get("data", [])
                total = len(total_rows)

            # data query with ordering and range
            data_query = base.select("*").order("created_at", desc=True)
            if platform:
                data_query = data_query.eq("platform", platform)
            data_query = data_query.range(offset, max(0, offset + limit - 1))
            data_res = data_query.execute()
            if hasattr(data_res, "data"):
                rows = data_res.data or []
            elif hasattr(data_res, "json") and callable(data_res.json):
                rows = data_res.json().get("data", [])
            else:
                rows = getattr(data_res, "json", {}).get("data", []) or []

            return {"rows": rows, "total": int(total)}
        except Exception as e:
            self.logger.error("Error fetching paginated bookings", platform=platform, offset=offset, limit=limit, error=str(e))
            return {"rows": [], "total": 0}

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

            bookings_res = query.execute()

            # Safely extract bookings (handle both supabase-py versions)
            if hasattr(bookings_res, "data"):
                bookings = bookings_res.data or []
            elif hasattr(bookings_res, "json") and callable(bookings_res.json):
                bookings = bookings_res.json().get("data", [])
            else:
                bookings = getattr(bookings_res, "json", {}).get("data", []) or []

            if not bookings:
                self.logger.info(f"No bookings found for platform={platform}")
                return []

            reservation_ids = [str(b["reservation_id"]) for b in bookings if b.get("reservation_id")]
            self.logger.info(f"Found {len(bookings)} bookings, reservation_ids={reservation_ids}")

            # 2️⃣ Fetch cleaning tasks
            tasks = []
            if reservation_ids:
                tasks_res = (
                    self.client.table("cleaning_tasks")
                    .select("*")
                    .in_("reservation_id", reservation_ids)
                    .order("scheduled_date", desc=True)
                    .execute()
                )

                if hasattr(tasks_res, "data"):
                    tasks = tasks_res.data or []
                elif hasattr(tasks_res, "json") and callable(tasks_res.json):
                    tasks = tasks_res.json().get("data", [])
                else:
                    tasks = getattr(tasks_res, "json", {}).get("data", []) or []

            self.logger.info(f"Fetched {len(tasks)} tasks for {len(reservation_ids)} bookings")

            # 3️⃣ Fetch crews if any crew_id exists
            crew_ids = list({t["crew_id"] for t in tasks if isinstance(t, dict) and t.get("crew_id")})
            crew_map = {}

            if crew_ids:
                crews_res = (
                    self.client.table("cleaning_crews")
                    .select("*")
                    .in_("id", crew_ids)
                    .execute()
                )

                if hasattr(crews_res, "data"):
                    crews = crews_res.data or []
                elif hasattr(crews_res, "json") and callable(crews_res.json):
                    crews = crews_res.json().get("data", [])
                else:
                    crews = getattr(crews_res, "json", {}).get("data", []) or []

                crew_map = {str(c["id"]): c for c in crews if isinstance(c, dict) and c.get("id")}

            self.logger.info(f"Fetched {len(crew_map)} crews")

            # 4️⃣ Group tasks by reservation_id
            from collections import defaultdict
            tasks_by_booking = defaultdict(list)

            for task in tasks:
                if not isinstance(task, dict):
                    continue
                res_id = str(task.get("reservation_id"))
                crew_info = crew_map.get(str(task.get("crew_id")))
                tasks_by_booking[res_id].append({
                    "task_id": task.get("id"),
                    "scheduled_date": task.get("scheduled_date"),
                    "crews": crew_info
                })

            # 5️⃣ Merge bookings with tasks (even if no tasks exist)
            result = []
            for booking in bookings:
                res_id = str(booking.get("reservation_id"))
                result.append({
                    **booking,
                    "tasks": tasks_by_booking.get(res_id, [])
                })

            self.logger.info(f"Final result: {len(result)} bookings (with/without tasks)")
            return result

        except Exception as e:
            self.logger.error(
                "Error getting bookings with tasks and crew",
                platform=platform,
                error=str(e)
            )
            return []

    def get_all_bookings(self) -> List[Dict[str, Any]]:
        """Fetch ALL bookings (for testing/debug)"""
        try:
            if not self.initialized and not self.initialize():
                self.logger.error("Supabase client not initialized — cannot fetch all bookings.")
                return []

            self.logger.info("Fetching ALL bookings from Supabase...")
            table_name = getattr(app_config, "bookings_collection", "bookings")
            self.logger.info(f"Using table: {table_name}")

            bookings_res = (
                self.client.table(table_name)
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )

            # Debug print the response
            self.logger.info(f"Supabase response: {bookings_res}")
            
            # Extract rows safely
            if hasattr(bookings_res, "data"):
                data = bookings_res.data or []
            elif hasattr(bookings_res, "json") and callable(bookings_res.json):
                data = bookings_res.json().get("data", [])
            else:
                data = getattr(bookings_res, "json", {}).get("data", []) or []

            self.logger.info(f"Fetched {len(data)} total bookings.")
            return data

        except Exception as e:
            self.logger.error("Error fetching all bookings", error=str(e))
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
            updates["updated_at"] = datetime.now(timezone.utc)
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

    def get_booking_by_property_and_dates(self, property_id: str, check_in: datetime, check_out: datetime) -> Optional[Dict[str, Any]]:
        try:
            if not self.initialized and not self.initialize():
                return None
            
            # Fetch all bookings for this property to perform robust date comparison in Python
            # This avoids issues with DB date format vs ISO string mismatch
            res = (
                self.client.table(app_config.bookings_collection)
                .select("*")
                .eq("property_id", property_id)
                .execute()
            )
            rows = getattr(res, "data", []) or getattr(res, "json", {}).get("data", [])
            
            # Get target dates as date objects
            target_ci = check_in.date() if hasattr(check_in, "date") else check_in
            target_co = check_out.date() if hasattr(check_out, "date") else check_out
            
            for row in rows:
                try:
                    # Safely parse DB dates (handle YYYY-MM-DD or ISO with time)
                    r_ci_str = str(row.get("check_in_date", ""))
                    r_co_str = str(row.get("check_out_date", ""))
                    
                    if len(r_ci_str) < 10 or len(r_co_str) < 10:
                        continue
                        
                    # Extract YYYY-MM-DD part
                    row_ci = datetime.strptime(r_ci_str[:10], "%Y-%m-%d").date()
                    row_co = datetime.strptime(r_co_str[:10], "%Y-%m-%d").date()
                    
                    if row_ci == target_ci and row_co == target_co:
                        return row
                except Exception:
                    continue
            
            return None
        except Exception as e:
            self.logger.error("Error getting booking by property and dates", property_id=property_id, error=str(e))
            return None

    # Context manager helpers
    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
