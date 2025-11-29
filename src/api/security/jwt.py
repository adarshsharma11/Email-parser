import os
import time
import hmac
import json
import base64
import hashlib
from typing import Dict, Any, Optional


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(payload: Dict[str, Any], exp_seconds: Optional[int] = None) -> str:
    secret = os.getenv("JWT_SECRET") or os.getenv("ENCRYPTION_SECRET") or "change-me"
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    exp = now + int(exp_seconds or int(os.getenv("JWT_EXP_SECONDS", "86400")))
    body = dict[str, Any](payload)
    body.setdefault("iat", now)
    body.setdefault("exp", exp)

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url_encode(json.dumps(body, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_token(token: str) -> Dict[str, Any]:
    secret = os.getenv("JWT_SECRET") or os.getenv("ENCRYPTION_SECRET") or "change-me"
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise ValueError("Invalid token format")

    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected_sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_sig, _b64url_decode(sig_b64)):
        raise ValueError("Invalid token signature")

    payload = json.loads(_b64url_decode(payload_b64).decode())
    if int(time.time()) >= int(payload.get("exp", 0)):
        raise ValueError("Token expired")
    return payload