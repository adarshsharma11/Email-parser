from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


# Phone country code to country name mapping
PHONE_COUNTRY_MAP = {
    "+1": "United States",
    "+44": "United Kingdom",
    "+91": "India",
    "+61": "Australia",
    "+49": "Germany",
    "+33": "France",
    "+39": "Italy",
    "+34": "Spain",
    "+81": "Japan",
    "+86": "China",
    "+55": "Brazil",
    "+52": "Mexico",
    "+7": "Russia",
    "+82": "South Korea",
    "+31": "Netherlands",
    "+46": "Sweden",
    "+47": "Norway",
    "+45": "Denmark",
    "+41": "Switzerland",
    "+43": "Austria",
    "+972": "Israel",
    "+971": "UAE",
    "+966": "Saudi Arabia",
    "+65": "Singapore",
    "+64": "New Zealand",
    "+353": "Ireland",
    "+351": "Portugal",
    "+48": "Poland",
    "+90": "Turkey",
    "+20": "Egypt",
    "+27": "South Africa",
    "+62": "Indonesia",
    "+66": "Thailand",
    "+60": "Malaysia",
    "+63": "Philippines",
}


def _country_from_phone(phone: str) -> str:
    """Extract country from phone number country code."""
    if not phone:
        return "Unknown"
    phone = phone.strip()
    # Try longest prefix first (e.g. +972 before +97 before +9)
    for length in [4, 3, 2]:
        prefix = phone[:length]
        if prefix in PHONE_COUNTRY_MAP:
            return PHONE_COUNTRY_MAP[prefix]
    return "Unknown"


class DashboardService:

    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = logging.getLogger(__name__)

    async def get_metrics(self, platform: str | None = None):

        revenue_total = await self._get_total_revenue(platform)
        active = await self._get_active_bookings(platform)
        properties = await self._get_top_properties(platform)
        services = await self._get_services_revenue()
        guest_origins = await self._get_guest_origins()

        metric_template = {
            "percentage_change": 0,
            "trend_direction": "up",
            "label": "vs last period"
        }

        return {
            "total_revenue": {"value": revenue_total, **metric_template},
            "property_revenue": {"value": revenue_total * 0.8, **metric_template},
            "service_revenue": {"value": revenue_total * 0.2, **metric_template},
            "active_bookings": {"value": active, **metric_template},
            "top_performing_properties": properties,
            "luxury_services_revenue": services,
            "guest_origins": guest_origins,
            "priority_tasks": []
        }

    async def get_extended_metrics(self, from_date: Optional[str] = None, to_date: Optional[str] = None):
        """Return extended dashboard metrics with date filtering."""

        # Parse dates or use current month
        if from_date:
            try:
                start = datetime.strptime(from_date, "%Y-%m-%d")
            except ValueError:
                start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        if to_date:
            try:
                end = datetime.strptime(to_date, "%Y-%m-%d")
            except ValueError:
                end = datetime.now()
        else:
            end = datetime.now()

        # Base metrics with date range
        revenue = await self._get_revenue_in_range(start, end)
        bookings_count = await self._get_bookings_count_in_range(start, end)
        total_nights = await self._get_total_nights_in_range(start, end)
        properties = await self._get_top_properties_in_range(start, end)
        services = await self._get_services_revenue()
        channel_revenue = await self._get_channel_revenue_in_range(start, end)
        occupancy = await self._get_occupancy_by_property(start, end)
        upcoming_checkins = await self._get_upcoming_events("check_in_date")
        upcoming_checkouts = await self._get_upcoming_events("check_out_date")
        payment_data = await self._get_payment_collection(start, end)
        guest_origins = await self._get_guest_origins_in_range(start, end)
        priority_tasks = await self._get_priority_tasks()

        # Calculate ADR
        adr = revenue / total_nights if total_nights > 0 else 0

        # Calculate occupancy rate
        days_in_range = max((end - start).days, 1)
        num_properties = max(len(occupancy), 1)
        available_nights = days_in_range * num_properties
        occ_rate = round((total_nights / available_nights) * 100, 1) if available_nights > 0 else 0

        # Pending payments
        pending = await self._get_pending_payments(start, end)

        metric_template = {
            "percentage_change": 0,
            "trend_direction": "neutral",
            "label": "vs last period"
        }

        return {
            # Base metrics
            "total_revenue": {"value": revenue, **metric_template},
            "property_revenue": {"value": round(revenue * 0.8, 2), **metric_template},
            "service_revenue": {"value": round(revenue * 0.2, 2), **metric_template},
            "active_bookings": {"value": bookings_count, **metric_template},

            # Extended metrics
            "average_daily_rate": {"value": round(adr, 2), **metric_template},
            "overall_occupancy_rate": {"value": occ_rate, **metric_template},
            "pending_payments": {"value": pending, **metric_template},

            # Lists
            "top_performing_properties": properties,
            "luxury_services_revenue": services,
            "guest_origins": guest_origins,
            "priority_tasks": priority_tasks,

            # Charts/Widgets
            "revenue_forecast": [
                {"period": "30d", "confirmed_revenue": revenue, "bookings_count": bookings_count, "potential_revenue": round(revenue * 1.2, 2)},
                {"period": "60d", "confirmed_revenue": round(revenue * 0.6, 2), "bookings_count": max(bookings_count - 3, 0), "potential_revenue": round(revenue * 1.5, 2)},
                {"period": "90d", "confirmed_revenue": round(revenue * 0.3, 2), "bookings_count": max(bookings_count - 5, 0), "potential_revenue": round(revenue * 1.8, 2)},
            ],
            "revenue_trends": await self._get_revenue_trends(start, end),
            "occupancy_by_property": occupancy,
            "revenue_by_channel": channel_revenue,
            "payment_collection": payment_data,
            "upcoming_check_ins": upcoming_checkins,
            "upcoming_check_outs": upcoming_checkouts,
        }

    # --- Guest Origins ---

    async def _get_guest_origins(self):
        """Derive guest origins from phone country codes."""
        result = await self.session.execute(text("""
            SELECT guest_phone, COUNT(*) as bookings, COALESCE(SUM(total_amount), 0) as revenue
            FROM bookings
            WHERE guest_phone IS NOT NULL AND guest_phone != ''
            GROUP BY guest_phone
        """))
        # Aggregate by country
        country_data: Dict[str, Dict] = {}
        total_bookings = 0
        for row in result.fetchall():
            country = _country_from_phone(row[0])
            if country not in country_data:
                country_data[country] = {"bookings": 0, "revenue": 0.0}
            country_data[country]["bookings"] += row[1]
            country_data[country]["revenue"] += float(row[2] or 0)
            total_bookings += row[1]

        total_bookings = max(total_bookings, 1)
        origins = []
        for country, data in sorted(country_data.items(), key=lambda x: x[1]["bookings"], reverse=True):
            origins.append({
                "origin": country,
                "bookings": data["bookings"],
                "revenue": round(data["revenue"], 2),
                "percentage": round((data["bookings"] / total_bookings) * 100, 1)
            })
        return origins[:10]

    async def _get_guest_origins_in_range(self, start, end):
        """Derive guest origins from phone country codes within date range."""
        result = await self.session.execute(
            text("""
                SELECT guest_phone, COUNT(*) as bookings, COALESCE(SUM(total_amount), 0) as revenue
                FROM bookings
                WHERE guest_phone IS NOT NULL AND guest_phone != ''
                AND check_in_date >= :start AND check_in_date <= :end
                GROUP BY guest_phone
            """),
            {"start": start, "end": end}
        )
        country_data: Dict[str, Dict] = {}
        total_bookings = 0
        for row in result.fetchall():
            country = _country_from_phone(row[0])
            if country not in country_data:
                country_data[country] = {"bookings": 0, "revenue": 0.0}
            country_data[country]["bookings"] += row[1]
            country_data[country]["revenue"] += float(row[2] or 0)
            total_bookings += row[1]

        total_bookings = max(total_bookings, 1)
        origins = []
        for country, data in sorted(country_data.items(), key=lambda x: x[1]["bookings"], reverse=True):
            origins.append({
                "origin": country,
                "bookings": data["bookings"],
                "revenue": round(data["revenue"], 2),
                "percentage": round((data["bookings"] / total_bookings) * 100, 1)
            })
        return origins[:10]

    # --- Priority Tasks ---

    async def _get_priority_tasks(self):
        """Get pending cleaning tasks and upcoming service bookings as priority tasks."""
        tasks = []
        task_id = 1

        # Pending cleaning tasks
        try:
            result = await self.session.execute(text("""
                SELECT ct.id, ct.property_id, ct.scheduled_date, ct.status, ct.reservation_id
                FROM cleaning_tasks ct
                WHERE ct.status = 'pending' AND ct.scheduled_date >= CURRENT_DATE
                ORDER BY ct.scheduled_date ASC LIMIT 5
            """))
            for r in result.fetchall():
                sched = r[2]
                tasks.append({
                    "id": task_id,
                    "title": f"Cleaning: {r[1] or 'Property'}",
                    "type": "cleaning",
                    "due_date": sched.strftime("%Y-%m-%d") if sched else "",
                    "priority": "high" if sched and (sched - datetime.now()).days <= 2 else "medium",
                    "status": "urgent" if sched and (sched - datetime.now()).days <= 1 else "pending"
                })
                task_id += 1
        except Exception as e:
            self.logger.warning(f"Error fetching cleaning tasks: {e}")

        # Upcoming check-ins needing preparation (next 3 days)
        try:
            result = await self.session.execute(text("""
                SELECT guest_name, property_name, check_in_date, number_of_guests
                FROM bookings
                WHERE check_in_date >= CURRENT_DATE AND check_in_date <= CURRENT_DATE + INTERVAL '3 days'
                ORDER BY check_in_date ASC LIMIT 5
            """))
            for r in result.fetchall():
                tasks.append({
                    "id": task_id,
                    "title": f"Prepare for {r[0] or 'Guest'} at {r[1] or 'Property'}",
                    "type": "check_in_prep",
                    "due_date": r[2].strftime("%Y-%m-%d") if r[2] else "",
                    "priority": "high",
                    "status": "urgent"
                })
                task_id += 1
        except Exception as e:
            self.logger.warning(f"Error fetching check-in tasks: {e}")

        return tasks[:10]

    # --- Date-range helpers ---

    async def _get_revenue_in_range(self, start, end):
        result = await self.session.execute(
            text("SELECT COALESCE(SUM(total_amount), 0) FROM bookings WHERE check_in_date >= :start AND check_in_date <= :end"),
            {"start": start, "end": end}
        )
        return float(result.scalar() or 0)

    async def _get_bookings_count_in_range(self, start, end):
        result = await self.session.execute(
            text("SELECT COUNT(*) FROM bookings WHERE check_in_date >= :start AND check_in_date <= :end"),
            {"start": start, "end": end}
        )
        return int(result.scalar() or 0)

    async def _get_total_nights_in_range(self, start, end):
        result = await self.session.execute(
            text("SELECT COALESCE(SUM(COALESCE(nights, 0)), 0) FROM bookings WHERE check_in_date >= :start AND check_in_date <= :end"),
            {"start": start, "end": end}
        )
        return int(result.scalar() or 0)

    async def _get_top_properties_in_range(self, start, end):
        result = await self.session.execute(
            text("""
                SELECT property_name, COUNT(*) as bookings_count, COALESCE(SUM(total_amount), 0) as revenue
                FROM bookings
                WHERE property_name IS NOT NULL AND check_in_date >= :start AND check_in_date <= :end
                GROUP BY property_name ORDER BY revenue DESC LIMIT 5
            """),
            {"start": start, "end": end}
        )
        return [{"name": r[0], "bookings_count": r[1], "revenue": float(r[2] or 0)} for r in result.fetchall()]

    async def _get_channel_revenue_in_range(self, start, end):
        result = await self.session.execute(
            text("""
                SELECT platform, COALESCE(SUM(total_amount), 0) as revenue, COUNT(*) as bookings_count
                FROM bookings
                WHERE platform IS NOT NULL AND check_in_date >= :start AND check_in_date <= :end
                GROUP BY platform ORDER BY revenue DESC
            """),
            {"start": start, "end": end}
        )
        rows = result.fetchall()
        total = sum(float(r[1] or 0) for r in rows) or 1
        return [
            {"channel": r[0], "revenue": float(r[1] or 0), "percentage": round((float(r[1] or 0) / total) * 100, 1), "bookings_count": r[2]}
            for r in rows
        ]

    async def _get_occupancy_by_property(self, start, end):
        days_in_range = max((end - start).days, 1)
        result = await self.session.execute(
            text("""
                SELECT property_name, property_id, COALESCE(SUM(COALESCE(nights, 0)), 0) as booked_nights
                FROM bookings
                WHERE property_name IS NOT NULL AND check_in_date >= :start AND check_in_date <= :end
                GROUP BY property_name, property_id
            """),
            {"start": start, "end": end}
        )
        return [
            {
                "property_id": r[1] or "",
                "property_name": r[0],
                "occupancy_rate": round(min((int(r[2]) / days_in_range) * 100, 100), 1),
                "booked_nights": int(r[2]),
                "available_nights": days_in_range
            }
            for r in result.fetchall()
        ]

    async def _get_upcoming_events(self, date_column):
        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        # Look ahead 7 days for upcoming events
        future = now + timedelta(days=7)
        result = await self.session.execute(
            text(f"""
                SELECT reservation_id, guest_name, property_name, property_id, {date_column}, number_of_guests
                FROM bookings
                WHERE {date_column} >= :now AND {date_column} <= :future
                ORDER BY {date_column} ASC LIMIT 10
            """),
            {"now": now, "future": future}
        )
        event_type = "check_in" if "check_in" in date_column else "check_out"
        return [
            {
                "id": r[0],
                "type": event_type,
                "guest_name": r[1] or "Unknown",
                "property_name": r[2] or "Unknown",
                "property_id": r[3] or "",
                "date": r[4].strftime("%Y-%m-%d") if r[4] else "",
                "time": r[4].strftime("%H:%M") if r[4] else "",
                "guests_count": r[5] or 0
            }
            for r in result.fetchall()
        ]

    async def _get_payment_collection(self, start, end):
        result = await self.session.execute(
            text("""
                SELECT
                    COALESCE(SUM(CASE WHEN total_amount > 0 THEN total_amount ELSE 0 END), 0) as paid,
                    COALESCE(SUM(CASE WHEN total_amount = 0 OR total_amount IS NULL THEN 0 ELSE 0 END), 0) as partial,
                    COUNT(CASE WHEN total_amount = 0 OR total_amount IS NULL THEN 1 END) as pending_count,
                    COALESCE(SUM(total_amount), 0) as total
                FROM bookings
                WHERE check_in_date >= :start AND check_in_date <= :end
            """),
            {"start": start, "end": end}
        )
        row = result.fetchone()
        return {
            "paid": float(row[0] or 0),
            "partial": 0.0,
            "pending": float(row[2] or 0) * 200,
            "total": float(row[3] or 0)
        }

    async def _get_pending_payments(self, start, end):
        result = await self.session.execute(
            text("""
                SELECT COUNT(*) FROM bookings
                WHERE (total_amount = 0 OR total_amount IS NULL)
                AND check_in_date >= :start AND check_in_date <= :end
            """),
            {"start": start, "end": end}
        )
        return int(result.scalar() or 0) * 200

    async def _get_revenue_trends(self, start, end):
        # Weekly data
        result = await self.session.execute(
            text("""
                SELECT DATE_TRUNC('week', check_in_date)::date as week_start,
                       COALESCE(SUM(total_amount), 0) as revenue,
                       COUNT(*) as bookings
                FROM bookings
                WHERE check_in_date >= :start AND check_in_date <= :end
                GROUP BY week_start ORDER BY week_start
            """),
            {"start": start, "end": end}
        )
        current_weekly = [{"date": r[0].isoformat(), "revenue": float(r[1] or 0), "bookings": r[2]} for r in result.fetchall()]

        # Monthly data
        result_monthly = await self.session.execute(
            text("""
                SELECT DATE_TRUNC('month', check_in_date)::date as month_start,
                       COALESCE(SUM(total_amount), 0) as revenue,
                       COUNT(*) as bookings
                FROM bookings
                WHERE check_in_date >= :start AND check_in_date <= :end
                GROUP BY month_start ORDER BY month_start
            """),
            {"start": start, "end": end}
        )
        current_monthly = [{"date": r[0].isoformat(), "revenue": float(r[1] or 0), "bookings": r[2]} for r in result_monthly.fetchall()]

        # Last year same period - weekly
        ly_start = start.replace(year=start.year - 1)
        ly_end = end.replace(year=end.year - 1)
        result2 = await self.session.execute(
            text("""
                SELECT DATE_TRUNC('week', check_in_date)::date as week_start,
                       COALESCE(SUM(total_amount), 0) as revenue,
                       COUNT(*) as bookings
                FROM bookings
                WHERE check_in_date >= :start AND check_in_date <= :end
                GROUP BY week_start ORDER BY week_start
            """),
            {"start": ly_start, "end": ly_end}
        )
        last_year_weekly = [{"date": r[0].isoformat(), "revenue": float(r[1] or 0), "bookings": r[2]} for r in result2.fetchall()]

        # Last year - monthly
        result2m = await self.session.execute(
            text("""
                SELECT DATE_TRUNC('month', check_in_date)::date as month_start,
                       COALESCE(SUM(total_amount), 0) as revenue,
                       COUNT(*) as bookings
                FROM bookings
                WHERE check_in_date >= :start AND check_in_date <= :end
                GROUP BY month_start ORDER BY month_start
            """),
            {"start": ly_start, "end": ly_end}
        )
        last_year_monthly = [{"date": r[0].isoformat(), "revenue": float(r[1] or 0), "bookings": r[2]} for r in result2m.fetchall()]

        return {
            "current_period": current_weekly,
            "last_year_period": last_year_weekly,
            "current_period_monthly": current_monthly,
            "last_year_period_monthly": last_year_monthly,
        }

    # --- Original helpers ---

    async def _get_total_revenue(self, platform):
        query = "SELECT COALESCE(SUM(total_amount),0) FROM bookings"
        params = {}
        if platform:
            query += " WHERE platform = :platform"
            params["platform"] = platform
        result = await self.session.execute(text(query), params)
        return float(result.scalar() or 0)

    async def _get_active_bookings(self, platform):
        query = "SELECT COUNT(*) FROM bookings WHERE check_out_date >= NOW()"
        params = {}
        if platform:
            query += " AND platform = :platform"
            params["platform"] = platform
        result = await self.session.execute(text(query), params)
        return int(result.scalar() or 0)

    async def _get_top_properties(self, platform):
        query = """
        SELECT property_name, COUNT(*) as bookings, SUM(total_amount) as revenue
        FROM bookings WHERE property_name IS NOT NULL
        """
        params = {}
        if platform:
            query += " AND platform = :platform"
            params["platform"] = platform
        query += " GROUP BY property_name ORDER BY revenue DESC LIMIT 5"
        result = await self.session.execute(text(query), params)
        return [
            {"name": r[0], "bookings_count": r[1], "revenue": float(r[2] or 0)}
            for r in result.fetchall()
        ]

    async def _get_services_revenue(self):
        try:
            result = await self.session.execute(text("""
                SELECT category_name, COALESCE(price::numeric, 0) as revenue
                FROM service_category
                WHERE status = true
                ORDER BY revenue DESC LIMIT 5
            """))
            return [
                {"name": r[0], "revenue": float(r[1] or 0), "bookings_count": 0}
                for r in result.fetchall()
            ]
        except Exception:
            return []
