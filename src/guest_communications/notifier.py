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

    def notify_cleaning_task(self, crew: dict, task: dict, include_calendar_invite: bool = True) -> bool:
        """
        crew: {id, name, phone, email}
        task: {id, booking_id, property_id, scheduled_date, ...}
        """
        try:
            msg = f"Cleaning task scheduled for {task['property_id']} on {task['scheduled_date']}. Please confirm."
            # Send SMS if phone exists
            if crew.get("phone"):
                self.sms.send(to=crew["phone"], body=msg)

            # Send email if crew email exists
            if crew.get("email"):
                subject = f"Cleaning Assignment – {task['property_id']} on {task['scheduled_date']}"
                body = f"Hi {crew.get('name','')}<br/><br/>{msg}<br/><br/>Task ID: {task['id']}"
                self.email.send(to=crew["email"], subject=subject, body=body)

            # Optionally add calendar event for crew via calendar service
            # if include_calendar_invite and self.calendar and crew.get("email"):
            #     event_id = self.calendar.add_cleaning_event(crew, task)
            self.logger.info("Cleaning notification sent", task_id=task['id'], crew=crew.get('name'))
            return True
        except Exception as e:
            self.logger.error("Failed to notify crew", error=str(e), task_id=task.get('id'))
            return False