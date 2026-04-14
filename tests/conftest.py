"""Shared pytest fixtures for the project."""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
