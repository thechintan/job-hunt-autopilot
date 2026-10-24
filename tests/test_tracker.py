"""test_tracker.py — Unit tests for the application tracker."""

import pytest
from datetime import date, datetime, timezone
from autopilot.models import Email, Classification
from autopilot.tracker import build_tracker


def _make_email(eid, from_email="hr@company.com", dt_str="2026-10-01T10:00:00+05:30"):
    from dateutil import parser as dp
    return Email(
        id=eid,
        from_name="Company HR",
        from_email=from_email,
        sender_domain=from_email.split("@")[1],
        to="me@example.com",
        subject="Test",
        date=dp.parse(dt_str),
        body="",
    )


def _make_clf(eid, label, company="Acme", role="Engineer"):
    return Classification(
        email_id=eid,
        label=label,
        confidence=0.9,
        reasons=[],
        scam_score=0.0,
        company=company,
        role=role,
    )


def test_single_applied():
    e = _make_email("e1")
    c = _make_clf("e1", "applied")
    apps = build_tracker([c], {"e1": e})
    assert len(apps) == 1
    assert apps[0].status == "applied"


def test_applied_then_interview():
    e1 = _make_email("e1", dt_str="2026-10-01T10:00:00+05:30")
    e2 = _make_email("e2", dt_str="2026-10-05T10:00:00+05:30")
    clfs = [
        _make_clf("e1", "applied"),
        _make_clf("e2", "interview"),
    ]
    apps = build_tracker(clfs, {"e1": e1, "e2": e2})
    assert len(apps) == 1
    assert apps[0].status == "interview"


def test_interview_then_offer():
    e1 = _make_email("e1", dt_str="2026-10-01T10:00:00+05:30")
    e2 = _make_email("e2", dt_str="2026-10-05T10:00:00+05:30")
    clfs = [
        _make_clf("e1", "interview"),
        _make_clf("e2", "offer"),
    ]
    apps = build_tracker(clfs, {"e1": e1, "e2": e2})
    assert apps[0].status == "offer"


def test_rejected_terminal():
    e1 = _make_email("e1", dt_str="2026-10-01T10:00:00+05:30")
    e2 = _make_email("e2", dt_str="2026-10-05T10:00:00+05:30")
    clfs = [
        _make_clf("e1", "applied"),
        _make_clf("e2", "rejected"),
    ]
    apps = build_tracker(clfs, {"e1": e1, "e2": e2})
    assert apps[0].status == "rejected"


def test_rejected_then_offer_upgrades():
    """Rejected can be overwritten by a later offer."""
    e1 = _make_email("e1", dt_str="2026-10-01T10:00:00+05:30")
    e2 = _make_email("e2", dt_str="2026-10-05T10:00:00+05:30")
    e3 = _make_email("e3", dt_str="2026-10-10T10:00:00+05:30")
    clfs = [
        _make_clf("e1", "applied"),
        _make_clf("e2", "rejected"),
        _make_clf("e3", "offer"),
    ]
    apps = build_tracker(clfs, {"e1": e1, "e2": e2, "e3": e3})
    assert apps[0].status == "offer"


def test_applied_does_not_downgrade():
    """An applied email after an interview should not downgrade to applied."""
    e1 = _make_email("e1", dt_str="2026-10-01T10:00:00+05:30")
    e2 = _make_email("e2", dt_str="2026-10-05T10:00:00+05:30")
    clfs = [
        _make_clf("e1", "interview"),
        _make_clf("e2", "applied"),
    ]
    apps = build_tracker(clfs, {"e1": e1, "e2": e2})
    assert apps[0].status == "interview"


def test_no_applied_creates_app():
    """If only a rejection email exists (no applied first), still create app."""
    e = _make_email("e1")
    c = _make_clf("e1", "rejected")
    apps = build_tracker([c], {"e1": e})
    assert len(apps) == 1
    assert apps[0].status == "rejected"


def test_scam_and_other_excluded():
    """Scam/other emails should not appear in tracker."""
    e1 = _make_email("e1")
    e2 = _make_email("e2")
    clfs = [
        _make_clf("e1", "scam"),
        _make_clf("e2", "other"),
    ]
    apps = build_tracker(clfs, {"e1": e1, "e2": e2})
    assert len(apps) == 0


def test_multiple_companies():
    e1 = _make_email("e1")
    e2 = _make_email("e2")
    clfs = [
        _make_clf("e1", "applied", company="Acme", role="Engineer"),
        _make_clf("e2", "applied", company="Beta Corp", role="Manager"),
    ]
    apps = build_tracker(clfs, {"e1": e1, "e2": e2})
    assert len(apps) == 2
