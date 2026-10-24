"""test_followups.py — Unit tests for follow-up reminder logic."""

import pytest
from datetime import date
from autopilot.models import Application
from autopilot.followups import due_followups


def _make_app(key, company, role, status, last_activity, first_seen=None):
    if first_seen is None:
        first_seen = last_activity
    return Application(
        key=key,
        company=company,
        role=role,
        status=status,
        first_seen=first_seen,
        last_activity=last_activity,
        history=[],
        needs_followup=False,
        days_silent=0,
    )


TODAY = date(2026, 10, 24)


def test_applied_7_days_silent_gets_followup():
    app = _make_app("acme|engineer", "Acme", "Engineer", "applied",
                    last_activity=date(2026, 10, 17), first_seen=date(2026, 10, 17))
    followups = due_followups([app], TODAY)
    assert len(followups) == 1
    assert app.needs_followup is True
    assert app.days_silent == 7


def test_applied_6_days_no_followup():
    app = _make_app("beta|dev", "Beta", "Dev", "applied",
                    last_activity=date(2026, 10, 18))
    followups = due_followups([app], TODAY)
    assert len(followups) == 0
    assert app.needs_followup is False


def test_interview_no_followup_even_if_old():
    app = _make_app("gamma|pm", "Gamma", "PM", "interview",
                    last_activity=date(2026, 10, 1))
    followups = due_followups([app], TODAY)
    assert len(followups) == 0


def test_offer_no_followup():
    app = _make_app("delta|eng", "Delta", "Eng", "offer",
                    last_activity=date(2026, 10, 1))
    followups = due_followups([app], TODAY)
    assert len(followups) == 0


def test_rejected_no_followup():
    app = _make_app("epsilon|qa", "Epsilon", "QA", "rejected",
                    last_activity=date(2026, 10, 1))
    followups = due_followups([app], TODAY)
    assert len(followups) == 0


def test_sorted_by_days_silent_desc():
    app1 = _make_app("a|r1", "A", "R1", "applied", last_activity=date(2026, 10, 5))
    app2 = _make_app("b|r2", "B", "R2", "applied", last_activity=date(2026, 10, 10))
    followups = due_followups([app1, app2], TODAY)
    assert followups[0].days_silent >= followups[1].days_silent


def test_draft_text_contains_company_and_role():
    app = _make_app("z|dev", "Zeta Corp", "Developer", "applied",
                    last_activity=date(2026, 10, 1), first_seen=date(2026, 10, 1))
    followups = due_followups([app], TODAY)
    assert len(followups) == 1
    draft = followups[0].draft_text
    assert "Zeta Corp" in draft
    assert "Developer" in draft


def test_no_role_uses_open_position():
    app = _make_app("w|none", "Widgetco", None, "applied",
                    last_activity=date(2026, 10, 1), first_seen=date(2026, 10, 1))
    followups = due_followups([app], TODAY)
    assert "open position" in followups[0].draft_text
