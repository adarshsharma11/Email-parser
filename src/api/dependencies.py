"""
Dependency injection and service container for FastAPI application.
"""
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI
from functools import lru_cache

from ..supabase_sync.supabase_client import SupabaseClient
from ..utils.logger import setup_logger
from .config import settings
from .services.booking_service import BookingService
from .services.user_service import UserService


# Global service instances
_supabase_client: Optional[SupabaseClient] = None
_logger = None


def get_logger():
    """Get application logger instance."""
    global _logger
    if _logger is None:
        _logger = setup_logger("fastapi_app", settings.log_level)
    return _logger


def get_supabase_client() -> SupabaseClient:
    """Get Supabase client instance."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = SupabaseClient()
    return _supabase_client


@lru_cache(maxsize=1)
def get_booking_service():
    """Get booking service instance with caching."""
    from .services.booking_service import BookingService
    return BookingService(get_supabase_client(), get_logger())


@lru_cache(maxsize=1)
def get_crew_service():
    """Get crew service instance with caching."""
    from .services.crew_service import CrewService
    return CrewService()


@lru_cache(maxsize=1)
def get_user_service():
    """Get user service instance with caching."""
    return UserService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    logger = get_logger()
    logger.info("Starting FastAPI application", version=settings.app_version)
    
    # Startup
    try:
        # Test Supabase connection
        client = get_supabase_client()
        logger.info("Supabase client initialized successfully")
        
        yield
        
    except Exception as e:
        logger.error("Failed to initialize application", error=str(e))
        raise
    
    # Shutdown
    logger.info("Shutting down FastAPI application")
    
    # Cleanup global instances
    global _supabase_client, _logger
    _supabase_client = None
    _logger = None
    
    # Clear cached services
    get_booking_service.cache_clear()