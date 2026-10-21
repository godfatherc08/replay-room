import json
import warnings

import pytest

from replay_room.attribution.engine import attribute_match
from replay_room.ingest.loader import Match
from replay_room.render import bundle_path, export_moment, write_bundles
from replay_room.render.export import BUNDLE_VERSION, dumps


@pytest.fixture(scope="module")
def accounts(match):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        return attribute_match(match)


@pytest.fixture(scope="module")
def bundles(accounts, match):
    return {a.moment.moment_id: export_moment(a, match) for a in accounts}


def test_bundle_is_self_contained(bundles, accounts):
    for a in accounts:
        b = bundles[a.moment.moment_id]
        assert b["bundle_version"] == BUNDLE_VERSION
        assert b["account"] == a.model_dump(mode="json")
        assert b["pitch"] == {"length": 105.0, "width": 68.0, "units": "m", "origin": "bottom-left corner",
                                   "x_axis": "along the touchline; the home team attacks +x", "frame_rate_hz": 10.0}
        w = a.moment.window
        assert b["frames"]["frame_ids"] == list(range(w.frame_start, w.frame_end + 1))
        assert b["frames"]["period_id"] == w.period_id
        assert len(b["frames"]["timestamps"]) == w.n_frames
        assert b["frames"]["timestamps"][0] == w.t_start and b["frames"]["timestamps"][-1] == w.t_end
        assert {t["side"] for t in b["teams"]} == {"home", "away"}


def test_tracks_are_the_observed_positions(bundles, match):
    b = bundles["SYN-0007-goal-1"]
    assert len(b["objects"]) == 23 and sum(o["kind"] == "ball" for o in b["objects"]) == 1
    fid = b["frames"]["frame_ids"][10]
    row = match.tracking[(match.tracking["frame_id"] == fid) & (match.tracking["player_id"] == "EPA-09")].iloc[0]
    tr = b["tracks"]["EPA-09"]
    assert (tr["x"][10], tr["y"][10], tr["vx"][10], tr["vy"][10]) == pytest.approx(
        (row.x, row.y, row.vx, row.vy), abs=0.005)


def test_every_evidence_frame_and_player_is_in_the_bundle(bundles):
    for b in bundles.values():
        frames = set(b["frames"]["frame_ids"])
        tracked = set(b["tracks"])
        a = b["account"]
        assert set(a["evidence"]["frames"]) <= frames
        for c in a["contributions"]:
            assert c["player_id"] in tracked
            for r in c["evidence"]:
                if r["kind"] == "frame":
                    assert set(r["player_ids"]) <= tracked
        for cf in a["counterfactuals"]:
            assert cf["decision_frame"]["frame_id"] in frames


def test_jumps_follow_the_account(bundles):
    for b in bundles.values():
        a = b["account"]
        assert [j["contribution_id"] for j in b["jumps"]] == [c["contribution_id"] for c in a["contributions"]]
        events = {e["action_id"]: e for e in b["events"]}
        for j, c in zip(b["jumps"], a["contributions"]):
            assert j["frame_id"] in b["frames"]["frame_ids"]
            frame_refs = [r["frame_id"] for r in c["evidence"] if r["kind"] == "frame"]
            if frame_refs:  # off-ball: the cited frame itself
                assert (j["source"], j["frame_id"]) == ("frame", frame_refs[0])
                assert j["frame_id"] in a["evidence"]["frames"]
            else:  # on-ball: the frame aligned with the cited event
                e = events[c["evidence"][0]["action_id"]]
                assert (j["source"], j["frame_id"], j["in_window"]) == ("event", e["frame_id"], e["in_window"])


def test_events_cover_the_chain_and_citations(bundles):
    b = bundles["SYN-0007-big_chance_saved-1"]
    ids = [e["action_id"] for e in b["events"]]
    a = b["account"]
    assert ids == sorted(ids)
    assert set(a["evidence"]["events"]) <= set(ids)
    assert {r["action_id"] for r in a["moment"]["chain"]} <= set(ids)
    save = next(e for e in b["events"] if e["action_id"] == 23)
    assert (save["type"], save["player_id"], save["in_window"]) == ("keeper_save", "NBR-01", True)


def test_missing_objects_stay_missing(accounts, match):
    a = accounts[0]
    w = a.moment.window
    gap = w.frame_start + 5
    t = match.tracking
    holed = Match(meta=match.meta, actions=match.actions, context=match.context,
                  tracking=t[~((t["frame_id"] == gap) & (t["player_id"] == "EPA-09"))], pass_targets=match.pass_targets)
    tr = export_moment(a, holed)["tracks"]["EPA-09"]
    assert tr["x"][5] is None and tr["vx"][5] is None and tr["x"][4] is not None and tr["x"][6] is not None


def test_deterministic_and_written_next_to_the_account(accounts, match, tmp_path):
    first = write_bundles(accounts[:2], match, tmp_path)
    text = [p.read_text(encoding="utf-8") for p in first]
    again = write_bundles(accounts[:2], match, tmp_path)
    assert [p.read_text(encoding="utf-8") for p in again] == text
    assert first[0] == bundle_path(accounts[0], tmp_path) == tmp_path / "SYN-0007" / f"{accounts[0].moment.moment_id}.bundle.json"
    assert text[0] == dumps(export_moment(accounts[0], match))
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert [e["bundle"] for e in index] == sorted(p.relative_to(tmp_path).as_posix() for p in first)
