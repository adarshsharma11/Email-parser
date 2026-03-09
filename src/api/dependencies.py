"""
Dependency injection and service container for FastAPI application using PostgreSQL.
"""
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from functools import lru_cache
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.psql_client import psql_client
from ..utils.logger import setup_logger
from .config import settings

# Global logger
_logger = None

def get_logger():
    """Get application logger instance."""
    global _logger
    if _logger is None:
        _logger = setup_logger("fastapi_app", settings.log_level)
    return _logger

async def get_db_session():
    """Get database session dependency."""
    async for session in psql_client.get_session():
        yield session

async def get_booking_service(session: AsyncSession = Depends(get_db_session)):
    """Get booking service instance."""
    from .services.booking_service import BookingService
    return BookingService(session, get_logger())

async def get_crew_service(session: AsyncSession = Depends(get_db_session)):
    """Get crew service instance."""
    from .services.crew_service import CrewService
    return CrewService(session)

async def get_user_service(session: AsyncSession = Depends(get_db_session)):
    """Get user service instance."""
    from .services.user_service import UserService
    return UserService(session)

async def get_dashboard_service(session: AsyncSession = Depends(get_db_session)):
    """Get dashboard service instance."""
    from .services.dashboard_service import DashboardService
    return DashboardService(session)

async def get_activity_rule_service(session: AsyncSession = Depends(get_db_session)):
    """Get activity rule service instance."""
    from .services.activity_rule_service import ActivityRuleService
    return ActivityRuleService(session, get_logger())

async def get_automation_service(
    activity_rule_service = Depends(get_activity_rule_service)
):
    """Get automation service instance."""
    from .services.automation_service import AutomationService
    return AutomationService(activity_rule_service)

async def get_service_category_service(session: AsyncSession = Depends(get_db_session)):
    """Get service category service instance."""
    from .services.service_category_service import ServiceCategoryService
    return ServiceCategoryService(session)

async def get_property_service(session: AsyncSession = Depends(get_db_session)):
    """Get property service instance."""
    from .services.property_service import PropertyService
    return PropertyService(session)

async def get_category_service(session: AsyncSession = Depends(get_db_session)):
    """Get category service instance."""
    from .services.category_service import CategoryService
    return CategoryService(session)

async def get_auth_service(session: AsyncSession = Depends(get_db_session)):
    """Get auth service instance."""
    from .services.auth_service import AuthService
    return AuthService(session)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    logger = get_logger()
    logger.info("Starting FastAPI application", version=settings.app_version)
    
    # Startup
    try:
        # Test PostgreSQL connection
        from sqlalchemy import text
        async with psql_client.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL connection verified successfully")
        
        yield
        
    except Exception as e:
        logger.error("Failed to initialize application", error=str(e))
        raise
    
    # Shutdown
    logger.info("Shutting down FastAPI application")
    
    # Close PostgreSQL engine
    await psql_client.close()
    logger.info("PostgreSQL engine closed")
