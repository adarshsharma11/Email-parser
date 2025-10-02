# guest_communication/email_client.py
import smtplib
from email.mime.text import MIMEText
import os

class EmailClient:
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.username = os.getenv("SMTP_USER")
        self.password = os.getenv("SMTP_PASSWORD")

    def send(self, to: str, subject: str, body: str):
        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"] = self.username
        msg["To"] = to

        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            server.login(self.username, self.password)
            server.sendmail(self.username, [to], msg.as_string())
