from googleapiclient.discovery import build
from google.oauth2 import service_account
from ..utils.logger import get_logger
from typing import Optional, Union
from datetime import datetime, timedelta
import json


class GoogleCalendarClient:
    def __init__(
        self,
        credentials_file="config/google_credentials.json",
        calendar_id="sharmaneha4191@gmail.com",
        log_level="INFO",
    ):
        scopes = ["https://www.googleapis.com/auth/calendar"]
        self.creds = service_account.Credentials.from_service_account_file(
            credentials_file, scopes=scopes
        )
        self.service = build("calendar", "v3", credentials=self.creds)
        self.logger = get_logger("google_calendar")
        self.calendar_id = calendar_id

    def add_booking_event(self, booking):
        """Add booking as calendar event."""
        try:
            event = {
                "summary": f"Booking - {booking.guest_name} ({booking.property_name})",
                "start": {"date": booking.check_in_date},
                "end": {"date": booking.check_out_date},
            }
            event = (
                self.service.events()
                .insert(calendarId=self.calendar_id, body=event)
                .execute()
            )

            self.logger.info(
                "Google Calendar booking event created",
                event_id=event["id"],
                reservation_id=booking.reservation_id,
                calendar=self.calendar_id,
            )
            return event["id"]
        except Exception as e:
            self.logger.error(
                "Failed to create booking event",
                error=str(e),
                reservation_id=getattr(booking, "reservation_id", None),
                calendar=self.calendar_id,
            )
            return None

    def block_dates(self, property_id, check_in, check_out):
        """Block property dates on calendar."""
        try:
            event = {
                "summary": f"Blocked - {property_id}",
                "start": {"date": check_in},
                "end": {"date": check_out},
            }
            result = (
                self.service.events()
                .insert(calendarId=self.calendar_id, body=event)
                .execute()
            )

            self.logger.info(
                "Property dates blocked on Google Calendar",
                event_id=result["id"],
                property_id=property_id,
                check_in=check_in,
                check_out=check_out,
                calendar=self.calendar_id,
            )
            return result
        except Exception as e:
            self.logger.error(
                "Failed to block dates",
                error=str(e),
                property_id=property_id,
                check_in=check_in,
                check_out=check_out,
                calendar=self.calendar_id,
            )
            return None

    
    def add_cleaning_event(self, crew: dict, task: Union[dict, str], calendar_id: Optional[str] = None):
        """
        Create a cleaning event and add crew as attendee (if crew.email is present).
        Returns the created event id (string) or None on failure.
        """
        try:
            # Debug logging to see what parameters are actually passed
            self.logger.info("add_cleaning_event called", crew_type=type(crew), crew_value=crew, task_type=type(task), task_value=task, calendar_id=calendar_id)
            
            # Ensure task is a dict
            if isinstance(task, str):
                task = json.loads(task)

            cal_id = calendar_id or self.calendar_id or "sharmaneha4191@gmail.com"
            self.logger.info("Using calendar ID", cal_id=cal_id)
            start = f"{task['scheduled_date']}T09:00:00Z"
            end_dt = datetime.fromisoformat(start.replace("Z", "+00:00")) + timedelta(hours=8)
            end = end_dt.isoformat()

            event = {
                "summary": f"Cleaning - {task['property_id']}",
                "description": f"Cleaning task id: {task['id']} for booking {task.get('booking_id')}",
                "start": {"dateTime": start, "timeZone": "UTC"},
                "end": {"dateTime": end, "timeZone": "UTC"}
            }

            # For service accounts, we cannot invite attendees without domain-wide delegation
            # We'll create the event without attendees and handle notifications separately
            created = self.service.events().insert(
                calendarId=cal_id, body=event
            ).execute()

            self.logger.info(
                "Cleaning event created",
                event_id=created.get("id"),
                task_id=task.get("id")
            )
            return created.get("id")

        except Exception as e:
            self.logger.error(
                "Failed to create cleaning event",
                error=str(e),
                task_id=task.get("id") if isinstance(task, dict) else task
            )
            return None