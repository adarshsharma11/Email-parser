# Cleaning Task Follow-up Cron Job - Implementation Guide

## Overview

This document provides comprehensive instructions for implementing a cron job that runs every 4 hours to check for unaccepted cleaning tasks and sends email notifications to the next eligible crew member.

## 🎯 Business Requirements

- **Frequency**: Run every 4 hours
- **Scope**: Check cleaning tasks that have not been accepted within a specified time window
- **Action**: Send email notifications to next available crew member
- **Tracking**: Maintain audit logs of all notifications sent

## 📋 Current System Analysis

### Existing Components

1. **Accept/Reject API** (`/src/api/routes/service_bookings.py`)
   - Endpoint: `GET /service-bookings/respond`
   - Updates task status in `cleaning_tasks` table
   - Logs responses in `task_responses` table

2. **Crew Service** (`/src/api/services/crew_service.py`)
   - Functions: `get_active_crews()`, `get_single_crew_by_category()`
   - Retrieves active crew members by category and property

3. **Notification System** (`/src/guest_communications/`)
   - `notifier.py`: `notify_cleaning_task()` function
   - `email_templates.py`: `get_cleaning_template()` with accept/reject URLs

### Database Schema

```sql
-- cleaning_tasks table
CREATE TABLE cleaning_tasks (
    id SERIAL PRIMARY KEY,
    reservation_id VARCHAR(255),
    property_id VARCHAR(255),
    scheduled_date DATE,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    category_id INTEGER,
    assigned_crew_id INTEGER
);

-- cleaning_crews table  
CREATE TABLE cleaning_crews (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    category_id INTEGER,
    active BOOLEAN DEFAULT TRUE,
    property_id VARCHAR(255)
);

-- task_responses table
CREATE TABLE task_responses (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(255),
    task_type VARCHAR(50),
    response VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 🏗️ Implementation Plan

### Phase 1: Core Cron Job Structure

Create a new file: `/src/cron_jobs/cleaning_task_followup.py`

```python
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from src.api.services.crew_service import CrewService
from src.guest_communications.notifier import Notifier
from src.api.dependencies import get_psql_client

logger = logging.getLogger(__name__)

class CleaningTaskFollowupCron:
    def __init__(self):
        self.psql_client = get_psql_client()
        self.notifier = Notifier()
        
    async def run(self):
        """Main cron job entry point"""
        logger.info("Starting cleaning task follow-up cron job")
        
        try:
            async with self.psql_client.async_session_factory() as session:
                # 1. Find unaccepted tasks older than threshold
                unaccepted_tasks = await self._find_unaccepted_tasks(session)
                
                # 2. Process each task
                for task in unaccepted_tasks:
                    await self._process_unaccepted_task(session, task)
                    
                await session.commit()
                
            logger.info(f"Completed processing {len(unaccepted_tasks)} unaccepted tasks")
            
        except Exception as e:
            logger.error(f"Error in cleaning task follow-up cron: {e}")
            raise
```

### Phase 2: Find Unaccepted Tasks

```python
    async def _find_unaccepted_tasks(self, session: AsyncSession) -> List[Dict]:
        """Find cleaning tasks that haven't been accepted within time window"""
        
        # Tasks created more than 4 hours ago with no response
        cutoff_time = datetime.utcnow() - timedelta(hours=4)
        
        query = text("""
            SELECT ct.id, ct.reservation_id, ct.property_id, ct.scheduled_date, 
                   ct.category_id, ct.assigned_crew_id, ct.created_at
            FROM cleaning_tasks ct
            WHERE ct.status = 'pending'
            AND ct.created_at <= :cutoff_time
            AND NOT EXISTS (
                SELECT 1 FROM task_responses tr 
                WHERE tr.task_id = ct.id::text 
                AND tr.task_type = 'cleaning'
                AND tr.response IN ('accepted', 'rejected')
            )
            ORDER BY ct.created_at ASC
            LIMIT 100
        """)
        
        result = await session.execute(query, {"cutoff_time": cutoff_time})
        tasks = [dict(row._mapping) for row in result.fetchall()]
        
        logger.info(f"Found {len(tasks)} unaccepted cleaning tasks")
        return tasks
```

### Phase 3: Process Individual Tasks

```python
    async def _process_unaccepted_task(self, session: AsyncSession, task: Dict):
        """Process a single unaccepted task"""
        
        task_id = task['id']
        logger.info(f"Processing unaccepted task {task_id}")
        
        # 1. Find next available crew member
        next_crew = await self._find_next_crew(session, task)
        
        if not next_crew:
            logger.warning(f"No available crew found for task {task_id}")
            return
            
        # 2. Send notification to next crew
        notification_sent = await self._send_notification(next_crew, task)
        
        if notification_sent:
            # 3. Update task assignment
            await self._update_task_assignment(session, task_id, next_crew['id'])
            
            # 4. Log the notification
            await self._log_notification(session, task_id, next_crew['id'])
            
            logger.info(f"Successfully notified crew {next_crew['name']} for task {task_id}")
        else:
            logger.error(f"Failed to send notification for task {task_id}")
```

### Phase 4: Find Next Available Crew

```python
    async def _find_next_crew(self, session: AsyncSession, task: Dict) -> Optional[Dict]:
        """Find the next available crew member for a task"""
        
        # Get all active crews for the property and category
        crew_service = CrewService(session)
        
        # First try: same property and category
        active_crews = await crew_service.get_active_crews(
            property_id=task['property_id']
        )
        
        # Filter by category and exclude previously assigned
        eligible_crews = [
            crew for crew in active_crews 
            if crew.get('category_id') == task['category_id'] 
            and crew['id'] != task['assigned_crew_id']
            and crew.get('active', True)
        ]
        
        if not eligible_crews:
            # Second try: same category, any property
            category_crews = await crew_service.get_single_crew_by_category(
                task['category_id']
            )
            if category_crews and category_crews['id'] != task['assigned_crew_id']:
                eligible_crews = [category_crews]
        
        # Select crew member (round-robin or least recently notified)
        if eligible_crews:
            # For now, select first available
            # TODO: Implement smart selection logic
            return eligible_crews[0]
            
        return None
```

### Phase 5: Send Notification

```python
    async def _send_notification(self, crew: Dict, task: Dict) -> bool:
        """Send email notification to crew member"""
        
        try:
            # Format task data for notification
            notification_task = {
                'id': task['id'],
                'property_id': task['property_id'],
                'scheduled_date': task['scheduled_date'].strftime('%Y-%m-%d'),
                'reservation_id': task['reservation_id']
            }
            
            # Use existing notification system
            success = self.notifier.notify_cleaning_task(
                crew=crew,
                task=notification_task,
                booking=None,  # Could enhance with booking data
                include_calendar_invite=True
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending notification to crew {crew['id']}: {e}")
            return False
```

### Phase 6: Update Task and Log

```python
    async def _update_task_assignment(self, session: AsyncSession, task_id: int, crew_id: int):
        """Update task with new crew assignment"""
        
        query = text("""
            UPDATE cleaning_tasks 
            SET assigned_crew_id = :crew_id, 
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :task_id
        """)
        
        await session.execute(query, {"task_id": task_id, "crew_id": crew_id})

    async def _log_notification(self, session: AsyncSession, task_id: int, crew_id: int):
        """Log the notification for audit purposes"""
        
        log_query = text("""
            INSERT INTO task_notifications 
            (task_id, crew_id, notification_type, sent_at)
            VALUES (:task_id, :crew_id, 'follow_up_email', CURRENT_TIMESTAMP)
        """)
        
        await session.execute(log_query, {
            "task_id": task_id,
            "crew_id": crew_id
        })
```

## 🚀 Deployment Setup

### 1. Create Cron Job Script

Create `/src/cron_jobs/run_cleaning_followup.py`:

```python
#!/usr/bin/env python3
"""
Cron job runner for cleaning task follow-up
Run every 4 hours: 0 */4 * * *
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.cron_jobs.cleaning_task_followup import CleaningTaskFollowupCron

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/cleaning_followup.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

async def main():
    """Main cron job entry point"""
    try:
        cron = CleaningTaskFollowupCron()
        await cron.run()
        logger.info("Cron job completed successfully")
        return 0
    except Exception as e:
        logger.error(f"Cron job failed: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
```

### 2. Add Cron Entry

Add to crontab:

```bash
# Run cleaning task follow-up every 4 hours
0 */4 * * * /usr/bin/python3 /path/to/project/src/cron_jobs/run_cleaning_followup.py >> /var/log/cleaning_followup_cron.log 2>&1
```

### 3. Environment Setup

Ensure these environment variables are set:

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/vacation_rentals

# API Settings  
API_BASE_URL=https://your-api-domain.com
API_PREFIX=/api
API_VERSION=v1

# Email/SMS credentials
SENDGRID_API_KEY=your_sendgrid_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
```

## 🧪 Testing Strategy

### Unit Tests

Create `/tests/test_cleaning_task_followup.py`:

```python
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

from src.cron_jobs.cleaning_task_followup import CleaningTaskFollowupCron

@pytest.fixture
def mock_session():
    """Mock database session"""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session

@pytest.fixture
def sample_task():
    """Sample unaccepted task"""
    return {
        'id': 1,
        'reservation_id': 'RES123',
        'property_id': 'PROP456',
        'scheduled_date': datetime.now() + timedelta(days=1),
        'category_id': 1,
        'assigned_crew_id': None,
        'created_at': datetime.utcnow() - timedelta(hours=5)
    }

@pytest.fixture
def sample_crew():
    """Sample crew member"""
    return {
        'id': 1,
        'name': 'John Doe',
        'email': 'john@example.com',
        'phone': '+1234567890',
        'category_id': 1,
        'active': True,
        'property_id': 'PROP456'
    }

@pytest.mark.asyncio
async def test_find_unaccepted_tasks(mock_session, sample_task):
    """Test finding unaccepted tasks"""
    cron = CleaningTaskFollowupCron()
    
    # Mock database response
    mock_result = AsyncMock()
    mock_result.fetchall.return_value = [Mock(_mapping=sample_task)]
    mock_session.execute.return_value = mock_result
    
    tasks = await cron._find_unaccepted_tasks(mock_session)
    
    assert len(tasks) == 1
    assert tasks[0]['id'] == 1
    mock_session.execute.assert_called_once()

@pytest.mark.asyncio
async def test_process_unaccepted_task(mock_session, sample_task, sample_crew):
    """Test processing individual task"""
    cron = CleaningTaskFollowupCron()
    
    # Mock dependencies
    cron._find_next_crew = AsyncMock(return_value=sample_crew)
    cron._send_notification = AsyncMock(return_value=True)
    cron._update_task_assignment = AsyncMock()
    cron._log_notification = AsyncMock()
    
    await cron._process_unaccepted_task(mock_session, sample_task)
    
    # Verify all steps were called
    cron._find_next_crew.assert_called_once()
    cron._send_notification.assert_called_once()
    cron._update_task_assignment.assert_called_once()
    cron._log_notification.assert_called_once()

@pytest.mark.asyncio
async def test_no_available_crew(mock_session, sample_task):
    """Test handling when no crew is available"""
    cron = CleaningTaskFollowupCron()
    
    # Mock no available crew
    cron._find_next_crew = AsyncMock(return_value=None)
    cron._send_notification = AsyncMock()
    
    await cron._process_unaccepted_task(mock_session, sample_task)
    
    # Verify notification was not attempted
    cron._send_notification.assert_not_called()
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_full_cron_job_flow():
    """Test complete cron job flow with real database"""
    # This test would use a test database
    # Create test data: pending tasks, active crews
    # Run cron job
    # Verify notifications sent and tasks updated
    pass

@pytest.mark.asyncio
async def test_email_template_integration():
    """Test that email templates are properly formatted"""
    from src.guest_communications.email_templates import EmailTemplates
    
    template = EmailTemplates.get_cleaning_template(
        crew_name="Test Crew",
        property_name="Test Property",
        scheduled_date="2024-01-15",
        task_id="123"
    )
    
    assert "Accept Task" in template
    assert "Reject Task" in template
    assert "Test Property" in template
    assert "2024-01-15" in template
```

### Test Data Setup

Create SQL script for test data:

```sql
-- Test data for cleaning_task_followup testing
INSERT INTO cleaning_crews (name, email, phone, category_id, active, property_id) VALUES
('John Doe', 'john@example.com', '+1234567890', 1, true, 'PROP123'),
('Jane Smith', 'jane@example.com', '+1234567891', 1, true, 'PROP123'),
('Bob Johnson', 'bob@example.com', '+1234567892', 2, true, 'PROP456');

INSERT INTO cleaning_tasks (reservation_id, property_id, scheduled_date, status, category_id, created_at) VALUES
('RES001', 'PROP123', CURRENT_DATE + 1, 'pending', 1, CURRENT_TIMESTAMP - INTERVAL '5 hours'),
('RES002', 'PROP123', CURRENT_DATE + 2, 'pending', 1, CURRENT_TIMESTAMP - INTERVAL '6 hours'),
('RES003', 'PROP456', CURRENT_DATE + 1, 'pending', 2, CURRENT_TIMESTAMP - INTERVAL '3 hours');

-- Insert some accepted/rejected tasks for testing
INSERT INTO task_responses (task_id, task_type, response, created_at) VALUES
('1', 'cleaning', 'accepted', CURRENT_TIMESTAMP - INTERVAL '2 hours'),
('2', 'cleaning', 'rejected', CURRENT_TIMESTAMP - INTERVAL '1 hour');
```

## 📊 Monitoring & Logging

### Key Metrics to Track

1. **Tasks Processed**: Number of unaccepted tasks found
2. **Notifications Sent**: Number of crew members notified
3. **Success Rate**: Percentage of successful notifications
4. **Response Rate**: How many notified crews respond
5. **Error Rate**: Failed notifications or processing errors

### Logging Configuration

```python
# Enhanced logging in cron job
logger.info("Cleaning follow-up cron started", extra={
    'cron_job': 'cleaning_task_followup',
    'timestamp': datetime.utcnow().isoformat()
})

logger.info("Processing task", extra={
    'task_id': task_id,
    'property_id': property_id,
    'scheduled_date': scheduled_date,
    'crew_id': crew_id
})

logger.error("Notification failed", extra={
    'task_id': task_id,
    'crew_id': crew_id,
    'error': str(e),
    'error_type': type(e).__name__
})
```

### Health Check Endpoint

Add monitoring endpoint to track cron job status:

```python
# Add to service_bookings.py or create new monitoring endpoint
@router.get("/cron-status")
async def get_cron_status():
    """Get status of cleaning task follow-up cron job"""
    try:
        async with psql_client.async_session_factory() as session:
            # Check last successful run
            last_run_query = text("""
                SELECT created_at, status, details
                FROM cron_job_logs 
                WHERE job_name = 'cleaning_task_followup'
                ORDER BY created_at DESC 
                LIMIT 1
            """)
            
            result = await session.execute(last_run_query)
            last_run = result.fetchone()
            
            # Check pending tasks count
            pending_count_query = text("""
                SELECT COUNT(*) as count
                FROM cleaning_tasks ct
                WHERE ct.status = 'pending'
                AND ct.created_at <= CURRENT_TIMESTAMP - INTERVAL '4 hours'
                AND NOT EXISTS (
                    SELECT 1 FROM task_responses tr 
                    WHERE tr.task_id = ct.id::text 
                    AND tr.task_type = 'cleaning'
                    AND tr.response IN ('accepted', 'rejected')
                )
            """)
            
            count_result = await session.execute(pending_count_query)
            pending_count = count_result.fetchone()[0]
            
            return {
                "success": True,
                "last_run": last_run._mapping if last_run else None,
                "pending_tasks_count": pending_count,
                "status": "healthy" if last_run and last_run.status == 'success' else "needs_attention"
            }
            
    except Exception as e:
        logger.error(f"Error getting cron status: {e}")
        return {"success": False, "error": str(e)}
```

## 🔧 Configuration Options

### Environment Variables

```bash
# Cron job configuration
CLEANING_FOLLOWUP_ENABLED=true
CLEANING_FOLLOWUP_INTERVAL_HOURS=4
CLEANING_FOLLOWUP_TASK_AGE_HOURS=4
CLEANING_FOLLOWUP_MAX_TASKS_PER_RUN=100
CLEANING_FOLLOWUP_MAX_NOTIFICATIONS_PER_TASK=3

# Notification configuration
CLEANING_NOTIFICATION_RETRY_ATTEMPTS=3
CLEANING_NOTIFICATION_RETRY_DELAY_MINUTES=30
```

### Config Class

```python
# Add to config/settings.py
class CronJobSettings:
    CLEANING_FOLLOWUP_ENABLED: bool = True
    CLEANING_FOLLOWUP_INTERVAL_HOURS: int = 4
    CLEANING_FOLLOWUP_TASK_AGE_HOURS: int = 4
    CLEANING_FOLLOWUP_MAX_TASKS_PER_RUN: int = 100
    CLEANING_FOLLOWUP_MAX_NOTIFICATIONS_PER_TASK: int = 3
    CLEANING_NOTIFICATION_RETRY_ATTEMPTS: int = 3
    CLEANING_NOTIFICATION_RETRY_DELAY_MINUTES: int = 30
```

## 🔄 Error Handling & Retry Logic

### Retry Mechanism

```python
async def _send_notification_with_retry(self, crew: Dict, task: Dict) -> bool:
    """Send notification with retry logic"""
    
    max_retries = settings.CLEANING_NOTIFICATION_RETRY_ATTEMPTS
    
    for attempt in range(max_retries):
        try:
            success = await self._send_notification(crew, task)
            if success:
                return True
                
            logger.warning(f"Notification attempt {attempt + 1} failed, retrying...")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(
                    settings.CLEANING_NOTIFICATION_RETRY_DELAY_MINUTES * 60
                )
                
        except Exception as e:
            logger.error(f"Notification attempt {attempt + 1} error: {e}")
            
    logger.error(f"All notification attempts failed for task {task['id']}")
    return False
```

### Error Categories

1. **Database Errors**: Connection issues, query failures
2. **Notification Errors**: Email/SMS service failures
3. **Configuration Errors**: Missing environment variables
4. **Data Errors**: Invalid task or crew data

## 📈 Future Enhancements

### Phase 2 Features

1. **Smart Crew Selection**
   - Implement round-robin selection
   - Consider crew workload and availability
   - Track response times and preferences

2. **Multi-channel Notifications**
   - Add WhatsApp notifications
   - Push notifications to mobile app
   - In-app notifications

3. **Advanced Scheduling**
   - Respect crew working hours
   - Handle timezone differences
   - Implement notification quiet hours

4. **Analytics Dashboard**
   - Response rate analytics
   - Crew performance metrics
   - Task completion trends

### Database Schema Extensions

```sql
-- Add crew performance tracking
ALTER TABLE cleaning_crews ADD COLUMN response_rate DECIMAL(5,2) DEFAULT 0.0;
ALTER TABLE cleaning_crews ADD COLUMN avg_response_time_minutes INTEGER DEFAULT 0;
ALTER TABLE cleaning_crews ADD COLUMN last_notification_sent TIMESTAMP;

-- Add notification preferences
CREATE TABLE crew_notification_preferences (
    id SERIAL PRIMARY KEY,
    crew_id INTEGER REFERENCES cleaning_crews(id),
    notification_type VARCHAR(50), -- 'email', 'sms', 'whatsapp'
    enabled BOOLEAN DEFAULT TRUE,
    working_hours_start TIME,
    working_hours_end TIME,
    timezone VARCHAR(50) DEFAULT 'UTC'
);
```

## 📚 References

### Code Files Referenced
- [`/src/api/routes/service_bookings.py`](file:///Users/adarshsharma/Desktop/Projects/Python/EmailParser/src/api/routes/service_bookings.py) - Accept/reject endpoints
- [`/src/api/services/crew_service.py`](file:///Users/adarshsharma/Desktop/Projects/Python/EmailParser/src/api/services/crew_service.py) - Crew retrieval logic
- [`/src/guest_communications/notifier.py`](file:///Users/adarshsharma/Desktop/Projects/Python/EmailParser/src/guest_communications/notifier.py) - Notification system
- [`/src/guest_communications/email_templates.py`](file:///Users/adarshsharma/Desktop/Projects/Python/EmailParser/src/guest_communications/email_templates.py) - Email templates

### Related Documentation
- [SQLAlchemy Async Documentation](https://docs.sqlalchemy.org/en/14/orm/extensions/asyncio.html)
- [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [PostgreSQL Date/Time Functions](https://www.postgresql.org/docs/current/functions-datetime.html)

## ✅ Implementation Checklist

### Development Phase
- [ ] Create cron job directory structure
- [ ] Implement core cron job class
- [ ] Add database query functions
- [ ] Integrate notification system
- [ ] Add error handling and logging
- [ ] Create test data and unit tests
- [ ] Test with sample data
- [ ] Code review and optimization

### Deployment Phase
- [ ] Set up production cron schedule
- [ ] Configure environment variables
- [ ] Set up monitoring and alerts
- [ ] Create database indexes for performance
- [ ] Deploy to staging environment
- [ ] Run integration tests
- [ ] Deploy to production
- [ ] Monitor initial runs

### Post-Deployment
- [ ] Monitor success rates
- [ ] Collect feedback from crew
- [ ] Optimize based on usage patterns
- [ ] Plan Phase 2 enhancements
- [ ] Document lessons learned

## 🆘 Troubleshooting

### Common Issues

1. **Cron job not running**
   - Check cron service status: `sudo service cron status`
   - Verify cron syntax: `crontab -l`
   - Check file permissions: `ls -la /path/to/cron/script`

2. **Database connection errors**
   - Verify DATABASE_URL environment variable
   - Check PostgreSQL connection limits
   - Review connection pool settings

3. **Notification failures**
   - Check SendGrid/Twilio credentials
   - Verify crew email/phone numbers
   - Review API rate limits

4. **Performance issues**
   - Add database indexes on frequently queried columns
   - Optimize query performance with EXPLAIN ANALYZE
   - Consider batching large result sets

### Debug Commands

```bash
# Check cron logs
tail -f /var/log/cron.log
tail -f /var/log/cleaning_followup.log

# Test database connection
python -c "from src.api.dependencies import get_psql_client; print(get_psql_client())"

# Test notification system
python -c "from src.guest_communications.notifier import Notifier; n = Notifier(); print('Notifier initialized')"

# Manual cron job test
cd /path/to/project && python src/cron_jobs/run_cleaning_followup.py
```

---

**Next Steps**: After implementing this cron job, consider implementing similar follow-up systems for other task types (maintenance, inspections) and adding more sophisticated crew scheduling algorithms.