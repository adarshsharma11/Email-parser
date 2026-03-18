import base64
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from config.settings import app_config




def send_email_with_pdf(to_email: str, subject: str, content: str, pdf_bytes: bytes):
    try:
        message = Mail(
            from_email=(app_config.SENDGRID_FROM_EMAIL, app_config.SENDGRID_FROM_NAME),
            to_emails=to_email,
            subject=subject,
            html_content=content
        )

        # ✅ PDF attach
        encoded_file = base64.b64encode(pdf_bytes).decode()

        attachment = Attachment(
            FileContent(encoded_file),
            FileName("Booking_Report.pdf"),
            FileType("application/pdf"),
            Disposition("attachment")
        )

        message.attachment = attachment

        # ✅ Send email
        sg = SendGridAPIClient(app_config.SENDGRID_API_KEY)
        response = sg.send(message)

        print(f"✅ Email sent to {to_email} | Status: {response.status_code}")

    except Exception as e:
        print(f"❌ SendGrid Error for {to_email}: {str(e)}")

def build_email_html(title: str, from_date: str, to_date: str):
    return f"""
    <html>
    <body style="font-family: Arial; background-color:#f6f6f6; padding:20px;">
        <div style="max-width:600px; margin:auto; background:white; padding:20px; border-radius:8px;">
            
            <h2 style="margin-bottom:5px;">MOMA.HOUSE</h2>
            <p style="color:gray; margin-top:0;">Premium Property Management</p>

            <hr>

            <h3>{title}</h3>
            <p><b>Reporting Period:</b> {from_date} → {to_date}</p>

            <p>
                This email contains your <b>scheduled report</b>, automatically generated 
                based on your system configuration.
            </p>

            <p>
                📎 The detailed report is attached as a PDF for your review.
            </p>

            <br>

            <p>
                If you have any questions or need assistance, feel free to contact our team.
            </p>

            <br>

            <hr>

            <p style="font-size:12px; color:gray;">
                MOMA.HOUSE — Premium Property Management<br>
                This is an automated email. Please do not reply.
            </p>

        </div>
    </body>
    </html>
    """