"""
Cleaning Task Follow-up Cron Job

Runs every 4 hours to find cleaning tasks that have not been accepted by a crew
member within the follow-up window, then escalates to the next eligible crew
member via email.

Key reliability features:
  - FOR UPDATE SKIP LOCKED  : prevents two cron instances racing on the same row
  - _has_reached_max_notifications : caps escalation attempts per task
  - _already_notified_crew  : prevents duplicate emails to the same crew member
  - _fetch_booking_data     : enriches notifications with guest details
  - Per-task transaction commits: a failure on one task never rolls back others
  - Notification status tracking: audit log records 'sent' or 'failed' per attempt
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.services.crew_service import CrewService
from src.guest_communications.notifier import Notifier

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

# Tasks created more than this many hours ago without a response are overdue.
FOLLOWUP_TASK_AGE_HOURS: int = 4

# Maximum number of follow-up notifications per task (escalation cap).
MAX_NOTIFICATIONS_PER_TASK: int = 3


# ---------------------------------------------------------------------------
# Main cron job class
# ---------------------------------------------------------------------------

class CleaningTaskFollowupCron:
    """Cron job that escalates unaccepted cleaning tasks to the next eligible crew."""

    def __init__(self) -> None:
        self.notifier = Notifier()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, session: AsyncSession) -> None:
        """
        Main entry point called by the runner script.

        Each task is processed inside its own savepoint so that a failure on
        one task cannot roll back updates already committed for previous tasks.
        """
        logger.info("Starting cleaning task follow-up cron job")

        unaccepted_tasks = await self._find_unaccepted_tasks(session)
        logger.info(f"Found {len(unaccepted_tasks)} unaccepted cleaning task(s)")

        processed = 0
        for task in unaccepted_tasks:
            task_id = task["id"]
            try:
                await self._process_unaccepted_task(session, task)
                await session.commit()
                processed += 1
            except Exception as exc:
                logger.error(
                    f"[task_id={task_id}] Unexpected error during processing; "
                    f"rolling back this task. Error: {exc}"
                )
                await session.rollback()

        logger.info(
            f"Completed processing: {processed}/{len(unaccepted_tasks)} task(s) handled successfully"
        )

    # ------------------------------------------------------------------
    # Step 1 – Query: find overdue, unaccepted tasks
    # ------------------------------------------------------------------

    async def _find_unaccepted_tasks(self, session: AsyncSession) -> List[Dict[str, Any]]:
        """
        Return cleaning tasks that are eligible for follow-up, which means they:
          - have not been accepted, AND
          - are either rejected, OR are pending and older than the timeout.

        Uses FOR UPDATE SKIP LOCKED to ensure only one concurrent cron instance
        processes each row.
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=FOLLOWUP_TASK_AGE_HOURS)

        query = text("""
            SELECT
                ct.id,
                ct.reservation_id,
                ct.property_id,
                ct.scheduled_date,
                ct.category_id,
                ct.crew_id,
                ct.created_at
            FROM cleaning_tasks ct
            WHERE
              -- Global condition: Task must not have been accepted.
               NOT EXISTS (
                   SELECT 1
                   FROM task_responses tr
                   WHERE (tr.task_id = ct.id::text OR tr.task_id = ct.reservation_id)
                     AND tr.task_type = 'cleaning'
                     AND tr.response = 'accepted'
               )
              AND (
                -- Trigger 1: Task is pending and has passed the follow-up timeout.
                (ct.status = 'pending' AND ct.created_at <= :cutoff_time)
                OR
                -- Trigger 2: Task has been explicitly rejected.
                (ct.status = 'rejected')
              )
            ORDER BY 
              CASE WHEN ct.status = 'rejected' THEN 0 ELSE 1 END, -- Prioritize rejected tasks
              ct.created_at DESC -- Then most recent ones
            LIMIT 500
            FOR UPDATE SKIP LOCKED
        """)

        result = await session.execute(query, {"cutoff_time": cutoff_time})
        tasks = [dict(row._mapping) for row in result.fetchall()]
        return tasks

    # ------------------------------------------------------------------
    # Step 2 – Orchestrate processing of a single task
    # ------------------------------------------------------------------

    async def _process_unaccepted_task(
        self, session: AsyncSession, task: Dict[str, Any]
    ) -> None:
        """
        Full escalation pipeline for one task:
          1. Check escalation cap
          2. Fetch booking data for richer email content
          3. Find the next eligible crew member
          4. Send notification email
          5. Update task assignment
          6. Log the notification (sent or failed)
        """
        task_id = task["id"]
        logger.info(
            f"[task_id={task_id}] Processing task "
            f"(property={task['property_id']}, scheduled={task['scheduled_date']})"
        )

        # --- Guard 1: escalation cap ---
        if await self._has_reached_max_notifications(session, task_id):
            logger.warning(
                f"[task_id={task_id}] Maximum notification limit "
                f"({MAX_NOTIFICATIONS_PER_TASK}) reached. Skipping."
            )
            return

        # --- Enrich with booking data ---
        booking = await self._fetch_booking_data(session, task.get("reservation_id"))
        if booking:
            logger.info(f"[task_id={task_id}] Booking data fetched (reservation_id={task.get('reservation_id')})")
        else:
            logger.info(f"[task_id={task_id}] No booking data found; proceeding without guest details")

        # --- Find next eligible crew ---
        next_crew = await self._find_next_crew(session, task)
        if not next_crew:
            logger.warning(f"[task_id={task_id}] No eligible crew member found. Skipping.")
            return

        crew_id = next_crew["id"]
        logger.info(
            f"[task_id={task_id}] Next crew selected: "
            f"name={next_crew.get('name')}, crew_id={crew_id}"
        )

        # --- Send notification ---
        notification_task = {
            "id": task_id,
            "property_id": task["property_id"],
            "scheduled_date": (
                task["scheduled_date"].strftime("%Y-%m-%d")
                if hasattr(task["scheduled_date"], "strftime")
                else str(task["scheduled_date"])
            ),
            "reservation_id": task.get("reservation_id"),
        }

        send_success, error_msg = await self._send_notification(
            next_crew, notification_task, booking
        )

        if send_success:
            logger.info(
                f"[task_id={task_id}] Notification email sent successfully to "
                f"crew_id={crew_id} ({next_crew.get('email')})"
            )
            # Update the task's assigned crew
            await self._update_task_assignment(session, task_id, crew_id)
            logger.info(f"[task_id={task_id}] Task assignment updated to crew_id={crew_id}")
        else:
            logger.error(
                f"[task_id={task_id}] Notification email FAILED for crew_id={crew_id}. "
                f"Error: {error_msg}"
            )

        # Always log the attempt (success or failure) for audit purposes
        await self._log_notification(
            session, task_id, crew_id, success=send_success, error_msg=error_msg
        )
        logger.info(
            f"[task_id={task_id}] Notification logged (status="
            f"{'sent' if send_success else 'failed'})"
        )

    # ------------------------------------------------------------------
    # Step 3 – Escalation cap guard
    # ------------------------------------------------------------------

    async def _has_reached_max_notifications(
        self, session: AsyncSession, task_id: int
    ) -> bool:
        """
        Return True if this task already has MAX_NOTIFICATIONS_PER_TASK or more
        entries in task_notifications (regardless of send status).
        """
        query = text("""
            SELECT COUNT(*) AS cnt
            FROM task_notifications
            WHERE task_id = :task_id
        """)
        result = await session.execute(query, {"task_id": task_id})
        row = result.fetchone()
        count = row[0] if row else 0
        return count >= MAX_NOTIFICATIONS_PER_TASK

    # ------------------------------------------------------------------
    # Step 4 – Duplicate-crew guard
    # ------------------------------------------------------------------

    async def _already_notified_crew(
        self, session: AsyncSession, task_id: int, crew_id: int
    ) -> bool:
        """
        Return True if the given (task_id, crew_id) pair already exists in
        task_notifications, meaning this crew member was already contacted for
        this task and should not receive a duplicate email.
        """
        query = text("""
            SELECT 1
            FROM task_notifications
            WHERE task_id = :task_id
              AND crew_id  = :crew_id
            LIMIT 1
        """)
        result = await session.execute(query, {"task_id": task_id, "crew_id": crew_id})
        return result.fetchone() is not None

    # ------------------------------------------------------------------
    # Step 5 – Fetch related booking data
    # ------------------------------------------------------------------

    async def _fetch_booking_data(
        self, session: AsyncSession, reservation_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch the booking record from the `bookings` table that corresponds to
        the task's reservation_id. Returns a plain dict or None if not found.
        The dict is passed into notify_cleaning_task() for richer email content.
        """
        if not reservation_id:
            return None
        try:
            query = text("""
                SELECT reservation_id, guest_name, guest_email, guest_phone,
                       check_in_date, check_out_date, property_name
                FROM bookings
                WHERE reservation_id = :reservation_id
                LIMIT 1
            """)
            result = await session.execute(query, {"reservation_id": reservation_id})
            row = result.fetchone()
            return dict(row._mapping) if row else None
        except Exception as exc:
            logger.warning(
                f"[reservation_id={reservation_id}] Could not fetch booking data: {exc}"
            )
            return None

    # ------------------------------------------------------------------
    # Step 6 – Determine next eligible crew member
    # ------------------------------------------------------------------

    async def _find_next_crew(
        self, session: AsyncSession, task: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Identify the next crew member to notify.
        
        Priority:
          1. Active crews for the same property AND category.
          2. Fallback: Any active crew in the same category.
        
        In both cases, we exclude:
          - the crew currently assigned to the task
          - any crew already notified (via task_notifications)
        """
        task_id = task["id"]
        current_crew_id = task.get("crew_id")
        category_id = task.get("category_id")
        property_id = task.get("property_id")

        crew_service = CrewService(session)

        # 1. Try finding crews for the specific property
        if property_id:
            active_crews = await crew_service.get_active_crews(property_id=property_id)
            for crew in active_crews:
                if self._is_crew_eligible(crew, current_crew_id, category_id):
                    if not await self._already_notified_crew(session, task_id, crew["id"]):
                        return crew

        # 2. Fallback: Try all active crews in the same category
        if category_id:
            all_crews = await crew_service.get_active_crews()
            for crew in all_crews:
                if self._is_crew_eligible(crew, current_crew_id, category_id):
                    if not await self._already_notified_crew(session, task_id, crew["id"]):
                        return crew

        return None

    def _is_crew_eligible(self, crew: Dict[str, Any], current_crew_id: Optional[int], category_id: Optional[int]) -> bool:
        """Helper to check if a crew member is eligible for a task."""
        crew_id = crew.get("id")
        
        # Must not be the current assignee
        if crew_id == current_crew_id:
            return False
            
        # Must match category if one is specified
        if category_id and crew.get("category_id") != category_id:
            return False
            
        return True

    # ------------------------------------------------------------------
    # Step 7 – Send the notification email
    # ------------------------------------------------------------------

    async def _send_notification(
        self,
        crew: Dict[str, Any],
        task: Dict[str, Any],
        booking: Optional[Dict[str, Any]],
    ) -> tuple[bool, Optional[str]]:
        """
        Attempt to send a cleaning task email via the existing Notifier.
        Returns a (success: bool, error_message: str | None) tuple.

        Booking data (if available) is passed in so the email template can
        include guest name, check-in/check-out dates, etc.
        """
        try:
            # notify_cleaning_task accepts a BookingData or None; pass the raw
            # dict as a simple namespace-like object when booking data exists.
            booking_obj = None
            if booking:
                # Build a minimal object that satisfies notifier's attribute access
                class _BookingProxy:
                    def __init__(self, d: Dict[str, Any]) -> None:
                        self.guest_name = d.get("guest_name", "Guest")
                        self.check_in_date = d.get("check_in_date", "")
                        self.check_out_date = d.get("check_out_date", "")
                        self.guest_email = d.get("guest_email")
                        self.guest_phone = d.get("guest_phone")
                        self.reservation_id = d.get("reservation_id", "")
                        self.property_name = d.get("property_name", task.get("property_id", ""))

                booking_obj = _BookingProxy(booking)

            success = self.notifier.notify_cleaning_task(
                crew=crew,
                task=task,
                booking=booking_obj,
                include_calendar_invite=True,
            )
            if success:
                return True, None
            return False, "notify_cleaning_task returned False"

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.error(
                f"[task_id={task.get('id')}] Exception while sending notification "
                f"to crew_id={crew.get('id')}: {error_msg}"
            )
            return False, error_msg

    # ------------------------------------------------------------------
    # Step 8 – Persist assignment update
    # ------------------------------------------------------------------

    async def _update_task_assignment(
        self, session: AsyncSession, task_id: int, crew_id: int
    ) -> None:
        """
        Update cleaning_tasks.crew_id to reflect the newly notified crew.
        Also reset the status to 'pending' so the new crew member has a chance
        to accept or reject it, and reset created_at so the 4-hour timeout
        starts fresh for the new assignee.
        """
        query = text("""
            UPDATE cleaning_tasks
            SET crew_id = :crew_id,
                status = 'pending',
                created_at = CURRENT_TIMESTAMP
            WHERE id = :task_id
        """)
        await session.execute(query, {"task_id": task_id, "crew_id": crew_id})

    # ------------------------------------------------------------------
    # Step 9 – Write audit log entry
    # ------------------------------------------------------------------

    async def _log_notification(
        self,
        session: AsyncSession,
        task_id: int,
        crew_id: int,
        *,
        success: bool,
        error_msg: Optional[str],
    ) -> None:
        """
        Insert a row into task_notifications for every notification attempt,
        recording whether the email was sent ('sent') or failed ('failed').
        This ensures the audit trail is accurate even when deliveries fail.
        """
        status = "sent" if success else "failed"
        query = text("""
            INSERT INTO task_notifications
                (task_id, crew_id, notification_type, status, error_message)
            VALUES
                (:task_id, :crew_id, 'follow_up_email', :status, :error_message)
        """)
        await session.execute(
            query,
            {
                "task_id": task_id,
                "crew_id": crew_id,
                "status": status,
                "error_message": error_msg,
            },
        )
