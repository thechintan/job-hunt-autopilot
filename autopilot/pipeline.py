"""pipeline.py — Orchestrates the full classification pipeline."""

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Union

from autopilot.models import Email, PipelineResult, ScamAlert
from autopilot.classify import classify_all
from autopilot.tracker import build_tracker
from autopilot.followups import due_followups
from autopilot.scam_ml import is_available as ml_available, get_f1 as ml_f1

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def run(emails: list, today: Optional[date] = None) -> PipelineResult:
    """
    Run the full pipeline on a list[Email].
    Returns PipelineResult.
    """
    if today is None:
        today = date.today()

    # Build lookup by email id
    emails_by_id = {e.id: e for e in emails}

    # Classify all emails
    classifications = classify_all(emails)

    # Build tracker (only applied/interview/rejected/offer)
    applications = build_tracker(classifications, emails_by_id)

    # Compute follow-ups (mutates applications)
    followups = due_followups(applications, today)

    # Build scam alerts
    scam_alerts = []
    for clf in classifications:
        if clf.label == "scam":
            email = emails_by_id.get(clf.email_id)
            if email:
                scam_alerts.append(
                    ScamAlert(
                        email_id=clf.email_id,
                        from_email=email.from_email,
                        subject=email.subject,
                        date=email.date,
                        scam_score=clf.scam_score,
                        reasons=clf.reasons,
                        claimed_company=clf.company,
                    )
                )

    # Sort scam alerts by score descending
    scam_alerts.sort(key=lambda a: a.scam_score, reverse=True)

    result = PipelineResult(
        emails=emails,
        classifications=classifications,
        applications=applications,
        scam_alerts=scam_alerts,
        followups=followups,
        ml_on=ml_available(),
        ml_f1=ml_f1(),
    )

    # Persist tracker to output/tracker.json
    _save_tracker(result)

    return result


def _save_tracker(result: PipelineResult) -> None:
    """Save tracker JSON to output/tracker.json."""
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        tracker_data = []
        for app in result.applications:
            tracker_data.append(
                {
                    "key": app.key,
                    "company": app.company,
                    "role": app.role,
                    "status": app.status,
                    "first_seen": str(app.first_seen),
                    "last_activity": str(app.last_activity),
                    "needs_followup": app.needs_followup,
                    "days_silent": app.days_silent,
                    "history": [
                        {"date": str(d), "label": lbl, "email_id": eid}
                        for d, lbl, eid in app.history
                    ],
                }
            )
        output_path = OUTPUT_DIR / "tracker.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(tracker_data, f, indent=2, default=str)
    except Exception as e:
        print(f"[pipeline] Warning: could not save tracker.json: {e}")
