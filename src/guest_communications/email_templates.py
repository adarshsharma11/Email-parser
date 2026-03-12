from ..api.config import settings

class EmailTemplates:
    @staticmethod
    def get_welcome_template(guest_name: str, property_name: str, check_in: str, check_out: str, reservation_id: str) -> str:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333; line-height: 1.6; margin: 0; padding: 0; }}
                .container {{ max-width: 600px; margin: 20px auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }}
                .header {{ background-color: #ff385c; color: white; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .content {{ padding: 30px; }}
                .property-info {{ background-color: #f7f7f7; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                .date-grid {{ display: flex; justify-content: space-between; margin-bottom: 10px; }}
                .date-item {{ flex: 1; }}
                .date-label {{ font-size: 12px; color: #717171; text-transform: uppercase; font-weight: bold; }}
                .date-value {{ font-size: 16px; font-weight: bold; }}
                .footer {{ background-color: #f7f7f7; padding: 20px; text-align: center; font-size: 12px; color: #717171; }}
                .btn {{ display: inline-block; background-color: #ff385c; color: white !important; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Your Booking is Confirmed! 🎉</h1>
                </div>
                <div class="content">
                    <p>Hi <strong>{guest_name}</strong>,</p>
                    <p>We're thrilled to host you! Your reservation at <strong>{property_name}</strong> is all set.</p>
                    
                    <div class="property-info">
                        <div class="date-grid">
                            <div class="date-item">
                                <div class="date-label">Check-in</div>
                                <div class="date-value">{check_in}</div>
                            </div>
                            <div class="date-item" style="text-align: right;">
                                <div class="date-label">Check-out</div>
                                <div class="date-value">{check_out}</div>
                            </div>
                        </div>
                        <div style="margin-top: 15px;">
                            <div class="date-label">Reservation ID</div>
                            <div class="date-value">{reservation_id}</div>
                        </div>
                    </div>

                    <p>If you have any questions before your arrival, please don't hesitate to reach out. We want to ensure your stay is absolutely perfect!</p>
                    <p>Contact us on effi@fireflymedia.com!</p>
                    
                </div>
                <div class="footer">
                    <p>&copy; 2026 Vacation Rental Management. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

    @staticmethod
    def get_cleaning_template(crew_name: str, property_name: str, scheduled_date: str, task_id: str, guest_details: str = "") -> str:
        api_base = f"{settings.api_base_url}{settings.api_prefix}/{settings.api_version}/service-bookings/respond"
        accept_url = f"{api_base}?task_id={task_id}&type=cleaning&action=accept"
        reject_url = f"{api_base}?task_id={task_id}&type=cleaning&action=reject"
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333; line-height: 1.6; margin: 0; padding: 0; }}
                .container {{ max-width: 600px; margin: 20px auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }}
                .header {{ background-color: #008489; color: white; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .content {{ padding: 30px; }}
                .task-info {{ background-color: #f7f7f7; border-radius: 8px; padding: 20px; margin: 20px 0; border-left: 4px solid #008489; }}
                .label {{ font-size: 12px; color: #717171; text-transform: uppercase; font-weight: bold; }}
                .value {{ font-size: 16px; font-weight: bold; margin-bottom: 15px; }}
                .guest-box {{ background-color: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 15px; margin-top: 20px; }}
                .footer {{ background-color: #f7f7f7; padding: 20px; text-align: center; font-size: 12px; color: #717171; }}
                .actions {{ text-align: center; margin-top: 30px; }}
                .btn {{ display: inline-block; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 0 10px; }}
                .btn-accept {{ background-color: #28a745; color: white !important; }}
                .btn-reject {{ background-color: #dc3545; color: white !important; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>New Cleaning Assignment 🧹</h1>
                </div>
                <div class="content">
                    <p>Hi <strong>{crew_name}</strong>,</p>
                    <p>You have a new cleaning task scheduled.</p>
                    
                    <div class="task-info">
                        <div class="label">Property</div>
                        <div class="value">{property_name}</div>
                        
                        <div class="label">Scheduled Date</div>
                        <div class="value">{scheduled_date}</div>
                    </div>

                    {f'<div class="guest-box"><strong>Guest Details:</strong><br/>{guest_details}</div>' if guest_details else ''}

                    <div class="actions">
                        <a href="{accept_url}" class="btn btn-accept">Accept Task</a>
                        <a href="{reject_url}" class="btn btn-reject">Reject Task</a>
                    </div>

                    <p style="margin-top: 20px; text-align: center; font-size: 14px;">Please confirm your availability by clicking one of the buttons above.</p>
                </div>
                <div class="footer">
                    <p>&copy; 2026 Vacation Rental Management. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

    @staticmethod
    def get_service_template(provider_name: str, service_name: str, property_name: str, service_date: str, service_time: str, task_id: str, reservation_id: str = "") -> str:
        api_base = f"{settings.api_base_url}{settings.api_prefix}/{settings.api_version}/service-bookings/respond"
        accept_url = f"{api_base}?task_id={task_id}&type=service&action=accept"
        reject_url = f"{api_base}?task_id={task_id}&type=service&action=reject"
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333; line-height: 1.6; margin: 0; padding: 0; }}
                .container {{ max-width: 600px; margin: 20px auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }}
                .header {{ background-color: #4a148c; color: white; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .content {{ padding: 30px; }}
                .task-info {{ background-color: #f3e5f5; border-radius: 8px; padding: 20px; margin: 20px 0; border-left: 4px solid #4a148c; }}
                .label {{ font-size: 12px; color: #717171; text-transform: uppercase; font-weight: bold; }}
                .value {{ font-size: 16px; font-weight: bold; margin-bottom: 15px; }}
                .footer {{ background-color: #f7f7f7; padding: 20px; text-align: center; font-size: 12px; color: #717171; }}
                .actions {{ text-align: center; margin-top: 30px; }}
                .btn {{ display: inline-block; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 0 10px; }}
                .btn-accept {{ background-color: #28a745; color: white !important; }}
                .btn-reject {{ background-color: #dc3545; color: white !important; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>New Service Assignment 🛠️</h1>
                </div>
                <div class="content">
                    <p>Hi <strong>{provider_name}</strong>,</p>
                    <p>You have a new service task assigned.</p>
                    
                    <div class="task-info">
                        <div class="label">Service</div>
                        <div class="value">{service_name}</div>

                        <div class="label">Property</div>
                        <div class="value">{property_name}</div>
                        
                        <div class="label">Date & Time</div>
                        <div class="value">{service_date} at {service_time}</div>
                        
                        {f'<div class="label">Reservation ID</div><div class="value">{reservation_id}</div>' if reservation_id else ''}
                    </div>

                    <div class="actions">
                        <a href="{accept_url}" class="btn btn-accept">Accept Task</a>
                        <a href="{reject_url}" class="btn btn-reject">Reject Task</a>
                    </div>

                    <p style="margin-top: 20px; text-align: center; font-size: 14px;">Please confirm your availability by clicking one of the buttons above.</p>
                </div>
                <div class="footer">
                    <p>&copy; 2026 Vacation Rental Management. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
