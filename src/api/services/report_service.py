from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from config.settings import app_config


class ReportService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = logging.getLogger(__name__)

    async def get_owner_statement(self, from_date: str, to_date: str, property_ids: Optional[List[str]] = None, owner_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        try:
            # 1. Fetch bookings for the period and properties/owners
            bookings = await self._fetch_filtered_bookings(from_date, to_date, property_ids, owner_ids)
            
            # 2. Fetch services for these bookings
            booking_ids = [str(b.get("reservation_id")) for b in bookings if b.get("reservation_id")]
            services = await self._fetch_services_for_bookings(booking_ids)
            
            # 3. Calculate actual days in period for occupancy
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            days_in_period = (to_dt - from_dt).days + 1
            if days_in_period <= 0:
                days_in_period = 30

            # 4. Group by property
            properties_data = {}
            global_services_breakdown = {}
            total_rental_revenue = 0
            total_services_revenue = 0
            
            for b in bookings:
                pid = str(b.get("property_id") or b.get("property_name") or "Unknown")
                if pid not in properties_data:
                    properties_data[pid] = {
                        "property_id": pid,
                        "property_name": b.get("property_name") or "Unknown",
                        "property_address": b.get("address") or "N/A",
                        "bookings": [],
                        "total_revenue": 0,
                        "rental_revenue": 0,
                        "services_revenue": 0,
                        "channel_fees": 0,
                        "cleaning_fees_collected": 0,
                        "cleaning_expenses": 0,
                        "maintenance_expenses": 0,
                        "other_expenses": 0,
                        "net_revenue": 0,
                        "occupancy_rate": 0,
                        "nights_booked": 0,
                        "average_daily_rate": 0,
                        "services_breakdown": {}
                    }
                
                bid = str(b.get("reservation_id"))
                rev = float(b.get("total_amount") or 0)
                nights = int(b.get("nights") or 1)
                
                # Calculate services for this specific booking
                booking_services = [s for s in services if str(s.get("booking_id")) == bid]
                booking_services_rev = sum(float(s.get("price") or 0) for s in booking_services)
                
                # Add to property totals
                properties_data[pid]["rental_revenue"] += rev
                properties_data[pid]["services_revenue"] += booking_services_rev
                properties_data[pid]["total_revenue"] += (rev + booking_services_rev)
                properties_data[pid]["nights_booked"] += nights
                properties_data[pid]["channel_fees"] += rev * 0.03
                
                total_rental_revenue += rev
                total_services_revenue += booking_services_rev

                # Track specific services for breakdown (per property and global)
                for s in booking_services:
                    s_name = s.get("service_name") or "Unknown Service"
                    # Per property
                    if s_name not in properties_data[pid]["services_breakdown"]:
                        properties_data[pid]["services_breakdown"][s_name] = {"name": s_name, "count": 0, "revenue": 0}
                    properties_data[pid]["services_breakdown"][s_name]["count"] += 1
                    properties_data[pid]["services_breakdown"][s_name]["revenue"] += float(s.get("price") or 0)
                    
                    # Global
                    if s_name not in global_services_breakdown:
                        global_services_breakdown[s_name] = {"name": s_name, "count": 0, "revenue": 0}
                    global_services_breakdown[s_name]["count"] += 1
                    global_services_breakdown[s_name]["revenue"] += float(s.get("price") or 0)

                # Format specific services for this individual booking
                booking_services_list = []
                for s in booking_services:
                    booking_services_list.append({
                        "service_id": str(s.get("service_id")),
                        "service_name": s.get("service_name"),
                        "price": float(s.get("price") or 0)
                    })

                properties_data[pid]["bookings"].append({
                    "booking_id": b.get("reservation_id"),
                    "guest_name": b.get("guest_name"),
                    "check_in": b.get("check_in_date").strftime("%Y-%m-%d") if b.get("check_in_date") else None,
                    "check_out": b.get("check_out_date").strftime("%Y-%m-%d") if b.get("check_out_date") else None,
                    "nights": nights,
                    "revenue": rev,
                    "services_revenue": booking_services_rev,
                    "services": booking_services_list,
                    "channel": b.get("platform"),
                    "channel_fee": rev * 0.03,
                    "cleaning_fee": 150, # Placeholder
                })

            # Calculate summaries
            total_net_payout = 0
            for pid, pdata in properties_data.items():
                pdata["net_revenue"] = round(pdata["total_revenue"] - pdata["channel_fees"], 2)
                if pdata["nights_booked"] > 0:
                    pdata["average_daily_rate"] = round(pdata["rental_revenue"] / pdata["nights_booked"], 2)
                
                # Calculate occupancy rate for owner statement using actual days in period
                pdata["occupancy_rate"] = round((pdata["nights_booked"] / float(days_in_period)) * 100, 2)
                
                total_net_payout += pdata["net_revenue"]
                # Convert breakdown dict to list
                pdata["services_summary"] = list(pdata["services_breakdown"].values())

            return {
                "owner_id": "global",
                "owner_name": "Global Admin",
                "owner_email": "admin@moma.house",
                "period_start": from_date,
                "period_end": to_date,
                "properties": list(properties_data.values()),
                "services_summary": list(global_services_breakdown.values()),
                "rental_revenue": round(total_rental_revenue, 2),
                "services_revenue": round(total_services_revenue, 2),
                "total_revenue": round(total_rental_revenue + total_services_revenue, 2),
                "total_expenses": round((total_rental_revenue + total_services_revenue) * 0.1, 2), # Placeholder
                "total_payout": round(total_net_payout * 0.9, 2), # Placeholder after management fee
                "management_fee": round(total_net_payout * 0.1, 2),
                "management_fee_percentage": 10.00,
            }
        except Exception as e:
            self.logger.error(f"Error generating owner statement: {e}", exc_info=True)
            raise

    async def _fetch_services_for_bookings(self, booking_ids: List[str]) -> List[Dict[str, Any]]:
        if not booking_ids:
            return []
        
        # Join booking_service with service_category to get names and prices
        query = text(f"""
            SELECT bs.*, sc.category_name as service_name, sc.price 
            FROM booking_service bs
            JOIN service_category sc ON bs.service_id = sc.id
            WHERE bs.booking_id::text = ANY(:bids)
        """)
        result = await self.session.execute(query, {"bids": booking_ids})
        return [dict(row._mapping) for row in result.fetchall()]

    async def get_booking_summary(self, from_date: str, to_date: str, property_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        try:
            bookings = await self._fetch_filtered_bookings(from_date, to_date, property_ids)
            
            total_rev = sum(float(b.get("total_amount") or 0) for b in bookings)
            total_nights = sum(int(b.get("nights") or 0) for b in bookings)
            
            # Group by channel
            by_channel = {}
            for b in bookings:
                ch = b.get("platform") or "Direct"
                if ch not in by_channel:
                    by_channel[ch] = {"channel": ch, "count": 0, "revenue": 0}
                by_channel[ch]["count"] += 1
                by_channel[ch]["revenue"] += float(b.get("total_amount") or 0)

            # Group by property
            by_property = {}
            for b in bookings:
                pid = str(b.get("property_id") or b.get("property_name") or "Unknown")
                if pid not in by_property:
                    by_property[pid] = {"property_id": pid, "property_name": b.get("property_name") or "Unknown", "count": 0, "revenue": 0}
                by_property[pid]["count"] += 1
                by_property[pid]["revenue"] += float(b.get("total_amount") or 0)

            return {
                "period_start": from_date,
                "period_end": to_date,
                "total_bookings": len(bookings),
                "total_revenue": total_rev,
                "total_nights": total_nights,
                "average_booking_value": total_rev / len(bookings) if bookings else 0,
                "bookings": [
                    {
                        "booking_id": b.get("reservation_id"),
                        "property_name": b.get("property_name"),
                        "guest_name": b.get("guest_name"),
                        "guest_email": b.get("guest_email"),
                        "check_in": b.get("check_in_date").strftime("%Y-%m-%d") if b.get("check_in_date") else None,
                        "check_out": b.get("check_out_date").strftime("%Y-%m-%d") if b.get("check_out_date") else None,
                        "nights": b.get("nights"),
                        "guests": b.get("number_of_guests"),
                        "total_amount": float(b.get("total_amount") or 0),
                        "channel": b.get("platform"),
                        "status": "Confirmed",
                        "payment_status": "Paid",
                        "created_at": b.get("created_at").strftime("%Y-%m-%d") if b.get("created_at") else None,
                    } for b in bookings
                ],
                "by_channel": list(by_channel.values()),
                "by_property": list(by_property.values()),
            }
        except Exception as e:
            self.logger.error(f"Error generating booking summary: {e}", exc_info=True)
            raise

    async def get_occupancy_report(self, from_date: str, to_date: str, property_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        try:
            # 1. Calculate actual days in period
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            days_in_period = (to_dt - from_dt).days + 1
            if days_in_period <= 0:
                days_in_period = 30 # Fallback

            # 2. Fetch requested properties to ensure even zero-booking ones appear
            all_props_query = f"SELECT id, name, address FROM {app_config.properties_collection}"
            params = {}
            if property_ids:
                all_props_query += " WHERE id::text = ANY(:pids) OR name = ANY(:pids)"
                params["pids"] = list(property_ids)
            
            props_res = await self.session.execute(text(all_props_query), params)
            properties_list = [dict(row._mapping) for row in props_res.fetchall()]

            # 3. Initialize by_property map with all selected properties
            by_property = {}
            for p in properties_list:
                pid = str(p["id"])
                by_property[pid] = {
                    "property_id": pid,
                    "property_name": p["name"] or "Unknown",
                    "property_address": p["address"] or "N/A",
                    "occupancy_rate": 0.00,
                    "available_nights": days_in_period,
                    "booked_nights": 0,
                    "blocked_nights": 0,
                    "revenue": 0.00,
                    "average_daily_rate": 0.00
                }

            # 4. Fetch bookings and update the map
            bookings = await self._fetch_filtered_bookings(from_date, to_date, property_ids)
            for b in bookings:
                pid = str(b.get("property_id"))
                # If property_id not in our map (maybe it was filtered by name in bookings but not in props query)
                if pid not in by_property:
                    # Try finding by name in existing map
                    p_name = b.get("property_name")
                    found_pid = next((k for k, v in by_property.items() if v["property_name"] == p_name), None)
                    if found_pid:
                        pid = found_pid
                    else:
                        # Add it if missing
                        by_property[pid] = {
                            "property_id": pid,
                            "property_name": p_name or "Unknown",
                            "property_address": b.get("address") or "N/A",
                            "occupancy_rate": 0.00,
                            "available_nights": days_in_period,
                            "booked_nights": 0,
                            "blocked_nights": 0,
                            "revenue": 0.00,
                            "average_daily_rate": 0.00
                        }
                
                nights = int(b.get("nights") or 0)
                rev = float(b.get("total_amount") or 0)
                by_property[pid]["booked_nights"] += nights
                by_property[pid]["revenue"] += rev

            # 5. Calculate final rates
            for pid, pdata in by_property.items():
                if days_in_period > 0:
                    pdata["occupancy_rate"] = round((pdata["booked_nights"] / float(days_in_period)) * 100, 2)
                if pdata["booked_nights"] > 0:
                    pdata["average_daily_rate"] = round(pdata["revenue"] / pdata["booked_nights"], 2)

            total_booked = sum(p["booked_nights"] for p in by_property.values())
            total_avail = len(by_property) * days_in_period

            return {
                "period_start": from_date,
                "period_end": to_date,
                "overall_occupancy": round((total_booked / total_avail * 100) if total_avail > 0 else 0, 2),
                "total_available_nights": total_avail,
                "total_booked_nights": total_booked,
                "properties": list(by_property.values()),
                "by_month": [{"month": from_date[:7], "occupancy": round((total_booked / total_avail * 100) if total_avail > 0 else 0, 2), "nights_booked": total_booked}]
            }
        except Exception as e:
            self.logger.error(f"Error generating occupancy report: {e}", exc_info=True)
            raise

    async def get_service_revenue(self, from_date: str, to_date: str, property_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        try:
            # Simplified mock for service revenue matching frontend interface
            return {
                "period_start": from_date,
                "period_end": to_date,
                "total_revenue": 4500.0,
                "total_bookings": 26,
                "services": [
                    {
                        "service_type": "Culinary",
                        "service_name": "Private Chef",
                        "total_revenue": 2500,
                        "bookings_count": 15,
                        "average_price": 166.67,
                        "trend": 12.5
                    },
                    {
                        "service_type": "Wellness",
                        "service_name": "Spa & Massage",
                        "total_revenue": 1200,
                        "bookings_count": 8,
                        "average_price": 150.0,
                        "trend": -5.2
                    },
                    {
                        "service_type": "Adventure",
                        "service_name": "Ski Guide",
                        "total_revenue": 800,
                        "bookings_count": 3,
                        "average_price": 266.67,
                        "trend": 24.1
                    }
                ],
                "by_month": [
                    {"month": "Jan", "revenue": 3800, "bookings": 20},
                    {"month": "Feb", "revenue": 4500, "bookings": 26}
                ],
                "top_properties": [
                    {"property_id": "1", "property_name": "Ocean View Villa", "revenue": 2200, "bookings": 12},
                    {"property_name": "Mountain Retreat", "property_id": "2", "revenue": 1500, "bookings": 8},
                    {"property_name": "Downtown Loft", "property_id": "3", "revenue": 800, "bookings": 6}
                ]
            }
        except Exception as e:
            self.logger.error(f"Error generating service revenue report: {e}", exc_info=True)
            raise

    async def get_performance_report(self, from_date: str, to_date: str, property_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        try:
            # Simplified mock for performance matching frontend interface
            return {
                "current_period": {
                    "start": from_date,
                    "end": to_date,
                    "label": "Current Period",
                    "total_revenue": 25000,
                    "total_bookings": 42,
                    "average_daily_rate": 305,
                    "occupancy_rate": 82,
                    "total_nights": 125
                },
                "previous_period": {
                    "start": "2024-01-01",
                    "end": "2024-01-31",
                    "label": "Previous Period",
                    "total_revenue": 22000,
                    "total_bookings": 38,
                    "average_daily_rate": 295,
                    "occupancy_rate": 78,
                    "total_nights": 110
                },
                "comparison_type": "month",
                "metrics_comparison": [
                    {
                        "metric": "Revenue",
                        "current_value": 25000,
                        "previous_value": 22000,
                        "change": 3000,
                        "change_percentage": 13.6,
                        "trend": "up"
                    },
                    {
                        "metric": "Occupancy",
                        "current_value": 82,
                        "previous_value": 78,
                        "change": 4,
                        "change_percentage": 5.1,
                        "trend": "up"
                    },
                    {
                        "metric": "ADR",
                        "current_value": 305,
                        "previous_value": 295,
                        "change": 10,
                        "change_percentage": 3.4,
                        "trend": "up"
                    }
                ],
                "revenue_trend": [
                    {"date": "2024-02-01", "current": 800, "previous": 700},
                    {"date": "2024-02-05", "current": 1200, "previous": 900}
                ],
                "occupancy_trend": [
                    {"date": "2024-02-01", "current": 75, "previous": 70},
                    {"date": "2024-02-05", "current": 85, "previous": 75}
                ]
            }
        except Exception as e:
            self.logger.error(f"Error generating performance report: {e}", exc_info=True)
            raise

    async def get_service_provider_report(self, from_date: str, to_date: str, provider_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            # For now, return mock data in correct format to avoid crashes
            # In a real scenario, we'd query jobs assigned to this provider
            return {
                "provider_id": provider_id or "prov-1",
                "provider_name": "John Doe Services",
                "provider_email": "john@example.com",
                "provider_phone": "+1 (555) 012-3456",
                "service_type": "Cleaning & Maintenance",
                "period_start": from_date,
                "period_end": to_date,
                "jobs": [
                    {
                        "job_id": "job-101",
                        "date": from_date,
                        "property_name": "Ocean View Villa",
                        "guest_name": "Alice Johnson",
                        "service_details": "Post-checkout full cleaning",
                        "amount": 150.0,
                        "tip": 20.0,
                        "status": "completed"
                    },
                    {
                        "job_id": "job-102",
                        "date": to_date,
                        "property_name": "Mountain Retreat",
                        "guest_name": "Bob Smith",
                        "service_details": "Emergency plumbing repair",
                        "amount": 250.0,
                        "tip": 0.0,
                        "status": "pending"
                    }
                ],
                "total_revenue": 400.0,
                "total_jobs": 2,
                "commission_rate": 10.0,
                "commission_amount": 40.0,
                "net_payout": 360.0,
                "average_job_value": 200.0
            }
        except Exception as e:
            self.logger.error(f"Error generating service provider report: {e}", exc_info=True)
            raise

    async def _fetch_filtered_bookings(self, from_date: str, to_date: str, property_ids: Optional[List[str]] = None, owner_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        # Convert string dates to date objects for SQLAlchemy/asyncpg
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            # Fallback to strings if format is wrong or already date objects
            from_dt = from_date
            to_dt = to_date

        query = f"SELECT b.* FROM {app_config.bookings_collection} b"
        
        # If owner_ids provided, we need to join with properties table
        if owner_ids:
            query += f" JOIN {app_config.properties_collection} p ON (b.property_id::text = p.id::text OR b.property_name = p.name)"
            
        params = {"from": from_dt, "to": to_dt}
        where_clauses = ["b.check_in_date >= :from", "b.check_in_date <= :to"]
        
        if property_ids:
            where_clauses.append("(b.property_id::text = ANY(:pids) OR b.property_name = ANY(:pids))")
            params["pids"] = list(property_ids)
            
        if owner_ids:
            where_clauses.append("p.owner_id::text = ANY(:oids)")
            params["oids"] = list(owner_ids)
            
        query += " WHERE " + " AND ".join(where_clauses)
        
        result = await self.session.execute(text(query), params)
        return [dict(row._mapping) for row in result.fetchall()]

    async def get_scheduled_reports(self) -> List[Dict[str, Any]]:
        try:
            query = text("SELECT * FROM scheduled_reports ORDER BY created_at DESC")
            result = await self.session.execute(query)
            reports = []
            for row in result.fetchall():
                report = dict(row._mapping)
                # Convert DATE objects to strings for JSON serialization
                if report.get("next_run"):
                    report["next_run"] = report["next_run"].isoformat()
                if report.get("last_run"):
                    report["last_run"] = report["last_run"].isoformat()
                if report.get("created_at"):
                    report["created_at"] = report["created_at"].isoformat()
                reports.append(report)
            return reports
        except Exception as e:
            self.logger.error(f"Error fetching scheduled reports: {e}", exc_info=True)
            raise

    async def create_scheduled_report(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Calculate next run based on frequency
            freq = data.get("frequency", "weekly")
            now = datetime.utcnow().date()
            if freq == "weekly":
                next_run = now + timedelta(days=7)
            elif freq == "monthly":
                # Rough approximation for monthly
                next_run = now + timedelta(days=30)
            elif freq == "quarterly":
                next_run = now + timedelta(days=90)
            else:
                next_run = now + timedelta(days=7)

            query = text("""
                INSERT INTO scheduled_reports 
                (report_type, name, frequency, recipients, filters, next_run, is_active)
                VALUES (:report_type, :name, :frequency, :recipients, :filters, :next_run, :is_active)
                RETURNING *
            """)
            
            params = {
                "report_type": data.get("report_type"),
                "name": data.get("name"),
                "frequency": freq,
                "recipients": data.get("recipients", []),
                "filters": json.dumps(data.get("filters", {})),
                "next_run": next_run,
                "is_active": True
            }
            
            result = await self.session.execute(query, params)
            row = result.fetchone()
            report = dict(row._mapping)
            if report.get("next_run"):
                report["next_run"] = report["next_run"].isoformat()
            if report.get("created_at"):
                report["created_at"] = report["created_at"].isoformat()
            return report
        except Exception as e:
            self.logger.error(f"Error creating scheduled report: {e}", exc_info=True)
            raise

    async def delete_scheduled_report(self, report_id: int) -> bool:
        try:
            query = text("DELETE FROM scheduled_reports WHERE id = :id")
            await self.session.execute(query, {"id": report_id})
            return True
        except Exception as e:
            self.logger.error(f"Error deleting scheduled report: {e}", exc_info=True)
            raise

    async def toggle_scheduled_report(self, report_id: int, is_active: bool) -> bool:
        try:
            query = text("UPDATE scheduled_reports SET is_active = :is_active, updated_at = CURRENT_TIMESTAMP WHERE id = :id")
            await self.session.execute(query, {"id": report_id, "is_active": is_active})
            return True
        except Exception as e:
            self.logger.error(f"Error toggling scheduled report: {e}", exc_info=True)
            raise
