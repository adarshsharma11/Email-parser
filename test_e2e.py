import sys
import os
import asyncio
from datetime import datetime, timezone

# Add 'src' and root to path
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.main import BookingAutomation
from src.utils.models import EmailData, Platform

# Create a mock EmailData for an Airbnb Booking
mock_email = EmailData(
    email_id="mock_12345",
    subject="Reservation confirmed - John Doe arrives Oct 10",
    sender="Airbnb <express@airbnb.com>",
    date=datetime.now(timezone.utc),
    body_text="""
    Reservation confirmed for John Doe
    Check-in: Oct 10, 2026
    Check-out: Oct 15, 2026
    Guests: 2
    Total (USD): $1500.00
    Reservation HMX1234567
    at Ocean View Villa
    """,
    body_html="",
    platform=Platform.AIRBNB
)

class MockGmailClient:
    def __init__(self):
        pass
    def connect_with_credentials(self, e, p):
        return True
    def fetch_emails(self, *args, **kwargs):
        # We inject our mock email here
        return [mock_email]
    def disconnect(self):
        pass

async def test_end_to_end():
    from src.main import GmailClient
    # Monkey-patch GmailClient in main to use our mock
    # Python allows substituting the class directly for the test
    import src.main
    src.main.GmailClient = MockGmailClient
    
    automation = BookingAutomation(log_level="DEBUG")
    print("Running process_emails with mock Gmail Client...")
    result = await automation.process_emails(dry_run=False)
    print("Process Result:")
    print(result)

if __name__ == "__main__":
    asyncio.run(test_end_to_end())
