from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field, ConfigDict
from ..services.category_service import CategoryService
from ..dependencies import get_category_service

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryCreateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = Field(..., description="Category name")
    parent_id: int | None = Field(None, description="Parent category ID")


class CategoryResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    success: bool
    message: str
    data: dict


@router.post(
    "",
    response_model=CategoryResponse,
    responses={
        400: {"description": "Bad Request"},
        500: {"description": "Server Error"},
    },
)
async def create_category(req: CategoryCreateRequest, service: CategoryService = Depends(get_category_service)):
    try:
        created = await service.create_category(req.name, req.parent_id)
        return {
            "success": True,
            "message": "Category created",
            "data": created,
        }
    except ValueError as ve:
        if str(ve) == "PARENT_NOT_FOUND":
            raise HTTPException(
                status_code=400,
                detail={"message": "Parent category not found"},
            )
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to create category",
                "details": {"error": str(e)},
            },
        )


@router.get("/tree", response_model=CategoryResponse)
async def get_category_tree(service: CategoryService = Depends(get_category_service)):
    try:
        tree = await service.get_category_tree()
        return {
            "success": True,
            "message": "Category Tree",
            "data": {"tree": tree},
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to get category tree",
                "details": {"error": str(e)},
            },
        )


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(category_id: int, service: CategoryService = Depends(get_category_service)):
    try:
        item = await service.get_category(category_id)
        if not item:
            raise HTTPException(
                status_code=404,
                detail={"message": "Category not found"},
            )
        return {
            "success": True,
            "message": "Category",
            "data": item,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to get category",
                "details": {"error": str(e)},
            },
        )


@router.get("", response_model=CategoryResponse)
async def list_children(parent_id: int | None = Query(None), service: CategoryService = Depends(get_category_service)):
    try:
        items = await service.list_children(parent_id)
        return {
            "success": True,
            "message": "Categories",
            "data": {"categories": items},
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to list categories",
                "details": {"error": str(e)},
            },
        )
