from fastapi import APIRouter, HTTPException
from ..models import RegisterRequest, LoginRequest, AuthResponse, ErrorResponse
from ..dependencies import get_logger
from ..services.user_service import UserService
from ..security.jwt import create_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def register(req: RegisterRequest):
    logger = get_logger()
    try:
        service = UserService()
        saved = service.save_user(req.email, req.password)
        token = create_token({"sub": req.email})
        logger.info("user_registered", email=req.email)
        return {"success": True, "message": "Registered", "data": {"token": token, "email": req.email}}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Registration failed", "details": {"error": str(e)}})


@router.post("/login", response_model=AuthResponse, responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def login(req: LoginRequest):
    logger = get_logger()
    try:
        service = UserService()
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