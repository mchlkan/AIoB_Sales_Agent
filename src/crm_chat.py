from __future__ import annotations

import json
import sqlite3
from typing import Any

from src.config import Settings, load_settings
from src.llm import LLMClient, LLMError
from src.schemas import CRMChatContext, ModelRun


def answer_question(conn: sqlite3.Connection, question: str) -> str:
    answer, _ = answer_question_with_metadata(conn, question)
    return answer


def answer_question_with_metadata(
    conn: sqlite3.Connection,
    question: str,
    settings: Settings | None = None,
) -> tuple[str, ModelRun]:
    contexts = retrieve_context(conn, question)
    prompt = _build_chat_prompt(question, contexts)
    settings = settings or load_settings()
    try:
        response = LLMClient(settings).complete(
            prompt,
            task="crm_chat",
            preferred_provider="gemini",
            json_mode=False,
        )
        return (
            response.text.strip(),
            ModelRun(
                task="crm_chat",
                provider=response.provider,
                model=response.model,
                fallback_used=response.fallback_used,
            ),
        )
    except LLMError as exc:
        return (
            _fallback_answer(conn, question),
            ModelRun(
                task="crm_chat",
                provider="chat_fallback",
                model="rule_based",
                fallback_used=True,
                error=str(exc),
            ),
        )


def retrieve_context(conn: sqlite3.Connection, question: str) -> list[CRMChatContext]:
    q = question.lower()
    contexts: list[CRMChatContext] = []

    if any(word in q for word in ["attend", "attendee", "joined", "meeting", "summary", "recent"]):
        contexts.append(
            CRMChatContext(
                source="recent_meeting_logs",
                rows=_rows(
                    conn,
                    """
                    SELECT account_name, opportunity_id, attendees, summary, objections,
                           buying_signals, next_steps, created_at
                    FROM meeting_logs
                    ORDER BY created_at DESC
                    LIMIT 8
                    """,
                ),
            )
        )

    if any(word in q for word in ["task", "follow", "owner", "due", "next step"]):
        contexts.append(
            CRMChatContext(
                source="tasks",
                rows=_rows(
                    conn,
                    """
                    SELECT account_name, opportunity_id, task_description, owner,
                           due_date, status, created_at
                    FROM tasks
                    ORDER BY created_at DESC
                    LIMIT 10
                    """,
                ),
            )
        )

    if any(word in q for word in ["pipeline", "open", "deal", "opportunity", "stage", "won", "lost"]):
        contexts.append(
            CRMChatContext(
                source="pipeline_summary",
                rows=_rows(
                    conn,
                    """
                    SELECT account, product, sales_agent, deal_stage, COUNT(*) AS count
                    FROM sales_pipeline
                    GROUP BY account, product, sales_agent, deal_stage
                    ORDER BY count DESC
                    LIMIT 20
                    """,
                ),
            )
        )

    if any(word in q for word in ["risk", "objection", "competitor", "delivery", "security", "budget"]):
        contexts.append(
            CRMChatContext(
                source="risk_meeting_logs",
                rows=_rows(
                    conn,
                    """
                    SELECT account_name, opportunity_id, summary, objections,
                           buying_signals, created_at
                    FROM meeting_logs
                    WHERE lower(objections) LIKE '%risk%'
                       OR lower(objections) LIKE '%competitor%'
                       OR lower(objections) LIKE '%delivery%'
                       OR lower(objections) LIKE '%security%'
                       OR lower(objections) LIKE '%budget%'
                    ORDER BY created_at DESC
                    LIMIT 8
                    """,
                ),
            )
        )

    if any(word in q for word in ["approve", "approved", "reject", "rejected", "audit", "changed"]):
        contexts.append(
            CRMChatContext(
                source="audit_log",
                rows=_rows(
                    conn,
                    """
                    SELECT created_at, decision, applied_changes_json, model_provider, model_name
                    FROM audit_log
                    ORDER BY created_at DESC
                    LIMIT 8
                    """,
                ),
            )
        )

    if not contexts:
        contexts = [
            CRMChatContext(
                source="recent_meeting_logs",
                rows=_rows(
                    conn,
                    """
                    SELECT account_name, opportunity_id, attendees, summary, created_at
                    FROM meeting_logs
                    ORDER BY created_at DESC
                    LIMIT 5
                    """,
                ),
            ),
            CRMChatContext(
                source="open_pipeline",
                rows=_rows(
                    conn,
                    """
                    SELECT account, product, sales_agent, deal_stage, COUNT(*) AS count
                    FROM sales_pipeline
                    WHERE deal_stage IN ('Prospecting', 'Engaging', 'Proposal')
                    GROUP BY account, product, sales_agent, deal_stage
                    ORDER BY count DESC
                    LIMIT 10
                    """,
                ),
            ),
        ]
    return contexts


def _build_chat_prompt(question: str, contexts: list[CRMChatContext]) -> str:
    context_json = json.dumps([context.model_dump() for context in contexts], indent=2)
    return f"""
You are Agent #5, the RepLog AI Ask-CRM agent.

Answer the user's CRM question in a natural, conversational style. Use only the retrieved CRM context below.
Do not invent people, accounts, tasks, opportunities, or dates. If the context is insufficient, say what is missing
and suggest the closest CRM question you can answer from the available records.

Prefer one concise paragraph. Use bullets only when the user asks for a list or when there are many concrete items.

Question:
{question}

Retrieved CRM context:
{context_json}
""".strip()


def _rows(conn: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query).fetchall()]


def _fallback_answer(conn: sqlite3.Connection, question: str) -> str:
    q = question.lower()
    if any(word in q for word in ["attend", "attended", "attendee", "joined", "who was", "who were"]):
        rows = conn.execute(
            """
            SELECT account_name, opportunity_id, attendees, summary, created_at
            FROM meeting_logs
            ORDER BY created_at DESC
            LIMIT 5
            """
        ).fetchall()
        if not rows:
            return (
                "I do not have an approved meeting with attendee information yet. "
                "Once you approve a note that mentions who joined, I can answer that directly."
            )
        answers = []
        for row in rows:
            attendees = _loads(row["attendees"])
            if attendees:
                answers.append((row["account_name"], row["opportunity_id"], attendees))
        if answers:
            account, opportunity_id, attendees = answers[0]
            if len(answers) == 1:
                return (
                    f"The latest meeting I found was for {account} "
                    f"on opportunity {opportunity_id}. The attendees I have on record are "
                    f"{_join_names(attendees)}."
                )
            others = "; ".join(
                f"{account} ({_join_names(attendees)})" for account, _, attendees in answers[1:4]
            )
            return (
                f"The most recent attendee record is for {account} on opportunity {opportunity_id}: "
                f"{_join_names(attendees)}. I also found attendee details for {others}."
            )
        return (
            "I found approved meetings, but the older logs do not include extracted attendee names. "
            "Approve a new note with attendees and I will be able to answer this cleanly."
        )

    if "delivery" in q or "risk" in q or "objection" in q:
        rows = conn.execute(
            """
            SELECT account_name, opportunity_id, summary, objections, created_at
            FROM meeting_logs
            WHERE lower(objections) LIKE '%delivery%'
               OR lower(objections) LIKE '%risk%'
               OR lower(objections) LIKE '%competitor%'
               OR lower(objections) LIKE '%integration%'
            ORDER BY created_at DESC
            LIMIT 5
            """
        ).fetchall()
        if not rows:
            return (
                "I do not see approved meeting logs mentioning delivery risk, integration risk, "
                "or competitor objections yet."
            )
        first = rows[0]
        if len(rows) == 1:
            return (
                f"I found one relevant risk signal for {first['account_name']} "
                f"on opportunity {first['opportunity_id']}: {first['summary']}"
            )
        return (
            f"I found {len(rows)} recent risk-related meeting logs. The latest is for "
            f"{first['account_name']} on opportunity {first['opportunity_id']}: {first['summary']} "
            f"There are also similar notes for {_join_names([row['account_name'] for row in rows[1:]])}."
        )

    if "task" in q or "follow" in q:
        rows = conn.execute(
            """
            SELECT account_name, opportunity_id, task_description, owner, due_date, status
            FROM tasks
            ORDER BY created_at DESC
            LIMIT 8
            """
        ).fetchall()
        if not rows:
            return "I do not see any approved follow-up tasks yet."
        first = rows[0]
        response = (
            f"You have {len(rows)} recent follow-up task"
            f"{'' if len(rows) == 1 else 's'}. The newest one is for {first['account_name']}: "
            f"{first['task_description']} Owner: {first['owner'] or 'unassigned'}, "
            f"due {first['due_date'] or 'not set'}."
        )
        if len(rows) > 1:
            response += " The other recent tasks are for " + _join_names(
                [row["account_name"] for row in rows[1:]]
            ) + "."
        return response

    if "open" in q or "pipeline" in q:
        rows = conn.execute(
            """
            SELECT account, product, sales_agent, deal_stage, COUNT(*) AS count
            FROM sales_pipeline
            WHERE deal_stage IN ('Prospecting', 'Engaging', 'Proposal')
            GROUP BY account, product, sales_agent, deal_stage
            ORDER BY count DESC
            LIMIT 8
            """
        ).fetchall()
        if not rows:
            return "I do not see any open opportunities in the current CRM database."
        total = sum(row["count"] for row in rows)
        first = rows[0]
        return (
            f"I found {total} open opportunity records in the top grouped view. "
            f"The largest group is {first['account'] or 'unassigned accounts'}: "
            f"{first['count']} {first['deal_stage']} opportunity/opportunities for {first['product']}, "
            f"owned by {first['sales_agent']}."
        )

    if "recent" in q or "meeting" in q or "summary" in q:
        rows = conn.execute(
            """
            SELECT account_name, opportunity_id, summary, created_at
            FROM meeting_logs
            ORDER BY created_at DESC
            LIMIT 5
            """
        ).fetchall()
        if not rows:
            return "I do not have approved meeting notes yet. Approve a proposal first, then I can summarize recent account activity."
        first = rows[0]
        if len(rows) == 1:
            return (
                f"The latest approved meeting is for {first['account_name']} "
                f"on opportunity {first['opportunity_id']}: {first['summary']}"
            )
        return (
            f"The latest approved meeting is for {first['account_name']} "
            f"on opportunity {first['opportunity_id']}: {first['summary']} "
            f"I also found recent approved meetings for {_join_names([row['account_name'] for row in rows[1:]])}."
        )

    return (
        "I can help with the CRM memory that has been approved so far. Try asking who attended the latest meeting, "
        "what follow-up tasks are open, which meetings mentioned delivery risk, or what open pipeline looks like."
    )


def _loads(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _join_names(values: list[str]) -> str:
    cleaned = [str(value) for value in values if value]
    if not cleaned:
        return "none"
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return ", ".join(cleaned[:-1]) + f", and {cleaned[-1]}"
