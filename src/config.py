from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DB_DIR = ROOT_DIR / "db"
SAMPLE_NOTES_DIR = ROOT_DIR / "sample_notes"
PROMPTS_DIR = ROOT_DIR / "prompts"
DEFAULT_DB_PATH = DB_DIR / "crm.db"


@dataclass(frozen=True)
class Settings:
    model_provider: str
    demo_fallback_enabled: bool
    gemini_api_key: str
    gemini_model: str
    groq_api_key: str
    groq_model: str


def load_settings() -> Settings:
    load_dotenv(ROOT_DIR / ".env")
    return Settings(
        model_provider=os.getenv("MODEL_PROVIDER", "gemini").strip().lower(),
        demo_fallback_enabled=os.getenv("DEMO_FALLBACK_ENABLED", "true").strip().lower()
        in {"1", "true", "yes", "on"},
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip(),
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        groq_model=os.getenv("GROQ_MODEL", "qwen/qwen3-32b").strip(),
    )

