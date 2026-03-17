from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from typing import Optional
from sqlalchemy import text
from ..dependencies import psql_client, get_logger
import logging
import asyncio
import json
from datetime import datetime
import time

router = APIRouter(prefix="/service-bookings", tags=["service-bookings"])
logger = logging.getLogger(__name__)

@router.get("/respond")
async def respond_to_task(
    task_id: str = Query(..., description="Task ID"),
    type: str = Query(..., description="Task type (cleaning or service)"),
    action: str = Query(..., description="Action (accept or reject)"),
    expires_at: Optional[int] = Query(None, description="Expiration timestamp")
):
    """
    Handle task response from crew or service provider.
    """
    try:
        # Check if the link has expired
        if expires_at and int(time.time()) > expires_at:
            raise HTTPException(
                status_code=410, 
                detail="This link has expired. Please contact management for a new assignment."
            )

        if action not in ["accept", "reject"]:
            raise HTTPException(status_code=400, detail="Invalid action")
        
        status = "accepted" if action == "accept" else "rejected"
        
        async with psql_client.async_session_factory() as session:
            # 1. Update the task status and verify it exists
            rows_updated = 0
            if type == "cleaning":
                # Check if id is numeric
                try:
                    task_id_int = int(task_id)
                    update_query = text("UPDATE cleaning_tasks SET status = :status WHERE id = :id RETURNING id")
                    res = await session.execute(update_query, {"status": status, "id": task_id_int})
                    rows_updated = len(res.fetchall())
                except ValueError:
                    # Fallback to reservation_id if task_id is not a direct id
                    update_query = text("UPDATE cleaning_tasks SET status = :status WHERE reservation_id = :id RETURNING id")
                    res = await session.execute(update_query, {"status": status, "id": task_id})
                    rows_updated = len(res.fetchall())
            elif type == "service":
                try:
                    task_id_int = int(task_id)
                    update_query = text("UPDATE booking_service SET status = :status WHERE id = :id RETURNING id")
                    res = await session.execute(update_query, {"status": status, "id": task_id_int})
                    rows_updated = len(res.fetchall())
                except ValueError:
                    # Fallback to booking_id if task_id is not a direct id
                    update_query = text("UPDATE booking_service SET status = :status WHERE booking_id = :id RETURNING id")
                    res = await session.execute(update_query, {"status": status, "id": task_id})
                    rows_updated = len(res.fetchall())
            
            if rows_updated == 0:
                raise HTTPException(status_code=404, detail=f"Task with ID {task_id} not found in {type} tasks")
            
            # 2. Log the response in task_responses
            log_query = text("""
                INSERT INTO task_responses (task_id, task_type, response)
                VALUES (:task_id, :task_type, :response)
            """)
            await session.execute(log_query, {
                "task_id": task_id,
                "task_type": type,
                "response": status
            })
            
            await session.commit()
            
        return {
            "success": True,
            "message": f"Task {status} successfully",
            "task_id": task_id,
            "status": status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error responding to task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_tasks_status():
    """
    Get the current status of all assigned tasks (cleaning and services).
    Used for the Provider Response Tracker.
    """
    try:
        async with psql_client.async_session_factory() as session:
            # 1. Fetch cleaning tasks
            cleaning_query = text("""
                SELECT id, reservation_id, property_id, scheduled_date, status, created_at, 'cleaning' as task_type 
                FROM cleaning_tasks 
                ORDER BY created_at DESC 
                LIMIT 50
            """)
            cleaning_res = await session.execute(cleaning_query)
            cleaning_tasks = [dict(row._mapping) for row in cleaning_res.fetchall()]
            
            # 2. Fetch service tasks (booking_service)
            # Join with service_category to get the name
            service_query = text("""
                SELECT bs.id, bs.booking_id as reservation_id, sc.category_name as service_name, 
                       bs.service_date, bs.time, bs.status, bs.created_at, 'service' as task_type
                FROM booking_service bs
                LEFT JOIN service_category sc ON bs.service_id = sc.id
                ORDER BY bs.created_at DESC
                LIMIT 50
            """)
            service_res = await session.execute(service_query)
            service_tasks = [dict(row._mapping) for row in service_res.fetchall()]
            
            # Combine and format
            all_tasks = cleaning_tasks + service_tasks
            # Sort combined list by created_at desc
            all_tasks.sort(key=lambda x: x['created_at'], reverse=True)
            
            # Serialize datetimes
            for t in all_tasks:
                for key, val in t.items():
                    if isinstance(val, (datetime, datetime.date, datetime.time)):
                        t[key] = val.isoformat()
            
            return {
                "success": True,
                "data": all_tasks
            }
    except Exception as e:
        logger.error(f"Error fetching tasks status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/responses")
async def get_response_logs(limit: int = Query(20, le=100)):
    """
    Get the history of accept/reject logs with detailed task and responder information.
    """
    try:
        async with psql_client.async_session_factory() as session:
            # Query task_responses and join with either cleaning_tasks/crews or booking_service/service_category
            query = text("""
                SELECT 
                    tr.id, tr.created_at, tr.task_id, tr.task_type, tr.response,
                    CASE 
                        WHEN tr.task_type = 'cleaning' THEN ct.property_id 
                        ELSE sc.category_name 
                    END as task_name,
                    CASE 
                        WHEN tr.task_type = 'cleaning' THEN cc.name 
                        ELSE sc.category_name 
                    END as person_name,
                    CASE 
                        WHEN tr.task_type = 'cleaning' THEN ct.scheduled_date::text
                        ELSE (bs.service_date::text || ' ' || bs.time::text)
                    END as task_date_time
                FROM task_responses tr
                LEFT JOIN cleaning_tasks ct ON tr.task_type = 'cleaning' AND (tr.task_id = ct.id::text OR tr.task_id = ct.reservation_id)
                LEFT JOIN cleaning_crews cc ON ct.crew_id = cc.id
                LEFT JOIN booking_service bs ON tr.task_type = 'service' AND (tr.task_id = bs.id::text OR tr.task_id = bs.booking_id::text)
                LEFT JOIN service_category sc ON bs.service_id = sc.id
                ORDER BY tr.created_at DESC 
                LIMIT :limit
            """)
            result = await session.execute(query, {"limit": limit})
            logs = [dict(row._mapping) for row in result.fetchall()]
            
            # Serialize datetimes
            for log in logs:
                if 'created_at' in log and isinstance(log['created_at'], datetime):
                    log['created_at'] = log['created_at'].isoformat()
                    
            return {
                "success": True,
                "data": logs
            }
    except Exception as e:
        logger.error(f"Error fetching response logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/responses/stream")
async def stream_task_responses():
    """
    Stream real-time task responses using Server-Sent Events (SSE).
    """
    async def event_generator():
        last_id = 0
        while True:
            try:
                async with psql_client.async_session_factory() as session:
                    query = text("SELECT * FROM task_responses WHERE id > :last_id ORDER BY id ASC")
                    result = await session.execute(query, {"last_id": last_id})
                    rows = result.fetchall()
                    
                    for row in rows:
                        data = dict(row._mapping)
                        last_id = data['id']
                        
                        # Serialize datetime to string
                        if 'created_at' in data and isinstance(data['created_at'], datetime):
                            data['created_at'] = data['created_at'].isoformat()
                            
                        yield f"data: {json.dumps(data)}\n\n"
                        
                await asyncio.sleep(2) # Poll every 2 seconds
            except Exception as e:
                logger.error(f"Error in task response stream: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                await asyncio.sleep(5)
                
    return StreamingResponse(event_generator(), media_type="text/event-stream")
