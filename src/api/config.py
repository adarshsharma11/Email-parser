"""
Configuration settings for FastAPI application.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from config.settings import supabase_config


class FastAPISettings(BaseSettings):
    """FastAPI application settings with environment variable loading."""
    
    # Application settings
    app_name: str = Field(default="Booking API", description="Application name")
    app_description: str = Field(default="API for vacation rental booking management", description="Application description")
    app_version: str = Field(default="1.0.0", description="Application version")
    
    # Server settings
    host: str = Field(default="127.0.0.1", description="Server host")
    port: int = Field(default=8001, description="Server port")
    environment: str = Field(default="development", description="Environment (development, staging, production)")
    
    # API settings
    api_version: str = Field(default="v1", description="API version")
    api_prefix: str = Field(default="/api", description="API prefix")
    
    # Security settings
    cors_origins: Optional[list[str]] = Field(
        default=None, 
        description="Allowed CORS origins",
        validation_alias="CORS_ORIGINS"
    )
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    
    # Supabase configuration (from existing config)
    supabase_url: str = Field(default_factory=lambda: supabase_config.url or "", description="Supabase project URL")
    supabase_anon_key: str = Field(default_factory=lambda: supabase_config.get_auth_key() if supabase_config.get_auth_key else "", description="Supabase anonymous key")
    supabase_service_role_key: Optional[str] = Field(default=None, description="Supabase service role key")
    
    # Performance settings
    cache_ttl_seconds: int = Field(default=300, description="Cache TTL in seconds")
    rate_limit_per_minute: int = Field(default=60, description="Rate limit per minute")
    
    model_config = {"extra": "ignore"}  # Allow extra fields from existing .env
    
    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from environment variable or return default."""
        if v is None or v == "":
            return ["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "https://email-parser-frontend-lyart.vercel.app/"]
        if isinstance(v, str):
            # Handle comma-separated string from environment variable
            origins = [origin.strip() for origin in v.split(',') if origin.strip()]
            return origins if origins else ["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "https://email-parser-frontend-lyart.vercel.app"]
        return v
    
    @property
    def supabase_auth_key(self) -> str:
        """Get the appropriate Supabase authentication key."""
        return self.supabase_service_role_key or self.supabase_anon_key


# Global settings instance
settings = FastAPISettings()