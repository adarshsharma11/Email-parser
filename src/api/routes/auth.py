from fastapi import APIRouter, HTTPException
import os
from fastapi import Request
from ..models import RegisterRequest, LoginRequest, AuthResponse, ErrorResponse, ProfileUpdateRequest, ForgotPasswordRequest, ResetPasswordRequest
from ..dependencies import get_logger
from ..services.auth_service import AuthService
from ...guest_communications.email_client import EmailClient
from ..security.jwt import create_token
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

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


@router.post("/forgot-password", response_model=AuthResponse, responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def forgot_password(req: ForgotPasswordRequest):
    logger = get_logger()
    try:
        service = AuthService()
        user = service.get_user(req.email)
        if not user:
            raise HTTPException(status_code=400, detail={"message": "Email not found"})
        exp = int(os.getenv("PASSWORD_RESET_EXP_SECONDS", "1800"))
        token = create_token({"sub": req.email, "scope": "password_reset"}, exp_seconds=exp)
        reset_base = os.getenv("PASSWORD_RESET_URL") or os.getenv("FRONTEND_RESET_URL") or "https://email-parser-frontend-lyart.vercel.app/reset-password"
        parsed = urlparse(reset_base)
        existing_qs = parse_qs(parsed.query)
        existing_qs["token"] = [token]
        new_query = urlencode(existing_qs, doseq=True)
        link = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
        subject = "Password Reset"
        body = (
            f"""
            <div style=\"font-family:Arial,sans-serif;line-height:1.6;color:#222\">
              <p>We received a request to reset your password.</p>
              <p>Please click the button below to set a new password:</p>
              <p>
                <a href=\"{link}\" style=\"display:inline-block;padding:10px 16px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-weight:600\">
                  Reset Password
                </a>
              </p>
              <p style=\"font-size:12px;color:#666\">This link expires soon. If you did not request this, you can ignore this email.</p>
            </div>
            """
        )
        email_client = EmailClient()
        email_client.send(to=req.email, subject=subject, body=body, html=True)
        logger.info("password_reset_requested", email=req.email)
        return {
            "success": True,
            "message": "Password reset email sent",
            "data": {"email": req.email, "reset_url": link},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to generate reset token", "details": {"error": str(e)}})


@router.post("/reset-password", response_model=AuthResponse, responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def reset_password(req: ResetPasswordRequest):
    logger = get_logger()
    try:
        from ..security.jwt import verify_token
        payload = verify_token(req.token)
        if payload.get("scope") != "password_reset":
            raise HTTPException(status_code=400, detail={"message": "Invalid reset token"})
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=400, detail={"message": "Invalid reset token"})
        service = AuthService()
        ok = service.update_password(email, req.new_password)
        logger.info("password_reset_completed", email=email)
        return {"success": ok, "message": "Password reset successful" if ok else "Password reset failed", "data": {"email": email}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Failed to reset password", "details": {"error": str(e)}})