from fastapi import APIRouter, Depends, HTTPException, Query
from ..dependencies import get_dashboard_service
from ..services.dashboard_service import DashboardService
from ..models import DashboardResponse, DashboardMetrics, ErrorResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse, responses={500: {"model": ErrorResponse}})
async def get_dashboard_metrics(platform: str | None = Query(None, description="Filter by platform"), service: DashboardService = Depends(get_dashboard_service)):
    try:
        data = service.get_metrics(platform)
        return {"success": True, "message": "Dashboard metrics", "data": DashboardMetrics(**data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to fetch dashboard metrics", "details": {"error": str(e)}})