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