from __future__ import annotations

import html
import json

import pandas as pd
import streamlit as st

from src.actions import WritebackAgent
from src.config import DEFAULT_DB_PATH, SAMPLE_NOTES_DIR
from src.critic import EvidenceCriticAgent
from src.crm_chat import answer_question
from src.database import connect, dataframe, ensure_database, run_eda, table_counts
from src.extraction import ExtractionAgent
from src.schemas import MatchResult, ReviewPackage, ValidationResult
from src.validation import ValidationAgent


st.set_page_config(page_title="RepLog AI", page_icon="RL", layout="wide")


def ensure_db() -> None:
    ensure_database(DEFAULT_DB_PATH)


@st.cache_data(show_spinner=False)
def cached_eda() -> dict:
    return run_eda()


def load_sample_notes() -> dict[str, str]:
    notes = {}
    for path in sorted(SAMPLE_NOTES_DIR.glob("*.txt")):
        label = path.stem.replace("_", " ").title()
        notes[label] = path.read_text(encoding="utf-8")
    return notes


def crm_context() -> str:
    eda = cached_eda()
    candidates = eda["integrity"]["demo_candidates"][:12]
    return json.dumps(
        {
            "known_data_quirks": {
                "product_alias": "Pipeline often uses GTXPro while product catalog uses GTX Pro."
            },
            "demo_open_opportunities": candidates,
        },
        indent=2,
    )


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .stApp {background: #f3f5f7;}
        .block-container {
            padding-top: 2rem;
            max-width: 1240px;
            color: #111827 !important;
        }
        .block-container h1,
        .block-container h2,
        .block-container h3,
        .block-container h4,
        .block-container p,
        .block-container span,
        .block-container label {
            color: #111827 !important;
        }
        [data-testid="stSidebar"] {
            background: #1f2937;
            border-right: 1px solid #374151;
        }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] label {color: #f9fafb !important;}
        [data-testid="stSidebar"] [role="radiogroup"] label {
            background: transparent;
            border-radius: 8px;
            padding: 8px 10px;
        }
        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        [data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
            background: #ffffff !important;
            color: #111827 !important;
            border: 1px solid #9ca3af !important;
            border-radius: 8px !important;
        }
        [data-testid="stTextInput"] input *,
        [data-testid="stTextArea"] textarea *,
        [data-testid="stSelectbox"] *,
        [data-testid="stMultiSelect"] * {
            color: #111827 !important;
        }
        [data-testid="stTextInput"] input::placeholder,
        [data-testid="stTextArea"] textarea::placeholder {
            color: #6b7280 !important;
            opacity: 1 !important;
        }
        [data-testid="stTextInput"] label,
        [data-testid="stTextArea"] label,
        [data-testid="stSelectbox"] label,
        [data-testid="stMultiSelect"] label {
            color: #1f2937 !important;
            font-weight: 600;
        }
        [data-baseweb="popover"],
        [data-baseweb="menu"] {
            background: #ffffff !important;
            color: #111827 !important;
        }
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #cfd7e2;
            border-radius: 8px;
            padding: 14px 16px;
            box-shadow: 0 2px 8px rgba(16, 24, 40, 0.06);
        }
        [data-testid="stMetric"] * {
            color: #111827 !important;
        }
        [data-testid="stMetricLabel"] p {
            color: #4b5563 !important;
            font-weight: 600;
        }
        [data-testid="stMetricValue"] div {
            color: #111827 !important;
            font-weight: 700;
        }
        .hero {
            border: 1px solid #293548;
            border-radius: 8px;
            padding: 22px 24px;
            background: linear-gradient(135deg, #111827 0%, #243447 100%);
            margin-bottom: 16px;
            box-shadow: 0 6px 20px rgba(16, 24, 40, 0.12);
        }
        .hero h1 {font-size: 2rem; margin: 0 0 4px 0; color: #ffffff !important;}
        .hero p {margin: 0; color: #cbd5e1 !important;}
        .field-card {
            border: 1px solid #d0d7e2;
            border-left: 5px solid #2f7d5b;
            background: #fff;
            border-radius: 8px;
            padding: 12px 14px;
            min-height: 88px;
            margin-bottom: 10px;
            box-shadow: 0 2px 7px rgba(16, 24, 40, 0.06);
        }
        .field-card.missing {border-left-color: #b54708; background: #fffaf5;}
        .field-card.optional {border-left-color: #667085;}
        .field-label {font-size: .76rem; font-weight: 700; color: #596579; text-transform: uppercase; letter-spacing: .04em;}
        .field-value {font-size: .98rem; color: #111827; margin-top: 6px; line-height: 1.35;}
        .field-value.muted {color: #8a94a6;}
        .pill {
            display: inline-block;
            border-radius: 999px;
            padding: 3px 9px;
            font-size: .78rem;
            font-weight: 700;
            margin-top: 8px;
        }
        .pill.good {background: #eef8f2; color: #1f6f4a;}
        .pill.bad {background: #fff4ed; color: #b54708;}
        .pill.neutral {background: #eef2f6; color: #475467;}
        .answer-box {
            border: 1px solid #cfd7e2;
            background: #ffffff;
            border-radius: 8px;
            padding: 14px 16px;
            margin-top: 12px;
            color: #1f2937;
            line-height: 1.5;
            box-shadow: 0 2px 7px rgba(16, 24, 40, 0.06);
        }
        .correction-box {
            border: 1px solid #cfd7e2;
            border-radius: 8px;
            padding: 10px 12px;
            background: #f8fafc;
            margin: -4px 0 12px 0;
        }
        .section-card {
            border: 1px solid #cfd7e2;
            border-radius: 8px;
            padding: 16px;
            background: #fff;
        }
        .stButton > button {
            border-radius: 8px;
            font-weight: 700;
        }
        .stButton > button:disabled {
            background: #e5e7eb !important;
            color: #6b7280 !important;
            border: 1px solid #d1d5db !important;
            opacity: 1 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    st.markdown(
        """
        <div class="hero">
            <h1>RepLog AI</h1>
            <p>Turn meeting notes into reviewed CRM updates, follow-up tasks, and searchable account memory.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metrics() -> None:
    eda = cached_eda()
    counts = table_counts(DEFAULT_DB_PATH)
    with connect(DEFAULT_DB_PATH) as conn:
        meeting_count = conn.execute("SELECT COUNT(*) FROM meeting_logs").fetchone()[0]
        task_count = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'open'").fetchone()[0]
    cols = st.columns(5)
    cols[0].metric("Accounts", counts.get("accounts", 0))
    cols[1].metric("Open opportunities", eda["integrity"]["open_opportunities"])
    cols[2].metric("Products", counts.get("products", 0))
    cols[3].metric("Approved meetings", meeting_count)
    cols[4].metric("Open tasks", task_count)


def render_status_card(label: str, value: str | list[str] | None, mandatory: bool = False) -> None:
    missing = mandatory and (not value or value == "None")
    optional_empty = not mandatory and not value
    css_class = "missing" if missing else "optional" if optional_empty else ""
    status_class = "bad" if missing else "neutral" if optional_empty else "good"
    status_text = "Needs review" if missing else "Optional" if optional_empty else "Ready"
    if isinstance(value, list):
        display = ", ".join(value) if value else "Not captured"
    else:
        display = value or "Not captured"
    muted = " muted" if missing or optional_empty else ""
    st.markdown(
        f"""
        <div class="field-card {css_class}">
            <div class="field-label">{html.escape(label)}</div>
            <div class="field-value{muted}">{html.escape(str(display))}</div>
            <span class="pill {status_class}">{status_text}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def clear_review_decisions() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith("decision_") or key.startswith("override_"):
            del st.session_state[key]


def field_decision_buttons(field_key: str, locked: bool = False) -> None:
    state_key = f"decision_{field_key}"
    current = st.session_state.get(state_key, "pending")
    accept, reject = st.columns(2)
    if accept.button(
        "Accept",
        key=f"accept_{field_key}",
        use_container_width=True,
        disabled=locked or current == "rejected",
    ):
        st.session_state[state_key] = "accepted"
        st.rerun()
    if reject.button(
        "Reject",
        key=f"reject_{field_key}",
        use_container_width=True,
        disabled=locked or current == "accepted",
    ):
        st.session_state[state_key] = "rejected"
        st.rerun()
    if current == "accepted":
        st.caption("Accepted")
    elif current == "rejected":
        st.caption("Rejected")


def field_correction_controls(field_key: str, review: ReviewPackage, locked: bool = False) -> None:
    if st.session_state.get(f"decision_{field_key}") != "rejected":
        return
    options = correction_options(field_key, review)
    st.markdown("<div class='correction-box'>", unsafe_allow_html=True)
    st.caption("Replace the rejected value")
    if field_key == "products":
        st.multiselect(
            "Choose from CRM",
            options,
            key=f"override_select_{field_key}",
            disabled=locked,
        )
        st.text_input(
            "Or type product names",
            key=f"override_free_{field_key}",
            placeholder="GTX Pro, MG Advanced",
            disabled=locked,
        )
    elif field_key in {"summary", "attendees", "risks", "signals"}:
        st.text_area(
            "Manual correction",
            value=current_field_text(field_key, review),
            key=f"override_free_{field_key}",
            height=90,
            disabled=locked,
        )
    else:
        st.selectbox(
            "Choose from CRM",
            [""] + options,
            key=f"override_select_{field_key}",
            disabled=locked,
        )
        st.text_input(
            "Or type manually",
            key=f"override_free_{field_key}",
            placeholder="Manual correction",
            disabled=locked,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def correction_options(field_key: str, review: ReviewPackage) -> list[str]:
    with connect(DEFAULT_DB_PATH) as conn:
        if field_key == "account":
            return [row["account"] for row in conn.execute("SELECT account FROM accounts ORDER BY account")]
        if field_key == "products":
            return [row["product"] for row in conn.execute("SELECT product FROM products ORDER BY product")]
        if field_key == "opportunity":
            rows = conn.execute(
                """
                SELECT opportunity_id, account, product, sales_agent, deal_stage
                FROM sales_pipeline
                WHERE deal_stage IN ('Prospecting', 'Engaging', 'Proposal')
                ORDER BY account, product
                LIMIT 300
                """
            ).fetchall()
            return [
                f"{row['opportunity_id']} | {row['account'] or 'Unassigned'} | {row['product']} | {row['deal_stage']}"
                for row in rows
            ]
    if field_key == "stage":
        return ["Prospecting", "Engaging", "Proposal", "Won", "Lost"]
    return []


def current_field_text(field_key: str, review: ReviewPackage) -> str:
    proposal = review.proposal
    matched = review.validation.matched
    values = {
        "account": matched.account_name,
        "opportunity": matched.opportunity_id,
        "products": ", ".join(matched.product_names),
        "stage": proposal.suggested_stage,
        "summary": proposal.meeting_summary,
        "attendees": ", ".join(proposal.attendees),
        "risks": ", ".join(proposal.objections_or_risks),
        "signals": ", ".join(proposal.buying_signals),
    }
    return values.get(field_key) or ""


def override_value(field_key: str) -> str | list[str] | None:
    free = st.session_state.get(f"override_free_{field_key}")
    selected = st.session_state.get(f"override_select_{field_key}")
    if isinstance(free, str) and free.strip():
        if field_key in {"products", "attendees", "risks", "signals"}:
            return split_list(free)
        return free.strip()
    if selected:
        if field_key == "opportunity" and isinstance(selected, str):
            return selected.split("|", 1)[0].strip()
        return selected
    return None


def split_list(value: str) -> list[str]:
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


def has_required_correction(field_key: str) -> bool:
    return bool(override_value(field_key))


def corrected_review(review: ReviewPackage) -> ReviewPackage:
    proposal = review.proposal.model_copy(deep=True)
    matched = review.validation.matched.model_copy(deep=True)

    account = override_value("account")
    opportunity = override_value("opportunity")
    products = override_value("products")
    stage = override_value("stage")
    summary = override_value("summary")
    attendees = override_value("attendees")
    risks = override_value("risks")
    signals = override_value("signals")

    if isinstance(account, str):
        matched.account_name = account
    if isinstance(opportunity, str):
        matched.opportunity_id = opportunity
    if isinstance(products, list):
        matched.product_names = products
        proposal.products_discussed = products
    if isinstance(stage, str) and stage in {"Prospecting", "Engaging", "Proposal", "Won", "Lost"}:
        proposal.suggested_stage = stage
    if isinstance(summary, str):
        proposal.meeting_summary = summary
    if isinstance(attendees, list):
        proposal.attendees = attendees
    if isinstance(risks, list):
        proposal.objections_or_risks = risks
    if isinstance(signals, list):
        proposal.buying_signals = signals

    validation = review.validation.model_copy(update={"matched": matched}, deep=True)
    validation.is_approvable = bool(matched.account_name and matched.opportunity_id and matched.product_names)
    return review.model_copy(update={"proposal": proposal, "validation": validation}, deep=True)


def render_review(review: ReviewPackage) -> None:
    proposal = review.proposal
    matched = review.validation.matched
    review_locked = bool(st.session_state.get("last_writeback"))
    st.subheader("Review proposed CRM update")
    if review_locked:
        st.caption("This review has already been submitted and is now locked.")

    completion = int(
        sum(
            bool(value)
            for value in [
                matched.account_name,
                matched.opportunity_id,
                matched.product_names,
                proposal.meeting_summary,
            ]
        )
        / 4
        * 100
    )
    st.progress(completion, text=f"Required fields complete: {completion}%")

    fields = [
        ("account", "Account", matched.account_name, True),
        ("opportunity", "Opportunity", matched.opportunity_id, True),
        ("products", "Products", matched.product_names, True),
        ("stage", "Stage change", _stage_text(matched.opportunity_stage, proposal.suggested_stage), False),
        ("summary", "Meeting summary", proposal.meeting_summary, True),
        ("attendees", "Attendees", proposal.attendees, False),
        ("risks", "Risks and objections", proposal.objections_or_risks, False),
        ("signals", "Buying signals", proposal.buying_signals, False),
    ]

    for idx in range(0, len(fields), 2):
        left, right = st.columns(2)
        for container, field in zip([left, right], fields[idx : idx + 2]):
            with container:
                key, label, value, mandatory = field
                render_status_card(label, value, mandatory)
                field_decision_buttons(key, locked=review_locked)
                field_correction_controls(key, review, locked=review_locked)

    st.markdown("**Follow-up tasks**")
    if proposal.next_steps:
        for task in proposal.next_steps:
            owner = task.owner or matched.sales_agent or proposal.sales_agent or "Unassigned"
            due = task.due_date or "No due date"
            st.write(f"- {task.description} | Owner: {owner} | Due: {due}")
    else:
        st.caption("No task proposed.")

    with st.expander("Evidence used for the proposal"):
        if proposal.evidence:
            for item in proposal.evidence:
                st.caption(f"{item.field}: {item.quote}")
        else:
            st.caption("No evidence snippets returned.")
        if review.critic:
            st.markdown("**Grounding check**")
            st.caption(f"Overall evidence confidence: {review.critic.overall_confidence:.0%}")
            for finding in review.critic.findings:
                if finding.status in {"inferred", "missing", "contradicted"}:
                    detail = finding.concern or finding.evidence or "Needs review."
                    st.caption(f"{finding.field}: {finding.status} - {detail}")


def render_workspace() -> None:
    render_hero()
    render_metrics()
    st.divider()

    left, right = st.columns([1.18, 0.82])
    with left:
        st.subheader("Meeting note")
        sample_notes = load_sample_notes()
        choice = st.selectbox("Start from sample", ["Blank"] + list(sample_notes.keys()))
        default_note = "" if choice == "Blank" else sample_notes[choice]
        note = st.text_area("Paste a note or transcript", value=default_note, height=210)

        if st.button("Analyze note", type="primary", disabled=not note.strip(), use_container_width=True):
            with st.spinner("Preparing CRM proposal..."):
                proposal, extraction_run = ExtractionAgent().extract(note, crm_context())
                critic, critic_run = EvidenceCriticAgent().critique(note, proposal)
                with connect(DEFAULT_DB_PATH) as conn:
                    validation = ValidationAgent().validate(conn, proposal, critic)
                st.session_state["review"] = ReviewPackage(
                    proposal=proposal,
                    validation=validation,
                    source_note=note,
                    model_provider=extraction_run.provider,
                    model_name=extraction_run.model,
                    critic=critic,
                    model_runs=[extraction_run, critic_run],
                )
                clear_review_decisions()
                st.session_state.pop("last_writeback", None)

    with right:
        st.subheader("Ask CRM")
        st.caption("Ask about approved meetings, attendees, tasks, risks, or open pipeline.")
        question = st.text_input("Question", placeholder="Who attended the latest meeting?")
        if st.button("Ask", use_container_width=True) and question:
            with connect(DEFAULT_DB_PATH) as conn:
                st.session_state["crm_answer"] = answer_question(conn, question)
        if st.session_state.get("crm_answer"):
            safe_answer = html.escape(st.session_state["crm_answer"]).replace("\n", "<br>")
            st.markdown(
                f"<div class='answer-box'>{safe_answer}</div>",
                unsafe_allow_html=True,
            )

    review = st.session_state.get("review")
    if review:
        st.divider()
        render_review(review)
        rejected_fields = [
            key
            for key in ["account", "opportunity", "products", "summary"]
            if st.session_state.get(f"decision_{key}") == "rejected" and not has_required_correction(key)
        ]
        submitted = bool(st.session_state.get("last_writeback"))
        review_to_apply = corrected_review(review)
        approve_disabled = submitted or not review_to_apply.validation.is_approvable or bool(rejected_fields)
        if not review.validation.is_approvable:
            st.caption("Complete the highlighted fields before approving.")
        if rejected_fields:
            st.caption("Resolve rejected required fields before approving.")
        approve, reject = st.columns([1, 1])
        with approve:
            if st.button("Approve update", type="primary", disabled=approve_disabled, use_container_width=True):
                with connect(DEFAULT_DB_PATH) as conn:
                    result = WritebackAgent().apply_decision(conn, review_to_apply, "approved")
                st.session_state["last_writeback"] = result
                st.success("CRM updated. Meeting, task, and audit records were saved.")
        with reject:
            if st.button("Reject proposal", disabled=submitted, use_container_width=True):
                with connect(DEFAULT_DB_PATH) as conn:
                    result = WritebackAgent().apply_decision(conn, review_to_apply, "rejected")
                st.session_state["last_writeback"] = result
                st.info("Proposal rejected. No CRM update was applied.")

        result = st.session_state.get("last_writeback")
        if result and result["status"] == "approved":
            st.markdown(
                f"Saved meeting log **#{result['meeting_log_id']}** and "
                f"created **{len(result['task_ids'])}** follow-up task(s)."
            )


def render_overview() -> None:
    st.subheader("CRM Health")
    render_metrics()
    eda = cached_eda()
    left, right = st.columns([1, 1])
    with left:
        stage_df = pd.DataFrame(
            [{"Stage": stage, "Deals": count} for stage, count in eda["deal_stage_distribution"].items()]
        )
        st.bar_chart(stage_df, x="Stage", y="Deals")
    with right:
        st.markdown("**What the data tells us**")
        st.write("The CRM has enough structured data for account, product, sales-agent, and opportunity matching.")
        st.write("Open opportunities are the records that can receive reviewed meeting updates.")
        st.write("The source CRM does not contain meeting transcripts, objections, buying signals, or tasks.")
        if eda["integrity"]["pipeline_products_not_in_products"]:
            st.info("Known data-quality note: GTXPro appears in the pipeline while GTX Pro appears in the product catalog.")


def render_deep_dive() -> None:
    st.subheader("Data Deep Dive")
    eda = cached_eda()
    st.markdown("**Table profile**")
    table_profile = [
        {
            "table": table,
            "rows": details["rows"],
            "columns": len(details["columns"]),
            "missing_cells": sum(details["missing_values"].values()),
        }
        for table, details in eda["tables"].items()
    ]
    st.dataframe(table_profile, use_container_width=True, hide_index=True)

    st.markdown("**Source tables**")
    table = st.selectbox(
        "Choose table",
        ["accounts", "products", "sales_pipeline", "sales_teams", "data_dictionary"],
    )
    st.dataframe(dataframe(table, DEFAULT_DB_PATH, limit=200), use_container_width=True, hide_index=True)

    st.markdown("**Synthetic note rationale**")
    st.write(eda["synthetic_data_rationale"])


def render_activity() -> None:
    st.subheader("Activity")
    for table, label in [
        ("meeting_logs", "Approved meetings"),
        ("tasks", "Follow-up tasks"),
        ("audit_log", "Approval history"),
    ]:
        with st.expander(label, expanded=(table == "meeting_logs")):
            df = dataframe(table, DEFAULT_DB_PATH, limit=50)
            if "model_provider" in df.columns:
                df = df.drop(columns=[col for col in ["model_provider", "model_name"] if col in df.columns])
            st.dataframe(df, use_container_width=True, hide_index=True)


def _stage_text(current_stage: str | None, suggested_stage: str | None) -> str | None:
    if not suggested_stage:
        return None
    if current_stage:
        return f"{current_stage} to {suggested_stage}"
    return suggested_stage


def main() -> None:
    ensure_db()
    inject_css()

    with st.sidebar:
        st.markdown("### RepLog AI")
        page = st.radio(
            "Navigation",
            ["Workspace", "CRM Overview", "Data Deep Dive", "Activity"],
            label_visibility="collapsed",
        )

    if page == "Workspace":
        render_workspace()
    elif page == "CRM Overview":
        render_overview()
    elif page == "Data Deep Dive":
        render_deep_dive()
    else:
        render_activity()


if __name__ == "__main__":
    main()
