from fastapi import APIRouter, HTTPException
from fastapi import Request
from ..models import RegisterRequest, LoginRequest, AuthResponse, ErrorResponse, ProfileUpdateRequest
from ..dependencies import get_logger
from ..services.auth_service import AuthService
from ..security.jwt import create_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def register(req: RegisterRequest):
    logger = get_logger()
    try:
        service = AuthService()
        saved = service.save_user(req.email, req.password, req.first_name, req.last_name)
        token = create_token({"sub": req.email}, exp_seconds=86400)
        logger.info("user_registered", email=req.email)
        return {"success": True, "message": "Registered", "data": {"token": token, "email": req.email}}
    except ValueError as ve:
        if str(ve) == "EMAIL_ALREADY_REGISTERED":
            raise HTTPException(status_code=400, detail={"message": "Email already registered"})
        raise HTTPException(status_code=400, detail={"message": "Invalid registration data", "details": {"error": str(ve)}})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Registration failed", "details": {"error": str(e)}})


@router.post("/login", response_model=AuthResponse, responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def login(req: LoginRequest):
    logger = get_logger()
    try:
        service = AuthService()
        user = service.get_user(req.email)
        if not user:
            raise HTTPException(status_code=401, detail={"message": "Invalid credentials"})
        try:
            stored = user.get("password")
            decrypted = service.decrypt(stored)
        except Exception:
            raise HTTPException(status_code=401, detail={"message": "Invalid credentials"})
        if decrypted != req.password:
            raise HTTPException(status_code=401, detail={"message": "Invalid credentials"})
        token = create_token({"sub": req.email}, exp_seconds=86400)
        logger.info("user_logged_in", email=req.email)
        return {
            "success": True,
            "message": "Logged in",
            "data": {
                "token": token,
                "email": req.email,
                "first_name": user.get("first_name"),
                "last_name": user.get("last_name"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Login failed", "details": {"error": str(e)}})


@router.post("/logout", response_model=AuthResponse, responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def logout(request: Request):
    logger = get_logger()
    try:
        email = getattr(request.state, "user_email", None)
        logger.info("user_logged_out", email=email)
        return {"success": True, "message": "Logged out", "data": {"email": email, "logged_out": True}}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Logout failed", "details": {"error": str(e)}})


@router.put("/profile", response_model=AuthResponse, responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def update_profile(req: ProfileUpdateRequest, request: Request):
    logger = get_logger()
    try:
        email = getattr(request.state, "user_email", None)
        if not email:
            raise HTTPException(status_code=401, detail={"message": "Unauthorized"})
        service = AuthService()
        updated = service.update_profile(email, req.first_name, req.last_name)
        logger.info("user_profile_updated", email=email)
        return {"success": True, "message": "Profile updated", "data": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Profile update failed", "details": {"error": str(e)}})