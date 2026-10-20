import copy

import pytest
from pydantic import ValidationError

from replay_room.contracts import CausalAccount, ContextEvent, Moment, SpadlAction
from replay_room.contracts.causal_account import SCHEMA_PATH, json_schema_text


def _ref(action_id, t):
    return {"kind": "event", "action_id": action_id, "original_event_id": f"e{action_id}", "period_id": 1,
            "time_seconds": t}


def _frame(frame_id, *players):
    return {"kind": "frame", "frame_id": frame_id, "timestamp": frame_id / 10, "player_ids": list(players)}


def _moment(**overrides):
    data = {
        "moment_id": "g1-goal-1",
        "type": "goal",
        "engine_eligible": True,
        "game_id": "g1",
        "period_id": 1,
        "t_event": 101.3,
        "attacking_team_id": "HOM",
        "defending_team_id": "AWY",
        "key_event_ref": _ref(42, 101.3),
        "key_player_id": "HOM-07",
        "outcome_ref": _ref(42, 101.3),
        "outcome_scored": True,
        "possession_id": 7,
        "chain": [_ref(39, 95.0), _ref(40, 97.0), _ref(41, 99.8), _ref(42, 101.3)],
        "chain_start": "regain",
        "turnover_event_ref": _ref(38, 94.6),
        "contested_action_ids": [40],
        "t_start": 89.3,
        "t_end": 103.3,
        "window": {"period_id": 1, "frame_start": 893, "frame_end": 1033, "t_start": 89.3, "t_end": 103.3},
    }
    data.update(overrides)
    return data


def _account(**overrides):
    """Mirrors the example account in REPLAY_ROOM_TECHNICAL_SPEC.md section 4."""
    data = {
        "account_id": "acc-1",
        "game_id": "g1",
        "moment": _moment(),
        "outcome": {"ref": _ref(42, 101.3), "value": 0.41, "value_source": "xg", "scored": True, "realized": True,
                    "beneficiary_team_id": "HOM", "conceding_team_id": "AWY"},
        "teams": [{"team_id": "HOM", "name": "Home FC"}, {"team_id": "AWY", "name": "Away FC"}],
        "participants": [
            {"player_id": "HOM-07", "name": "A Seven", "team_id": "HOM"},
            {"player_id": "HOM-09", "name": "A Nine", "team_id": "HOM"},
            {"player_id": "AWY-04", "name": "D Four", "team_id": "AWY"},
        ],
        "headline_contribution_id": "c1",
        "contributions": [
            {
                "contribution_id": "c1", "rank": 1, "track": "off_ball", "kind": "marking_break",
                "role": "primary_cause", "signal": "stopped_tracking_runner",
                "player_id": "AWY-04", "team_id": "AWY", "t": 99.4, "effect": 0.18,
                "metrics": {"space_conceded": 0.18}, "evidence": [_frame(994, "AWY-04", "HOM-07")],
            },
            {
                "contribution_id": "c2", "rank": 2, "track": "off_ball", "kind": "space_creation",
                "role": "space_creation", "signal": "run_in_behind",
                "player_id": "HOM-07", "team_id": "HOM", "t": 99.0, "effect": 0.14,
                "metrics": {"space_created": 0.14}, "evidence": [_frame(990, "HOM-07")],
            },
            {
                "contribution_id": "c3", "rank": 3, "track": "on_ball", "kind": "action_value",
                "role": "assist", "action": "through_ball",
                "player_id": "HOM-09", "team_id": "HOM", "t": 99.8, "effect": 0.11,
                "metrics": {"vaep": 0.11}, "evidence": [_ref(41, 99.8)],
            },
            {
                "contribution_id": "c4", "rank": 4, "track": "on_ball", "kind": "action_value",
                "role": "finish", "action": "shot",
                "player_id": "HOM-07", "team_id": "HOM", "t": 101.3, "effect": 0.09,
                "metrics": {"xg": 0.41, "vaep": 0.09}, "evidence": [_ref(42, 101.3)],
            },
        ],
        "counterfactuals": [
            {
                "contribution_id": "c4",
                "decision_frame": _frame(1013, "HOM-07", "HOM-09"),
                "chosen": "shot",
                "chosen_value": 0.41,
                "alternatives": [
                    {"description": "square pass to HOM-09", "target_player_id": "HOM-09",
                     "completion_prob": 0.83, "value": 0.55, "evidence": [_frame(1013, "HOM-09")]},
                ],
            }
        ],
        "evidence": {"events": [41, 42], "frames": [990, 994, 1013]},
        "provenance": {
            "pipeline_version": "0.1.0",
            "source": "synthetic-v1",
            "effect_threshold": 0.02,
            "counterfactual_margin": 0.05,
            "generated_at": "2026-10-20T00:00:00Z",
        },
    }
    data.update(overrides)
    return data


def _mutated(fn):
    data = copy.deepcopy(_account())
    fn(data)
    return data


def test_causal_account_valid_roundtrip():
    account = CausalAccount.model_validate(_account())
    assert account.headline.signal == "stopped_tracking_runner"
    assert account.counterfactuals[0].best_gap == pytest.approx(0.14)
    assert account.evidence_index() == {"events": (41, 42), "frames": (990, 994, 1013)}
    again = CausalAccount.model_validate_json(account.model_dump_json())
    assert again == account


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda d: d["contributions"][0].update(evidence=[]), None),
        (lambda d: d["contributions"][0].update(evidence=[_ref(41, 99.8)]), "frame reference"),
        (lambda d: d["contributions"][2].update(evidence=[_frame(998)]), "event reference"),
        (lambda d: d["contributions"][2].update(action=None), "action label"),
        (lambda d: d["contributions"][1].update(signal=None), "signal label"),
        (lambda d: d["contributions"][1].update(rank=3), "rank"),
        (lambda d: d["contributions"][3].update(effect=-0.5), r"\|effect\|"),
        (lambda d: d["contributions"][1].update(role="primary_cause"), "primary_cause"),
        (lambda d: d.update(headline_contribution_id="nope"), "headline"),
        (lambda d: d["counterfactuals"][0].update(contribution_id="c2"), "on-ball"),
        (lambda d: d["provenance"].update(counterfactual_margin=0.2), "margin"),
        (lambda d: d["counterfactuals"][0]["alternatives"].append(
            {"description": "shoot far post", "value": 0.6, "evidence": [_frame(1013)]}), "best first"),
        (lambda d: d["participants"].pop(), "participants"),
        (lambda d: d["outcome"].update(ref=_ref(41, 99.8)), "outcome must match"),
        (lambda d: d["outcome"].update(beneficiary_team_id="AWY", conceding_team_id="HOM"), "outcome must match"),
        (lambda d: d["outcome"].update(realized=False), "denied the chance"),
        (lambda d: d["contributions"][1].update(evidence=[_frame(2000, "HOM-07")]), "outside the moment window"),
        (lambda d: d["evidence"].update(frames=[990, 994]), "exactly the records"),
        (lambda d: d["teams"][1].update(team_id="XYZ"), "teams"),
    ],
)
def test_account_invariants(mutate, match):
    with pytest.raises(ValidationError, match=match):
        CausalAccount.model_validate(_mutated(mutate))


def test_checked_in_json_schema_is_current():
    # Regenerate with: python -m replay_room.contracts
    assert SCHEMA_PATH.read_text(encoding="utf-8") == json_schema_text()


def test_spadl_action_vocabulary_and_ids():
    a = SpadlAction("g", "e1", 0, 1, 1.0, "HOM", "HOM-01", 1, 2, 3, 4, "pass", "success", "foot_right")
    row = a.to_row()
    assert (row["type_id"], row["result_id"]) == (0, 1)
    assert SpadlAction.from_row(row) == a
    with pytest.raises(ValueError):
        SpadlAction("g", "e1", 0, 1, 1.0, "HOM", "HOM-01", 1, 2, 3, 4, "volley", "success", "foot")


def test_context_event_kind_checked():
    ContextEvent("e1", 1, 0.0, "pressure")
    with pytest.raises(ValueError):
        ContextEvent("e1", 1, 0.0, "goal")


def test_moment_valid():
    m = Moment.model_validate(_moment())
    assert m.chain_action_ids == (39, 40, 41, 42)
    assert m.window.n_frames == 141


@pytest.mark.parametrize(
    "overrides",
    [
        {"chain": [_ref(39, 95.0), _ref(41, 99.8)]},  # does not end at the key event
        {"chain": [_ref(40, 97.0), _ref(39, 95.0), _ref(42, 101.3)]},  # out of order
        {"contested_action_ids": [12]},  # not in the chain
        {"turnover_event_ref": None},  # regain without the lost-ball action
        {"chain_start": "kickoff"},  # kickoff with a turnover event
        {"turnover_event_ref": _ref(40, 97.0)},  # turnover inside the chain
        {"defending_team_id": "HOM"},
        {"t_end": 100.0},
        {"window": {"period_id": 2, "frame_start": 893, "frame_end": 1033, "t_start": 89.3, "t_end": 103.3}},
        {"window": {"period_id": 1, "frame_start": 1033, "frame_end": 893, "t_start": 89.3, "t_end": 103.3}},
        {"engine_eligible": False},  # a goal is explained
        {"outcome_ref": None},  # explained moments name their terminal action
        {"outcome_scored": False},  # a goal moment scored
        {"outcome_ref": _ref(43, 103.0)},  # outcome is the key event (only a penalty's follows it)
        {"type": "big_chance_saved"},  # ...that did not score
        {"secondary_types": ["goal"]},  # not its own type
        {"window": None},
        {"key_event_ref": {"kind": "context", "event_id": "c1", "period_id": 1, "time_seconds": 101.3}},
    ],
)
def test_moment_invariants(overrides):
    with pytest.raises(ValidationError):
        Moment.model_validate(_moment(**overrides))


def _flagged(**overrides):
    data = {
        "moment_id": "g1-substitution-1", "type": "substitution", "engine_eligible": False, "game_id": "g1",
        "period_id": 2, "t_event": 61.0, "attacking_team_id": None, "defending_team_id": None, "team_id": "HOM",
        "key_event_ref": {"kind": "context", "event_id": "c9", "period_id": 2, "time_seconds": 61.0},
        "key_player_id": "HOM-07", "t_start": 61.0, "t_end": 61.0,
    }
    data.update(overrides)
    return data


def test_flagged_moment_valid():
    m = Moment.model_validate(_flagged())
    assert not m.engine_eligible and m.chain == () and m.window is None and m.outcome_ref is None
    assert Moment.model_validate_json(m.model_dump_json()) == m


def test_penalty_outcome_follows_key_event():
    m = Moment.model_validate(_moment(type="penalty", outcome_ref=_ref(43, 140.0), outcome_xg=0.76,
                                      secondary_types=["goal"]))
    assert m.outcome_ref.action_id == 43 and m.key_event_ref.action_id == 42


@pytest.mark.parametrize(
    "overrides",
    [
        {"engine_eligible": True},  # flagged classes are never engine-eligible
        {"chain": [_ref(39, 61.0)]},
        {"outcome_ref": _ref(42, 61.0)},
        {"outcome_xg": 0.3},
        {"possession_id": 3},
        {"attacking_team_id": "HOM"},  # attacking and defending come together
    ],
)
def test_flagged_moment_invariants(overrides):
    with pytest.raises(ValidationError):
        Moment.model_validate(_flagged(**overrides))


def test_account_rejects_flagged_moment():
    offside = _flagged(type="offside", moment_id="g1-offside-1", attacking_team_id="HOM", defending_team_id="AWY",
                       period_id=1, t_event=101.3, t_start=101.3, t_end=101.3, key_event_ref=_ref(42, 101.3))
    with pytest.raises(ValidationError, match="flagged, not explained"):
        CausalAccount.model_validate(_account(moment=offside))
