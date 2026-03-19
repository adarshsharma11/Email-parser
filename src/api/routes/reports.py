from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
import base64
from datetime import datetime
from ..dependencies import get_report_service
from ..services.report_service import ReportService
from ..models import ErrorResponse, APIResponse
from src.utils.report_email import send_email_with_pdf, build_email_html

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
        return {"success": True, "message": "Owner statement generated", "data": data, "generated_at": datetime.utcnow().isoformat()}
    except HTTPException:
        raise
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
        return {"success": True, "message": "Booking summary generated", "data": data, "generated_at": datetime.utcnow().isoformat()}
    except HTTPException:
        raise
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
        return {"success": True, "message": "Occupancy report generated", "data": data, "generated_at": datetime.utcnow().isoformat()}
    except HTTPException:
        raise
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
        return {"success": True, "message": "Service revenue report generated", "data": data, "generated_at": datetime.utcnow().isoformat()}
    except HTTPException:
        raise
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
        return {"success": True, "message": "Performance report generated", "data": data, "generated_at": datetime.utcnow().isoformat()}
    except HTTPException:
        raise
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
        return {"success": True, "message": "Service provider report generated", "data": data, "generated_at": datetime.utcnow().isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to generate service provider report", "details": {"error": str(e)}})

@router.post("/send-email")
async def send_report_email(payload: dict):
    try:
        recipients = payload.get("recipients", [])
        subject = payload.get("subject", "Report Email")
        message = payload.get("message", "")
        pdf_base64 = payload.get("pdf_base64")
        report_type = payload.get("report_type", "Owner Statement")
        from_date = payload.get("from", "")
        to_date = payload.get("to", "")

        if not recipients:
            raise HTTPException(status_code=400, detail="Recipients are required")

        pdf_bytes = None
        if pdf_base64:
            # Strip data URI prefix if present
            if "," in pdf_base64:
                pdf_base64 = pdf_base64.split(",")[1]
            pdf_bytes = base64.b64decode(pdf_base64)

        # Generate HTML content if message is not provided
        content = message
        if not content:
            content = build_email_html(report_type, from_date, to_date)

        for email in recipients:
            send_email_with_pdf(
                to_email=email,
                subject=subject,
                content=content,
                pdf_bytes=pdf_bytes
            )

        return {"success": True, "message": f"Report email sent to {len(recipients)} recipients"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/scheduled")
async def get_scheduled_reports(service: ReportService = Depends(get_report_service)):
    try:
        data = await service.get_scheduled_reports()
        return {"success": True, "message": "Scheduled reports retrieved", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to fetch scheduled reports", "details": {"error": str(e)}})

@router.post("/scheduled")
async def create_scheduled_report(payload: dict, service: ReportService = Depends(get_report_service)):
    try:
        data = await service.create_scheduled_report(payload)
        return {"success": True, "message": "Report scheduled", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to schedule report", "details": {"error": str(e)}})

@router.delete("/scheduled/{report_id}")
async def delete_scheduled_report(report_id: int, service: ReportService = Depends(get_report_service)):
    try:
        await service.delete_scheduled_report(report_id)
        return {"success": True, "message": "Scheduled report deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to delete scheduled report", "details": {"error": str(e)}})

@router.patch("/scheduled/{report_id}")
async def toggle_scheduled_report(report_id: int, payload: dict, service: ReportService = Depends(get_report_service)):
    try:
        is_active = payload.get("is_active", True)
        await service.toggle_scheduled_report(report_id, is_active)
        return {"success": True, "message": f"Report {'activated' if is_active else 'deactivated'}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to update report status", "details": {"error": str(e)}})


@router.get("/internal/run-scheduled-reports")
async def run_scheduled_reports(service: ReportService = Depends(get_report_service)):
    try:
        await service.run_scheduled_reports()
        return {"success": True, "message": "Scheduled reports executed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))