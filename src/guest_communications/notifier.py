# guest_communication/notifier.py
from .sms_client import SMSClient
from .email_client import EmailClient
from ..utils.logger import get_logger
from ..utils.models import BookingData

class Notifier:
    def __init__(self):
        self.sms = SMSClient()
        self.email = EmailClient()
        self.logger = get_logger("notifier")

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
                self.email.send(to=booking.guest_email, subject=subject, body=email_body)

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

    def notify_cleaning_task(self, crew: dict, task: dict, include_calendar_invite: bool = True) -> bool:
        """
        crew: {id, name, phone, email}
        task: {id, booking_id, property_id, scheduled_date, ...}
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
                    body = f"Hi {crew_name}<br/><br/>{msg}<br/><br/>Task ID: {task['id']}"
                    
                    self.logger.info("Sending email to crew", 
                                   crew_name=crew_name, 
                                   email=crew_email, 
                                   subject=subject)
                    self.email.send(to=crew_email, subject=subject, body=body)
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
