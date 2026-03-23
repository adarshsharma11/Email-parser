# guest_communication/notifier.py
from .sms_client import SMSClient
from .sendgrid_client import SendGridClient
from .email_templates import EmailTemplates
from ..utils.logger import get_logger
from ..utils.models import BookingData
import os

class Notifier:
    def __init__(self, email_credentials: dict = None):
        self.sms = SMSClient()
        self.email = SendGridClient()
        self.logger = get_logger("notifier")
        self.email_credentials = email_credentials

    def send_welcome(self, booking: BookingData) -> bool:
        """Send both email and SMS welcome messages."""
        try:
            subject = f"Your Booking is Confirmed! 🏠 {booking.property_name}"
            
            # Format dates and append fixed times
            check_in_str = booking.check_in_date.strftime('%Y-%m-%d') if hasattr(booking.check_in_date, 'strftime') else str(booking.check_in_date)
            check_out_str = booking.check_out_date.strftime('%Y-%m-%d') if hasattr(booking.check_out_date, 'strftime') else str(booking.check_out_date)
            
            check_in_display = f"{check_in_str} at 11:00 AM"
            check_out_display = f"{check_out_str} at 3:00 PM"

            # Use beautiful SendGrid template
            email_body = EmailTemplates.get_welcome_template(
                guest_name=booking.guest_name,
                property_name=booking.property_name or "Your Property",
                check_in=check_in_display,
                check_out=check_out_display,
                reservation_id=booking.reservation_id
            )

            sms_body = (
                f"Hi {booking.guest_name}, your booking at {booking.property_name} "
                f"is confirmed! Check-in {check_in_display}, "
                f"Checkout {check_out_display}. Visit our site for details."
            )

            email_sent = False
            if booking.guest_email:
                try:
                    # Using SendGrid client
                    self.email.send(to=booking.guest_email, subject=subject, body=email_body, html=True)
                    email_sent = True
                    self.logger.info("welcome_email_sent", reservation_id=booking.reservation_id, email=booking.guest_email)
                except Exception as e:
                    self.logger.error("welcome_email_failed", error=str(e), reservation_id=booking.reservation_id)
            else:
                self.logger.warning("welcome_email_skipped_no_email", reservation_id=booking.reservation_id)

            sms_sent = False
            if booking.guest_phone:
                try:
                    self.sms.send(to=booking.guest_phone, body=sms_body)
                    sms_sent = True
                    self.logger.info("welcome_sms_sent", reservation_id=booking.reservation_id, phone=booking.guest_phone)
                except Exception as e:
                    self.logger.error("welcome_sms_failed", error=str(e), reservation_id=booking.reservation_id)
            else:
                self.logger.warning("welcome_sms_skipped_no_phone", reservation_id=booking.reservation_id)

            return email_sent or sms_sent
        except Exception as e:
            self.logger.error("welcome_failed", error=str(e), reservation_id=booking.reservation_id)
            return False

    def send_welcome_whatsapp(self, booking: BookingData) -> bool:
        try:
            # Format dates and append fixed times
            check_in_str = booking.check_in_date.strftime('%Y-%m-%d') if hasattr(booking.check_in_date, 'strftime') else str(booking.check_in_date)
            check_out_str = booking.check_out_date.strftime('%Y-%m-%d') if hasattr(booking.check_out_date, 'strftime') else str(booking.check_out_date)
            
            check_in_display = f"{check_in_str} at 11:00 AM"
            check_out_display = f"{check_out_str} at 3:00 PM"

            body = (
                f"Hi {booking.guest_name} 👋\n\n"
                f"Your booking at *{booking.property_name}* is confirmed! 🎉\n\n"
                f"🛎 *Check-in:* {check_in_display}\n"
                f"🚪 *Check-out:* {check_out_display}\n\n"
                f"If you need anything before your stay, just reply to this message.\n"
                f"We look forward to hosting you! 😊"
            )
            if booking.guest_phone:
                self.sms.send_whatsapp(to=booking.guest_phone, body=body)
            self.logger.info("welcome_whatsapp_sent", reservation_id=booking.reservation_id)
            return True
        except Exception as e:
            self.logger.error("welcome_whatsapp_failed", error=str(e), reservation_id=booking.reservation_id)
            return False

    def notify_cleaning_task(self, crew: dict, task: dict, booking: BookingData = None, include_calendar_invite: bool = True) -> bool:
        """
        crew: {id, name, phone, email}
        task: {id, booking_id, property_id, scheduled_date, ...}
        booking: Optional BookingData for guest details
        """
        try:
            msg = f"Cleaning task scheduled for {task['property_id']} on {task['scheduled_date']}. Please confirm."
            
            # Debug: Log crew contact info
            crew_name = crew.get("name", "Unknown")
            crew_email = crew.get("email")
            crew_phone = crew.get("phone")
            
            self.logger.info("Starting crew notification", 
                           task_id=task.get('id'), 
                           crew_name=crew_name,
                           crew_email=crew_email, 
                           crew_phone=crew_phone,
                           has_email=bool(crew_email),
                           has_phone=bool(crew_phone))

            # Send SMS if phone exists
            sms_success = False
            if crew_phone:
                try:
                    self.logger.info("Sending SMS to crew", crew_name=crew_name, phone=crew_phone)
                    self.sms.send(to=crew_phone, body=msg)
                    sms_success = True
                    self.logger.info("SMS sent successfully", crew_name=crew_name)
                except Exception as e:
                    self.logger.error("SMS failed", crew_name=crew_name, phone=crew_phone, error=str(e))
                    sms_success = False

            # Send email if crew email exists
            email_success = False
            if crew_email:
                try:
                    subject = f"Cleaning Assignment – {task['property_id']} on {task['scheduled_date']}"
                    
                    guest_details_str = ""
                    if booking:
                        # Format dates and append fixed times
                        check_in_str = booking.check_in_date.strftime('%Y-%m-%d') if hasattr(booking.check_in_date, 'strftime') else str(booking.check_in_date)
                        check_out_str = booking.check_out_date.strftime('%Y-%m-%d') if hasattr(booking.check_out_date, 'strftime') else str(booking.check_out_date)
                        
                        check_in_display = f"{check_in_str} at 11:00 AM"
                        check_out_display = f"{check_out_str} at 3:00 PM"

                        guest_details_str = f"""
                        <strong>Guest:</strong> {booking.guest_name}<br/>
                        <strong>Check-in:</strong> {check_in_display}<br/>
                        <strong>Check-out:</strong> {check_out_display}<br/>
                        """

                    # Using SendGrid template
                    body = EmailTemplates.get_cleaning_template(
                        crew_name=crew_name,
                        property_name=task['property_id'],
                        scheduled_date=str(task['scheduled_date']),
                        task_id=str(task.get('id', '')),
                        guest_details=guest_details_str
                    )
                    
                    self.logger.info("Sending email to crew via SendGrid", 
                                   crew_name=crew_name, 
                                   email=crew_email, 
                                   subject=subject)
                    self.email.send(to=crew_email, subject=subject, body=body, html=True)
                    email_success = True
                    self.logger.info("Email sent successfully", crew_name=crew_name, email=crew_email)
                except Exception as e:
                    self.logger.error("Email failed", 
                                    crew_name=crew_name, 
                                    email=crew_email, 
                                    error=str(e))
                    email_success = False

            # Report overall success
            if sms_success or email_success:
                self.logger.info("Cleaning notification sent successfully", 
                               task_id=task['id'], 
                               crew_name=crew_name,
                               sms_success=sms_success,
                               email_success=email_success)
                return True
            else:
                self.logger.error("Failed to send any notifications", 
                                task_id=task['id'], 
                                crew_name=crew_name,
                                sms_success=sms_success,
                                email_success=email_success)
                return False
                
        except Exception as e:
            self.logger.error("Critical error in notify_cleaning_task", 
                            error=str(e), 
                            task_id=task.get('id'),
                            crew_name=crew.get('name'),
                            error_type=type(e).__name__)
            return False

    def notify_service_provider(self, provider: dict, service_details: dict) -> bool:
        """
        Notify a service provider about a newly assigned service.
        provider: {id, name, email, phone}
        service_details: {reservation_id, service_name, service_date, service_time, property_name}
        """
        try:
            provider_name = provider.get("name", "Service Provider")
            provider_email = provider.get("email")
            provider_phone = provider.get("phone")
            
            reservation_id = service_details.get("reservation_id")
            service_name = service_details.get("service_name", "Service")
            service_date = service_details.get("service_date")
            service_time = service_details.get("service_time")
            property_name = service_details.get("property_name", "Property")

            subject = f"New Service Assignment: {service_name} at {property_name}"
            
            # Using new service template
            body = EmailTemplates.get_service_template(
                provider_name=provider_name,
                service_name=service_name,
                property_name=property_name,
                service_date=str(service_date),
                service_time=str(service_time),
                task_id=str(service_details.get("id", reservation_id)),
                reservation_id=reservation_id
            )

            self.logger.info("Notifying service provider", 
                           provider_name=provider_name, 
                           service_name=service_name,
                           reservation_id=reservation_id)

            email_success = False
            if provider_email:
                try:
                    self.email.send(to=provider_email, subject=subject, body=body, html=True)
                    email_success = True
                    self.logger.info("Service provider email sent successfully", email=provider_email)
                except Exception as e:
                    self.logger.error("Service provider email failed", email=provider_email, error=str(e))

            sms_success = False
            if provider_phone:
                try:
                    sms_body = f"Hi {provider_name}, new service '{service_name}' assigned for {property_name} on {service_date} at {service_time}."
                    self.sms.send(to=provider_phone, body=sms_body)
                    sms_success = True
                    self.logger.info("Service provider SMS sent successfully", phone=provider_phone)
                except Exception as e:
                    self.logger.error("Service provider SMS failed", phone=provider_phone, error=str(e))

            return email_success or sms_success

        except Exception as e:
            self.logger.error("Error in notify_service_provider", error=str(e))
            return False
