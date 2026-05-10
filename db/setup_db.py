from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DEFAULT_DB_PATH
from src.database import setup_database, table_counts


if __name__ == "__main__":
    setup_database(DEFAULT_DB_PATH, reset_runtime=True)
    print(f"Created {DEFAULT_DB_PATH}")
    for table, count in table_counts(DEFAULT_DB_PATH).items():
        print(f"{table}: {count}")
