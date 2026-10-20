import io
import json

import numpy as np
import pandas as pd
import pytest

from replay_room.contracts.match import ContextEvent
from replay_room.detect import detect_goal_moments
from replay_room.metrics import LtrActions, load_models, orient, rate_actions, value_moment
from replay_room.metrics.__main__ import main
from replay_room.metrics.corpus import build_corpus
from replay_room.metrics.orientation import require_ltr
from replay_room.metrics.pass_value import FEATURES as PASS_FEATURES
from replay_room.metrics.pass_value import frame_ids_at, pass_context, pass_features, under_pressure
from replay_room.metrics.models import MODELS_DIR
from replay_room.metrics.xg import shot_features


@pytest.fixture(scope="module")
def models():
    return load_models()


@pytest.fixture(scope="module")
def valued(match, models):
    av = rate_actions(match.actions, match.tracking, match.meta, match.context, models, match.pass_targets)
    return [value_moment(c.moment, match.actions, c.frames, match.meta, match.context, models, av)
            for c in detect_goal_moments(match.actions, match.tracking)]


def _ltr(rows, lane_gap=8.0, receiver_gap=8.0):
    """Hand-built actions already in the left-to-right frame: (type, result, sx, sy, ex, ey, bodypart).

    Pass context: the intended point is the end point; opponents are ``lane_gap`` / ``receiver_gap`` away.
    """
    df = pd.DataFrame([
        {"game_id": "g", "action_id": i, "period_id": 1, "time_seconds": float(i), "team_id": "H",
         "player_id": "H-1", "type_name": t, "result_name": r, "start_x": sx, "start_y": sy,
         "end_x": ex, "end_y": ey, "bodypart_name": bp, "intended_end_x": ex, "intended_end_y": ey,
         "lane_gap": lane_gap, "receiver_gap": receiver_gap}
        for i, (t, r, sx, sy, ex, ey, bp) in enumerate(rows)
    ])
    return LtrActions(df, "H")


# --------------------------------------------------------------------------- models / manifest


def test_manifest_records_validation_and_signal(models):
    m = json.loads((MODELS_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert m["xg"]["passed"] and m["pass"]["passed"]
    assert m["on_ball_signal"] == ("vaep" if m["vaep"]["passed"] else "xt_delta")
    assert (models.vaep is not None) == (m["on_ball_signal"] == "vaep")
    assert (MODELS_DIR / "vaep.joblib").exists() == m["vaep"]["passed"]  # no unvalidated model shipped
    assert m["split"] == {"train": 120, "tune": 40, "test": 40}
    sources = m["pass"]["receiver_source"]  # the pass model saw only feed-named targets
    assert sources.get("feed", 0) >= 0.9 * sum(sources.values())


# --------------------------------------------------------------------------- xT


def test_xt_dangerous_central_zones_highest(models):
    xt = models.xt
    assert (xt.grid > 0).all()  # unsupported zones were filled, none left at zero
    centre_box, wide_final_third, own_half = xt.at(100, 34)[()], xt.at(100, 4)[()], xt.at(20, 34)[()]
    assert centre_box > wide_final_third > own_half
    assert xt.grid.max() == pytest.approx(centre_box)
    along = xt.at(np.array([10, 40, 70, 95]), np.full(4, 34.0))
    assert (np.diff(along) > 0).all()  # more dangerous closer to goal


def test_delta_xt_direction(models):
    rated = models.xt.rate(_ltr([
        ("pass", "success", 40, 34, 90, 34, "foot"),          # 0 line-breaking forward pass
        ("pass", "success", 60, 34, 30, 34, "foot"),          # 1 backpass
        ("pass", "fail", 80, 34, 85, 34, "foot"),             # 2 lost the ball
        ("interception", "success", 60, 34, 60, 34, "foot"),  # 3 regain
        ("foul", "fail", 50, 34, 50, 34, "foot"),             # 4 not valued
    ]))
    d = rated["xt_delta"]
    assert d[0] > 0 and d[1] < 0 and d[2] < 0 and d[3] > 0
    assert np.isnan(d[4])
    assert d[2] == pytest.approx(-models.xt.at(80, 34)[()])


def test_xt_requires_orientation(models, match):
    with pytest.raises(TypeError):
        models.xt.rate(match.actions)


# --------------------------------------------------------------------------- xG / pass


def test_xg_monotonic(models):
    shots = _ltr([
        ("shot", "fail", 99, 34, 105, 34, "foot"),     # 0 close, central
        ("shot", "fail", 88, 34, 105, 34, "foot"),     # 1 further
        ("shot", "fail", 75, 34, 105, 34, "foot"),     # 2 further still
        ("shot", "fail", 99, 14, 105, 34, "foot"),     # 3 tight angle
        ("shot", "fail", 99, 34, 105, 34, "head"),     # 4 header from 0's spot
        ("pass", "success", 99, 34, 105, 34, "foot"),  # 5 not a shot
    ])
    xg = models.xg.predict(shots)
    assert xg[0] > xg[1] > xg[2]
    assert xg[0] > xg[3]
    assert xg[4] < xg[0]
    assert np.isnan(xg[5])
    f = shot_features(shots.df)
    assert f["angle"][0] > f["angle"][3] and f["distance"][0] == pytest.approx(6.0)


def test_pass_completion_sane(models):
    passes = _ltr([
        ("pass", "success", 50, 34, 60, 34, "foot"),  # short
        ("pass", "success", 50, 34, 95, 34, "foot"),  # long
    ])
    pc = models.passes.predict(passes)
    assert 0 < pc[1] < pc[0] < 1
    pressured = LtrActions(passes.df.assign(under_pressure=True), "H")
    assert models.passes.predict(pressured)[0] < pc[0]
    rows = [("pass", "success", 50, 34, 70, 34, "foot")]
    open_, lane_blocked, receiver_marked = (models.passes.predict(_ltr(rows, lane, recv))[0]
                                            for lane, recv in ((8, 8), (0.5, 8), (8, 0.5)))
    assert lane_blocked < open_ and receiver_marked < open_


def test_pass_model_needs_tracking_context(models):
    bare = LtrActions(_ltr([("pass", "success", 50, 34, 60, 34, "foot")]).df.drop(columns=["lane_gap"]), "H")
    with pytest.raises(ValueError, match="pass_context"):
        models.passes.predict(bare)


def _raw_recipients(fixture_dir):
    events = (json.loads(line) for line in (fixture_dir / "events.jsonl").read_text(encoding="utf-8").splitlines())
    return {e["id"]: e.get("recipient") for e in events}


def test_pass_context_uses_feed_targets(match, fixture_dir):
    passes = match.actions["type_name"].isin(["pass", "cross"])
    truth = _raw_recipients(fixture_dir)
    named = match.actions[passes].set_index("action_id")["original_event_id"].map(truth).dropna()
    pd.testing.assert_series_equal(match.pass_targets, named, check_names=False)
    assert (match.actions.loc[passes, "result_name"] == "fail").any()  # failed passes are named too
    ctx = pass_context(match.actions, match.tracking, match.pass_targets)
    assert ctx.loc[~passes, "lane_gap"].isna().all() and ctx.loc[passes, "lane_gap"].notna().all()
    feed = ctx["receiver_source"] == "feed"
    assert feed.sum() == len(named)
    ids = match.actions.loc[feed, "action_id"]
    assert ctx.loc[feed, "receiver_id"].tolist() == match.pass_targets.loc[ids].tolist()


def test_pass_context_infers_intended_receiver(match, fixture_dir):
    ctx = pass_context(match.actions, match.tracking)  # no feed targets: inference only
    passes = match.actions["type_name"].isin(["pass", "cross"])
    assert set(ctx.loc[passes, "receiver_source"]) <= {"inferred", "none"}
    truth = _raw_recipients(fixture_dir)  # the generator's ground truth; not part of the canonical contract
    done = match.actions[passes & (match.actions["result_name"] == "success")]
    hits = [truth[a.original_event_id] == ctx.at[i, "receiver_id"] for i, a in done.iterrows()]
    assert np.mean(hits) >= 0.85
    # A completed pass's intended point is close to where it was received.
    gap = np.hypot(ctx.loc[done.index, "intended_end_x"] - done["end_x"],
                   ctx.loc[done.index, "intended_end_y"] - done["end_y"])
    assert gap.median() < 3.0


def test_pass_context_ignores_outcome(match):
    """The context must not depend on the result it is used to predict."""
    flipped = match.actions.assign(result_name=np.where(match.actions["result_name"] == "success", "fail", "success"))
    for targets in (None, match.pass_targets):
        pd.testing.assert_frame_equal(pass_context(match.actions, match.tracking, targets),
                                      pass_context(flipped, match.tracking, targets))


def test_intended_point_oriented_with_the_action(match):
    enriched = match.actions.join(pass_context(match.actions, match.tracking, match.pass_targets))
    ltr = require_ltr(orient(enriched, match.meta.home_team_id))
    away = enriched["team_id"] != match.meta.home_team_id
    i = enriched.index[away & enriched["intended_end_x"].notna()][0]
    assert ltr.at[i, "intended_end_x"] == pytest.approx(105 - enriched.at[i, "intended_end_x"])
    assert ltr.at[i, "intended_end_y"] == pytest.approx(68 - enriched.at[i, "intended_end_y"])
    home = enriched.index[~away & enriched["intended_end_x"].notna()][0]
    assert ltr.at[home, "intended_end_x"] == enriched.at[home, "intended_end_x"]
    assert list(pass_features(ltr.loc[[i]]).columns) == list(PASS_FEATURES)


def test_frame_ids_at_nearest(match):
    t = match.tracking.drop_duplicates("frame_id")
    f = t[t["period_id"] == 2].iloc[40]
    got = frame_ids_at(match.tracking, pd.Series([2, 2, 1]), pd.Series([f["timestamp"] + 0.04, f["timestamp"] - 0.04, 0.0]))
    assert got.tolist() == [f["frame_id"], f["frame_id"], t["frame_id"].iloc[0]]


def test_under_pressure_flag():
    actions = pd.DataFrame({"period_id": [1, 1, 1], "player_id": ["A", "A", "B"], "time_seconds": [5.0, 9.0, 5.5]})
    ctx = (ContextEvent("p1", 1, 4.0, "pressure", "X", "X-1", "A"),)
    assert under_pressure(actions, ctx).tolist() == [True, False, False]


# --------------------------------------------------------------------------- valued moments


def test_every_chain_action_and_window_frame_valued(valued):
    assert len(valued) == 4
    for vm in valued:
        assert [va.action.action_id for va in vm.actions] == list(vm.moment.chain_action_ids)
        assert [s.frame_id for s in vm.surfaces] == list(range(vm.moment.window.frame_start,
                                                              vm.moment.window.frame_end + 1))
        assert all(s.team_id == vm.moment.attacking_team_id for s in vm.surfaces)
        assert vm.actions[-1].xg is not None  # the goal carries its xG
        assert all(va.value is not None for va in vm.actions)


def test_authoritative_signal_labelled(valued, models):
    for vm in valued:
        assert vm.on_ball_signal == models.on_ball_signal
        for va in vm.actions:
            expected = va.vaep if vm.on_ball_signal == "vaep" else va.xt_delta
            assert va.value == expected
        assert "pitch_control" in vm.models and "xt" in vm.models


def test_goal2_short_window_values_every_available_frame(valued, match, models):
    vm = valued[1]
    assert vm.moment.moment_id.endswith("goal-2")
    assert len(vm.surfaces) == vm.moment.window.n_frames == 95  # 0.0..9.4 s, not a fixed length
    assert vm.surfaces[0].timestamp == 0.0
    # Any subset of frames is valued as given, frame by frame.
    ctx = detect_goal_moments(match.actions, match.tracking)[1]
    some = ctx.frames[ctx.frames["frame_id"].isin([1501, 1550, 1595])]
    vm3 = value_moment(ctx.moment, match.actions, some, match.meta, match.context, models, tracking=match.tracking,
                       pass_targets=match.pass_targets)
    assert [s.frame_id for s in vm3.surfaces] == [1501, 1550, 1595]
    outside = match.tracking[match.tracking["frame_id"] == 10]
    with pytest.raises(ValueError):
        value_moment(ctx.moment, match.actions, outside, match.meta, match.context, models, tracking=match.tracking)


def test_goal3_short_chain_sensible(valued):
    vm = valued[2]
    interception, dribble, shot = vm.actions
    assert interception.action.type_name == "interception" and interception.xt_delta > 0
    assert dribble.xt_delta is not None and dribble.value is not None
    assert shot.xg is not None and 0 < shot.xg < 1
    assert interception.value > 0 and shot.value > 0


def test_surface_summaries_in_range(valued):
    for vm in valued:
        for s in vm.surfaces:
            assert 0 <= s.box_control <= 1 and 0 <= s.space_value <= 1 and 0 <= s.control_share <= 1
            assert s.control.shape == (len(s.y), len(s.x))


def test_valuation_deterministic(match, models, valued):
    ctx = detect_goal_moments(match.actions, match.tracking)[3]
    again = value_moment(ctx.moment, match.actions, ctx.frames, match.meta, match.context, models,
                         tracking=match.tracking, pass_targets=match.pass_targets)
    with pytest.raises(ValueError, match="tracking"):
        value_moment(ctx.moment, match.actions, ctx.frames, match.meta, match.context, models)
    assert again.actions == valued[3].actions
    assert all(np.array_equal(a.control, b.control) for a, b in zip(again.surfaces, valued[3].surfaces))


def test_vaep_rejects_oriented_actions(models, match):
    if models.vaep is None:
        pytest.skip("VAEP did not validate")
    with pytest.raises(TypeError):
        models.vaep.rate(orient(match.actions, match.meta.home_team_id), match.meta.home_team_id)


# --------------------------------------------------------------------------- corpus / CLI


def test_corpus_deterministic_and_cached(tmp_path):
    a = build_corpus(n=1, seed0=5000, root=tmp_path / "a", workers=1)
    b = build_corpus(n=1, seed0=5000, root=tmp_path / "b", workers=1)
    pd.testing.assert_frame_equal(a.actions, b.actions)
    cached = build_corpus(n=1, seed0=5000, root=tmp_path / "a", workers=1)
    pd.testing.assert_frame_equal(a.actions, cached.actions)
    assert {"under_pressure", "type_name", "receiver_id", "receiver_source", "lane_gap", "intended_end_x"} <= set(a.actions.columns)
    assert a.actions["pass_frame_id"].dtype == "Int64"
    assert a.games["home_team_id"].tolist() == ["NBR"]


def test_cli(fixture_dir):
    out = io.StringIO()
    assert main([str(fixture_dir), "--frame-every", "0"], out=out) == 0
    text = out.getvalue()
    assert "4 goal moment(s)" in text and "authoritative on-ball signal" in text
    assert "#129 EPA-07 shot" in text
