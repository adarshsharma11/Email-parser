from datetime import datetime
from typing import Dict, Any, List
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class DashboardService:

    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = logging.getLogger(__name__)

    async def get_metrics(self, platform: str | None = None):

        revenue_total = await self._get_total_revenue(platform)
        active = await self._get_active_bookings(platform)
        properties = await self._get_top_properties(platform)
        services = await self._get_services_revenue()

        metric_template = {
            "percentage_change": 0,
            "trend_direction": "up",
            "label": "vs last period"
        }

        return {
            "total_revenue": {
                "value": revenue_total,
                **metric_template
            },

            "property_revenue": {
                "value": revenue_total * 0.8,
                **metric_template
            },

            "service_revenue": {
                "value": revenue_total * 0.2,
                **metric_template
            },

            "active_bookings": {
                "value": active,
                **metric_template
            },

            "top_performing_properties": properties,

            "luxury_services_revenue": services,

            "guest_origins": [],

            "priority_tasks": []
        }

    async def _get_total_revenue(self, platform):

        query = """
        SELECT COALESCE(SUM(total_amount),0)
        FROM bookings
        """

        params = {}

        if platform:
            query += " WHERE platform = :platform"
            params["platform"] = platform

        result = await self.session.execute(text(query), params)

        return float(result.scalar() or 0)
    
    async def _get_active_bookings(self, platform):

        query = """
        SELECT COUNT(*)
        FROM bookings
        WHERE check_out_date >= NOW()
        """

        params = {}

        if platform:
            query += " AND platform = :platform"
            params["platform"] = platform

        result = await self.session.execute(text(query), params)

        return int(result.scalar() or 0)

    async def _get_top_properties(self, platform):

        query = """
        SELECT property_name, COUNT(*) as bookings, SUM(total_amount) as revenue
        FROM bookings
        WHERE property_name IS NOT NULL
        """

        params = {}

        if platform:
            query += " AND platform = :platform"
            params["platform"] = platform

        query += """
        GROUP BY property_name
        ORDER BY revenue DESC
        LIMIT 5
        """

        result = await self.session.execute(text(query), params)

        rows = result.fetchall()

        return [
            {
                "property_name": r[0],
                "bookings": r[1],
                "revenue": float(r[2] or 0)
            }
            for r in rows
        ]

    async def _get_platform_distribution(self):

        query = """
        SELECT platform, COUNT(*)
        FROM bookings
        WHERE platform IS NOT NULL
        GROUP BY platform
        ORDER BY COUNT(*) DESC
        """

        result = await self.session.execute(text(query))

        rows = result.fetchall()

        total = sum(r[1] for r in rows) or 1

        return [
            {
                "platform": r[0],
                "percentage": round((r[1] / total) * 100, 1)
            }
            for r in rows
        ]

    async def _get_services_revenue(self):

        query = """
        SELECT service_name, SUM(amount)
        FROM services
        GROUP BY service_name
        ORDER BY SUM(amount) DESC
        LIMIT 5
        """

        result = await self.session.execute(text(query))

        rows = result.fetchall()

        return [
            {
                "service_name": r[0],
                "revenue": float(r[1] or 0)
            }
            for r in rows
        ]

    async def _get_upcoming_cleaning_tasks(self):

        query = """
        SELECT reservation_id, property_id, scheduled_date, status
        FROM cleaning_tasks
        ORDER BY scheduled_date ASC
        LIMIT 5
        """

        result = await self.session.execute(text(query))

        rows = result.fetchall()

        return [
            {
                "reservation_id": r[0],
                "property_id": r[1],
                "scheduled_date": str(r[2]),
                "status": r[3]
            }
            for r in rows
        ]