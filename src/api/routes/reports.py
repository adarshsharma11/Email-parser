from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from ..dependencies import get_report_service
from ..services.report_service import ReportService
from ..models import ErrorResponse, APIResponse

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/owner-statement")
async def get_owner_statement(
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    propertyIds: Optional[str] = Query(None),
    ownerIds: Optional[str] = Query(None),
    service: ReportService = Depends(get_report_service)
):
    try:
        pids = propertyIds.split(",") if propertyIds else None
        oids = ownerIds.split(",") if ownerIds else None
        data = await service.get_owner_statement(from_date, to_date, pids, oids)
        return {"success": True, "message": "Owner statement generated", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to generate owner statement", "details": {"error": str(e)}})

@router.get("/booking-summary")
async def get_booking_summary(
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    propertyIds: Optional[str] = Query(None),
    service: ReportService = Depends(get_report_service)
):
    try:
        pids = propertyIds.split(",") if propertyIds else None
        data = await service.get_booking_summary(from_date, to_date, pids)
        return {"success": True, "message": "Booking summary generated", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to generate booking summary", "details": {"error": str(e)}})

@router.get("/occupancy")
async def get_occupancy_report(
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    propertyIds: Optional[str] = Query(None),
    service: ReportService = Depends(get_report_service)
):
    try:
        pids = propertyIds.split(",") if propertyIds else None
        data = await service.get_occupancy_report(from_date, to_date, pids)
        return {"success": True, "message": "Occupancy report generated", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to generate occupancy report", "details": {"error": str(e)}})

@router.get("/service-revenue")
async def get_service_revenue(
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    propertyIds: Optional[str] = Query(None),
    service: ReportService = Depends(get_report_service)
):
    try:
        pids = propertyIds.split(",") if propertyIds else None
        data = await service.get_service_revenue(from_date, to_date, pids)
        return {"success": True, "message": "Service revenue report generated", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to generate service revenue report", "details": {"error": str(e)}})

@router.get("/performance")
async def get_performance_report(
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    propertyIds: Optional[str] = Query(None),
    service: ReportService = Depends(get_report_service)
):
    try:
        pids = propertyIds.split(",") if propertyIds else None
        data = await service.get_performance_report(from_date, to_date, pids)
        return {"success": True, "message": "Performance report generated", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to generate performance report", "details": {"error": str(e)}})

@router.get("/service-provider")
async def get_service_provider_report(
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    providerId: Optional[str] = Query(None),
    service: ReportService = Depends(get_report_service)
):
    try:
        data = await service.get_service_provider_report(from_date, to_date, providerId)
        return {"success": True, "message": "Service provider report generated", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to generate service provider report", "details": {"error": str(e)}})

@router.post("/send-email")
async def send_report_email(payload: dict):
    # Placeholder for email sending logic
    return {"success": True, "message": "Report email sent (placeholder)"}
