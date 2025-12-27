from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, List
from pydantic import BaseModel

from ..dependencies import get_automation_service
from ..services.automation_service import AutomationService

router = APIRouter(
    prefix="/automation",
    tags=["Automation"]
)

class RuleToggleRequest(BaseModel):
    enabled: bool

class RuleResponse(BaseModel):
    name: str
    enabled: bool

class RulesListResponse(BaseModel):
    rules: List[RuleResponse]

@router.get(
    "/rules",
    response_model=RulesListResponse,
    summary="Get all automation rules",
    description="Get the status of all automation rules"
)
async def get_rules(
    service: AutomationService = Depends(get_automation_service)
):
    rules = service.get_all_rules()
    return {
        "rules": [
            {"name": name, "enabled": enabled}
            for name, enabled in rules.items()
        ]
    }

@router.post(
    "/rules/{rule_name}/toggle",
    response_model=RuleResponse,
    summary="Toggle an automation rule",
    description="Enable or disable a specific automation rule"
)
async def toggle_rule(
    rule_name: str,
    request: RuleToggleRequest,
    service: AutomationService = Depends(get_automation_service)
):
    # Verify rule exists in current rules (optional, but good practice)
    current_rules = service.get_all_rules()
    # Note: AutomationService currently allows adding new rules dynamically via toggle,
    # but we might want to restrict to known rules if strict validation is needed.
    # For now, we'll allow it as the service handles persistence.
    
    updated_rules = service.toggle_rule(rule_name, request.enabled)
    
    return {
        "name": rule_name,
        "enabled": updated_rules.get(rule_name, request.enabled)
    }
