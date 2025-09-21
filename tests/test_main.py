"""
Unit tests for the main orchestrator and CLI functionality.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date
from click.testing import CliRunner

from src.main import BookingAutomation, main
from src.utils.models import EmailData, BookingData, Platform, ProcessingResult, SyncResult


class TestBookingAutomation:
    """Test cases for BookingAutomation class."""
    
    @pytest.fixture
    def automation(self):
        """Create BookingAutomation instance for testing."""
        return BookingAutomation()
    
    @pytest.fixture
    def sample_email_data(self):
        """Sample email data for testing."""
        return EmailData(
            email_id="12345",
            subject="Booking Confirmation - Vrbo",
            sender="noreply@vrbo.com",
            body_text="Your booking has been confirmed",
            body_html="""
            <html>
            <body>
                <h1>Booking Confirmation</h1>
                <p>Guest: John Doe</p>
                <p>Phone: +1-555-123-4567</p>
                <p>Check-in: 12/15/2024</p>
                <p>Check-out: 12/20/2024</p>
                <p>Reservation ID: VRBO-12345</p>
                <p>Property ID: PROP-67890</p>
                <p>Number of guests: 4</p>
            </body>
            </html>
            """,
            platform=Platform.VRBO,
            date=datetime.now()
        )
    
    @pytest.fixture
    def sample_booking_data(self):
        """Sample booking data for testing."""
        return BookingData(
            guest_name="John Doe",
            guest_phone="+1-555-123-4567",
            check_in_date=date(2024, 12, 15),
            check_out_date=date(2024, 12, 20),
            reservation_id="VRBO-12345",
            property_id="PROP-67890",
            platform=Platform.VRBO,
            number_of_guests=4,
            email_id="email-12345"
        )
    
    def test_initialization(self, automation):
        """Test BookingAutomation initialization."""
        assert automation.gmail_client is not None
        assert automation.booking_parser is not None
        assert automation.firestore_client is not None
        assert automation.logger is not None
        assert automation.booking_logger is not None
    
    @patch('src.main.GmailClient')
    @patch('src.main.BookingParser')
    @patch('src.main.FirestoreClient')
    def test_process_emails_success(self, mock_firestore, mock_parser, mock_gmail, automation, sample_email_data, sample_booking_data):
        """Test successful email processing."""
        # Mock Gmail client
        mock_gmail_instance = Mock()
        mock_gmail_instance.connect.return_value = True
        mock_gmail_instance.fetch_emails.return_value = [sample_email_data]
        mock_gmail_instance.disconnect.return_value = None
        automation.gmail_client = mock_gmail_instance
        
        # Mock booking parser
        mock_parser_instance = Mock()
        mock_parser_instance.parse_email.return_value = ProcessingResult(
            success=True,
            booking_data=sample_booking_data,
            error_message=None
        )
        automation.booking_parser = mock_parser_instance
        
        # Mock Firestore client
        mock_firestore_instance = Mock()
        mock_firestore_instance.sync_bookings.return_value = [
            SyncResult(
                success=True,
                is_new=True,
                reservation_id="VRBO-12345",
                error_message=None
            )
        ]
        automation.firestore_client = mock_firestore_instance
        
        # Mock booking logger
        mock_logger = Mock()
        automation.booking_logger = mock_logger
        
        results = automation.process_emails()
        
        assert results['emails_processed'] == 1
        assert results['bookings_parsed'] == 1
        assert results['new_bookings'] == 1
        assert results['duplicate_bookings'] == 0
        assert len(results['failed_emails']) == 0
        assert len(results['sync_errors']) == 0
        assert results['dry_run'] is False
    
    @patch('src.main.GmailClient')
    def test_process_emails_gmail_connection_failure(self, mock_gmail, automation):
        """Test email processing when Gmail connection fails."""
        # Mock Gmail client connection failure
        mock_gmail_instance = Mock()
        mock_gmail_instance.connect.return_value = False
        automation.gmail_client = mock_gmail_instance
        
        results = automation.process_emails()
        
        assert 'error' in results
        assert "Failed to connect to Gmail" in results['error']
    
    @patch('src.main.GmailClient')
    def test_process_emails_no_emails_found(self, mock_gmail, automation):
        """Test email processing when no emails are found."""
        # Mock Gmail client
        mock_gmail_instance = Mock()
        mock_gmail_instance.connect.return_value = True
        mock_gmail_instance.fetch_emails.return_value = []
        mock_gmail_instance.disconnect.return_value = None
        automation.gmail_client = mock_gmail_instance
        
        results = automation.process_emails()
        
        assert results['emails_processed'] == 0
        assert results['bookings_parsed'] == 0
        assert results['new_bookings'] == 0
        assert results['duplicate_bookings'] == 0
    
    @patch('src.main.GmailClient')
    @patch('src.main.BookingParser')
    def test_process_emails_parsing_failure(self, mock_parser, mock_gmail, automation, sample_email_data):
        """Test email processing when parsing fails."""
        # Mock Gmail client
        mock_gmail_instance = Mock()
        mock_gmail_instance.connect.return_value = True
        mock_gmail_instance.fetch_emails.return_value = [sample_email_data]
        mock_gmail_instance.disconnect.return_value = None
        automation.gmail_client = mock_gmail_instance
        
        # Mock booking parser failure
        mock_parser_instance = Mock()
        mock_parser_instance.parse_email.return_value = ProcessingResult(
            success=False,
            booking_data=None,
            error_message="Failed to parse email"
        )
        automation.booking_parser = mock_parser_instance
        
        results = automation.process_emails()
        
        assert results['emails_processed'] == 1
        assert results['bookings_parsed'] == 0
        assert len(results['failed_emails']) == 1
        assert results['failed_emails'][0]['error'] == "Failed to parse email"
    
    @patch('src.main.GmailClient')
    @patch('src.main.BookingParser')
    @patch('src.main.FirestoreClient')
    def test_process_emails_sync_failure(self, mock_firestore, mock_parser, mock_gmail, automation, sample_email_data, sample_booking_data):
        """Test email processing when database sync fails."""
        # Mock Gmail client
        mock_gmail_instance = Mock()
        mock_gmail_instance.connect.return_value = True
        mock_gmail_instance.fetch_emails.return_value = [sample_email_data]
        mock_gmail_instance.disconnect.return_value = None
        automation.gmail_client = mock_gmail_instance
        
        # Mock booking parser
        mock_parser_instance = Mock()
        mock_parser_instance.parse_email.return_value = ProcessingResult(
            success=True,
            booking_data=sample_booking_data,
            error_message=None
        )
        automation.booking_parser = mock_parser_instance
        
        # Mock database client failure
        mock_firestore_instance = Mock()
        mock_firestore_instance.sync_bookings.return_value = [
            SyncResult(
                success=False,
                is_new=False,
                reservation_id="VRBO-12345",
                error_message="Database sync failed"
            )
        ]
        automation.firestore_client = mock_firestore_instance
        
        results = automation.process_emails()
        
        assert results['emails_processed'] == 1
        assert results['bookings_parsed'] == 1
        assert results['new_bookings'] == 0
        assert len(results['sync_errors']) == 1
        assert results['sync_errors'][0].error_message == "Database sync failed"
    
    @patch('src.main.GmailClient')
    @patch('src.main.BookingParser')
    @patch('src.main.FirestoreClient')
    def test_process_emails_dry_run(self, mock_firestore, mock_parser, mock_gmail, automation, sample_email_data, sample_booking_data):
        """Test email processing in dry run mode."""
        # Mock Gmail client
        mock_gmail_instance = Mock()
        mock_gmail_instance.connect.return_value = True
        mock_gmail_instance.fetch_emails.return_value = [sample_email_data]
        mock_gmail_instance.disconnect.return_value = None
        automation.gmail_client = mock_gmail_instance
        
        # Mock booking parser
        mock_parser_instance = Mock()
        mock_parser_instance.parse_email.return_value = ProcessingResult(
            success=True,
            booking_data=sample_booking_data,
            error_message=None
        )
        automation.booking_parser = mock_parser_instance
        
        # Mock Firestore client
        mock_firestore_instance = Mock()
        automation.firestore_client = mock_firestore_instance
        
        results = automation.process_emails(dry_run=True)
        
        assert results['emails_processed'] == 1
        assert results['bookings_parsed'] == 1
        assert results['dry_run'] is True
        
        # Verify Firestore sync was not called in dry run mode
        mock_firestore_instance.sync_bookings.assert_not_called()
    
    @patch('src.main.GmailClient')
    @patch('src.main.BookingParser')
    @patch('src.main.FirestoreClient')
    def test_process_emails_with_platform_filter(self, mock_firestore, mock_parser, mock_gmail, automation):
        """Test email processing with platform filter."""
        # Mock Gmail client
        mock_gmail_instance = Mock()
        mock_gmail_instance.connect.return_value = True
        mock_gmail_instance.fetch_emails.return_value = []
        mock_gmail_instance.disconnect.return_value = None
        automation.gmail_client = mock_gmail_instance
        
        automation.process_emails(platform=Platform.AIRBNB)
        
        # Verify Gmail client was called with platform filter
        mock_gmail_instance.fetch_emails.assert_called_with(
            Platform.AIRBNB,
            None,
            None
        )
    
    @patch('src.main.GmailClient')
    @patch('src.main.BookingParser')
    @patch('src.main.FirestoreClient')
    def test_process_emails_with_date_filter(self, mock_firestore, mock_parser, mock_gmail, automation):
        """Test email processing with date filter."""
        # Mock Gmail client
        mock_gmail_instance = Mock()
        mock_gmail_instance.connect.return_value = True
        mock_gmail_instance.fetch_emails.return_value = []
        mock_gmail_instance.disconnect.return_value = None
        automation.gmail_client = mock_gmail_instance
        
        automation.process_emails(since_days=7)
        
        # Verify Gmail client was called with date filter
        mock_gmail_instance.fetch_emails.assert_called_with(
            None,
            7,
            None
        )
    
    @patch('src.main.GmailClient')
    @patch('src.main.BookingParser')
    @patch('src.main.FirestoreClient')
    def test_process_emails_with_limit(self, mock_firestore, mock_parser, mock_gmail, automation):
        """Test email processing with limit."""
        # Mock Gmail client
        mock_gmail_instance = Mock()
        mock_gmail_instance.connect.return_value = True
        mock_gmail_instance.fetch_emails.return_value = []
        mock_gmail_instance.disconnect.return_value = None
        automation.gmail_client = mock_gmail_instance
        
        automation.process_emails(limit=10)
        
        # Verify Gmail client was called with limit
        mock_gmail_instance.fetch_emails.assert_called_with(
            None,
            None,
            10
        )
    
    @patch('src.main.FirestoreClient')
    def test_get_booking_stats_success(self, mock_firestore, automation):
        """Test successful retrieval of booking statistics."""
        # Mock Firestore client
        mock_firestore_instance = Mock()
        mock_firestore_instance.get_booking_stats.return_value = {
            'total_bookings': 10,
            'by_platform': {
                'vrbo': 5,
                'airbnb': 3,
                'booking': 2
            }
        }
        automation.firestore_client = mock_firestore_instance
        
        stats = automation.get_booking_stats()
        
        assert stats['total_bookings'] == 10
        assert stats['by_platform']['vrbo'] == 5
        assert stats['by_platform']['airbnb'] == 3
        assert stats['by_platform']['booking'] == 2
    
    @patch('src.main.FirestoreClient')
    def test_get_booking_stats_failure(self, mock_firestore, automation):
        """Test booking statistics retrieval failure."""
        # Mock Firestore client failure
        mock_firestore_instance = Mock()
        mock_firestore_instance.get_booking_stats.side_effect = Exception("Database error")
        automation.firestore_client = mock_firestore_instance
        
        stats = automation.get_booking_stats()
        
        assert 'error' in stats
        assert "Database error" in stats['error']
    
    def test_get_empty_results(self, automation):
        """Test empty results structure."""
        results = automation._get_empty_results()
        
        assert results['emails_processed'] == 0
        assert results['bookings_parsed'] == 0
        assert results['new_bookings'] == 0
        assert results['duplicate_bookings'] == 0
        assert results['failed_emails'] == []
        assert results['sync_errors'] == []
        assert results['dry_run'] is False


class TestCLI:
    """Test cases for CLI functionality."""
    
    @pytest.fixture
    def runner(self):
        """Create CLI runner for testing."""
        return CliRunner()
    
    @patch('src.main.BookingAutomation')
    def test_cli_basic_usage(self, mock_automation, runner):
        """Test basic CLI usage."""
        # Mock automation instance
        mock_automation_instance = Mock()
        mock_automation_instance.process_emails.return_value = {
            'emails_processed': 5,
            'bookings_parsed': 4,
            'new_bookings': 3,
            'duplicate_bookings': 1,
            'failed_emails': [],
            'sync_errors': [],
            'dry_run': False
        }
        mock_automation.return_value = mock_automation_instance
        
        result = runner.invoke(main)
        
        assert result.exit_code == 0
        assert "Processing completed:" in result.output
        assert "Emails processed: 5" in result.output
        assert "Bookings parsed: 4" in result.output
        assert "New bookings: 3" in result.output
        assert "Duplicate bookings: 1" in result.output
    
    @patch('src.main.BookingAutomation')
    def test_cli_with_platform_option(self, mock_automation, runner):
        """Test CLI with platform option."""
        # Mock automation instance
        mock_automation_instance = Mock()
        mock_automation_instance.process_emails.return_value = {
            'emails_processed': 2,
            'bookings_parsed': 2,
            'new_bookings': 2,
            'duplicate_bookings': 0,
            'failed_emails': [],
            'sync_errors': [],
            'dry_run': False
        }
        mock_automation.return_value = mock_automation_instance
        
        result = runner.invoke(main, ['--platform', 'vrbo'])
        
        assert result.exit_code == 0
        mock_automation_instance.process_emails.assert_called_with(
            platform=Platform.VRBO,
            since_days=None,
            limit=None,
            dry_run=False
        )
    
    @patch('src.main.BookingAutomation')
    def test_cli_with_since_days_option(self, mock_automation, runner):
        """Test CLI with since-days option."""
        # Mock automation instance
        mock_automation_instance = Mock()
        mock_automation_instance.process_emails.return_value = {
            'emails_processed': 3,
            'bookings_parsed': 3,
            'new_bookings': 3,
            'duplicate_bookings': 0,
            'failed_emails': [],
            'sync_errors': [],
            'dry_run': False
        }
        mock_automation.return_value = mock_automation_instance
        
        result = runner.invoke(main, ['--since-days', '7'])
        
        assert result.exit_code == 0
        mock_automation_instance.process_emails.assert_called_with(
            platform=None,
            since_days=7,
            limit=None,
            dry_run=False
        )
    
    @patch('src.main.BookingAutomation')
    def test_cli_with_limit_option(self, mock_automation, runner):
        """Test CLI with limit option."""
        # Mock automation instance
        mock_automation_instance = Mock()
        mock_automation_instance.process_emails.return_value = {
            'emails_processed': 10,
            'bookings_parsed': 8,
            'new_bookings': 8,
            'duplicate_bookings': 0,
            'failed_emails': [],
            'sync_errors': [],
            'dry_run': False
        }
        mock_automation.return_value = mock_automation_instance
        
        result = runner.invoke(main, ['--limit', '10'])
        
        assert result.exit_code == 0
        mock_automation_instance.process_emails.assert_called_with(
            platform=None,
            since_days=None,
            limit=10,
            dry_run=False
        )
    
    @patch('src.main.BookingAutomation')
    def test_cli_with_dry_run_option(self, mock_automation, runner):
        """Test CLI with dry-run option."""
        # Mock automation instance
        mock_automation_instance = Mock()
        mock_automation_instance.process_emails.return_value = {
            'emails_processed': 5,
            'bookings_parsed': 5,
            'new_bookings': 5,
            'duplicate_bookings': 0,
            'failed_emails': [],
            'sync_errors': [],
            'dry_run': True
        }
        mock_automation.return_value = mock_automation_instance
        
        result = runner.invoke(main, ['--dry-run'])
        
        assert result.exit_code == 0
        assert "DRY RUN MODE" in result.output
        mock_automation_instance.process_emails.assert_called_with(
            platform=None,
            since_days=None,
            limit=None,
            dry_run=True
        )
    
    @patch('src.main.BookingAutomation')
    def test_cli_with_stats_option(self, mock_automation, runner):
        """Test CLI with stats option."""
        # Mock automation instance
        mock_automation_instance = Mock()
        mock_automation_instance.get_booking_stats.return_value = {
            'total_bookings': 25,
            'by_platform': {
                'vrbo': 12,
                'airbnb': 8,
                'booking': 5
            }
        }
        mock_automation.return_value = mock_automation_instance
        
        result = runner.invoke(main, ['--stats'])
        
        assert result.exit_code == 0
        assert "Booking Statistics:" in result.output
        assert "Total bookings: 25" in result.output
        assert "vrbo: 12" in result.output
        assert "airbnb: 8" in result.output
        assert "booking: 5" in result.output
        
        # Verify process_emails was not called
        mock_automation_instance.process_emails.assert_not_called()
    
    @patch('src.main.BookingAutomation')
    def test_cli_with_log_level_option(self, mock_automation, runner):
        """Test CLI with log-level option."""
        # Mock automation instance
        mock_automation_instance = Mock()
        mock_automation_instance.process_emails.return_value = {
            'emails_processed': 1,
            'bookings_parsed': 1,
            'new_bookings': 1,
            'duplicate_bookings': 0,
            'failed_emails': [],
            'sync_errors': [],
            'dry_run': False
        }
        mock_automation.return_value = mock_automation_instance
        
        result = runner.invoke(main, ['--log-level', 'DEBUG'])
        
        assert result.exit_code == 0
        # Verify automation was initialized with DEBUG log level
        mock_automation.assert_called_with('DEBUG', None)
    
    @patch('src.main.BookingAutomation')
    def test_cli_with_log_file_option(self, mock_automation, runner):
        """Test CLI with log-file option."""
        # Mock automation instance
        mock_automation_instance = Mock()
        mock_automation_instance.process_emails.return_value = {
            'emails_processed': 1,
            'bookings_parsed': 1,
            'new_bookings': 1,
            'duplicate_bookings': 0,
            'failed_emails': [],
            'sync_errors': [],
            'dry_run': False
        }
        mock_automation.return_value = mock_automation_instance
        
        result = runner.invoke(main, ['--log-file', 'test.log'])
        
        assert result.exit_code == 0
        # Verify automation was initialized with log file
        mock_automation.assert_called_with('INFO', 'test.log')
    
    @patch('src.main.BookingAutomation')
    def test_cli_processing_error(self, mock_automation, runner):
        """Test CLI when processing encounters an error."""
        # Mock automation instance
        mock_automation_instance = Mock()
        mock_automation_instance.process_emails.return_value = {
            'error': 'Processing failed'
        }
        mock_automation.return_value = mock_automation_instance
    
        result = runner.invoke(main)
    
        # The main function should return 1 when there's an error in results
        assert result.exit_code == 1
        assert "Error: Processing failed" in result.output
    
    @patch('src.main.BookingAutomation')
    def test_cli_stats_error(self, mock_automation, runner):
        """Test CLI when stats retrieval encounters an error."""
        # Mock automation instance
        mock_automation_instance = Mock()
        mock_automation_instance.get_booking_stats.return_value = {
            'error': 'Stats retrieval failed'
        }
        mock_automation.return_value = mock_automation_instance
        
        result = runner.invoke(main, ['--stats'])
        
        assert result.exit_code == 1
        assert "Error: Stats retrieval failed" in result.output
    
    @patch('src.main.BookingAutomation')
    def test_cli_fatal_error(self, mock_automation, runner):
        """Test CLI when a fatal error occurs."""
        # Mock automation to raise an exception
        mock_automation.side_effect = Exception("Fatal error")
        
        result = runner.invoke(main)
        
        assert result.exit_code == 1
        assert "Fatal error: Fatal error" in result.output
    
    def test_cli_help(self, runner):
        """Test CLI help output."""
        result = runner.invoke(main, ['--help'])
        
        assert result.exit_code == 0
        assert "Vacation Rental Booking Automation System" in result.output
        assert "--platform" in result.output
        assert "--since-days" in result.output
        assert "--limit" in result.output
        assert "--dry-run" in result.output
        assert "--stats" in result.output
    
    def test_cli_invalid_platform(self, runner):
        """Test CLI with invalid platform option."""
        result = runner.invoke(main, ['--platform', 'invalid'])
        
        assert result.exit_code != 0
        assert "Invalid value" in result.output
    
    def test_cli_invalid_log_level(self, runner):
        """Test CLI with invalid log level."""
        result = runner.invoke(main, ['--log-level', 'INVALID'])
        
        assert result.exit_code != 0
        assert "Invalid value" in result.output
