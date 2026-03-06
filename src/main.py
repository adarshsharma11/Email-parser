"""
Main orchestrator for the Vacation Rental Booking Automation system.
"""
import sys
import click
import os
from typing import Optional, List
from datetime import datetime, timedelta

from .email_reader.gmail_client import GmailClient
from .booking_parser.parser import BookingParser
from .guest_communications.notifier import Notifier
from .calendar_integration.google_calendar_client import GoogleCalendarClient
# UseSupabaseClient alias removed, we use AsyncSession from project
from .utils.models import EmailData, BookingData, Platform, ProcessingResult, SyncResult
from .utils.logger import setup_logger, BookingLogger
from config.settings import app_config
from .api.services.user_service import UserService
from .api.services.booking_service import BookingService
from .api.services.property_service import PropertyService
from .api.app import create_app
from .db.psql_client import psql_client
import asyncio

# Create FastAPI app instance for uvicorn
app = create_app()

dummy_booking = BookingData(
    reservation_id="123",
    platform=Platform.AIRBNB,
    guest_name="Alice",
    guest_phone="+18777804236",
    guest_email="adarshsharma002@gmail.com",
    check_in_date=datetime(2025, 9, 23),
    check_out_date=datetime(2025, 9, 25),
    property_name="Sea View Villa"
)

class BookingAutomation:
    """Main orchestrator for vacation rental booking automation using PostgreSQL."""
    
    def __init__(self, log_level: str = "INFO", log_file: Optional[str] = None):
        self.logger = setup_logger("booking_automation", log_level, log_file)
        self.booking_logger = BookingLogger(self.logger)
        
        # Initialize components
        self.gmail_client = GmailClient()
        self.booking_parser = BookingParser()
        self.notifier = None  # Initialized asynchronously in process_emails
        self.calendar_client = GoogleCalendarClient()
    
    async def _get_notifier(self, session, user_service) -> Notifier:
        """Get or initialize notifier with dynamic credentials if not development."""
        if self.notifier:
            return self.notifier
            
        credentials = None
        app_env = os.getenv("APP_ENV", "development")
        
        if app_env != "development":
            try:
                from sqlalchemy import text
                from config.settings import app_config
                
                # Try to fetch from user_credentials with platform='crdetails'
                table_name = app_config.users_collection
                query = text(f"SELECT email, password FROM {table_name} WHERE platform = 'crdetails' LIMIT 1")
                result = await session.execute(query)
                row = result.fetchone()
                
                # If no 'crdetails' platform, try fetching the first available from user_credentials
                if not row:
                    self.logger.info(f"No 'crdetails' platform in {table_name}, trying first available row")
                    query = text(f"SELECT email, password FROM {table_name} LIMIT 1")
                    result = await session.execute(query)
                    row = result.fetchone()

                # If still no row, maybe 'crdetails' is the table name itself?
                if not row:
                    try:
                        self.logger.info("Trying to fetch from 'crdetails' table directly")
                        query = text("SELECT email, password FROM crdetails LIMIT 1")
                        result = await session.execute(query)
                        row = result.fetchone()
                    except Exception:
                        self.logger.info("'crdetails' table does not exist")

                if row:
                    row_dict = dict(row._mapping)
                    cred_email = row_dict.get("email")
                    cred_password = row_dict.get("password")
                    
                    if cred_email and cred_password:
                        # Decrypt password using UserService
                        decrypted_password = user_service.decrypt(cred_password)
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

    async def process_emails(
        self,
        platform: Optional[Platform] = None,
        since_days: Optional[int] = 1,
        limit: Optional[int] = None,
        mailbox: str = "INBOX",
        text_query: Optional[str] = None,
        dry_run: bool = False
    ) -> dict:
        """
        Main method to process emails and sync bookings.
        """
        try:
            # Enforce 24 hours (1 day) if not specified
            since_days_effective = since_days if since_days is not None else 1
            
            self.logger.info("Starting email processing",
                           platform=platform.value if platform else "all",
                           since_days=since_days_effective,
                           limit=limit,
                           dry_run=dry_run)
            
            async with psql_client.async_session_factory() as session:
                user_service = UserService(session)
                booking_service = BookingService(session, self.logger)
                property_service = PropertyService(session)
                
                # Get dynamic notifier
                notifier = await self._get_notifier(session, user_service)
                
                # Use only active credentials from DB
                active_users = await user_service.list_active_users()
                
                # Fallback to .env credentials if no DB users found
                if not active_users:
                    from config.settings import gmail_config
                    if gmail_config.email and gmail_config.password:
                        self.logger.info("No active users in DB, using .env credentials")
                        try:
                            # Encrypt password to match expected format
                            enc_pwd = user_service.encrypt(gmail_config.password)
                            active_users = [{
                                "email": gmail_config.email, 
                                "password": enc_pwd
                            }]
                        except Exception as e:
                            self.logger.warning("Failed to encrypt .env password", error=str(e))
                
                if not active_users:
                    return self._get_empty_results()

                emails: List[EmailData] = []
                for u in active_users:
                    email_addr = u.get("email")
                    enc = u.get("password")
                    if not email_addr or not enc:
                        continue
                    try:
                        pwd = user_service.decrypt(enc)
                    except Exception:
                        try:
                            await user_service.update_status(email_addr, "inactive")
                        except Exception:
                            pass
                        continue
                    client = GmailClient()
                    if not client.connect_with_credentials(email_addr, pwd):
                        try:
                            await user_service.update_status(email_addr, "inactive")
                        except Exception:
                            pass
                        continue
                    
                    fetched = client.fetch_emails(platform, since_days_effective, limit, mailbox=mailbox, text_query=text_query)
                    emails.extend(fetched or [])
                    client.disconnect()
                
                if not emails:
                    self.logger.info("No emails found matching criteria")
                    return self._get_empty_results()
                
                self.logger.info(f"Found {len(emails)} emails to process")
                
                successful_bookings = []
                failed_emails = []
                parsed_details = []
                
                for email_data in emails:
                    try:
                        platform_name = email_data.platform.value if email_data.platform else "unknown"
                        self.booking_logger.log_email_processed(platform_name, email_data.email_id)
                        
                        parse_result = self.booking_parser.parse_email(email_data)
                        
                        if parse_result.success and parse_result.booking_data:
                            bd = parse_result.booking_data
                            self.logger.info(f"Successfully parsed booking: {bd.reservation_id} for guest {bd.guest_name} at property {bd.property_name}")
                            self.booking_logger.log_booking_parsed(bd.to_dict())
                            
                            # Real bookings filter
                            booking_type = (bd.raw_data or {}).get("booking_type")
                            if booking_type in ("inquiry", "other"):
                                failed_emails.append({'email_id': email_data.email_id, 'error': "Skipped inquiry", 'platform': platform_name})
                                continue
                                
                            # Basic validation - require reservation_id and at least one date
                            if not bd.reservation_id:
                                failed_emails.append({'email_id': email_data.email_id, 'error': "Missing reservation_id", 'platform': platform_name})
                                continue
                            
                            # Allow if we have at least check-in OR check-out date, or use booking_date as fallback
                            if not (bd.check_in_date or bd.check_out_date or bd.booking_date):
                                failed_emails.append({'email_id': email_data.email_id, 'error': "Missing dates (check_in, check_out, or booking_date)", 'platform': platform_name})
                                continue
                            
                            # Fallback: if check_in/check_out missing but booking_date exists, use booking_date
                            if not bd.check_in_date and bd.booking_date:
                                bd.check_in_date = bd.booking_date
                            if not bd.check_out_date and bd.booking_date:
                                # Set checkout to day after booking date as fallback
                                bd.check_out_date = bd.booking_date + timedelta(days=1)
                                
                            successful_bookings.append(bd)
                            parsed_details.append({
                                'email_id': bd.email_id,
                                'platform': bd.platform.value if bd.platform else None,
                                'reservation_id': bd.reservation_id,
                                'guest_name': bd.guest_name,
                                'property_name': bd.property_name,
                                'nights': bd.nights
                            })
                        else:
                            failed_emails.append({'email_id': email_data.email_id, 'error': parse_result.error_message, 'platform': platform_name})
                    except Exception as e:
                        failed_emails.append({'email_id': email_data.email_id, 'error': str(e), 'platform': "error"})
                
                # Sync to PostgreSQL
                new_count = 0
                processed_in_session = set() # To track duplicates in the current batch
                if successful_bookings:
                    for b in successful_bookings:
                        try:
                            # Session-level duplicate check (Property + Dates)
                            session_key = f"{b.property_id}_{b.check_in_date}_{b.check_out_date}"
                            if b.property_id and b.check_in_date and b.check_out_date:
                                if session_key in processed_in_session:
                                    self.logger.info(f"Duplicate booking found in current batch for property {b.property_id}, skipping.")
                                    continue
                                processed_in_session.add(session_key)

                            from .api.models import CreateBookingRequest
                            req = CreateBookingRequest(
                                reservation_id=b.reservation_id,
                                platform=b.platform.value if hasattr(b.platform, "value") else b.platform,
                                guest_name=b.guest_name,
                                guest_phone=b.guest_phone,
                                guest_email=b.guest_email,
                                check_in_date=b.check_in_date,
                                check_out_date=b.check_out_date,
                                property_id=b.property_id,
                                property_name=b.property_name,
                                nights=b.nights,
                                number_of_guests=b.number_of_guests,
                                total_amount=b.total_amount,
                                currency=b.currency,
                                booking_date=b.booking_date,
                                email_id=b.email_id,
                                raw_data=b.raw_data
                            )
                            # Check for existing booking (By ID OR by Property+Dates)
                            existing = await booking_service.get_booking_by_reservation_id(b.reservation_id)
                            
                            if not existing and b.property_id and b.check_in_date and b.check_out_date:
                                existing = await booking_service.get_booking_by_property_and_dates(
                                    b.property_id, b.check_in_date, b.check_out_date
                                )
                                if existing:
                                    self.logger.info(f"Duplicate booking found by dates for property {b.property_id}, skipping.")

                            if not existing:
                                new_count += 1
                                if not dry_run:
                                    res = await booking_service.create_booking(req)
                                    if res.success:
                                        self.booking_logger.log_new_booking(b.to_dict())
                                        
                                        # Step 1: Guest Welcome Email (with rule check)
                                        if await booking_service.automation_service.is_rule_enabled("guest_welcome_message"):
                                            notifier.send_welcome(b)
                                            await booking_service.automation_service.log_rule_execution("Guest Welcome Message", "success")
                                        else:
                                            self.logger.info("Skipping welcome email (rule disabled)")

                                        # Step 2: Cleaning Crew Notification (with rule check)
                                        if await booking_service.automation_service.is_rule_enabled("create_cleaning_task"):
                                            # Find a crew member for cleaning
                                            crew = await booking_service.crew_service.get_single_crew_by_category(category_id=2) # 2 is usually cleaning
                                            if crew:
                                                scheduled_date = b.check_out_date
                                                task = await booking_service.create_cleaning_task(
                                                    booking_id=b.reservation_id,
                                                    property_id=b.property_name or b.property_id or "Unknown",
                                                    scheduled_date=scheduled_date,
                                                    crew_id=crew.get("id")
                                                )
                                                
                                                if task:
                                                    task_for_notify = {
                                                        "id": task.get("id", f"task_{b.reservation_id}"),
                                                        "booking_id": b.reservation_id,
                                                        "property_id": b.property_name or b.property_id or "Unknown",
                                                        "scheduled_date": scheduled_date
                                                    }
                                                    
                                                    if notifier.notify_cleaning_task(crew, task_for_notify, b):
                                                        self.logger.info(f"Cleaning crew notified for booking {b.reservation_id}")
                                                        await booking_service.automation_service.log_rule_execution("Create Cleaning Task", "success")
                                            else:
                                                self.logger.warning("No active cleaning crew found for notification")
                                        else:
                                            self.logger.info("Skipping cleaning notification (rule disabled)")

                                        await booking_service.automation_service.log_rule_execution("New Booking Processed", "success")
                                else:
                                    # Still count for stats in dry run
                                    self.booking_logger.stats['new_bookings'] += 1
                            elif not dry_run:
                                # Update existing if needed
                                await booking_service.create_booking(req)
                                
                        except Exception as e:
                            self.logger.error(f"Sync failed for {b.reservation_id}: {e}")
                    
                    # COMMIT CHANGES TO POSTGRESQL
                    if not dry_run:
                        await session.commit()
                        self.logger.info("Database sync committed successfully")

                self.booking_logger.print_summary()
                return {
                    'emails_processed': len(emails),
                    'bookings_parsed': len(successful_bookings),
                    'new_bookings': new_count,
                    'failed_emails': failed_emails,
                    'parsed_bookings': parsed_details
                }
                
        except Exception as e:
            self.logger.error("Error in email processing", error=str(e))
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
@click.option('--since-days', type=int, default=1,
              help='Number of days to look back for emails (default: 1 for 24 hours)')
@click.option('--limit', type=int, 
              help='Maximum number of emails to process')
@click.option('--mailbox', default='INBOX', help='Gmail mailbox to process')
@click.option('--text-query', default=None, help='Additional text query for email search')
@click.option('--dry-run', is_flag=True, 
              help='Run without actually syncing to the database')
@click.option('--log-level', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']), 
              default='INFO', help='Logging level')
@click.option('--log-file', type=str, 
              help='Log file path (optional)')
@click.option('--stats', is_flag=True, 
              help='Show booking statistics only')
def main(platform, since_days, limit, mailbox, text_query, dry_run, log_level, log_file, stats):
    """
    Vacation Rental Booking Automation System.
    """
    try:
        # Initialize automation system
        automation = BookingAutomation(log_level, log_file)
        
        # Process emails (async)
        platform_enum = None
        if platform:
            platform_enum = Platform(platform)
        
        results = asyncio.run(automation.process_emails(
            platform=platform_enum,
            since_days=since_days,
            limit=limit,
            mailbox=mailbox,
            text_query=text_query,
            dry_run=dry_run
        ))
        
        if 'error' in results:
            click.echo(f"Error: {results['error']}")
            sys.exit(1)
        
        # Print results
        click.echo(f"\nProcessing completed:")
        click.echo(f"  Emails processed: {results['emails_processed']}")
        click.echo(f"  Bookings parsed: {results['bookings_parsed']}")
        click.echo(f"  New bookings: {results['new_bookings']}")
        click.echo(f"  Failed emails: {len(results['failed_emails'])}")
        
        if results.get('parsed_bookings'):
            click.echo("\nParsed bookings (up to 10):")
            for item in results['parsed_bookings'][:10]:
                nights_str = f" ({item.get('nights', 0)} nights)" if item.get('nights') else ""
                click.echo(f"  - email_id={item['email_id']}, platform={item['platform']}, reservation_id={item['reservation_id']}, guest_name={item['guest_name']}, property_name={item['property_name']}{nights_str}")
        
        if dry_run:
            click.echo("\n⚠️  DRY RUN MODE - No data was actually synced to database")
        
        return 0
        
    except Exception as e:
        click.echo(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
