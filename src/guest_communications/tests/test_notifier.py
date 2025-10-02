def test_send_welcome_email_and_sms(mocker):
    mock_email = mocker.patch("guest_communications.email_client.EmailClient.send")
    mock_sms = mocker.patch("guest_communications.sms_client.SMSClient.send")

    from guest_communications.notifier import Notifier
    from utils.models import BookingData, Platform

    booking = BookingData(
        reservation_id="123",
        platform=Platform.AIRBNB,
        guest_name="Alice",
        guest_phone="+1234567890",
        guest_email="alice@example.com",
        check_in_date="2025-09-23",
        check_out_date="2025-09-25",
        property_name="Sea View Villa"
    )

    notifier = Notifier()
    result = notifier.send_welcome(booking)

    assert result is True
    mock_email.assert_called_once()
    mock_sms.assert_called_once()
