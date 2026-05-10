from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import DATA_DIR, DB_DIR, DEFAULT_DB_PATH


SOURCE_TABLES = {
    "accounts": "accounts.csv",
    "products": "products.csv",
    "sales_pipeline": "sales_pipeline.csv",
    "sales_teams": "sales_teams.csv",
    "data_dictionary": "data_dictionary.csv",
}


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def setup_database(
    db_path: Path = DEFAULT_DB_PATH,
    data_dir: Path = DATA_DIR,
    reset_runtime: bool = False,
) -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        for table, filename in SOURCE_TABLES.items():
            df = pd.read_csv(data_dir / filename)
            df.to_sql(table, conn, if_exists="replace", index=False)
        if reset_runtime:
            conn.executescript(
                """
                DROP TABLE IF EXISTS audit_log;
                DROP TABLE IF EXISTS tasks;
                DROP TABLE IF EXISTS meeting_logs;
                """
            )
        _create_runtime_tables(conn)


def ensure_database(db_path: Path = DEFAULT_DB_PATH, data_dir: Path = DATA_DIR) -> None:
    if not db_path.exists():
        setup_database(db_path, data_dir)
        return
    with connect(db_path) as conn:
        _create_runtime_tables(conn)


def _create_runtime_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meeting_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            account_name TEXT,
            opportunity_id TEXT,
            sales_agent TEXT,
            attendees TEXT NOT NULL DEFAULT '[]',
            summary TEXT NOT NULL,
            products_discussed TEXT NOT NULL,
            objections TEXT NOT NULL,
            buying_signals TEXT NOT NULL,
            next_steps TEXT NOT NULL,
            source_note TEXT NOT NULL,
            model_provider TEXT,
            model_name TEXT
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            account_name TEXT,
            opportunity_id TEXT,
            task_description TEXT NOT NULL,
            owner TEXT,
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            source_meeting_log_id INTEGER,
            FOREIGN KEY(source_meeting_log_id) REFERENCES meeting_logs(id)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_note TEXT NOT NULL,
            proposal_json TEXT NOT NULL,
            approved_proposal_json TEXT,
            validation_json TEXT NOT NULL,
            critic_json TEXT,
            decision TEXT NOT NULL CHECK(decision IN ('approved', 'rejected')),
            writeback_plan_json TEXT,
            applied_changes_json TEXT NOT NULL,
            model_runs_json TEXT,
            model_provider TEXT,
            model_name TEXT
        );
        """
    )
    _ensure_column(conn, "meeting_logs", "attendees", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "audit_log", "approved_proposal_json", "TEXT")
    _ensure_column(conn, "audit_log", "critic_json", "TEXT")
    _ensure_column(conn, "audit_log", "writeback_plan_json", "TEXT")
    _ensure_column(conn, "audit_log", "model_runs_json", "TEXT")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def table_counts(db_path: Path = DEFAULT_DB_PATH) -> dict[str, int]:
    with connect(db_path) as conn:
        tables = [*SOURCE_TABLES.keys(), "meeting_logs", "tasks", "audit_log"]
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
            if _table_exists(conn, table)
        }


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table,)
        ).fetchone()
        is not None
    )


def run_eda(data_dir: Path = DATA_DIR) -> dict[str, Any]:
    frames = {table: pd.read_csv(data_dir / filename) for table, filename in SOURCE_TABLES.items()}
    summary: dict[str, Any] = {"tables": {}, "deal_stage_distribution": {}, "integrity": {}}

    for table, df in frames.items():
        summary["tables"][table] = {
            "rows": int(len(df)),
            "columns": list(df.columns),
            "missing_values": {col: int(df[col].isna().sum()) for col in df.columns},
            "unique_values": {col: int(df[col].nunique(dropna=False)) for col in df.columns},
        }

    pipeline = frames["sales_pipeline"]
    summary["deal_stage_distribution"] = {
        str(k): int(v) for k, v in pipeline["deal_stage"].value_counts().to_dict().items()
    }

    accounts = set(frames["accounts"]["account"].dropna())
    products = set(frames["products"]["product"].dropna())
    agents = set(frames["sales_teams"]["sales_agent"].dropna())
    pipeline_accounts = set(pipeline["account"].dropna()) - {""}
    pipeline_products = set(pipeline["product"].dropna())
    pipeline_agents = set(pipeline["sales_agent"].dropna())

    open_pipeline = pipeline[pipeline["deal_stage"].isin(["Prospecting", "Engaging"])]
    open_with_accounts = open_pipeline[open_pipeline["account"].notna() & (open_pipeline["account"] != "")]
    demo_candidates = (
        open_with_accounts[["opportunity_id", "account", "product", "sales_agent", "deal_stage", "engage_date"]]
        .head(25)
        .to_dict(orient="records")
    )

    summary["integrity"] = {
        "pipeline_accounts_not_in_accounts": sorted(pipeline_accounts - accounts),
        "pipeline_products_not_in_products": sorted(pipeline_products - products),
        "products_not_in_pipeline": sorted(products - pipeline_products),
        "pipeline_agents_not_in_sales_teams": sorted(pipeline_agents - agents),
        "sales_team_agents_not_in_pipeline": sorted(agents - pipeline_agents),
        "open_opportunities": int(len(open_pipeline)),
        "open_opportunities_with_account": int(len(open_with_accounts)),
        "demo_candidates": demo_candidates,
    }
    summary["synthetic_data_rationale"] = (
        "The provided CRM data has accounts, products, sales teams, and pipeline rows, "
        "but no meeting transcripts, objections, buying signals, or follow-up tasks. "
        "Synthetic notes are therefore limited to realistic rep inputs tied to real CRM records."
    )
    return summary


def dataframe(table: str, db_path: Path = DEFAULT_DB_PATH, limit: int = 200) -> pd.DataFrame:
    with connect(db_path) as conn:
        return pd.read_sql_query(f"SELECT * FROM {table} LIMIT ?", conn, params=(limit,))
