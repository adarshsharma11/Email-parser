"""
Gmail IMAP client for reading vacation rental booking emails.
"""
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
from typing import List, Optional
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
        """Connect to Gmail IMAP server."""
        try:
            self.logger.info(
                "Connecting to Gmail IMAP server",
                server=gmail_config.imap_server,
                port=gmail_config.imap_port,
            )

            self.connection = imaplib.IMAP4_SSL(
                gmail_config.imap_server,
                gmail_config.imap_port,
            )
            self.connection.login(gmail_config.email, gmail_config.password)
            self.connected = True

            self.logger.info("Successfully connected to Gmail")
            return True
        except Exception as e:
            self.logger.error("Failed to connect to Gmail", error=str(e))
            self.connected = False
            return False

    def connect_with_credentials(self, email_addr: str, password: str) -> bool:
        """Connect to Gmail using provided credentials instead of .env."""
        try:
            self.logger.info(
                "Connecting to Gmail IMAP server with provided credentials",
                server=gmail_config.imap_server,
                port=gmail_config.imap_port,
            )

            self.connection = imaplib.IMAP4_SSL(
                gmail_config.imap_server,
                gmail_config.imap_port,
            )
            self.connection.login(email_addr, password)
            self.connected = True

            self.logger.info("Successfully connected to Gmail (provided credentials)")
            return True
        except Exception as e:
            self.logger.error("Failed to connect to Gmail with provided credentials", error=str(e))
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

    def _build_or_chain(self, terms: List[List[str]]) -> List[str]:
        """
        Build nested OR query for Gmail IMAP.
        Example: [["TEXT", "airbnb"], ["TEXT", "vrbo"], ["TEXT", "plumguide"]]
        => ["OR", "TEXT", "airbnb", "OR", "TEXT", "vrbo", "TEXT", "plumguide"]
        """
        if not terms:
            return []

        if len(terms) == 1:
            return terms[0]

        # Nest OR recursively
        query = ["OR"] + terms[0] + self._build_or_chain(terms[1:])
        return query

    def search_emails(
        self,
        platform: Optional[Platform] = None,
        since_days: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[str]:
        """Search for emails matching given criteria."""
        if not self.connected:
            self.logger.error("Not connected to Gmail")
            return []

        try:
            self.connection.select("INBOX")
            criteria = ["ALL"]

            # Date filter
            if since_days:
                since_date = datetime.now() - timedelta(days=since_days)
                criteria += ["SINCE", since_date.strftime("%d-%b-%Y")]

            # Platform-specific matching (using TEXT for robustness with forwarded mails)
            if platform:
                if platform == Platform.AIRBNB:
                    criteria += ["TEXT", "airbnb"]
                elif platform == Platform.VRBO:
                    criteria += ["TEXT", "vrbo"]
                elif platform == Platform.BOOKING:
                    criteria += ["TEXT", "booking.com"]
                elif platform == Platform.PLUMGUIDE:
                    criteria += ["TEXT", "plumguide"]
            else:
                # Multi-platform: Airbnb + Vrbo + HomeAway + PlumGuide + Booking
                patterns = [
                    ["TEXT", "airbnb"],
                    ["TEXT", "vrbo"],
                    ["TEXT", "homeaway"],
                    ["TEXT", "plumguide"],
                    ["TEXT", "booking.com"],
                ]
                criteria += self._build_or_chain(patterns)

            self.logger.info("Searching emails", criteria=criteria)

            status, email_ids = self.connection.search(None, *criteria)

            if status != "OK":
                self.logger.error("Failed to search emails", status=status)
                return []

            email_id_list = email_ids[0].split()
            if limit:
                email_id_list = email_id_list[:limit]

            self.logger.info("Found emails", count=len(email_id_list))
            return [eid.decode() for eid in email_id_list]

        except Exception as e:
            self.logger.error("Error searching emails", error=str(e))
            return []

    def fetch_email(self, email_id: str) -> Optional[EmailData]:
        """Fetch and parse a single email."""
        if not self.connected:
            self.logger.error("Not connected to Gmail")
            return None

        try:
            status, msg_data = self.connection.fetch(email_id, "(RFC822)")
            if status != "OK":
                self.logger.error(
                    "Failed to fetch email", email_id=email_id, status=status
                )
                return None

            raw_email = msg_data[0][1]
            email_message = email.message_from_bytes(raw_email)

            subject = self._decode_header(email_message["subject"])
            sender = self._decode_header(email_message["from"])
            date_str = email_message["date"]

            try:
                date = email.utils.parsedate_to_datetime(date_str)
            except Exception:
                date = datetime.now()

            body_text, body_html = self._extract_body(email_message)
            platform = self._detect_platform(sender, subject)

            email_data = EmailData(
                email_id=email_id,
                subject=subject,
                sender=sender,
                date=date,
                body_text=body_text,
                body_html=body_html,
                platform=platform,
            )

            self.logger.debug(
                "Email fetched successfully",
                email_id=email_id,
                platform=platform.value if platform else None,
            )
            return email_data

        except Exception as e:
            self.logger.error("Error fetching email", email_id=email_id, error=str(e))
            return None

    def fetch_emails(
        self,
        platform: Optional[Platform] = None,
        since_days: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[EmailData]:
        """Fetch multiple emails from vacation rental platforms."""
        email_ids = self.search_emails(platform, since_days, limit)
        emails = []

        for eid in email_ids:
            email_data = self.fetch_email(eid)
            if email_data:
                emails.append(email_data)

        self.logger.info("Fetched emails", count=len(emails))
        return emails

    def mark_as_read(self, email_id: str) -> bool:
        """Mark an email as read."""
        if not self.connected:
            return False

        try:
            self.connection.store(email_id, "+FLAGS", "\\Seen")
            self.logger.debug("Marked email as read", email_id=email_id)
            return True
        except Exception as e:
            self.logger.error(
                "Error marking email as read", email_id=email_id, error=str(e)
            )
            return False

    def _decode_header(self, header: str) -> str:
        """Decode email header safely."""
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
                        decoded_string += part.decode("utf-8", errors="ignore")
                else:
                    decoded_string += str(part)
            return decoded_string
        except Exception:
            return str(header)

    def _extract_body(self, email_message) -> tuple[str, str]:
        """Extract text and HTML body from email."""
        body_text = ""
        body_html = ""

        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if "attachment" in content_disposition:
                    continue

                try:
                    body = part.get_payload(decode=True).decode()
                except Exception:
                    continue

                if content_type == "text/plain":
                    body_text += body
                elif content_type == "text/html":
                    body_html += body
        else:
            content_type = email_message.get_content_type()
            try:
                body = email_message.get_payload(decode=True).decode()
            except Exception:
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

        if any(domain in sender_lower for domain in ["vrbo.com", "homeaway.com"]):
            return Platform.VRBO
        if any(domain in sender_lower for domain in ["airbnb.com", "airbnb.co.uk"]):
            return Platform.AIRBNB
        if any(domain in sender_lower for domain in ["booking.com", "booking.co.uk"]):
            return Platform.BOOKING
        if any(domain in sender_lower for domain in ["plumguide.com", "plumguide.co.uk"]):
            return Platform.PLUMGUIDE

        if any(keyword in subject_lower for keyword in ["vrbo", "homeaway"]):
            return Platform.VRBO
        elif "airbnb" in subject_lower:
            return Platform.AIRBNB
        elif "booking.com" in subject_lower:
            return Platform.BOOKING
        elif "plumguide.com" in subject_lower:
            return Platform.PLUMGUIDE

        return None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
