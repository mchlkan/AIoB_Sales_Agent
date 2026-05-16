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


def _read(key: str, default: str = "") -> str:
    value = os.getenv(key, "").strip()
    if value:
        return value
    try:
        import streamlit as st

        secret = st.secrets.get(key)
        if secret is not None and str(secret).strip():
            return str(secret).strip()
    except Exception:
        pass
    return default


def load_settings() -> Settings:
    load_dotenv(ROOT_DIR / ".env")
    return Settings(
        model_provider=_read("MODEL_PROVIDER", "gemini").lower(),
        demo_fallback_enabled=_read("DEMO_FALLBACK_ENABLED", "true").lower()
        in {"1", "true", "yes", "on"},
        gemini_api_key=_read("GEMINI_API_KEY"),
        gemini_model=_read("GEMINI_MODEL", "gemini-2.5-flash-lite"),
        groq_api_key=_read("GROQ_API_KEY"),
        groq_model=_read("GROQ_MODEL", "qwen/qwen3-32b"),
    )

