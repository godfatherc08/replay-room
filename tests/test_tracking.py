import numpy as np

from replay_room.contracts import BALL_ID, TRACKING_COLUMNS


def test_tracking_table_schema(match):
    tr = match.tracking
    assert tuple(tr.columns) == TRACKING_COLUMNS
    assert not tr.isna().any().any()
    assert tr["frame_id"].is_monotonic_increasing


def test_every_player_and_ball_in_every_frame(match):
    tr = match.tracking
    n_players = len(match.meta.home_team.players) + len(match.meta.away_team.players)
    assert (tr.groupby("frame_id").size() == n_players + 1).all()
    ball = tr[tr["player_id"] == BALL_ID]
    assert (ball["team_id"] == BALL_ID).all()
    assert ball["frame_id"].nunique() == tr["frame_id"].nunique()
    team_ids = {match.meta.home_team_id, match.meta.away_team.team_id}
    assert set(tr.loc[tr["player_id"] != BALL_ID, "team_id"]) == team_ids


def test_frame_rate_and_timestamps(match):
    tr = match.tracking
    for _, g in tr[tr["player_id"] == BALL_ID].groupby("period_id"):
        assert np.allclose(np.diff(g["timestamp"]), 1 / match.meta.frame_rate_hz)


def test_velocities_consistent_with_positions(match):
    # Velocities are observed, not modelled: they must agree with displacement.
    tr = match.tracking
    dt = 1 / match.meta.frame_rate_hz
    p = tr[(tr["player_id"] == match.meta.home_team.players[9].player_id) & (tr["period_id"] == 1)]
    resid = np.abs(np.diff(p["x"]) / dt - p["vx"].to_numpy()[:-1])
    assert resid.max() < 1.0


def test_home_keeper_defends_low_x_in_both_periods(match):
    tr = match.tracking
    gk = match.meta.home_team.players[0].player_id
    for _, g in tr[tr["player_id"] == gk].groupby("period_id"):
        assert g["x"].mean() < 20


def test_iter_frames_matches_table(match):
    frames = list(match.iter_frames())
    assert len(frames) == match.tracking["frame_id"].nunique()
    f = frames[100]
    assert f.ball is not None and len(f.players) == 22
    rows = match.tracking[match.tracking["frame_id"] == f.frame_id]
    assert f.timestamp == rows["timestamp"].iloc[0]
    assert {o.player_id for o in f.objects} == set(rows["player_id"])
