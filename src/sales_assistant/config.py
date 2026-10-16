"""Settings read from the environment and an optional `.env` file."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(".env")
DEFAULT_DATA_DIR = "data"
DEFAULT_OPENAI_MODEL = "gpt-6-luna"

# What the assignment's data folder must contain.
EXPECTED_DATA = ("brochures", "HistoricalServices", "flotation_process_data_hourly.csv")


@dataclass(frozen=True)
class Settings:
    """Where the data lives and which model the agent uses."""

    data_dir: Path
    openai_model: str
    has_openai_key: bool


def load_settings() -> Settings:
    """Load `.env` from the working directory, then read the settings from the environment."""
    load_dotenv(ENV_FILE)
    # Only whether the key is set is kept here; the OpenAI client reads the key itself.
    return Settings(
        data_dir=Path(os.getenv("DATA_DIR", DEFAULT_DATA_DIR)),
        openai_model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        has_openai_key=bool(os.getenv("OPENAI_API_KEY")),
    )
