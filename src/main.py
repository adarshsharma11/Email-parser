"""
Main orchestrator for the Vacation Rental Booking Automation system.
"""
import click
from typing import Optional, List
from datetime import datetime

from .email_reader.gmail_client import GmailClient
from .booking_parser.parser import BookingParser
from .guest_communications.notifier import Notifier
from .calendar_integration.google_calendar_client import GoogleCalendarClient
# Use Supabase client under the FirestoreClient alias to keep interface stable
from .supabase_sync.supabase_client import SupabaseClient as FirestoreClient
from .utils.models import EmailData, BookingData, Platform, ProcessingResult, SyncResult
from .utils.logger import setup_logger, BookingLogger
from config.settings import app_config

dummy_booking = BookingData(
    reservation_id="123",
    platform=Platform.AIRBNB,
    guest_name="Alice",
    guest_phone="+18777804236",
    guest_email="adarshsharma002@gmail.com",
    check_in_date="2025-09-23",
    check_out_date="2025-09-25",
    property_name="Sea View Villa"
)

class BookingAutomation:
    """Main orchestrator for vacation rental booking automation."""
    
    def __init__(self, log_level: str = "INFO", log_file: Optional[str] = None):
        self.logger = setup_logger("booking_automation", log_level, log_file)
        self.booking_logger = BookingLogger(self.logger)
        
        # Initialize components
        self.gmail_client = GmailClient()
        self.booking_parser = BookingParser()
        self.firestore_client = FirestoreClient()
        self.notifier = Notifier()
        self.calendar_client = GoogleCalendarClient()
    
    def process_emails(
        self,
        platform: Optional[Platform] = None,
        since_days: Optional[int] = None,
        limit: Optional[int] = None,
        dry_run: bool = False
    ) -> dict:
        """
        Main method to process emails and sync bookings.
        
        Args:
            platform: Specific platform to process
            since_days: Number of days to look back
            limit: Maximum number of emails to process
            dry_run: If True, don't actually write to the database
            
        Returns:
            Dictionary with processing results
        """
        try:
            self.logger.info("Starting email processing",
                           platform=platform.value if platform else "all",
                           since_days=since_days,
                           limit=limit,
                           dry_run=dry_run)
            
            # Connect to Gmail
            if not self.gmail_client.connect():
                raise Exception("Failed to connect to Gmail")
            
            # Fetch emails
            emails = self.gmail_client.fetch_emails(platform, since_days, limit)
            
            if not emails:
                self.logger.info("No emails found matching criteria")
                return self._get_empty_results()
            
            self.logger.info(f"Found {len(emails)} emails to process")
            
            # Process each email
            successful_bookings = []
            failed_emails = []
            
            for email_data in emails:
                try:
                    # Log email processing
                    platform_name = email_data.platform.value if email_data.platform else "unknown"
                    self.booking_logger.log_email_processed(platform_name, email_data.email_id)
                    
                    # Parse email
                    parse_result = self.booking_parser.parse_email(email_data)
                    
                    if parse_result.success and parse_result.booking_data:
                        self.booking_logger.log_booking_parsed(parse_result.booking_data.to_dict())
                        successful_bookings.append(parse_result.booking_data)
                    else:
                        failed_emails.append({
                            'email_id': email_data.email_id,
                            'error': parse_result.error_message,
                            'platform': platform_name
                        })
                        self.booking_logger.log_error(
                            Exception(parse_result.error_message),
                            f"Email parsing failed: {email_data.email_id}"
                        )
                
                except Exception as e:
                    failed_emails.append({
                        'email_id': email_data.email_id,
                        'error': str(e),
                        'platform': email_data.platform.value if email_data.platform else "unknown"
                    })
                    self.booking_logger.log_error(e, f"Email processing failed: {email_data.email_id}")
            
            # Sync bookings to database
            sync_results = []
            if successful_bookings and not dry_run:
                sync_results = self.firestore_client.sync_bookings(successful_bookings, dry_run)
                
                for i, sync_result in enumerate(sync_results):
                    if sync_result.success:
                        if sync_result.is_new:
                            self.booking_logger.log_new_booking(successful_bookings[i].to_dict())
                            # Send welcome notification
                            notify_success = self.notifier.send_welcome(successful_bookings[i])
                            if not notify_success:
                                self.logger.warning(
                                    "Failed to send welcome notification",
                                    reservation_id=sync_result.reservation_id
                                )
                                self.booking_logger.log_error(
                                    Exception("Failed to send welcome notification"),
                                    f"Notification failed for booking {sync_result.reservation_id}"
                                )
                        else:
                          event_id = self.calendar_client.add_booking_event(dummy_booking)
                        if event_id:
                            self.logger.info(
                                "Google Calendar booking event created",
                                event_id=event_id,
                                reservation_id=dummy_booking.reservation_id
                            )

                        # Block the dates on the calendar
                        block_event = self.calendar_client.block_dates(
                            property_id=dummy_booking.property_name,
                            check_in=dummy_booking.check_in_date,
                            check_out=dummy_booking.check_out_date
                        )
                        if block_event:
                            self.logger.info(
                                "Property dates blocked on Google Calendar",
                                property=successful_bookings[i].property_name,
                                check_in=dummy_booking.check_in_date,
                                check_out=dummy_booking.check_out_date,
                            )
                    else:
                        self.booking_logger.log_error(
                            Exception(sync_result.error_message),
                            f"Database sync failed: {sync_result.reservation_id}"
                        )

                    if block_event:
                        try:
                            # Calculate cleaning date (same as check_out)
                            scheduled_date = successful_bookings[i].check_out_date  
                            # Get active crew for property
                            from src.utils.crew import pick_crew_round_robin
                            crew = pick_crew_round_robin(self.firestore_client, successful_bookings[i].property_name)
                            crew_id = crew.get("id") if crew else None
                            
                            if not crew:
                                self.logger.warning(
                                    "No active crew found for property, creating task without crew assignment",
                                    property=successful_bookings[i].property_name
                                )

                            # Create cleaning task in Supabase
                            task = self.firestore_client.create_cleaning_task(
                                            booking_id=successful_bookings[i].reservation_id,
                                            property_id=dummy_booking.property_name,
                                            scheduled_date=scheduled_date,
                                            crew_id=crew_id
                                    )
                            # Note: Notification temporarily disabled to avoid service account issues
                            # notify_success = True  # Placeholder for notification success
                            notify_success = self.notifier.notify_cleaning_task(crew, task)
                            if not notify_success:
                                self.logger.warning(
                                    "Failed to send cleaning notification",
                                    task_id=task["id"] if task else None
                                )
                                self.booking_logger.log_error(
                                    Exception("Failed to send cleaning notification"),
                                    f"Notification failed for task {task['id'] if task else 'unknown'}"
                                )
                            if crew and task:
                                # Add cleaning event in Google Calendar
                                self.logger.info("About to call add_cleaning_event", crew_type=type(crew), crew_value=crew, task_type=type(task), task_value=task)
                                event_id = self.calendar_client.add_cleaning_event(crew, task)
                                if event_id:
                                    # Update Supabase with calendar event ID
                                    # self.firestore_client.update_cleaning_task(task["id"], {"calendar_event_id": event_id})
                                    self.logger.info(
                                        "Cleaning event scheduled",
                                        event_id=event_id,
                                        task_id=task["id"],
                                        property=successful_bookings[i].property_name
                                    )
                        except Exception as e:
                            self.booking_logger.log_error(e, f"Failed to schedule cleaning for booking {successful_bookings[i].reservation_id}")    
            
            # Mark emails as read (only if not dry run)
            if not dry_run:
                for email_data in emails:
                    self.gmail_client.mark_as_read(email_data.email_id)
            
            # Disconnect from Gmail
            self.gmail_client.disconnect()
            
            # Print summary
            self.booking_logger.print_summary()
            
            return {
                'emails_processed': len(emails),
                'bookings_parsed': len(successful_bookings),
                'new_bookings': len([r for r in sync_results if r.success and r.is_new]),
                'duplicate_bookings': len([r for r in sync_results if r.success and not r.is_new]),
                'failed_emails': failed_emails,
                'sync_errors': [r for r in sync_results if not r.success],
                'dry_run': dry_run
            }
            
        except Exception as e:
            self.logger.error("Error in email processing", error=str(e))
            self.booking_logger.log_error(e, "Main processing error")
            return {'error': str(e)}
    
    def get_booking_stats(self) -> dict:
        """Get booking statistics from the database."""
        try:
            stats = self.firestore_client.get_booking_stats()
            self.logger.info("Retrieved booking statistics", stats=stats)
            return stats
        except Exception as e:
            self.logger.error("Error getting booking statistics", error=str(e))
            return {'error': str(e)}
    
    def _get_empty_results(self) -> dict:
        """Return empty results structure."""
        return {
            'emails_processed': 0,
            'bookings_parsed': 0,
            'new_bookings': 0,
            'duplicate_bookings': 0,
            'failed_emails': [],
            'sync_errors': [],
            'dry_run': False
        }


@click.command()
@click.option('--platform', type=click.Choice(['vrbo', 'airbnb', 'booking', 'plumguide']), 
              help='Specific platform to process')
@click.option('--since-days', type=int, 
              help='Number of days to look back for emails')
@click.option('--limit', type=int, 
              help='Maximum number of emails to process')
@click.option('--dry-run', is_flag=True, 
              help='Run without actually syncing to the database')
@click.option('--log-level', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']), 
              default='INFO', help='Logging level')
@click.option('--log-file', type=str, 
              help='Log file path (optional)')
@click.option('--stats', is_flag=True, 
              help='Show booking statistics only')
def main(platform, since_days, limit, dry_run, log_level, log_file, stats):
    """
    Vacation Rental Booking Automation System.
    
    Automatically extracts booking data from vacation rental platform emails
    and syncs them to Supabase.
    """
    try:
        # Initialize automation system
        automation = BookingAutomation(log_level, log_file)
        
        if stats:
            # Show statistics only
            stats_data = automation.get_booking_stats()
            if 'error' in stats_data:
                click.echo(f"Error: {stats_data['error']}")
                click.get_current_context().exit(1)
            
            click.echo("Booking Statistics:")
            click.echo(f"Total bookings: {stats_data.get('total_bookings', 0)}")
            for platform_name, count in stats_data.get('by_platform', {}).items():
                click.echo(f"  {platform_name}: {count}")
            return 0
        
        # Process emails
        platform_enum = None
        if platform:
            platform_enum = Platform(platform)
        
        results = automation.process_emails(
            platform=platform_enum,
            since_days=since_days,
            limit=limit,
            dry_run=dry_run
        )
        
        if 'error' in results:
            click.echo(f"Error: {results['error']}")
            click.get_current_context().exit(1)
        
        # Print results
        click.echo(f"\nProcessing completed:")
        click.echo(f"  Emails processed: {results['emails_processed']}")
        click.echo(f"  Bookings parsed: {results['bookings_parsed']}")
        click.echo(f"  New bookings: {results['new_bookings']}")
        click.echo(f"  Duplicate bookings: {results['duplicate_bookings']}")
        click.echo(f"  Failed emails: {len(results['failed_emails'])}")
        click.echo(f"  Sync errors: {len(results['sync_errors'])}")
        
        if dry_run:
            click.echo("\n⚠️  DRY RUN MODE - No data was actually synced to database")
        
        return 0
        
    except Exception as e:
        click.echo(f"Fatal error: {str(e)}")
        click.get_current_context().exit(1)


if __name__ == "__main__":
    main()
