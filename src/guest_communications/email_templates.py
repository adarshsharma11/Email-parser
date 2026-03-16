from ..api.config import settings
import time

class EmailTemplates:
    @staticmethod
    def get_welcome_template(guest_name: str, property_name: str, check_in: str, check_out: str, reservation_id: str) -> str:
        return f"""
        <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
        <html xmlns="http://www.w3.org/1999/xhtml">
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
            <title>Booking Confirmation</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
        </head>
        <body style="margin: 0; padding: 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333333; line-height: 1.6; background-color: #f9f9f9;">
            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                    <td style="padding: 20px 0 30px 0;">
                        <table align="center" border="0" cellpadding="0" cellspacing="0" width="600" style="border: 1px solid #e0e0e0; border-radius: 8px; background-color: #ffffff; overflow: hidden;">
                            <tr>
                                <td align="center" bgcolor="#ff385c" style="padding: 40px 0 30px 0; color: #ffffff; font-size: 28px; font-weight: bold;">
                                    Your Booking is Confirmed! 🎉
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px 30px 40px 30px;">
                                    <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                        <tr>
                                            <td style="font-size: 18px; font-weight: bold; padding-bottom: 20px;">
                                                Hi {guest_name},
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="font-size: 16px; padding-bottom: 30px;">
                                                We're thrilled to host you! Your reservation at <strong>{property_name}</strong> is all set. Here are your booking details:
                                            </td>
                                        </tr>
                                        <tr>
                                            <td>
                                                <table border="0" cellpadding="20" cellspacing="0" width="100%" style="background-color: #f7f7f7; border-radius: 8px;">
                                                    <tr>
                                                        <td width="50%" style="vertical-align: top;">
                                                            <div style="font-size: 12px; color: #717171; text-transform: uppercase; font-weight: bold;">Check-in</div>
                                                            <div style="font-size: 16px; font-weight: bold;">{check_in}</div>
                                                        </td>
                                                        <td width="50%" style="vertical-align: top; text-align: right;">
                                                            <div style="font-size: 12px; color: #717171; text-transform: uppercase; font-weight: bold;">Check-out</div>
                                                            <div style="font-size: 16px; font-weight: bold;">{check_out}</div>
                                                        </td>
                                                    </tr>
                                                    <tr>
                                                        <td colspan="2" style="padding-top: 15px; border-top: 1px solid #e0e0e0;">
                                                            <div style="font-size: 12px; color: #717171; text-transform: uppercase; font-weight: bold;">Reservation ID</div>
                                                            <div style="font-size: 16px; font-weight: bold;">{reservation_id}</div>
                                                        </td>
                                                    </tr>
                                                </table>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="padding-top: 30px; font-size: 16px;">
                                                If you have any questions before your arrival, please don't hesitate to reach out. We want to ensure your stay is absolutely perfect!
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="padding-top: 20px; font-size: 16px;">
                                                Contact us at <a href="mailto:effi@fireflymedia.com" style="color: #ff385c; text-decoration: none; font-weight: bold;">effi@fireflymedia.com</a>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                            <tr>
                                <td bgcolor="#f7f7f7" style="padding: 30px 30px 30px 30px; color: #717171; font-size: 12px; text-align: center;">
                                    <p style="margin: 0;">&copy; 2026 Vacation Rental Management. All rights reserved.</p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

    @staticmethod
    def get_cleaning_template(crew_name: str, property_name: str, scheduled_date: str, task_id: str, guest_details: str = "") -> str:
        api_base = f"{settings.api_base_url}/service-bookings/respond"
        # 4 hour expiration (14400 seconds)
        expires_at = int(time.time()) + 14400
        accept_url = f"{api_base}?task_id={task_id}&type=cleaning&action=accept&expires_at={expires_at}"
        reject_url = f"{api_base}?task_id={task_id}&type=cleaning&action=reject&expires_at={expires_at}"
        
        return f"""
        <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
        <html xmlns="http://www.w3.org/1999/xhtml">
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
            <title>New Cleaning Assignment</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
        </head>
        <body style="margin: 0; padding: 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333333; line-height: 1.6; background-color: #f9f9f9;">
            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                    <td style="padding: 20px 0 30px 0;">
                        <table align="center" border="0" cellpadding="0" cellspacing="0" width="600" style="border: 1px solid #e0e0e0; border-radius: 8px; background-color: #ffffff; overflow: hidden;">
                            <tr>
                                <td align="center" bgcolor="#008489" style="padding: 40px 0 30px 0; color: #ffffff; font-size: 28px; font-weight: bold;">
                                    New Cleaning Assignment 🧹
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px 30px 40px 30px;">
                                    <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                        <tr>
                                            <td style="font-size: 18px; font-weight: bold; padding-bottom: 20px;">
                                                Hi {crew_name},
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="font-size: 16px; padding-bottom: 30px;">
                                                You have a new cleaning task scheduled. Please review the details below:
                                            </td>
                                        </tr>
                                        <tr>
                                            <td>
                                                <table border="0" cellpadding="20" cellspacing="0" width="100%" style="background-color: #f7f7f7; border-radius: 8px; border-left: 4px solid #008489;">
                                                    <tr>
                                                        <td>
                                                            <div style="font-size: 12px; color: #717171; text-transform: uppercase; font-weight: bold;">Property</div>
                                                            <div style="font-size: 16px; font-weight: bold; margin-bottom: 15px;">{property_name}</div>
                                                            
                                                            <div style="font-size: 12px; color: #717171; text-transform: uppercase; font-weight: bold;">Scheduled Date</div>
                                                            <div style="font-size: 16px; font-weight: bold;">{scheduled_date}</div>
                                                        </td>
                                                    </tr>
                                                </table>
                                            </td>
                                        </tr>
                                        {f'<tr><td style="padding-top: 20px;"><div style="background-color: #ffffff; border: 1px solid #dddddd; border-radius: 8px; padding: 15px;"><strong>Guest Details:</strong><br/>{guest_details}</div></td></tr>' if guest_details else ''}
                                        <tr>
                                            <td align="center" style="padding-top: 40px;">
                                                <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                                    <tr>
                                                        <td align="center" style="padding-bottom: 20px;">
                                                            <a href="{accept_url}" style="background-color: #28a745; color: #ffffff; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; min-width: 120px; text-align: center;">Accept Task</a>
                                                        </td>
                                                    </tr>
                                                    <tr>
                                                        <td align="center">
                                                            <a href="{reject_url}" style="background-color: #dc3545; color: #ffffff; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; min-width: 120px; text-align: center;">Reject Task</a>
                                                        </td>
                                                    </tr>
                                                </table>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="padding-top: 30px; font-size: 14px; text-align: center; color: #717171;">
                                                Please confirm your availability by clicking one of the buttons above.<br/>
                                                <em>Note: These links will expire in 4 hours.</em>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                            <tr>
                                <td bgcolor="#f7f7f7" style="padding: 30px 30px 30px 30px; color: #717171; font-size: 12px; text-align: center;">
                                    <p style="margin: 0;">&copy; 2026 Vacation Rental Management. All rights reserved.</p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

    @staticmethod
    def get_service_template(provider_name: str, service_name: str, property_name: str, service_date: str, service_time: str, task_id: str, reservation_id: str = "") -> str:
        api_base = f"{settings.api_base_url}/service-bookings/respond"
        # 4 hour expiration (14400 seconds)
        expires_at = int(time.time()) + 14400
        accept_url = f"{api_base}?task_id={task_id}&type=service&action=accept&expires_at={expires_at}"
        reject_url = f"{api_base}?task_id={task_id}&type=service&action=reject&expires_at={expires_at}"
        
        return f"""
        <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
        <html xmlns="http://www.w3.org/1999/xhtml">
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
            <title>New Service Assignment</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
        </head>
        <body style="margin: 0; padding: 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333333; line-height: 1.6; background-color: #f9f9f9;">
            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                    <td style="padding: 20px 0 30px 0;">
                        <table align="center" border="0" cellpadding="0" cellspacing="0" width="600" style="border: 1px solid #e0e0e0; border-radius: 8px; background-color: #ffffff; overflow: hidden;">
                            <tr>
                                <td align="center" bgcolor="#4a148c" style="padding: 40px 0 30px 0; color: #ffffff; font-size: 28px; font-weight: bold;">
                                    New Service Assignment 🛠️
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px 30px 40px 30px;">
                                    <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                        <tr>
                                            <td style="font-size: 18px; font-weight: bold; padding-bottom: 20px;">
                                                Hi {provider_name},
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="font-size: 16px; padding-bottom: 30px;">
                                                You have a new service task assigned. Please review the details below:
                                            </td>
                                        </tr>
                                        <tr>
                                            <td>
                                                <table border="0" cellpadding="20" cellspacing="0" width="100%" style="background-color: #f3e5f5; border-radius: 8px; border-left: 4px solid #4a148c;">
                                                    <tr>
                                                        <td>
                                                            <div style="font-size: 12px; color: #717171; text-transform: uppercase; font-weight: bold;">Service</div>
                                                            <div style="font-size: 16px; font-weight: bold; margin-bottom: 15px;">{service_name}</div>

                                                            <div style="font-size: 12px; color: #717171; text-transform: uppercase; font-weight: bold;">Property</div>
                                                            <div style="font-size: 16px; font-weight: bold; margin-bottom: 15px;">{property_name}</div>
                                                            
                                                            <div style="font-size: 12px; color: #717171; text-transform: uppercase; font-weight: bold;">Date & Time</div>
                                                            <div style="font-size: 16px; font-weight: bold; margin-bottom: 15px;">{service_date} at {service_time}</div>
                                                            
                                                            {f'<div style="font-size: 12px; color: #717171; text-transform: uppercase; font-weight: bold;">Reservation ID</div><div style="font-size: 16px; font-weight: bold;">{reservation_id}</div>' if reservation_id else ''}
                                                        </td>
                                                    </tr>
                                                </table>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td align="center" style="padding-top: 40px;">
                                                <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                                    <tr>
                                                        <td align="center" style="padding-bottom: 20px;">
                                                            <a href="{accept_url}" style="background-color: #28a745; color: #ffffff; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; min-width: 120px; text-align: center;">Accept Task</a>
                                                        </td>
                                                    </tr>
                                                    <tr>
                                                        <td align="center">
                                                            <a href="{reject_url}" style="background-color: #dc3545; color: #ffffff; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; min-width: 120px; text-align: center;">Reject Task</a>
                                                        </td>
                                                    </tr>
                                                </table>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="padding-top: 30px; font-size: 14px; text-align: center; color: #717171;">
                                                Please confirm your availability by clicking one of the buttons above.<br/>
                                                <em>Note: These links will expire in 4 hours.</em>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                            <tr>
                                <td bgcolor="#f7f7f7" style="padding: 30px 30px 30px 30px; color: #717171; font-size: 12px; text-align: center;">
                                    <p style="margin: 0;">&copy; 2026 Vacation Rental Management. All rights reserved.</p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
