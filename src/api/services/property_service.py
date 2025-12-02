from typing import Dict, Any
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from ...supabase_sync.supabase_client import SupabaseClient
from ..models import APIResponse, ErrorResponse
from config.settings import app_config, api_config


class PropertyService:
    """Service for managing property operations."""

    def __init__(self):
        """Initialize property service with Supabase client."""
        self.supabase_client = SupabaseClient()

    def create_property(
        self,
        name: str,
        vrbo_id: str | None = None,
        airbnb_id: str | None = None,
        booking_id: str | None = None,
        status: str = "active",
    )-> Dict[str, Any]:
        """
        Save a new property and generate its iCal feed URL.
        """
        try:
            # Ensure Supabase client is ready
            if not self.supabase_client.initialized:
                if not self.supabase_client.initialize():
                    raise Exception("Failed to initialize Supabase client")

            # Use base URL from API config
            base_url = api_config.base_url or "http://127.0.0.1:8000"

            # Create property data without manual ID
            property_data = {
                "name": name,
                "vrbo_id": vrbo_id,
                "airbnb_id": airbnb_id,
                "booking_id": booking_id,
                "status": status,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            # Insert into Supabase
            result = (
                self.supabase_client.client
                .table(app_config.properties_collection)
                .insert(property_data)
                .execute()
            )

            if result.data and len(result.data) > 0:
                inserted_property = result.data[0]
                # Construct iCal URL using the DB-generated ID
                inserted_property["ical_feed_url"] = f"{base_url}/property/{inserted_property['id']}.ics"
                self.supabase_client.client.table(app_config.properties_collection)\
                .update({"ical_feed_url": inserted_property["ical_feed_url"]})\
                .eq("id", inserted_property["id"]).execute()
                return {"success": True, "data": inserted_property}
            else:
                raise Exception("Failed to insert property record")

        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_property(self, property_id: str) -> Dict[str, Any]:
        """Delete a property by its ID."""
        try:
            if not self.supabase_client.initialized:
                self.supabase_client.initialize()

            result = (
                self.supabase_client.client
                .table(app_config.properties_collection)
                .delete()
                .eq("id", property_id)
                .execute()
            )

            if result.data:
                return {
                    "success": True,
                    "message": f"Property with ID {property_id} deleted successfully",
                    "deleted_count": len(result.data)
                }
            else:
                return {
                    "success": False,
                    "error": f"No property found with ID {property_id}"
                }

        except Exception as e:
            return {"success": False, "error": str(e)}


    def get_properties(self, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        """Get paginated list of properties."""
        try:
            if not self.supabase_client.initialized:
                self.supabase_client.initialize()

            offset = (page - 1) * limit

            result = (
                self.supabase_client.client
                .table(app_config.properties_collection)
                .select("*")
                .range(offset, offset + limit - 1)
                .execute()
            )

            total_result = (
                self.supabase_client.client
                .table(app_config.properties_collection)
                .select("id")
                .execute()
            )

            return {
                "success": True,
                "data": {
                    "data": result.data or [],
                    "total": len(total_result.data or []),
                    "page": page,
                    "limit": limit
                }
            }

        except Exception as e:
            self.logger.error(f"Error fetching properties: {str(e)}")
            return {"success": False, "error": str(e)}  

    def get_property_by_id(self, property_id: str) -> Dict[str, Any] | None:
        """Fetch property by ID from Supabase"""
        if not self.supabase_client.initialized:
            self.supabase_client.initialize()
        result = (
            self.supabase_client.client
            .table(app_config.properties_collection)
            .select("*")
            .eq("id", property_id)
            .execute()
        )
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None

    def generate_ical_feed(self, prop: Dict[str, Any]) -> str:
        """
        Generate valid iCal content for the property.

        Notes:
        - Lines must not have leading spaces; in iCalendar, a leading space indicates
          a folded continuation line, which would corrupt properties.
        - Use CRLF line endings per RFC 5545.
        """
        property_id = prop["id"]
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        start_dt = datetime.now(timezone.utc).replace(year=2026, hour=12, minute=0, second=0, microsecond=0)
        end_dt = start_dt + timedelta(days=2)
        start = start_dt.strftime("%Y%m%dT%H%M%SZ")
        end = end_dt.strftime("%Y%m%dT%H%M%SZ")

        # Derive a meaningful UID domain from configured base URL
        parsed = urlparse(api_config.base_url or "")
        uid_domain = (parsed.hostname or "example.com").strip()

        prodid = f"-//{uid_domain}//Booking Calendar//EN"

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            f"PRODID:{prodid}",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            f"UID:{property_id}@{uid_domain}",
            f"DTSTAMP:{now}",
            f"SUMMARY:Sample Booking for {prop['name']}",
            f"DTSTART:{start}",
            f"DTEND:{end}",
            "END:VEVENT",
            "END:VCALENDAR",
        ]

        # Join with CRLF and ensure trailing newline
        return "\r\n".join(lines) + "\r\n"
