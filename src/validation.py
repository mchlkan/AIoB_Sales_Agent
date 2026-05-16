from __future__ import annotations

import sqlite3

from src.matching import best_match, can_advance_stage, open_opportunities, product_match
from src.schemas import CriticReport, MatchResult, ValidationResult, ExtractionProposal


class ValidationAgent:
    def validate(
        self,
        conn: sqlite3.Connection,
        proposal: ExtractionProposal,
        critic: CriticReport | None = None,
        corrected_fields: set[str] | None = None,
    ) -> ValidationResult:
        warnings: list[str] = []
        blocking_reasons: list[str] = []
        needs_correction: list[str] = []
        corrected_fields = corrected_fields or set()
        accounts = [row[0] for row in conn.execute("SELECT account FROM accounts").fetchall()]
        products = [row[0] for row in conn.execute("SELECT product FROM products").fetchall()]
        agents = [row[0] for row in conn.execute("SELECT sales_agent FROM sales_teams").fetchall()]

        account_name, account_confidence = best_match(proposal.account_name, accounts)
        if not account_name:
            warnings.append(f"Could not match account: {proposal.account_name or 'missing'}")
        elif proposal.account_name and proposal.account_name != account_name:
            warnings.append(f"Matched account '{proposal.account_name}' to '{account_name}'.")

        product_names = []
        product_warnings = []
        for product in proposal.products_discussed:
            matched_product, warning = product_match(product, products)
            if matched_product:
                product_names.append(matched_product)
            if warning:
                product_warnings.append(warning)
                warnings.append(warning)
        if not product_names:
            warnings.append("No valid product match found.")

        sales_agent, agent_confidence = best_match(proposal.sales_agent, agents, cutoff=0.88)
        if proposal.sales_agent and not sales_agent:
            warnings.append(f"Could not match sales agent: {proposal.sales_agent}")

        opportunities = open_opportunities(conn, account_name, product_names, sales_agent)
        if not opportunities and sales_agent:
            opportunities = open_opportunities(conn, account_name, product_names)
            if opportunities:
                warnings.append("No open opportunity matched the sales agent exactly; showing account/product match.")

        opportunity_id = None
        opportunity_stage = None
        opportunity_warning = None
        if proposal.opportunity_id:
            row = conn.execute(
                "SELECT * FROM sales_pipeline WHERE opportunity_id = ?", (proposal.opportunity_id,)
            ).fetchone()
            if row:
                opportunity_id = row["opportunity_id"]
                opportunity_stage = row["deal_stage"]
            else:
                warnings.append(f"LLM provided unknown opportunity id: {proposal.opportunity_id}")
        elif len(opportunities) == 1:
            opportunity_id = opportunities[0]["opportunity_id"]
            opportunity_stage = opportunities[0]["deal_stage"]
        elif len(opportunities) > 1:
            opportunity_id = opportunities[0]["opportunity_id"]
            opportunity_stage = opportunities[0]["deal_stage"]
            opportunity_warning = f"{len(opportunities)} open opportunities match; using most recent as default."
            warnings.append(opportunity_warning)
        else:
            opportunity_warning = "No open opportunity matched account/product."
            warnings.append(opportunity_warning)

        if not can_advance_stage(opportunity_stage, proposal.suggested_stage):
            stage_update_allowed = False
            stage_update_blocked_reason = (
                f"Suggested stage '{proposal.suggested_stage}' is not a logical advance from "
                f"'{opportunity_stage}'."
            )
            warnings.append(stage_update_blocked_reason)
        else:
            stage_update_allowed = True
            stage_update_blocked_reason = None

        if proposal.confidence < 0.65:
            warnings.append("Low extraction confidence; review carefully before approval.")

        if critic:
            warnings.extend(critic.warnings)
            if critic.overall_confidence < 0.65:
                warnings.append("Evidence critic confidence is low; review the proposed fields carefully.")
            for field in critic.needs_human_attention:
                warnings.append(f"Evidence critic flagged {field} for human review.")
            field_map = {
                "account_name": "account",
                "products_discussed": "products",
                "meeting_summary": "summary",
            }
            for finding in critic.findings:
                if finding.field not in field_map or finding.status not in {"missing", "contradicted"}:
                    continue
                correction_key = field_map[finding.field]
                if correction_key in corrected_fields:
                    continue
                reason = f"{finding.field} is {finding.status} according to the evidence critic."
                blocking_reasons.append(reason)
                needs_correction.append(correction_key)

        matched = MatchResult(
            account_name=account_name,
            account_confidence=account_confidence,
            product_names=product_names,
            product_warnings=product_warnings,
            opportunity_id=opportunity_id,
            opportunity_stage=opportunity_stage,
            opportunity_warning=opportunity_warning,
            sales_agent=sales_agent,
        )
        required_checks = [
            ("account", account_name, "Account is required before approval."),
            ("products", product_names, "At least one valid product is required before approval."),
            ("opportunity", opportunity_id, "An open opportunity is required before approval."),
            ("summary", proposal.meeting_summary.strip(), "Meeting summary is required before approval."),
        ]
        for field, value, reason in required_checks:
            if value:
                continue
            blocking_reasons.append(reason)
            needs_correction.append(field)

        unique_blockers = list(dict.fromkeys(blocking_reasons))
        unique_corrections = list(dict.fromkeys(needs_correction))
        review_risk_level = "low"
        if unique_blockers:
            review_risk_level = "high"
        elif proposal.confidence < 0.65 or (critic and critic.overall_confidence < 0.65):
            review_risk_level = "medium"
        elif stage_update_blocked_reason:
            review_risk_level = "medium"

        return ValidationResult(
            is_approvable=not unique_blockers,
            warnings=warnings,
            blocking_reasons=unique_blockers,
            needs_correction=unique_corrections,
            stage_update_allowed=stage_update_allowed,
            stage_update_blocked_reason=stage_update_blocked_reason,
            review_risk_level=review_risk_level,
            matched=matched,
        )
