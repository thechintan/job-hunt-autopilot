"""scam_rules.py — Weighted rule-based scam signal detector.

Returns (rule_score: float, reasons: list[str], claimed_company: str | None)
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Hinglish scam terms (easy to extend — single constant)
# ---------------------------------------------------------------------------
HINGLISH_SCAM_TERMS = {
    "fee_demand": [
        r"fee\s+(?:bhej|dena|jama|deposit|pay|bhejo)",
        r"training\s+fee",
        r"registration\s+(?:fee|amount|shulk)",
        r"refundable\s+hai",
        r"upi\s+se\s+(?:bhej|pay|send)",
        r"paisa\s+(?:bhej|jama|dena)",
    ],
    "urgency": [
        r"\bjaldi\b",
        r"\bsirf\s+aaj\b",
        r"aaj\s+ka\s+offer",
        r"abhi\s+(?:bhej|pay|send)",
    ],
    "selection": [
        r"selection\s+ho\s+gaya",
        r"aapka\s+selection",
        r"ho\s+gaya\s+hai",
    ],
    "otp_aadhaar": [
        r"aadhaar\s+number\b",
        r"otp\s+(?:share|bhej|send|dena)",
        r"share\s+karo\s+otp",
    ],
}

# ---------------------------------------------------------------------------
# Free mail domains
# ---------------------------------------------------------------------------
_FREE_MAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.in", "yahoo.co.in",
    "outlook.com", "hotmail.com", "rediffmail.com", "ymail.com",
    "hotmail.in",
}

# Known large companies (display name / body mentions)
_KNOWN_LARGE_COMPANIES = [
    "tcs", "tata consultancy", "infosys", "wipro", "google", "amazon",
    "microsoft", "accenture", "cognizant", "hcl", "flipkart", "reliance",
    "facebook", "meta", "apple", "ibm", "deloitte", "kpmg", "pwc",
    "capgemini", "oracle", "sap", "ey", "ernst",
]
_LARGE_COMPANY_RE = re.compile(
    "|".join(re.escape(c) for c in _KNOWN_LARGE_COMPANIES),
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Signal patterns and weights
# ---------------------------------------------------------------------------

# --- Money / fee demand (weight 0.50) ---
_FEE_PATTERNS = [
    r"registration\s+fee",
    r"training\s+fee",
    r"security\s+deposit",
    r"processing\s+fee",
    r"laptop\s+deposit",
    r"pay\s+(?:rs\.?\s*\d+|₹\s*\d+|inr\s*\d+)",
    r"(?:rs\.?\s*|₹\s*|inr\s*)\d[\d,]*\s*(?:registration|deposit|fee|charge)",
    r"\brefundable\b",
    r"kit\s+charges",
    r"pay\s+a\s+(?:refundable\s+)?(?:registration|training|security|processing)\s+fee",
]
_FEE_RE = [re.compile(p, re.IGNORECASE) for p in _FEE_PATTERNS]
# Hinglish fee
_HINGLISH_FEE_RE = [re.compile(p, re.IGNORECASE) for p in HINGLISH_SCAM_TERMS["fee_demand"]]
FEE_WEIGHT = 0.50

# --- Sensitive docs / data (weight 0.45) ---
_DOC_PATTERNS = [
    r"\baadhaar\b",
    r"\bpan\s*card\b",
    r"\bpassport\b",
    r"bank\s+(?:details|passbook|account)",
    r"\bOTP\b",
    r"\bcvv\b",
    r"photo\s+of\s+(?:your\s+)?(?:\w+\s+)?card",
    r"scanned\s+copy\s+of",
]
_DOC_RE = [re.compile(p, re.IGNORECASE) for p in _DOC_PATTERNS]
_HINGLISH_DOC_RE = [re.compile(p, re.IGNORECASE) for p in HINGLISH_SCAM_TERMS["otp_aadhaar"]]
DOC_WEIGHT = 0.45

# --- No interview / pre-selected (weight 0.30) ---
_NO_INTERVIEW_PATTERNS = [
    r"without\s+(?:an\s+)?interview",
    r"no\s+interview",
    r"pre[- ]?selected",
    r"direct\s+selection",
]
_NO_INTERVIEW_RE = [re.compile(p, re.IGNORECASE) for p in _NO_INTERVIEW_PATTERNS]
_HINGLISH_SELECTION_RE = [re.compile(p, re.IGNORECASE) for p in HINGLISH_SCAM_TERMS["selection"]]
NO_INTERVIEW_WEIGHT = 0.30

# --- Off-platform (WhatsApp / Telegram) (weight 0.25) ---
_OFFPLATFORM_PATTERNS = [
    r"whatsapp\s+\+?\d[\d\s]{6,}",
    r"message\s+(?:us\s+)?on\s+whatsapp",
    r"telegram\s+@\w+",
    r"contact\s+(?:us\s+)?on\s+telegram",
    r"(?:whatsapp|telegram)\s+(?:number|handle|us|me|@)",
]
_OFFPLATFORM_RE = [re.compile(p, re.IGNORECASE) for p in _OFFPLATFORM_PATTERNS]
OFFPLATFORM_WEIGHT = 0.25

# --- Urgency / pressure (weight 0.20) ---
_URGENCY_PATTERNS = [
    r"within\s+24\s+hours",
    r"\burgent\b",
    r"limited\s+seats",
    r"\bonly\s+today\b",
    r"offer\s+will\s+be\s+cancelled",
    r"apply\s+today",
]
_URGENCY_RE = [re.compile(p, re.IGNORECASE) for p in _URGENCY_PATTERNS]
_HINGLISH_URGENCY_RE = [re.compile(p, re.IGNORECASE) for p in HINGLISH_SCAM_TERMS["urgency"]]
URGENCY_WEIGHT = 0.20

# --- Unrealistic pay (weight 0.25) ---
_PAY_PATTERNS = [
    r"earn\s+(?:rs\.?\s*|₹\s*)?\d{3,}\s+per\s+day",
    r"(?:no|zero)\s+experience\s+(?:needed|required|necessary).*(?:rs\.?|₹|salary|earn|pay)",
    r"work\s+from\s+home.*earn\s+(?:rs\.?|₹)\s*[\d,]+",
    r"earn\s+(?:rs\.?|₹)\s*[\d,]+.*work\s+from\s+home",
]
_PAY_RE = [re.compile(p, re.IGNORECASE) for p in _PAY_PATTERNS]
PAY_WEIGHT = 0.25

# --- Shortened / odd links (weight 0.20) ---
_LINK_PATTERNS = [
    r"bit\.ly/\S+",
    r"tinyurl\.com/\S+",
    r"https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
    r"goo\.gl/\S+",
    r"t\.co/\S+",
]
_LINK_RE = [re.compile(p, re.IGNORECASE) for p in _LINK_PATTERNS]
LINK_WEIGHT = 0.20

# --- Shouty formatting (weight 0.10) ---
SHOUTY_WEIGHT = 0.10


def _match_any(patterns: list, text: str) -> Optional[str]:
    for p in patterns:
        m = p.search(text)
        if m:
            return m.group(0)
    return None


def _is_free_mail(domain: str) -> bool:
    return domain.lower() in _FREE_MAIL_DOMAINS


def _claimed_large_company(from_name: str, body: str) -> Optional[str]:
    """Return company name if a large company is claimed in display name or body."""
    text = (from_name + " " + body[:300]).lower()
    m = _LARGE_COMPANY_RE.search(text)
    if m:
        return m.group(0).title()
    return None


def _is_shouty(subject: str, body: str) -> bool:
    """True if subject has >50% caps ratio OR ≥3 exclamation marks."""
    alpha = [c for c in subject if c.isalpha()]
    if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.5:
        return True
    excls = subject.count("!") + body.count("!")
    return excls >= 3


def score_scam(
    subject: str,
    body: str,
    from_name: str,
    sender_domain: str,
) -> tuple:
    """
    Returns (rule_score: float, reasons: list[str], claimed_company: str | None)
    """
    text = subject + " " + body
    reasons = []
    total_weight = 0.0

    # 1. Fee demand
    matched = _match_any(_FEE_RE, text) or _match_any(_HINGLISH_FEE_RE, text)
    if matched:
        reasons.append("Asks for payment / registration fee")
        total_weight += FEE_WEIGHT

    # 2. Sensitive docs
    matched = _match_any(_DOC_RE, text) or _match_any(_HINGLISH_DOC_RE, text)
    if matched:
        reasons.append("Requests sensitive ID/bank/OTP details before any hiring process")
        total_weight += DOC_WEIGHT

    # 3. Free mail + large company
    claimed = None
    if _is_free_mail(sender_domain):
        claimed = _claimed_large_company(from_name, body)
        if claimed:
            reasons.append(
                f"Claims to be {claimed} but emails from a free {sender_domain} address"
            )
            total_weight += 0.40

    # 4. No interview / pre-selected
    matched = _match_any(_NO_INTERVIEW_RE, text) or _match_any(_HINGLISH_SELECTION_RE, text)
    if matched:
        reasons.append("Offer with no interview or application on your part")
        total_weight += NO_INTERVIEW_WEIGHT

    # 5. Off-platform
    matched = _match_any(_OFFPLATFORM_RE, text)
    if matched:
        reasons.append("Pushes conversation to WhatsApp/Telegram")
        total_weight += OFFPLATFORM_WEIGHT

    # 6. Urgency
    matched = _match_any(_URGENCY_RE, text) or _match_any(_HINGLISH_URGENCY_RE, text)
    if matched:
        reasons.append("Artificial urgency / pressure")
        total_weight += URGENCY_WEIGHT

    # 7. Unrealistic pay
    matched = _match_any(_PAY_RE, text)
    if matched:
        reasons.append("Unrealistic pay for no skills")
        total_weight += PAY_WEIGHT

    # 8. Shortened links
    matched = _match_any(_LINK_RE, text)
    if matched:
        reasons.append("Contains shortened/suspicious link")
        total_weight += LINK_WEIGHT

    # 9. Shouty formatting
    if _is_shouty(subject, body):
        reasons.append("Shouty formatting (ALL CAPS or excessive exclamation marks)")
        total_weight += SHOUTY_WEIGHT

    rule_score = min(1.0, total_weight)
    return rule_score, reasons, claimed
