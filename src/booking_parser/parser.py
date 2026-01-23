"""
Booking parser for extracting structured data from vacation rental confirmation emails.
"""
import re
from datetime import datetime
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup

from ..utils.models import EmailData, BookingData, Platform, ProcessingResult
from ..utils.logger import get_logger


class BookingParser:
    """Parser for extracting booking information from vacation rental emails."""

    def __init__(self):
        self.logger = get_logger("booking_parser")

        # Regex patterns for different platforms (body/html parsing)
        self.patterns = {
            Platform.VRBO: {
                'reservation_id': [
                    r'Reservation ID[:\s]*([A-Z0-9\-]+)',
                    r'Confirmation[:\s]*([A-Z0-9\-]+)',
                    r'Booking[:\s]*([A-Z0-9\-]+)'
                ],
                'guest_name': [r'Guest[:\s]*([A-Za-z\s]+)'],
                'guest_phone': [r'Phone[:\s]*([0-9\-\+\(\)\s]+)'],
                'guest_email': [r'Email[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'],
                'property_id': [r'Property ID[:\s]*([A-Z0-9\-]+)'],
                'property_name': [r'Property[:\s]*([A-Za-z0-9\s\-\.]+)'],
                'number_of_guests': [r'Guests[:\s]*(\d+)'],
                'total_amount': [r'Total[:\s]*\$?([0-9,]+\.?[0-9]*)']
            },
            Platform.AIRBNB: {
                'reservation_id': [r'Reservation[:\s]*([A-Z0-9\-]+)'],
                'guest_name': [r'Guest[:\s]*([A-Za-z\s]+)'],
                'guest_email': [r'Email[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'],
                'number_of_guests': [r'Guests[:\s]*(\d+)'],
                'total_amount': [r'Total[:\s]*\$?([0-9,]+\.?[0-9]*)']
            },
            Platform.BOOKING: {
                'reservation_id': [r'Reservation[:\s]*([A-Z0-9\-]+)'],
                'guest_name': [r'Guest[:\s]*([A-Za-z\s]+)'],
                'guest_email': [r'Email[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'],
                'property_name': [r'Property[:\s]*([A-Za-z0-9\s\-\.]+)'],
                'number_of_guests': [r'Guests[:\s]*(\d+)'],
                'total_amount': [r'Total[:\s]*\$?([0-9,]+\.?[0-9]*)']
            },
            Platform.PLUMGUIDE: {
                'reservation_id': [r'Reservation[:\s]*([A-Z0-9\-]+)'],
                'guest_name': [r'Guest[:\s]*([A-Za-z\s]+)'],
                'guest_email': [r'Email[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'],
                'property_name': [r'Property[:\s]*([A-Za-z0-9\s\-\.]+)'],
                'number_of_guests': [r'Guests[:\s]*(\d+)'],
                'total_amount': [r'Total[:\s]*\$?([0-9,]+\.?[0-9]*)']
            },
        }

    def parse_email(self, email_data: EmailData) -> ProcessingResult:
        """Parse email and extract booking information."""
        try:
            if not email_data.platform:
                return ProcessingResult(
                    success=False,
                    error_message="Could not determine platform",
                    email_id=email_data.email_id
                )

            # Extract data (subject + body + html)
            extracted_data = self._extract_data(email_data)

            # Fallback: if reservation_id missing, use email_id to ensure booking capture
            if not extracted_data.get("reservation_id"):
                if email_data.platform == Platform.AIRBNB and extracted_data.get("booking_type") == "inquiry":
                    extracted_data["reservation_id"] = f"INQ-{email_data.email_id}"
                else:
                    extracted_data["reservation_id"] = str(email_data.email_id)

            booking_data = BookingData(
                reservation_id=extracted_data['reservation_id'],
                platform=email_data.platform,
                guest_name=extracted_data.get('guest_name', 'Unknown Guest'),
                guest_phone=extracted_data.get('guest_phone'),
                guest_email=extracted_data.get('guest_email'),
                check_in_date=extracted_data.get('check_in_date'),
                check_out_date=extracted_data.get('check_out_date'),
                property_id=extracted_data.get('property_id'),
                property_name=extracted_data.get('property_name'),
                number_of_guests=extracted_data.get('number_of_guests'),
                total_amount=extracted_data.get('total_amount'),
                currency=extracted_data.get('currency', 'USD'),
                booking_date=email_data.date,
                email_id=email_data.email_id,
                raw_data=extracted_data
            )

            self.logger.info("Successfully parsed booking",
                             reservation_id=booking_data.reservation_id,
                             platform=booking_data.platform.value,
                             guest_name=booking_data.guest_name)

            return ProcessingResult(success=True,
                                    booking_data=booking_data,
                                    email_id=email_data.email_id,
                                    platform=email_data.platform)

        except Exception as e:
            self.logger.error("Error parsing email",
                              email_id=email_data.email_id,
                              error=str(e))
            return ProcessingResult(success=False,
                                    error_message=str(e),
                                    email_id=email_data.email_id,
                                    platform=email_data.platform)

    def _extract_data(self, email_data: EmailData) -> Dict[str, Any]:
        """Extract data from subject + body + html."""
        extracted_data: Dict[str, Any] = {}
        content = f"{email_data.body_text}\n{email_data.body_html}"
        subject = email_data.subject or ""

        # ---- SUBJECT LINE EXTRACTION ----
        if email_data.platform == Platform.VRBO:
            match = re.search(r'Vrbo\s*#(\d+)', subject, re.IGNORECASE)
            if match:
                extracted_data['reservation_id'] = match.group(1)

            match = re.search(r'Booking from (.*?):', subject)
            if match:
                extracted_data['guest_name'] = match.group(1).strip()

            match = re.search(r'(\w+ \d{1,2}) - (\w+ \d{1,2}), (\d{4})', subject)
            if match:
                try:
                    ci = datetime.strptime(f"{match.group(1)}, {match.group(3)}", "%b %d, %Y")
                    co = datetime.strptime(f"{match.group(2)}, {match.group(3)}", "%b %d, %Y")
                    extracted_data['check_in_date'] = ci
                    extracted_data['check_out_date'] = co
                except Exception:
                    pass

        elif email_data.platform == Platform.AIRBNB:
            if re.search(r'\bInquiry\b', subject, re.IGNORECASE):
                extracted_data["booking_type"] = "inquiry"
            else:
                extracted_data["booking_type"] = "booking"
            match = re.search(r'Reservation\s*([A-Z0-9]+)', subject)
            if match:
                extracted_data['reservation_id'] = match.group(1)

            # match = re.search(r'for (.*?) from', subject)
            # if match:
            #     extracted_data['guest_name'] = match.group(1).strip()
            match = re.search(r'at\s+(.+?)(?:\s+(?:from|—|-)|$)', subject)
            if match:
                extracted_data['property_name'] = match.group(1).strip()

        elif email_data.platform == Platform.BOOKING:
            match = re.search(r'Booking number\s*([0-9]+)', subject)
            if match:
                extracted_data['reservation_id'] = match.group(1)

            match = re.search(r'Guest[:\s]*(.*)', subject)
            if match:
                extracted_data['guest_name'] = match.group(1).strip()

            # ---- PROTECT AIRBNB INQUIRY FIELDS FROM REGEX ----
            platform_patterns = self.patterns.get(email_data.platform, {})

            if email_data.platform == Platform.AIRBNB and extracted_data.get("booking_type") == "inquiry":
                platform_patterns = {
                    k: v for k, v in platform_patterns.items()
                    if k not in ("guest_name", "guest_email", "reservation_id")
                }
        # ---- BODY/HTML REGEX FALLBACKS ----
        platform_patterns = self.patterns.get(email_data.platform, {})
        for field, patterns in platform_patterns.items():
            if field in extracted_data:
                continue
            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    if value:
                        extracted_data[field] = value
                        break

        # ---- DATE EXTRACTION ----
        dates = self._extract_dates(email_data.body_html)
        if dates:
            extracted_data.update({k: v for k, v in dates.items() if k not in extracted_data})

        # ---- EXTRA DATA FROM HTML ----
        html_data = self._extract_html_data(email_data.body_html)
        if html_data:
            extracted_data.update({k: v for k, v in html_data.items() if k not in extracted_data})

        return self._clean_data(extracted_data)

    def _extract_dates(self, html_content: str) -> Dict[str, Any]:
        """Extract check-in/check-out from HTML text."""
        dates: Dict[str, Any] = {}
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            text = soup.get_text(" ")

            match = re.findall(r'(\w+ \d{1,2}, \d{4})', text)
            if len(match) >= 2:
                ci = self._parse_date(match[0])
                co = self._parse_date(match[1])
                if ci and co:
                    dates['check_in_date'] = ci
                    dates['check_out_date'] = co
        except Exception as e:
            self.logger.debug("Date extraction error", error=str(e))
        return dates

    def _extract_html_data(self, html_content: str) -> Dict[str, Any]:
        """Parse structured table/meta data in HTML."""
        html_data: Dict[str, Any] = {}
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            h2_tags = soup.find_all("h2")
            for h2 in h2_tags:
                name = h2.get_text(strip=True)
                if name and name.isalpha() and len(name) >= 3:
                    html_data["guest_name"] = name
                    break
            tables = soup.find_all('table')
            for table in tables:
                for row in table.find_all('tr'):
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        key = cells[0].get_text().strip().lower()
                        value = cells[1].get_text().strip()
                        if 'reservation' in key and 'id' in key:
                            html_data['reservation_id'] = value
                        elif 'guest' in key and 'name' in key:
                            html_data['guest_name'] = value
                        elif 'phone' in key:
                            html_data['guest_phone'] = value
                        elif 'email' in key:
                            html_data['guest_email'] = value
                        elif 'property' in key and 'id' in key:
                            html_data['property_id'] = value
                        elif 'property' in key:
                            html_data['property_name'] = value
                        elif 'guest' in key:
                            try:
                                html_data['number_of_guests'] = int(value)
                            except Exception:
                                pass
                        elif 'total' in key:
                            try:
                                clean_val = value.replace(",", "")
                                clean_val = re.sub(r'[^\d.]', '', clean_val)
                                html_data['total_amount'] = float(clean_val) if clean_val else None
                            except Exception:
                                pass
            if 'property_name' not in html_data:
                for h in soup.find_all(['h1', 'h2', 'h3']):
                    t = h.get_text().strip()
                    if t and len(t.split()) >= 2 and not re.search(r'(reservation|booking)', t, re.IGNORECASE):
                        html_data['property_name'] = t
                        break
            for a in soup.find_all('a', href=True):
                href = a['href']
                m_airbnb = re.search(r'airbnb\.com/rooms/(\d+)', href)
                if m_airbnb:
                    html_data['property_id'] = m_airbnb.group(1)
                    break
        except Exception as e:
            self.logger.debug("HTML extraction error", error=str(e))
        return html_data

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse common date formats."""
        date_formats = ["%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"]
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except Exception:
                continue
        return None

    def _clean_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize extracted values."""
        cleaned = {}
        for key, value in data.items():
            if isinstance(value, str):
                value = re.sub(r'\s+', ' ', value).strip()
                if key == 'guest_phone':
                    value = re.sub(r'[^\d\-\+\(\)\s]', '', value)
                elif key == 'total_amount':
                    try:
                        clean_val = value.replace(",", "")
                        clean_val = re.sub(r'[^\d.]', '', clean_val)
                        value = float(clean_val) if clean_val else None
                    except Exception:
                        value = None
                elif key == 'number_of_guests':
                    try:
                        value = int(re.sub(r'[^\d]', '', value))
                    except Exception:
                        value = None
            cleaned[key] = value
        return cleaned
