import pytest
from pydantic import ValidationError

from replay_room.contracts import CausalAccount, ContextEvent, Moment, SpadlAction
from replay_room.contracts.causal_account import SCHEMA_PATH, json_schema_text


def _ref(action_id, t):
    return {"kind": "event", "action_id": action_id, "original_event_id": f"e{action_id}", "period_id": 1,
            "time_seconds": t}


def _moment(**overrides):
    data = {
        "moment_id": "g1-goal-1",
        "type": "goal",
        "game_id": "g1",
        "period_id": 1,
        "t_event": 101.3,
        "attacking_team_id": "HOM",
        "defending_team_id": "AWY",
        "key_event_ref": _ref(42, 101.3),
        "key_player_id": "HOM-09",
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
    data = {
        "account_id": "acc-1",
        "game_id": "g1",
        "moment": _moment(),
        "headline_contribution_id": "c1",
        "contributions": [
            {
                "contribution_id": "c1",
                "rank": 1,
                "track": "on_ball",
                "kind": "action_value",
                "player_id": "HOM-08",
                "team_id": "HOM",
                "t": 99.8,
                "effect": 0.21,
                "metrics": {"vaep": 0.21},
                "evidence": [{"kind": "event", "action_id": 41, "original_event_id": "e41", "period_id": 1, "time_seconds": 99.8}],
            },
            {
                "contribution_id": "c2",
                "rank": 2,
                "track": "off_ball",
                "kind": "space_creation",
                "player_id": "HOM-11",
                "team_id": "HOM",
                "t": 99.0,
                "effect": 0.08,
                "evidence": [{"kind": "frame", "frame_id": 990, "timestamp": 99.0, "player_ids": ["HOM-11"]}],
            },
        ],
        "counterfactuals": [
            {
                "contribution_id": "c1",
                "chosen_value": 0.21,
                "alternatives": [
                    {
                        "description": "pass to HOM-07",
                        "target_player_id": "HOM-07",
                        "value": 0.25,
                        "evidence": [{"kind": "frame", "frame_id": 998, "timestamp": 99.8}],
                    }
                ],
            }
        ],
        "provenance": {
            "pipeline_version": "0.1.0",
            "source": "synthetic-v1",
            "effect_threshold": 0.02,
            "generated_at": "2026-10-20T00:00:00Z",
        },
    }
    data.update(overrides)
    return data


def test_causal_account_valid_roundtrip():
    account = CausalAccount.model_validate(_account())
    assert account.headline.player_id == "HOM-08"
    assert account.counterfactuals[0].best_gap == pytest.approx(0.04)
    again = CausalAccount.model_validate_json(account.model_dump_json())
    assert again == account


def test_contribution_without_evidence_rejected():
    data = _account()
    data["contributions"][0]["evidence"] = []
    with pytest.raises(ValidationError):
        CausalAccount.model_validate(data)


def test_off_ball_contribution_needs_frame_evidence():
    data = _account()
    data["contributions"][1]["evidence"] = [
        {"kind": "event", "action_id": 40, "original_event_id": "e40", "period_id": 1, "time_seconds": 99.0}
    ]
    with pytest.raises(ValidationError, match="frame reference"):
        CausalAccount.model_validate(data)


@pytest.mark.parametrize(
    "overrides",
    [
        {"headline_contribution_id": "nope"},
        {"counterfactuals": [{**_account()["counterfactuals"][0], "contribution_id": "c2"}]},
    ],
)
def test_dangling_references_rejected(overrides):
    with pytest.raises(ValidationError):
        CausalAccount.model_validate(_account(**overrides))


def test_ranks_must_be_contiguous():
    data = _account()
    data["contributions"][1]["rank"] = 3
    with pytest.raises(ValidationError, match="rank"):
        CausalAccount.model_validate(data)


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
    ],
)
def test_moment_invariants(overrides):
    with pytest.raises(ValidationError):
        Moment.model_validate(_moment(**overrides))
