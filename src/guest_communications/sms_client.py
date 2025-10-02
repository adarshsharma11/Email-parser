# guest_communication/sms_client.py
from twilio.rest import Client
import os

class SMSClient:
    def __init__(self):
        self.client = Client(os.getenv("TWILIO_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
        self.from_number = os.getenv("TWILIO_PHONE_NUMBER")

    def send(self, to: str, body: str):
        msg = self.client.messages.create(
            body=body,
            from_=self.from_number,
            to=to
        )
        return msg.sid
