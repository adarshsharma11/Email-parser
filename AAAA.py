#!/usr/bin/env python3
"""
gmail_probe.py — quick tester with keyword CONTEXT
- Edit SEARCH_KEYWORD / SEARCH_FROM / LIMIT below.
- Uses your existing GmailClient, which reads creds from config.settings (.env).
- Prints From/Subject/Date and up to a few snippets around each match.
"""

import re
from pathlib import Path

# --- EDIT THESE ---
SEARCH_KEYWORD = "booking"   # word or phrase to find (case-insensitive)
SEARCH_FROM    = ""          # e.g. "booking.com" or "sender@domain.com" ; "" = any sender
LIMIT          = 5           # how many emails to print
SNIPPET_CHARS  = 90          # characters before/after each match to show
MAX_HITS_PER_EMAIL = 3       # max snippets per email
# ------------------

# force-load .env from project root so config.settings picks it up reliably
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parents[0] / ".env"
    # If your .env is at project root (one level up), switch to parents[1]
    if not env_path.exists():
        env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(dotenv_path=env_path, override=False)
except Exception:
    pass  # it's fine; config.settings also calls load_dotenv()


def strip_html(html: str) -> str:
    """Very light HTML to text (enough for snippet searching)."""
    if not html:
        return ""
    # Remove scripts/styles
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    # Replace breaks and paragraphs with newlines
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</p>", "\n", html)
    # Drop all other tags
    html = re.sub(r"(?s)<.*?>", " ", html)
    # Collapse whitespace
    return re.sub(r"\s+", " ", html).strip()


def extract_contexts(text: str, needle: str, window: int = 90, max_hits: int = 3):
    """
    Return up to `max_hits` snippets like: '... <context-before> [MATCH] <context-after> ...'
    Case-insensitive. Shows `window` chars on each side.
    """
    if not text or not needle:
        return []
    snippets = []
    pattern = re.compile(re.escape(needle), flags=re.IGNORECASE)
    for m in pattern.finditer(text):
        start = max(0, m.start() - window)
        end   = min(len(text), m.end() + window)
        left  = text[start:m.start()].strip()
        match = text[m.start():m.end()]
        right = text[m.end():end].strip()
        snippet = f"... {left} \x1b[1m{match}\x1b[0m {right} ..."
        # remove excessive whitespace
        snippet = re.sub(r"\s+", " ", snippet)
        snippets.append(snippet)
        if len(snippets) >= max_hits:
            break
    return snippets


def compact_line(s: str, limit: int = 220) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return (s[:limit] + "…") if len(s) > limit else s


def main():
    # Import your client + config
    try:
        from src.email_reader.gmail_client import GmailClient
        from config.settings import gmail_config
    except Exception as e:
        print(f"❌ Import error: {e}")
        print("Check your import paths. If your project layout differs, adjust the imports.")
        return

    # Show which account we're using
    print(f"Using Gmail: {gmail_config.email or '<EMPTY>'}")

    client = GmailClient()
    if not client.connect():
        print("❌ Failed to connect. Verify your .env (GMAIL_EMAIL / GMAIL_PASSWORD) and IMAP app password (no spaces).")
        return

    try:
        # IMAP search using FROM/TEXT so we can control sender & keyword
        client.connection.select("INBOX")
        criteria = []
        if SEARCH_FROM:
            criteria += ["FROM", f'"{SEARCH_FROM}"']
        if SEARCH_KEYWORD:
            criteria += ["TEXT", f'"{SEARCH_KEYWORD}"']
        search_query = " ".join(criteria) if criteria else "ALL"

        status, data = client.connection.search(None, search_query)
        if status != "OK":
            print(f"❌ Search failed: {status} {data}")
            return

        ids = list(reversed(data[0].split()))[:LIMIT]
        if not ids:
            print(f"No matches for query: {search_query}")
            return

        print(f"✅ Found {len(ids)} messages for query: {search_query}\n")

        for i, eid in enumerate(ids, 1):
            eid_str = eid.decode() if isinstance(eid, (bytes, bytearray)) else str(eid)
            ed = client.fetch_email(eid_str)
            if not ed:
                print(f"[{i}] (failed to fetch id={eid_str})")
                continue

            # Assemble a searchable body
            body_text = ed.body_text or ""
            if not body_text and ed.body_html:
                body_text = strip_html(ed.body_html)

            contexts = extract_contexts(body_text, SEARCH_KEYWORD, window=SNIPPET_CHARS, max_hits=MAX_HITS_PER_EMAIL)

            print("-" * 80)
            print(f"[{i}] From:    {compact_line(ed.sender)}")
            print(f"     Subject: {compact_line(ed.subject)}")
            print(f"     Date:    {ed.date}")
            if contexts:
                print(f"     Matches ({len(contexts)}):")
                for j, snip in enumerate(contexts, 1):
                    # strip ANSI if your terminal doesn't support bold:
                    # snip = snip.replace("\x1b[1m", "").replace("\x1b[0m", "")
                    print(f"       {j}. {snip}")
            else:
                # fallback: short snippet of the body
                print(f"     Snippet: {compact_line(body_text)}")

    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
