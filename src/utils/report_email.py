# src/utils/report_email.py
import base64
import ssl
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from config.settings import app_config

logger = logging.getLogger(__name__)

# Handle SSL certificate verification issue (common on macOS)
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context




def send_email_with_pdf(to_email: str, subject: str, content: str, pdf_bytes: bytes = None, filename: str = None):
    try:
        # Use provided filename or default
        if not filename:
            filename = "scheduled_report.pdf"
        
        message = Mail(
            from_email=(app_config.SENDGRID_FROM_EMAIL, app_config.SENDGRID_FROM_NAME),
            to_emails=to_email,
            subject=subject,
            html_content=content
        )

        # PDF attach if provided
        if pdf_bytes:
            encoded_file = base64.b64encode(pdf_bytes).decode()

            attachment = Attachment(
                FileContent(encoded_file),
                FileName(filename),
                FileType("application/pdf"),
                Disposition("attachment")
            )

            message.attachment = attachment

        # Send email
        sg = SendGridAPIClient(app_config.SENDGRID_API_KEY)
        response = sg.send(message)

        logger.info(f" Email sent to {to_email} | Status: {response.status_code} | File: {filename}")

    except Exception as e:
        logger.error(f" SendGrid Error for {to_email}: {str(e)}")
        raise


def build_email_html(title: str, from_date: str, to_date: str):
    """Build HTML email content"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: 'Segoe UI', Arial, sans-serif; background-color:#f6f6f6; padding:20px; margin:0;">
        <div style="max-width:600px; margin:auto; background:white; padding:25px; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            
            <!-- Header -->
            <div style="border-bottom:2px solid #00BFFF; padding-bottom:15px; margin-bottom:20px;">
                <h2 style="margin-bottom:5px; color:#1a2c3e;">MOMA.HOUSE</h2>
                <p style="color:#6c757d; margin-top:0;">Premium Property Management</p>
            </div>

            <!-- Report Title -->
            <h3 style="color:#2c3e50; margin-bottom:10px;">{title}</h3>
            <p style="color:#6c757d; margin-top:0;">
                <strong>Reporting Period:</strong> {from_date} → {to_date}
            </p>

            <hr style="margin:20px 0; border:none; border-top:1px solid #e9ecef;">

            <!-- Content -->
            <p style="line-height:1.6; color:#495057;">
                This email contains your <strong>scheduled report</strong>, automatically generated 
                based on your system configuration.
            </p>

            <div style="background:#f8f9fa; padding:15px; border-radius:5px; margin:20px 0;">
                <p style="margin:0; color:#495057;">
                    📎 <strong>Attachment:</strong> The detailed report is attached as a PDF file.
                </p>
                <p style="margin:10px 0 0 0; font-size:12px; color:#6c757d;">
                    Please download the attachment to view the complete report.
                </p>
            </div>

            <p style="line-height:1.6; color:#495057;">
                If you have any questions or need assistance, feel free to contact our support team.
            </p>

            <br>

            <hr style="margin:20px 0; border:none; border-top:1px solid #e9ecef;">

            <!-- Footer -->
            <p style="font-size:12px; color:#adb5bd; margin:0;">
                MOMA.HOUSE — Premium Property Management<br>
                This is an automated email. Please do not reply.
            </p>
            <p style="font-size:10px; color:#adb5bd; margin:5px 0 0 0;">
                Generated on: {__import__('datetime').datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
            </p>

        </div>
    </body>
    </html>
    """