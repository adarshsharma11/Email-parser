from datetime import datetime
from typing import Dict, Any, List

from ...supabase_sync.supabase_client import SupabaseClient
from config.settings import app_config


class DashboardService:
    def __init__(self):
        self.supabase = SupabaseClient()

    def _ensure(self) -> None:
        if not self.supabase.initialized:
            if not self.supabase.initialize():
                raise RuntimeError("Supabase initialization failed")

    def get_metrics(self, platform: str | None = None) -> Dict[str, Any]:
        self._ensure()

        total = self._get_total_bookings(platform)
        unique = self._get_unique_customers(platform)
        monthly = self._get_monthly_sales(platform)

        return {
            "total_bookings": total,
            "unique_customers": unique,
            "monthly_sales": monthly,
        }

    def _get_total_bookings(self, platform: str | None) -> int:
        query = (
            self.supabase.client
            .table(app_config.bookings_collection)
            .select("reservation_id", count="exact")
        )
        if platform:
            query = query.eq("platform", platform)
        res = query.execute()
        count = getattr(res, "count", None)
        if count is None:
            rows = getattr(res, "data", []) or getattr(res, "json", {}).get("data", [])
            count = len(rows)
        return int(count or 0)

    def _get_unique_customers(self, platform: str | None) -> int:
        query = (
            self.supabase.client
            .table(app_config.bookings_collection)
            .select("guest_email")
        )
        if platform:
            query = query.eq("platform", platform)
        res = query.execute()
        rows = getattr(res, "data", []) or getattr(res, "json", {}).get("data", [])
        emails = {str((r or {}).get("guest_email")).strip() for r in rows if (r or {}).get("guest_email")}
        return len(emails)

    def _get_monthly_sales(self, platform: str | None) -> List[Dict[str, Any]]:
        query = (
            self.supabase.client
            .table(app_config.bookings_collection)
            .select("booking_date,total_amount")
        )
        if platform:
            query = query.eq("platform", platform)
        res = query.execute()
        rows = getattr(res, "data", []) or getattr(res, "json", {}).get("data", [])
        totals: Dict[str, float] = {}
        for r in rows:
            dt = (r or {}).get("booking_date")
            amt = (r or {}).get("total_amount")
            if not dt or amt is None:
                continue
            try:
                d = datetime.fromisoformat(str(dt).replace("Z", "+00:00"))
            except Exception:
                continue
            key = f"{d.year:04d}-{d.month:02d}"
            totals[key] = float(totals.get(key, 0.0)) + float(amt)
        return [{"month": k, "total_amount": v} for k, v in sorted(totals.items())]