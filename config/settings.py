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
                "booking": "from:booking.com OR from:booking.co.uk",
                "plumguide": "from:plumguide.com OR from:plumguide.co.uk"
            }




@dataclass
class SupabaseConfig:
    """Supabase configuration settings (replaces Firebase)."""
    url: str = os.getenv("SUPABASE_URL", "")
    anon_key: str = os.getenv("SUPABASE_ANON_KEY", "")
    service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    def get_auth_key(self) -> str:
        """Prefer service role key for server-side operations when available."""
        return self.service_role_key or self.anon_key


@dataclass
class AppConfig:
    """Application configuration settings."""
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    default_timezone: str = os.getenv("DEFAULT_TIMEZONE", "UTC")
    max_emails_per_run: int = int(os.getenv("MAX_EMAILS_PER_RUN", "100"))
    
    # Data storage collection/table names
    bookings_collection: str = "bookings"
    properties_collection: str = "properties"
    cleaning_tasks_collection: str = "cleaning_tasks"
    cleaning_crews_collection: str = "cleaning_crews"
    properties_collection= "properties"
    users_collection: str = "user_credentials"
    auth_collection: str = "users"
    # Email processing settings
    supported_platforms: tuple = ("vrbo", "airbnb", "booking", "plumguide")
    
    # Date formats for different platforms
    date_formats: Dict[str, str] = None
    
    # RAG and LLM settings
    rag_cache_ttl_hours: int = int(os.getenv("RAG_CACHE_TTL_HOURS", "24"))
    
    def __post_init__(self):
        if self.date_formats is None:
            self.date_formats = {
                "vrbo": ["%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y"],
                "airbnb": ["%B %d, %Y", "%Y-%m-%d", "%d/%m/%Y"],
                "booking": ["%Y-%m-%d", "%d/%m/%Y", "%B %d, %Y"],
                "plumguide": ["%a, %d %b %Y", "%d/%m/%Y", "%B %d, %Y"],
            }


@dataclass
class APIConfig:
    """API and URL configuration settings."""
    base_url: str = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


gmail_config = GmailConfig()
supabase_config = SupabaseConfig()
app_config = AppConfig()
api_config = APIConfig()
