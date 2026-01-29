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
        
        # ---- STATUS DETECTION (e.g., cancellations) ----
        try:
            cancel_pattern = r'\b(cancelled|canceled|cancellation|booking\s+canceled)\b'
            if re.search(cancel_pattern, subject, re.IGNORECASE) or re.search(cancel_pattern, content, re.IGNORECASE):
                extracted_data['status'] = 'cancelled'
        except Exception:
            pass
        
        # ---- BOOKING TYPE ----
        try:
            subj_lower = subject.lower()
            if "inquiry" in subj_lower:
                extracted_data["booking_type"] = "inquiry"
            elif any(k in subj_lower for k in ["reservation", "booking", "confirmed", "confirmation", "itinerary", "trip details"]):
                extracted_data["booking_type"] = "booking"
            else:
                extracted_data["booking_type"] = "other"
        except Exception:
            extracted_data["booking_type"] = "other"
        
        # ---- EXTRA MESSAGE ----
        try:
            msg = (email_data.body_text or "").strip()
            if msg:
                extracted_data["extra_message"] = msg
        except Exception:
            pass

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
            match = re.search(r'Reservation\s+(?!for\b)([A-Z0-9\-]+)', subject)
            if match:
                extracted_data['reservation_id'] = match.group(1)

            if extracted_data.get("booking_type") == "booking":
                m_at = re.search(r'at\s+(.+?)(?:\s+(?:from|—|-|–)|,|$)', subject)
                if m_at:
                    extracted_data['property_name'] = m_at.group(1).strip()
                else:
                    m_for = re.search(r'Reservation\s+for\s+(.+?)(?:\s+(?:from|—|-|–)|,|$)', subject, re.IGNORECASE)
                    if m_for:
                        extracted_data['property_name'] = m_for.group(1).strip()

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
        # ---- GUEST NAME FALLBACKS ----
        if 'guest_name' not in extracted_data:
            try:
                m_guest = re.search(r'\bGuest(?!s)\s*[:\-]?\s*([A-Za-z][A-Za-z\s\'\-]{1,60})', content, re.IGNORECASE)
                if m_guest:
                    name = m_guest.group(1).strip()
                    name = re.split(r'\b(Check-?in|Check-?out|Phone|Email|GUESTS|Guests|Adults|Children)\b', name, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                    if len(name) >= 2:
                        extracted_data['guest_name'] = name
                if 'guest_name' not in extracted_data:
                    m_traveler = re.search(r'\bTraveler\s*[:\-]?\s*([A-Za-z][A-Za-z\s\'\-]{1,60})', content, re.IGNORECASE)
                    if m_traveler:
                        name = m_traveler.group(1).strip()
                        name = re.split(r'\b(Check-?in|Check-?out|Phone|Email|GUESTS|Guests|Adults|Children)\b', name, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                        if len(name) >= 2:
                            extracted_data['guest_name'] = name
                if 'guest_name' not in extracted_data:
                    m_booker = re.search(r'\b([A-Z][A-Za-z\'\-]{2,})\s+Booker\b', content)
                    if m_booker:
                        extracted_data['guest_name'] = m_booker.group(1).strip()
            except Exception:
                pass

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
            date_word = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?'
            d1 = rf'{date_word}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,\s*\d{{4}}|\s+\d{{4}})?'
            d2 = r'\d{1,2}\s+' + date_word + r'(?:,\s*\d{4}|\s+\d{4})'
            d3 = r'\d{4}[-/]\d{2}[-/]\d{2}'
            d4 = r'\d{1,2}/\d{1,2}/\d{4}'
            dp = rf'(?:{d1}|{d2}|{d3}|{d4})'
            ci_sel = None
            co_sel = None
            m_from_to = re.search(rf'(?:from|between)\s*({dp}).*?(?:to|until|–|-|—)\s*({dp})', text, re.IGNORECASE | re.DOTALL)
            if m_from_to:
                ci = self._parse_date(m_from_to.group(1))
                co = self._parse_date(m_from_to.group(2))
                if ci and co and co > ci:
                    ci_sel, co_sel = ci, co
            if ci_sel is None or co_sel is None:
                m_ci = re.search(rf'(check[\s-]?in|arrival|start\s+date)\s*[:\-]?\s*({dp})', text, re.IGNORECASE)
                m_co = re.search(rf'(check[\s-]?out|departure|end\s+date)\s*[:\-]?\s*({dp})', text, re.IGNORECASE)
                if m_ci and m_co:
                    ci = self._parse_date(m_ci.group(2))
                    co = self._parse_date(m_co.group(2))
                    if ci and co and co > ci:
                        ci_sel, co_sel = ci, co
            if ci_sel is None or co_sel is None:
                candidates = []
                for m in re.finditer(dp, text, re.IGNORECASE):
                    ds = m.group(0)
                    dt = self._parse_date(ds)
                    if dt:
                        candidates.append((m.start(), ds, dt))
                candidates.sort(key=lambda x: x[0])
                for i in range(len(candidates) - 1):
                    ci_dt = candidates[i][2]
                    co_dt = candidates[i + 1][2]
                    if co_dt > ci_dt:
                        ci_sel, co_sel = ci_dt, co_dt
                        break
            if ci_sel and co_sel:
                time_matches = re.findall(r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))', text)
                if len(time_matches) >= 2:
                    try:
                        t_ci = datetime.strptime(time_matches[0].upper().replace(' ', ''), "%I:%M%p").time()
                        t_co = datetime.strptime(time_matches[1].upper().replace(' ', ''), "%I:%M%p").time()
                        ci_sel = datetime(ci_sel.year, ci_sel.month, ci_sel.day, t_ci.hour, t_ci.minute)
                        co_sel = datetime(co_sel.year, co_sel.month, co_sel.day, t_co.hour, t_co.minute)
                    except Exception:
                        pass
                dates['check_in_date'] = ci_sel
                dates['check_out_date'] = co_sel
        except Exception as e:
            self.logger.debug("Date extraction error", error=str(e))
        return dates

    def _extract_html_data(self, html_content: str) -> Dict[str, Any]:
        """Parse structured table/meta data in HTML."""
        html_data: Dict[str, Any] = {}
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
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
                        date_word = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
                        if re.search(rf'\b{date_word}\b', t, re.IGNORECASE) or re.search(r'\d{1,2}\s*(?:–|-|—)\s*\d{1,2}', t):
                            continue
                        if ' Home - ' in t:
                            t = t.split(' Home - ', 1)[0].strip()
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
        s = date_str.strip()
        s = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', s)
        s = re.sub(r'\bSept\b', 'Sep', s)
        s = re.sub(r'\s*,\s*', ', ', s)
        s = re.sub(r'\.\b', '', s)
        date_formats = [
            "%B %d, %Y",
            "%b %d, %Y",
            "%B %d %Y",
            "%b %d %Y",
            "%d %B %Y",
            "%d %b %Y",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%Y-%m-%d",
            "%Y/%m/%d"
        ]
        for fmt in date_formats:
            try:
                return datetime.strptime(s, fmt)
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
                elif key == 'property_name':
                    month = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
                    if ',' in value:
                        parts = [p.strip() for p in value.split(',')]
                        tail = ','.join(parts[1:])
                        if re.search(rf'\b{month}\b', tail, re.IGNORECASE) or re.search(r'\d{1,2}\s*(?:–|-|—)\s*\d{1,2}', tail):
                            value = parts[0]
            cleaned[key] = value
        return cleaned
