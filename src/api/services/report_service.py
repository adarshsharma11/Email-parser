from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
import logging
import json
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from src.utils.report_email import build_email_html, send_email_with_pdf
from src.utils.report_pdf import generate_pdf_report, get_report_filename
from config.settings import app_config


class ReportService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = logging.getLogger(__name__)

    async def _fetch_filtered_bookings(self, from_date: str, to_date: str, 
                                        property_ids: Optional[List[str]] = None, 
                                        owner_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Fetch bookings filtered by date range, properties, and/or owners"""
        
        # Convert string dates to date objects
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            from_dt = from_date
            to_dt = to_date

        # Build query with property join to get owner info
        # Removed p.owner_name as it doesn't exist in the database
        query = f"""
            SELECT b.*, 
                   p.name as property_name, 
                   p.address, 
                   p.owner_id
            FROM {app_config.bookings_collection} b
            LEFT JOIN {app_config.properties_collection} p 
                ON b.property_id::text = p.id::text
        """
        
        params = {"from": from_dt, "to": to_dt}
        where_clauses = ["b.check_in_date >= :from", "b.check_in_date <= :to"]
        
        # Add property filter if provided
        if property_ids and len(property_ids) > 0:
            placeholders = []
            for i, pid in enumerate(property_ids):
                param_key = f"pid_{i}"
                params[param_key] = pid
                placeholders.append(f"b.property_id::text = :{param_key}")
                placeholders.append(f"b.property_name = :{param_key}")
            where_clauses.append(f"({' OR '.join(placeholders)})")
        
        # Add owner filter if provided
        if owner_ids and len(owner_ids) > 0:
            owner_placeholders = []
            for i, oid in enumerate(owner_ids):
                param_key = f"oid_{i}"
                params[param_key] = oid
                owner_placeholders.append(f"p.owner_id::text = :{param_key}")
            where_clauses.append(f"({' OR '.join(owner_placeholders)})")
        
        query += " WHERE " + " AND ".join(where_clauses)
        query += " ORDER BY b.check_in_date DESC"
        
        self.logger.debug(f"Executing query with params: {params}")
        
        result = await self.session.execute(text(query), params)
        bookings = [dict(row._mapping) for row in result.fetchall()]
        
        self.logger.info(f"Found {len(bookings)} bookings for period {from_date} to {to_date}")
        
        return bookings

    async def _fetch_services_for_bookings(self, booking_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch services for given booking IDs"""
        if not booking_ids:
            return []
        
        query = text("""
            SELECT bs.*, sc.category_name as service_name, sc.price 
            FROM booking_service bs
            JOIN service_category sc ON bs.service_id = sc.id
            WHERE bs.booking_id::text = ANY(:bids)
        """)
        result = await self.session.execute(query, {"bids": booking_ids})
        return [dict(row._mapping) for row in result.fetchall()]

    def _calculate_nights(self, booking: Dict[str, Any]) -> int:
        """Calculate nights from booking data"""
        # First try the nights field
        nights = int(booking.get("nights") or 0)
        if nights > 0:
            return nights
        
        # Calculate from check-in/check-out dates
        try:
            check_in = booking.get("check_in_date")
            check_out = booking.get("check_out_date")
            
            if not check_in or not check_out:
                return 1
            
            # Convert to date objects if needed
            if isinstance(check_in, str):
                check_in = datetime.strptime(check_in, "%Y-%m-%d").date()
            if isinstance(check_out, str):
                check_out = datetime.strptime(check_out, "%Y-%m-%d").date()
            
            if hasattr(check_in, 'date'):
                check_in = check_in.date()
            if hasattr(check_out, 'date'):
                check_out = check_out.date()
            
            nights = (check_out - check_in).days
            return max(1, nights)
        except Exception as e:
            self.logger.warning(f"Error calculating nights: {e}")
            return 1

    def _get_channel_fee_rate(self, platform: str) -> float:
        """Get channel fee rate based on platform"""
        platform_lower = (platform or "").lower()
        if "airbnb" in platform_lower:
            return 0.03  # 3%
        elif "vrbo" in platform_lower:
            return 0.05  # 5%
        elif "booking" in platform_lower:
            return 0.15  # 15%
        elif "direct" in platform_lower:
            return 0.00  # 0%
        else:
            return 0.03  # Default 3%

    async def get_owner_statement(self, from_date: str, to_date: str, 
                                   property_ids: Optional[List[str]] = None, 
                                   owner_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Generate owner statement for the given period"""
        try:
            self.logger.info(f"Generating owner statement: from={from_date}, to={to_date}, owner_ids={owner_ids}")
            
            # Calculate days in period
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            days_in_period = (to_dt - from_dt).days + 1
            
            # Fetch bookings
            bookings = await self._fetch_filtered_bookings(from_date, to_date, property_ids, owner_ids)
            
            # Fetch services
            booking_ids = [str(b.get("reservation_id")) for b in bookings if b.get("reservation_id")]
            services = await self._fetch_services_for_bookings(booking_ids)
            
            # Group by property
            properties_data = {}
            global_services_breakdown = {}
            total_rental_revenue = 0
            total_services_revenue = 0
            
            for b in bookings:
                property_id = str(b.get("property_id") or "unknown")
                property_name = b.get("property_name") or b.get("property_name_from_booking") or "Unknown Property"
                
                if property_id not in properties_data:
                    properties_data[property_id] = {
                        "property_id": property_id,
                        "property_name": property_name,
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
                
                booking_id = str(b.get("reservation_id"))
                revenue = float(b.get("total_amount") or 0)
                nights = self._calculate_nights(b)
                channel_fee_rate = self._get_channel_fee_rate(b.get("platform"))
                channel_fee = revenue * channel_fee_rate
                
                # Get services for this booking
                booking_services = [s for s in services if str(s.get("booking_id")) == booking_id]
                booking_services_rev = sum(float(s.get("price") or 0) for s in booking_services)
                
                # Update property totals
                properties_data[property_id]["rental_revenue"] += revenue
                properties_data[property_id]["services_revenue"] += booking_services_rev
                properties_data[property_id]["total_revenue"] += (revenue + booking_services_rev)
                properties_data[property_id]["nights_booked"] += nights
                properties_data[property_id]["channel_fees"] += channel_fee
                
                total_rental_revenue += revenue
                total_services_revenue += booking_services_rev
                
                # Track service breakdown
                for s in booking_services:
                    service_name = s.get("service_name") or "Unknown Service"
                    service_price = float(s.get("price") or 0)
                    
                    # Per property
                    if service_name not in properties_data[property_id]["services_breakdown"]:
                        properties_data[property_id]["services_breakdown"][service_name] = {
                            "name": service_name, "count": 0, "revenue": 0
                        }
                    properties_data[property_id]["services_breakdown"][service_name]["count"] += 1
                    properties_data[property_id]["services_breakdown"][service_name]["revenue"] += service_price
                    
                    # Global
                    if service_name not in global_services_breakdown:
                        global_services_breakdown[service_name] = {
                            "name": service_name, "count": 0, "revenue": 0
                        }
                    global_services_breakdown[service_name]["count"] += 1
                    global_services_breakdown[service_name]["revenue"] += service_price
                
                # Format dates
                check_in = b.get("check_in_date")
                check_out = b.get("check_out_date")
                check_in_str = check_in.strftime("%Y-%m-%d") if hasattr(check_in, 'strftime') else str(check_in)[:10] if check_in else None
                check_out_str = check_out.strftime("%Y-%m-%d") if hasattr(check_out, 'strftime') else str(check_out)[:10] if check_out else None
                
                # Add booking
                properties_data[property_id]["bookings"].append({
                    "booking_id": booking_id,
                    "guest_name": b.get("guest_name") or "Unknown Guest",
                    "check_in": check_in_str,
                    "check_out": check_out_str,
                    "nights": nights,
                    "revenue": revenue,
                    "services_revenue": booking_services_rev,
                    "services": [{"service_name": s.get("service_name"), "price": float(s.get("price") or 0)} for s in booking_services],
                    "channel": b.get("platform") or "Direct",
                    "channel_fee": channel_fee,
                    "cleaning_fee": 0,
                })
            
            # Calculate final metrics for each property
            total_net_payout = 0
            for pid, pdata in properties_data.items():
                pdata["net_revenue"] = round(pdata["total_revenue"] - pdata["channel_fees"], 2)
                if pdata["nights_booked"] > 0:
                    pdata["average_daily_rate"] = round(pdata["rental_revenue"] / pdata["nights_booked"], 2)
                pdata["occupancy_rate"] = round((pdata["nights_booked"] / days_in_period) * 100, 2) if days_in_period > 0 else 0
                total_net_payout += pdata["net_revenue"]
                pdata["services_summary"] = list(pdata["services_breakdown"].values())
            
            # Calculate management fee
            management_fee = total_net_payout * 0.10
            total_payout = total_net_payout - management_fee
            
            return {
                "owner_id": owner_ids[0] if owner_ids else "global",
                "owner_name": "Global Admin",
                "owner_email": "admin@moma.house",
                "period_start": from_date,
                "period_end": to_date,
                "properties": list(properties_data.values()),
                "services_summary": list(global_services_breakdown.values()),
                "rental_revenue": round(total_rental_revenue, 2),
                "services_revenue": round(total_services_revenue, 2),
                "total_revenue": round(total_rental_revenue + total_services_revenue, 2),
                "total_expenses": round(total_rental_revenue * 0.1, 2),
                "total_payout": round(total_payout, 2),
                "management_fee": round(management_fee, 2),
                "management_fee_percentage": 10.00,
            }
        except Exception as e:
            self.logger.error(f"Error generating owner statement: {e}", exc_info=True)
            raise

    async def get_booking_summary(self, from_date: str, to_date: str, 
                                   property_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Generate booking summary report"""
        try:
            bookings = await self._fetch_filtered_bookings(from_date, to_date, property_ids)
            
            total_rev = sum(float(b.get("total_amount") or 0) for b in bookings)
            total_nights = sum(self._calculate_nights(b) for b in bookings)
            
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
                pid = str(b.get("property_id") or "unknown")
                pname = b.get("property_name") or "Unknown"
                if pid not in by_property:
                    by_property[pid] = {"property_id": pid, "property_name": pname, "count": 0, "revenue": 0}
                by_property[pid]["count"] += 1
                by_property[pid]["revenue"] += float(b.get("total_amount") or 0)

            return {
                "period_start": from_date,
                "period_end": to_date,
                "total_bookings": len(bookings),
                "total_revenue": round(total_rev, 2),
                "total_nights": total_nights,
                "average_booking_value": round(total_rev / len(bookings), 2) if bookings else 0,
                "bookings": [
                    {
                        "booking_id": b.get("reservation_id"),
                        "property_name": b.get("property_name") or "Unknown",
                        "guest_name": b.get("guest_name") or "Unknown Guest",
                        "guest_email": b.get("guest_email"),
                        "check_in": b.get("check_in_date").strftime("%Y-%m-%d") if hasattr(b.get("check_in_date"), 'strftime') else str(b.get("check_in_date"))[:10] if b.get("check_in_date") else None,
                        "check_out": b.get("check_out_date").strftime("%Y-%m-%d") if hasattr(b.get("check_out_date"), 'strftime') else str(b.get("check_out_date"))[:10] if b.get("check_out_date") else None,
                        "nights": self._calculate_nights(b),
                        "guests": b.get("number_of_guests"),
                        "total_amount": float(b.get("total_amount") or 0),
                        "channel": b.get("platform") or "Direct",
                        "status": "Confirmed",
                        "payment_status": "Paid",
                        "created_at": b.get("created_at").strftime("%Y-%m-%d") if hasattr(b.get("created_at"), 'strftime') else str(b.get("created_at"))[:10] if b.get("created_at") else None,
                    } for b in bookings
                ],
                "by_channel": list(by_channel.values()),
                "by_property": list(by_property.values()),
            }
        except Exception as e:
            self.logger.error(f"Error generating booking summary: {e}", exc_info=True)
            raise

    async def get_occupancy_report(self, from_date: str, to_date: str, 
                                    property_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Generate occupancy report"""
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            days_in_period = (to_dt - from_dt).days + 1

            # Get all properties
            all_props_query = f"SELECT id, name, address FROM {app_config.properties_collection}"
            params = {}
            if property_ids:
                all_props_query += " WHERE id::text = ANY(:pids)"
                params["pids"] = list(property_ids)
            
            props_res = await self.session.execute(text(all_props_query), params)
            properties_list = [dict(row._mapping) for row in props_res.fetchall()]

            # Initialize property data
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

            # Fetch bookings
            bookings = await self._fetch_filtered_bookings(from_date, to_date, property_ids)
            
            for b in bookings:
                pid = str(b.get("property_id"))
                if pid not in by_property:
                    # Add if missing
                    by_property[pid] = {
                        "property_id": pid,
                        "property_name": b.get("property_name") or "Unknown",
                        "property_address": b.get("address") or "N/A",
                        "occupancy_rate": 0.00,
                        "available_nights": days_in_period,
                        "booked_nights": 0,
                        "blocked_nights": 0,
                        "revenue": 0.00,
                        "average_daily_rate": 0.00
                    }
                
                nights = self._calculate_nights(b)
                rev = float(b.get("total_amount") or 0)
                by_property[pid]["booked_nights"] += nights
                by_property[pid]["revenue"] += rev

            # Calculate rates
            for pid, pdata in by_property.items():
                if days_in_period > 0:
                    pdata["occupancy_rate"] = round((pdata["booked_nights"] / days_in_period) * 100, 2)
                if pdata["booked_nights"] > 0:
                    pdata["average_daily_rate"] = round(pdata["revenue"] / pdata["booked_nights"], 2)
                pdata["available_nights"] = days_in_period - pdata["booked_nights"]

            total_booked = sum(p["booked_nights"] for p in by_property.values())
            total_avail = len(by_property) * days_in_period

            return {
                "period_start": from_date,
                "period_end": to_date,
                "overall_occupancy": round((total_booked / total_avail * 100), 2) if total_avail > 0 else 0,
                "total_available_nights": total_avail,
                "total_booked_nights": total_booked,
                "properties": list(by_property.values()),
                "by_month": [{"month": from_date[:7], "occupancy": round((total_booked / total_avail * 100), 2) if total_avail > 0 else 0, "nights_booked": total_booked}]
            }
        except Exception as e:
            self.logger.error(f"Error generating occupancy report: {e}", exc_info=True)
            raise

    async def get_service_revenue(self, from_date: str, to_date: str, 
                                   property_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Generate service revenue report"""
        try:
            # Fetch current period data
            bookings = await self._fetch_filtered_bookings(from_date, to_date, property_ids)
            booking_ids = [str(b.get("reservation_id")) for b in bookings if b.get("reservation_id")]
            services = await self._fetch_services_for_bookings(booking_ids)
            
            # Fetch previous period for trends
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            days_in_period = (to_dt - from_dt).days + 1
            prev_to_dt = from_dt - timedelta(days=1)
            prev_from_dt = prev_to_dt - timedelta(days=days_in_period - 1)
            
            prev_bookings = await self._fetch_filtered_bookings(
                prev_from_dt.strftime("%Y-%m-%d"), 
                prev_to_dt.strftime("%Y-%m-%d"), 
                property_ids
            )
            prev_booking_ids = [str(b.get("reservation_id")) for b in prev_bookings if b.get("reservation_id")]
            prev_services = await self._fetch_services_for_bookings(prev_booking_ids)
            
            total_rev = sum(float(s.get("price") or 0) for s in services)
            
            # Group by service name
            service_stats = {}
            for s in services:
                name = s.get("service_name") or "Unknown"
                if name not in service_stats:
                    service_stats[name] = {
                        "service_type": "Service",
                        "service_name": name,
                        "total_revenue": 0,
                        "bookings_count": 0,
                        "average_price": 0,
                        "trend": 0
                    }
                service_stats[name]["total_revenue"] += float(s.get("price") or 0)
                service_stats[name]["bookings_count"] += 1

            # Calculate trends
            prev_service_stats = {}
            for s in prev_services:
                name = s.get("service_name") or "Unknown"
                prev_service_stats[name] = prev_service_stats.get(name, 0) + float(s.get("price") or 0)

            for name, stats in service_stats.items():
                stats["average_price"] = round(stats["total_revenue"] / stats["bookings_count"], 2) if stats["bookings_count"] > 0 else 0
                prev_rev = prev_service_stats.get(name, 0)
                if prev_rev > 0:
                    stats["trend"] = round(((stats["total_revenue"] - prev_rev) / prev_rev * 100), 2)
                else:
                    stats["trend"] = 100 if stats["total_revenue"] > 0 else 0

            # Group by property
            booking_prop_map = {str(b["reservation_id"]): {"id": str(b.get("property_id")), "name": b.get("property_name") or "Unknown"} for b in bookings}
            
            prop_stats = {}
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
                "by_month": [],
                "top_properties": sorted(list(prop_stats.values()), key=lambda x: x["revenue"], reverse=True)[:5]
            }
        except Exception as e:
            self.logger.error(f"Error generating service revenue report: {e}", exc_info=True)
            raise

    async def get_performance_report(self, from_date: str, to_date: str, 
                                      property_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Generate performance comparison report"""
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            days_in_period = (to_dt - from_dt).days + 1
            
            prev_to_dt = from_dt - timedelta(days=1)
            prev_from_dt = prev_to_dt - timedelta(days=days_in_period - 1)
            
            # Get properties count
            prop_query = f"SELECT COUNT(*) FROM {app_config.properties_collection}"
            prop_params = {}
            if property_ids:
                prop_query += " WHERE id::text = ANY(:pids)"
                prop_params["pids"] = list(property_ids)
            
            prop_res = await self.session.execute(text(prop_query), prop_params)
            num_properties = prop_res.scalar() or 1

            # Fetch bookings
            current_bookings = await self._fetch_filtered_bookings(from_date, to_date, property_ids)
            previous_bookings = await self._fetch_filtered_bookings(
                prev_from_dt.strftime("%Y-%m-%d"), 
                prev_to_dt.strftime("%Y-%m-%d"), 
                property_ids
            )

            def calculate_metrics(bookings, start_date, end_date, label):
                total_rev = sum(float(b.get("total_amount") or 0) for b in bookings)
                total_bookings = len(bookings)
                total_nights = sum(self._calculate_nights(b) for b in bookings)
                
                adr = total_rev / total_nights if total_nights > 0 else 0
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
            previous_metrics = calculate_metrics(previous_bookings, 
                                                 prev_from_dt.strftime("%Y-%m-%d"), 
                                                 prev_to_dt.strftime("%Y-%m-%d"), 
                                                 "Previous Period")

            # Metrics comparison
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

            # Revenue trend
            rev_trend_map = {}
            for i in range(days_in_period):
                d = (from_dt + timedelta(days=i)).strftime("%Y-%m-%d")
                rev_trend_map[d] = {"date": d, "current": 0, "previous": 0}

            for b in current_bookings:
                check_in = b.get("check_in_date")
                if check_in:
                    if hasattr(check_in, 'strftime'):
                        d = check_in.strftime("%Y-%m-%d")
                    else:
                        d = str(check_in)[:10]
                    if d in rev_trend_map:
                        rev_trend_map[d]["current"] += float(b.get("total_amount") or 0)

            for b in previous_bookings:
                check_in = b.get("check_in_date")
                if check_in:
                    if hasattr(check_in, 'strftime'):
                        b_dt = check_in.date() if hasattr(check_in, 'date') else check_in
                    else:
                        b_dt = datetime.strptime(str(check_in)[:10], "%Y-%m-%d").date()
                    
                    days_diff = (b_dt - prev_from_dt).days
                    if 0 <= days_diff < days_in_period:
                        target_dt = (from_dt + timedelta(days=days_diff)).strftime("%Y-%m-%d")
                        if target_dt in rev_trend_map:
                            rev_trend_map[target_dt]["previous"] += float(b.get("total_amount") or 0)

            return {
                "current_period": current_metrics,
                "previous_period": previous_metrics,
                "comparison_type": "period",
                "metrics_comparison": metrics_comparison,
                "revenue_trend": sorted(list(rev_trend_map.values()), key=lambda x: x["date"])
            }
        except Exception as e:
            self.logger.error(f"Error generating performance report: {e}", exc_info=True)
            raise

    async def get_service_provider_report(self, from_date: str, to_date: str, 
                                           provider_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate service provider report"""
        try:
            # Parse dates
            try:
                from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
                to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                from_dt = from_date
                to_dt = to_date

            # Find provider if not specified
            if not provider_id:
                crew_check = text(f"SELECT id FROM {app_config.cleaning_crews_collection} WHERE active = True LIMIT 1")
                crew_check_res = await self.session.execute(crew_check)
                first_crew = crew_check_res.fetchone()
                if first_crew:
                    provider_id = str(first_crew[0])
            
            if not provider_id:
                raise HTTPException(status_code=404, detail="No active service providers found")

            # Check cleaning crews first
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
                    "provider_email": provider.get("email", ""),
                    "provider_phone": provider.get("phone", ""),
                    "service_type": provider.get("role") or "Cleaning"
                }
                
                # Fetch cleaning tasks
                tasks_query = text(f"""
                    SELECT ct.id as job_id, ct.scheduled_date as date, p.name as property_name, 
                           b.guest_name, 'Cleaning' as service_details, 
                           150.0 as amount, 0.0 as tip, ct.status
                    FROM {app_config.cleaning_tasks_collection} ct
                    LEFT JOIN {app_config.properties_collection} p ON ct.property_id::text = p.id::text
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
                # Check service category
                cat_query = text("SELECT * FROM service_category WHERE id::text = :id")
                cat_res = await self.session.execute(cat_query, {"id": provider_id})
                category = cat_res.fetchone()
                
                if category:
                    category = dict(category._mapping)
                    provider_data = {
                        "provider_id": str(category["id"]),
                        "provider_name": category["category_name"],
                        "provider_email": category.get("email", ""),
                        "provider_phone": category.get("phone", ""),
                        "service_type": category["category_name"]
                    }
                    
                    # Fetch service bookings
                    services_query = text(f"""
                        SELECT bs.id as job_id, bs.service_date as date, p.name as property_name,
                               b.guest_name, sc.category_name as service_details,
                               sc.price as amount, 0.0 as tip, bs.status
                        FROM booking_service bs
                        JOIN service_category sc ON bs.service_id = sc.id
                        LEFT JOIN {app_config.bookings_collection} b ON bs.booking_id = b.reservation_id
                        LEFT JOIN {app_config.properties_collection} p ON b.property_id::text = p.id::text
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

            # Calculate totals
            total_rev = 0
            for job in jobs:
                total_rev += float(job.get("amount") or 0)
                if job.get("date") and hasattr(job["date"], "strftime"):
                    job["date"] = job["date"].strftime("%Y-%m-%d")
            
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

    async def get_scheduled_reports(self) -> List[Dict[str, Any]]:
        """Get all scheduled reports"""
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
        """
        Create a new scheduled report.
        
        This function:
        1. Takes user input (report_type, name, frequency, recipients, filters)
        2. Calculates the next_run date based on frequency
        3. Stores the schedule in the database
        4. Returns the created schedule
        
        The next_run is calculated as:
        - Weekly: 7 days from today (runs on the same day of week)
        - Monthly: 1st day of next month
        - Quarterly: 1st day of month, 3 months from now
        """
        try:
            freq = data.get("frequency", "weekly").lower()
            now = datetime.utcnow().date()
            
            if freq == "weekly":
                # Next run is exactly 7 days from now
                next_run = now + timedelta(days=7)
                
            elif freq == "monthly":
                # Next run is the 1st of next month
                if now.month == 12:
                    next_run = now.replace(year=now.year + 1, month=1, day=1)
                else:
                    next_run = now.replace(month=now.month + 1, day=1)
                    
            elif freq == "quarterly":
                # Next run is the 1st of month, 3 months from now
                month = now.month + 3
                year = now.year
                if month > 12:
                    month -= 12
                    year += 1
                next_run = now.replace(year=year, month=month, day=1)
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
        """Delete a scheduled report"""
        try:
            query = text("DELETE FROM scheduled_reports WHERE id = :id")
            await self.session.execute(query, {"id": report_id})
            return True
        except Exception as e:
            self.logger.error(f"Error deleting scheduled report: {e}", exc_info=True)
            raise

    async def toggle_scheduled_report(self, report_id: int, is_active: bool) -> bool:
        """Activate or deactivate a scheduled report"""
        try:
            query = text("""
                UPDATE scheduled_reports 
                SET is_active = :is_active, updated_at = CURRENT_TIMESTAMP 
                WHERE id = :id
            """)
            await self.session.execute(query, {"id": report_id, "is_active": is_active})
            return True
        except Exception as e:
            self.logger.error(f"Error toggling scheduled report: {e}", exc_info=True)
            raise

    def _calculate_next_run(self, freq: str, base_date: Optional[date] = None) -> date:
        """Calculate the next scheduled run date based on frequency."""
        if base_date is None:
            base_date = datetime.utcnow().date()
        
        freq_lower = freq.lower()
        
        if freq_lower == "weekly":
            # Next run is exactly 7 days from base_date
            return base_date + timedelta(days=7)
            
        elif freq_lower == "monthly":
            # Next run is the 1st of next month
            if base_date.day == 1:
                # Add 1 month
                if base_date.month == 12:
                    return base_date.replace(year=base_date.year + 1, month=1, day=1)
                else:
                    return base_date.replace(month=base_date.month + 1, day=1)
            else:
                # Go to 1st of next month
                if base_date.month == 12:
                    return base_date.replace(year=base_date.year + 1, month=1, day=1)
                else:
                    return base_date.replace(month=base_date.month + 1, day=1)
            
        elif freq_lower == "quarterly":
            # Next run is the 1st of month, 3 months from now
            month = base_date.month + 3
            year = base_date.year
            if month > 12:
                month -= 12
                year += 1
            return base_date.replace(year=year, month=month, day=1)
        
        # Default: add 7 days
        return base_date + timedelta(days=7)

    async def run_scheduled_reports(self):
        """Run all scheduled reports that are due"""
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
                
                # Normalize report type
                raw_type = (report.get("report_type") or "").strip().lower()
                REPORT_TYPE_MAP = {
                    "booking": "booking",
                    "booking summary": "booking",
                    "booking-summary": "booking",
                    "occupancy": "occupancy",
                    "occupancy report": "occupancy",
                    "owner": "owner",
                    "owner statement": "owner",
                    "owner-statement": "owner",
                    "service revenue": "service_revenue",
                    "service-revenue": "service_revenue",
                    "service provider": "service_provider",
                    "service-provider": "service_provider",
                    "performance": "performance",
                    "performance comparison": "performance",
                    "performance-comparison": "performance",
                }
                
                report_type = REPORT_TYPE_MAP.get(raw_type)
                if not report_type:
                    self.logger.warning(f"Unknown report type: {raw_type}")
                    continue
                
                # Parse filters
                filters = report.get("filters", {})
                if isinstance(filters, str):
                    filters = json.loads(filters)
                
                recipients = report.get("recipients", [])
                if isinstance(recipients, str):
                    recipients = json.loads(recipients)
                
                # Get reference date for period calculation
                ref_date = report.get("next_run")
                if isinstance(ref_date, str):
                    ref_date = datetime.strptime(ref_date, "%Y-%m-%d").date()
                elif isinstance(ref_date, datetime):
                    ref_date = ref_date.date()
                else:
                    ref_date = datetime.now().date()
                
                freq = report.get("frequency", "").lower()
                from_date = None
                to_date = None
                
                # Calculate date range based on frequency
                if freq == "weekly":
                    # Previous 7 days: ref_date-7 to ref_date-1
                    last_start = ref_date - timedelta(days=7)
                    last_end = ref_date - timedelta(days=1)
                    from_date = last_start.strftime("%Y-%m-%d")
                    to_date = last_end.strftime("%Y-%m-%d")
                    self.logger.info(f"Weekly report: period {from_date} to {to_date}")
                    
                elif freq == "monthly":
                    # Previous month: 1st to last day of previous month
                    first_of_this_month = ref_date.replace(day=1)
                    last_day_of_prev_month = first_of_this_month - timedelta(days=1)
                    first_day_of_prev_month = last_day_of_prev_month.replace(day=1)
                    from_date = first_day_of_prev_month.strftime("%Y-%m-%d")
                    to_date = last_day_of_prev_month.strftime("%Y-%m-%d")
                    self.logger.info(f"Monthly report: period {from_date} to {to_date}")
                    
                elif freq == "quarterly":
                    # Previous 3 months (quarter)
                    first_of_this_month = ref_date.replace(day=1)
                    last_day_of_prev_month = first_of_this_month - timedelta(days=1)
                    # Go back 3 months
                    quarter_end = last_day_of_prev_month
                    quarter_start = quarter_end.replace(day=1)
                    # Subtract 2 more months to get 3 months total
                    for _ in range(2):
                        if quarter_start.month == 1:
                            quarter_start = quarter_start.replace(year=quarter_start.year - 1, month=12, day=1)
                        else:
                            quarter_start = quarter_start.replace(month=quarter_start.month - 1, day=1)
                    from_date = quarter_start.strftime("%Y-%m-%d")
                    to_date = quarter_end.strftime("%Y-%m-%d")
                    self.logger.info(f"Quarterly report: period {from_date} to {to_date}")
                    
                else:
                    # Fallback to filters from the schedule
                    from_date = filters.get("from")
                    to_date = filters.get("to")
                    self.logger.info(f"Custom frequency report: period {from_date} to {to_date}")
                
                # Skip if dates are missing
                if not from_date or not to_date:
                    self.logger.warning(f"Missing dates for report: {report_type}")
                    continue

                data = None
                title = ""

                # Generate report based on type
                if report_type == "booking":
                    property_ids = filters.get("property_ids")
                    data = await self.get_booking_summary(from_date, to_date, property_ids)
                    title = "Booking Summary Report"
                elif report_type == "occupancy":
                    property_ids = filters.get("property_ids")
                    data = await self.get_occupancy_report(from_date, to_date, property_ids)
                    title = "Occupancy Report"
                elif report_type == "owner":
                    owner_ids = filters.get("owner_ids")
                    property_ids = filters.get("property_ids")
                    data = await self.get_owner_statement(from_date, to_date, property_ids, owner_ids)
                    title = "Owner Statement Report"
                elif report_type == "service_revenue":
                    property_ids = filters.get("property_ids")
                    data = await self.get_service_revenue(from_date, to_date, property_ids)
                    title = "Service Revenue Report"
                elif report_type == "service_provider":
                    provider_id = filters.get("provider_id")
                    data = await self.get_service_provider_report(from_date, to_date, provider_id)
                    title = "Service Provider Report"
                elif report_type == "performance":
                    property_ids = filters.get("property_ids")
                    data = await self.get_performance_report(from_date, to_date, property_ids)
                    title = "Performance Comparison Report"
                
                if not data:
                    self.logger.warning(f"No data generated for report: {report_type}")
                    continue
                
                # Generate PDF
                pdf_bytes = generate_pdf_report(title, data)
                
                # Generate proper filename
                clean_title = title.replace(" Report", "").replace(" Statement", "")
                filename = get_report_filename(clean_title, from_date, to_date)
                
                self.logger.info(f"Generated PDF: {filename} for report type: {title}")

                # Send Email to all recipients
                email_sent = False
                for email in recipients:
                    try:
                        send_email_with_pdf(
                            to_email=email,
                            subject=f"{title} ({from_date} to {to_date})",
                            content=build_email_html(title, from_date, to_date),
                            pdf_bytes=pdf_bytes,
                            filename=filename
                        )
                        self.logger.info(f"Email sent to {email} with attachment: {filename}")
                        email_sent = True
                    except Exception as email_error:
                        self.logger.error(f"Email failed for {email}: {email_error}")
                        continue

                if not email_sent:
                    self.logger.warning(f"No emails were sent for report ID: {report.get('id')}")

                # Calculate next run date
                current_scheduled = report.get("next_run")
                if isinstance(current_scheduled, str):
                    current_scheduled = datetime.strptime(current_scheduled, "%Y-%m-%d").date()
                elif isinstance(current_scheduled, datetime):
                    current_scheduled = current_scheduled.date()
                else:
                    current_scheduled = datetime.now().date()
                
                next_run = self._calculate_next_run(freq, current_scheduled)

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
            self.logger.info("Scheduled reports execution completed successfully")

        except Exception as e:
            self.logger.error(f"Error running scheduled reports: {e}", exc_info=True)
            await self.session.rollback()
            raise