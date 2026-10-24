"""classify.py — Classify a single email into one label.

Order of operations (per PRD §6):
1. Compute scam_score (rules + ML) for every email.
2. If scam_score >= 0.60 → label = "scam", stop.
3. Else run status rules: offer → interview → rejected → applied → other.
"""

from autopilot.models import Email, Classification
from autopilot.scam_rules import score_scam
from autopilot.scam_ml import predict_proba, is_available as ml_available
from autopilot.status_rules import classify_status
from autopilot.normalize import extract_company, extract_role

SCAM_THRESHOLD = 0.60


def _combine_scam_score(rule_score: float, ml_prob: float) -> float:
    """Combine rule score and ML probability per PRD §6.3.
    
    scam_score = max(rule_score, 0.5*rule_score + 0.5*ml_prob)
    Rules can never be dragged down by ML; ML only boosts.
    """
    if not ml_available() or ml_prob == 0.0:
        return rule_score
    combined = 0.5 * rule_score + 0.5 * ml_prob
    return max(rule_score, combined)


def classify_email(email: Email) -> Classification:
    """Classify a single email. Returns a Classification."""
    text = email.subject + " " + email.body

    # Step 1: Compute scam score
    rule_score, scam_reasons, claimed_company = score_scam(
        subject=email.subject,
        body=email.body,
        from_name=email.from_name,
        sender_domain=email.sender_domain,
    )
    ml_prob = predict_proba(text) if ml_available() else 0.0
    scam_score = _combine_scam_score(rule_score, ml_prob)

    # Extract company and role for all emails
    company = extract_company(email)
    role = extract_role(email)

    # Step 2: Scam wins
    if scam_score >= SCAM_THRESHOLD:
        return Classification(
            email_id=email.id,
            label="scam",
            confidence=round(scam_score, 3),
            reasons=scam_reasons,
            scam_score=round(scam_score, 3),
            company=company,
            role=role,
        )

    # Step 3: Status rules
    label, status_reasons = classify_status(
        subject=email.subject,
        body=email.body,
        from_email=email.from_email,
    )

    confidence = 0.9 if label != "other" else 0.6

    return Classification(
        email_id=email.id,
        label=label,
        confidence=confidence,
        reasons=status_reasons,
        scam_score=round(scam_score, 3),
        company=company,
        role=role,
    )


def classify_all(emails: list) -> list:
    """Classify a list of Email objects. Returns list[Classification]."""
    return [classify_email(email) for email in emails]
