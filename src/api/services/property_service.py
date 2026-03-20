from typing import Dict, Any, List, Optional
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from config.settings import app_config, api_config
from ..config import settings
from .auth_service import AuthService


class PropertyService:
    """Service for managing property operations using PostgreSQL."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.auth_service = AuthService(session)

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
        new_owner_data: Dict[str, Any] | None = None,
    )-> Dict[str, Any]:
        """Save a new property and generate its iCal feed URL."""
        try:
            # If new owner data is provided, create the user first
            if new_owner_data:
                try:
                    new_user = await self.auth_service.save_user(
                        email=new_owner_data["email"],
                        password=new_owner_data.get("password") or "effi@12345",  # User requested default password or provided one
                        first_name=new_owner_data.get("first_name"),
                        last_name=new_owner_data.get("last_name"),
                        role="property_owner"
                    )
                    owner_id = new_user["id"]
                except ValueError as e:
                    if str(e) == "EMAIL_ALREADY_REGISTERED":
                        # If email already exists, try to get the existing user's ID
                        existing_user = await self.auth_service.get_user(new_owner_data["email"])
                        if existing_user:
                            owner_id = existing_user["id"]
                    else:
                        raise e

            base_url = settings.api_base_url or "http://127.0.0.1:8001"
            api_prefix = settings.api_prefix or ""
            api_version = settings.api_version or "v1"

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
                # Ensure the URL includes the version prefix so it's routed correctly
                # We use the /ical suffix instead of .ics to avoid proxy issues with static file extensions
                prefix_part = f"{api_prefix}/{api_version}" if api_prefix else f"/{api_version}"
                ical_url = f"{base_url}{prefix_part}/property/{inserted_property['id']}/ical"
                
                update_query = text(f"UPDATE {app_config.properties_collection} SET ical_feed_url = :url WHERE id = :id RETURNING *")
                result = await self.session.execute(update_query, {"url": ical_url, "id": inserted_property["id"]})
                row = result.fetchone()
                return {"success": True, "data": dict(row._mapping)}
            else:
                raise Exception("Failed to insert property record")

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_property(self, property_id: int) -> Optional[Dict[str, Any]]:
        query = text(f"""
            SELECT p.*, 
                   u.first_name as owner_first_name, 
                   u.last_name as owner_last_name, 
                   u.email as owner_email
            FROM {app_config.properties_collection} p
            LEFT JOIN users u ON p.owner_id = u.id
            WHERE p.id = :id
        """)
        result = await self.session.execute(query, {"id": property_id})
        row = result.fetchone()
        if not row:
            return None
            
        p_dict = dict(row._mapping)
        # Nest owner details
        p_dict["owner"] = {
            "first_name": p_dict.pop("owner_first_name"),
            "last_name": p_dict.pop("owner_last_name"),
            "email": p_dict.pop("owner_email")
        } if p_dict.get("owner_email") else None
        
        return p_dict

    async def list_properties(self) -> List[Dict[str, Any]]:
        query = text(f"""
            SELECT p.*, 
                   u.first_name as owner_first_name, 
                   u.last_name as owner_last_name, 
                   u.email as owner_email
            FROM {app_config.properties_collection} p
            LEFT JOIN users u ON p.owner_id = u.id
        """)
        result = await self.session.execute(query)
        rows = result.fetchall()
        
        properties = []
        for row in rows:
            p_dict = dict(row._mapping)
            # Nest owner details
            p_dict["owner"] = {
                "first_name": p_dict.pop("owner_first_name"),
                "last_name": p_dict.pop("owner_last_name"),
                "email": p_dict.pop("owner_email")
            } if p_dict.get("owner_email") else None
            properties.append(p_dict)
            
        return properties

    async def get_properties(self, page: int, limit: int) -> Dict[str, Any]:
        try:
            offset = (page - 1) * limit
            # Join properties with users to get owner details
            query = text(f"""
                SELECT p.*, 
                       u.first_name as owner_first_name, 
                       u.last_name as owner_last_name, 
                       u.email as owner_email
                FROM {app_config.properties_collection} p
                LEFT JOIN users u ON p.owner_id = u.id
                LIMIT :limit OFFSET :offset
            """)
            result = await self.session.execute(query, {"limit": limit, "offset": offset})
            rows = result.fetchall()
            
            count_query = text(f"SELECT COUNT(*) FROM {app_config.properties_collection}")
            count_result = await self.session.execute(count_query)
            total = count_result.scalar() or 0
            
            properties = []
            for row in rows:
                p_dict = dict(row._mapping)
                # Nest owner details
                p_dict["owner"] = {
                    "first_name": p_dict.pop("owner_first_name"),
                    "last_name": p_dict.pop("owner_last_name"),
                    "email": p_dict.pop("owner_email")
                } if p_dict.get("owner_email") else None
                properties.append(p_dict)

            return {
                "success": True,
                "data": properties,
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

    async def update_property(self, property_id: int, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing property."""
        try:
            # Filter out None values and handle ID
            update_data = {k: v for k, v in update_data.items() if v is not None}
            if not update_data:
                return {"success": False, "error": "No data to update"}

            update_data["updated_at"] = datetime.now(timezone.utc)
            
            set_clauses = [f"{k} = :{k}" for k in update_data.keys()]
            query = text(f"""
                UPDATE {app_config.properties_collection} 
                SET {', '.join(set_clauses)} 
                WHERE id = :prop_id 
                RETURNING *
            """)
            
            params = {**update_data, "prop_id": int(property_id)}
            result = await self.session.execute(query, params)
            row = result.fetchone()

            if row:
                return {"success": True, "data": dict(row._mapping)}
            else:
                return {"success": False, "error": f"Property with ID {property_id} not found"}

        except Exception as e:
            return {"success": False, "error": str(e)}
