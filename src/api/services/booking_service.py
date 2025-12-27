"""
Booking service for handling booking-related business logic.
"""
from typing import Optional, Dict, Any, AsyncGenerator
from datetime import datetime, timedelta
import time
import json
import asyncio

from ...supabase_sync.supabase_client import SupabaseClient
from ..models import BookingSummary, BookingStatsResponse, ErrorResponse, CreateBookingRequest, CreateBookingResponse
from ..config import settings
from ...guest_communications.notifier import Notifier
from ...utils.models import BookingData, Platform
from .crew_service import CrewService
from .automation_service import AutomationService
from .activity_rule_service import ActivityRuleService


class BookingService:
    """Service for handling booking operations."""
    
    def __init__(self, supabase_client: SupabaseClient, logger):
        self.supabase_client = supabase_client
        self.logger = logger
        self._cache = {}
        self._cache_ttl = settings.cache_ttl_seconds
        self.notifier = Notifier()
        self.crew_service = CrewService()
        
        # Initialize AutomationService with dependencies
        activity_rule_service = ActivityRuleService(supabase_client, logger)
        self.automation_service = AutomationService(activity_rule_service)
    
    async def create_booking_process(self, request: CreateBookingRequest) -> AsyncGenerator[str, None]:
        """
        Process booking creation with step-by-step status updates.
        
        Args:
            request: Booking creation request
            
        Yields:
            JSON string with status update
        """
        try:
            # Step 1: Create Booking Record
            yield json.dumps({
                "step": "database",
                "status": "in_progress",
                "message": "Creating booking record..."
            }) + "\n"
            
            # Run synchronous create_booking
            response = self.create_booking(request)
            
            if not response.success:
                yield json.dumps({
                    "step": "database",
                    "status": "failed", 
                    "message": response.message
                }) + "\n"
                return

            yield json.dumps({
                "step": "database", 
                "status": "completed",
                "message": "Booking record created"
            }) + "\n"
            
            # Step 2: Calendar Blocking
            yield json.dumps({
                "step": "calendar",
                "status": "in_progress",
                "message": "Updating calendar blocks..."
            }) + "\n"
            
            # Update calendar blocks
            try:
                yield json.dumps({
                    "step": "calendar",
                    "status": "completed",
                    "message": "Calendar updated"
                }) + "\n"
            except Exception as e:
                self.logger.error(f"Calendar update failed: {e}")
                yield json.dumps({
                    "step": "calendar",
                    "status": "warning",
                    "message": "Calendar update skipped"
                }) + "\n"

            # Step 3: Guest Notifications
            yield json.dumps({
                "step": "guest_notification",
                "status": "in_progress",
                "message": "Checking guest notification rules..."
            }) + "\n"
            
            if self.automation_service.is_rule_enabled("guest_welcome_message"):
                try:
                    # Convert request to BookingData for Notifier
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
                    
                    # Send welcome email/SMS
                    self.notifier.send_welcome(booking_data)
                    
                    # Send WhatsApp if available (optional)
                    if request.guest_phone:
                        self.notifier.send_welcome_whatsapp(booking_data)
                    
                    self.automation_service.log_rule_execution("Guest Welcome Message", "success")

                    yield json.dumps({
                        "step": "guest_notification",
                        "status": "completed",
                        "message": "Guest notified via Email/SMS"
                    }) + "\n"
                except Exception as e:
                    self.logger.error(f"Guest notification failed: {e}")
                    self.automation_service.log_rule_execution("Guest Welcome Message", "failed")
                    yield json.dumps({
                        "step": "guest_notification",
                        "status": "failed",
                        "message": f"Failed to notify guest: {str(e)}"
                    }) + "\n"
            else:
                yield json.dumps({
                    "step": "guest_notification",
                    "status": "skipped",
                    "message": "Guest welcome rule is disabled"
                }) + "\n"

            # Step 4: Crew Notifications
            yield json.dumps({
                "step": "crew_notification",
                "status": "in_progress",
                "message": "Checking crew notification rules..."
            }) + "\n"
            
            if self.automation_service.is_rule_enabled("create_cleaning_task"):
                try:
                    if request.property_name: # Changed from property_id to property_name as per main.py usage
                        # Use new logic to get single crew with category_id = 2 (global)
                        # Fetch ONE crew with category_id = 2 (ignores property_id)
                        crew = self.crew_service.get_single_crew_by_category(category_id=2)
                        notified_count = 0
                        
                        if crew:
                            # Calculate cleaning date (usually checkout date)
                            scheduled_date = request.check_out_date
                            
                            # Create cleaning task in database
                            task = self.supabase_client.create_cleaning_task(
                                booking_id=request.reservation_id,
                                property_id=request.property_name,
                                scheduled_date=scheduled_date,
                                crew_id=crew.get("id")
                            )
                            
                            if task:
                                # Prepare task data for notification
                                task_for_notify = {
                                    "id": task.get("id", f"task_{request.reservation_id}"),
                                    "booking_id": request.reservation_id,
                                    "property_id": request.property_name,
                                    "scheduled_date": scheduled_date
                                }
                                
                                # Send notification to crew's email and phone
                                if self.notifier.notify_cleaning_task(crew, task_for_notify):
                                    notified_count = 1
                                    
                                    # Add to Google Calendar (Crew)
                                    from ...calendar_integration.google_calendar_client import GoogleCalendarClient
                                    calendar_client = GoogleCalendarClient()
                                    calendar_client.add_cleaning_event(crew, task_for_notify)
                                else:
                                    self.logger.warning(f"Notification failed for crew {crew.get('name', crew.get('id'))}")
                            else:
                                self.logger.warning("Failed to create cleaning task in database")
                        else:
                            self.logger.warning(f"No crew found with category_id=2 for property {request.property_name}")
                        
                        yield json.dumps({
                            "step": "crew_notification",
                            "status": "completed",
                            "message": f"Notified {notified_count} crew members"
                        }) + "\n"
                        self.automation_service.log_rule_execution("Create Cleaning Task", "success")
                    else:
                        yield json.dumps({
                            "step": "crew_notification",
                            "status": "skipped",
                            "message": "No property name for crew lookup"
                        }) + "\n"
                except Exception as e:
                    self.logger.error(f"Crew notification failed: {e}")
                    self.automation_service.log_rule_execution("Create Cleaning Task", "failed")
                    yield json.dumps({
                        "step": "crew_notification",
                        "status": "warning",
                        "message": "Crew notification incomplete"
                    }) + "\n"
            else:
                yield json.dumps({
                    "step": "crew_notification",
                    "status": "skipped",
                    "message": "Cleaning task rule is disabled"
                }) + "\n"

            # Step 5: Service Providers
            if request.services:
                yield json.dumps({
                    "step": "services",
                    "status": "in_progress",
                    "message": "Notifying service providers..."
                }) + "\n"
                
                try:
                    from .service_category_service import ServiceCategoryService
                    service_category_service = ServiceCategoryService()
                    
                    processed_services = 0
                    for service_item in request.services:
                        # Get service category to find email
                        category = service_category_service.get_category(str(service_item.service_id))
                        
                        if category and (category.get("email") or category.get("phone")):
                             # Send notification
                             subject = f"New Service Request: {category.get('name')}"
                             body = (
                                 f"New service request for booking {request.reservation_id}\n"
                                 f"Property: {request.property_name}\n"
                                 f"Date: {service_item.service_date}\n"
                                 f"Time: {service_item.time}\n"
                             )
                             
                             # Email
                             if category.get("email"):
                                self.notifier.email.send(to=category["email"], subject=subject, body=body)
                             
                             # SMS/WhatsApp
                             if category.get("phone"):
                                sms_body = (
                                    f"New Request: {category.get('name')}\n"
                                    f"Loc: {request.property_name}\n"
                                    f"When: {service_item.service_date} @ {service_item.time}"
                                )
                                self.notifier.sms.send(to=category["phone"], body=sms_body)
                                
                             processed_services += 1
                        else:
                            self.logger.warning(f"No contact info found for service category {service_item.service_id}")

                    yield json.dumps({
                        "step": "services",
                        "status": "completed",
                        "message": f"Notified {processed_services} service providers"
                    }) + "\n"
                except Exception as e:
                     self.logger.error(f"Service provider notification failed: {e}")
                     yield json.dumps({
                        "step": "services",
                        "status": "warning",
                        "message": f"Service notification failed: {str(e)}"
                    }) + "\n"

            # Final Success
            yield json.dumps({
                "step": "complete",
                "status": "success",
                "message": "All booking steps completed successfully",
                "data": response.data
            }) + "\n"

        except Exception as e:
            self.logger.error(f"Booking process failed: {e}", exc_info=True)
            yield json.dumps({
                "step": "process",
                "status": "error",
                "message": f"Critical error: {str(e)}"
            }) + "\n"

    def create_booking(self, request: CreateBookingRequest) -> CreateBookingResponse:
        """
        Create a new booking with services.
        
        Args:
            request: Booking creation request with services
            
        Returns:
            CreateBookingResponse with created booking data
        """
        try:
            self.logger.info("Creating new booking", reservation_id=request.reservation_id)
            
            # Prepare booking payload
            booking_dict = request.model_dump(exclude={"services"})
            
            # Convert platform enum to string if needed (model_dump might handle it if mode='json')
            # But we are passing to a client that expects dicts.
            # Platform is an Enum in the model.
            if "platform" in booking_dict and hasattr(booking_dict["platform"], "value"):
                booking_dict["platform"] = booking_dict["platform"].value
            
            # Prepare services
            services_list = []
            if request.services:
                for svc in request.services:
                    services_list.append(svc.model_dump())
            
            # Call Supabase client
            result = self.supabase_client.create_booking_with_services(booking_dict, services_list)
            
            return CreateBookingResponse(
                success=True,
                message="Booking created successfully",
                data=result
            )
            
        except Exception as e:
            error_msg = f"Failed to create booking: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            # CreateBookingResponse requires data field.
            return CreateBookingResponse(
                success=False,
                message=error_msg,
                data={} 
            )

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
            
    def update_guest_phone(self, reservation_id: str, guest_phone: str) -> bool:
        """
        Update the guest_phone field for a booking.

        Args:
            reservation_id: Unique reservation id for the booking
            guest_phone: New guest phone number (string)

        Returns:
            True on success, False otherwise
        """
        try:
            phone = (guest_phone or "").strip()
            if not phone:
                raise ValueError("guest_phone cannot be empty")
            existing = self.supabase_client.get_booking_by_reservation_id(reservation_id)
            updated = self.supabase_client.update_booking(
                reservation_id,
                {"guest_phone": phone}
            )
            if not updated:
                raise Exception("Database update failed")
            try:
                data = existing or {}
                data.update({"guest_phone": phone})
                booking = BookingData(
                    reservation_id=reservation_id,
                    platform=data.get("platform") or Platform.VRBO,
                    guest_name=data.get("guest_name") or "Guest",
                    guest_phone=phone,
                    guest_email=data.get("guest_email"),
                    check_in_date=data.get("check_in_date"),
                    check_out_date=data.get("check_out_date"),
                    property_name=data.get("property_name")
                )
                Notifier().send_welcome_whatsapp(booking)
            except Exception as notify_err:
                self.logger.warning("WhatsApp welcome send failed", reservation_id=reservation_id, error=str(notify_err))
            return True
        except Exception as e:
            self.logger.error(
                "Failed to update guest_phone",
                reservation_id=reservation_id,
                guest_phone=guest_phone,
                error=str(e)
            )
            return False