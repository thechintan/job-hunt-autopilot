
# Job Hunt Autopilot — PRD + Architecture (build spec for a coding agent)

> **Tagline:** Track every application. Catch every fake offer.
> **Time budget:** 2.5 hours, one developer + one coding agent.
> **Rule for the agent:** Follow this document literally. Every decision is already made. Do NOT ask clarifying questions; if something is truly missing, pick the simplest option, write it in `DECISIONS.md`, and move on.

---

## 1. What we are building

A small web app. A person who was laid off has applied to many jobs and their inbox is a mess. They load their inbox (JSON or .mbox). The app:

1. **Classifies each email once** into exactly one label: `applied`, `interview`, `rejected`, `offer`, `scam` (plus `other` for noise like newsletters/job alerts).
2. **Builds a self-updating tracker**: one row per application (company + role) with its current status.
3. **Flags fake offers in red** with human-readable reasons (fee demand, Aadhaar/PAN request, free-mail sender claiming to be a big company, etc.).
4. **Creates follow-up reminders** for applications still at `applied` with no reply after **7 days**, with a ready-to-send follow-up draft.

The scam check is **a label inside the same pipeline, not a separate product**.

### Demo story (keep this front and center in the UI copy)

"After a layoff you apply to 100+ roles. Autopilot tells you who replied, who rejected you, who to nudge today — and which 'offers' are traps."

### Explicitly OUT of scope (do not build)

- Gmail/Outlook login or any OAuth
- PF, gratuity, severance calculators
- Resume rewriting / cover-letter generation
- User accounts, auth, multi-tenant, deployment
- Sending emails (we only *draft* follow-ups as text)

---

## 2. Final decisions (do not revisit)

| Topic                  | Decision                                                                                                     |
| ---------------------- | ------------------------------------------------------------------------------------------------------------ |
| Language               | Python 3.11+                                                                                                 |
| UI                     | **Streamlit** single page (fastest for 2.5h)                                                           |
| Core logic             | Plain Python package`autopilot/`, UI is a thin layer on top                                                |
| Status classification  | **Rule-based** regex/keyword classifier (deterministic, explainable)                                   |
| Scam detection         | **Hybrid**: weighted rule signals (primary) + small scikit-learn text model (secondary)                |
| ML model               | TF-IDF (word 1-2gram + char 3-5gram) + Logistic Regression,`class_weight="balanced"`                       |
| LLM calls              | **None required.** App must work fully offline. (Optional stretch only, behind a flag, off by default) |
| Storage                | No DB. Tracker is recomputed from emails every time (idempotent) and cached to`output/tracker.json`        |
| "Today" for 7-day rule | Configurable; default = real today; sample demo pins to`2026-10-24` via `--today` / sidebar date input   |
| Input formats          | `.json` (schema in §5) and `.mbox`                                                                      |
| Tests                  | `pytest`, must pass before declaring done                                                                  |

---

## 3. Datasets (read carefully — there are traps)

### 3.1 Real or Fake Job Posting (Kaggle)

- URL: https://www.kaggle.com/datasets/shivamb/real-or-fake-fake-jobposting-prediction
- File: `fake_job_postings.csv` (EMSCAD), ~17,880 rows, ~866 fraudulent (≈5%, very imbalanced).
- Expected columns: `job_id, title, location, department, salary_range, company_profile, description, requirements, benefits, telecommuting, has_company_logo, has_questions, employment_type, required_experience, required_education, industry, function, fraudulent`. **Verify column names on load and fail with a clear message if missing.**
- Label: `fraudulent` (1 = fake).
- **Needs Kaggle login to download.** The agent cannot fetch it. Expect the human to place it at `data/raw/fake_job_postings.csv`. Provide `scripts/download_data.py` that tries `kaggle datasets download -d shivamb/real-or-fake-fake-jobposting-prediction` if the Kaggle CLI + credentials exist, otherwise prints exact manual steps.
- **Caveat:** these are job *postings*, not emails. So this data is only a **secondary** signal for "does this text read like a fake job ad". Do not expect it to classify emails on its own.
- Usage: build text = `title + description + requirements + benefits + company_profile` (fill NaN with ""), label = `fraudulent`.

### 3.2 Hinglish & English scam text (Hugging Face)

- URL: https://huggingface.co/datasets/bolewara/hinglish-scam-text-dataset
- License cc-by-4.0. Total 3,787 rows. Labels: `0` benign, `1` scam.
- Composition (from dataset card): English benign ~3,000 and English scam ~700 (mostly **SMS Spam Collection**), **only 35 Hinglish scam + 28 Hinglish benign** hand-written rows.
- Format: a JSON file shaped like `{"rows": [{"text": "...", "label": 0|1}, ...]}`.
- **Trap:** the Hugging Face dataset viewer/`datasets.load_dataset` fails on this repo (JSON parse error). **Do not use `load_dataset`.** Instead:
  1. `from huggingface_hub import HfApi, hf_hub_download`
  2. `HfApi().list_repo_files("bolewara/hinglish-scam-text-dataset", repo_type="dataset")` → pick the `.json` file
  3. `hf_hub_download(...)` → `json.load` → accept either a top-level list or `{"rows": [...]}`; each item may be `{"text","label"}` or `{"row": {"text","label"}}`.
  4. Save a copy to `data/raw/hinglish_scam.json` so the build is reproducible offline.
- **Caveat:** SMS spam ≠ job scams, and Hinglish rows are tiny (63). So:
  - **Upsample the Hinglish rows ×10** in training (and keep them out of the English-only metric).
  - Hand-written **rule keywords** for Hinglish (see §6.2) matter more than the ML model for Hinglish.
- Fallback: if either dataset is missing, train on whatever exists; if neither exists, skip ML and run **rules only**. The app must never crash because a dataset is missing; show a small sidebar notice "ML model: off (rules only)".

---

## 4. Architecture

```
          ┌────────────────────┐
 inbox    │  ingest.py         │  JSON / .mbox  →  list[Email]
 (.json/  └─────────┬──────────┘
  .mbox)            ▼
          ┌────────────────────┐
          │  normalize.py      │  clean text, extract sender domain,
          └─────────┬──────────┘  company + role guess
                    ▼
          ┌────────────────────┐        ┌──────────────────────┐
          │  classify.py       │◄───────│ scam.py              │
          │  (1 label / email) │  scam  │  rules + ML score    │
          │  scam checked 1st  │        └──────────┬───────────┘
          └─────────┬──────────┘                   │ loads
                    ▼                       ┌──────▼──────────┐
          ┌────────────────────┐            │ models/scam.joblib│ (trained by
          │  tracker.py        │            └──────────────────┘  train.py)
          │  group by app key, │
          │  state machine     │
          └─────────┬──────────┘
                    ▼
          ┌────────────────────┐
          │  followups.py      │  applied + ≥7 days silent → reminder + draft
          └─────────┬──────────┘
                    ▼
          ┌────────────────────┐
          │  app.py (Streamlit)│  tracker table, red scam panel,
          └────────────────────┘  follow-ups, "simulate new email"
```

### Project structure

```
job-hunt-autopilot/
├── README.md
├── DECISIONS.md                 # agent logs any assumption here
├── requirements.txt
├── app.py                       # Streamlit UI (thin)
├── autopilot/
│   ├── __init__.py
│   ├── models.py                # dataclasses / pydantic
│   ├── ingest.py                # load_json(path), load_mbox(path)
│   ├── normalize.py
│   ├── status_rules.py          # regex lists for applied/interview/rejected/offer
│   ├── scam_rules.py            # weighted signals + reasons
│   ├── scam_ml.py               # load model, predict_proba
│   ├── classify.py              # classify_email(email) -> Classification
│   ├── tracker.py               # build_tracker(classified_emails) -> list[Application]
│   ├── followups.py             # due_followups(apps, today) -> list[FollowUp]
│   └── pipeline.py              # run(emails, today) -> PipelineResult
├── scripts/
│   ├── download_data.py
│   └── train.py                 # trains + saves models/scam.joblib, prints metrics
├── data/
│   ├── raw/                     # fake_job_postings.csv, hinglish_scam.json (gitignored if large)
│   └── sample_inbox.json        # the 20-email demo inbox (provided separately)
├── models/                      # scam.joblib
├── output/                      # tracker.json
└── tests/
    ├── test_status_rules.py
    ├── test_scam_rules.py
    ├── test_tracker.py
    ├── test_followups.py
    └── test_sample_inbox.py     # acceptance test, see §9
```

`requirements.txt`: `streamlit, pandas, scikit-learn, joblib, python-dateutil, huggingface_hub, pytest` (add `kaggle` as optional).

---

## 5. Data model

### 5.1 Input JSON schema (list of emails)

```json
{
  "id": "e01",
  "from_name": "Acme Robotics Careers",
  "from_email": "careers@acmerobotics.com",
  "to": "me@example.com",
  "subject": "Application received: Backend Engineer",
  "date": "2026-10-05T10:12:00+05:30",
  "body": "plain text body"
}
```

`.mbox` loader must output the same structure (use stdlib `mailbox` + `email`; prefer `text/plain`, strip HTML tags if only HTML exists; parse `Date` header; missing fields → empty string).

### 5.2 Internal types (`models.py`)

```python
Label = Literal["applied","interview","rejected","offer","scam","other"]

class Email:            id, from_name, from_email, sender_domain, to, subject, date(datetime, tz-aware), body

class Classification:   email_id, label: Label,
                        confidence: float,            # 0..1
                        reasons: list[str],           # human-readable, shown in UI
                        scam_score: float,            # 0..1, always computed for every email
                        company: str | None, role: str | None

class Application:      key, company, role,
                        status: Literal["applied","interview","rejected","offer"],
                        first_seen: date, last_activity: date,
                        history: list[(date, label, email_id)],
                        needs_followup: bool, days_silent: int

class ScamAlert:        email_id, from_email, subject, date,
                        scam_score, reasons: list[str], claimed_company: str | None

class FollowUp:         application_key, company, role, applied_on, days_silent, draft_text
```

---

## 6. Classification logic

**Order of operations per email (important):**

1. Compute `scam_score` (rules + ML) for **every** email.
2. If `scam_score >= 0.60` → `label="scam"`, stop. (Scam wins even if the text says "offer letter".)
3. Else run status rules in this priority order: `offer` → `interview` → `rejected` → `applied` → else `other`.
   (Priority matters: "we regret... offer" style phrases; "interview" mail often also says "thank you for applying".)

### 6.1 Status rules (`status_rules.py`) — case-insensitive regex on `subject + " " + body`

Return the first matching label plus the matched phrase as a reason (e.g. `Matched "regret to inform"`).

- **offer**: `offer letter`, `pleased to offer`, `delighted to (extend|offer)`, `extend an offer`, `we are happy to offer`, `compensation (details|package)`, `accept(ance)? (of )?(the )?offer`
- **interview**: `interview (invit|schedule|slot|round)`, `invite you (for|to) (an? )?(\w+ )?interview`, `schedule (a|an) (video )?(call|interview)`, `next (round|steps)`, `technical (round|interview|assessment)`, `shortlisted`, `availability for`
- **rejected**: `regret to inform`, `not (be )?moving forward`, `will not be moving forward`, `move forward with other candidates`, `unfortunately`, `not selected`, `decided not to proceed`, `position has been filled`
- **applied**: `application (has been )?(received|submitted)`, `received your application`, `thank(s| you) for applying`, `thank you for your interest`, `we acknowledge receipt`, `successfully (applied|submitted)`
- Guard: emails from known job-alert/newsletter patterns (`noreply`, `jobalerts`, `unsubscribe`, `new jobs for`) → `other`, unless scam.

Guard against false positives: `unfortunately` alone should NOT trigger `rejected` unless the text also contains `application|candidacy|position|role`.

### 6.2 Scam signals (`scam_rules.py`)

Each signal has a **weight** and a **reason string**. `rule_score = min(1.0, sum(weights))`. All fired reasons are returned (shown in red in UI).

| Signal                                                                                                                                                                                                                                                                  | Weight         | Reason shown                                                                       |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- | ---------------------------------------------------------------------------------- |
| Asks for money:`registration fee`, `training fee`, `security deposit`, `processing fee`, `laptop deposit`, `pay (rs\.?                                                                                                                                        | ₹             | inr)`, `refundable`, `kit charges`; Hinglish: `fee .* (bhej                  |
| Asks for sensitive docs/data:`aadhaar`, `pan card`, `passport`, `bank (details\|passbook\|account)`, `OTP`, `cvv`, `photo of .* card`; Hinglish: `aadhaar number`, `otp share`                                                                          | **0.45** | "Requests sensitive ID/bank/OTP details before any hiring process"                 |
| Sender uses free mail (`gmail.com, yahoo.*, outlook.com, hotmail.com, rediffmail.com`) **and** claims a known/large company (display name or body mentions TCS, Infosys, Wipro, Google, Amazon, Microsoft, Accenture, Cognizant, HCL, Flipkart, Reliance, etc.) | **0.40** | "Claims to be<Company></company> but emails from a free <domain></domain> address" |
| "Selected/pre-selected without interview":`without (an )?interview`, `no interview`, `pre-selected`, `direct selection`; Hinglish: `selection ho gaya`                                                                                                        | **0.30** | "Offer with no interview or application on your part"                              |
| Moves chat off-platform:`whatsapp`, `telegram` + a phone/handle                                                                                                                                                                                                     | **0.25** | "Pushes conversation to WhatsApp/Telegram"                                         |
| Urgency/pressure:`within 24 hours`, `urgent`, `limited seats`, `only today`, `offer will be cancelled`; Hinglish: `jaldi`, `sirf aaj`                                                                                                                     | **0.20** | "Artificial urgency / pressure"                                                    |
| Unrealistic pay:`earn rs\.? ?\d{4,} per day`, `no experience needed` + salary, `work from home` + high pay                                                                                                                                                        | **0.25** | "Unrealistic pay for no skills"                                                    |
| Shortened/odd links (`bit.ly`, `tinyurl`, raw IP)                                                                                                                                                                                                                   | **0.20** | "Contains shortened/suspicious link"                                               |
| ALL-CAPS subject ratio > 0.5 or ≥3 exclamation marks                                                                                                                                                                                                                   | **0.10** | "Shouty formatting"                                                                |

Hinglish keyword lists must live in a single constant `HINGLISH_SCAM_TERMS` so they are easy to extend.

### 6.3 ML scam model (`scam_ml.py`, `scripts/train.py`)

- Training data = Kaggle postings (label `fraudulent`) + HF rows (label 1 scam / 0 benign, Hinglish ×10 upsampled).
- Text cleaning: lowercase, strip HTML, collapse whitespace, keep digits/currency symbols.
- Pipeline: `FeatureUnion[TfidfVectorizer(word 1-2gram, min_df=2, max_features=50k), TfidfVectorizer(char_wb 3-5gram, max_features=100k)]` → `LogisticRegression(class_weight="balanced", max_iter=1000)`.
- `train.py` prints precision/recall/F1 on a stratified 80/20 split **per source** (Kaggle, HF-English, HF-Hinglish) and saves `models/scam.joblib`.
- `predict_proba(text) -> float`.
- **Combination:** `scam_score = max(rule_score, 0.5*rule_score + 0.5*ml_prob)` — rules can never be dragged down by the ML model, the ML only boosts. If ML is unavailable, `scam_score = rule_score`.
- Also expose top-5 contributing n-gram features for the reason list **only if** `ml_prob >= 0.7` (e.g. "Model also flags wording like: 'registration fee', 'selected'"). Skip if it complicates; rules reasons are enough.
- Because of domain mismatch (ads/SMS vs emails), **rules are the source of truth**. Do not tune thresholds to make ML dominate.

### 6.4 Company/role extraction (`normalize.py`)

- **Company:** sender display name with suffix words stripped (`Careers, HR, Talent, Hiring, Recruiting, Team, Department, Recruitment`) → else title-cased domain root (`hr@zenithtech.io` → `Zenith Tech` via simple split is optional; `Zenithtech` acceptable). Also try regex `at ([A-Z][\w& ]+)` in subject/body. Normalize for keying: lowercase, strip punctuation/legal suffixes (`pvt ltd, inc, llc`).
- **Role:** regex on subject/body: `(?:for|as) (?:the |an? )?(.+?) (?:position|role|post|job)` or after `:`/`-` in subject (`Application received: Backend Engineer`). If not found → `None`.
- Matching key = `normalized_company + "|" + normalized_role` ; if role missing, `normalized_company` and attach to that company's only open application if exactly one exists, else create a role-less application.
- Known limitation is acceptable: sender-domain root is the strongest company signal, since reply emails keep the same domain.

---

## 7. Tracker + follow-ups

### 7.1 State machine (`tracker.py`)

- Consider only emails labelled `applied/interview/rejected/offer` (scam and other are excluded from the tracker).
- Group by application key; sort history by date.
- **Status = highest-progress label in history, with rejection as a terminal state:**
  - Rank: `applied(1) < interview(2) < offer(3)`; `rejected` ends the application unless a *later-dated* `offer` or `interview` email arrives (then the later one wins).
  - Simple rule that implements this: iterate chronologically; an `applied` email never lowers an existing status; any other label overwrites the current status.
- `last_activity` = date of newest email in the group. `first_seen` = oldest.
- If an interview/offer/rejection arrives with **no prior applied email** (user applied elsewhere), still create the application.

### 7.2 Follow-ups (`followups.py`)

- `days_silent = (today - last_activity).days`
- `needs_followup = status == "applied" and days_silent >= 7`
- Sort by `days_silent` desc.
- `draft_text` template (plain text, no LLM):
  ```
  Subject: Following up on my application — {role}
  Hi {company} team,
  I applied for the {role} position on {applied_on} and wanted to check on the status of my application.
  I'm very interested in the role and happy to share anything else you need.
  Thanks for your time,
  <Your name>
  ```
- `role` missing → "the open position".

---

## 8. UI spec (Streamlit `app.py`)

Single page, wide layout, light theme.

**Sidebar**

- File uploader (`.json`, `.mbox`) + button "Load sample inbox" (loads `data/sample_inbox.json`)
- Date input "Today (for 7-day rule)", default real today; sample button sets it to **2026-10-24**
- ML status badge: "Scam ML: on (F1 x.xx)" / "off (rules only)"

**Header**: title "Job Hunt Autopilot", tagline "Track every application. Catch every fake offer.", one-line layoff story.

**KPI row** (st.metric): Total applications · Applied · Interview · Offer · Rejected · 🚩 Scams caught · ⏰ Follow-ups due

**Section 1 — Application tracker** (`st.dataframe`/custom HTML table)
Columns: Company · Role · Status (colored pill: applied=gray, interview=blue, offer=green, rejected=muted red text/strikethrough) · Applied on · Last activity · Days silent · Follow-up (⏰ if due).
Filter chips by status.

**Section 2 — 🚩 Fake offers flagged** (red cards, `st.error`-style or custom red border)
Each card: sender (name + address), subject, date, scam score as a bar/percent, **bulleted reasons** (every fired rule), claimed company if any. Expander "Show email". Cards sorted by score desc. This section is the visual hero of the demo.

**Section 3 — ⏰ Follow-ups due**
Each: company/role, "Applied N days ago, no reply", expander with the draft + a copy button (`st.code(draft)` is fine).

**Section 4 — Add an email (simulate "self-updating")**
A small form (from_email, from_name, subject, body, date) → appends to session inbox → pipeline reruns → the tracker row changes immediately. Pre-fill buttons: "Simulate: Kiran Foods sends interview invite" and "Simulate: Pixelwave rejection". Must visibly update status + KPIs without page reload.

**Section 5 — Email log (collapsible)**: all 20 emails with assigned label + confidence + reasons (for debugging/trust).

Use `st.session_state` for the inbox list. Pipeline is fast enough to rerun on every change.

Persist results to `output/tracker.json` on each run (`default=str` for dates).

---

## 9. Acceptance criteria (the agent must make `tests/test_sample_inbox.py` pass)

Use `data/sample_inbox.json` (20 emails, provided alongside this doc) with `today = 2026-10-24`. Expected:

**Per-email labels**

| id                                          | Expected label |
| ------------------------------------------- | -------------- |
| e01, e02, e04, e06, e09, e10, e11, e13, e15 | applied        |
| e03, e07, e14                               | interview      |
| e05, e12                                    | rejected       |
| e08                                         | offer          |
| e16, e17, e18, e19                          | scam           |
| e20                                         | other          |

**Tracker (9 applications)**

| Company       | Role                      | Status    | Follow-up due           |
| ------------- | ------------------------- | --------- | ----------------------- |
| Acme Robotics | Backend Engineer          | applied   | **Yes** (19 days) |
| Zenith Tech   | Data Analyst              | interview | No                      |
| Nimbus Cloud  | DevOps Engineer           | rejected  | No                      |
| Orbit Labs    | Full Stack Developer      | offer     | No                      |
| Pixelwave     | QA Engineer               | applied   | No (4 days)             |
| Kiran Foods   | Operations Manager        | applied   | **Yes** (14 days) |
| Finlytics     | Business Analyst          | rejected  | No                      |
| Cloudbase     | Site Reliability Engineer | interview | No                      |
| Brightlane    | Product Analyst           | applied   | **Yes** (12 days) |

**KPIs:** 9 applications · 3 applied-at-risk follow-ups (Acme, Kiran Foods, Brightlane) · 4 scams · 1 offer (genuine, Orbit Labs) · 2 rejected · 2 interview.

**Scam reasons (minimum required)**

- e16: fee demand, no-interview selection, urgency, free-mail sender claiming TCS
- e17: sensitive documents, WhatsApp, unrealistic pay, free-mail
- e18: Hinglish fee demand (`training fee … UPI`), OTP/Aadhaar request, urgency (`jaldi`, `sirf aaj`)
- e19: free-mail sender claiming Google, passport request, security deposit, no interview, Telegram
- **Zero false positives:** none of e01–e15 or e20 may be labelled scam. In particular the real offer **e08** must stay `offer`, not scam.

**Other checks**

- Loading the same inbox twice yields identical tracker (idempotent).
- Adding an interview-invite email from `hr@kiranfoods.in` flips Kiran Foods to `interview` and removes its follow-up.
- Missing datasets → app still runs (rules only) and tests still pass.
- `python -m scripts.train` prints per-source metrics without error when both datasets are present.
- `streamlit run app.py` starts with no exceptions on the sample inbox.

---

## 10. Build plan (2.5 hours)

| Time       | Milestone                                                                              | Done when                                  |
| ---------- | -------------------------------------------------------------------------------------- | ------------------------------------------ |
| 0:00–0:15 | Scaffold repo,`requirements.txt`, `models.py`, `ingest.py` (json + mbox)         | Sample inbox loads to`list[Email]`       |
| 0:15–0:40 | `normalize.py`, `status_rules.py`, `scam_rules.py`, `classify.py` (rules only) | e01–e20 labelled per §9 using rules only |
| 0:40–1:05 | `tracker.py`, `followups.py`, `pipeline.py`, tests green                         | §9 tracker table matches                  |
| 1:05–1:35 | `app.py` Streamlit UI: KPIs, tracker, red scam cards, follow-ups                     | Demo flow works end to end                 |
| 1:35–2:05 | `download_data.py`, `train.py`, `scam_ml.py`, wire ML boost + sidebar badge      | Metrics print, ML on/off graceful          |
| 2:05–2:25 | "Add an email" simulate section, email log, polish colors                              | Tracker visibly updates live               |
| 2:25–2:30 | README with run steps + 60-second demo script                                          | Fresh clone runs in 3 commands             |

**Cut order if time runs short:** (1) ML model, (2) .mbox ingest, (3) email log section. Never cut: rules, tracker, red scam cards, follow-ups.

---

## 11. Instructions to the coding agent

1. Read this whole file first, then `data/sample_inbox.json`.
2. Build in the order of §10. After each milestone run `pytest`.
3. Write tests **before** polishing UI. The §9 acceptance test is the definition of done.
4. Keep modules small and pure (no Streamlit imports outside `app.py`). Type hints everywhere.
5. Every classification must carry `reasons` (explainability is a feature).
6. Do not add features from §1 "OUT of scope". Do not add Gmail integration, auth, databases, or LLM calls.
7. Timezone handling: parse all dates tz-aware; compute `days_silent` on dates (`date()`), not datetimes.
8. Keep a `DECISIONS.md` with any assumption you made.
9. Final deliverable: working `streamlit run app.py`, passing `pytest`, README with setup (`pip install -r requirements.txt`, place datasets, `python -m scripts.train`, run app).

---

## 12. 60-second demo script

1. "Laid off, 100+ applications, inbox is chaos." → click **Load sample inbox**.
2. KPIs appear: 9 applications, 1 offer, 2 interviews, 2 rejections.
3. Scroll to **🚩 Fake offers**: "4 emails that looked like offers. Here's why each is fake — a ₹4,500 'registration fee' from a Gmail address pretending to be TCS, and a Hinglish message asking for UPI and OTP."
4. Point at the real Orbit Labs offer staying green: "No false alarm on the genuine one."
5. **⏰ Follow-ups**: "Three applications went silent for 7+ days — here's a ready draft."
6. Hit **Simulate: Kiran Foods sends interview invite** → row flips to Interview, follow-up disappears. "Self-updating."
