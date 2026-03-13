from fastapi import APIRouter, Depends, HTTPException, Query
from ..dependencies import get_dashboard_service
from ..services.dashboard_service import DashboardService
from ..models import DashboardResponse, DashboardMetrics, ErrorResponse, DashboardExtendedResponse, DashboardExtendedMetrics

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse, responses={500: {"model": ErrorResponse}})
async def get_dashboard_metrics(platform: str | None = Query(None, description="Filter by platform"), service: DashboardService = Depends(get_dashboard_service)):
    try:
        data = await service.get_metrics(platform)
        return {"success": True, "message": "Dashboard metrics", "data": DashboardMetrics(**data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to fetch dashboard metrics", "details": {"error": str(e)}})

@router.get("/extended", response_model=DashboardExtendedResponse, responses={500: {"model": ErrorResponse}})
async def get_dashboard_extended(
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    service: DashboardService = Depends(get_dashboard_service)
):
    try:
        data = await service.get_extended_metrics(from_date, to_date)
        return {"success": True, "message": "Extended dashboard metrics", "data": DashboardExtendedMetrics(**data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to fetch extended dashboard metrics", "details": {"error": str(e)}})