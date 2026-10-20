from pathlib import Path

import pytest

from replay_room.ingest import load_match

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "synthetic_match_01"


@pytest.fixture(scope="session")
def fixture_dir() -> Path:
    return FIXTURE


@pytest.fixture(scope="session")
def match(fixture_dir):
    return load_match(fixture_dir)
