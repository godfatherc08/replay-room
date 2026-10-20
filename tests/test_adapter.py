import json

import pandas as pd
import pytest
from socceraction.spadl import SPADLSchema

from replay_room.contracts import PITCH_LENGTH, PITCH_WIDTH, SPADL_COLUMNS, SpadlAction
from replay_room.ingest import SyntheticFeedAdapter, detect_adapter


def _raw_events(fixture_dir):
    with (fixture_dir / "events.jsonl").open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def test_detects_synthetic_adapter(fixture_dir, tmp_path):
    assert isinstance(detect_adapter(fixture_dir), SyntheticFeedAdapter)
    with pytest.raises(ValueError):
        detect_adapter(tmp_path)


def test_actions_are_valid_spadl(match):
    assert tuple(match.actions.columns) == SPADL_COLUMNS
    SPADLSchema.validate(match.actions)
    assert match.actions["action_id"].tolist() == list(range(len(match.actions)))


def test_every_raw_event_is_accounted_for(match, fixture_dir):
    raw = _raw_events(fixture_dir)
    mapped = set(match.actions["original_event_id"]) | {c.event_id for c in match.context}
    assert mapped == {e["id"] for e in raw}


def test_type_and_result_mapping(match, fixture_dir):
    raw = {e["id"]: e for e in _raw_events(fixture_dir)}
    for a in match.iter_actions():
        ev = raw[a.original_event_id]
        if ev["type"] == "Shot":
            assert a.type_name == "shot"
            assert a.result_name == ("success" if ev["outcome"] == "goal" else "fail")
        elif ev["type"] == "Pass":
            assert a.type_name == ("cross" if ev.get("cross") else "pass")
            assert a.result_name == ("success" if ev["outcome"] == "complete" else "fail")
        elif ev["type"] == "Carry":
            assert a.type_name == "dribble"
        if ev.get("body_part") == "head":
            assert a.bodypart_name == "head"


def test_context_events_kept_out_of_spadl(match):
    kinds = {c.kind for c in match.context}
    assert {"pressure", "possession_change", "period_start", "period_end"} <= kinds


def test_coordinates_normalised_to_canonical_frame(match):
    a = match.actions
    assert a[["start_x", "end_x"]].min().min() >= 0 and a[["start_x", "end_x"]].max().max() <= PITCH_LENGTH
    assert a[["start_y", "end_y"]].min().min() >= 0 and a[["start_y", "end_y"]].max().max() <= PITCH_WIDTH
    # Home attacks +x in BOTH periods (raw feed switches sides at half time).
    home = match.meta.home_team_id
    shots = a[a["type_name"] == "shot"]
    for period in (1, 2):
        s = shots[shots["period_id"] == period]
        assert (s[s["team_id"] == home]["end_x"] > PITCH_LENGTH / 2).all()
        assert (s[s["team_id"] != home]["end_x"] < PITCH_LENGTH / 2).all()


def test_raw_to_canonical_point_mapping():
    xy = SyntheticFeedAdapter._xy
    assert xy(0.0, 0.0, 1.0) == (52.5, 34.0)
    assert xy(52.5, 34.0, 1.0) == (105.0, 68.0)
    assert xy(52.5, 34.0, -1.0) == (0.0, 0.0)  # second half: raw +x is the home goal


def test_actions_line_up_with_tracking(match):
    tr = match.tracking.set_index(["period_id", "timestamp", "player_id"])
    for a in match.iter_actions():
        if a.type_name not in ("pass", "cross", "shot"):
            continue
        row = tr.loc[(a.period_id, a.time_seconds, a.player_id)]
        assert ((row.x - a.start_x) ** 2 + (row.y - a.start_y) ** 2) ** 0.5 < 1.0, a


def test_spadl_action_roundtrip_from_table(match):
    first = next(match.iter_actions())
    assert isinstance(first, SpadlAction)
    assert pd.Series(first.to_row()).equals(pd.Series(match.actions.iloc[0].to_dict()))
