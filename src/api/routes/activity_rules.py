"""
API routes for Activity Rules.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from ..models import (
    CreateActivityRuleRequest,
    UpdateActivityRuleRequest,
    ActivityRuleResponse,
    ActivityRuleListResponse,
    ActivityRuleDetailResponse,
    ErrorResponse
)
from ..dependencies import get_activity_rule_service
from ..services.activity_rule_service import ActivityRuleService

router = APIRouter(prefix="/activity-rules", tags=["activity-rules"])

@router.post(
    "",
    response_model=ActivityRuleDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new activity rule",
    responses={
        201: {"description": "Activity rule created successfully"},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def create_activity_rule(
    request: CreateActivityRuleRequest,
    service: ActivityRuleService = Depends(get_activity_rule_service)
):
    """Create a new activity rule."""
    result = service.create_rule(request)
    return {
        "success": True,
        "message": "Activity rule created successfully",
        "data": result
    }

@router.get(
    "",
    response_model=ActivityRuleListResponse,
    summary="List all activity rules",
    responses={
        200: {"description": "Activity rules retrieved successfully"},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def list_activity_rules(
    service: ActivityRuleService = Depends(get_activity_rule_service)
):
    """Get all activity rules."""
    result = service.get_rules()
    return {
        "success": True,
        "message": "Activity rules retrieved successfully",
        "data": result
    }

@router.get(
    "/{rule_id}",
    response_model=ActivityRuleDetailResponse,
    summary="Get a specific activity rule",
    responses={
        200: {"description": "Activity rule retrieved successfully"},
        404: {"description": "Activity rule not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def get_activity_rule(
    rule_id: int,
    service: ActivityRuleService = Depends(get_activity_rule_service)
):
    """Get an activity rule by ID."""
    result = service.get_rule(rule_id)
    return {
        "success": True,
        "message": "Activity rule retrieved successfully",
        "data": result
    }

@router.put(
    "/{rule_id}",
    response_model=ActivityRuleDetailResponse,
    summary="Update an activity rule",
    responses={
        200: {"description": "Activity rule updated successfully"},
        404: {"description": "Activity rule not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def update_activity_rule(
    rule_id: int,
    request: UpdateActivityRuleRequest,
    service: ActivityRuleService = Depends(get_activity_rule_service)
):
    """Update an activity rule."""
    result = service.update_rule(rule_id, request)
    return {
        "success": True,
        "message": "Activity rule updated successfully",
        "data": result
    }

@router.patch(
    "/{rule_id}/status",
    response_model=ActivityRuleDetailResponse,
    summary="Enable or disable an activity rule",
    responses={
        200: {"description": "Activity rule status updated successfully"},
        404: {"description": "Activity rule not found", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse}
    }
)
async def toggle_activity_rule_status(
    rule_id: int,
    enable: bool,
    service: ActivityRuleService = Depends(get_activity_rule_service)
):
    """
    Enable or disable an activity rule.
    
    Args:
        rule_id: ID of the rule
        enable: True to enable, False to disable
    """
    result = service.toggle_status(rule_id, enable)
    return {
        "success": True,
        "message": f"Activity rule {'enabled' if enable else 'disabled'} successfully",
        "data": result
    }
