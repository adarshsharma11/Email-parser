"""
Configuration settings for the Vacation Rental Booking Automation system.
"""
import os
from typing import Dict, Any
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class GmailConfig:
    """Gmail IMAP configuration settings."""
    email: str = os.getenv("GMAIL_EMAIL", "")
    password: str = os.getenv("GMAIL_PASSWORD", "")
    imap_server: str = os.getenv("GMAIL_IMAP_SERVER", "imap.gmail.com")
    imap_port: int = int(os.getenv("GMAIL_IMAP_PORT", "993"))
    
    # Email search patterns for vacation rental platforms
    search_patterns: Dict[str, str] = None
    
    def __post_init__(self):
        if self.search_patterns is None:
            self.search_patterns = {
                "vrbo": "from:vrbo.com OR from:homeaway.com",
                "airbnb": "from:airbnb.com OR from:airbnb.co.uk",
                "booking": "from:booking.com OR from:booking.co.uk"
            }


@dataclass
class FirebaseConfig:
    """Firebase Firestore configuration settings."""
    project_id: str = os.getenv("FIREBASE_PROJECT_ID", "")
    private_key_id: str = os.getenv("FIREBASE_PRIVATE_KEY_ID", "")
    private_key: str = os.getenv("FIREBASE_PRIVATE_KEY", "")
    client_email: str = os.getenv("FIREBASE_CLIENT_EMAIL", "")
    client_id: str = os.getenv("FIREBASE_CLIENT_ID", "")
    auth_uri: str = os.getenv("FIREBASE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth")
    token_uri: str = os.getenv("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token")
    auth_provider_x509_cert_url: str = os.getenv(
        "FIREBASE_AUTH_PROVIDER_X509_CERT_URL", 
        "https://www.googleapis.com/oauth2/v1/certs"
    )
    client_x509_cert_url: str = os.getenv("FIREBASE_CLIENT_X509_CERT_URL", "")
    
    def get_credentials_dict(self) -> Dict[str, Any]:
        """Return Firebase credentials as a dictionary."""
        return {
            "type": "service_account",
            "project_id": self.project_id,
            "private_key_id": self.private_key_id,
            "private_key": self.private_key.replace("\\n", "\n"),
            "client_email": self.client_email,
            "client_id": self.client_id,
            "auth_uri": self.auth_uri,
            "token_uri": self.token_uri,
            "auth_provider_x509_cert_url": self.auth_provider_x509_cert_url,
            "client_x509_cert_url": self.client_x509_cert_url
        }


@dataclass
class AppConfig:
    """Application configuration settings."""
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    default_timezone: str = os.getenv("DEFAULT_TIMEZONE", "UTC")
    max_emails_per_run: int = int(os.getenv("MAX_EMAILS_PER_RUN", "100"))
    
    # Firestore collection names
    bookings_collection: str = "bookings"
    properties_collection: str = "properties"
    
    # Email processing settings
    supported_platforms: tuple = ("vrbo", "airbnb", "booking")
    
    # Date formats for different platforms
    date_formats: Dict[str, str] = None
    
    def __post_init__(self):
        if self.date_formats is None:
            self.date_formats = {
                "vrbo": ["%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y"],
                "airbnb": ["%B %d, %Y", "%Y-%m-%d", "%d/%m/%Y"],
                "booking": ["%Y-%m-%d", "%d/%m/%Y", "%B %d, %Y"]
            }


# Global configuration instances
gmail_config = GmailConfig()
firebase_config = FirebaseConfig()
app_config = AppConfig()
