"""app.py — Job Hunt Autopilot · Streamlit UI.

Single-page, wide layout. Thin layer over the autopilot/ package.
No Streamlit imports are allowed in any autopilot/ module.
"""

import json
import io
from datetime import date, datetime, timezone
from pathlib import Path

import streamlit as st
import pandas as pd

from autopilot.ingest import load_json, load_json_dicts, load_mbox
from autopilot.pipeline import run
from autopilot.scam_ml import is_available as ml_available, get_f1 as ml_f1

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Job Hunt Autopilot",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

SAMPLE_INBOX = Path(__file__).parent / "data" / "sample_inbox.json"
SAMPLE_DATE = date(2026, 10, 24)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
/* ── Fonts ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ── Header gradient ── */
.hero-header {
    background: linear-gradient(135deg, #1e1b4b 0%, #312e81 40%, #4338ca 100%);
    border-radius: 16px;
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    color: white;
}
.hero-header h1 {
    font-size: 2.4rem;
    font-weight: 700;
    margin: 0 0 0.25rem 0;
    letter-spacing: -0.5px;
}
.hero-header .tagline {
    font-size: 1.1rem;
    color: #c7d2fe;
    margin: 0 0 0.5rem 0;
}
.hero-header .story {
    font-size: 0.92rem;
    color: #a5b4fc;
    font-style: italic;
}

/* ── Status pills ── */
.pill {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.4px;
    text-transform: uppercase;
}
.pill-applied   { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }
.pill-interview { background: #dbeafe; color: #1d4ed8; border: 1px solid #93c5fd; }
.pill-offer     { background: #d1fae5; color: #065f46; border: 1px solid #6ee7b7; }
.pill-rejected  { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5;
                  text-decoration: line-through; }

/* ── Section headers ── */
.section-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: #1e1b4b;
    margin: 1.5rem 0 0.75rem 0;
    padding-bottom: 0.4rem;
    border-bottom: 2px solid #e0e7ff;
}

/* ── Scam card ── */
.scam-card {
    background: linear-gradient(135deg, #fff1f2 0%, #ffe4e6 100%);
    border: 2px solid #f87171;
    border-radius: 12px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.85rem;
    position: relative;
}
.scam-score-bar-outer {
    background: #fecdd3;
    border-radius: 999px;
    height: 8px;
    margin: 6px 0;
    overflow: hidden;
}
.scam-score-bar-inner {
    background: linear-gradient(90deg, #ef4444, #dc2626);
    height: 8px;
    border-radius: 999px;
    transition: width 0.4s ease;
}

/* ── Follow-up card ── */
.followup-card {
    background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
    border: 2px solid #fbbf24;
    border-radius: 12px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
}

/* ── KPI metric override ── */
[data-testid="metric-container"] {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 0.75rem 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

/* ── Filter chips ── */
.filter-row {
    display: flex;
    gap: 8px;
    margin-bottom: 1rem;
    flex-wrap: wrap;
}

/* ── Tracker table ── */
.tracker-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
}
.tracker-table th {
    background: #1e1b4b;
    color: white;
    padding: 10px 14px;
    text-align: left;
    font-weight: 600;
    font-size: 0.82rem;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
.tracker-table td {
    padding: 10px 14px;
    border-bottom: 1px solid #f1f5f9;
    vertical-align: middle;
}
.tracker-table tr:hover td {
    background: #f8fafc;
}

/* ── Sidebar ── */
.sidebar-badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 600;
}
.badge-on  { background: #d1fae5; color: #065f46; }
.badge-off { background: #f1f5f9; color: #64748b; }
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------
def _init_session():
    if "email_dicts" not in st.session_state:
        st.session_state["email_dicts"] = []
    if "today" not in st.session_state:
        st.session_state["today"] = date.today()
    if "pipeline_result" not in st.session_state:
        st.session_state["pipeline_result"] = None
    if "status_filter" not in st.session_state:
        st.session_state["status_filter"] = "All"


def _run_pipeline():
    """Run pipeline on current session_state emails."""
    dicts = st.session_state["email_dicts"]
    if not dicts:
        st.session_state["pipeline_result"] = None
        return
    emails = load_json_dicts(dicts)
    result = run(emails, today=st.session_state["today"])
    st.session_state["pipeline_result"] = result


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def _sidebar():
    with st.sidebar:
        st.markdown("## ⚙️ Controls")

        # File uploader
        uploaded = st.file_uploader(
            "Upload inbox (.json or .mbox)",
            type=["json", "mbox"],
            key="uploader",
        )
        if uploaded:
            try:
                if uploaded.name.endswith(".json"):
                    content = json.loads(uploaded.read().decode("utf-8"))
                    if not isinstance(content, list):
                        st.error("JSON must be a list of email objects.")
                    else:
                        st.session_state["email_dicts"] = content
                        st.session_state["today"] = date.today()
                        _run_pipeline()
                        st.success(f"Loaded {len(content)} emails.")
                elif uploaded.name.endswith(".mbox"):
                    # Write to temp file
                    tmp_path = Path("output") / "tmp_upload.mbox"
                    tmp_path.parent.mkdir(parents=True, exist_ok=True)
                    tmp_path.write_bytes(uploaded.read())
                    emails = load_mbox(tmp_path)
                    st.session_state["email_dicts"] = [
                        {
                            "id": e.id, "from_name": e.from_name,
                            "from_email": e.from_email, "to": e.to,
                            "subject": e.subject,
                            "date": e.date.isoformat(),
                            "body": e.body,
                        }
                        for e in emails
                    ]
                    _run_pipeline()
                    st.success(f"Loaded {len(emails)} emails from mbox.")
            except Exception as exc:
                st.error(f"Failed to load: {exc}")

        # Load sample inbox
        if st.button("📂 Load sample inbox", use_container_width=True):
            try:
                with open(SAMPLE_INBOX, "r", encoding="utf-8") as f:
                    content = json.load(f)
                st.session_state["email_dicts"] = content
                st.session_state["today"] = SAMPLE_DATE
                _run_pipeline()
                st.success(f"Loaded {len(content)} sample emails.")
            except Exception as exc:
                st.error(f"Cannot load sample inbox: {exc}")

        st.divider()

        # Date picker
        today_val = st.date_input(
            "📅 Today (for 7-day rule)",
            value=st.session_state["today"],
            key="today_input",
        )
        if today_val != st.session_state["today"]:
            st.session_state["today"] = today_val
            _run_pipeline()

        st.divider()

        # ML status badge
        if ml_available():
            f1 = ml_f1()
            f1_str = f"F1 {f1:.2f}" if f1 is not None else ""
            st.markdown(
                f'<span class="sidebar-badge badge-on">🤖 Scam ML: on {f1_str}</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<span class="sidebar-badge badge-off">⚙️ ML model: off (rules only)</span>',
                unsafe_allow_html=True,
            )
            st.caption("Run `python -m scripts.download_data` then `python -m scripts.train`")


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
def _header():
    st.markdown(
        """
<div class="hero-header">
  <h1>🚀 Job Hunt Autopilot</h1>
  <p class="tagline">Track every application. Catch every fake offer.</p>
  <p class="story">
    After a layoff you apply to 100+ roles. Autopilot tells you who replied,
    who rejected you, who to nudge today — and which "offers" are traps.
  </p>
</div>
""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
def _kpi_row(result):
    apps = result.applications
    total = len(apps)
    n_applied = sum(1 for a in apps if a.status == "applied")
    n_interview = sum(1 for a in apps if a.status == "interview")
    n_offer = sum(1 for a in apps if a.status == "offer")
    n_rejected = sum(1 for a in apps if a.status == "rejected")
    n_scam = len(result.scam_alerts)
    n_followup = len(result.followups)

    cols = st.columns(7)
    cols[0].metric("📋 Total", total)
    cols[1].metric("📤 Applied", n_applied)
    cols[2].metric("🎯 Interview", n_interview)
    cols[3].metric("🟢 Offer", n_offer)
    cols[4].metric("❌ Rejected", n_rejected)
    cols[5].metric("🚩 Scams caught", n_scam)
    cols[6].metric("⏰ Follow-ups due", n_followup)


# ---------------------------------------------------------------------------
# Status pill HTML
# ---------------------------------------------------------------------------
def _pill(status: str) -> str:
    return f'<span class="pill pill-{status}">{status}</span>'


# ---------------------------------------------------------------------------
# Section 1 — Application Tracker
# ---------------------------------------------------------------------------
def _section_tracker(result):
    st.markdown('<div class="section-title">📊 Application Tracker</div>', unsafe_allow_html=True)

    apps = result.applications
    if not apps:
        st.info("No applications tracked yet.")
        return

    # Filter chips
    all_statuses = ["All", "applied", "interview", "offer", "rejected"]
    filter_cols = st.columns(len(all_statuses))
    for i, status in enumerate(all_statuses):
        label = {
            "All": "🗂️ All",
            "applied": "📤 Applied",
            "interview": "🎯 Interview",
            "offer": "🟢 Offer",
            "rejected": "❌ Rejected",
        }[status]
        if filter_cols[i].button(label, key=f"filter_{status}", use_container_width=True):
            st.session_state["status_filter"] = status

    active_filter = st.session_state.get("status_filter", "All")
    filtered = apps if active_filter == "All" else [a for a in apps if a.status == active_filter]

    # Build table HTML
    rows_html = ""
    for app in sorted(filtered, key=lambda a: a.last_activity, reverse=True):
        followup_icon = "⏰" if app.needs_followup else ""
        days_str = str(app.days_silent)
        rows_html += f"""
        <tr>
          <td><strong>{app.company}</strong></td>
          <td>{app.role or '<em style="color:#94a3b8">—</em>'}</td>
          <td>{_pill(app.status)}</td>
          <td>{app.first_seen}</td>
          <td>{app.last_activity}</td>
          <td>{days_str}</td>
          <td style="text-align:center;font-size:1.2rem">{followup_icon}</td>
        </tr>"""

    table_html = f"""
    <table class="tracker-table">
      <thead>
        <tr>
          <th>Company</th><th>Role</th><th>Status</th>
          <th>Applied on</th><th>Last activity</th><th>Days silent</th><th>Follow-up</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>"""
    st.markdown(table_html, unsafe_allow_html=True)
    st.caption(f"Showing {len(filtered)} of {len(apps)} applications · Filter: {active_filter}")


# ---------------------------------------------------------------------------
# Section 2 — 🚩 Fake Offers
# ---------------------------------------------------------------------------
def _section_scam(result):
    scams = result.scam_alerts
    st.markdown(
        f'<div class="section-title">🚩 Fake Offers Flagged ({len(scams)})</div>',
        unsafe_allow_html=True,
    )

    if not scams:
        st.success("✅ No suspicious emails detected.")
        return

    for alert in scams:
        score_pct = int(alert.scam_score * 100)
        bar_width = score_pct
        claimed = f" · claiming to be **{alert.claimed_company}**" if alert.claimed_company else ""

        reasons_html = "".join(f"<li>⚠️ {r}</li>" for r in alert.reasons)

        card_html = f"""
<div class="scam-card">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div>
      <strong style="color:#b91c1c;font-size:1rem">📛 {alert.subject}</strong><br>
      <span style="color:#6b7280;font-size:0.85rem">From: {alert.from_email}{claimed}</span><br>
      <span style="color:#9ca3af;font-size:0.8rem">{str(alert.date)[:16]}</span>
    </div>
    <div style="text-align:right;min-width:90px">
      <div style="font-size:1.4rem;font-weight:700;color:#dc2626">{score_pct}%</div>
      <div style="font-size:0.7rem;color:#9ca3af">scam score</div>
    </div>
  </div>
  <div class="scam-score-bar-outer">
    <div class="scam-score-bar-inner" style="width:{bar_width}%"></div>
  </div>
  <ul style="margin:8px 0 0 0;padding-left:1.2rem;color:#7f1d1d;font-size:0.88rem">
    {reasons_html}
  </ul>
</div>"""
        st.markdown(card_html, unsafe_allow_html=True)

        # Find the original email body for expander
        orig_email = None
        for e in result.emails:
            if e.id == alert.email_id:
                orig_email = e
                break
        if orig_email:
            with st.expander(f"📧 Show email · {alert.email_id}"):
                st.markdown(f"**Subject:** {orig_email.subject}")
                st.markdown(f"**From:** {orig_email.from_name} `<{orig_email.from_email}>`")
                st.text(orig_email.body)


# ---------------------------------------------------------------------------
# Section 3 — ⏰ Follow-ups
# ---------------------------------------------------------------------------
def _section_followups(result):
    followups = result.followups
    st.markdown(
        f'<div class="section-title">⏰ Follow-ups Due ({len(followups)})</div>',
        unsafe_allow_html=True,
    )

    if not followups:
        st.success("✅ No follow-ups needed right now.")
        return

    for fu in followups:
        role_str = fu.role or "Open position"
        card_html = f"""
<div class="followup-card">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div>
      <strong style="font-size:1rem;color:#92400e">{fu.company}</strong>
      <span style="color:#b45309"> · {role_str}</span>
    </div>
    <div style="background:#fef3c7;border:1px solid #fbbf24;border-radius:8px;padding:4px 12px;
                font-size:0.82rem;font-weight:600;color:#92400e">
      {fu.days_silent} days silent
    </div>
  </div>
  <div style="color:#78350f;font-size:0.85rem;margin-top:6px">
    Applied {fu.applied_on} — no reply yet. Time to follow up!
  </div>
</div>"""
        st.markdown(card_html, unsafe_allow_html=True)
        with st.expander(f"📝 Draft follow-up email · {fu.company}"):
            st.code(fu.draft_text, language=None)
            st.caption("Copy and paste to send via your email client.")


# ---------------------------------------------------------------------------
# Section 4 — Add an Email (simulate)
# ---------------------------------------------------------------------------
def _section_simulate(result):
    st.markdown('<div class="section-title">✉️ Add an Email (Simulate Self-Updating)</div>', unsafe_allow_html=True)

    # Quick pre-fill buttons
    btn_cols = st.columns(2)
    if btn_cols[0].button("📨 Simulate: Kiran Foods interview invite", use_container_width=True):
        st.session_state["sim_from_email"] = "hr@kiranfoods.in"
        st.session_state["sim_from_name"] = "Kiran Foods HR"
        st.session_state["sim_subject"] = "Interview invitation: Operations Manager"
        st.session_state["sim_body"] = (
            "Hi, we would like to invite you for an interview for the Operations Manager role. "
            "Please confirm your availability for next week."
        )
        st.session_state["sim_date"] = "2026-10-23T10:00:00+05:30"

    if btn_cols[1].button("📨 Simulate: Pixelwave rejection", use_container_width=True):
        st.session_state["sim_from_email"] = "careers@pixelwave.dev"
        st.session_state["sim_from_name"] = "Pixelwave Careers"
        st.session_state["sim_subject"] = "Update on your application - QA Engineer"
        st.session_state["sim_body"] = (
            "Thank you for your interest. Unfortunately, we have decided not to proceed "
            "with your application for the QA Engineer position at this time."
        )
        st.session_state["sim_date"] = "2026-10-23T15:00:00+05:30"

    with st.form("add_email_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        from_email = col1.text_input(
            "From email", value=st.session_state.get("sim_from_email", ""), key="f_from_email"
        )
        from_name = col2.text_input(
            "From name", value=st.session_state.get("sim_from_name", ""), key="f_from_name"
        )
        subject = st.text_input(
            "Subject", value=st.session_state.get("sim_subject", ""), key="f_subject"
        )
        body = st.text_area(
            "Body", value=st.session_state.get("sim_body", ""), height=100, key="f_body"
        )
        date_str = st.text_input(
            "Date (ISO)", value=st.session_state.get("sim_date", datetime.now(timezone.utc).isoformat()), key="f_date"
        )

        submitted = st.form_submit_button("➕ Add & Rerun Pipeline", use_container_width=True)
        if submitted:
            if not from_email or not subject:
                st.error("From email and Subject are required.")
            else:
                existing = st.session_state.get("email_dicts", [])
                new_id = f"sim_{len(existing)+1:04d}"
                new_email = {
                    "id": new_id,
                    "from_name": from_name,
                    "from_email": from_email,
                    "to": "me@example.com",
                    "subject": subject,
                    "date": date_str,
                    "body": body,
                }
                existing.append(new_email)
                st.session_state["email_dicts"] = existing
                # Clear sim state
                for k in ["sim_from_email","sim_from_name","sim_subject","sim_body","sim_date"]:
                    st.session_state.pop(k, None)
                _run_pipeline()
                st.success(f"Added email `{new_id}`. Pipeline updated!")
                st.rerun()


# ---------------------------------------------------------------------------
# Section 5 — Email Log
# ---------------------------------------------------------------------------
def _section_email_log(result):
    with st.expander("📋 Email Log (all emails with labels)", expanded=False):
        email_map = {e.id: e for e in result.emails}
        rows = []
        for clf in result.classifications:
            e = email_map.get(clf.email_id)
            if e:
                rows.append(
                    {
                        "ID": clf.email_id,
                        "From": e.from_email,
                        "Subject": e.subject[:60] + ("..." if len(e.subject) > 60 else ""),
                        "Label": clf.label,
                        "Confidence": f"{clf.confidence:.0%}",
                        "Scam Score": f"{clf.scam_score:.0%}",
                        "Reasons": "; ".join(clf.reasons[:2]),
                    }
                )
        df = pd.DataFrame(rows)

        def _color_label(val):
            colors = {
                "applied": "#f1f5f9",
                "interview": "#dbeafe",
                "offer": "#d1fae5",
                "rejected": "#fee2e2",
                "scam": "#fecaca",
                "other": "#f8fafc",
            }
            return f"background-color: {colors.get(val, 'white')}"

        styled = df.style.applymap(_color_label, subset=["Label"])
        st.dataframe(styled, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------
def main():
    _init_session()
    _sidebar()
    _header()

    result = st.session_state.get("pipeline_result")

    if result is None:
        st.markdown(
            """
<div style="background:#f8fafc;border:2px dashed #cbd5e1;border-radius:12px;padding:3rem;text-align:center;margin-top:2rem">
  <div style="font-size:3rem">📬</div>
  <h2 style="color:#1e1b4b;margin:0.5rem 0">Load your inbox to get started</h2>
  <p style="color:#64748b">Click <strong>"📂 Load sample inbox"</strong> in the sidebar to see a demo,
  or upload your own <code>.json</code> / <code>.mbox</code> file.</p>
</div>""",
            unsafe_allow_html=True,
        )
        return

    _kpi_row(result)
    st.divider()
    _section_tracker(result)
    st.divider()
    _section_scam(result)
    st.divider()
    _section_followups(result)
    st.divider()
    _section_simulate(result)
    st.divider()
    _section_email_log(result)


if __name__ == "__main__":
    main()
