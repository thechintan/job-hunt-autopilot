"""tracker.py — Build per-application tracker from classified emails.

State machine rules (§7.1):
- Group by application key (company + role).
- Sort history chronologically.
- Status priority: applied(1) < interview(2) < offer(3).
- rejected is terminal UNLESS a later-dated offer/interview arrives.
- Simple rule: iterate chronologically; applied never lowers existing status; any other label overwrites.
"""

from datetime import date
from typing import Optional
from autopilot.models import Classification, Application
from autopilot.normalize import make_application_key, normalize_company, extract_company

# Status priority (higher = more progressed)
_STATUS_RANK = {
    "applied": 1,
    "interview": 2,
    "offer": 3,
    "rejected": 0,  # Special: terminal
}

_TRACKER_LABELS = {"applied", "interview", "rejected", "offer"}


def _update_status(current: str, new_label: str, new_date: date, last_date: date) -> str:
    """
    State machine transition logic.
    - 'applied' never downgrades existing status.
    - rejected is set immediately but can be overwritten by a later interview/offer.
    - interview and offer always upgrade.
    """
    if new_label == "applied":
        # Applied never lowers status
        if current == "":
            return "applied"
        return current  # Keep whatever we have

    if new_label == "rejected":
        # Set as rejected, but only if no higher status already
        if current in ("interview", "offer"):
            return current  # Don't downgrade from interview/offer
        return "rejected"

    if new_label in ("interview", "offer"):
        # Always upgrade; can rescue from rejected if later-dated
        if new_label == "offer":
            return "offer"
        if new_label == "interview":
            if current == "offer":
                return "offer"  # Don't downgrade from offer
            return "interview"

    return current


def build_tracker(classifications: list, emails_by_id: dict) -> list:
    """
    Build list[Application] from list[Classification].
    emails_by_id: dict[email_id -> Email]
    """
    # Filter to only trackable labels
    trackable = [c for c in classifications if c.label in _TRACKER_LABELS]

    # Group by application key
    groups: dict = {}  # key -> list[Classification]
    for clf in trackable:
        company = clf.company
        role = clf.role
        key = make_application_key(company, role)
        if key not in groups:
            groups[key] = []
        groups[key].append(clf)

    applications = []
    for key, clfs in groups.items():
        # Sort by email date
        clfs_sorted = sorted(
            clfs,
            key=lambda c: emails_by_id[c.email_id].date if c.email_id in emails_by_id else date.min,
        )

        # Build history
        history = []
        for clf in clfs_sorted:
            email = emails_by_id.get(clf.email_id)
            if email:
                history.append((email.date.date(), clf.label, clf.email_id))

        # Run state machine
        status = ""
        for d, label, eid in history:
            status = _update_status(status, label, d, d)
        if not status:
            status = "applied"

        # Derive display company and role from first clf
        first_clf = clfs_sorted[0]
        company_display = first_clf.company or key.split("|")[0].title()
        role_display = first_clf.role

        # If multiple clfs, prefer a non-None role
        for clf in clfs_sorted:
            if clf.role:
                role_display = clf.role
                break

        first_seen = history[0][0] if history else date.today()
        last_activity = history[-1][0] if history else date.today()

        applications.append(
            Application(
                key=key,
                company=company_display,
                role=role_display,
                status=status,
                first_seen=first_seen,
                last_activity=last_activity,
                history=history,
                needs_followup=False,  # Set by followups.py
                days_silent=0,         # Set by followups.py
            )
        )

    return applications
