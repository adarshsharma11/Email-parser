import os
import base64
from typing import Optional, Dict, Any, List
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime

from config.settings import app_config, supabase_config


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.fernet = self._build_fernet()

    def _build_fernet(self) -> Fernet:
        # We keep using the same encryption logic for compatibility with existing passwords
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

    async def save_user(self, email: str, password: str, platform: Optional[str] = None) -> Dict[str, Any]:
        encrypted = self.encrypt(password)
        
        # Check if user exists
        check_query = text(f"SELECT email, platform FROM {app_config.users_collection} WHERE email = :email" + 
                          (" AND platform = :platform" if platform else ""))
        params = {"email": email}
        if platform:
            params["platform"] = platform
            
        result = await self.session.execute(check_query, params)
        existing = result.fetchone()

        if existing:
            # Update existing user
            update_query = text(f"UPDATE {app_config.users_collection} SET password = :password, updated_at = :updated_at" + 
                               (", platform = :platform" if platform else "") + 
                               " WHERE email = :email")
            update_params = {"password": encrypted, "email": email, "updated_at": datetime.utcnow()}
            if platform:
                update_params["platform"] = platform
            await self.session.execute(update_query, update_params)
            return {"email": email, "password": encrypted}
        else:
            # Insert new user
            columns = ["email", "password"]
            placeholders = [":email", ":password"]
            insert_params = {"email": email, "password": encrypted}
            
            if platform:
                columns.append("platform")
                placeholders.append(":platform")
                insert_params["platform"] = platform
                
            insert_query = text(f"INSERT INTO {app_config.users_collection} ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) RETURNING *")
            result = await self.session.execute(insert_query, insert_params)
            row = result.fetchone()
            data = dict(row._mapping) if row else {"email": email, "password": encrypted}
            return {"email": data.get("email"), "password": data.get("password")}

    async def update_password(self, email: str, password: str, platform: Optional[str] = None) -> bool:
        encrypted = self.encrypt(password)
        query_str = f"UPDATE {app_config.users_collection} SET password = :password, updated_at = :updated_at WHERE email = :email"
        params = {"password": encrypted, "email": email, "updated_at": datetime.utcnow()}
        if platform:
            query_str += " AND platform = :platform"
            params["platform"] = platform
            
        await self.session.execute(text(query_str), params)
        return True

    async def update_status(self, email: str, status: str) -> bool:
        query = text(f"UPDATE {app_config.users_collection} SET status = :status, updated_at = :updated_at WHERE email = :email")
        await self.session.execute(query, {"status": status, "email": email, "updated_at": datetime.utcnow()})
        return True

    async def get_user(self, email: str, platform: Optional[str] = None) -> Optional[Dict[str, Any]]:
        query_str = f"SELECT email, password, platform FROM {app_config.users_collection} WHERE email = :email"
        params = {"email": email}
        if platform:
            query_str += " AND platform = :platform"
            params["platform"] = platform
            
        result = await self.session.execute(text(query_str), params)
        row = result.fetchone()
        if row:
            return dict(row._mapping)
        return None

    async def list_active_users(self) -> List[Dict[str, Any]]:
        query = text(f"SELECT email, password, platform FROM {app_config.users_collection} WHERE status = 'active'")
        result = await self.session.execute(query)
        rows = result.fetchall()
        return [dict(row._mapping) for row in rows]

    async def list_users(self) -> List[Dict[str, Any]]:
        query = text(f"SELECT email, password, status, platform, created_at FROM {app_config.users_collection}")
        result = await self.session.execute(query)
        rows = result.fetchall()
        return [dict(row._mapping) for row in rows]

    async def delete_user(self, email: str, platform: Optional[str] = None) -> bool:
        query_str = f"DELETE FROM {app_config.users_collection} WHERE email = :email"
        params = {"email": email}
        if platform:
            query_str += " AND platform = :platform"
            params["platform"] = platform
            
        await self.session.execute(text(query_str), params)
        return True
