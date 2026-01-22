from fastapi import APIRouter, Depends, HTTPException
from ..services.user_service import UserService
from ..models import UserRequest, UserUpdateRequest, UserResponse, UserListResponse, ConnectionResponse, ErrorResponse
from ..dependencies import get_user_service
from ...email_reader.gmail_client import GmailClient
from cryptography.fernet import InvalidToken

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, responses={500: {"model": ErrorResponse}})
async def create_or_update_user(payload: UserRequest, service: UserService = Depends(get_user_service)):
    try:
        plat = payload.platform.value if payload.platform else None
        data = service.save_user(payload.email, payload.password, platform=plat)
        return {"success": True, "message": "User saved", "data": {"email": data["email"]}}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to save user", "details": {"error": str(e)}})


@router.put("/{email}", response_model=UserResponse, responses={500: {"model": ErrorResponse}})
async def update_user(email: str, payload: UserUpdateRequest, service: UserService = Depends(get_user_service)):
    try:
        plat = payload.platform.value if payload.platform else None
        service.update_user(email, new_email=payload.new_email, password=payload.password, platform=plat)
        return {"success": True, "message": "User updated", "data": {"email": payload.new_email or email}}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to update user", "details": {"error": str(e)}})

@router.put("/platform/{platform}", response_model=UserResponse, responses={500: {"model": ErrorResponse}})
async def update_by_platform(platform: str, payload: UserRequest, service: UserService = Depends(get_user_service)):
    try:
        service.update_by_platform(platform, payload.email, payload.password)
        return {"success": True, "message": "User updated", "data": {"platform": platform, "email": payload.email}}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to update user by platform", "details": {"error": str(e)}})

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


@router.post("/{email}/connect", response_model=ConnectionResponse, responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def connect_user_email(email: str, service: UserService = Depends(get_user_service)):
    try:
        user = service.get_user(email)
        if not user:
            raise HTTPException(status_code=404, detail={"message": "User not found"})
        decrypted = None
        if user.get("password"):
            try:
                decrypted = service.decrypt(user["password"])
            except InvalidToken:
                service.update_status(email, "inactive")
                raise HTTPException(status_code=400, detail={"message": "Invalid encrypted password for user"})
        if not decrypted:
            service.update_status(email, "inactive")
            raise HTTPException(status_code=400, detail={"message": "Password missing for user"})

        client = GmailClient()
        ok = client.connect_with_credentials(email, decrypted)
        service.update_status(email, "active" if ok else "inactive")
        return {"success": ok, "message": "Connection successful" if ok else "Connection failed", "data": {"email": email, "connected": ok}}
    except HTTPException:
        raise
    except Exception as e:
        try:
            service.update_status(email, "inactive")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail={"message": "Failed to connect to Gmail", "details": {"error": str(e)}})


@router.post("/{email}/deactivate", response_model=UserResponse, responses={500: {"model": ErrorResponse}})
async def deactivate_user(email: str, service: UserService = Depends(get_user_service)):
    try:
        service.update_status(email, "inactive")
        return {"success": True, "message": "User deactivated", "data": {"email": email}}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to update status", "details": {"error": str(e)}})
