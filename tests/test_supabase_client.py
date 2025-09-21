"""
Unit tests for the Supabase client module.
"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, date

from src.supabase_sync.supabase_client import SupabaseClient
from src.utils.models import BookingData, Platform


@pytest.fixture
def supabase_client():
    client = SupabaseClient()
    client.initialized = True
    client.client = Mock()
    return client


@pytest.fixture
def sample_booking_data():
    return BookingData(
        guest_name="John Doe",
        guest_phone="+1-555-123-4567",
        check_in_date=date(2024, 12, 15),
        check_out_date=date(2024, 12, 20),
        reservation_id="VRBO-12345",
        property_id="PROP-67890",
        platform=Platform.VRBO,
        number_of_guests=4,
        email_id="email-12345"
    )


def _mock_select_return(mock_client, rows):
    table = Mock()
    mock_client.table.return_value = table
    table.select.return_value = table
    table.eq.return_value = table
    table.limit.return_value = table
    table.order.return_value = table

    res = Mock()
    res.data = rows
    table.execute.return_value = res
    return table


def test_sync_single_booking_success(supabase_client, sample_booking_data):
    # Not existing first
    _mock_select_return(supabase_client.client, [])
    # Upsert mock
    table = supabase_client.client.table.return_value
    table.upsert.return_value = table

    result = supabase_client.sync_booking(sample_booking_data)

    assert result.success is True
    assert result.is_new is True
    table.upsert.assert_called_once()


def test_sync_booking_duplicate(supabase_client, sample_booking_data):
    _mock_select_return(supabase_client.client, [sample_booking_data.to_dict()])

    result = supabase_client.sync_booking(sample_booking_data)
    assert result.success is True
    assert result.is_new is False
    # upsert should not be called when already exists and not dry_run
    table = supabase_client.client.table.return_value
    table.upsert.assert_not_called()


def test_sync_booking_dry_run(supabase_client, sample_booking_data):
    _mock_select_return(supabase_client.client, [])
    table = supabase_client.client.table.return_value
    table.upsert.return_value = table

    result = supabase_client.sync_booking(sample_booking_data, dry_run=True)
    assert result.success is True
    assert result.is_new is True
    table.upsert.assert_not_called()


def test_get_bookings_by_platform(supabase_client):
    rows = [{"reservation_id": "1", "platform": "vrbo"}]
    table = _mock_select_return(supabase_client.client, rows)
    res = supabase_client.get_bookings_by_platform("vrbo", limit=5)
    assert res == rows
    table.limit.assert_called_with(5)


def test_update_and_delete_booking(supabase_client):
    table = supabase_client.client.table.return_value
    # Update
    table.update.return_value = table
    table.eq.return_value = table
    assert supabase_client.update_booking("ABC", {"guest_name": "Jane"}) is True
    # Delete
    table.delete.return_value = table
    assert supabase_client.delete_booking("ABC") is True


def test_initialize_missing_config(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "")
    from importlib import reload
    from config import settings
    reload(settings)
    client = SupabaseClient()
    assert client.initialize() is False
