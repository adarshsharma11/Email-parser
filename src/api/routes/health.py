"""
Health check and monitoring endpoints.
"""
from datetime import datetime
from fastapi import APIRouter
from ..models import HealthResponse


router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "",
    response_model=HealthResponse,
    summary="Health check endpoint",
    description="Check if the API is running and healthy",
    responses={
        200: {"description": "Service is healthy"}
    }
)
async def health_check() -> HealthResponse:
    """
    Health check endpoint for monitoring.
    
    Returns:
        Health status information
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        version="1.0.0",
        dependencies={}
    )