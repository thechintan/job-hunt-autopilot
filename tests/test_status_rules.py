"""test_status_rules.py — Unit tests for the status rule classifier."""

import pytest
from autopilot.status_rules import classify_status


def test_offer_letter():
    label, reasons = classify_status("Offer letter - Software Engineer", "Please find your offer letter attached.", "careers@company.com")
    assert label == "offer"


def test_pleased_to_offer():
    label, _ = classify_status("Job Offer", "We are pleased to offer you the position.", "hr@corp.com")
    assert label == "offer"


def test_interview_invite():
    label, _ = classify_status("Interview invitation", "We would like to invite you for a technical interview.", "hr@company.com")
    assert label == "interview"


def test_next_steps():
    label, _ = classify_status("Next steps: interview schedule", "Please share your availability.", "hr@company.com")
    assert label == "interview"


def test_rejected_regret():
    label, _ = classify_status("Update on your application", "We regret to inform you that you were not selected.", "hr@company.com")
    assert label == "rejected"


def test_rejected_not_moving_forward():
    label, _ = classify_status("Application update", "We will not be moving forward with your application.", "hr@company.com")
    assert label == "rejected"


def test_applied_received():
    label, _ = classify_status("Application received: Data Analyst", "We have received your application.", "hr@company.com")
    assert label == "applied"


def test_applied_thanks_for_applying():
    label, _ = classify_status("Thanks for applying", "Thank you for applying for the role.", "hr@company.com")
    assert label == "applied"


def test_other_newsletter():
    label, _ = classify_status("12 new jobs for you", "Check out these jobs.", "jobalerts-noreply@linkedin.com")
    assert label == "other"


def test_unfortunately_without_context_not_rejected():
    """'unfortunately' alone should not trigger rejected."""
    label, _ = classify_status("Sorry", "Unfortunately the weather is bad today.", "person@company.com")
    assert label != "rejected"


def test_unfortunately_with_application_context():
    """'unfortunately' + 'application' should be rejected."""
    label, _ = classify_status("Update", "Unfortunately we will not be moving forward with your application.", "hr@company.com")
    assert label == "rejected"


def test_offer_priority_over_rejected():
    """'offer letter' beats 'unfortunately' in the same text."""
    label, _ = classify_status("Offer", "Unfortunately we can only offer you a lower salary. Offer letter attached.", "hr@company.com")
    assert label == "offer"


def test_shortlisted_alone_not_interview():
    """'Shortlisted candidates will be contacted' should NOT be interview."""
    label, _ = classify_status(
        "Application received: Operations Manager",
        "Dear applicant, we acknowledge receipt of your application. Shortlisted candidates will be contacted.",
        "hr@kiranfoods.in",
    )
    # Should be applied (or other), NOT interview
    assert label in ("applied", "other")
