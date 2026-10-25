"""The onside-correct corpus (generator v2): scoring moves are onside; offside is a deliberate, flagged class."""

from pathlib import Path

import pytest

from onside import decisive_passes, is_offside
from replay_room.contracts.moment import EXPLAINED_CLASSES, FLAGGED_CLASSES
from replay_room.detect import detect_moments
from replay_room.ingest import load_match
from replay_room.metrics import load_models

CORPUS = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "synthetic_match_02"


@pytest.fixture(scope="module")
def corpus():
    return load_match(CORPUS)


@pytest.fixture(scope="module")
def moments(corpus):
    found = detect_moments(corpus.actions, corpus.tracking, corpus.meta, (*EXPLAINED_CLASSES, *FLAGGED_CLASSES),
                           corpus.context, load_models().xg)
    return [c.moment for c in found]


def test_no_engine_eligible_scoring_moment_is_offside(corpus, moments):
    checked = 0
    for m in moments:
        if not m.engine_eligible:
            continue
        for period, t, receiver in decisive_passes(corpus, m):
            home = m.attacking_team_id == corpus.meta.home_team_id
            assert not is_offside(corpus.tracking, period, t, receiver, m.attacking_team_id, home), m.moment_id
            checked += 1
    assert checked >= 4  # about half the moves are set up by a pass (the rest by a regain or a carry): exercised


def test_every_completed_pass_finds_an_onside_receiver(corpus):
    a = corpus.actions.sort_values("action_id").reset_index(drop=True)
    for k, row in a[(a["type_name"] == "pass") & (a["result_name"] == "success")].iterrows():
        nxt = a.iloc[k + 1] if k + 1 < len(a) else None
        if nxt is None or nxt["team_id"] != row["team_id"]:
            continue
        home = row["team_id"] == corpus.meta.home_team_id
        assert not is_offside(corpus.tracking, int(row["period_id"]), float(row["time_seconds"]),
                              str(nxt["player_id"]), str(row["team_id"]), home), int(row["action_id"])


def test_offside_is_only_ever_a_flagged_class(corpus, moments):
    flagged = [m for m in moments if m.type == "offside"]  # this corpus has none; any would be flagged, and real
    assert all(not m.engine_eligible for m in flagged)  # described, never explained
    targets = corpus.pass_targets
    for m in flagged:  # each flag is a real offside: the intended receiver was beyond the line at the pass
        aid = m.key_event_ref.action_id
        row = corpus.actions.set_index("action_id").loc[aid]
        home = row["team_id"] == corpus.meta.home_team_id
        assert is_offside(corpus.tracking, int(row["period_id"]), float(row["time_seconds"]), str(targets[aid]),
                          str(row["team_id"]), home), m.moment_id


def test_the_menu_is_demo_sized(moments):
    explained = [m for m in moments if m.engine_eligible]
    assert 8 <= len(explained) <= 9  # a demo-sized menu
    assert sum(m.type == "goal" for m in explained) >= 2 and sum(m.type == "big_chance_saved" for m in explained) >= 2


def test_the_hero_carries_every_layer_of_the_analysis():
    from replay_room.attribution.engine import attribute_match

    (hero,) = [a for a in attribute_match(load_match(CORPUS)) if a.moment.moment_id == "SYN-0055-big_chance_saved-2"]
    assert hero.counterfactuals and hero.links  # a better option existed, and a computed link
