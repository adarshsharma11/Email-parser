from typing import Dict, Any, List, Optional
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from config.settings import app_config, api_config


class PropertyService:
    """Service for managing property operations using PostgreSQL."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_property(
        self,
        name: str,
        address: str | None = None,
        vrbo_id: str | None = None,
        airbnb_id: str | None = None,
        booking_id: str | None = None,
        status: str = "active",
        base_price: float = 0.0,
        bedrooms: int = 0,
        owner_id: int | None = None,
    )-> Dict[str, Any]:
        """Save a new property and generate its iCal feed URL."""
        try:
            base_url = api_config.base_url or "http://127.0.0.1:8000"

            property_data = {
                "name": name,
                "address": address,
                "vrbo_id": vrbo_id,
                "airbnb_id": airbnb_id,
                "booking_id": booking_id,
                "status": status,
                "base_price": base_price,
                "bedrooms": bedrooms,
                "owner_id": owner_id,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }

            columns = ", ".join(property_data.keys())
            placeholders = ", ".join([f":{k}" for k in property_data.keys()])
            query = text(f"INSERT INTO {app_config.properties_collection} ({columns}) VALUES ({placeholders}) RETURNING *")
            
            result = await self.session.execute(query, property_data)
            row = result.fetchone()

            if row:
                inserted_property = dict(row._mapping)
                ical_url = f"{base_url}/property/{inserted_property['id']}.ics"
                
                update_query = text(f"UPDATE {app_config.properties_collection} SET ical_feed_url = :url WHERE id = :id RETURNING *")
                result = await self.session.execute(update_query, {"url": ical_url, "id": inserted_property["id"]})
                row = result.fetchone()
                return {"success": True, "data": dict(row._mapping)}
            else:
                raise Exception("Failed to insert property record")

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_property(self, property_id: int) -> Optional[Dict[str, Any]]:
        query = text(f"SELECT * FROM {app_config.properties_collection} WHERE id = :id")
        result = await self.session.execute(query, {"id": property_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def list_properties(self) -> List[Dict[str, Any]]:
        query = text(f"SELECT * FROM {app_config.properties_collection}")
        result = await self.session.execute(query)
        rows = result.fetchall()
        return [dict(row._mapping) for row in rows]

    async def get_properties(self, page: int, limit: int) -> Dict[str, Any]:
        try:
            offset = (page - 1) * limit
            query = text(f"SELECT * FROM {app_config.properties_collection} LIMIT :limit OFFSET :offset")
            result = await self.session.execute(query, {"limit": limit, "offset": offset})
            rows = result.fetchall()
            
            count_query = text(f"SELECT COUNT(*) FROM {app_config.properties_collection}")
            count_result = await self.session.execute(count_query)
            total = count_result.scalar() or 0
            
            return {
                "success": True,
                "data": [dict(row._mapping) for row in rows],
                "total": total,
                "page": page,
                "limit": limit
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def generate_ical_feed(self, prop: Dict[str, Any]) -> str:
        """Generate iCal feed content for a property."""
        from icalendar import Calendar, Event
        
        cal = Calendar()
        cal.add('prodid', '-//Email Parser iCal Feed//')
        cal.add('version', '2.0')
        cal.add('x-wr-calname', f"Bookings - {prop['name']}")
        
        # Fetch bookings for this property
        # Use property_name or property_id depending on how it's stored in bookings
        query = text(f"SELECT * FROM {app_config.bookings_collection} WHERE property_id = :pid OR property_name = :pname")
        result = await self.session.execute(query, {"pid": str(prop["id"]), "pname": prop["name"]})
        bookings = result.fetchall()
        
        for booking in bookings:
            event = Event()
            event.add('summary', f"Booking: {booking.guest_name}")
            event.add('dtstart', booking.check_in_date)
            event.add('dtend', booking.check_out_date)
            event.add('uid', booking.reservation_id)
            event.add('description', f"Platform: {booking.platform}\nGuests: {booking.number_of_guests}")
            cal.add_component(event)
            
        return cal.to_ical().decode('utf-8')

    async def delete_property(self, property_id: int) -> Dict[str, Any]:
        """Delete a property by its ID."""
        try:
            query = text(f"DELETE FROM {app_config.properties_collection} WHERE id = :id RETURNING *")
            result = await self.session.execute(query, {"id": int(property_id)})
            row = result.fetchone()

            if row:
                return {
                    "success": True,
                    "message": f"Property with ID {property_id} deleted successfully",
                    "data": dict(row._mapping)
                }
            else:
                return {
                    "success": False,
                    "error": f"No property found with ID {property_id}"
                }

        except Exception as e:
            return {"success": False, "error": str(e)}
