import json

import numpy as np
import pandas as pd
import pytest

from replay_room.ingest.generator import _has_goal_with_buildup, generate_match, write_fixture


@pytest.fixture(scope="module")
def short_match():
    return generate_match(seed=3, period_seconds=60.0)


def test_same_seed_same_match(short_match):
    again = generate_match(seed=3, period_seconds=60.0)
    assert again.meta == short_match.meta
    assert again.events == short_match.events
    pd.testing.assert_frame_equal(again.tracking, short_match.tracking)


def test_different_seed_differs(short_match):
    other = generate_match(seed=4, period_seconds=60.0)
    assert other.events != short_match.events


def test_written_files_are_byte_identical(short_match, tmp_path):
    a = write_fixture(short_match, tmp_path / "a")
    b = write_fixture(generate_match(seed=3, period_seconds=60.0), tmp_path / "b")
    for name in ("meta.json", "events.jsonl", "tracking.csv.gz"):
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_has_goal_with_buildup(short_match):
    assert _has_goal_with_buildup(short_match.events)
    assert any(e["type"] == "Shot" and e["outcome"] == "goal" for e in short_match.events)


def test_full_tracking_every_frame(short_match):
    tr = short_match.tracking
    n_frames = tr["frame"].nunique()
    assert n_frames == 2 * (60 * 10 + 1)  # both periods, 10 Hz, inclusive of the final whistle
    assert (tr.groupby("frame").size() == 23).all()  # 22 players + ball
    assert not tr[["x", "y", "vx", "vy"]].isna().any().any()


def test_players_move_plausibly(short_match):
    tr = short_match.tracking
    players = tr[tr["object"] != "BALL"]
    assert np.hypot(players["vx"], players["vy"]).max() < 9.0  # m/s, sprint ceiling
    ball = tr[tr["object"] == "BALL"]
    assert np.hypot(ball["vx"], ball["vy"]).max() < 40.0


def test_events_time_ordered_and_ids_unique(short_match):
    keys = [(e["period"], e["t"]) for e in short_match.events]
    assert keys == sorted(keys)
    ids = [e["id"] for e in short_match.events]
    assert len(ids) == len(set(ids))


def test_committed_fixture_matches_its_recorded_seed(fixture_dir):
    meta = json.loads((fixture_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["generator"]["seed"] == 7
    assert meta["feed_version"] == "synthetic-v1"
