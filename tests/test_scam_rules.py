"""test_scam_rules.py — Unit tests for scam signal detection."""

import pytest
from autopilot.scam_rules import score_scam


def test_fee_demand_triggers():
    score, reasons, _ = score_scam(
        "Job Offer", "Pay a registration fee of Rs 4500 to confirm joining.", "TCS HR", "gmail.com"
    )
    assert score >= 0.50
    assert any("fee" in r.lower() or "payment" in r.lower() for r in reasons)


def test_aadhaar_triggers():
    score, reasons, _ = score_scam(
        "Verification", "Please send your Aadhaar card and PAN card for verification.", "HR", "yahoo.com"
    )
    assert score >= 0.45
    assert any("sensitive" in r.lower() or "id" in r.lower() for r in reasons)


def test_free_mail_large_company():
    score, reasons, claimed = score_scam(
        "Offer from TCS", "You have been selected.", "TCS HR Department", "gmail.com"
    )
    assert score >= 0.40
    assert claimed is not None
    assert "tcs" in claimed.lower() or "Tcs" in claimed


def test_no_interview_triggers():
    score, reasons, _ = score_scam(
        "Selected without interview", "You are hired without any interview process.", "HR", "gmail.com"
    )
    assert score >= 0.30
    assert any("interview" in r.lower() for r in reasons)


def test_urgency_triggers():
    score, reasons, _ = score_scam(
        "URGENT!", "Reply within 24 hours or offer will be cancelled.", "HR", "yahoo.com"
    )
    assert any("urgency" in r.lower() or "pressure" in r.lower() for r in reasons)


def test_whatsapp_triggers():
    score, reasons, _ = score_scam(
        "Job Offer", "Message us on WhatsApp +91 90000 00000 now.", "HR", "gmail.com"
    )
    assert any("whatsapp" in r.lower() or "telegram" in r.lower() for r in reasons)


def test_hinglish_fee():
    score, reasons, _ = score_scam(
        "Selection", "Training fee Rs 2999 UPI se turant bhej dijiye.", "Rahul", "outlook.com"
    )
    assert score >= 0.50
    assert any("fee" in r.lower() or "payment" in r.lower() for r in reasons)


def test_hinglish_urgency():
    score, reasons, _ = score_scam(
        "Offer", "Jaldi karein, sirf aaj ka offer hai.", "HR", "gmail.com"
    )
    assert any("urgency" in r.lower() or "pressure" in r.lower() for r in reasons)


def test_legitimate_offer_not_scam():
    """A real offer letter from a corporate domain should have low scam score."""
    score, reasons, _ = score_scam(
        "Offer letter - Full Stack Developer at Orbit Labs",
        "We are delighted to extend an offer for the Full Stack Developer position. "
        "Please find the offer letter attached with compensation details.",
        "Orbit Labs Talent",
        "orbitlabs.co",
    )
    assert score < 0.60, f"False positive! score={score}, reasons={reasons}"


def test_e08_real_offer_not_scam():
    """The Orbit Labs offer (e08) must NOT be flagged scam."""
    score, reasons, _ = score_scam(
        "Offer letter - Full Stack Developer at Orbit Labs",
        "Dear candidate, we are delighted to extend an offer for the Full Stack Developer position "
        "at Orbit Labs. Please find the offer letter attached with compensation details. "
        "Kindly confirm your acceptance by 25 October.",
        "Orbit Labs Talent",
        "orbitlabs.co",
    )
    assert score < 0.60, f"e08 false positive! score={score}"


def test_shouty_subject():
    score, reasons, _ = score_scam(
        "CONGRATULATIONS YOU ARE SELECTED!!!",
        "You have been selected.",
        "HR",
        "gmail.com",
    )
    assert any("caps" in r.lower() or "shouty" in r.lower() for r in reasons)
