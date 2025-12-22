from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any, Dict
from ..services.service_category_service import ServiceCategoryService

router = APIRouter(prefix="/service-categories", tags=["service-categories"])

def get_service():
    return ServiceCategoryService()

class ServiceCategoryCreate(BaseModel):
    model_config = ConfigDict(extra="allow")
    category_name: str = Field(..., description="Service category name")
    time: Optional[str] = Field(None, description="Duration or time")
    price: Optional[float] = Field(None, description="Default price")
    status: bool = Field(True, description="Active status")
    email: Optional[str] = Field(None, description="Provider email for notifications")
    phone: Optional[str] = Field(None, description="Provider phone for notifications")

class ServiceCategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")
    category_name: Optional[str] = Field(None)
    time: Optional[str] = Field(None)
    price: Optional[float] = Field(None)
    status: Optional[bool] = Field(None)
    email: Optional[str] = Field(None)
    phone: Optional[str] = Field(None)

class ServiceCategoryStatusUpdate(BaseModel):
    status: bool = Field(..., description="New status value")

class ServiceCategoryResponse(BaseModel):
    success: bool
    message: str
    data: Any

@router.post("", response_model=ServiceCategoryResponse)
def create_service_category(
    data: ServiceCategoryCreate,
    service: ServiceCategoryService = Depends(get_service)
):
    try:
        result = service.create_category(data.model_dump())
        return {"success": True, "message": "Service category created", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{category_id}/status", response_model=ServiceCategoryResponse)
def update_service_category_status(
    category_id: str,
    data: ServiceCategoryStatusUpdate,
    service: ServiceCategoryService = Depends(get_service)
):
    try:
        result = service.update_status(category_id, data.status)
        return {"success": True, "message": "Service category status updated", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=ServiceCategoryResponse)
def list_service_categories(service: ServiceCategoryService = Depends(get_service)):
    try:
        result = service.list_categories()
        return {"success": True, "message": "Service categories list", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{category_id}", response_model=ServiceCategoryResponse)
def get_service_category(
    category_id: str,
    service: ServiceCategoryService = Depends(get_service)
):
    try:
        result = service.get_category(category_id)
        if not result:
            raise HTTPException(status_code=404, detail="Service category not found")
        return {"success": True, "message": "Service category details", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{category_id}", response_model=ServiceCategoryResponse)
def replace_service_category(
    category_id: str,
    data: ServiceCategoryUpdate,
    service: ServiceCategoryService = Depends(get_service)
):
    try:
        # PUT conceptually replaces, but here we'll map it to update for flexibility
        # unless strict replacement is required. Using update_category handles both.
        result = service.update_category(category_id, data.model_dump(exclude_unset=True))
        return {"success": True, "message": "Service category updated", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{category_id}", response_model=ServiceCategoryResponse)
def update_service_category(
    category_id: str,
    data: ServiceCategoryUpdate,
    service: ServiceCategoryService = Depends(get_service)
):
    try:
        result = service.update_category(category_id, data.model_dump(exclude_unset=True))
        return {"success": True, "message": "Service category updated", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
