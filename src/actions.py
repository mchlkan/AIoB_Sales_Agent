from __future__ import annotations

import json
import sqlite3
from typing import Any

from src.schemas import Decision, ReviewPackage
from src.schemas import WritebackOperation, WritebackPlan


class WritebackAgent:
    def apply_decision(
        self,
        conn: sqlite3.Connection,
        review: ReviewPackage,
        decision: Decision,
    ) -> dict[str, Any]:
        writeback_plan = self.plan_writeback(review, decision)
        if decision == "rejected":
            applied = {"status": "rejected", "changes": [], "writeback_plan": writeback_plan.model_dump()}
            self._write_audit(conn, review, decision, applied, writeback_plan)
            conn.commit()
            return applied

        proposal = review.proposal
        matched = review.validation.matched
        meeting_id = conn.execute(
            """
            INSERT INTO meeting_logs (
                account_name, opportunity_id, sales_agent, attendees, summary, products_discussed,
                objections, buying_signals, next_steps, source_note, model_provider, model_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                matched.account_name,
                matched.opportunity_id,
                matched.sales_agent or proposal.sales_agent,
                json.dumps(proposal.attendees),
                proposal.meeting_summary,
                json.dumps(matched.product_names),
                json.dumps(proposal.objections_or_risks),
                json.dumps(proposal.buying_signals),
                json.dumps([task.model_dump() for task in proposal.next_steps]),
                review.source_note,
                review.model_provider,
                review.model_name,
            ),
        ).lastrowid

        task_ids = []
        for task in proposal.next_steps:
            task_id = conn.execute(
                """
                INSERT INTO tasks (
                    account_name, opportunity_id, task_description, owner,
                    due_date, status, source_meeting_log_id
                )
                VALUES (?, ?, ?, ?, ?, 'open', ?)
                """,
                (
                    matched.account_name,
                    matched.opportunity_id,
                    task.description,
                    task.owner or matched.sales_agent or proposal.sales_agent,
                    task.due_date,
                    meeting_id,
                ),
            ).lastrowid
            task_ids.append(task_id)

        stage_change = None
        if matched.opportunity_id and proposal.suggested_stage:
            current = conn.execute(
                "SELECT deal_stage FROM sales_pipeline WHERE opportunity_id = ?",
                (matched.opportunity_id,),
            ).fetchone()
            previous_stage = current["deal_stage"] if current else None
            conn.execute(
                "UPDATE sales_pipeline SET deal_stage = ? WHERE opportunity_id = ?",
                (proposal.suggested_stage, matched.opportunity_id),
            )
            stage_change = {
                "opportunity_id": matched.opportunity_id,
                "previous_stage": previous_stage,
                "new_stage": proposal.suggested_stage,
            }

        applied = {
            "status": "approved",
            "meeting_log_id": meeting_id,
            "task_ids": task_ids,
            "stage_change": stage_change,
            "writeback_plan": writeback_plan.model_dump(),
        }
        self._write_audit(conn, review, decision, applied, writeback_plan)
        conn.commit()
        return applied

    @staticmethod
    def plan_writeback(review: ReviewPackage, decision: Decision) -> WritebackPlan:
        operations = [
            WritebackOperation(
                operation="insert_audit_log",
                target="audit_log",
                summary=f"Record the human {decision} decision and model metadata.",
            )
        ]
        if decision == "approved":
            operations.insert(
                0,
                WritebackOperation(
                    operation="insert_meeting_log",
                    target="meeting_logs",
                    summary="Save the approved meeting summary and extracted account context.",
                ),
            )
            operations[1:1] = [
                WritebackOperation(
                    operation="insert_task",
                    target="tasks",
                    summary=f"Create follow-up task: {task.description}",
                )
                for task in review.proposal.next_steps
            ]
            if review.validation.matched.opportunity_id and review.proposal.suggested_stage:
                operations.insert(
                    -1,
                    WritebackOperation(
                        operation="update_opportunity_stage",
                        target="sales_pipeline",
                        summary=(
                            f"Update {review.validation.matched.opportunity_id} "
                            f"to {review.proposal.suggested_stage}."
                        ),
                    ),
                )
        return WritebackPlan(decision=decision, operations=operations)

    @staticmethod
    def _write_audit(
        conn: sqlite3.Connection,
        review: ReviewPackage,
        decision: Decision,
        applied: dict[str, Any],
        writeback_plan: WritebackPlan,
    ) -> None:
        conn.execute(
            """
            INSERT INTO audit_log (
                source_note, proposal_json, approved_proposal_json, validation_json,
                critic_json, decision, writeback_plan_json, applied_changes_json,
                model_runs_json, model_provider, model_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review.source_note,
                review.proposal.model_dump_json(),
                review.proposal.model_dump_json(),
                review.validation.model_dump_json(),
                review.critic.model_dump_json() if review.critic else None,
                decision,
                writeback_plan.model_dump_json(),
                json.dumps(applied),
                json.dumps([run.model_dump() for run in review.model_runs]),
                review.model_provider,
                review.model_name,
            ),
        )
