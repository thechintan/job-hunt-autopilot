# DECISIONS.md — Agent assumptions and choices

## General
- Project root: `d:\Garbathon\` (as found in workspace).
- "Today" for acceptance tests: `2026-10-24` (pinned per PRD §9).

## models.py
- Used Python `dataclasses` instead of Pydantic (simpler, no extra dep).
- `history` in `Application` stored as `list[tuple[date, str, str]]` (date, label, email_id).

## normalize.py
- Company name extraction order: strip suffix words from display name → regex in subject/body → domain root.
- Legal suffixes stripped: `pvt ltd`, `inc`, `llc`, `ltd`, `co`, `corp`, `pvt`.
- Role extraction regex applied to subject first (colon/dash pattern), then body.
- Domain root: take first part of domain before first dot, title-case it.

## status_rules.py
- `unfortunately` guard: only fires `rejected` if the same text also contains `application|candidacy|position|role|candidate`.
- "shortlisted" is treated as an interview signal (§6.1 lists it under interview).
- e10 ("shortlisted candidates will be contacted") — body mentions "Shortlisted" but in context "shortlisted candidates will be contacted" means pending review, not an interview invite. The expected label is `applied`. Decision: only treat "shortlisted" as interview signal if paired with interview-specific words OR it is a standalone phrase indicating selection to interview stage.  Revised: "shortlisted" alone in this context ("shortlisted candidates will be contacted") is ambiguous; e10 expected label is `applied` so we require "shortlisted" to co-occur with an interview action word to fire the interview rule. Implemented as a separate tighter regex.

## scam_rules.py
- Free-mail domains list: `gmail.com, yahoo.com, yahoo.in, yahoo.co.in, outlook.com, hotmail.com, rediffmail.com, ymail.com`.
- Known large company names: TCS, Infosys, Wipro, Google, Amazon, Microsoft, Accenture, Cognizant, HCL, Flipkart, Reliance, Facebook, Meta, Apple, IBM, Deloitte, KPMG, EY, PwC, Capgemini, Oracle, SAP.
- Hinglish terms in `HINGLISH_SCAM_TERMS` constant.
- "work from home" + high pay: detected if body contains "work from home" AND "earn rs" / "per day" within the text.

## classify.py
- `confidence` field: for rule-based labels set to 0.9 (high confidence rules), for `other` set to 0.6.
- `scam_score` always computed for all emails (even those not labelled scam).

## tracker.py
- Application key: `normalized_company|normalized_role`; if role is None, key is just `normalized_company`.
- Status priority: applied(1) < interview(2) < offer(3); rejected is terminal unless later offer/interview.
- When a later-dated email upgrades from rejected, status is updated.

## followups.py
- `applied_on` = `first_seen` date of the application.
- draft uses "the open position" if role is None.

## ML / train.py
- If both datasets missing, skip ML entirely (rules-only mode).
- HF dataset fetched via `hf_hub_download`; saved to `data/raw/hinglish_scam.json`.
- Hinglish rows upsampled ×10 in training.

## app.py
- Wide layout, single page.
- Session state key: `st.session_state["emails"]` holds list of raw email dicts.
- Pipeline reruns on every inbox change.
- `output/` directory created automatically if missing.

## Repository & Environment Configuration
- `.gitignore`: Ignores `.env`, bytecode, `.pytest_cache`, large raw datasets (`data/raw/*.csv`, `data/raw/*.json`), binary ML models (`models/*.joblib`), generated runtime output (`output/*.json`), and OS/IDE metadata.
- `.env.example`: Provides template for optional Kaggle API credentials (`KAGGLE_USERNAME`, `KAGGLE_KEY`), optional HuggingFace token, and Streamlit configs.
- `.env`: Created locally with default blank keys (gitignored).
- `.gitkeep`: Created in `data/raw/`, `models/`, and `output/` so directory structure is preserved in clones.
- `LICENSE`: Added MIT License under copyright of `thechintan`.
- `requirements.txt`: Added `python-dotenv>=1.0.0` and updated `scripts/download_data.py` to auto-load `.env` if present.
