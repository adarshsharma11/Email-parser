"""
Booking service for handling booking-related business logic using PostgreSQL.
"""
from typing import Optional, Dict, Any, AsyncGenerator, List
from datetime import datetime, timedelta, date
import time
import json
import asyncio
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func, and_, or_

from ..models import (
    BookingSummary, BookingStatsResponse, ErrorResponse, 
    CreateBookingRequest, CreateBookingResponse, BookingStatus
)
from ..config import settings
from config.settings import app_config
from ...guest_communications.notifier import Notifier
from ...utils.models import BookingData, Platform
from .crew_service import CrewService
from .automation_service import AutomationService
from .activity_rule_service import ActivityRuleService
from .service_category_service import ServiceCategoryService
from .user_service import UserService


class BookingService:
    """Service for handling booking operations."""
    
    def __init__(self, session: AsyncSession, logger):
        self.session = session
        self.logger = logger
        self._cache = {}
        self._cache_ttl = settings.cache_ttl_seconds
        self.crew_service = CrewService(session)
        self.service_category_service = ServiceCategoryService(session)
        self.user_service = UserService(session)
        self.notifier = None # Initialized asynchronously if needed
        
        # Initialize AutomationService with dependencies
        activity_rule_service = ActivityRuleService(session, logger)
        self.automation_service = AutomationService(activity_rule_service)

    async def _get_notifier(self) -> Notifier:
        """Get or initialize notifier with dynamic credentials if not development."""
        if self.notifier:
            return self.notifier
            
        credentials = None
        app_env = os.getenv("APP_ENV", "development")
        
        if app_env != "development":
            try:
                # Try to fetch from user_credentials with platform='crdetails'
                table_name = app_config.users_collection
                query = text(f"SELECT email, password FROM {table_name} WHERE platform = 'crdetails' LIMIT 1")
                result = await self.session.execute(query)
                row = result.fetchone()
                
                # If no 'crdetails' platform, try fetching the first available from user_credentials
                if not row:
                    self.logger.info(f"No 'crdetails' platform in {table_name}, trying first available row")
                    query = text(f"SELECT email, password FROM {table_name} LIMIT 1")
                    result = await self.session.execute(query)
                    row = result.fetchone()

                # If still no row, maybe 'crdetails' is the table name itself?
                if not row:
                    try:
                        self.logger.info("Trying to fetch from 'crdetails' table directly")
                        query = text("SELECT email, password FROM crdetails LIMIT 1")
                        result = await self.session.execute(query)
                        row = result.fetchone()
                    except Exception:
                        self.logger.info("'crdetails' table does not exist")

                if row:
                    row_dict = dict(row._mapping)
                    cred_email = row_dict.get("email")
                    cred_password = row_dict.get("password")
                    
                    if cred_email and cred_password:
                        # Decrypt password using UserService
                        decrypted_password = self.user_service.decrypt(cred_password)
                        credentials = {
                            "username": cred_email,
                            "password": decrypted_password
                        }
                        self.logger.info(f"Using database credentials for email: {cred_email}")
                    else:
                        self.logger.warning("Found database credential but email or password missing")
                else:
                    self.logger.warning("No email credentials found in database")
            except Exception as e:
                self.logger.error(f"Failed to fetch production email credentials: {e}")
        
        self.notifier = Notifier(email_credentials=credentials)
        return self.notifier
    
    async def create_booking_process(self, request: CreateBookingRequest) -> AsyncGenerator[str, None]:
        """
        Process booking creation with step-by-step status updates.
        """
        try:
            notifier = await self._get_notifier()
            # Step 1: Create Booking Record
            yield json.dumps({
                "step": "database",
                "status": "in_progress",
                "message": "Creating booking record..."
            }, default=str) + "\n"
            
            response = await self.create_booking(request)
            
            if not response.success:
                yield json.dumps({
                    "step": "database",
                    "status": "failed", 
                    "message": response.message
                }, default=str) + "\n"
                return

            yield json.dumps({
                "step": "database", 
                "status": "completed",
                "message": "Booking record created"
            }, default=str) + "\n"
            
            # Step 2: Calendar Blocking
            yield json.dumps({
                "step": "calendar",
                "status": "in_progress",
                "message": "Updating calendar blocks..."
            }, default=str) + "\n"
            
            # Mock calendar update for now
            yield json.dumps({
                "step": "calendar",
                "status": "completed",
                "message": "Calendar updated"
            }, default=str) + "\n"

            # Step 3: Guest Notifications
            yield json.dumps({
                "step": "guest_notification",
                "status": "in_progress",
                "message": "Checking guest notification rules..."
            }, default=str) + "\n"
            
            if await self.automation_service.is_rule_enabled("guest_welcome_message"):
                try:
                    booking_data = BookingData(
                        reservation_id=request.reservation_id,
                        platform=request.platform,
                        guest_name=request.guest_name,
                        guest_phone=request.guest_phone,
                        guest_email=request.guest_email,
                        check_in_date=request.check_in_date,
                        check_out_date=request.check_out_date,
                        property_name=request.property_name or "Vacation Rental",
                        property_id=request.property_id
                    )
                    
                    notifier.send_welcome(booking_data)
                    if request.guest_phone:
                        notifier.send_welcome_whatsapp(booking_data)
                    
                    await self.automation_service.log_rule_execution("Guest Welcome Message", "success")

                    yield json.dumps({
                        "step": "guest_notification",
                        "status": "completed",
                        "message": "Guest notified via Email/SMS"
                    }, default=str) + "\n"
                except Exception as e:
                    self.logger.error(f"Guest notification failed: {e}")
                    await self.automation_service.log_rule_execution("Guest Welcome Message", "failed")
                    yield json.dumps({
                        "step": "guest_notification",
                        "status": "failed",
                        "message": f"Failed to notify guest: {str(e)}"
                    }, default=str) + "\n"
            else:
                yield json.dumps({
                    "step": "guest_notification",
                    "status": "skipped",
                    "message": "Guest welcome rule is disabled"
                }, default=str) + "\n"

            # Step 4: Crew Notifications
            yield json.dumps({
                "step": "crew_notification",
                "status": "in_progress",
                "message": "Checking crew notification rules..."
            }, default=str) + "\n"
            
            if await self.automation_service.is_rule_enabled("create_cleaning_task"):
                try:
                    if request.property_name:
                        crew = await self.crew_service.get_single_crew_by_category(category_id=2)
                        notified_count = 0
                        
                        if crew:
                            scheduled_date = request.check_out_date
                            task = await self.create_cleaning_task(
                                booking_id=request.reservation_id,
                                property_id=request.property_name,
                                scheduled_date=scheduled_date,
                                crew_id=crew.get("id")
                            )
                            
                            if task:
                                task_for_notify = {
                                    "id": task.get("id", f"task_{request.reservation_id}"),
                                    "booking_id": request.reservation_id,
                                    "property_id": request.property_name,
                                    "scheduled_date": scheduled_date
                                }
                                
                                if notifier.notify_cleaning_task(crew, task_for_notify, booking_data):
                                    notified_count = 1
                                    from ...calendar_integration.google_calendar_client import GoogleCalendarClient
                                    calendar_client = GoogleCalendarClient()
                                    calendar_client.add_cleaning_event(crew, task_for_notify)
                            
                        yield json.dumps({
                            "step": "crew_notification",
                            "status": "completed",
                            "message": f"Notified {notified_count} crew members"
                        }, default=str) + "\n"
                        await self.automation_service.log_rule_execution("Create Cleaning Task", "success")
                    else:
                        yield json.dumps({
                            "step": "crew_notification",
                            "status": "skipped",
                            "message": "No property name for crew lookup"
                        }, default=str) + "\n"
                except Exception as e:
                    self.logger.error(f"Crew notification failed: {e}")
                    await self.automation_service.log_rule_execution("Create Cleaning Task", "failed")
                    yield json.dumps({
                        "step": "crew_notification",
                        "status": "warning",
                        "message": "Crew notification incomplete"
                    }, default=str) + "\n"
            else:
                yield json.dumps({
                    "step": "crew_notification",
                    "status": "skipped",
                    "message": "Cleaning task rule is disabled"
                }, default=str) + "\n"

            # Step 5: Service Provider Notifications
            if request.services:
                yield json.dumps({
                    "step": "service_notification",
                    "status": "in_progress",
                    "message": f"Notifying {len(request.services)} service providers..."
                }, default=str) + "\n"
                
                notified_services = 0
                for svc in request.services:
                    try:
                        service_category = await self.service_category_service.get_category(svc.service_id)
                        if service_category:
                            provider = {
                                "id": service_category.get("id"),
                                "name": service_category.get("category_name", "Service Provider"),
                                "email": service_category.get("email"),
                                "phone": service_category.get("phone")
                            }
                            
                            service_details = {
                                "reservation_id": request.reservation_id,
                                "service_name": service_category.get("category_name", "Service"),
                                "service_date": svc.service_date.strftime("%Y-%m-%d") if hasattr(svc.service_date, "strftime") else str(svc.service_date),
                                "service_time": svc.time,
                                "property_name": request.property_name or "Vacation Rental"
                            }
                            
                            if notifier.notify_service_provider(provider, service_details):
                                notified_services += 1
                        else:
                            self.logger.warning(f"No service category found for ID {svc.service_id}")
                    except Exception as e:
                        self.logger.error(f"Failed to notify service provider for service {svc.service_id}: {e}")
                
                yield json.dumps({
                    "step": "service_notification",
                    "status": "completed",
                    "message": f"Notified {notified_services} service providers"
                }, default=str) + "\n"

            # Final Success
            yield json.dumps({
                "step": "complete",
                "status": "success",
                "message": "All booking steps completed successfully",
                "data": response.data
            }, default=str) + "\n"

        except Exception as e:
            self.logger.error(f"Booking process failed: {e}", exc_info=True)
            yield json.dumps({
                "step": "process",
                "status": "error",
                "message": f"Critical error: {str(e)}"
            }, default=str) + "\n"

    async def create_booking(self, request: CreateBookingRequest) -> CreateBookingResponse:
        """Create a new booking with services in PostgreSQL."""
        try:
            self.logger.info("Creating new booking", reservation_id=request.reservation_id)
            
            booking_dict = request.model_dump(exclude={"services"})
            if "platform" in booking_dict and hasattr(booking_dict["platform"], "value"):
                booking_dict["platform"] = booking_dict["platform"].value
            
            # Ensure raw_data is a JSON string if it's a dict
            if "raw_data" in booking_dict and isinstance(booking_dict["raw_data"], dict):
                booking_dict["raw_data"] = json.dumps(booking_dict["raw_data"], default=str)
            
            # Upsert booking
            columns = ", ".join(booking_dict.keys())
            placeholders = ", ".join([f":{k}" for k in booking_dict.keys()])
            query = text(f"""
                INSERT INTO bookings ({columns}) 
                VALUES ({placeholders}) 
                ON CONFLICT (reservation_id) DO UPDATE 
                SET {', '.join([f"{k} = EXCLUDED.{k}" for k in booking_dict.keys() if k != 'reservation_id'])},
                    updated_at = NOW()
                RETURNING *
            """)
            
            result = await self.session.execute(query, booking_dict)
            booking_row = result.fetchone()
            
            if not booking_row:
                raise Exception("Failed to create/update booking")
                
            booking_record = dict(booking_row._mapping)
            
            # Handle services
            if request.services:
                for svc in request.services:
                    # Convert time string to time object if it's a string
                    service_time = svc.time
                    import datetime as dt_mod
                    if isinstance(service_time, str):
                        try:
                            # Try HH:MM format
                            parsed_dt = datetime.strptime(service_time, "%H:%M")
                            # Make it timezone-aware (UTC) since the DB column expects it
                            service_time = parsed_dt.time().replace(tzinfo=dt_mod.timezone.utc)
                        except ValueError:
                            try:
                                # Try HH:MM:SS format
                                parsed_dt = datetime.strptime(service_time, "%H:%M:%S")
                                service_time = parsed_dt.time().replace(tzinfo=dt_mod.timezone.utc)
                            except ValueError:
                                # Fallback to original if parsing fails
                                pass
                    elif hasattr(service_time, "tzinfo") and service_time.tzinfo is None:
                        # If it's already a time object but naive, make it aware
                        service_time = service_time.replace(tzinfo=dt_mod.timezone.utc)

                    svc_dict = {
                        "booking_id": request.reservation_id,
                        "service_id": svc.service_id,
                        "service_date": svc.service_date.date() if hasattr(svc.service_date, "date") else svc.service_date,
                        "time": service_time
                    }
                    svc_query = text("""
                        INSERT INTO booking_service (booking_id, service_id, service_date, time)
                        VALUES (:booking_id, :service_id, :service_date, :time)
                    """)
                    await self.session.execute(svc_query, svc_dict)
            
            return CreateBookingResponse(
                success=True,
                message="Booking created successfully",
                data=booking_record
            )
            
        except Exception as e:
            error_msg = f"Failed to create booking: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return CreateBookingResponse(success=False, message=error_msg, data={})

    async def get_booking_statistics(self) -> BookingStatsResponse:
        """Get booking statistics from PostgreSQL with caching."""
        try:
            cache_key = "booking_stats"
            current_time = time.time()
            
            if cache_key in self._cache:
                cached_data, timestamp = self._cache[cache_key]
                if current_time - timestamp < self._cache_ttl:
                    return cached_data
            
            # Total bookings
            res_total = await self.session.execute(text("SELECT COUNT(*) FROM bookings"))
            total = res_total.scalar() or 0
            
            # By platform
            by_platform = {}
            for platform in ["vrbo", "airbnb", "booking", "plumguide"]:
                res = await self.session.execute(
                    text("SELECT COUNT(*) FROM bookings WHERE platform = :p"),
                    {"p": platform}
                )
                by_platform[platform] = res.scalar() or 0
            
            booking_summary = BookingSummary(
                total_bookings=total,
                by_platform=by_platform,
                last_updated=datetime.utcnow()
            )
            
            response = BookingStatsResponse(
                success=True,
                message="Booking statistics retrieved successfully",
                data=booking_summary
            )
            
            self._cache[cache_key] = (response, current_time)
            return response
            
        except Exception as e:
            self.logger.error(f"Error fetching stats: {e}")
            raise

    async def create_cleaning_task(self, booking_id: str, property_id: str, scheduled_date: Any, crew_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        try:
            payload = {
                "reservation_id": booking_id,
                "property_id": property_id,
                "scheduled_date": scheduled_date,
                "crew_id": crew_id
            }
            query = text("""
                INSERT INTO cleaning_tasks (reservation_id, property_id, scheduled_date, crew_id)
                VALUES (:reservation_id, :property_id, :scheduled_date, :crew_id)
                RETURNING *
            """)
            result = await self.session.execute(query, payload)
            row = result.fetchone()
            return dict(row._mapping) if row else None
        except Exception as e:
            self.logger.error(f"Failed to create cleaning task: {e}")
            return None

    async def get_bookings_paginated(self, platform: Optional[str], page: int, limit: int) -> Dict[str, Any]:
        try:
            offset = (page - 1) * limit
            
            # Count
            count_query = "SELECT COUNT(*) FROM bookings"
            params = {}
            if platform:
                count_query += " WHERE platform = :p"
                params["p"] = platform
            
            res_count = await self.session.execute(text(count_query), params)
            total = res_count.scalar() or 0
            
            # Data
            data_query = "SELECT * FROM bookings"
            if platform:
                data_query += " WHERE platform = :p"
            data_query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            params.update({"limit": limit, "offset": offset})
            
            res_data = await self.session.execute(text(data_query), params)
            rows = res_data.fetchall()
            
            return {
                "bookings": [dict(row._mapping) for row in rows],
                "total": total,
                "page": page,
                "limit": limit
            }
        except Exception as e:
            self.logger.error(f"Error fetching paginated bookings: {e}")
            return {"bookings": [], "total": 0, "page": page, "limit": limit}

    async def get_booking_by_reservation_id(self, reservation_id: str) -> Optional[Dict[str, Any]]:
        query = text("SELECT * FROM bookings WHERE reservation_id = :rid LIMIT 1")
        result = await self.session.execute(query, {"rid": reservation_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def update_guest_phone(self, reservation_id: str, guest_phone: str) -> bool:
        try:
            query = text("UPDATE bookings SET guest_phone = :phone, updated_at = NOW() WHERE reservation_id = :rid")
            await self.session.execute(query, {"phone": guest_phone, "rid": reservation_id})
            return True
        except Exception as e:
            self.logger.error(f"Failed to update guest phone: {e}")
            return False
