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
        address: str | None = None,
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
                "address": address,
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
            # Note: logger might not be available here, using print for now
            print(f"Error fetching properties: {str(e)}")
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

    def get_bookings_by_property(self, property_id: str) -> list:
        """
        Fetch all bookings for a specific property.
        
        Args:
            property_id: Property ID to search for
            
        Returns:
            List of booking dictionaries
        """
        try:
            if not self.supabase_client.initialized:
                if not self.supabase_client.initialize():
                    return []
            
            # Try to fetch bookings by property name (common pattern in the codebase)
            result = (
                self.supabase_client.client
                .table(app_config.bookings_collection)
                .select("*")
                .eq("property_name", property_id)
                .order("check_in_date", desc=True)
                .execute()
            )
            
            bookings = result.data if result.data else []
            
            # If no bookings found by property_name, try by property_id
            if not bookings:
                result = (
                    self.supabase_client.client
                    .table(app_config.bookings_collection)
                    .select("*")
                    .eq("property_id", property_id)
                    .order("check_in_date", desc=True)
                    .execute()
                )
                bookings = result.data if result.data else []
            
            return bookings
            
        except Exception as e:
            print(f"Error fetching bookings for property {property_id}: {e}")
            return []

    def generate_ical_feed(self, prop: Dict[str, Any]) -> str:
        """
        Generate valid iCal content for the property with actual bookings.
        
        Notes:
        - Lines must not have leading spaces; in iCalendar, a leading space indicates
          a folded continuation line, which would corrupt properties.
        - Use CRLF line endings per RFC 5545.
        """
        property_id = prop["id"]
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        # Derive a meaningful UID domain from configured base URL
        parsed = urlparse(api_config.base_url or "")
        uid_domain = (parsed.hostname or "example.com").strip()
        prodid = f"-//{uid_domain}//Booking Calendar//EN"

        # Fetch actual bookings for this property
        bookings = self.get_bookings_by_property(property_id)
        
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            f"PRODID:{prodid}",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]

        # Add booking events
        for booking in bookings:
            try:
                # Parse booking dates
                check_in = datetime.fromisoformat(booking['check_in_date'].replace('Z', '+00:00'))
                check_out = datetime.fromisoformat(booking['check_out_date'].replace('Z', '+00:00'))
                
                # Format dates for iCal
                start = check_in.strftime("%Y%m%dT%H%M%SZ")
                end = check_out.strftime("%Y%m%dT%H%M%SZ")
                
                # Create summary with guest name if available
                guest_name = booking.get('guest_name', 'Guest')
                reservation_id = booking.get('reservation_id', 'Unknown')
                summary = f"Booking - {guest_name} ({reservation_id})"
                
                lines.extend([
                    "BEGIN:VEVENT",
                    f"UID:{reservation_id}@{uid_domain}",
                    f"DTSTAMP:{now}",
                    f"SUMMARY:{summary}",
                    f"DTSTART:{start}",
                    f"DTEND:{end}",
                    f"DESCRIPTION:Guest: {guest_name}\\nPlatform: {booking.get('platform', 'Unknown')}\\nReservation ID: {reservation_id}",
                    "END:VEVENT",
                ])
            except Exception as e:
                # Log error but continue with other bookings
                print(f"Error processing booking {booking.get('reservation_id', 'unknown')}: {e}")
                continue

        lines.append("END:VCALENDAR")

        # Join with CRLF and ensure trailing newline
        return "\r\n".join(lines) + "\r\n"
