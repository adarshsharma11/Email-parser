# guest_communication/email_client.py
import smtplib
from email.mime.text import MIMEText
import os
from typing import Optional

class EmailClient:
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.username = username or os.getenv("SMTP_USER")
        self.password = password or os.getenv("SMTP_PASSWORD")

    def send(self, to: str, subject: str, body: str, html: bool = False, credentials: Optional[dict] = None):
        subtype = "html" if html else "plain"
        
        # Use provided credentials or fall back to instance defaults
        username = self.username
        password = self.password
        
        if credentials:
            username = credentials.get("username", username)
            password = credentials.get("password", password)

        msg = MIMEText(body, subtype)
        msg["Subject"] = subject
        msg["From"] = username
        msg["To"] = to

        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            server.login(username, password)
            server.sendmail(username, [to], msg.as_string())
