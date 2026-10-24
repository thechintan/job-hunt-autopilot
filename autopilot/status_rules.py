"""status_rules.py — Rule-based email status classifier.

Priority order (highest first): offer → interview → rejected → applied → other
Returns (label, [reasons])
"""

import re
from typing import Optional

# --- Patterns ---

_OFFER_PATTERNS = [
    r"offer\s+letter",
    r"pleased\s+to\s+offer",
    r"delighted\s+to\s+(?:extend|offer)",
    r"extend\s+an\s+offer",
    r"we\s+are\s+happy\s+to\s+offer",
    r"compensation\s+(?:details|package)",
    r"acceptan?ce?\s+(?:of\s+)?(?:the\s+)?offer",
]

_INTERVIEW_PATTERNS = [
    r"interview\s+(?:invit|schedul|slot|round)",
    r"invite\s+you\s+(?:for|to)\s+(?:an?\s+)?(?:\w+\s+)?interview",
    r"schedule\s+(?:a|an)\s+(?:video\s+)?(?:call|interview)",
    r"next\s+(?:round|steps)",
    r"technical\s+(?:round|interview|assessment)",
    r"availability\s+for",
    # "shortlisted" only fires if paired with an action word (invite, schedule, meet, call, round)
    r"shortlisted.*(?:interview|meet|call|round|schedule|invite|slot)",
    r"(?:interview|meet|call|round|schedule|invite|slot).*shortlisted",
    r"invite\s+you\s+to\s+(?:a\s+)?(?:first[- ]round\s+)?interview",
    r"would\s+like\s+to\s+invite\s+you",
    r"move\s+(?:you\s+)?to\s+the\s+next\s+(?:round|stage|step)",
]

_REJECTED_PATTERNS = [
    r"regret\s+to\s+inform",
    r"not\s+(?:be\s+)?moving\s+forward",
    r"will\s+not\s+be\s+moving\s+forward",
    r"move\s+forward\s+with\s+other\s+candidates",
    r"not\s+selected",
    r"decided\s+not\s+to\s+proceed",
    r"position\s+has\s+been\s+filled",
]

# "unfortunately" alone is a weak signal — guard with application context
_UNFORTUNATELY_RE = re.compile(r"unfortunately", re.IGNORECASE)
_UNFORTUNATELY_CONTEXT_RE = re.compile(
    r"application|candidacy|position|role|candidate|moving\s+forward|proceed",
    re.IGNORECASE,
)

_APPLIED_PATTERNS = [
    r"application\s+(?:has\s+been\s+)?(?:received|submitted)",
    r"received\s+your\s+application",
    r"thank(?:s|\s+you)\s+for\s+applying",
    r"thank\s+you\s+for\s+your\s+interest",
    r"we\s+acknowledge\s+receipt",
    r"successfully\s+(?:applied|submitted)",
]

# Guard: these sender patterns → other (unless already flagged scam)
_OTHER_GUARD_RE = re.compile(
    r"noreply|no-reply|jobalerts|job[-\s]?alerts|unsubscribe|new\s+jobs\s+for",
    re.IGNORECASE,
)


def _compile_patterns(patterns: list) -> list:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


_OFFER_RE = _compile_patterns(_OFFER_PATTERNS)
_INTERVIEW_RE = _compile_patterns(_INTERVIEW_PATTERNS)
_REJECTED_RE = _compile_patterns(_REJECTED_PATTERNS)
_APPLIED_RE = _compile_patterns(_APPLIED_PATTERNS)


def _match_any(patterns: list, text: str) -> Optional[str]:
    """Return the first matched string from the text, or None."""
    for pattern in patterns:
        m = pattern.search(text)
        if m:
            return m.group(0)
    return None


def classify_status(subject: str, body: str, from_email: str) -> tuple:
    """
    Classify email status using rules.
    Returns (label: str, reasons: list[str])
    """
    text = (subject + " " + body).strip()

    # Guard: newsletter / job alert → other
    if _OTHER_GUARD_RE.search(from_email + " " + subject):
        return "other", ["Sender/subject matches newsletter or job-alert pattern"]

    # Offer
    matched = _match_any(_OFFER_RE, text)
    if matched:
        return "offer", [f'Matched "{matched}"']

    # Interview
    matched = _match_any(_INTERVIEW_RE, text)
    if matched:
        return "interview", [f'Matched "{matched}"']

    # Rejected (multi-pattern)
    matched = _match_any(_REJECTED_RE, text)
    if matched:
        return "rejected", [f'Matched "{matched}"']

    # "unfortunately" guarded
    if _UNFORTUNATELY_RE.search(text) and _UNFORTUNATELY_CONTEXT_RE.search(text):
        return "rejected", ['Matched "unfortunately" + application context']

    # Applied
    matched = _match_any(_APPLIED_RE, text)
    if matched:
        return "applied", [f'Matched "{matched}"']

    return "other", ["No status keyword matched"]
