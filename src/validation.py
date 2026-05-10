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
    ) -> ValidationResult:
        warnings: list[str] = []
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
            warnings.append(
                f"Suggested stage '{proposal.suggested_stage}' is not a logical advance from '{opportunity_stage}'."
            )

        if proposal.confidence < 0.65:
            warnings.append("Low extraction confidence; review carefully before approval.")

        if critic:
            warnings.extend(critic.warnings)
            if critic.overall_confidence < 0.65:
                warnings.append("Evidence critic confidence is low; review the proposed fields carefully.")
            for field in critic.needs_human_attention:
                warnings.append(f"Evidence critic flagged {field} for human review.")

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
        is_approvable = bool(account_name and product_names and opportunity_id)
        return ValidationResult(is_approvable=is_approvable, warnings=warnings, matched=matched)
