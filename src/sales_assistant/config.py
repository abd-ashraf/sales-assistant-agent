"""Settings read from the environment and an optional `.env` file."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(".env")
CACHE_DIR = Path(".cache")
DEFAULT_DATA_DIR = "data"
DEFAULT_OPENAI_MODEL = "gpt-6-luna"

BROCHURES_DIR = "brochures"
SERVICE_REPORTS_DIR = "HistoricalServices"
FLOTATION_CSV = "flotation_process_data_hourly.csv"
EXPECTED_DATA = (BROCHURES_DIR, SERVICE_REPORTS_DIR, FLOTATION_CSV)

LANGFUSE_SETTINGS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")


@dataclass(frozen=True)
class Settings:
    """Where the data lives, which model the agent uses, and where traces go."""

    data_dir: Path
    openai_model: str
    has_openai_key: bool
    langfuse_url: str | None  # None turns tracing off


def load_settings() -> Settings:
    """Load `.env` from the working directory, then read the settings from the environment."""
    load_dotenv(ENV_FILE)
    # Only whether keys are set is kept here; the OpenAI and Langfuse clients read them.
    tracing = all(os.getenv(name) for name in LANGFUSE_SETTINGS)
    return Settings(
        data_dir=Path(os.getenv("DATA_DIR", DEFAULT_DATA_DIR)),
        openai_model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        has_openai_key=bool(os.getenv("OPENAI_API_KEY")),
        langfuse_url=os.getenv("LANGFUSE_BASE_URL") if tracing else None,
    )
