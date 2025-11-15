from fastapi import APIRouter, Depends, HTTPException
from ..services.user_service import UserService
from ..models import UserRequest, UserUpdateRequest, UserResponse, UserListResponse, ErrorResponse
from ..dependencies import get_user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, responses={500: {"model": ErrorResponse}})
async def create_or_update_user(payload: UserRequest, service: UserService = Depends(get_user_service)):
    try:
        data = service.save_user(payload.email, payload.password)
        return {"success": True, "message": "User saved", "data": {"email": data["email"]}}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to save user", "details": {"error": str(e)}})


@router.put("/{email}", response_model=UserResponse, responses={500: {"model": ErrorResponse}})
async def update_user_password(email: str, payload: UserUpdateRequest, service: UserService = Depends(get_user_service)):
    try:
        service.update_password(email, payload.password)
        return {"success": True, "message": "Password updated", "data": {"email": email}}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to update password", "details": {"error": str(e)}})


@router.get("", response_model=UserListResponse, responses={500: {"model": ErrorResponse}})
async def list_users(service: UserService = Depends(get_user_service)):
    try:
        users = service.list_users()
        return {"success": True, "message": "Users retrieved", "data": users}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to fetch users", "details": {"error": str(e)}})


@router.delete("/{email}", response_model=UserResponse, responses={500: {"model": ErrorResponse}})
async def delete_user(email: str, service: UserService = Depends(get_user_service)):
    try:
        service.delete_user(email)
        return {"success": True, "message": "User deleted", "data": {"email": email}}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to delete user", "details": {"error": str(e)}})