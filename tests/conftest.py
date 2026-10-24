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


@pytest.fixture(scope="session")
def all_accounts(match):
    """Every explained moment's account, by moment id (attributed once per test session)."""
    import warnings

    from replay_room.attribution.engine import attribute_match

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        return {a.moment.moment_id: a for a in attribute_match(match)}


@pytest.fixture(scope="session")
def all_contexts(match, all_accounts):
    from replay_room.context import match_context_for

    return {mid: match_context_for(match, a.moment) for mid, a in all_accounts.items()}
