"""normalize.py — Clean email text, extract sender domain, company, and role."""

import re
from typing import Optional
from autopilot.models import Email

# Words to strip from display name to get company name
_DISPLAY_NAME_SUFFIX_WORDS = {
    "careers", "hr", "talent", "hiring", "recruiting", "recruiter",
    "team", "department", "recruitment", "jobs", "staffing", "people",
    "executive",
}

# Legal suffixes to strip when normalizing company keys
_LEGAL_SUFFIXES = re.compile(
    r"\b(pvt\.?\s*ltd\.?|private\s+limited|inc\.?|llc\.?|ltd\.?|co\.?|corp\.?|limited)\b",
    re.IGNORECASE,
)

# Regex to find "at <Company>" in subject or body
_AT_COMPANY_RE = re.compile(r"\bat\s+([A-Z][A-Za-z0-9&\s\-]{1,40}?)(?=\s+(?:for|and|\.|\,|$)|\s*$)", re.MULTILINE)

# Role extraction patterns
_ROLE_COLON_RE = re.compile(
    r"(?:application\s+received|invitation|invite|interview|update\s+on\s+your\s+application)\s*[:\-–]\s*(.+?)(?:\s+at\s+|\s*$)",
    re.IGNORECASE,
)
_ROLE_FOR_AS_RE = re.compile(
    r"(?:for|as)\s+(?:the\s+|an?\s+)?(.+?)\s+(?:position|role|post|job)\b",
    re.IGNORECASE,
)
_ROLE_SUBJECT_TAIL_RE = re.compile(
    r"[:\-–]\s*([A-Z][A-Za-z\s&\-]{2,50}?)(?:\s+at\s+|\s*$)",
    re.MULTILINE,
)


def _clean_company_name(name: str) -> str:
    """Strip suffix words from a display name to extract company name."""
    parts = name.split()
    filtered = [p for p in parts if p.lower() not in _DISPLAY_NAME_SUFFIX_WORDS]
    if not filtered:
        filtered = parts  # Don't remove everything
    return " ".join(filtered).strip()


def normalize_company(name: str) -> str:
    """Normalize a company name for use as a tracker key (lowercase, strip punctuation/legal)."""
    name = _LEGAL_SUFFIXES.sub("", name)
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip().lower()
    return name


def _domain_root_to_company(domain: str) -> str:
    """Turn a domain root (e.g. 'zenithtech' from 'zenithtech.io') into a display name."""
    root = domain.split(".")[0]
    # Split on camelCase or hyphens
    root = re.sub(r"([a-z])([A-Z])", r"\1 \2", root)
    root = root.replace("-", " ").replace("_", " ")
    return root.title()


def extract_company(email: "Email") -> Optional[str]:
    """Extract company name from email. Returns display name (not normalized key)."""
    # 1. Try stripping suffix words from display name
    if email.from_name:
        cleaned = _clean_company_name(email.from_name)
        if cleaned and len(cleaned) > 1:
            return cleaned

    # 2. Try "at <Company>" regex in subject
    combined = email.subject + " " + email.body[:500]
    m = _AT_COMPANY_RE.search(combined)
    if m:
        candidate = m.group(1).strip().rstrip(".,;")
        if len(candidate) > 1:
            return candidate

    # 3. Fallback: domain root
    if email.sender_domain:
        return _domain_root_to_company(email.sender_domain)

    return None


def extract_role(email: "Email") -> Optional[str]:
    """Extract job role from email subject and body."""
    # 1. Pattern: "Application received: <Role>" or "invite: <Role>"
    m = _ROLE_COLON_RE.search(email.subject)
    if m:
        role = m.group(1).strip().rstrip(".,;-")
        if role:
            return role

    # 2. Pattern: tail after colon/dash in subject
    m = _ROLE_SUBJECT_TAIL_RE.search(email.subject)
    if m:
        role = m.group(1).strip().rstrip(".,;-")
        if role and len(role) > 2:
            return role

    # 3. Pattern: "for/as the <Role> position/role"
    combined = email.subject + " " + email.body[:1000]
    m = _ROLE_FOR_AS_RE.search(combined)
    if m:
        role = m.group(1).strip().rstrip(".,;-")
        if role and len(role) > 2:
            return role

    return None


def make_application_key(company: Optional[str], role: Optional[str]) -> str:
    """Create a normalized key for grouping emails into applications."""
    norm_company = normalize_company(company) if company else "unknown"
    if role:
        norm_role = re.sub(r"\s+", " ", role.lower().strip())
        norm_role = re.sub(r"[^\w\s]", "", norm_role).strip()
        return f"{norm_company}|{norm_role}"
    return norm_company


def normalize_email(email: "Email") -> "Email":
    """Return the email unchanged (domain already set in ingest). Kept for pipeline symmetry."""
    return email
