
import os
import ssl
from typing import Optional, List, Union
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from ..utils.logger import get_logger

class SendGridClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SENDGRID_API_KEY")
        self.from_email = os.getenv("SENDGRID_FROM_EMAIL", "notifications@yourdomain.com")
        self.from_name = os.getenv("SENDGRID_FROM_NAME", "Vacation Rental Notifications")
        self.logger = get_logger("sendgrid_client")
        
        if not self.api_key:
            self.logger.error("SENDGRID_API_KEY not found in environment")
            
    def send(self, to: Union[str, List[str]], subject: str, body: str, html: bool = True) -> bool:
        if not self.api_key:
            self.logger.error("Cannot send email: SENDGRID_API_KEY is missing")
            return False
            
        try:
            sg = SendGridAPIClient(self.api_key)
            from_email = Email(self.from_email, self.from_name)
            
            if isinstance(to, str):
                to_emails = To(to)
            else:
                to_emails = [To(email) for email in to]
                
            content_type = "text/html" if html else "text/plain"
            content = Content(content_type, body)
            
            mail = Mail(from_email, to_emails, subject, content)
            
            # Use the requests library if it's available, otherwise fallback to default
            # Some environments have SSL issues with the default urllib client
            try:
                import requests
                import json
                
                headers = {
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'
                }
                
                response = requests.post(
                    'https://api.sendgrid.com/v3/mail/send',
                    headers=headers,
                    data=json.dumps(mail.get()),
                    verify=False # Disable SSL verification for this specific call
                )
                
                if response.status_code >= 200 and response.status_code < 300:
                    self.logger.info(f"Email sent successfully to {to}", status_code=response.status_code)
                    return True
                else:
                    self.logger.error(f"Failed to send email to {to}", status_code=response.status_code, body=response.text)
                    return False
            except ImportError:
                # Fallback to SendGrid's default client if requests is not installed
                response = sg.client.mail.send.post(request_body=mail.get())
                
                if response.status_code >= 200 and response.status_code < 300:
                    self.logger.info(f"Email sent successfully to {to}", status_code=response.status_code)
                    return True
                else:
                    self.logger.error(f"Failed to send email to {to}", status_code=response.status_code, body=response.body)
                    return False
                
        except Exception as e:
            self.logger.error(f"Error sending SendGrid email: {str(e)}", to=to, subject=subject)
            return False
