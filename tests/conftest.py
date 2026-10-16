"""Fixtures shared by the tests."""

from pathlib import Path

import pytest

SETTING_NAMES = ("DATA_DIR", "OPENAI_API_KEY", "OPENAI_MODEL")


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty working directory, with no `.env` and no settings in the environment."""
    monkeypatch.chdir(tmp_path)
    for name in SETTING_NAMES:
        # Set, then delete: pytest then restores the original even if `.env` loading changed it.
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    return tmp_path
