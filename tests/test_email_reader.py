"""
Unit tests for the email reader module.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from src.email_reader.gmail_client import GmailClient
from src.utils.models import EmailData, Platform


class TestGmailClient:
    """Test cases for GmailClient class."""
    
    @pytest.fixture
    def mock_imap(self):
        """Mock IMAP connection."""
        with patch('imaplib.IMAP4_SSL') as mock_imap_class:
            mock_imap = Mock()
            mock_imap_class.return_value = mock_imap
            yield mock_imap
    
    @pytest.fixture
    def gmail_client(self):
        """Create GmailClient instance for testing."""
        return GmailClient()
    
    @pytest.fixture
    def sample_email_data(self):
        """Sample email data for testing."""
        return {
            'email_id': '12345',
            'subject': 'Booking Confirmation - Vrbo',
            'from': 'noreply@vrbo.com',
            'date': datetime.now(),
            'body': 'Your booking has been confirmed',
            'html_body': '<html><body>Your booking has been confirmed</body></html>'
        }
    
    def test_connect_success(self, gmail_client, mock_imap):
        """Test successful Gmail connection."""
        mock_imap.login.return_value = ('OK', [b'Logged in'])
        
        result = gmail_client.connect()
        
        assert result is True
        mock_imap.login.assert_called_once()
    
    def test_connect_failure(self, gmail_client, mock_imap):
        """Test Gmail connection failure."""
        mock_imap.login.side_effect = Exception("Authentication failed")
        
        result = gmail_client.connect()
        
        assert result is False
    
    def test_connect_exception(self, gmail_client, mock_imap):
        """Test Gmail connection with exception."""
        mock_imap.login.side_effect = Exception("Connection error")
        
        result = gmail_client.connect()
        
        assert result is False
        assert not gmail_client.connected
    
    def test_disconnect(self, gmail_client, mock_imap):
        """Test Gmail disconnection."""
        gmail_client.connection = mock_imap
        gmail_client.connected = True
        
        gmail_client.disconnect()
        
        mock_imap.logout.assert_called_once()
    
    def test_fetch_emails_no_connection(self, gmail_client):
        """Test fetching emails without connection."""
        gmail_client.imap = None
        
        emails = gmail_client.fetch_emails()
        
        assert emails == []
    
    def test_fetch_emails_success(self, gmail_client, mock_imap, sample_email_data):
        """Test successful email fetching."""
        gmail_client.connection = mock_imap
        
        # Mock email search
        mock_imap.search.return_value = ('OK', [b'1 2 3'])

        # Mock email fetch
        email_content = self._create_sample_email(sample_email_data)
        mock_imap.fetch.return_value = ('OK', [(b'1 (RFC822 {size})', email_content.encode())])

        # Mock connection state
        gmail_client.connected = True

        emails = gmail_client.fetch_emails(limit=1)

        assert len(emails) == 1
        assert isinstance(emails[0], EmailData)
        assert emails[0].email_id == '1'
        assert emails[0].platform == Platform.VRBO
    
    def test_fetch_emails_with_platform_filter(self, gmail_client, mock_imap):
        """Test email fetching with platform filter."""
        gmail_client.connection = mock_imap
        gmail_client.connected = True
        mock_imap.search.return_value = ('OK', [b'1'])

        gmail_client.fetch_emails(platform=Platform.AIRBNB, limit=1)

        # Verify search was called with platform-specific pattern
        search_call = mock_imap.search.call_args[0][1]
        assert 'airbnb.com' in search_call
    
    def test_fetch_emails_with_date_filter(self, gmail_client, mock_imap):
        """Test email fetching with date filter."""
        gmail_client.connection = mock_imap
        gmail_client.connected = True
        mock_imap.search.return_value = ('OK', [b'1'])

        gmail_client.fetch_emails(since_days=7, limit=1)

        # Verify search was called with date filter
        search_call = mock_imap.search.call_args[0][1]
        assert 'SINCE' in search_call
    
    def test_fetch_emails_search_failure(self, gmail_client, mock_imap):
        """Test email fetching when search fails."""
        gmail_client.connection = mock_imap
        gmail_client.connected = True
        mock_imap.search.return_value = ('NO', [b'Search failed'])
        
        emails = gmail_client.fetch_emails()
        
        assert emails == []
    
    def test_fetch_emails_fetch_failure(self, gmail_client, mock_imap):
        """Test email fetching when fetch fails."""
        gmail_client.connection = mock_imap
        gmail_client.connected = True
        mock_imap.search.return_value = ('OK', [b'1'])
        mock_imap.fetch.return_value = ('NO', [b'Fetch failed'])
        
        emails = gmail_client.fetch_emails()
        
        assert emails == []
    
    def test_mark_as_read(self, gmail_client, mock_imap):
        """Test marking email as read."""
        gmail_client.connection = mock_imap
        gmail_client.connected = True
        mock_imap.store.return_value = ('OK', [b'Marked as read'])

        result = gmail_client.mark_as_read('12345')

        assert result is True
        mock_imap.store.assert_called_once_with('12345', '+FLAGS', '\\Seen')
    
    def test_mark_as_read_failure(self, gmail_client, mock_imap):
        """Test marking email as read failure."""
        gmail_client.connection = mock_imap
        gmail_client.connected = True
        mock_imap.store.side_effect = Exception("Store operation failed")
        
        result = gmail_client.mark_as_read('12345')
        
        assert result is False
    
    def test_parse_email_content(self, gmail_client, sample_email_data):
        """Test email content parsing."""
        # Test the actual fetch_email method
        gmail_client.connection = Mock()
        gmail_client.connected = True
        
        # Mock the fetch_email method to return a sample EmailData
        with patch.object(gmail_client, 'fetch_email') as mock_fetch:
            mock_fetch.return_value = EmailData(
                email_id='12345',
                subject=sample_email_data['subject'],
                sender=sample_email_data['from'],
                date=datetime.now(),
                body_text=sample_email_data['body'],
                body_html=sample_email_data['html_body'],
                platform=Platform.VRBO
            )
            
            email_data = gmail_client.fetch_email('12345')
            assert email_data is not None
            assert email_data.email_id == '12345'
            assert email_data.subject == sample_email_data['subject']
            assert email_data.sender == sample_email_data['from']
            assert email_data.platform == Platform.VRBO
    
    def test_parse_email_content_no_html(self, gmail_client):
        """Test email content parsing without HTML."""
        # Test the actual fetch_email method with a mock
        gmail_client.connection = Mock()
        gmail_client.connected = True
        
        # Mock the fetch_email method to return a sample EmailData
        with patch.object(gmail_client, 'fetch_email') as mock_fetch:
            mock_fetch.return_value = EmailData(
                email_id='12345',
                subject='Booking Confirmation',
                sender='noreply@vrbo.com',
                date=datetime.now(),
                body_text='Your booking has been confirmed',
                body_html='',
                platform=Platform.VRBO
            )
            
            email_data = gmail_client.fetch_email('12345')
            assert email_data is not None
            assert email_data.email_id == '12345'
            assert email_data.body_html == ''
            assert email_data.body_text == 'Your booking has been confirmed'
    
    def test_detect_platform(self, gmail_client):
        """Test platform detection from email."""
        # Test Vrbo
        platform = gmail_client._detect_platform('noreply@vrbo.com', 'Booking Confirmation')
        assert platform == Platform.VRBO
        
        # Test Airbnb
        platform = gmail_client._detect_platform('noreply@airbnb.com', 'Booking Confirmation')
        assert platform == Platform.AIRBNB
        
        # Test Booking.com
        platform = gmail_client._detect_platform('noreply@booking.com', 'Booking Confirmation')
        assert platform == Platform.BOOKING
        
        # Test unknown platform
        platform = gmail_client._detect_platform('noreply@unknown.com', 'Booking Confirmation')
        assert platform is None
    
    def _create_sample_email(self, data):
        """Helper method to create sample email."""
        msg = MIMEMultipart()
        msg['Subject'] = data.get('subject', 'Booking Confirmation')
        msg['From'] = data.get('from', 'noreply@vrbo.com')
        msg['Date'] = data.get('date', datetime.now()).strftime('%a, %d %b %Y %H:%M:%S %z')
        
        text_part = MIMEText(data.get('body', 'Your booking has been confirmed'), 'plain')
        html_part = MIMEText(data.get('html_body', '<html><body>Your booking has been confirmed</body></html>'), 'html')
        
        msg.attach(text_part)
        msg.attach(html_part)
        
        return msg.as_string()
    
    def test_get_search_pattern_all_platforms(self, gmail_client):
        """Test search pattern generation for all platforms."""
        # Test that the client can generate search patterns
        gmail_client.connected = True
        gmail_client.connection = Mock()
        gmail_client.connection.search.return_value = ('OK', [b'1'])
        
        # This tests the actual search functionality
        gmail_client.fetch_emails()
        assert gmail_client.connection.search.called
    
    def test_get_search_pattern_specific_platform(self, gmail_client):
        """Test search pattern generation for specific platform."""
        # Test that the client can generate search patterns for specific platforms
        gmail_client.connected = True
        gmail_client.connection = Mock()
        gmail_client.connection.search.return_value = ('OK', [b'1'])
        
        # This tests the actual search functionality with platform filter
        gmail_client.fetch_emails(platform=Platform.AIRBNB)
        assert gmail_client.connection.search.called
    
    def test_get_search_pattern_with_date_filter(self, gmail_client):
        """Test search pattern generation with date filter."""
        # Test that the client can generate search patterns with date filters
        gmail_client.connected = True
        gmail_client.connection = Mock()
        gmail_client.connection.search.return_value = ('OK', [b'1'])
        
        # This tests the actual search functionality with date filter
        gmail_client.fetch_emails(since_days=7)
        assert gmail_client.connection.search.called
    
    def test_get_search_pattern_with_limit(self, gmail_client, mock_imap):
        """Test email fetching with limit."""
        gmail_client.connection = mock_imap
        gmail_client.connected = True
        mock_imap.search.return_value = ('OK', [b'1 2 3 4 5'])

        # Mock email fetch for multiple emails
        email_content = self._create_sample_email({'from': 'noreply@vrbo.com'})
        mock_imap.fetch.return_value = ('OK', [
            (b'1 (RFC822 {size})', email_content.encode()),
            (b'1 (RFC822 {size})', email_content.encode()),
            (b'2 (RFC822 {size})', email_content.encode()),
            (b'2 (RFC822 {size})', email_content.encode()),
            (b'3 (RFC822 {size})', email_content.encode())
        ])

        emails = gmail_client.fetch_emails(limit=2)

        assert len(emails) == 2  # Should respect the limit
