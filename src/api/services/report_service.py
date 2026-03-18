from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
import json
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from src.utils.report_pdf import generate_pdf_report
from src.utils.report_email import build_email_html, send_email_with_pdf


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
            # 1. Fetch current period data
            bookings = await self._fetch_filtered_bookings(from_date, to_date, property_ids)
            booking_ids = [str(b.get("reservation_id")) for b in bookings if b.get("reservation_id")]
            services = await self._fetch_services_for_bookings(booking_ids)
            
            # 2. Fetch previous period for trends
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            days_in_period = (to_dt - from_dt).days + 1
            prev_to_dt = from_dt - timedelta(days=1)
            prev_from_dt = prev_to_dt - timedelta(days=days_in_period - 1)
            
            prev_bookings = await self._fetch_filtered_bookings(prev_from_dt.strftime("%Y-%m-%d"), prev_to_dt.strftime("%Y-%m-%d"), property_ids)
            prev_booking_ids = [str(b.get("reservation_id")) for b in prev_bookings if b.get("reservation_id")]
            prev_services = await self._fetch_services_for_bookings(prev_booking_ids)
            
            total_rev = sum(float(s.get("price") or 0) for s in services)
            prev_total_rev = sum(float(s.get("price") or 0) for s in prev_services)
            
            # 3. Group by service name
            service_stats = {}
            for s in services:
                name = s.get("service_name") or "Unknown"
                if name not in service_stats:
                    service_stats[name] = {
                        "service_type": "Service", # Placeholder as we don't have explicit type
                        "service_name": name,
                        "total_revenue": 0,
                        "bookings_count": 0,
                        "average_price": 0,
                        "trend": 0
                    }
                service_stats[name]["total_revenue"] += float(s.get("price") or 0)
                service_stats[name]["bookings_count"] += 1

            # Calculate trends for services
            prev_service_stats = {}
            for s in prev_services:
                name = s.get("service_name") or "Unknown"
                if name not in prev_service_stats:
                    prev_service_stats[name] = 0
                prev_service_stats[name] += float(s.get("price") or 0)

            for name, stats in service_stats.items():
                stats["average_price"] = round(stats["total_revenue"] / stats["bookings_count"], 2) if stats["bookings_count"] > 0 else 0
                prev_rev = prev_service_stats.get(name, 0)
                if prev_rev > 0:
                    stats["trend"] = round(((stats["total_revenue"] - prev_rev) / prev_rev * 100), 2)
                else:
                    stats["trend"] = 100 if stats["total_revenue"] > 0 else 0

            # 4. Group by month
            by_month = {}
            for s in services:
                # Need to find the booking date for this service
                # The service object doesn't have the date directly, but we can find it from booking_ids
                # Actually, bs.service_date is in the table but not fetched in _fetch_services_for_bookings
                # Let's use the month of the service_date if available, else fallback to booking check-in
                month = s.get("service_date").strftime("%b") if s.get("service_date") else "Unknown"
                if month not in by_month:
                    by_month[month] = {"month": month, "revenue": 0, "bookings": 0}
                by_month[month]["revenue"] += float(s.get("price") or 0)
                by_month[month]["bookings"] += 1

            # 5. Group by property
            prop_stats = {}
            # Need to map booking_id to property info
            booking_prop_map = {str(b["reservation_id"]): {"id": str(b.get("property_id")), "name": b.get("property_name") or "Unknown"} for b in bookings}
            
            for s in services:
                bid = str(s.get("booking_id"))
                p_info = booking_prop_map.get(bid, {"id": "Unknown", "name": "Unknown"})
                pid = p_info["id"]
                if pid not in prop_stats:
                    prop_stats[pid] = {"property_id": pid, "property_name": p_info["name"], "revenue": 0, "bookings": 0}
                prop_stats[pid]["revenue"] += float(s.get("price") or 0)
                prop_stats[pid]["bookings"] += 1

            return {
                "period_start": from_date,
                "period_end": to_date,
                "total_revenue": round(total_rev, 2),
                "total_bookings": len(services),
                "services": list(service_stats.values()),
                "by_month": list(by_month.values()),
                "top_properties": sorted(list(prop_stats.values()), key=lambda x: x["revenue"], reverse=True)[:5]
            }
        except Exception as e:
            self.logger.error(f"Error generating service revenue report: {e}", exc_info=True)
            raise

    async def get_performance_report(self, from_date: str, to_date: str, property_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        try:
            # 1. Calculate periods
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            days_in_period = (to_dt - from_dt).days + 1
            
            prev_to_dt = from_dt - timedelta(days=1)
            prev_from_dt = prev_to_dt - timedelta(days=days_in_period - 1)
            
            prev_from_date = prev_from_dt.strftime("%Y-%m-%d")
            prev_to_date = prev_to_dt.strftime("%Y-%m-%d")

            # 2. Fetch properties count for occupancy calculation
            prop_query = f"SELECT COUNT(*) FROM {app_config.properties_collection}"
            prop_params = {}
            if property_ids:
                prop_query += " WHERE id::text = ANY(:pids) OR name = ANY(:pids)"
                prop_params["pids"] = list(property_ids)
            
            prop_res = await self.session.execute(text(prop_query), prop_params)
            num_properties = prop_res.scalar() or 1

            # 3. Fetch bookings for both periods
            current_bookings = await self._fetch_filtered_bookings(from_date, to_date, property_ids)
            previous_bookings = await self._fetch_filtered_bookings(prev_from_date, prev_to_date, property_ids)

            def calculate_metrics(bookings, start_date, end_date, label):
                total_rev = sum(float(b.get("total_amount") or 0) for b in bookings)
                total_bookings = len(bookings)
                
                # Calculate nights from check-in and check-out if 'nights' is 0 or missing
                total_nights = 0
                for b in bookings:
                    n = int(b.get("nights") or 0)
                    if n <= 0:
                        try:
                            check_in = b.get("check_in_date")
                            check_out = b.get("check_out_date")
                            if check_in and check_out:
                                # Ensure we have date objects
                                if isinstance(check_in, str):
                                    check_in = datetime.strptime(check_in, "%Y-%m-%d").date()
                                if isinstance(check_out, str):
                                    check_out = datetime.strptime(check_out, "%Y-%m-%d").date()
                                
                                diff = (check_out - check_in).days
                                n = max(0, diff)
                        except (ValueError, TypeError, AttributeError):
                            n = 1 # Fallback to 1 night per booking if calculation fails
                    total_nights += n
                
                adr = total_rev / total_nights if total_nights > 0 else 0
                
                # Occupancy = booked nights / (days in period * number of properties)
                total_possible_nights = days_in_period * num_properties
                occupancy = (total_nights / total_possible_nights * 100) if total_possible_nights > 0 else 0
                
                return {
                    "start": start_date,
                    "end": end_date,
                    "label": label,
                    "total_revenue": round(total_rev, 2),
                    "total_bookings": total_bookings,
                    "average_daily_rate": round(adr, 2),
                    "occupancy_rate": round(occupancy, 2),
                    "total_nights": total_nights
                }

            current_metrics = calculate_metrics(current_bookings, from_date, to_date, "Current Period")
            previous_metrics = calculate_metrics(previous_bookings, prev_from_date, prev_to_date, "Previous Period")

            # 4. Metrics Comparison
            def get_comparison(metric_name, current_val, previous_val):
                change = current_val - previous_val
                change_pct = (change / previous_val * 100) if previous_val != 0 else (100 if current_val > 0 else 0)
                return {
                    "metric": metric_name,
                    "current_value": current_val,
                    "previous_value": previous_val,
                    "change": round(change, 2),
                    "change_percentage": round(change_pct, 2),
                    "trend": "up" if change > 0 else "down" if change < 0 else "neutral"
                }

            metrics_comparison = [
                get_comparison("Revenue", current_metrics["total_revenue"], previous_metrics["total_revenue"]),
                get_comparison("Occupancy", current_metrics["occupancy_rate"], previous_metrics["occupancy_rate"]),
                get_comparison("ADR", current_metrics["average_daily_rate"], previous_metrics["average_daily_rate"])
            ]

            # 5. Trend Data (Revenue and Occupancy)
            # Group by date
            rev_trend_map = {}
            occ_trend_map = {}
            
            # Initialize with current period dates
            for i in range(days_in_period):
                d = (from_dt + timedelta(days=i)).strftime("%Y-%m-%d")
                rev_trend_map[d] = {"date": d, "current": 0, "previous": 0}
                occ_trend_map[d] = {"date": d, "current": 0, "previous": 0}

            for b in current_bookings:
                d_dt = b.get("check_in_date")
                if d_dt:
                    if isinstance(d_dt, datetime):
                        d_dt = d_dt.date()
                    d = d_dt.strftime("%Y-%m-%d")
                    if d in rev_trend_map:
                        rev_trend_map[d]["current"] += float(b.get("total_amount") or 0)
                        occ_trend_map[d]["current"] += int(b.get("nights") or 0)

            # Map previous period data to current period timeline for comparison
            for b in previous_bookings:
                # Find corresponding date in current period
                b_dt = b.get("check_in_date")
                if b_dt:
                    # Ensure we are comparing dates, not datetimes
                    if isinstance(b_dt, datetime):
                        b_dt = b_dt.date()
                    
                    days_diff = (b_dt - prev_from_dt).days
                    if 0 <= days_diff < days_in_period:
                        target_dt = (from_dt + timedelta(days=days_diff)).strftime("%Y-%m-%d")
                        if target_dt in rev_trend_map:
                            rev_trend_map[target_dt]["previous"] += float(b.get("total_amount") or 0)
                            occ_trend_map[target_dt]["previous"] += int(b.get("nights") or 0)

            # Convert occ_trend_map counts to percentages
            for d in occ_trend_map:
                occ_trend_map[d]["current"] = round((occ_trend_map[d]["current"] / num_properties * 100), 2)
                occ_trend_map[d]["previous"] = round((occ_trend_map[d]["previous"] / num_properties * 100), 2)

            return {
                "current_period": current_metrics,
                "previous_period": previous_metrics,
                "comparison_type": "period",
                "metrics_comparison": metrics_comparison,
                "revenue_trend": sorted(list(rev_trend_map.values()), key=lambda x: x["date"]),
                "occupancy_trend": sorted(list(occ_trend_map.values()), key=lambda x: x["date"])
            }
        except Exception as e:
            self.logger.error(f"Error generating performance report: {e}", exc_info=True)
            raise

    async def get_service_provider_report(self, from_date: str, to_date: str, provider_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            # Convert string dates to date objects for SQLAlchemy/asyncpg
            try:
                from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
                to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                # Fallback to strings if format is wrong or already date objects
                from_dt = from_date
                to_dt = to_date

            # If no provider_id is specified, try to find the first available provider to make the report "just work"
            if not provider_id:
                # Try cleaning crews first
                crew_check = text(f"SELECT id FROM {app_config.cleaning_crews_collection} WHERE active = True LIMIT 1")
                crew_check_res = await self.session.execute(crew_check)
                first_crew = crew_check_res.fetchone()
                if first_crew:
                    provider_id = str(first_crew[0])
                else:
                    # Try service categories
                    cat_check = text("SELECT id FROM service_category WHERE status = True LIMIT 1")
                    cat_check_res = await self.session.execute(cat_check)
                    first_cat = cat_check_res.fetchone()
                    if first_cat:
                        provider_id = str(first_cat[0])
            
            if not provider_id:
                # If still no provider found in DB, we can't generate a report
                raise HTTPException(status_code=404, detail="No active service providers found in database")

            # 1. Try to find in cleaning_crews first
            crew_query = text(f"SELECT * FROM {app_config.cleaning_crews_collection} WHERE id::text = :id")
            crew_res = await self.session.execute(crew_query, {"id": provider_id})
            provider = crew_res.fetchone()
            
            provider_data = None
            jobs = []
            
            if provider:
                provider = dict(provider._mapping)
                provider_data = {
                    "provider_id": str(provider["id"]),
                    "provider_name": provider["name"],
                    "provider_email": provider["email"],
                    "provider_phone": provider["phone"],
                    "service_type": provider["role"] or "Cleaning"
                }
                
                # Fetch cleaning tasks for this provider
                tasks_query = text(f"""
                    SELECT ct.id as job_id, ct.scheduled_date as date, p.name as property_name, 
                           b.guest_name, 'Cleaning' as service_details, 
                           150.0 as amount, 0.0 as tip, ct.status
                    FROM {app_config.cleaning_tasks_collection} ct
                    LEFT JOIN {app_config.properties_collection} p ON (ct.property_id::text = p.id::text OR ct.property_id = p.name)
                    LEFT JOIN {app_config.bookings_collection} b ON ct.reservation_id = b.reservation_id
                    WHERE ct.crew_id::text = :id AND ct.scheduled_date >= :from AND ct.scheduled_date <= :to
                    ORDER BY ct.scheduled_date DESC
                """)
                tasks_res = await self.session.execute(tasks_query, {
                    "id": provider_id,
                    "from": from_dt,
                    "to": to_dt
                })
                jobs = [dict(row._mapping) for row in tasks_res.fetchall()]
            else:
                # 2. Try to find in service_category
                cat_query = text(f"SELECT * FROM service_category WHERE id::text = :id")
                cat_res = await self.session.execute(cat_query, {"id": provider_id})
                category = cat_res.fetchone()
                
                if category:
                    category = dict(category._mapping)
                    provider_data = {
                        "provider_id": str(category["id"]),
                        "provider_name": category["category_name"],
                        "provider_email": category["email"],
                        "provider_phone": category["phone"],
                        "service_type": category["category_name"]
                    }
                    
                    # Fetch service bookings for this category
                    services_query = text(f"""
                        SELECT bs.id as job_id, bs.service_date as date, p.name as property_name,
                               b.guest_name, sc.category_name as service_details,
                               sc.price as amount, 0.0 as tip, bs.status
                        FROM booking_service bs
                        LEFT JOIN service_category sc ON bs.service_id = sc.id
                        LEFT JOIN {app_config.bookings_collection} b ON bs.booking_id = b.reservation_id
                        LEFT JOIN {app_config.properties_collection} p ON (b.property_id::text = p.id::text OR b.property_name = p.name)
                        WHERE bs.service_id::text = :id AND bs.service_date >= :from AND bs.service_date <= :to
                        ORDER BY bs.service_date DESC
                    """)
                    services_res = await self.session.execute(services_query, {
                        "id": provider_id,
                        "from": from_dt,
                        "to": to_dt
                    })
                    jobs = [dict(row._mapping) for row in services_res.fetchall()]

            if not provider_data:
                raise HTTPException(status_code=404, detail="Provider not found")

            # Format jobs and calculate totals
            total_rev = 0
            for job in jobs:
                total_rev += float(job.get("amount") or 0)
                # Serialize dates
                if job.get("date") and hasattr(job["date"], "isoformat"):
                    job["date"] = job["date"].isoformat()
                elif job.get("date") and hasattr(job["date"], "strftime"):
                    job["date"] = job["date"].strftime("%Y-%m-%d")
            
            # Use a default commission rate (e.g., 10%) if not defined
            commission_rate = 10.0
            commission_amount = total_rev * (commission_rate / 100.0)
            
            return {
                **provider_data,
                "period_start": from_date,
                "period_end": to_date,
                "jobs": jobs,
                "total_revenue": round(total_rev, 2),
                "total_jobs": len(jobs),
                "commission_rate": commission_rate,
                "commission_amount": round(commission_amount, 2),
                "net_payout": round(total_rev - commission_amount, 2),
                "average_job_value": round(total_rev / len(jobs), 2) if jobs else 0
            }
        except HTTPException:
            raise
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

    def _calculate_next_run(self, freq: str):
        now = datetime.utcnow().date()
        if freq == "weekly":
            return now + timedelta(days=7)
        elif freq == "monthly":
            return now + timedelta(days=30)
        elif freq == "quarterly":
            return now + timedelta(days=90)
        return now + timedelta(days=7)

   

    async def run_scheduled_reports(self):
        try:
            query = text("""
                SELECT * FROM scheduled_reports
                WHERE is_active = true
                AND next_run <= CURRENT_DATE
            """)
            result = await self.session.execute(query)
            reports = result.fetchall()

            for row in reports:
                report = dict(row._mapping)

                report_type = report.get("report_type")
                filters = report.get("filters", {})
                if isinstance(filters, str):
                    filters = json.loads(filters)

                recipients = report.get("recipients", [])
                if isinstance(recipients, str):
                    recipients = json.loads(recipients)
                from_date = filters.get("from")
                to_date = filters.get("to")

                data = None

                # ✅ Generate report
                if report_type == "booking":
                    data = await self.get_booking_summary(from_date, to_date)
                    title = "Booking Report"

                elif report_type == "occupancy":
                    data = await self.get_occupancy_report(from_date, to_date)
                    title = "Occupancy Report"

                elif report_type == "owner":
                    data = await self.get_owner_statement(from_date, to_date)
                    title = "Owner Statement"

                if not data:
                    continue

                # ✅ Generate PDF
                pdf_bytes = generate_pdf_report(title, data)

                # ✅ Send Email to all recipients
                for email in recipients:
                    send_email_with_pdf(
                        to_email=email,
                        subject=f"{title} ({from_date} to {to_date})",
                        content=build_email_html(title, from_date, to_date),
                        pdf_bytes=pdf_bytes
                    )

                # ✅ Update next_run
                next_run = self._calculate_next_run(report.get("frequency"))

                update_query = text("""
                    UPDATE scheduled_reports
                    SET last_run = CURRENT_TIMESTAMP,
                        next_run = :next_run
                    WHERE id = :id
                """)

                await self.session.execute(update_query, {
                    "next_run": next_run,
                    "id": report.get("id")
                })

            await self.session.commit()

        except Exception as e:
            self.logger.error(f"Error running scheduled reports: {e}", exc_info=True)
            raise
        