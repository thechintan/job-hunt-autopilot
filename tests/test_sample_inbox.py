"""test_sample_inbox.py — Acceptance tests using data/sample_inbox.json.

This is the definition of done (PRD §9). All assertions must pass.
Today is pinned to 2026-10-24.
"""

import pytest
from datetime import date
from pathlib import Path

from autopilot.ingest import load_json
from autopilot.pipeline import run

SAMPLE_INBOX = Path(__file__).parent.parent / "data" / "sample_inbox.json"
TODAY = date(2026, 10, 24)


@pytest.fixture(scope="module")
def result():
    emails = load_json(SAMPLE_INBOX)
    return run(emails, today=TODAY)


@pytest.fixture(scope="module")
def label_map(result):
    return {c.email_id: c.label for c in result.classifications}


# ---------------------------------------------------------------------------
# 1. Per-email labels
# ---------------------------------------------------------------------------

class TestEmailLabels:
    APPLIED_IDS = {"e01", "e02", "e04", "e06", "e09", "e10", "e11", "e13", "e15"}
    INTERVIEW_IDS = {"e03", "e07", "e14"}
    REJECTED_IDS = {"e05", "e12"}
    OFFER_IDS = {"e08"}
    SCAM_IDS = {"e16", "e17", "e18", "e19"}
    OTHER_IDS = {"e20"}

    def test_applied_labels(self, label_map):
        for eid in self.APPLIED_IDS:
            assert label_map[eid] == "applied", f"{eid}: expected applied, got {label_map[eid]}"

    def test_interview_labels(self, label_map):
        for eid in self.INTERVIEW_IDS:
            assert label_map[eid] == "interview", f"{eid}: expected interview, got {label_map[eid]}"

    def test_rejected_labels(self, label_map):
        for eid in self.REJECTED_IDS:
            assert label_map[eid] == "rejected", f"{eid}: expected rejected, got {label_map[eid]}"

    def test_offer_label(self, label_map):
        for eid in self.OFFER_IDS:
            assert label_map[eid] == "offer", f"{eid}: expected offer, got {label_map[eid]}"

    def test_scam_labels(self, label_map):
        for eid in self.SCAM_IDS:
            assert label_map[eid] == "scam", f"{eid}: expected scam, got {label_map[eid]}"

    def test_other_label(self, label_map):
        for eid in self.OTHER_IDS:
            assert label_map[eid] == "other", f"{eid}: expected other, got {label_map[eid]}"

    def test_zero_false_positives(self, label_map):
        """None of e01-e15, e20 may be labelled scam."""
        safe_ids = (
            self.APPLIED_IDS | self.INTERVIEW_IDS | self.REJECTED_IDS |
            self.OFFER_IDS | self.OTHER_IDS
        )
        for eid in safe_ids:
            assert label_map[eid] != "scam", f"{eid} was falsely flagged as scam"

    def test_e08_real_offer_not_scam(self, label_map):
        """The genuine Orbit Labs offer must NOT be scam."""
        assert label_map["e08"] == "offer", f"e08 should be offer, got {label_map['e08']}"


# ---------------------------------------------------------------------------
# 2. Tracker (9 applications)
# ---------------------------------------------------------------------------

class TestTracker:

    def test_nine_applications(self, result):
        assert len(result.applications) == 9, (
            f"Expected 9 applications, got {len(result.applications)}: "
            + str([a.company for a in result.applications])
        )

    def _get_app(self, result, company_fragment: str):
        for app in result.applications:
            if company_fragment.lower() in app.company.lower():
                return app
        return None

    def test_acme_robotics_applied(self, result):
        app = self._get_app(result, "Acme")
        assert app is not None, "Acme Robotics not found"
        assert app.status == "applied"
        assert app.needs_followup is True
        assert app.days_silent >= 19

    def test_zenith_tech_interview(self, result):
        app = self._get_app(result, "Zenith")
        assert app is not None
        assert app.status == "interview"
        assert app.needs_followup is False

    def test_nimbus_cloud_rejected(self, result):
        app = self._get_app(result, "Nimbus")
        assert app is not None
        assert app.status == "rejected"
        assert app.needs_followup is False

    def test_orbit_labs_offer(self, result):
        app = self._get_app(result, "Orbit")
        assert app is not None
        assert app.status == "offer"
        assert app.needs_followup is False

    def test_pixelwave_applied_no_followup(self, result):
        app = self._get_app(result, "Pixel")
        assert app is not None
        assert app.status == "applied"
        assert app.needs_followup is False  # 4 days, < 7

    def test_kiran_foods_applied_followup(self, result):
        app = self._get_app(result, "Kiran")
        assert app is not None
        assert app.status == "applied"
        assert app.needs_followup is True
        assert app.days_silent >= 14

    def test_finlytics_rejected(self, result):
        app = self._get_app(result, "Finlytics")
        assert app is not None
        assert app.status == "rejected"
        assert app.needs_followup is False

    def test_cloudbase_interview(self, result):
        app = self._get_app(result, "Cloudbase")
        assert app is not None
        assert app.status == "interview"
        assert app.needs_followup is False

    def test_brightlane_applied_followup(self, result):
        app = self._get_app(result, "Brightlane")
        assert app is not None
        assert app.status == "applied"
        assert app.needs_followup is True
        assert app.days_silent >= 12


# ---------------------------------------------------------------------------
# 3. KPI checks
# ---------------------------------------------------------------------------

class TestKPIs:

    def test_followup_count(self, result):
        """Exactly 3 follow-ups due: Acme, Kiran Foods, Brightlane."""
        assert len(result.followups) == 3, (
            f"Expected 3 follow-ups, got {len(result.followups)}: "
            + str([f.company for f in result.followups])
        )

    def test_scam_count(self, result):
        assert len(result.scam_alerts) == 4, (
            f"Expected 4 scam alerts, got {len(result.scam_alerts)}"
        )

    def test_one_offer(self, result):
        offers = [a for a in result.applications if a.status == "offer"]
        assert len(offers) == 1
        assert "orbit" in offers[0].company.lower()

    def test_two_rejected(self, result):
        rejected = [a for a in result.applications if a.status == "rejected"]
        assert len(rejected) == 2

    def test_two_interview(self, result):
        interviews = [a for a in result.applications if a.status == "interview"]
        assert len(interviews) == 2


# ---------------------------------------------------------------------------
# 4. Scam reasons (minimum required)
# ---------------------------------------------------------------------------

class TestScamReasons:

    def _get_alert(self, result, email_id):
        for a in result.scam_alerts:
            if a.email_id == email_id:
                return a
        return None

    def _reasons_text(self, alert):
        return " ".join(alert.reasons).lower()

    def test_e16_reasons(self, result):
        alert = self._get_alert(result, "e16")
        assert alert is not None, "e16 not in scam alerts"
        rt = self._reasons_text(alert)
        # fee demand + free mail + no interview + urgency
        assert any("fee" in r or "payment" in r for r in alert.reasons), f"e16 missing fee reason: {alert.reasons}"
        assert any("free" in r or "gmail" in r or "tcs" in r.lower() for r in alert.reasons), f"e16 missing free-mail reason: {alert.reasons}"

    def test_e17_reasons(self, result):
        alert = self._get_alert(result, "e17")
        assert alert is not None, "e17 not in scam alerts"
        assert any("sensitive" in r or "id" in r or "aadhaar" in r.lower() for r in alert.reasons), f"e17 missing doc reason: {alert.reasons}"
        assert any("whatsapp" in r.lower() or "telegram" in r.lower() for r in alert.reasons), f"e17 missing platform reason: {alert.reasons}"

    def test_e18_hinglish_reasons(self, result):
        alert = self._get_alert(result, "e18")
        assert alert is not None, "e18 not in scam alerts"
        assert any("fee" in r or "payment" in r for r in alert.reasons), f"e18 missing fee reason: {alert.reasons}"
        assert any("urgency" in r.lower() or "pressure" in r.lower() for r in alert.reasons), f"e18 missing urgency reason: {alert.reasons}"

    def test_e19_reasons(self, result):
        alert = self._get_alert(result, "e19")
        assert alert is not None, "e19 not in scam alerts"
        assert any("google" in r.lower() or "free" in r.lower() or "gmail" in r.lower() for r in alert.reasons), f"e19 missing free-mail/Google reason: {alert.reasons}"
        assert any("interview" in r.lower() for r in alert.reasons), f"e19 missing no-interview reason: {alert.reasons}"


# ---------------------------------------------------------------------------
# 5. Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:

    def test_same_inbox_twice_gives_same_tracker(self):
        emails = load_json(SAMPLE_INBOX)
        r1 = run(emails, today=TODAY)
        r2 = run(emails, today=TODAY)
        keys1 = sorted(a.key for a in r1.applications)
        keys2 = sorted(a.key for a in r2.applications)
        assert keys1 == keys2
        statuses1 = {a.key: a.status for a in r1.applications}
        statuses2 = {a.key: a.status for a in r2.applications}
        assert statuses1 == statuses2


# ---------------------------------------------------------------------------
# 6. Simulate: adding a Kiran Foods interview flips status
# ---------------------------------------------------------------------------

class TestSimulateInterview:

    def test_kiran_interview_flips_status_and_removes_followup(self):
        from autopilot.ingest import load_json_dicts
        from datetime import timezone

        emails = load_json(SAMPLE_INBOX)

        # Add a new interview invite from Kiran Foods
        new_email = {
            "id": "sim_kiran_interview",
            "from_name": "Kiran Foods HR",
            "from_email": "hr@kiranfoods.in",
            "to": "me@example.com",
            "subject": "Interview invitation: Operations Manager",
            "date": "2026-10-23T10:00:00+05:30",
            "body": "Hi, we would like to invite you for an interview for the Operations Manager role.",
        }
        emails_with_sim = emails + load_json_dicts([new_email])
        result = run(emails_with_sim, today=TODAY)

        # Find Kiran Foods
        kiran = None
        for app in result.applications:
            if "kiran" in app.company.lower():
                kiran = app
                break
        assert kiran is not None
        assert kiran.status == "interview", f"Kiran Foods should be interview, got {kiran.status}"
        assert kiran.needs_followup is False


# ---------------------------------------------------------------------------
# 7. Missing datasets — rules-only mode (ML off)
# ---------------------------------------------------------------------------

class TestRulesOnlyMode:

    def test_pipeline_runs_without_ml(self):
        """Pipeline must run even when ML is off."""
        from autopilot import scam_ml
        orig = scam_ml._ml_available
        scam_ml._ml_available = False
        try:
            emails = load_json(SAMPLE_INBOX)
            result = run(emails, today=TODAY)
            # Should still classify correctly
            lm = {c.email_id: c.label for c in result.classifications}
            for eid in ["e16", "e17", "e18", "e19"]:
                assert lm[eid] == "scam", f"{eid} should still be scam in rules-only mode"
            assert lm["e08"] == "offer"
        finally:
            scam_ml._ml_available = orig
