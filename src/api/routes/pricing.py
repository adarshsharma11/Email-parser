from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
from ..dependencies import get_db_session, get_auth_service
from ..services.pricing_service import PricingService
from ..models import (
    PricingSettings, 
    PricingSettingsResponse, 
    PricingRuleListResponse, 
    CreatePricingRuleRequest, 
    PricingRuleDetailResponse,
    APIResponse,
    ErrorResponse
)

router = APIRouter(prefix="/pricing", tags=["pricing"])

@router.get("/settings", response_model=PricingSettingsResponse)
async def get_settings(session = Depends(get_db_session)):
    try:
        service = PricingService(session)
        data = await service.get_settings()
        return {"success": True, "message": "Settings retrieved", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to fetch settings", "error": str(e)})

@router.post("/settings", response_model=PricingSettingsResponse)
async def update_settings(settings: PricingSettings, session = Depends(get_db_session)):
    try:
        service = PricingService(session)
        data = await service.update_settings(settings)
        return {"success": True, "message": "Settings updated", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to update settings", "error": str(e)})

@router.get("/rules", response_model=PricingRuleListResponse)
async def list_rules(property_id: Optional[str] = None, session = Depends(get_db_session)):
    try:
        service = PricingService(session)
        data = await service.list_rules(property_id)
        return {"success": True, "message": "Rules retrieved", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to fetch rules", "error": str(e)})

@router.post("/rules", response_model=PricingRuleDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(rule: CreatePricingRuleRequest, session = Depends(get_db_session)):
    try:
        service = PricingService(session)
        data = await service.create_rule(rule)
        return {"success": True, "message": "Rule created", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to create rule", "error": str(e)})

@router.delete("/rules/{rule_id}", response_model=APIResponse)
async def delete_rule(rule_id: int, session = Depends(get_db_session)):
    try:
        service = PricingService(session)
        await service.delete_rule(rule_id)
        return {"success": True, "message": "Rule deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to delete rule", "error": str(e)})
