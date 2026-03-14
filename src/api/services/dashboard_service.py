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

    async def get_extended_metrics(self, from_date: str | None = None, to_date: str | None = None) -> Dict[str, Any]:
        try:
            # 1. Base metrics
            base = await self.get_metrics()
            
            # 2. Average Daily Rate
            adr = await self._get_average_daily_rate()
            
            # 3. Overall Occupancy Rate
            occupancy = await self._get_overall_occupancy_rate()
            
            # 4. Revenue Forecast
            forecast = await self._get_revenue_forecast()
            
            # 5. Revenue Trends
            trends = await self._get_revenue_trends()
            
            # 6. Occupancy by Property
            prop_occupancy = await self._get_occupancy_by_property()
            
            # 7. Revenue by Channel
            channel_revenue = await self._get_revenue_by_channel()
            
            # 8. Upcoming Check-ins & Check-outs
            check_ins = await self._get_upcoming_check_ins()
            check_outs = await self._get_upcoming_check_outs()
            
            return {
                **base,
                "average_daily_rate": adr,
                "overall_occupancy_rate": occupancy,
                "pending_payments": {"value": base["total_revenue"]["value"] * 0.15, "percentage_change": -5.2, "trend_direction": "down", "label": "vs last month"},
                "revenue_forecast": forecast,
                "revenue_trends": trends,
                "occupancy_by_property": prop_occupancy,
                "revenue_by_channel": channel_revenue,
                "payment_collection": {
                    "paid": base["total_revenue"]["value"] * 0.8,
                    "partial": base["total_revenue"]["value"] * 0.05,
                    "pending": base["total_revenue"]["value"] * 0.15,
                    "total": base["total_revenue"]["value"]
                },
                "upcoming_check_ins": check_ins,
                "upcoming_check_outs": check_outs,
                "priority_tasks": await self._get_priority_tasks()
            }
        except Exception as e:
            self.logger.error(f"Error calculating extended dashboard metrics: {e}", exc_info=True)
            raise

    async def _get_priority_tasks(self, platform: str | None = None) -> List[Dict[str, Any]]:
        query_str = f"""
            SELECT id, reservation_id, scheduled_date as due_date, property_id as property 
            FROM {app_config.cleaning_tasks_collection} 
            ORDER BY scheduled_date ASC LIMIT 5
        """
        result = await self.session.execute(text(query_str))
        rows = result.fetchall()
        return [dict(row._mapping) for row in rows]

    async def _get_average_daily_rate(self) -> Dict[str, Any]:
        query = f"SELECT AVG(total_amount / NULLIF(nights, 0)) FROM {app_config.bookings_collection} WHERE nights > 0"
        result = await self.session.execute(text(query))
        val = result.scalar() or 0
        return {"value": round(val, 1), "percentage_change": 2.4, "trend_direction": "up", "label": "vs last month"}

    async def _get_overall_occupancy_rate(self) -> Dict[str, Any]:
        # Placeholder calculation
        return {"value": 72.5, "percentage_change": 1.8, "trend_direction": "up", "label": "vs last month"}

    async def _get_revenue_forecast(self) -> List[Dict[str, Any]]:
        now = datetime.utcnow().date()
        periods = [30, 60, 90]
        results = []
        for p in periods:
            future_date = now + timedelta(days=p)
            query = f"SELECT SUM(total_amount), COUNT(*) FROM {app_config.bookings_collection} WHERE check_in_date BETWEEN :now AND :future"
            result = await self.session.execute(text(query), {"now": now, "future": future_date})
            row = result.fetchone()
            rev = row[0] or 0 if row else 0
            count = row[1] or 0 if row else 0
            results.append({
                "period": f"{p}d",
                "confirmed_revenue": rev,
                "bookings_count": count,
                "potential_revenue": rev * 0.2 # Placeholder
            })
        return results

    async def _get_revenue_trends(self) -> Dict[str, List[Dict[str, Any]]]:
        # Group by week/month placeholder
        return {
            "current_period": [
                {"date": "2024-01-01", "revenue": 12000, "bookings": 4},
                {"date": "2024-01-08", "revenue": 15000, "bookings": 5}
            ],
            "last_year_period": [
                {"date": "2023-01-01", "revenue": 10000, "bookings": 3},
                {"date": "2023-01-08", "revenue": 13000, "bookings": 4}
            ]
        }

    async def _get_occupancy_by_property(self) -> List[Dict[str, Any]]:
        query = f"SELECT property_id, property_name, COUNT(*) * 100 / 30 as occupancy_rate FROM {app_config.bookings_collection} GROUP BY property_id, property_name LIMIT 5"
        result = await self.session.execute(text(query))
        rows = result.fetchall()
        return [{"property_id": str(r[0]), "property_name": r[1] or "Unknown", "occupancy_rate": round(float(r[2]), 1), "booked_nights": 20, "available_nights": 10} for r in rows]

    async def _get_revenue_by_channel(self) -> List[Dict[str, Any]]:
        query = f"SELECT platform, SUM(total_amount) as revenue FROM {app_config.bookings_collection} GROUP BY platform"
        result = await self.session.execute(text(query))
        rows = result.fetchall()
        total = sum(r[1] for r in rows) if rows else 1
        return [{"channel": r[0], "revenue": float(r[1]), "percentage": round(float(r[1])/total * 100, 1), "bookings_count": 10} for r in rows]

    async def _get_upcoming_check_ins(self) -> List[Dict[str, Any]]:
        now = datetime.utcnow().date()
        query = f"SELECT reservation_id, guest_name, property_name, check_in_date FROM {app_config.bookings_collection} WHERE check_in_date >= :now ORDER BY check_in_date ASC LIMIT 5"
        result = await self.session.execute(text(query), {"now": now})
        rows = result.fetchall()
        return [{
            "id": str(r[0]),
            "type": "check_in",
            "guest_name": r[1],
            "property_name": r[2] or "Unknown",
            "property_id": "1",
            "date": r[3].strftime("%Y-%m-%d") if r[3] else "",
            "time": "15:00",
            "guests_count": 2
        } for r in rows]

    async def _get_upcoming_check_outs(self) -> List[Dict[str, Any]]:
        now = datetime.utcnow().date()
        query = f"SELECT reservation_id, guest_name, property_name, check_out_date FROM {app_config.bookings_collection} WHERE check_out_date >= :now ORDER BY check_out_date ASC LIMIT 5"
        result = await self.session.execute(text(query), {"now": now})
        rows = result.fetchall()
        return [{
            "id": str(r[0]),
            "type": "check_out",
            "guest_name": r[1],
            "property_name": r[2] or "Unknown",
            "property_id": "1",
            "date": r[3].strftime("%Y-%m-%d") if r[3] else "",
            "time": "11:00",
            "guests_count": 2
        } for r in rows]
