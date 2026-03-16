#!/usr/bin/env python3
"""
Runner script for the Cleaning Task Follow-up Cron Job.

Intended to be invoked directly from the OS scheduler:
    0 */4 * * * python /path/to/Email-parser/src/cron_jobs/run_cleaning_followup.py

Exit codes:
    0 – job completed successfully
    1 – job encountered an unrecoverable error
"""

import asyncio
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the project root (Email-parser/) is on sys.path so that absolute
# imports such as `src.cron_jobs.cleaning_task_followup` resolve correctly
# when this script is invoked from any working directory.
# ---------------------------------------------------------------------------
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.db.psql_client import psql_client  # noqa: E402
from src.cron_jobs.cleaning_task_followup import CleaningTaskFollowupCron  # noqa: E402

# ---------------------------------------------------------------------------
# Logging – write to stdout only; no hardcoded /var/log paths so the script
# works on Windows, Linux, and macOS without any extra configuration.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Async main
# ---------------------------------------------------------------------------

async def main() -> int:
    """Open a database session and run the cron job. Returns an exit code."""
    try:
        cron = CleaningTaskFollowupCron()
        async with psql_client.async_session_factory() as session:
            await cron.run(session)
        logger.info("Cron job completed successfully")
        return 0
    except Exception as exc:
        logger.error(f"Cron job failed with unrecoverable error: {exc}", exc_info=True)
        return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
