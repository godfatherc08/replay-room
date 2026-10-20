import pandas as pd
import pytest

from replay_room.detect.possessions import (
    FLEETING_MAX_SECONDS,
    control_team,
    is_goal,
    possession_index,
    segment_possessions,
)


def spadl(rows):
    """Hand-built SPADL rows: (period, t, team, type, result)."""
    return pd.DataFrame(
        [
            {"game_id": "g", "original_event_id": f"e{i}", "action_id": i, "period_id": p, "time_seconds": t,
             "team_id": team, "player_id": f"{team}-{i}", "type_name": typ, "result_name": res}
            for i, (p, t, team, typ, res) in enumerate(rows)
        ]
    )


# A hand-checked sequence covering every rule. Expected possessions are listed after it.
SEQUENCE = [
    (1, 0.0, "A", "pass", "success"),           # 0  A kickoff (period_start)
    (1, 2.0, "A", "dribble", "success"),        # 1
    (1, 3.0, "B", "tackle", "fail"),            # 2  failed tackle: no control change
    (1, 4.0, "A", "pass", "fail"),              # 3
    (1, 4.5, "B", "interception", "success"),   # 4  B regain...
    (1, 5.0, "A", "tackle", "success"),         # 5  ...won straight back: contested, merged into A
    (1, 6.0, "A", "pass", "success"),           # 6
    (1, 7.0, "B", "foul", "fail"),              # 7  foul: no control change
    (1, 9.0, "A", "freekick_short", "success"), # 8  set piece: new A possession
    (1, 10.0, "A", "shot", "fail"),             # 9
    (1, 10.5, "B", "keeper_save", "success"),   # 10 B regain (keeper)
    (1, 12.0, "B", "pass", "fail"),             # 11 keeper attempted a pass: B had control
    (1, 12.5, "A", "interception", "success"),  # 12 A regain
    (1, 13.0, "A", "shot", "success"),          # 13 GOAL A
    (1, 20.0, "B", "pass", "success"),          # 14 B kickoff
    (1, 22.0, "B", "cross", "success"),         # 15
    (1, 23.0, "A", "clearance", "owngoal"),     # 16 own goal by A: stays in B's possession, goal for B
    (1, 30.0, "A", "pass", "success"),          # 17 A kickoff
    (2, 0.0, "B", "pass", "success"),           # 18 period 2 start
    (2, 1.0, "B", "throw_in", "success"),       # 19 same team, but a restart: new possession
]
EXPECTED = [
    # (team, start, end, action_ids, contested)
    ("A", "period_start", "stoppage", (0, 1, 2, 3, 4, 5, 6, 7), (4,)),
    ("A", "set_piece", "turnover", (8, 9), ()),
    ("B", "regain", "turnover", (10, 11), ()),
    ("A", "regain", "goal", (12, 13), ()),
    ("B", "kickoff", "goal", (14, 15, 16), ()),
    ("A", "kickoff", "period_end", (17,), ()),
    ("B", "period_start", "stoppage", (18,), ()),
    ("B", "set_piece", "period_end", (19,), ()),
]


def test_hand_checked_sequence():
    got = segment_possessions(spadl(SEQUENCE))
    assert [(p.team_id, p.start_type, p.end_type, p.action_ids, p.contested_action_ids) for p in got] == EXPECTED
    assert [p.possession_id for p in got] == list(range(len(EXPECTED)))
    assert got[0].t_start == 0.0 and got[0].t_end == 7.0  # includes the foul


def test_slow_regain_is_a_real_possession():
    rows = [
        (1, 0.0, "A", "pass", "fail"),
        (1, 0.5, "B", "interception", "success"),
        (1, 0.5 + FLEETING_MAX_SECONDS + 0.5, "A", "tackle", "success"),
    ]
    assert [p.team_id for p in segment_possessions(spadl(rows))] == ["A", "B", "A"]


def test_input_not_modified():
    df = spadl(SEQUENCE).sample(frac=1, random_state=0)  # shuffled: segmentation sorts internally
    before = df.copy()
    assert len(segment_possessions(df)) == len(EXPECTED)
    pd.testing.assert_frame_equal(df, before)


@pytest.mark.parametrize(
    ("typ", "res", "goal", "control"),
    [
        ("shot", "success", True, "A"),
        ("shot_penalty", "success", True, "A"),
        ("shot", "fail", False, "A"),
        ("clearance", "owngoal", True, None),
        ("tackle", "fail", False, None),
        ("keeper_save", "fail", False, None),
        ("foul", "fail", False, None),
        ("pass", "fail", False, "A"),
    ],
)
def test_goal_and_control_predicates(typ, res, goal, control):
    assert is_goal(typ, res) is goal
    assert control_team(typ, res, "A") == control


def test_fixture_possessions_partition_the_actions(match):
    ps = segment_possessions(match.actions)
    ids = [aid for p in ps for aid in p.action_ids]
    assert ids == match.actions["action_id"].tolist()  # every action exactly once, in order
    idx = possession_index(ps)
    assert idx.loc[36] == idx.loc[31]  # EPA's first-half goal move is one possession
    assert sum(p.end_type == "goal" for p in ps) == 4


def test_fixture_hand_checked_first_half_boundaries(match):
    """Actions #13..#41, checked against the event log by hand."""
    ps = {p.action_ids[0]: p for p in segment_possessions(match.actions)}
    assert (ps[13].team_id, ps[13].action_ids[-1], ps[13].end_type) == ("EPA", 17, "turnover")  # shot saved
    assert (ps[18].team_id, ps[18].start_type, ps[18].action_ids) == ("NBR", "regain", (18, 19))  # keeper, pass lost
    assert (ps[23].team_id, ps[23].start_type, ps[23].action_ids[-1]) == ("NBR", "regain", 30)
    assert (ps[31].team_id, ps[31].start_type, ps[31].end_type) == ("EPA", "regain", "goal")
    assert (ps[37].team_id, ps[37].start_type) == ("NBR", "kickoff")
