"""ingest.py — Load emails from JSON or .mbox files."""

import json
import mailbox
import email as email_lib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Union
from dateutil import parser as dateparser

from autopilot.models import Email


def _extract_domain(email_addr: str) -> str:
    """Extract domain from email address."""
    if "@" in email_addr:
        return email_addr.split("@", 1)[1].lower().strip()
    return ""


def _strip_html(html: str) -> str:
    """Strip HTML tags and unescape entities."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_date(date_str: str) -> datetime:
    """Parse a date string into a tz-aware datetime. Falls back to UTC now."""
    if not date_str:
        return datetime.now(timezone.utc)
    try:
        dt = dateparser.parse(date_str)
        if dt is None:
            return datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def _dict_to_email(d: dict) -> Email:
    """Convert a raw dict to an Email dataclass."""
    from_email = str(d.get("from_email", ""))
    date_val = d.get("date", "")
    if isinstance(date_val, datetime):
        dt = date_val
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = _parse_date(str(date_val))

    return Email(
        id=str(d.get("id", "")),
        from_name=str(d.get("from_name", "")),
        from_email=from_email,
        sender_domain=_extract_domain(from_email),
        to=str(d.get("to", "")),
        subject=str(d.get("subject", "")),
        date=dt,
        body=str(d.get("body", "")),
    )


def load_json(path: Union[str, Path]) -> list:
    """Load emails from a JSON file. Returns list[Email]."""
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list at top level, got {type(data)}")
    return [_dict_to_email(item) for item in data]


def load_json_dicts(dicts: list) -> list:
    """Load emails from a list of dicts (e.g. from session_state). Returns list[Email]."""
    return [_dict_to_email(item) for item in dicts]


def load_mbox(path: Union[str, Path]) -> list:
    """Load emails from an .mbox file. Returns list[Email]."""
    path = Path(path)
    mbox = mailbox.mbox(str(path))
    emails = []
    for i, msg in enumerate(mbox):
        email_id = f"mbox_{i:04d}"
        from_raw = msg.get("From", "")
        # Parse "Display Name <addr>" format
        from_name = ""
        from_email = ""
        if "<" in from_raw and ">" in from_raw:
            m = re.match(r"^(.*?)\s*<([^>]+)>", from_raw.strip())
            if m:
                from_name = m.group(1).strip().strip('"')
                from_email = m.group(2).strip()
        else:
            from_email = from_raw.strip()

        to = msg.get("To", "")
        subject = msg.get("Subject", "")
        date_raw = msg.get("Date", "")
        dt = _parse_date(date_raw)

        # Extract body
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    try:
                        body = part.get_payload(decode=True).decode(
                            part.get_content_charset() or "utf-8", errors="replace"
                        )
                    except Exception:
                        body = str(part.get_payload())
                    break
            # Fallback to HTML if no plain text
            if not body:
                for part in msg.walk():
                    ct = part.get_content_type()
                    if ct == "text/html":
                        try:
                            html = part.get_payload(decode=True).decode(
                                part.get_content_charset() or "utf-8", errors="replace"
                            )
                            body = _strip_html(html)
                        except Exception:
                            body = str(part.get_payload())
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                try:
                    body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    body = str(payload)
            if msg.get_content_type() == "text/html":
                body = _strip_html(body)

        emails.append(
            Email(
                id=email_id,
                from_name=from_name,
                from_email=from_email,
                sender_domain=_extract_domain(from_email),
                to=str(to),
                subject=str(subject),
                date=dt,
                body=body.strip(),
            )
        )
    return emails
