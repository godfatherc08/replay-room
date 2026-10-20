import asyncio

import pytest

from replay_room.contracts import MatchMeta, Period, Team
from replay_room.contracts.match import ContextEvent
from replay_room.ingest import FileReplaySource
from replay_room.ingest.source import FeedItem, IngestSource
from replay_room.replay import ReplayClock


class FakeTime:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, dt):
        self.now += dt


class TinySource(IngestSource):
    """Two 10 s periods with an item every second (timeline 0..19)."""

    def __init__(self):
        team = Team(team_id="A", name="A", short_name="A", players=())
        self._meta = MatchMeta(
            game_id="g", competition="c", home_team=team, away_team=team.model_copy(update={"team_id": "B"}),
            periods=(Period(period_id=1, start_seconds=0, end_seconds=10),
                     Period(period_id=2, start_seconds=0, end_seconds=10)),
            frame_rate_hz=1, source="test",
        )
        self._items = [
            FeedItem(p, float(t), "context", ContextEvent(f"e{p}-{t}", p, float(t), "pressure"))
            for p in (1, 2) for t in range(10)
        ]

    @property
    def meta(self):
        return self._meta

    def items(self):
        return self._items


def _ids(items):
    return [i.payload.event_id for i in items]


@pytest.fixture
def clock_and_time():
    ft = FakeTime()
    return ReplayClock(TinySource(), time_fn=ft), ft


def test_timeline_spans_periods(clock_and_time):
    clock, _ = clock_and_time
    assert clock.duration == 20
    assert clock.timeline_t(2, 3.0) == 13.0
    assert clock.period_t(13.0) == (2, 3.0)
    assert clock.period_t(10.0) == (2, 0.0)


def test_emits_as_time_passes_at_speed_1(clock_and_time):
    clock, ft = clock_and_time
    clock.play()
    assert _ids(clock.poll()) == ["e1-0"]
    ft.now += 2.5
    assert _ids(clock.poll()) == ["e1-1", "e1-2"]
    assert clock.poll() == []


def test_speed_scales_match_time(clock_and_time):
    clock, ft = clock_and_time
    clock.set_speed(4)
    clock.play()
    ft.now += 1.0
    assert clock.position == pytest.approx(4.0)
    assert len(clock.poll()) == 5
    clock.set_speed(0.5)  # change mid-play keeps the position continuous
    assert clock.position == pytest.approx(4.0)
    ft.now += 2.0
    assert clock.position == pytest.approx(5.0)
    with pytest.raises(ValueError):
        clock.set_speed(0)


def test_pause_freezes_time(clock_and_time):
    clock, ft = clock_and_time
    clock.play()
    ft.now += 3.0
    clock.poll()
    clock.pause()
    ft.now += 100.0
    assert clock.position == pytest.approx(3.0)
    assert clock.poll() == []
    clock.play()
    ft.now += 1.0
    assert _ids(clock.poll()) == ["e1-4"]


def test_seek_skips_and_rewinds(clock_and_time):
    clock, ft = clock_and_time
    seeks = []
    got = []
    clock.subscribe(got.append, on_seek=seeks.append)
    clock.seek_period(2, 5.0)
    clock.play()
    assert _ids(clock.poll()) == ["e2-5"]  # item exactly at the target is pending
    clock.seek(1.0)  # backwards
    assert _ids(clock.poll()) == ["e1-1"]
    assert seeks == [15.0, 1.0]
    assert _ids(got) == ["e2-5", "e1-1"]
    clock.seek(999)  # clamped to the end
    assert clock.position == 20 and clock.finished


def test_subscribe_filters_kinds_and_unsubscribes(clock_and_time):
    clock, _ = clock_and_time
    ctx, frames = [], []
    unsub = clock.subscribe(ctx.append, kinds=["context"])
    clock.subscribe(frames.append, kinds=["frame"])
    clock.advance_to(2.0)
    assert len(ctx) == 3 and frames == []
    unsub()
    clock.advance_to(5.0)
    assert len(ctx) == 3


def test_advance_to_ignores_wall_clock(clock_and_time):
    clock, _ = clock_and_time
    assert len(clock.advance_to(clock.duration)) == 20
    assert clock.finished


def test_run_drains_with_injected_sleep(clock_and_time):
    clock, ft = clock_and_time
    clock.set_speed(10)
    got = []
    clock.subscribe(got.append)
    clock.run(sleep=ft.sleep)
    assert len(got) == 20
    assert 1.8 <= ft.now - 1000.0 <= 2.0  # 19 s of match at x10


def test_run_on_tick_can_stop(clock_and_time):
    clock, ft = clock_and_time
    clock.run(sleep=ft.sleep, on_tick=lambda c: c.position >= 5)
    assert not clock.finished


def test_async_stream_yields_in_order():
    clock = ReplayClock(TinySource(), speed=200.0)

    async def collect():
        return [item async for item in clock.stream(max_idle=0.001)]

    items = asyncio.run(collect())
    assert _ids(items) == [f"e{p}-{t}" for p in (1, 2) for t in range(10)]


def test_fixture_stream_is_time_ordered(match):
    source = FileReplaySource(match)
    clock = ReplayClock(source)
    items = clock.advance_to(clock.duration)
    assert len(items) == len(source.items())
    times = [clock.timeline_t(i.period_id, i.t) for i in items]
    assert times == sorted(times)
    kinds = {i.kind for i in items}
    assert kinds == {"frame", "context", "action"}
    # Within a timestamp the frame (state at t) precedes what happens at t.
    first = items[:3]
    assert first[0].kind == "frame"
