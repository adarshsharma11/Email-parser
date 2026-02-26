from fastapi import APIRouter, Query, Request, Depends, HTTPException
from typing import Optional, List, Dict, Any
from ..dependencies import get_user_service
from ...email_reader.gmail_client import GmailClient
from ...utils.models import Platform, EmailData
import email.utils as eutils
import asyncio

router = APIRouter(tags=["emails"])


def _serialize_email(e: EmailData) -> Dict[str, Any]:
    return {
        "email_id": e.email_id,
        "subject": e.subject,
        "sender": e.sender,
        "date": e.date.isoformat(),
        "body_text": e.body_text,
        "body_html": e.body_html,
        "platform": e.platform.value if e.platform else None,
        "folder": getattr(e, "folder", "INBOX"),
    }


@router.get("/emails/inbox")
async def list_inbox(
    request: Request,
    platform: Optional[str] = Query(default=None),
    since_days: Optional[int] = Query(default=None),
    limit: Optional[int] = Query(default=50),
    folder: Optional[str] = Query(default="INBOX"),
    q: Optional[str] = Query(default=None),
    only_booking: bool = Query(default=True),
    user_service = Depends(get_user_service),
) -> List[Dict[str, Any]]:
    user_email, password = await _get_credentials(request, user_service)
    if not user_email or not password:
        return []

    client = GmailClient()
    if not client.connect_with_credentials(user_email, password):
        return []

    plat_enum = None
    if platform:
        try:
            plat_enum = Platform(platform.lower())
        except Exception:
            plat_enum = None
    target_folder = (folder or "INBOX").upper()
    emails = client.fetch_emails(
        platform=plat_enum,
        since_days=since_days,
        limit=limit,
        mailbox=target_folder,
        text_query=q,
        only_booking=only_booking,
    )
    client.disconnect()
    return [_serialize_email(e) for e in emails]


@router.get("/emails/sent")
async def list_sent(
    request: Request,
    since_days: Optional[int] = Query(default=None),
    limit: Optional[int] = Query(default=50),
    q: Optional[str] = Query(default=None),
    user_service = Depends(get_user_service),
) -> List[Dict[str, Any]]:
    """
    Fetch emails from SENT folder without platform filtering (all sent emails).
    """
    user_email, password = await _get_credentials(request, user_service)
    if not user_email or not password:
        return []

    client = GmailClient()
    if not client.connect_with_credentials(user_email, password):
        return []

    emails = client.fetch_emails(
        platform=None,
        since_days=since_days,
        limit=limit,
        mailbox="SENT",
        text_query=q,
        only_booking=False,
    )
    client.disconnect()
    return [_serialize_email(e) for e in emails]


async def _get_credentials(request: Request, user_service):
    """Helper to get credentials from request state or fallback to env."""
    user_email = getattr(request.state, "user_email", None)
    password = None
    
    if user_email:
        user = await user_service.get_user(user_email)
        if user and user.get("password"):
            try:
                password = user_service.decrypt(user.get("password", ""))
            except Exception:
                password = None
                
    if not user_email or not password:
        # Try active credentials from user_credentials table first
        users = await user_service.list_active_users()
        if not users:
            # Fallback to all users if no active ones
            users = await user_service.list_users()
            
        first = users[0] if users else None
        if first and first.get("email") and first.get("password"):
            try:
                password = user_service.decrypt(first.get("password", ""))
                user_email = first.get("email")
            except Exception:
                password = None
        if not user_email or not password:
            from config.settings import gmail_config
            if gmail_config.email and gmail_config.password:
                user_email = gmail_config.email
                password = gmail_config.password
            
    return user_email, password


@router.get("/emails/{email_id}")
async def get_email(
    request: Request, 
    email_id: str, 
    folder: Optional[str] = Query(default="INBOX"),
    user_service = Depends(get_user_service)
) -> Dict[str, Any]:
    user_email, password = await _get_credentials(request, user_service)
    if not user_email or not password:
        return {}

    client = GmailClient()
    if not client.connect_with_credentials(user_email, password):
        return {}
    target_folder = (folder or "INBOX").upper()
    e = client.fetch_email(email_id, mailbox=target_folder)
    client.disconnect()
    return _serialize_email(e) if e else {}


@router.post("/emails/{email_id}/reply")
async def reply_email(
    request: Request,
    email_id: str,
    body_text: str,
    body_html: Optional[str] = None,
    subject: Optional[str] = None,
    user_service = Depends(get_user_service)
) -> Dict[str, Any]:
    user_email, password = await _get_credentials(request, user_service)
    if not user_email or not password:
        return {"success": False}

    client = GmailClient()
    if not client.connect_with_credentials(user_email, password):
        return {"success": False}
    original = client.fetch_email(email_id)
    if not original:
        client.disconnect()
        return {"success": False, "message": "Original email not found"}
    _, to_addr = eutils.parseaddr(original.sender)
    if not to_addr:
        to_addr = original.sender
    sub = subject or f"Re: {original.subject}"
    ok = client.reply_to_email(email_id, to_addr, sub, body_text, body_html)
    client.disconnect()
    return {"success": ok}
