import json

import pytest

from replay_room.explain import narrate
from replay_room.framing import rules_plan
from replay_room.ingest.loader import Match
from replay_room.render import bundle_path, export_moment, write_bundles
from replay_room.render.export import BUNDLE_VERSION, dumps


@pytest.fixture(scope="module")
def accounts(all_accounts):
    return list(all_accounts.values())


@pytest.fixture(scope="module")
def told(accounts, all_contexts):
    out = {}
    for a in accounts:
        ctx = all_contexts[a.moment.moment_id]
        plan = rules_plan(a, ctx)
        out[a.moment.moment_id] = {"narration": narrate(a, "template", context=ctx, plan=plan), "plan": plan,
                                   "context": ctx}
    return out


def _export(a, match, told, accounts):
    t = told[a.moment.moment_id]
    return export_moment(a, match, t["narration"], t["plan"], accounts, t["context"])


@pytest.fixture(scope="module")
def bundles(accounts, match, told):
    return {a.moment.moment_id: _export(a, match, told, accounts) for a in accounts}


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
    key = next(e for e in b["events"] if e["action_id"] == a["moment"]["key_event_ref"]["action_id"])
    assert [b["key_spot"]["x"], b["key_spot"]["y"]] == key["start"] and b["key_spot"]["sigma_m"] == 4.0
    save = next(e for e in b["events"] if e["action_id"] == 23)
    assert (save["type"], save["player_id"], save["in_window"]) == ("keeper_save", "NBR-01", True)


def test_missing_objects_stay_missing(accounts, match, told):
    a = accounts[0]
    w = a.moment.window
    gap = w.frame_start + 5
    t = match.tracking
    holed = Match(meta=match.meta, actions=match.actions, context=match.context,
                  tracking=t[~((t["frame_id"] == gap) & (t["player_id"] == "EPA-09"))], pass_targets=match.pass_targets)
    tr = _export(a, holed, told, accounts)["tracks"]["EPA-09"]
    assert tr["x"][5] is None and tr["vx"][5] is None and tr["x"][4] is not None and tr["x"][6] is not None


def test_deterministic_and_written_next_to_the_account(accounts, match, told, tmp_path):
    first = write_bundles(accounts[:2], match, told, tmp_path)
    text = [p.read_text(encoding="utf-8") for p in first]
    again = write_bundles(accounts[:2], match, told, tmp_path)
    assert [p.read_text(encoding="utf-8") for p in again] == text
    assert first[0] == bundle_path(accounts[0], tmp_path) == tmp_path / "SYN-0007" / f"{accounts[0].moment.moment_id}.bundle.json"
    assert text[0] == dumps(_export(accounts[0], match, told, accounts[:2]))
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert [e["bundle"] for e in index] == sorted(p.relative_to(tmp_path).as_posix() for p in first)


def test_match_header_fields(bundles, match):
    b = bundles["SYN-0007-goal-4"]  # NBR's goal at 2nd-half 78.0 s: EPA scored three before it
    assert b["match"]["home"] == {"team_id": "NBR", "name": "Northbridge FC", "short_name": "NBR"}
    assert b["match"]["score_before"] == {"home": 0, "away": 3}
    assert b["match"]["period_offset_s"] == 150.0 and b["match"]["duration_s"] == 300.0
    assert b["match"]["moment_clock"] == "03:48"  # 150 + 78.0 s
    first = bundles["SYN-0007-turnover_to_shot-1"]
    assert first["match"]["score_before"] == {"home": 0, "away": 0}
    keepers = set(b["goalkeepers"])
    assert keepers == {p["player_id"] for t in b["teams"] for p in t["players"] if p["position"] == "GK"}
    assert len(keepers) == 2


def test_display_rows_follow_the_account(bundles):
    for b in bundles.values():
        a = b["account"]
        assert [d["contribution_id"] for d in b["display"]] == [c["contribution_id"] for c in a["contributions"]]
        for d, c in zip(b["display"], a["contributions"]):
            ref = c["evidence"][0]
            assert d["t"] == round(ref["time_seconds"] if ref["kind"] == "event" else ref["timestamp"], 2)
            assert d["title"].lower() == (c["action"] or c["signal"]).replace("_", " ")
            if c["kind"] == "chance_denied":
                assert d["unit"] == "xG"
            elif c["track"] == "off_ball":
                assert d["unit"] == "P(goal)"
    hero = bundles["SYN-0007-big_chance_saved-3"]
    units = {d["contribution_id"]: d["unit"] for d in hero["display"]}
    assert units["d163"] == "xG" and units["a163"] == "ΔxT" and units["a157"] == "VAEP"


def test_narration_plan_context_and_moments_are_embedded(bundles, accounts):
    for b in bundles.values():
        n = b["narration"]
        assert n["moment_id"] == b["account"]["moment"]["moment_id"] and n["narration_version"] == "2"
        assert [x["beat_id"] for x in n["beats"]] == [x["beat_id"] for x in b["plan"]["beats"]]
        assert b["context"]["moment_id"] == n["moment_id"] and b["editions"] == {}
        cited = {r["action_id"] for x in n["beats"] for r in x["refs"] if r["kind"] == "event"}
        assert cited <= {e["action_id"] for e in b["events"]}  # every event a beat cites can be drawn
        assert [m["moment_id"] for m in b["match_moments"]] == sorted(
            (a.moment.moment_id for a in accounts),
            key=lambda i: next((a.moment.period_id, a.moment.t_event, i) for a in accounts if a.moment.moment_id == i))


def test_meaning_glosses_every_contribution(bundles):
    for b in bundles.values():
        a = b["account"]
        rows = b["meaning"]
        assert [m["contribution_id"] for m in rows] == [c["contribution_id"] for c in a["contributions"]]
        peak = max(abs(c["effect"]) for c in a["contributions"])
        for m, c in zip(rows, a["contributions"]):
            assert m["gloss"] and m["icon"] in {"pass", "carry", "shot", "save", "turnover", "run", "space", "marking"}
            assert m["positive"] == (c["effect"] >= 0)
            assert m["magnitude"] == pytest.approx(abs(c["effect"]) / peak, abs=1e-3)
        assert max(m["magnitude"] for m in rows) == 1.0
    hero = {m["contribution_id"]: m for m in bundles["SYN-0007-big_chance_saved-3"]["meaning"]}
    assert hero["d163"]["gloss"] == "the miss that let them off" and not hero["d163"]["positive"]
    assert hero["a157"]["gloss"] == "a dangerous pass"  # VAEP +0.087 >= DANGEROUS_VALUE
    assert hero["a159"]["gloss"] == "moved the ball forward"
    assert hero["a161"]["gloss"] == "set up the shot"
    assert hero["sEPA-11"]["icon"] == "run" and hero["sNBR-05"]["gloss"] == "left space open"
    saved = {m["contribution_id"]: m for m in bundles["SYN-0007-big_chance_saved-1"]["meaning"]}
    assert saved["d23"]["gloss"] == "the save that stopped it" and saved["d23"]["icon"] == "save"
    assert saved["a19"]["gloss"] == "lost possession here" and saved["a19"]["icon"] == "turnover"


def test_outcome_display_and_kits(bundles):
    hero = bundles["SYN-0007-big_chance_saved-3"]
    assert hero["outcome_display"] == {"percent": 15, "label": "15% chance of scoring", "band": "a good chance",
                                       "result": "A goal that didn't happen"}
    assert bundles["SYN-0007-goal-1"]["outcome_display"]["result"] == "Goal"
    for b in bundles.values():
        kits = {t["side"]: t["kit"] for t in b["teams"]}
        assert kits["home"]["shirt"] != kits["away"]["shirt"]
        assert kits["home"]["keeper"] not in (kits["home"]["shirt"], kits["away"]["shirt"])


def test_story_plays_the_plan_in_both_registers(bundles):
    for b in bundles.values():
        story, plan = b["story"], b["plan"]
        assert [s["index"] for s in story] == list(range(len(story)))
        assert [(s["beat_id"], s["kind"]) for s in story] == [(x["beat_id"], x["kind"]) for x in plan["beats"]]
        frames = set(b["frames"]["frame_ids"])
        told = {x["beat_id"]: x for x in b["narration"]["beats"]}
        for s in story:
            assert s["frame_id"] in frames
            assert (s["caption"], s["plain"]) == (told[s["beat_id"]]["text"], told[s["beat_id"]]["fan"])
            assert not any(ch.isdigit() for ch in s["plain"])
    hero = bundles["SYN-0007-big_chance_saved-3"]["story"]
    assert [s["kind"] for s in hero[-3:]] == ["lead", "outcome", "counterfactual"]
    assert hero[-1]["frame_id"] == 2408  # the decision frame
    flaw = next(s for s in hero if s["kind"] == "flaw")
    assert flaw["link_id"] == "LNBR-05" and flaw["frame_id"] == 2419  # the link's end: the gap at its widest
    assert hero[-1]["plain"] == "Instead of the pass to Ferraro, Hale had a better option: a pass to Adeyemi."
