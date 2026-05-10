from __future__ import annotations

import sqlite3
from difflib import get_close_matches


VALID_STAGE_FLOW = ["Prospecting", "Engaging", "Proposal", "Won", "Lost"]
PRODUCT_ALIASES = {"GTX Pro": "GTXPro", "GTXPro": "GTX Pro"}


def normalize(value: str | None) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def best_match(value: str | None, choices: list[str], cutoff: float = 0.82) -> tuple[str | None, float]:
    if not value:
        return None, 0
    normalized = {normalize(choice): choice for choice in choices}
    target = normalize(value)
    if target in normalized:
        return normalized[target], 1
    close = get_close_matches(target, list(normalized.keys()), n=1, cutoff=cutoff)
    if not close:
        return None, 0
    score = _rough_score(target, close[0])
    return normalized[close[0]], score


def product_match(value: str | None, choices: list[str]) -> tuple[str | None, str | None]:
    direct, _ = best_match(value, choices)
    if direct:
        return direct, None
    alias = PRODUCT_ALIASES.get(value or "")
    if alias:
        pipeline_name = alias if alias == "GTXPro" else value
        product_name = alias if alias == "GTX Pro" else value
        if product_name in choices:
            return product_name, f"Product appears as {pipeline_name} in pipeline but {product_name} in products."
    compact = normalize(value)
    for choice in choices:
        if normalize(choice) == compact:
            return choice, None
    return None, f"Unknown product: {value}" if value else None


def open_opportunities(
    conn: sqlite3.Connection,
    account_name: str | None,
    product_names: list[str],
    sales_agent: str | None = None,
) -> list[sqlite3.Row]:
    if not account_name:
        return []
    params: list[str] = [account_name]
    clauses = ["account = ?", "deal_stage IN ('Prospecting', 'Engaging')"]
    if product_names:
        variants = set(product_names)
        for product in product_names:
            alias = PRODUCT_ALIASES.get(product)
            if alias:
                variants.add(alias)
        placeholders = ",".join("?" for _ in variants)
        clauses.append(f"product IN ({placeholders})")
        params.extend(sorted(variants))
    if sales_agent:
        clauses.append("sales_agent = ?")
        params.append(sales_agent)
    query = f"SELECT * FROM sales_pipeline WHERE {' AND '.join(clauses)} ORDER BY engage_date DESC"
    return conn.execute(query, params).fetchall()


def can_advance_stage(current_stage: str | None, suggested_stage: str | None) -> bool:
    if not current_stage or not suggested_stage:
        return True
    if suggested_stage in {"Won", "Lost"}:
        return True
    if current_stage not in VALID_STAGE_FLOW or suggested_stage not in VALID_STAGE_FLOW:
        return False
    return VALID_STAGE_FLOW.index(suggested_stage) >= VALID_STAGE_FLOW.index(current_stage)


def _rough_score(a: str, b: str) -> float:
    if not a or not b:
        return 0
    common = sum(1 for ch in a if ch in b)
    return min(0.99, common / max(len(a), len(b)))

