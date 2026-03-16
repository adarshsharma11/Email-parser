"""
Unit tests for CleaningTaskFollowupCron.

All database and email interactions are mocked – no live DB or network calls.
Run with:
    pytest tests/test_cleaning_task_followup.py -v
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from src.cron_jobs.cleaning_task_followup import (
    CleaningTaskFollowupCron,
    FOLLOWUP_TASK_AGE_HOURS,
    MAX_NOTIFICATIONS_PER_TASK,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session():
    """Async SQLAlchemy session mock."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def sample_task():
    """A cleaning task that is overdue for a follow-up."""
    return {
        "id": 1,
        "reservation_id": "RES-001",
        "property_id": "PROP-101",
        "scheduled_date": datetime.now(timezone.utc) + timedelta(days=1),
        "category_id": 2,
        "crew_id": 10,                        # currently assigned crew
        "created_at": datetime.now(timezone.utc) - timedelta(hours=5),
    }


@pytest.fixture
def sample_crew():
    """A crew member eligible for the next notification."""
    return {
        "id": 20,
        "name": "Jane Smith",
        "email": "jane@example.com",
        "phone": "+10000000000",
        "category_id": 2,
        "active": True,
        "property_id": "PROP-101",
    }


@pytest.fixture
def sample_booking():
    """Booking data that enriches the notification email."""
    return {
        "reservation_id": "RES-001",
        "guest_name": "Alice Guest",
        "guest_email": "alice@example.com",
        "guest_phone": "+19999999999",
        "check_in_date": datetime.now(timezone.utc).date(),
        "check_out_date": (datetime.now(timezone.utc) + timedelta(days=3)).date(),
        "property_name": "Sunset Villa",
    }


def _make_cron() -> CleaningTaskFollowupCron:
    """Return a cron instance without actually calling Notifier().__init__."""
    with patch("src.cron_jobs.cleaning_task_followup.Notifier"):
        return CleaningTaskFollowupCron()


# ---------------------------------------------------------------------------
# 1 – _find_unaccepted_tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_find_unaccepted_tasks(mock_session, sample_task):
    """
    _find_unaccepted_tasks should execute a query and return a list of dicts.
    """
    cron = _make_cron()

    mock_row = Mock()
    mock_row._mapping = sample_task

    mock_result = Mock()
    mock_result.fetchall.return_value = [mock_row]
    mock_session.execute.return_value = mock_result

    tasks = await cron._find_unaccepted_tasks(mock_session)

    assert len(tasks) == 1
    assert tasks[0]["id"] == 1
    assert tasks[0]["property_id"] == "PROP-101"
    mock_session.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# 2 – _process_unaccepted_task – happy path (full flow)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_task_full_flow(mock_session, sample_task, sample_crew, sample_booking):
    """
    When a crew member is available and the email succeeds, all steps should
    run in the correct order.
    """
    cron = _make_cron()

    cron._has_reached_max_notifications = AsyncMock(return_value=False)
    cron._fetch_booking_data = AsyncMock(return_value=sample_booking)
    cron._find_next_crew = AsyncMock(return_value=sample_crew)
    cron._send_notification = AsyncMock(return_value=(True, None))
    cron._update_task_assignment = AsyncMock()
    cron._log_notification = AsyncMock()

    await cron._process_unaccepted_task(mock_session, sample_task)

    cron._has_reached_max_notifications.assert_awaited_once_with(mock_session, 1)
    cron._fetch_booking_data.assert_awaited_once_with(mock_session, "RES-001")
    cron._find_next_crew.assert_awaited_once_with(mock_session, sample_task)
    cron._send_notification.assert_awaited_once()
    cron._update_task_assignment.assert_awaited_once_with(mock_session, 1, 20)
    cron._log_notification.assert_awaited_once_with(
        mock_session, 1, 20, success=True, error_msg=None
    )


# ---------------------------------------------------------------------------
# 3 – _process_unaccepted_task – no crew available
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_task_no_crew(mock_session, sample_task):
    """
    When _find_next_crew returns None, no notification or assignment update
    should happen (but also no error is raised).
    """
    cron = _make_cron()

    cron._has_reached_max_notifications = AsyncMock(return_value=False)
    cron._fetch_booking_data = AsyncMock(return_value=None)
    cron._find_next_crew = AsyncMock(return_value=None)
    cron._send_notification = AsyncMock()
    cron._update_task_assignment = AsyncMock()
    cron._log_notification = AsyncMock()

    await cron._process_unaccepted_task(mock_session, sample_task)

    cron._send_notification.assert_not_awaited()
    cron._update_task_assignment.assert_not_awaited()
    cron._log_notification.assert_not_awaited()


# ---------------------------------------------------------------------------
# 4 – _process_unaccepted_task – max notifications cap reached
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_task_max_notifications_reached(mock_session, sample_task):
    """
    When the escalation cap is already hit, the task should be skipped
    entirely – no crew lookup, no email, no log entry.
    """
    cron = _make_cron()

    cron._has_reached_max_notifications = AsyncMock(return_value=True)
    cron._fetch_booking_data = AsyncMock()
    cron._find_next_crew = AsyncMock()
    cron._send_notification = AsyncMock()
    cron._log_notification = AsyncMock()

    await cron._process_unaccepted_task(mock_session, sample_task)

    cron._fetch_booking_data.assert_not_awaited()
    cron._find_next_crew.assert_not_awaited()
    cron._send_notification.assert_not_awaited()
    cron._log_notification.assert_not_awaited()


# ---------------------------------------------------------------------------
# 5 – _already_notified_crew – duplicate protection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_already_notified_crew_skips_duplicate(mock_session, sample_task, sample_crew):
    """
    When _already_notified_crew returns True for a candidate, _find_next_crew
    should not return that candidate; it must skip to the next one.
    """
    cron = _make_cron()

    # Simulate: first candidate (crew_id=20) already notified → return None
    cron._already_notified_crew = AsyncMock(return_value=True)

    # Patch CrewService so it returns only one crew member (crew_id=20)
    mock_crew_service = AsyncMock()
    mock_crew_service.get_active_crews = AsyncMock(return_value=[sample_crew])
    mock_crew_service.get_single_crew_by_category = AsyncMock(return_value=None)

    with patch(
        "src.cron_jobs.cleaning_task_followup.CrewService",
        return_value=mock_crew_service,
    ):
        result = await cron._find_next_crew(mock_session, sample_task)

    assert result is None, "Should return None when all candidates are already notified"


# ---------------------------------------------------------------------------
# 6 – _send_notification – email succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_notification_success(sample_crew, sample_task, sample_booking):
    """
    _send_notification should return (True, None) when notify_cleaning_task
    returns True.
    """
    cron = _make_cron()
    cron.notifier = MagicMock()
    cron.notifier.notify_cleaning_task.return_value = True

    notification_task = {
        "id": sample_task["id"],
        "property_id": sample_task["property_id"],
        "scheduled_date": "2026-03-15",
        "reservation_id": sample_task["reservation_id"],
    }

    success, error = await cron._send_notification(sample_crew, notification_task, sample_booking)

    assert success is True
    assert error is None
    cron.notifier.notify_cleaning_task.assert_called_once()


# ---------------------------------------------------------------------------
# 7 – _send_notification – email fails (returns False)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_notification_failure(sample_crew, sample_task):
    """
    _send_notification should return (False, <message>) when
    notify_cleaning_task returns False.
    """
    cron = _make_cron()
    cron.notifier = MagicMock()
    cron.notifier.notify_cleaning_task.return_value = False

    notification_task = {
        "id": sample_task["id"],
        "property_id": sample_task["property_id"],
        "scheduled_date": "2026-03-15",
        "reservation_id": sample_task["reservation_id"],
    }

    success, error = await cron._send_notification(sample_crew, notification_task, None)

    assert success is False
    assert error is not None
    assert isinstance(error, str)


# ---------------------------------------------------------------------------
# 8 – _update_task_assignment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_task_assignment(mock_session):
    """
    _update_task_assignment should execute exactly one UPDATE statement with
    the correct task_id and crew_id parameters.
    """
    cron = _make_cron()
    await cron._update_task_assignment(mock_session, task_id=1, crew_id=20)
    mock_session.execute.assert_awaited_once()
    call_args = mock_session.execute.call_args
    params = call_args[0][1]  # second positional arg is the params dict
    assert params["task_id"] == 1
    assert params["crew_id"] == 20


# ---------------------------------------------------------------------------
# 9 – _log_notification – status = 'sent'
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_log_notification_sent(mock_session):
    """
    _log_notification should insert a row with status='sent' and no error_message
    when success=True.
    """
    cron = _make_cron()
    await cron._log_notification(
        mock_session, task_id=1, crew_id=20, success=True, error_msg=None
    )
    mock_session.execute.assert_awaited_once()
    params = mock_session.execute.call_args[0][1]
    assert params["status"] == "sent"
    assert params["error_message"] is None
    assert params["task_id"] == 1
    assert params["crew_id"] == 20


# ---------------------------------------------------------------------------
# 10 – _log_notification – status = 'failed'
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_log_notification_failed(mock_session):
    """
    _log_notification should insert a row with status='failed' and a populated
    error_message when success=False.
    """
    cron = _make_cron()
    await cron._log_notification(
        mock_session,
        task_id=1,
        crew_id=20,
        success=False,
        error_msg="SMTPConnectionError: timeout",
    )
    mock_session.execute.assert_awaited_once()
    params = mock_session.execute.call_args[0][1]
    assert params["status"] == "failed"
    assert params["error_message"] == "SMTPConnectionError: timeout"
