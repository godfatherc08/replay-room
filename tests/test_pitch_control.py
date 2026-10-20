import numpy as np
import pandas as pd
import pytest

from replay_room.metrics.pitch_control import grid, influence, influence_control, voronoi_control


def _frame(rows, ball=(52.5, 34.0)):
    """rows: (player_id, team_id, x, y, vx, vy)."""
    data = list(rows) + [("ball", "ball", ball[0], ball[1], 0.0, 0.0)]
    return pd.DataFrame(data, columns=["player_id", "team_id", "x", "y", "vx", "vy"])


@pytest.fixture(scope="module")
def xy():
    return grid()


def test_grid_covers_pitch(xy):
    x, y = xy
    assert 0 < x[0] < x[-1] < 105 and 0 < y[0] < y[-1] < 68
    assert np.allclose(np.diff(x), 105 / len(x))


def test_controls_sum_to_one(xy, match):
    x, y = xy
    frame = match.tracking[match.tracking["frame_id"] == 2290]
    home = influence_control(frame, "NBR", x, y)
    away = influence_control(frame, "EPA", x, y)
    assert home.shape == (len(y), len(x))
    assert np.allclose(home + away, 1.0)
    assert ((home >= 0) & (home <= 1)).all()


def test_high_at_isolated_players_own_position(xy):
    x, y = xy
    frame = _frame([("A", "H", 30.0, 20.0, 0.0, 0.0), ("B", "W", 80.0, 50.0, 0.0, 0.0)])
    pc = influence_control(frame, "H", x, y)
    i, j = np.abs(x - 30).argmin(), np.abs(y - 20).argmin()
    assert pc[j, i] > 0.7  # sigmoid(1) ~ 0.73 at an isolated player's cell
    i, j = np.abs(x - 80).argmin(), np.abs(y - 50).argmin()
    assert pc[j, i] < 0.3


def test_influence_normalised_and_leads_with_velocity():
    cells = np.array([[50.0, 34.0], [55.0, 34.0], [45.0, 34.0]])
    pos, ball = np.array([[50.0, 34.0]]), np.array([60.0, 34.0])
    still = influence(pos, np.zeros((1, 2)), ball, cells)[0]
    assert still[0] == pytest.approx(1.0)  # normalised at the player's own position
    running = influence(pos, np.array([[7.0, 0.0]]), ball, cells)[0]
    assert running[1] > running[2]  # influence extends ahead, not behind


def test_wider_influence_far_from_ball():
    cells = np.array([[56.0, 34.0]])
    pos = np.array([[50.0, 34.0]])
    near = influence(pos, np.zeros((1, 2)), np.array([50.0, 34.0]), cells)[0, 0]
    far = influence(pos, np.zeros((1, 2)), np.array([10.0, 34.0]), cells)[0, 0]
    assert far > near


def test_agrees_with_voronoi_baseline(xy, match):
    x, y = xy
    frame = match.tracking[match.tracking["frame_id"] == 1800]
    pc = influence_control(frame, "EPA", x, y)
    vo = voronoi_control(frame, "EPA", x, y)
    assert set(np.unique(vo)) <= {0.0, 1.0}
    assert ((pc > 0.5) == (vo > 0.5)).mean() > 0.85


def test_frame_without_ball_rejected(xy):
    x, y = xy
    frame = _frame([("A", "H", 30.0, 20.0, 0.0, 0.0)])
    with pytest.raises(ValueError):
        influence_control(frame[frame["player_id"] != "ball"], "H", x, y)
