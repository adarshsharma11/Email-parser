"""
Booking parser for extracting structured data from vacation rental confirmation emails.
"""
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
import structlog

from ..utils.models import EmailData, BookingData, Platform, ProcessingResult
from ..utils.logger import get_logger
from config.settings import app_config


class BookingParser:
    """Parser for extracting booking information from vacation rental emails."""
    
    def __init__(self):
        self.logger = get_logger("booking_parser")
        
        # Regex patterns for different platforms
        self.patterns = {
            Platform.VRBO: {
                'reservation_id': [
                    r'Reservation ID[:\s]*([A-Z0-9\-]+)',
                    r'Confirmation[:\s]*([A-Z0-9\-]+)',
                    r'Booking[:\s]*([A-Z0-9\-]+)'
                ],
                'guest_name': [
                    r'Guest[:\s]*([A-Za-z\s]+)',
                    r'Name[:\s]*([A-Za-z\s]+)',
                    r'Contact[:\s]*([A-Za-z\s]+)'
                ],
                'guest_phone': [
                    r'Phone[:\s]*([0-9\-\+\(\)\s]+)',
                    r'Tel[:\s]*([0-9\-\+\(\)\s]+)',
                    r'Contact[:\s]*([0-9\-\+\(\)\s]+)'
                ],
                'guest_email': [
                    r'Email[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
                    r'Contact[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
                ],
                'property_id': [
                    r'Property ID[:\s]*([A-Z0-9\-]+)',
                    r'Listing[:\s]*([A-Z0-9\-]+)',
                    r'Unit[:\s]*([A-Z0-9\-]+)'
                ],
                'property_name': [
                    r'Property[:\s]*([A-Za-z0-9\s\-\.]+)',
                    r'Listing[:\s]*([A-Za-z0-9\s\-\.]+)',
                    r'Unit[:\s]*([A-Za-z0-9\s\-\.]+)'
                ],
                'number_of_guests': [
                    r'Guests[:\s]*(\d+)',
                    r'Occupancy[:\s]*(\d+)',
                    r'People[:\s]*(\d+)'
                ],
                'total_amount': [
                    r'Total[:\s]*\$?([0-9,]+\.?[0-9]*)',
                    r'Amount[:\s]*\$?([0-9,]+\.?[0-9]*)',
                    r'Price[:\s]*\$?([0-9,]+\.?[0-9]*)'
                ]
            },
            Platform.AIRBNB: {
                'reservation_id': [
                    r'Reservation[:\s]*([A-Z0-9\-]+)',
                    r'Booking[:\s]*([A-Z0-9\-]+)',
                    r'Confirmation[:\s]*([A-Z0-9\-]+)'
                ],
                'guest_name': [
                    r'Guest[:\s]*([A-Za-z\s]+)',
                    r'Name[:\s]*([A-Za-z\s]+)',
                    r'Contact[:\s]*([A-Za-z\s]+)'
                ],
                'guest_phone': [
                    r'Phone[:\s]*([0-9\-\+\(\)\s]+)',
                    r'Tel[:\s]*([0-9\-\+\(\)\s]+)',
                    r'Contact[:\s]*([0-9\-\+\(\)\s]+)'
                ],
                'guest_email': [
                    r'Email[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
                    r'Contact[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
                ],
                'property_id': [
                    r'Listing[:\s]*([A-Z0-9\-]+)',
                    r'Property[:\s]*([A-Z0-9\-]+)',
                    r'Unit[:\s]*([A-Z0-9\-]+)'
                ],
                'property_name': [
                    r'Listing[:\s]*([A-Za-z0-9\s\-\.]+)',
                    r'Property[:\s]*([A-Za-z0-9\s\-\.]+)',
                    r'Unit[:\s]*([A-Za-z0-9\s\-\.]+)'
                ],
                'number_of_guests': [
                    r'Guests[:\s]*(\d+)',
                    r'Occupancy[:\s]*(\d+)',
                    r'People[:\s]*(\d+)'
                ],
                'total_amount': [
                    r'Total[:\s]*\$?([0-9,]+\.?[0-9]*)',
                    r'Amount[:\s]*\$?([0-9,]+\.?[0-9]*)',
                    r'Price[:\s]*\$?([0-9,]+\.?[0-9]*)'
                ]
            },
            Platform.BOOKING: {
                'reservation_id': [
                    r'Reservation[:\s]*([A-Z0-9\-]+)',
                    r'Booking[:\s]*([A-Z0-9\-]+)',
                    r'Confirmation[:\s]*([A-Z0-9\-]+)'
                ],
                'guest_name': [
                    r'Guest[:\s]*([A-Za-z\s]+)',
                    r'Name[:\s]*([A-Za-z\s]+)',
                    r'Contact[:\s]*([A-Za-z\s]+)'
                ],
                'guest_phone': [
                    r'Phone[:\s]*([0-9\-\+\(\)\s]+)',
                    r'Tel[:\s]*([0-9\-\+\(\)\s]+)',
                    r'Contact[:\s]*([0-9\-\+\(\)\s]+)'
                ],
                'guest_email': [
                    r'Email[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
                    r'Contact[:\s]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
                ],
                'property_id': [
                    r'Property[:\s]*([A-Z0-9\-]+)',
                    r'Hotel[:\s]*([A-Z0-9\-]+)',
                    r'Unit[:\s]*([A-Z0-9\-]+)'
                ],
                'property_name': [
                    r'Property[:\s]*([A-Za-z0-9\s\-\.]+)',
                    r'Hotel[:\s]*([A-Za-z0-9\s\-\.]+)',
                    r'Unit[:\s]*([A-Za-z0-9\s\-\.]+)'
                ],
                'number_of_guests': [
                    r'Guests[:\s]*(\d+)',
                    r'Occupancy[:\s]*(\d+)',
                    r'People[:\s]*(\d+)'
                ],
                'total_amount': [
                    r'Total[:\s]*\$?([0-9,]+\.?[0-9]*)',
                    r'Amount[:\s]*\$?([0-9,]+\.?[0-9]*)',
                    r'Price[:\s]*\$?([0-9,]+\.?[0-9]*)'
                ]
            }
        }
    
    def parse_email(self, email_data: EmailData) -> ProcessingResult:
        """
        Parse email and extract booking information.
        
        Args:
            email_data: Email data to parse
            
        Returns:
            ProcessingResult with extracted booking data
        """
        try:
            if not email_data.platform:
                return ProcessingResult(
                    success=False,
                    error_message="Could not determine platform",
                    email_id=email_data.email_id
                )
            
            # Extract data using platform-specific patterns
            extracted_data = self._extract_data(email_data)
            
            if not extracted_data.get('reservation_id'):
                return ProcessingResult(
                    success=False,
                    error_message="Could not extract reservation ID",
                    email_id=email_data.email_id,
                    platform=email_data.platform
                )
            
            # Create booking data object
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
            
            return ProcessingResult(
                success=True,
                booking_data=booking_data,
                email_id=email_data.email_id,
                platform=email_data.platform
            )
            
        except Exception as e:
            self.logger.error("Error parsing email", 
                            email_id=email_data.email_id,
                            error=str(e))
            return ProcessingResult(
                success=False,
                error_message=str(e),
                email_id=email_data.email_id,
                platform=email_data.platform
            )
    
    def _extract_data(self, email_data: EmailData) -> Dict[str, Any]:
        """Extract data from email using regex patterns and HTML parsing."""
        extracted_data = {}
        
        # Get platform-specific patterns
        platform_patterns = self.patterns.get(email_data.platform, {})
        
        # Combine text and HTML content
        content = f"{email_data.body_text}\n{email_data.body_html}"
        
        # Extract data using regex patterns
        for field, patterns in platform_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    if value:
                        extracted_data[field] = value
                        break
        
        # Extract dates using HTML parsing
        dates = self._extract_dates(email_data.body_html)
        if dates:
            extracted_data.update(dates)
        
        # Extract additional data using HTML parsing
        html_data = self._extract_html_data(email_data.body_html)
        if html_data:
            extracted_data.update(html_data)
        
        # Clean and validate extracted data
        extracted_data = self._clean_data(extracted_data)
        
        return extracted_data
    
    def _extract_dates(self, html_content: str) -> Dict[str, Any]:
        """Extract check-in and check-out dates from HTML content."""
        dates = {}
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for date patterns in text
            date_patterns = [
                r'Check-in[:\s]*([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
                r'Check-out[:\s]*([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
                r'Arrival[:\s]*([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
                r'Departure[:\s]*([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
                r'From[:\s]*([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
                r'To[:\s]*([A-Za-z]+\s+\d{1,2},?\s+\d{4})'
            ]
            
            for pattern in date_patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                if len(matches) >= 2:
                    try:
                        check_in = self._parse_date(matches[0])
                        check_out = self._parse_date(matches[1])
                        if check_in and check_out:
                            dates['check_in_date'] = check_in
                            dates['check_out_date'] = check_out
                            break
                    except:
                        continue
            
            # Look for dates in specific HTML elements
            date_elements = soup.find_all(['span', 'div', 'td'], 
                                        text=re.compile(r'Check-in|Check-out|Arrival|Departure'))
            
            for element in date_elements:
                text = element.get_text()
                if 'check-in' in text.lower() or 'arrival' in text.lower():
                    date_match = re.search(r'([A-Za-z]+\s+\d{1,2},?\s+\d{4})', text)
                    if date_match:
                        check_in = self._parse_date(date_match.group(1))
                        if check_in:
                            dates['check_in_date'] = check_in
                
                elif 'check-out' in text.lower() or 'departure' in text.lower():
                    date_match = re.search(r'([A-Za-z]+\s+\d{1,2},?\s+\d{4})', text)
                    if date_match:
                        check_out = self._parse_date(date_match.group(1))
                        if check_out:
                            dates['check_out_date'] = check_out
        
        except Exception as e:
            self.logger.debug("Error extracting dates from HTML", error=str(e))
        
        return dates
    
    def _extract_html_data(self, html_content: str) -> Dict[str, Any]:
        """Extract additional data from HTML structure."""
        html_data = {}
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for data in table cells
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
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
                        elif 'property' in key and 'name' in key:
                            html_data['property_name'] = value
                        elif 'guests' in key or 'occupancy' in key:
                            try:
                                html_data['number_of_guests'] = int(value)
                            except:
                                pass
                        elif 'total' in key and 'amount' in key:
                            try:
                                # Remove currency symbols and commas
                                clean_value = re.sub(r'[^\d.]', '', value)
                                html_data['total_amount'] = float(clean_value)
                            except:
                                pass
            
            # Look for data in specific HTML attributes
            meta_tags = soup.find_all('meta')
            for meta in meta_tags:
                name = meta.get('name', '').lower()
                content = meta.get('content', '')
                
                if 'reservation' in name and 'id' in name:
                    html_data['reservation_id'] = content
                elif 'guest' in name and 'name' in name:
                    html_data['guest_name'] = content
        
        except Exception as e:
            self.logger.debug("Error extracting HTML data", error=str(e))
        
        return html_data
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string using multiple formats."""
        date_str = date_str.strip()
        
        # Common date formats
        date_formats = [
            '%B %d, %Y',    # January 15, 2024
            '%B %d %Y',     # January 15 2024
            '%b %d, %Y',    # Jan 15, 2024
            '%b %d %Y',     # Jan 15 2024
            '%m/%d/%Y',     # 01/15/2024
            '%Y-%m-%d',     # 2024-01-15
            '%d/%m/%Y',     # 15/01/2024
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        return None
    
    def _clean_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and validate extracted data."""
        cleaned_data = {}
        
        for key, value in data.items():
            if isinstance(value, str):
                # Remove extra whitespace
                value = re.sub(r'\s+', ' ', value).strip()
                
                # Clean phone numbers
                if key == 'guest_phone':
                    value = re.sub(r'[^\d\-\+\(\)\s]', '', value)
                
                # Clean amounts
                elif key == 'total_amount':
                    try:
                        value = float(re.sub(r'[^\d.]', '', value))
                    except:
                        value = None
                
                # Clean guest count
                elif key == 'number_of_guests':
                    try:
                        value = int(re.sub(r'[^\d]', '', value))
                    except:
                        value = None
            
            if value:  # Only keep non-empty values
                cleaned_data[key] = value
        
        return cleaned_data
