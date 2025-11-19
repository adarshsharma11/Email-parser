# guest_communication/sms_client.py
from twilio.rest import Client
import os
from config.settings import api_config
from ..utils.logger import get_logger

class SMSClient:
    def __init__(self):
        self.logger = get_logger("sms_client")
        is_local = ("localhost" in (api_config.base_url or "")) or ("127.0.0.1" in (api_config.base_url or ""))
        sid = (
            os.getenv("TWILIO_DEV_SID") if is_local else os.getenv("TWILIO_PROD_SID")
        ) or os.getenv("TWILIO_SID")
        token = (
            os.getenv("TWILIO_DEV_AUTH_TOKEN") if is_local else os.getenv("TWILIO_PROD_AUTH_TOKEN")
        ) or os.getenv("TWILIO_AUTH_TOKEN")
        from_number = (
            os.getenv("TWILIO_DEV_PHONE_NUMBER") if is_local else os.getenv("TWILIO_PROD_PHONE_NUMBER")
        ) or os.getenv("TWILIO_PHONE_NUMBER")
        whatsapp_from = (
            os.getenv("TWILIO_DEV_WHATSAPP_NUMBER") if is_local else os.getenv("TWILIO_PROD_WHATSAPP_NUMBER")
        ) or os.getenv("TWILIO_WHATSAPP_NUMBER") or from_number

        self.client = Client(sid, token)
        self.from_number = from_number
        self.whatsapp_from_number = whatsapp_from
        self.sid = sid
        self.is_local = is_local

    def send(self, to: str, body: str):
        try:
            msg = self.client.messages.create(
                body=body,
                from_=self.from_number,
                to=to
            )
            self.logger.info("twilio_sms_sent", sid=getattr(msg, "sid", None), status=getattr(msg, "status", None), to=to)
            return msg.sid
        except Exception as e:
            self.logger.error("twilio_sms_failed", error=str(e), to=to, from_number=self.from_number)
            raise

    def send_whatsapp(self, to: str, body: str):
        try:
            msg = self.client.messages.create(
                body=body,
                from_=f"whatsapp:{self.whatsapp_from_number}",
                to=f"whatsapp:{to}"
            )
            self.logger.info("twilio_whatsapp_sent", sid=getattr(msg, "sid", None), status=getattr(msg, "status", None), to=to)
            return msg.sid
        except Exception as e:
            self.logger.error("twilio_whatsapp_failed", error=str(e), to=to, from_number=self.whatsapp_from_number)
            raise
