import os
import base64
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet

from ...supabase_sync.supabase_client import SupabaseClient
from config.settings import supabase_config


class AuthService:
    def __init__(self):
        self.supabase = SupabaseClient()
        self.fernet = self._build_fernet()

    def _build_fernet(self) -> Fernet:
        secret = os.getenv("ENCRYPTION_SECRET") or supabase_config.get_auth_key()
        salt = os.getenv("ENCRYPTION_SALT", "email-parser123")
        key = self._derive_key(secret, salt)
        return Fernet(key)

    def _derive_key(self, secret: str, salt: str) -> bytes:
        import hashlib
        raw = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(), 390000, dklen=32)
        return base64.urlsafe_b64encode(raw)

    def encrypt(self, plaintext: str) -> str:
        return self.fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self.fernet.decrypt(token.encode()).decode()

    def save_user(self, email: str, password: str, first_name: Optional[str] = None, last_name: Optional[str] = None) -> Dict[str, Any]:
        if not self.supabase.initialized:
            if not self.supabase.initialize():
                raise RuntimeError("Supabase initialization failed")

        encrypted = self.encrypt(password)
        payload = {"email": email, "password": encrypted}
        if first_name is not None:
            payload["first_name"] = first_name
        if last_name is not None:
            payload["last_name"] = last_name

        existing = (
            self.supabase.client
            .table("users")
            .select("email")
            .eq("email", email)
            .limit(1)
            .execute()
        )

        if existing.data:
            update_data = {"password": encrypted}
            if first_name is not None:
                update_data["first_name"] = first_name
            if last_name is not None:
                update_data["last_name"] = last_name
            (
                self.supabase.client
                .table("users")
                .update(update_data)
                .eq("email", email)
                .execute()
            )
            return {"email": email, "password": encrypted, **({"first_name": first_name} if first_name is not None else {}), **({"last_name": last_name} if last_name is not None else {})}
        else:
            insert_result = (
                self.supabase.client
                .table("users")
                .insert(payload)
                .execute()
            )
            data = insert_result.data[0] if insert_result.data else payload
            return {
                "email": data.get("email"),
                "password": data.get("password"),
                "first_name": data.get("first_name"),
                "last_name": data.get("last_name"),
            }

    def get_user(self, email: str) -> Optional[Dict[str, Any]]:
        if not self.supabase.initialized:
            if not self.supabase.initialize():
                raise RuntimeError("Supabase initialization failed")

        result = (
            self.supabase.client
            .table("users")
            .select("email,password,first_name,last_name")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        return None