"""
Gmail IMAP client for reading vacation rental booking emails.
"""
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import structlog
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from ..utils.models import EmailData, Platform
from ..utils.logger import get_logger
from config.settings import gmail_config


class GmailClient:
    """Gmail IMAP client for reading vacation rental booking emails."""
    
    def __init__(self):
        self.logger = get_logger("gmail_client")
        self.connection: Optional[imaplib.IMAP4_SSL] = None
        self.connected = False
    
    def connect(self) -> bool:
        """
        Connect to Gmail IMAP server.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.logger.info("Connecting to Gmail IMAP server", 
                           server=gmail_config.imap_server, 
                           port=gmail_config.imap_port)
            
            self.connection = imaplib.IMAP4_SSL(
                gmail_config.imap_server, 
                gmail_config.imap_port
            )
            
            # Login
            self.connection.login(gmail_config.email, gmail_config.password)
            self.connected = True
            
            self.logger.info("Successfully connected to Gmail")
            return True
            
        except Exception as e:
            self.logger.error("Failed to connect to Gmail", error=str(e))
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from Gmail IMAP server."""
        if self.connection and self.connected:
            try:
                self.connection.logout()
                self.connected = False
                self.logger.info("Disconnected from Gmail")
            except Exception as e:
                self.logger.error("Error disconnecting from Gmail", error=str(e))
    
    def search_emails(
        self, 
        platform: Optional[Platform] = None,
        since_days: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[str]:
        """
        Search for emails from vacation rental platforms.
        
        Args:
            platform: Specific platform to search for
            since_days: Number of days to look back
            limit: Maximum number of emails to return
            
        Returns:
            List of email IDs
        """
        if not self.connected:
            self.logger.error("Not connected to Gmail")
            return []
        
        try:
            # Select INBOX
            self.connection.select('INBOX')
            
            # Build search criteria
            search_criteria = ['UNSEEN']  # Only unread emails
            
            # Add date filter if specified
            if since_days:
                since_date = datetime.now() - timedelta(days=since_days)
                search_criteria.append(f'SINCE {since_date.strftime("%d-%b-%Y")}')
            
            # Add platform-specific search
            if platform:
                search_pattern = gmail_config.search_patterns.get(platform.value, "")
                if search_pattern:
                    search_criteria.append(search_pattern)
            else:
                # Search for all supported platforms
                all_patterns = []
                for pattern in gmail_config.search_patterns.values():
                    all_patterns.append(f"({pattern})")
                search_criteria.append(f"({' OR '.join(all_patterns)})")
            
            search_string = ' '.join(search_criteria)
            self.logger.info("Searching emails", criteria=search_string)
            
            # Execute search
            status, email_ids = self.connection.search(None, search_string)
            
            if status != 'OK':
                self.logger.error("Failed to search emails", status=status)
                return []
            
            # Convert to list and limit results
            email_id_list = email_ids[0].split()
            
            if limit:
                email_id_list = email_id_list[:limit]
            
            self.logger.info("Found emails", count=len(email_id_list))
            return [email_id.decode() for email_id in email_id_list]
            
        except Exception as e:
            self.logger.error("Error searching emails", error=str(e))
            return []
    
    def fetch_email(self, email_id: str) -> Optional[EmailData]:
        """
        Fetch and parse a single email.
        
        Args:
            email_id: Email ID to fetch
            
        Returns:
            EmailData object or None if failed
        """
        if not self.connected:
            self.logger.error("Not connected to Gmail")
            return None
        
        try:
            # Fetch email
            status, msg_data = self.connection.fetch(email_id, '(RFC822)')
            
            if status != 'OK':
                self.logger.error("Failed to fetch email", email_id=email_id, status=status)
                return None
            
            # Parse email
            raw_email = msg_data[0][1]
            email_message = email.message_from_bytes(raw_email)
            
            # Extract basic information
            subject = self._decode_header(email_message['subject'])
            sender = self._decode_header(email_message['from'])
            date_str = email_message['date']
            
            # Parse date
            try:
                date = email.utils.parsedate_to_datetime(date_str)
            except:
                date = datetime.now()
            
            # Extract body
            body_text, body_html = self._extract_body(email_message)
            
            # Determine platform
            platform = self._detect_platform(sender, subject)
            
            email_data = EmailData(
                email_id=email_id,
                subject=subject,
                sender=sender,
                date=date,
                body_text=body_text,
                body_html=body_html,
                platform=platform
            )
            
            self.logger.debug("Email fetched successfully", 
                            email_id=email_id, 
                            platform=platform.value if platform else None)
            
            return email_data
            
        except Exception as e:
            self.logger.error("Error fetching email", email_id=email_id, error=str(e))
            return None
    
    def fetch_emails(
        self, 
        platform: Optional[Platform] = None,
        since_days: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[EmailData]:
        """
        Fetch multiple emails from vacation rental platforms.
        
        Args:
            platform: Specific platform to search for
            since_days: Number of days to look back
            limit: Maximum number of emails to return
            
        Returns:
            List of EmailData objects
        """
        email_ids = self.search_emails(platform, since_days, limit)
        emails = []
        
        for email_id in email_ids:
            email_data = self.fetch_email(email_id)
            if email_data:
                emails.append(email_data)
        
        self.logger.info("Fetched emails", count=len(emails))
        return emails
    
    def mark_as_read(self, email_id: str) -> bool:
        """
        Mark an email as read.
        
        Args:
            email_id: Email ID to mark as read
            
        Returns:
            True if successful, False otherwise
        """
        if not self.connected:
            return False
        
        try:
            self.connection.store(email_id, '+FLAGS', '\\Seen')
            self.logger.debug("Marked email as read", email_id=email_id)
            return True
        except Exception as e:
            self.logger.error("Error marking email as read", email_id=email_id, error=str(e))
            return False
    
    def _decode_header(self, header: str) -> str:
        """Decode email header."""
        if not header:
            return ""
        
        try:
            decoded_parts = decode_header(header)
            decoded_string = ""
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    if encoding:
                        decoded_string += part.decode(encoding)
                    else:
                        decoded_string += part.decode('utf-8', errors='ignore')
                else:
                    decoded_string += str(part)
            return decoded_string
        except:
            return str(header)
    
    def _extract_body(self, email_message) -> tuple[str, str]:
        """Extract text and HTML body from email."""
        body_text = ""
        body_html = ""
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                # Skip attachments
                if "attachment" in content_disposition:
                    continue
                
                try:
                    body = part.get_payload(decode=True).decode()
                except:
                    continue
                
                if content_type == "text/plain":
                    body_text += body
                elif content_type == "text/html":
                    body_html += body
        else:
            # Not multipart
            content_type = email_message.get_content_type()
            try:
                body = email_message.get_payload(decode=True).decode()
            except:
                body = ""
            
            if content_type == "text/plain":
                body_text = body
            elif content_type == "text/html":
                body_html = body
            else:
                body_text = body
        
        return body_text, body_html
    
    def _detect_platform(self, sender: str, subject: str) -> Optional[Platform]:
        """Detect platform from sender and subject."""
        sender_lower = sender.lower()
        subject_lower = subject.lower()
        
        # VRBO/HomeAway
        if any(domain in sender_lower for domain in ['vrbo.com', 'homeaway.com']):
            return Platform.VRBO
        
        # Airbnb
        if any(domain in sender_lower for domain in ['airbnb.com', 'airbnb.co.uk']):
            return Platform.AIRBNB
        
        # Booking.com
        if any(domain in sender_lower for domain in ['booking.com', 'booking.co.uk']):
            return Platform.BOOKING
        
        # Fallback: check subject line
        if any(keyword in subject_lower for keyword in ['vrbo', 'homeaway']):
            return Platform.VRBO
        elif any(keyword in subject_lower for keyword in ['airbnb']):
            return Platform.AIRBNB
        elif any(keyword in subject_lower for keyword in ['booking.com']):
            return Platform.BOOKING
        
        return None
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
