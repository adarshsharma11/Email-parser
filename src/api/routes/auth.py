from fastapi import APIRouter, HTTPException
from fastapi import Request
from ..models import RegisterRequest, LoginRequest, AuthResponse, ErrorResponse
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
        token = create_token({"sub": req.email})
        logger.info("user_registered", email=req.email)
        return {"success": True, "message": "Registered", "data": {"token": token, "email": req.email}}
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
        token = create_token({"sub": req.email})
        logger.info("user_logged_in", email=req.email)
        return {"success": True, "message": "Logged in", "data": {"token": token, "email": req.email}}
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