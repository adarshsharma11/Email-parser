from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from ..models import PricingSettings, CreatePricingRuleRequest, PricingRuleResponse

class PricingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings_table = "pricing_settings"
        self.rules_table = "pricing_rules"

    async def get_settings(self) -> PricingSettings:
        query = text(f"SELECT weekend_boost, seasonal_strength, island_discount, updated_at FROM {self.settings_table} LIMIT 1")
        result = await self.session.execute(query)
        row = result.fetchone()
        if not row:
            # Default settings if none exist
            return PricingSettings(weekend_boost=20.0, seasonal_strength=75.0, island_discount=10.0)
        return PricingSettings(**dict(row._mapping))

    async def update_settings(self, settings: PricingSettings) -> PricingSettings:
        # Update or Insert
        query = text(f"""
            INSERT INTO {self.settings_table} (id, weekend_boost, seasonal_strength, island_discount, updated_at)
            VALUES (1, :wb, :ss, :id, :ua)
            ON CONFLICT (id) DO UPDATE SET
                weekend_boost = EXCLUDED.weekend_boost,
                seasonal_strength = EXCLUDED.seasonal_strength,
                island_discount = EXCLUDED.island_discount,
                updated_at = EXCLUDED.updated_at
            RETURNING *
        """)
        params = {
            "wb": settings.weekend_boost,
            "ss": settings.seasonal_strength,
            "id": settings.island_discount,
            "ua": datetime.utcnow()
        }
        result = await self.session.execute(query, params)
        row = result.fetchone()
        if not row:
            raise Exception("Failed to update pricing settings")
        return PricingSettings(**dict(row._mapping))

    async def list_rules(self, property_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query_str = f"SELECT * FROM {self.rules_table}"
        params = {}
        if property_id:
            query_str += " WHERE property_id = :pid OR property_id IS NULL"
            params["pid"] = property_id
        
        query_str += " ORDER BY created_at DESC"
        result = await self.session.execute(text(query_str), params)
        return [dict(row._mapping) for row in result.fetchall()]

    async def create_rule(self, rule: CreatePricingRuleRequest) -> Dict[str, Any]:
        payload = rule.model_dump(exclude_unset=True)
        columns = ", ".join(payload.keys())
        placeholders = ", ".join([f":{k}" for k in payload.keys()])
        query = text(f"INSERT INTO {self.rules_table} ({columns}) VALUES ({placeholders}) RETURNING *")
        result = await self.session.execute(query, payload)
        row = result.fetchone()
        if not row:
            raise Exception("Failed to create pricing rule")
        return dict(row._mapping)

    async def delete_rule(self, rule_id: int) -> bool:
        query = text(f"DELETE FROM {self.rules_table} WHERE id = :id")
        await self.session.execute(query, {"id": rule_id})
        return True
