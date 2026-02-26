import os
import base64
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime

from config.settings import supabase_config


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
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

    async def save_user(self, email: str, password: str, first_name: Optional[str] = None, last_name: Optional[str] = None) -> Dict[str, Any]:
        encrypted = self.encrypt(password)
        payload = {"email": email, "password": encrypted}
        if first_name is not None:
            payload["first_name"] = first_name
        if last_name is not None:
            payload["last_name"] = last_name

        # Check if email exists
        check_query = text("SELECT email FROM users WHERE email = :email LIMIT 1")
        result = await self.session.execute(check_query, {"email": email})
        if result.fetchone():
            raise ValueError("EMAIL_ALREADY_REGISTERED")
            
        # Insert new user
        columns = ", ".join(payload.keys())
        placeholders = ", ".join([f":{k}" for k in payload.keys()])
        insert_query = text(f"INSERT INTO users ({columns}) VALUES ({placeholders}) RETURNING *")
        
        result = await self.session.execute(insert_query, payload)
        row = result.fetchone()
        
        if not row:
            raise Exception("Failed to save user")
            
        data = dict(row._mapping)
        return {
            "email": data.get("email"),
            "password": data.get("password"),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
        }

    async def get_user(self, email: str) -> Optional[Dict[str, Any]]:
        query = text("SELECT email, password, first_name, last_name FROM users WHERE email = :email LIMIT 1")
        result = await self.session.execute(query, {"email": email})
        row = result.fetchone()
        if row:
            return dict(row._mapping)
        return None

    async def update_profile(self, email: str, first_name: str, last_name: str) -> Dict[str, Any]:
        query = text("UPDATE users SET first_name = :first_name, last_name = :last_name, updated_at = :updated_at WHERE email = :email RETURNING *")
        result = await self.session.execute(query, {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "updated_at": datetime.utcnow()
        })
        row = result.fetchone()
        if not row:
            raise Exception("User not found")
        return dict(row._mapping)

    async def update_password(self, email: str, password: str) -> bool:
        encrypted = self.encrypt(password)
        query = text("UPDATE users SET password = :password, updated_at = :updated_at WHERE email = :email")
        await self.session.execute(query, {
            "password": encrypted,
            "email": email,
            "updated_at": datetime.utcnow()
        })
        return True
