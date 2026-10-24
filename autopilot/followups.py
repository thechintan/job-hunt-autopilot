"""followups.py — Compute follow-up reminders for silent applications."""

from datetime import date
from typing import Optional
from autopilot.models import Application, FollowUp

FOLLOWUP_DAYS = 7


def _draft_followup(company: str, role: Optional[str], applied_on: date) -> str:
    role_str = role if role else "the open position"
    applied_str = applied_on.strftime("%B %d, %Y")
    return (
        f"Subject: Following up on my application — {role_str}\n\n"
        f"Hi {company} team,\n\n"
        f"I applied for the {role_str} position on {applied_str} and wanted to "
        f"check on the status of my application.\n"
        f"I'm very interested in the role and happy to share anything else you need.\n\n"
        f"Thanks for your time,\n"
        f"<Your name>"
    )


def due_followups(applications: list, today: date) -> list:
    """
    Compute follow-ups for applications that are still at 'applied' with ≥7 days silence.
    Mutates each Application to set needs_followup and days_silent.
    Returns list[FollowUp] sorted by days_silent desc.
    """
    followups = []
    for app in applications:
        days_silent = (today - app.last_activity).days
        app.days_silent = days_silent

        if app.status == "applied" and days_silent >= FOLLOWUP_DAYS:
            app.needs_followup = True
            draft = _draft_followup(app.company, app.role, app.first_seen)
            followups.append(
                FollowUp(
                    application_key=app.key,
                    company=app.company,
                    role=app.role,
                    applied_on=app.first_seen,
                    days_silent=days_silent,
                    draft_text=draft,
                )
            )
        else:
            app.needs_followup = False

    followups.sort(key=lambda f: f.days_silent, reverse=True)
    return followups
