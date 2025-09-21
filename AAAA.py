#!/usr/bin/env python3
"""
gmail_firebase_probe.py — Quick Gmail → Firestore test

- Connects to Gmail using GmailClient (config/.env)
- Prints a few recent emails with keyword context windows
- Writes up to 50 emails into Firestore (collection "Alon-test")
"""

import re
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

# === CONFIG ===
SEARCH_KEYWORD = "booking"   # word to highlight in console output
SEARCH_FROM    = ""          # e.g. "booking.com"; "" = any sender
PRINT_LIMIT    = 5           # how many to show in console
FIRESTORE_LIMIT = 50         # how many to write to Firestore
SNIPPET_CHARS  = 90
MAX_HITS_PER_EMAIL = 3
# ==============

# Load .env explicitly
env_path = Path(__file__).resolve().parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=env_path, override=False)


def strip_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", html)
    html = re.sub(r"(?i)<br\\s*/?>", "\n", html)
    html = re.sub(r"(?i)</p>", "\n", html)
    html = re.sub(r"(?s)<.*?>", " ", html)
    return re.sub(r"\\s+", " ", html).strip()


def compact(s: str, limit: int = 240) -> str:
    s = re.sub(r"\\s+", " ", (s or "").strip())
    return (s[:limit] + "…") if len(s) > limit else s


def highlight_matches(text: str, keyword: str, window: int, max_hits: int):
    if not text or not keyword:
        return []
    out, pat = [], re.compile(re.escape(keyword), re.IGNORECASE)
    for m in pat.finditer(text):
        start, end = max(0, m.start() - window), min(len(text), m.end() + window)
        left, mid, right = text[start:m.start()].strip(), m.group(), text[m.end():end].strip()
        out.append(f"... {left} \x1b[1m{mid}\x1b[0m {right} ...")
        if len(out) >= max_hits:
            break
    return out


def write_bulk_emails(client: Any, max_total: int):
    """Dump up to max_total emails into Firestore collection 'Alon-test'."""
    from firebase_admin import credentials, firestore, initialize_app, get_app
    from config.settings import firebase_config

    # Init Firestore
    cred_dict = firebase_config.get_credentials_dict()
    try:
        app = get_app()
    except Exception:
        app = initialize_app(credentials.Certificate(cred_dict))
    db = firestore.client()

    client.connection.select("INBOX")
    status, data = client.connection.search(None, "ALL")
    if status != "OK":
        print(f"❌ Bulk search failed: {status} {data}")
        return

    ids = list(reversed(data[0].split()))[:max_total]
    print(f"Writing {len(ids)} emails → Firestore 'Alon-test'")

    for eid in ids:
        eid_str = eid.decode() if isinstance(eid, (bytes, bytearray)) else str(eid)
        ed = client.fetch_email(eid_str)
        if not ed:
            continue

        body = ed.body_text or strip_html(ed.body_html) or ""
        doc = {
            "subject": ed.subject,
            "sender": ed.sender,
            "date": ed.date,
            "snippet": compact(body, 300),
            "updated_at": firestore.SERVER_TIMESTAMP,
        }

        db.collection("Alon-test").document(eid_str).set(doc, merge=True)

    print("✅ Bulk write done")


def main():
    from src.email_reader.gmail_client import GmailClient
    from config.settings import gmail_config

    print(f"Using Gmail: {gmail_config.email or '<EMPTY>'}")
    client = GmailClient()
    if not client.connect():
        print("❌ Failed to connect. Check .env and app password (no spaces).")
        return

    try:
        # Console print of a few emails
        client.connection.select("INBOX")
        criteria = []
        if SEARCH_FROM:
            criteria += ["FROM", f'"{SEARCH_FROM}"']
        if SEARCH_KEYWORD:
            criteria += ["TEXT", f'"{SEARCH_KEYWORD}"']
        search_query = " ".join(criteria) if criteria else "ALL"

        status, data = client.connection.search(None, search_query)
        if status == "OK":
            ids = list(reversed(data[0].split()))[:PRINT_LIMIT]
            print(f"\n✅ Showing {len(ids)} messages for query → {search_query}\n")
            for idx, eid in enumerate(ids, 1):
                eid_str = eid.decode() if isinstance(eid, (bytes, bytearray)) else str(eid)
                ed = client.fetch_email(eid_str)
                if not ed:
                    continue
                body = ed.body_text or strip_html(ed.body_html) or ""
                windows = highlight_matches(body, SEARCH_KEYWORD, SNIPPET_CHARS, MAX_HITS_PER_EMAIL)
                print("─" * 72)
                print(f"From:    {compact(ed.sender)}")
                print(f"Subject: {compact(ed.subject)}")
                print(f"Date:    {ed.date}\n")
                for j, w in enumerate(windows or [compact(body)], 1):
                    print(f"[{j}] {w}")
            print("─" * 72)

        # Bulk write to Firestore
        write_bulk_emails(client, FIRESTORE_LIMIT)

    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
