"""
Main FastAPI application factory.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from datetime import datetime
import json

from .config import settings
from .dependencies import get_logger, get_supabase_client, get_booking_service
from .routes import bookings, health, crews, ical, users, dashboard, auth
from .models import ErrorResponse


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("Starting FastAPI application")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"API Version: {settings.api_version}")
    
    # Initialize services
    try:
        supabase_client = get_supabase_client()
        booking_service = get_booking_service()
        logger.info("Services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down FastAPI application")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title=settings.app_name,
        description=settings.app_description,
        version=settings.api_version,
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        lifespan=lifespan
    )
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins
        allow_credentials=False,  # MUST be False when using "*"
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    
    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Global exception handler for unhandled errors."""
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                success=False,
                message="Internal server error",
                error_code="INTERNAL_ERROR",
                details={"error": str(exc)}
            ).dict()
        )
    
    # Include routers with versioning
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path
        method = request.method
        open_paths = {
            f"{settings.api_prefix}/v1/auth/login",
            f"{settings.api_prefix}/v1/auth/register",
        }
        if method == "OPTIONS" or any(path.startswith(p) for p in open_paths):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content=ErrorResponse(success=False, message="Unauthorized", error_code="UNAUTHORIZED").dict())
        token = auth_header.split(" ", 1)[1]
        try:
            from .security.jwt import verify_token
            payload = verify_token(token)
            request.state.user_email = payload.get("sub")
        except Exception as e:
            return JSONResponse(status_code=401, content=ErrorResponse(success=False, message="Invalid token", error_code="UNAUTHORIZED", details={"error": str(e)}).dict())
        return await call_next(request)
    app.include_router(
        bookings.router,
        prefix=f"{settings.api_prefix}/v1"
    )
    
    app.include_router(
        health.router,
        prefix=f"{settings.api_prefix}/v1"
    )
    
    app.include_router(
        crews.router,
        prefix=f"{settings.api_prefix}/v1"
    )

    app.include_router(
        ical.router,
        prefix=f"{settings.api_prefix}/v1"
    )

    app.include_router(
        users.router,
        prefix=f"{settings.api_prefix}/v1"
    )

    app.include_router(
        dashboard.router,
        prefix=f"{settings.api_prefix}/v1"
    )

    app.include_router(
        auth.router,
        prefix=f"{settings.api_prefix}/v1"
    )
    
    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "message": "Booking API is running",
            "version": settings.api_version,
            "environment": settings.environment,
            "docs": f"{settings.api_prefix}/docs"
        }
    
    return app