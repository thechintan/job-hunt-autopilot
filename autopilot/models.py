"""Data models for Job Hunt Autopilot."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Optional

Label = Literal["applied", "interview", "rejected", "offer", "scam", "other"]
StatusLabel = Literal["applied", "interview", "rejected", "offer"]


@dataclass
class Email:
    id: str
    from_name: str
    from_email: str
    sender_domain: str
    to: str
    subject: str
    date: datetime  # tz-aware
    body: str


@dataclass
class Classification:
    email_id: str
    label: Label
    confidence: float           # 0..1
    reasons: list               # list[str] - human-readable
    scam_score: float           # 0..1, always computed
    company: Optional[str]
    role: Optional[str]


@dataclass
class Application:
    key: str
    company: str
    role: Optional[str]
    status: StatusLabel
    first_seen: date
    last_activity: date
    history: list               # list[tuple[date, str, str]] = (date, label, email_id)
    needs_followup: bool
    days_silent: int


@dataclass
class ScamAlert:
    email_id: str
    from_email: str
    subject: str
    date: datetime
    scam_score: float
    reasons: list               # list[str]
    claimed_company: Optional[str]


@dataclass
class FollowUp:
    application_key: str
    company: str
    role: Optional[str]
    applied_on: date
    days_silent: int
    draft_text: str


@dataclass
class PipelineResult:
    emails: list                        # list[Email]
    classifications: list               # list[Classification]
    applications: list                  # list[Application]
    scam_alerts: list                   # list[ScamAlert]
    followups: list                     # list[FollowUp]
    ml_on: bool
    ml_f1: Optional[float]
