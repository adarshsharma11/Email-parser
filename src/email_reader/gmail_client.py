"""
Gmail IMAP client for reading vacation rental booking emails.
"""
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
from typing import List, Optional, Union
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import email.utils

from ..utils.models import EmailData, Platform
from ..utils.logger import get_logger
from config.settings import gmail_config


class GmailClient:
    """Gmail IMAP client for reading vacation rental booking emails."""

    def __init__(self):
        self.logger = get_logger("gmail_client")
        self.connection: Optional[imaplib.IMAP4_SSL] = None
        self.connected = False
        self.auth_email: Optional[str] = None
        self.auth_password: Optional[str] = None

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
            self.auth_email = gmail_config.email
            self.auth_password = gmail_config.password

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
            self.auth_email = email_addr
            self.auth_password = password

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

    def select_mailbox(self, mailbox: str) -> bool:
        try:
            # 1. Handle special "SENT" alias
            if mailbox.upper() == "SENT":
                # Try known variations, quoting those with spaces
                candidates = ['"[Gmail]/Sent Mail"', "[Gmail]/Sent Mail", "[Gmail]/Sent", "Sent"]
                for name in candidates:
                    try:
                        status, _ = self.connection.select(name)
                        if status == "OK":
                            return True
                    except Exception:
                        continue
                return False

            # 2. Handle "INBOX" explicitly
            if mailbox.upper() == "INBOX":
                status, _ = self.connection.select("INBOX")
                return status == "OK"

            # 3. Handle arbitrary folders
            # If it has spaces and isn't quoted, quote it
            target = mailbox
            if " " in target and not target.startswith('"'):
                target = f'"{target}"'
            
            status, _ = self.connection.select(target)
            return status == "OK"

        except Exception as e:
            self.logger.error("Error selecting mailbox", mailbox=mailbox, error=str(e))
            return False
    
    def search_emails(
        self,
        platform: Optional[Platform] = None,
        since_days: Optional[int] = None,
        limit: Optional[int] = None,
        mailbox: str = "INBOX",
        text_query: Optional[str] = None,
        match_any_booking: bool = False,
    ) -> List[str]:
        if not self.connected:
            self.logger.error("Not connected to Gmail")
            return []
        
        try:
            if not self.select_mailbox(mailbox):
                return []
            criteria = []
            
            # Date filter
            if since_days:
                since_date = datetime.now() - timedelta(days=since_days)
                criteria += ["SINCE", since_date.strftime("%d-%b-%Y")]
            
            # Text query
            if text_query:
                criteria += ["TEXT", text_query]
            
            # Platform filters
            if platform:
                if platform == Platform.AIRBNB:
                    criteria += ["TEXT", "airbnb"]
                elif platform == Platform.VRBO:
                    criteria += ["OR", "TEXT", "vrbo", "TEXT", "homeaway"]
                elif platform == Platform.BOOKING:
                    criteria += ["TEXT", "booking.com"]
                elif platform == Platform.PLUMGUIDE:
                    criteria += ["TEXT", "plumguide"]
            elif match_any_booking:
                # Search for ANY of the booking platforms using recursive OR
                terms = [
                    ["TEXT", "airbnb"],
                    ["TEXT", "vrbo"],
                    ["TEXT", "homeaway"],
                    ["TEXT", "booking.com"],
                    ["TEXT", "plumguide"]
                ]
                criteria += self._build_or_chain(terms)
            else:
                # No specific platform and not restricting to booking -> ALL
                # Only add ALL if no other criteria exist, otherwise implicit AND applies
                if not criteria:
                    criteria = ["ALL"]

            # If criteria is empty (shouldn't happen due to logic above, but safe fallback)
            if not criteria:
                criteria = ["ALL"]

            self.logger.debug("Searching emails with criteria", criteria=criteria, mailbox=mailbox)
            status, email_ids = self.connection.search(None, *criteria)
            if status != "OK":
                return []
            email_id_list = email_ids[0].split()
            # Gmail returns IDs in ascending order (oldest first). 
            # We want the newest emails, so we reverse the list.
            email_id_list.reverse()
            
            if limit:
                email_id_list = email_id_list[:limit]
            return [eid.decode() for eid in email_id_list]
        except Exception as e:
            self.logger.error("Error searching emails", error=str(e))
            return []

    def fetch_email(self, email_id: str, mailbox: str = "INBOX") -> Optional[EmailData]:
        """Fetch and parse a single email."""
        if not self.connected:
            self.logger.error("Not connected to Gmail")
            return None
        
        try:
            if not self.select_mailbox(mailbox):
                self.logger.error("Failed to select mailbox", mailbox=mailbox)
                return None
            status, msg_data = self.connection.fetch(email_id, "(RFC822)")
            if status != "OK":
                # Try UID fetch as a fallback
                status_uid, msg_data_uid = self.connection.uid("fetch", email_id, "(RFC822)")
                if status_uid != "OK":
                    self.logger.error(
                        "Failed to fetch email", email_id=email_id, status=status
                    )
                    return None
                raw_email = msg_data_uid[0][1]
            else:
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
                folder=mailbox,
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
        mailbox: Union[str, List[str]] = "INBOX",
        text_query: Optional[str] = None,
        only_booking: bool = True,
    ) -> List[EmailData]:
        mailboxes = []
        if isinstance(mailbox, str):
            if mailbox.upper() == "BOTH":
                mailboxes = ["INBOX", "SENT"]
            elif "," in mailbox:
                mailboxes = [m.strip() for m in mailbox.split(",")]
            else:
                mailboxes = [mailbox]
        elif isinstance(mailbox, list):
            mailboxes = mailbox
        else:
            mailboxes = ["INBOX"]

        all_emails = []
        for box in mailboxes:
            email_ids = self.search_emails(
                platform, 
                since_days, 
                limit, 
                box, 
                text_query,
                match_any_booking=(only_booking and platform is None)
            )
            for eid in email_ids:
                email_data = self.fetch_email(eid, mailbox=box)
                if email_data:
                    all_emails.append(email_data)
        
        emails = all_emails
        
        if only_booking:
            emails = [
                e for e in emails
                if e.platform in (Platform.VRBO, Platform.AIRBNB, Platform.BOOKING, Platform.PLUMGUIDE)
            ]
        emails.sort(key=lambda e: e.date, reverse=True)
        
        if limit and len(emails) > limit:
            emails = emails[:limit]
            
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
    
    def send_email(self, to_address: str, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
        """Send an email using Gmail SMTP."""
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.auth_email or gmail_config.email
            msg["To"] = to_address
            msg["Subject"] = subject
            msg["Date"] = email.utils.formatdate(localtime=True)
            
            part1 = MIMEText(body_text or "", "plain")
            msg.attach(part1)
            if body_html:
                part2 = MIMEText(body_html, "html")
                msg.attach(part2)
            
            with smtplib.SMTP(gmail_config.smtp_server, gmail_config.smtp_port) as server:
                server.ehlo()
                server.starttls()
                login_email = self.auth_email or gmail_config.email
                login_pass = self.auth_password or gmail_config.password
                server.login(login_email, login_pass)
                server.sendmail(login_email, [to_address], msg.as_string())
            return True
        except Exception as e:
            self.logger.error("Failed to send email", error=str(e))
            return False
    
    def reply_to_email(self, original_email_id: str, to_address: str, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
        """Reply to a specific email by ID."""
        try:
            if not self.connected:
                self.logger.error("Not connected to Gmail")
                return False
            
            status, msg_data = self.connection.fetch(original_email_id, "(RFC822)")
            if status != "OK":
                self.logger.error("Failed to fetch original email", email_id=original_email_id, status=status)
                return False
            raw_email = msg_data[0][1]
            original = email.message_from_bytes(raw_email)
            
            msg = MIMEMultipart("alternative")
            msg["From"] = self.auth_email or gmail_config.email
            msg["To"] = to_address
            msg["Subject"] = subject
            msg["Date"] = email.utils.formatdate(localtime=True)
            msg["In-Reply-To"] = original.get("Message-ID", "")
            refs = original.get("References", "")
            msg["References"] = (refs + " " + original.get("Message-ID", "")).strip()
            
            part1 = MIMEText(body_text or "", "plain")
            msg.attach(part1)
            if body_html:
                part2 = MIMEText(body_html, "html")
                msg.attach(part2)
            
            with smtplib.SMTP(gmail_config.smtp_server, gmail_config.smtp_port) as server:
                server.ehlo()
                server.starttls()
                login_email = self.auth_email or gmail_config.email
                login_pass = self.auth_password or gmail_config.password
                server.login(login_email, login_pass)
                server.sendmail(login_email, [to_address], msg.as_string())
            return True
        except Exception as e:
            self.logger.error("Failed to reply to email", error=str(e))
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
