import pytest

from replay_room.metrics.orientation import LtrActions, orient, require_absolute, require_ltr


def test_forward_progress_positive_after_ltr(match):
    """NBR (home) attacks +x and EPA (away) attacks -x in the absolute frame; after orientation both attack +x."""
    a = match.actions.set_index("action_id")
    away_pass = a.loc[35]  # EPA-07's ball into the box before goal-1
    assert away_pass["team_id"] == "EPA" and away_pass["end_x"] < away_pass["start_x"]  # backwards in absolute
    ltr = require_ltr(orient(match.actions, match.meta.home_team_id)).set_index("action_id")
    assert ltr.loc[35, "end_x"] > ltr.loc[35, "start_x"]  # forward after orientation
    home_pass = a.loc[152]  # NBR-07's pass towards the box before goal-4
    assert ltr.loc[152, "end_x"] == home_pass["end_x"]  # home actions untouched


def test_orientation_does_not_mutate_input(match):
    before = match.actions.copy()
    orient(match.actions, match.meta.home_team_id)
    assert match.actions.equals(before)


def test_guards(match):
    ltr = orient(match.actions, match.meta.home_team_id)
    with pytest.raises(TypeError):
        orient(ltr, match.meta.home_team_id)  # no double flip
    with pytest.raises(TypeError):
        require_ltr(match.actions)  # xT/xG must not see absolute coordinates
    with pytest.raises(TypeError):
        require_absolute(ltr)  # VAEP must not see pre-oriented coordinates
    assert require_absolute(match.actions) is match.actions
    with pytest.raises(ValueError):
        orient(match.actions, "NOPE")
    assert isinstance(ltr, LtrActions)
