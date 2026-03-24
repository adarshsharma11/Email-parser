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
    CreateBookingRequest, CreateBookingResponse, BookingStatus,
    SendWelcomeEmailRequest, APIResponse
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
from fastapi import HTTPException
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)



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
                    notified_count = 0
                    # Notify all active crews where role='Cleaning'
                    # Per user request, crews work on all properties, so no property_id check needed.
                    crews = await self.crew_service.get_active_crews(role="Cleaning")
                    
                    if crews:
                        # Per user request, pick first one only not all
                        crew = crews[0]
                        scheduled_date = request.check_out_date
                        
                        # Ensure booking_data is available even if guest welcome step was skipped
                        if 'booking_data' not in locals():
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

                        task = await self.create_cleaning_task(
                            booking_id=request.reservation_id,
                            property_id=request.property_name or request.property_id or "Unknown",
                            scheduled_date=scheduled_date,
                            crew_id=crew.get("id"),
                            category_id=crew.get("category_id")
                        )
                        
                        if task:
                            task_for_notify = {
                                "id": task.get("id", f"task_{request.reservation_id}"),
                                "booking_id": request.reservation_id,
                                "property_id": request.property_name or request.property_id or "Unknown",
                                "scheduled_date": scheduled_date
                            }

                            # Per user request: Only send notifications/events if check-in is today or in the future
                            is_future_stay = True
                            if request.check_in_date:
                                # Normalize both to dates for comparison
                                check_in_date = request.check_in_date.date() if hasattr(request.check_in_date, 'date') else request.check_in_date
                                today_date = datetime.utcnow().date()
                                if check_in_date < today_date:
                                    is_future_stay = False
                                    self.logger.info(f"Skipping notifications for past stay (check-in: {check_in_date})")

                            if is_future_stay:
                                if notifier.notify_cleaning_task(crew, task_for_notify, booking_data):
                                    notified_count += 1
                                    
                                    # Log to task_notifications so the follow-up cron knows this crew was notified
                                    try:
                                        # Use a nested transaction (savepoint) to prevent aborting the whole transaction if this fails
                                        async with self.session.begin_nested():
                                            log_query = text("""
                                                INSERT INTO task_notifications 
                                                (task_id, crew_id, notification_type, status, created_at)
                                                VALUES (:task_id, :crew_id, 'initial_notification', 'sent', CURRENT_TIMESTAMP)
                                            """)
                                            await self.session.execute(log_query, {
                                                "task_id": task.get("id"),
                                                "crew_id": crew.get("id")
                                            })
                                    except Exception as log_err:
                                        self.logger.warning(f"Failed to log initial notification (possibly missing table): {log_err}")
                                        # We don't want to fail the whole booking process just because logging failed

                                    try:
                                        from ...calendar_integration.google_calendar_client import GoogleCalendarClient
                                        calendar_client = GoogleCalendarClient()
                                        calendar_client.add_cleaning_event(crew, task_for_notify)
                                    except Exception as cal_err:
                                        self.logger.error(f"Failed to add crew calendar event: {cal_err}")
                            else:
                                self.logger.info(f"Past stay detected for {request.reservation_id}, skipping notifications and calendar event.")
                        
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
                            "message": "No active cleaning crew found"
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
                # Get created services from the response data
                created_services = response.data.get("services", [])
                
                for idx, svc in enumerate(request.services):
                    try:
                        service_category = await self.service_category_service.get_category(int(svc.service_id))
                        if service_category:
                            provider = {
                                "id": service_category.get("id"),
                                "name": service_category.get("category_name", "Service Provider"),
                                "email": service_category.get("email"),
                                "phone": service_category.get("phone")
                            }
                            
                            # Find the corresponding created service record for the ID
                            service_record = created_services[idx] if idx < len(created_services) else {}
                            
                            service_details = {
                                "id": service_record.get("id"), # Pass the unique service task ID
                                "reservation_id": request.reservation_id,
                                "service_name": service_category.get("category_name", "Service"),
                                "service_date": svc.service_date.strftime("%Y-%m-%d") if hasattr(svc.service_date, "strftime") else str(svc.service_date),
                                "service_time": str(svc.time),
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
            
            # Upsert booking - Use COALESCE for specific fields to avoid overwriting with null
            columns = ", ".join(booking_dict.keys())
            placeholders = ", ".join([f":{k}" for k in booking_dict.keys()])
            
            # Fields that we want to keep if the new one is null
            coalesce_fields = {'total_amount', 'guest_email', 'guest_phone'}
            
            set_clause = []
            for k in booking_dict.keys():
                if k == 'reservation_id':
                    continue
                if k in coalesce_fields:
                    set_clause.append(f"{k} = COALESCE(EXCLUDED.{k}, bookings.{k})")
                # Do not update other fields if they already exist
            
            query = text(f"""
                INSERT INTO bookings ({columns}) 
                VALUES ({placeholders}) 
                ON CONFLICT (reservation_id) DO UPDATE 
                SET {', '.join(set_clause)},
                    updated_at = NOW()
                RETURNING *
            """)
            
            result = await self.session.execute(query, booking_dict)
            booking_row = result.fetchone()
            
            if not booking_row:
                raise Exception("Failed to create/update booking")
                
            booking_record = dict(booking_row._mapping)
            
            # Handle services
            service_records = []
            if request.services:
                for svc in request.services:
                    # Convert time string to time object if it's a string
                    service_time = svc.time
                    import datetime as dt_mod
                    if isinstance(service_time, str):
                        try:
                            # Try HH:MM format
                            parsed_dt = dt_mod.datetime.strptime(service_time, "%H:%M")
                            # Make it timezone-aware (UTC) since the DB column expects it
                            service_time = parsed_dt.time().replace(tzinfo=dt_mod.timezone.utc)
                        except ValueError:
                            try:
                                # Try HH:MM:SS format
                                parsed_dt = dt_mod.datetime.strptime(service_time, "%H:%M:%S")
                                service_time = parsed_dt.time().replace(tzinfo=dt_mod.timezone.utc)
                            except ValueError:
                                # Fallback to original if parsing fails
                                pass
                    elif hasattr(service_time, "tzinfo") and service_time.tzinfo is None:
                        # If it's already a time object but naive, make it aware
                        service_time = service_time.replace(tzinfo=dt_mod.timezone.utc)

                    # Use reservation_id as the link (booking_id column is now text)
                    booking_id_val = request.reservation_id
                    
                    # Handle date parsing
                    s_date = svc.service_date
                    if isinstance(s_date, str):
                        try:
                            s_date_obj = dt_mod.datetime.strptime(s_date, "%Y-%m-%d").date()
                        except ValueError:
                            s_date_obj = dt_mod.datetime.fromisoformat(s_date).date()
                    else:
                        s_date_obj = s_date.date() if hasattr(s_date, "date") else s_date

                    s_dict = {
                        "booking_id": booking_id_val,
                        "service_id": svc.service_id,
                        "service_date": s_date_obj,
                        "time": service_time
                    }
                    s_query = text("""
                        INSERT INTO booking_service (booking_id, service_id, service_date, time)
                        VALUES (:booking_id, :service_id, :service_date, :time)
                        RETURNING *
                    """)
                    res = await self.session.execute(s_query, s_dict)
                    row = res.fetchone()
                    if row:
                        service_records.append(dict(row._mapping))
            
            booking_record["services"] = service_records
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

    async def send_welcome_email(self, request: SendWelcomeEmailRequest) -> APIResponse:
        """Send a manual welcome email/whatsapp and update the booking record."""
        try:
            self.logger.info("Sending manual welcome message", reservation_id=request.reservation_id, email=request.guest_email, phone=request.guest_phone)
            
            # 1. Fetch the booking
            query = text("SELECT * FROM bookings WHERE reservation_id = :rid")
            result = await self.session.execute(query, {"rid": request.reservation_id})
            row = result.fetchone()
            
            if not row:
                return APIResponse(success=False, message=f"Booking {request.reservation_id} not found")
            
            booking_dict = dict(row._mapping)
            
            # 2. Update the email and phone in database
            updates = []
            params = {"rid": request.reservation_id}
            
            if request.guest_email:
                updates.append("guest_email = :email")
                params["email"] = request.guest_email
            
            if request.guest_phone:
                updates.append("guest_phone = :phone")
                params["phone"] = request.guest_phone
                
            if updates:
                update_query = text(f"""
                    UPDATE bookings 
                    SET {", ".join(updates)}, updated_at = NOW() 
                    WHERE reservation_id = :rid
                """)
                await self.session.execute(update_query, params)
            
            # 3. Trigger notification
            # Convert dict to BookingData model for the notifier
            booking_data = BookingData(
                reservation_id=booking_dict['reservation_id'],
                platform=Platform(booking_dict['platform']),
                guest_name=booking_dict.get('guest_name') or 'Guest',
                guest_email=request.guest_email or booking_dict.get('guest_email'), 
                guest_phone=request.guest_phone or booking_dict.get('guest_phone'),
                check_in_date=booking_dict.get('check_in_date'),
                check_out_date=booking_dict.get('check_out_date'),
                property_name=booking_dict.get('property_name') or 'Your Property',
                total_amount=booking_dict.get('total_amount'),
                booking_date=booking_dict.get('booking_date'),
                email_id=booking_dict.get('email_id')
            )
            
            notifier = await self._get_notifier()
            
            # Send Email
            email_success = False
            if booking_data.guest_email:
                email_success = notifier.send_welcome(booking_data)
                
            # Send WhatsApp/SMS
            whatsapp_success = False
            if booking_data.guest_phone:
                whatsapp_success = notifier.send_welcome_whatsapp(booking_data)
            
            if email_success or whatsapp_success:
                # Log execution in automation history
                await self.automation_service.log_rule_execution("Manual Welcome Message", "success")
                msg = []
                if email_success: msg.append(f"email to {booking_data.guest_email}")
                if whatsapp_success: msg.append(f"WhatsApp to {booking_data.guest_phone}")
                return APIResponse(success=True, message=f"Welcome message sent successfully via: {', '.join(msg)}")
            else:
                return APIResponse(success=False, message="Failed to send welcome messages via Email or WhatsApp")
                
        except Exception as e:
            self.logger.error(f"Failed to send manual welcome message: {e}", exc_info=True)
            return APIResponse(success=False, message=str(e))

    async def create_cleaning_task(self, booking_id: str, property_id: str, scheduled_date: Any, crew_id: Optional[int] = None, category_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        try:
            # Ensure reservation_id is passed as a string (the column type is text)
            res_id_val = str(booking_id)

            # Handle date parsing if string
            from datetime import datetime
            scheduled_date_obj = scheduled_date
            if isinstance(scheduled_date, str):
                try:
                    # Try common formats
                    if 'T' in scheduled_date:
                        scheduled_date_obj = datetime.fromisoformat(scheduled_date.replace('Z', ''))
                    else:
                        scheduled_date_obj = datetime.strptime(scheduled_date, "%Y-%m-%d")
                except ValueError:
                    pass

            payload = {
                "reservation_id": res_id_val,
                "property_id": property_id,
                "scheduled_date": scheduled_date_obj,
                "crew_id": crew_id,
                "category_id": category_id
            }
            query = text("""
                INSERT INTO cleaning_tasks (reservation_id, property_id, scheduled_date, crew_id, category_id)
                VALUES (:reservation_id, :property_id, :scheduled_date, :crew_id, :category_id)
                RETURNING *
            """)
            result = await self.session.execute(query, payload)
            row = result.fetchone()
            return dict(row._mapping) if row else None
        except Exception as e:
            self.logger.error(f"Failed to create cleaning task: {e}")
            return None

    async def get_bookings_paginated(
        self, 
        platform: Optional[str], 
        page: int, 
        limit: int, 
        search: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            offset = (page - 1) * limit
            
            # Build WHERE clause
            where_clauses = []
            params = {"limit": limit, "offset": offset}
            
            if platform:
                where_clauses.append("platform = :p")
                params["p"] = platform
            
            if status and status != 'all':
                 # Map frontend status filter to database logic
                 if status == 'confirmed':
                     # Confirmed = explicitly confirmed OR has payment (and not cancelled/failed)
                     where_clauses.append("(COALESCE(LOWER(TRIM(status)), '') = 'confirmed' OR (COALESCE(total_amount, 0) > 0 AND COALESCE(LOWER(TRIM(status)), '') NOT IN ('cancelled', 'failed')))")
                 elif status == 'paid':
                     # Explicitly paid bookings or anything with amount
                     where_clauses.append("COALESCE(total_amount, 0) > 0")
                 elif status == 'failed':
                     where_clauses.append("LOWER(TRIM(status)) = 'failed'")
                 elif status == 'cancelled':
                     where_clauses.append("LOWER(TRIM(status)) = 'cancelled'")
                 elif status == 'pending':
                     # Pending = explicitly pending OR (status is null/empty AND no payment)
                     # BUT MUST NOT have payment (if it has payment, it is confirmed/paid)
                     where_clauses.append("(COALESCE(LOWER(TRIM(status)), 'pending') = 'pending') AND (COALESCE(total_amount, 0) <= 0)")
                 else:
                     where_clauses.append("LOWER(TRIM(status)) = LOWER(TRIM(:status_val))")
                     params["status_val"] = status

            if search:
                where_clauses.append("(guest_name ILIKE :s OR reservation_id::text ILIKE :s OR property_name ILIKE :s)")
                params["s"] = f"%{search}%"

            where_sql = ""
            if where_clauses:
                where_sql = " WHERE " + " AND ".join(where_clauses)

            # Count
            count_query = text(f"SELECT COUNT(*) FROM bookings{where_sql}")
            res_count = await self.session.execute(count_query, params)
            total = res_count.scalar() or 0
            
            # Data
            data_query = text(f"SELECT * FROM bookings{where_sql} ORDER BY check_in_date DESC LIMIT :limit OFFSET :offset")
            
            res_data = await self.session.execute(data_query, params)
            rows = res_data.fetchall()
            
            import math
            total_pages = math.ceil(total / limit) if limit > 0 else 0

            # Fetch tasks for these bookings
            reservation_ids = [row.reservation_id for row in rows]
            tasks_by_reservation = {}
            if reservation_ids:
                tasks_query = text("""
                    SELECT ct.*, cc.name as crew_name, cc.property_id as crew_property_id
                    FROM cleaning_tasks ct
                    LEFT JOIN cleaning_crews cc ON ct.crew_id = cc.id
                    WHERE ct.reservation_id = ANY(:ids)
                """)
                tasks_res = await self.session.execute(tasks_query, {"ids": reservation_ids})
                for t_row in tasks_res:
                    t_dict = dict(t_row._mapping)
                    rid = t_dict['reservation_id']
                    if rid not in tasks_by_reservation:
                        tasks_by_reservation[rid] = []
                    
                    # Format for frontend toVendorTask
                    tasks_by_reservation[rid].append({
                        "task_id": str(t_dict['id']),
                        "scheduled_date": t_dict['scheduled_date'].isoformat() if t_dict['scheduled_date'] else None,
                        "status": t_dict['status'],
                        "crews": {
                            "name": t_dict['crew_name'] or "Unknown Crew",
                            "property_id": t_dict['crew_property_id'] or t_dict['property_id']
                        }
                    })

            bookings_list = []
            for row in rows:
                b_dict = dict(row._mapping)
                # Ensure nights is present and correct
                if b_dict.get('nights') is None or b_dict.get('nights') == 0:
                    ci = b_dict.get('check_in_date')
                    co = b_dict.get('check_out_date')
                    if ci and co:
                        # Use date() to avoid time-of-day issues
                        d1 = ci.date() if hasattr(ci, 'date') else ci
                        d2 = co.date() if hasattr(co, 'date') else co
                        delta = d2 - d1
                        b_dict['nights'] = max(0, delta.days)
                    else:
                        b_dict['nights'] = 0
                
                # Calculate payment_status if not present
                if 'payment_status' not in b_dict:
                    if b_dict.get('total_amount') and b_dict.get('total_amount') > 0:
                        b_dict['payment_status'] = 'Paid'
                    elif b_dict.get('status') == 'failed':
                        b_dict['payment_status'] = 'Failed'
                    else:
                        b_dict['payment_status'] = 'Pending'

                # Fix status column for consistent display
                db_status_raw = b_dict.get('status')
                db_status = db_status_raw.strip().lower() if db_status_raw else 'pending'
                amount = b_dict.get('total_amount') or 0
                
                if db_status == 'cancelled':
                    b_dict['status'] = 'cancelled'
                elif db_status == 'confirmed' or amount > 0:
                    # Anything with payment is at least "confirmed"
                    b_dict['status'] = 'confirmed'
                elif db_status == 'paid':
                    b_dict['status'] = 'paid'
                elif db_status == 'failed':
                    b_dict['status'] = 'failed'
                else:
                    # Default to pending if no payment and no explicit higher status
                    b_dict['status'] = 'pending'

                # Add tasks to booking
                b_dict['tasks'] = tasks_by_reservation.get(b_dict['reservation_id'], [])
                bookings_list.append(b_dict)

            return {
                "bookings": bookings_list,
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages
            }
        except Exception as e:
            self.logger.error(f"Error fetching paginated bookings: {e}")
            return {"bookings": [], "total": 0, "page": page, "limit": limit}

    async def get_booking_by_reservation_id(self, reservation_id: str) -> Optional[Dict[str, Any]]:
        query = text("SELECT * FROM bookings WHERE reservation_id = :rid LIMIT 1")
        result = await self.session.execute(query, {"rid": reservation_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def get_booking_by_property_and_dates(self, property_identifiers: Any, check_in: Any, check_out: Any, guest_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Find a booking by property and dates to prevent duplicates."""
        try:
            # Normalize identifiers to a list of strings
            if isinstance(property_identifiers, (str, int)):
                p_ids = [str(property_identifiers)]
            else:
                p_ids = [str(x) for x in property_identifiers if x]

            if not p_ids:
                return None

            # Handle potential string dates
            if isinstance(check_in, str):
                from datetime import datetime
                check_in = datetime.fromisoformat(check_in.replace('Z', '+00:00'))
            if isinstance(check_out, str):
                from datetime import datetime
                check_out = datetime.fromisoformat(check_out.replace('Z', '+00:00'))

            sql = """
                SELECT * FROM bookings 
                WHERE (property_id = ANY(:p_ids) OR property_name = ANY(:p_ids))
                AND DATE(check_in_date) = DATE(:ci) 
                AND DATE(check_out_date) = DATE(:co)
            """
            params = {
                "p_ids": p_ids,
                "ci": check_in,
                "co": check_out
            }

            # If we have a real guest name, try to match it specifically first
            if guest_name and guest_name != "Unknown Guest":
                specific_sql = sql + " AND guest_name = :gn LIMIT 1"
                specific_params = {**params, "gn": guest_name}
                result = await self.session.execute(text(specific_sql), specific_params)
                row = result.fetchone()
                if row:
                    return dict(row._mapping)

            # Fallback: Match by property and dates only (very likely a duplicate even if guest name is missing/wrong)
            sql += " LIMIT 1"
            result = await self.session.execute(text(sql), params)
            row = result.fetchone()
            return dict(row._mapping) if row else None
        except Exception as e:
            self.logger.error(f"Error checking duplicate by dates: {e}")
            return None

    async def update_guest_phone(self, reservation_id: str, guest_phone: str) -> bool:
        try:
            query = text("UPDATE bookings SET guest_phone = :phone, updated_at = NOW() WHERE reservation_id = :rid")
            await self.session.execute(query, {"phone": guest_phone, "rid": reservation_id})
            return True
        except Exception as e:
            self.logger.error(f"Failed to update guest phone: {e}")
            return False


    async def delete_booking(self, reservation_id: str) -> Dict[str, Any]:
        """Delete booking and all related entities"""
        try:
            # 1. Delete cleaning tasks
            await self.session.execute(
                text("DELETE FROM cleaning_tasks WHERE reservation_id = :rid"),
                {"rid": reservation_id}
            )
            
            # 2. Delete booking services
            await self.session.execute(
                text("DELETE FROM booking_service WHERE booking_id = :rid OR booking_id IN (SELECT id::text FROM bookings WHERE reservation_id = :rid)"),
                {"rid": reservation_id}
            )
            
            # 3. Delete booking
            result = await self.session.execute(
                text("DELETE FROM bookings WHERE reservation_id = :rid RETURNING *"),
                {"rid": reservation_id}
            )
            
            await self.session.commit()
            
            if result.rowcount > 0:
                return {"success": True, "message": f"Booking {reservation_id} deleted successfully"}
            else:
                return {"success": False, "message": f"Booking {reservation_id} not found"}
                
        except Exception as e:
            self.logger.error(f"Error deleting booking {reservation_id}: {e}")
            await self.session.rollback()
            return {"success": False, "message": str(e)}

    async def add_service_to_booking_process(self, reservation_id: str, service_id: int, service_date: str, service_time: str) -> AsyncGenerator[str, None]:
        """
        Add a single service to an existing booking and send notifications.
        Used when adding a task/service from the calendar.
        """
        try:
            notifier = await self._get_notifier()
            
            # 1. Fetch the existing booking
            yield json.dumps({
                "step": "database",
                "status": "in_progress",
                "message": f"Fetching booking {reservation_id}..."
            }, default=str) + "\n"
            
            query = text("SELECT * FROM bookings WHERE reservation_id = :rid")
            result = await self.session.execute(query, {"rid": reservation_id})
            booking_row = result.fetchone()
            
            if not booking_row:
                yield json.dumps({
                    "step": "database",
                    "status": "failed",
                    "message": f"Booking {reservation_id} not found"
                }, default=str) + "\n"
                return
            
            booking_record = dict(booking_row._mapping)
            
            # 2. Add the service record
            yield json.dumps({
                "step": "database",
                "status": "in_progress",
                "message": "Adding service record..."
            }, default=str) + "\n"
            
            # Use reservation_id as the link (booking_id column is now text)
            booking_id_val = reservation_id
            
            # Handle date parsing
            from datetime import datetime
            if isinstance(service_date, str):
                try:
                    service_date_obj = datetime.strptime(service_date, "%Y-%m-%d").date()
                except ValueError:
                    service_date_obj = datetime.fromisoformat(service_date).date()
            else:
                service_date_obj = service_date

            # Handle time parsing
            import datetime as dt_mod
            parsed_time = None
            try:
                parsed_time = datetime.strptime(service_time, "%H:%M").time().replace(tzinfo=dt_mod.timezone.utc)
            except Exception:
                try:
                    parsed_time = datetime.strptime(service_time, "%H:%M:%S").time().replace(tzinfo=dt_mod.timezone.utc)
                except Exception:
                    parsed_time = dt_mod.time(10, 0, tzinfo=dt_mod.timezone.utc)

            # Insert service record
            s_query = text("""
                INSERT INTO booking_service (booking_id, service_id, service_date, time)
                VALUES (:booking_id, :service_id, :service_date, :time)
                RETURNING *
            """)
            
            s_res = await self.session.execute(s_query, {
                "booking_id": booking_id_val,
                "service_id": service_id,
                "service_date": service_date_obj,
                "time": parsed_time
            })
            service_row = s_res.fetchone()

            if not service_row:
                yield json.dumps({
                    "step": "database",
                    "status": "failed",
                    "message": "Failed to create service record"
                }, default=str) + "\n"
                return

            service_record = dict(service_row._mapping)
            await self.session.commit()
            
            yield json.dumps({
                "step": "database",
                "status": "completed",
                "message": "Service record added to booking"
            }, default=str) + "\n"
            
            # 3. Notify Service Provider
            yield json.dumps({
                "step": "service_notification",
                "status": "in_progress",
                "message": "Notifying service provider..."
            }, default=str) + "\n"
            
            service_category = await self.service_category_service.get_category(int(service_id))
            if service_category:
                provider = {
                    "id": service_category.get("id"),
                    "name": service_category.get("category_name", "Service Provider"),
                    "email": service_category.get("email"),
                    "phone": service_category.get("phone")
                }
                
                service_details = {
                    "id": service_record.get("id"),
                    "reservation_id": reservation_id,
                    "service_name": service_category.get("category_name", "Service"),
                    "service_date": service_date,
                    "service_time": service_time,
                    "property_name": booking_record.get("property_name") or "Vacation Rental"
                }
                
                if notifier.notify_service_provider(provider, service_details):
                    yield json.dumps({
                        "step": "service_notification",
                        "status": "completed",
                        "message": f"Notified {provider['name']} via Email"
                    }, default=str) + "\n"
                else:
                    yield json.dumps({
                        "step": "service_notification",
                        "status": "failed",
                        "message": "Failed to send provider notification"
                    }, default=str) + "\n"
            else:
                yield json.dumps({
                    "step": "service_notification",
                    "status": "skipped",
                    "message": "Service category not found"
                }, default=str) + "\n"

            # 4. Notify Guest (Optional, can be added if needed)
            # For now, just finish
            
            yield json.dumps({
                "step": "complete",
                "status": "success",
                "message": "Service added and provider notified successfully"
            }, default=str) + "\n"

        except Exception as e:
            self.logger.error(f"Failed to add service to booking: {e}", exc_info=True)
            yield json.dumps({
                "step": "process",
                "status": "error",
                "message": f"Critical error: {str(e)}"
            }, default=str) + "\n"

    async def add_cleaning_task_process(self, reservation_id: str, scheduled_date: str) -> AsyncGenerator[str, None]:
        """
        Add a cleaning task to an existing booking and notify crew.
        Used when adding a task/service from the calendar.
        """
        try:
            notifier = await self._get_notifier()
            
            # 1. Fetch the existing booking
            yield json.dumps({
                "step": "database",
                "status": "in_progress",
                "message": f"Fetching booking {reservation_id}..."
            }, default=str) + "\n"
            
            query = text("SELECT * FROM bookings WHERE reservation_id = :rid")
            result = await self.session.execute(query, {"rid": reservation_id})
            booking_row = result.fetchone()
            
            if not booking_row:
                yield json.dumps({
                    "step": "database",
                    "status": "failed",
                    "message": f"Booking {reservation_id} not found"
                }, default=str) + "\n"
                return
            
            booking_record = dict(booking_row._mapping)
            
            # 2. Add cleaning task
            yield json.dumps({
                "step": "database",
                "status": "in_progress",
                "message": "Adding cleaning task..."
            }, default=str) + "\n"
            
            crews = await self.crew_service.get_active_crews(role="Cleaning")
            if not crews:
                yield json.dumps({
                    "step": "database",
                    "status": "failed",
                    "message": "No active cleaning crew found"
                }, default=str) + "\n"
                return
            
            crew = crews[0]
            task = await self.create_cleaning_task(
                booking_id=reservation_id,
                property_id=booking_record.get("property_name") or booking_record.get("property_id") or "Unknown",
                scheduled_date=scheduled_date,
                crew_id=crew.get("id"),
                category_id=crew.get("category_id")
            )
            
            if not task:
                yield json.dumps({
                    "step": "database",
                    "status": "failed",
                    "message": "Failed to create cleaning task record"
                }, default=str) + "\n"
                return
            
            await self.session.commit()
            
            yield json.dumps({
                "step": "database",
                "status": "completed",
                "message": "Cleaning task added to booking"
            }, default=str) + "\n"
            
            # 3. Notify Crew
            yield json.dumps({
                "step": "crew_notification",
                "status": "in_progress",
                "message": "Notifying cleaning crew..."
            }, default=str) + "\n"
            
            booking_data = BookingData(
                reservation_id=booking_record['reservation_id'],
                platform=Platform(booking_record['platform']),
                guest_name=booking_record.get('guest_name') or 'Guest',
                guest_email=booking_record.get('guest_email'),
                guest_phone=booking_record.get('guest_phone'),
                check_in_date=booking_record.get('check_in_date'),
                check_out_date=booking_record.get('check_out_date'),
                property_name=booking_record.get('property_name') or 'Your Property',
                property_id=booking_record.get('property_id')
            )
            
            task_for_notify = {
                "id": task.get("id"),
                "booking_id": reservation_id,
                "property_id": booking_record.get("property_name") or "Unknown",
                "scheduled_date": scheduled_date
            }
            
            if notifier.notify_cleaning_task(crew, task_for_notify, booking_data):
                yield json.dumps({
                    "step": "crew_notification",
                    "status": "completed",
                    "message": f"Notified {crew['name']} via Email"
                }, default=str) + "\n"
            else:
                yield json.dumps({
                    "step": "crew_notification",
                    "status": "failed",
                    "message": "Failed to send crew notification"
                }, default=str) + "\n"
                
            yield json.dumps({
                "step": "complete",
                "status": "success",
                "message": "Cleaning task added and crew notified successfully"
            }, default=str) + "\n"

        except Exception as e:
            self.logger.error(f"Failed to add cleaning task: {e}", exc_info=True)
            yield json.dumps({
                "step": "process",
                "status": "error",
                "message": f"Critical error: {str(e)}"
            }, default=str) + "\n"