# guest_communication/notifier.py
from .sms_client import SMSClient
from .email_client import EmailClient
from ..utils.logger import get_logger
from ..utils.models import BookingData
import os

class Notifier:
    def __init__(self, email_credentials: dict = None):
        self.sms = SMSClient()
        self.email = EmailClient()
        self.logger = get_logger("notifier")
        self.email_credentials = email_credentials

    def send_welcome(self, booking: BookingData) -> bool:
        """Send both email and SMS welcome messages."""
        try:
            subject = f"Booking Confirmation - {booking.property_name}"
            email_body = f"""
            Hi {booking.guest_name},

            Your booking at {booking.property_name} is confirmed!
            Check-in: {booking.check_in_date}
            Check-out: {booking.check_out_date}

            See more at: https://our-website.com/bookings/{booking.reservation_id}
            """

            sms_body = (
                f"Hi {booking.guest_name}, your booking at {booking.property_name} "
                f"is confirmed! Check-in {booking.check_in_date}, "
                f"Checkout {booking.check_out_date}. Visit our site for details."
            )

            if booking.guest_email:
                self.email.send(to=booking.guest_email, subject=subject, body=email_body, credentials=self.email_credentials)

            if booking.guest_phone:
                self.sms.send(to=booking.guest_phone, body=sms_body)

            self.logger.info("welcome_sent", reservation_id=booking.reservation_id)
            return True
        except Exception as e:
            self.logger.error("welcome_failed", error=str(e), reservation_id=booking.reservation_id)
            return False

    def send_welcome_whatsapp(self, booking: BookingData) -> bool:
        try:
            body = (
                f"Hi {booking.guest_name} 👋\n\n"
                f"Your booking at *{booking.property_name}* is confirmed! 🎉\n\n"
                f"🛎 *Check-in:* {booking.check_in_date}\n"
                f"🚪 *Check-out:* {booking.check_out_date}\n\n"
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
                    
                    guest_details_html = ""
                    if booking:
                        guest_details_html = f"""
                        <b>Guest Details:</b><br/>
                        Name: {booking.guest_name}<br/>
                        Phone: {booking.guest_phone or 'N/A'}<br/>
                        Email: {booking.guest_email or 'N/A'}<br/>
                        Check-in: {booking.check_in_date}<br/>
                        Check-out: {booking.check_out_date}<br/><br/>
                        """

                    body = f"Hi {crew_name}<br/><br/>{msg}<br/><br/>{guest_details_html}"
                    
                    self.logger.info("Sending email to crew", 
                                   crew_name=crew_name, 
                                   email=crew_email, 
                                   subject=subject)
                    self.email.send(to=crew_email, subject=subject, body=body, html=True, credentials=self.email_credentials)
                    email_success = True
                    self.logger.info("Email sent successfully", crew_name=crew_name, email=crew_email)
                except Exception as e:
                    self.logger.error("Email failed", 
                                    crew_name=crew_name, 
                                    email=crew_email, 
                                    error=str(e),
                                    smtp_server=self.email.smtp_server,
                                    smtp_port=self.email.smtp_port,
                                    has_smtp_user=bool(self.email.username))
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
            msg = f"New service '{service_name}' has been assigned to you for {property_name} on {service_date} at {service_time}."
            
            body = f"""
            Hi {provider_name},<br/><br/>
            {msg}<br/><br/>
            <b>Reservation ID:</b> {reservation_id}<br/>
            <b>Service:</b> {service_name}<br/>
            <b>Date:</b> {service_date}<br/>
            <b>Time:</b> {service_time}<br/>
            <b>Property:</b> {property_name}<br/><br/>
            Please confirm your availability.
            """

            self.logger.info("Notifying service provider", 
                           provider_name=provider_name, 
                           service_name=service_name,
                           reservation_id=reservation_id)

            email_success = False
            if provider_email:
                try:
                    self.email.send(to=provider_email, subject=subject, body=body, html=True, credentials=self.email_credentials)
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
