import os
import base64
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet

from ...supabase_sync.supabase_client import SupabaseClient
from config.settings import app_config, supabase_config


class UserService:
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

    def save_user(self, email: str, password: str) -> Dict[str, Any]:
        if not self.supabase.initialized:
            if not self.supabase.initialize():
                raise RuntimeError("Supabase initialization failed")

        encrypted = self.encrypt(password)
        payload = {"email": email, "password": encrypted}

        existing = (
            self.supabase.client
            .table(app_config.users_collection)
            .select("email")
            .eq("email", email)
            .limit(1)
            .execute()
        )

        if existing.data:
            (
                self.supabase.client
                .table(app_config.users_collection)
                .update({"password": encrypted})
                .eq("email", email)
                .execute()
            )
            return {"email": email, "password": encrypted}
        else:
            insert_result = (
                self.supabase.client
                .table(app_config.users_collection)
                .insert(payload)
                .execute()
            )
            data = insert_result.data[0] if insert_result.data else payload
            return {"email": data.get("email"), "password": data.get("password")}

    def update_password(self, email: str, password: str) -> bool:
        if not self.supabase.initialized:
            if not self.supabase.initialize():
                raise RuntimeError("Supabase initialization failed")

        encrypted = self.encrypt(password)
        (
            self.supabase.client
            .table(app_config.users_collection)
            .update({"password": encrypted})
            .eq("email", email)
            .execute()
        )
        return True

    def update_status(self, email: str, status: str) -> bool:
        if not self.supabase.initialized:
            if not self.supabase.initialize():
                raise RuntimeError("Supabase initialization failed")

        (
            self.supabase.client
            .table(app_config.users_collection)
            .update({"status": status})
            .eq("email", email)
            .execute()
        )
        return True

    def get_user(self, email: str) -> Optional[Dict[str, Any]]:
        if not self.supabase.initialized:
            if not self.supabase.initialize():
                raise RuntimeError("Supabase initialization failed")

        result = (
            self.supabase.client
            .table(app_config.users_collection)
            .select("email,password")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        return None

    def list_users(self, limit: int = 50, offset: int = 0) -> list[Dict[str, Any]]:
        if not self.supabase.initialized:
            if not self.supabase.initialize():
                raise RuntimeError("Supabase initialization failed")

        result = (
            self.supabase.client
            .table(app_config.users_collection)
            .select("email,status")
            .range(offset, offset + max(0, limit) - 1)
            .execute()
        )
        return result.data or []

    def delete_user(self, email: str) -> bool:
        if not self.supabase.initialized:
            if not self.supabase.initialize():
                raise RuntimeError("Supabase initialization failed")

        (
            self.supabase.client
            .table(app_config.users_collection)
            .delete()
            .eq("email", email)
            .execute()
        )
        return True