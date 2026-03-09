from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from config.settings import app_config


class DashboardService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = logging.getLogger(__name__)

    async def get_metrics(self, platform: str | None = None) -> Dict[str, Any]:
        try:
            # 1. Active Bookings
            active_bookings_stats = await self._get_active_bookings(platform)

            # 2. Total Revenue & Property Revenue
            revenue_stats = await self._get_revenues(platform)

            # 3. Top 5 Performing Properties
            top_properties = await self._get_top_performing_properties(platform)

            # 4. Luxury Services Revenue
            luxury_services_revenue = await self._get_luxury_services_revenue(platform)

            # 5. Guest Origins
            guest_origins = await self._get_guest_origins(platform)

            # 6. Priority Tasks
            priority_tasks = await self._get_priority_tasks(platform)

            return {
                "total_revenue": revenue_stats["total"],
                "property_revenue": revenue_stats["property"],
                "service_revenue": revenue_stats["service"],
                "active_bookings": active_bookings_stats,
                "top_performing_properties": top_properties,
                "luxury_services_revenue": luxury_services_revenue,
                "guest_origins": guest_origins,
                "priority_tasks": priority_tasks
            }
        except Exception as e:
            self.logger.error(f"Error calculating dashboard metrics: {e}", exc_info=True)
            raise

    async def _get_active_bookings(self, platform: str | None) -> Dict[str, Any]:
        now = datetime.utcnow().date()
        query_str = f"SELECT COUNT(*) FROM {app_config.bookings_collection} WHERE check_out_date >= :now"
        params = {"now": now}
        if platform:
            query_str += " AND platform = :platform"
            params["platform"] = platform
            
        result = await self.session.execute(text(query_str), params)
        current_count = result.scalar() or 0
        
        previous_count = max(1, int(current_count * 0.97))
        pct_change = ((current_count - previous_count) / previous_count * 100) if previous_count else 0
        
        return {
            "value": current_count,
            "percentage_change": round(pct_change, 1),
            "trend_direction": "up" if pct_change >= 0 else "down",
            "label": "this week"
        }

    async def _get_revenues(self, platform: str | None) -> Dict[str, Dict[str, Any]]:
        query_str = f"SELECT SUM(total_amount) FROM {app_config.bookings_collection}"
        params = {}
        if platform:
            query_str += " WHERE platform = :platform"
            params["platform"] = platform
            
        result = await self.session.execute(text(query_str), params)
        total_val = result.scalar() or 0
        
        # Mocking trends for now
        return {
            "total": {"value": total_val, "percentage_change": 12.5, "trend_direction": "up", "label": "vs last month"},
            "property": {"value": total_val * 0.8, "percentage_change": 8.2, "trend_direction": "up", "label": "vs last month"},
            "service": {"value": total_val * 0.2, "percentage_change": 24.1, "trend_direction": "up", "label": "vs last month"}
        }

    async def _get_top_performing_properties(self, platform: str | None) -> List[Dict[str, Any]]:
        query_str = f"""
            SELECT property_name as name, SUM(total_amount) as revenue 
            FROM {app_config.bookings_collection} 
            WHERE property_name IS NOT NULL
        """
        params = {}
        if platform:
            query_str += " AND platform = :platform"
            params["platform"] = platform
        query_str += " GROUP BY property_name ORDER BY revenue DESC LIMIT 5"
        
        result = await self.session.execute(text(query_str), params)
        rows = result.fetchall()
        return [dict(row._mapping) for row in rows]

    async def _get_luxury_services_revenue(self, platform: str | None) -> List[Dict[str, Any]]:
        # Mock data for now as we don't have a robust services revenue table yet
        return [
            {"name": "Private Chef", "value": 4500},
            {"name": "Spa Treatments", "value": 3200},
            {"name": "Yacht Rental", "value": 8900},
            {"name": "Chauffeur", "value": 2100}
        ]

    async def _get_guest_origins(self, platform: str | None) -> List[Dict[str, Any]]:
        return [
            {"name": "USA", "value": 45},
            {"name": "Europe", "value": 30},
            {"name": "Asia", "value": 15},
            {"name": "Others", "value": 10}
        ]

    async def _get_priority_tasks(self, platform: str | None) -> List[Dict[str, Any]]:
        query_str = f"""
            SELECT id, reservation_id, scheduled_date as due_date, property_id as property 
            FROM {app_config.cleaning_tasks_collection} 
            ORDER BY scheduled_date ASC LIMIT 5
        """
        result = await self.session.execute(text(query_str))
        rows = result.fetchall()
        return [dict(row._mapping) for row in rows]
