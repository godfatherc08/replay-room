"""On-ball action contract: one SPADL action.

The bulk form is a pandas DataFrame that validates against
``socceraction.spadl.SPADLSchema`` (with names added). ``SpadlAction`` is the
row form used when actions are streamed one at a time by the replay clock.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from socceraction.spadl import config as _spadl

ACTION_TYPES: tuple[str, ...] = tuple(_spadl.actiontypes)
RESULTS: tuple[str, ...] = tuple(_spadl.results)
BODYPARTS: tuple[str, ...] = tuple(_spadl.bodyparts)

# Column order of the SPADL table produced by the loader.
SPADL_COLUMNS: tuple[str, ...] = (
    "game_id",
    "original_event_id",
    "action_id",
    "period_id",
    "time_seconds",
    "team_id",
    "player_id",
    "start_x",
    "start_y",
    "end_x",
    "end_y",
    "type_id",
    "type_name",
    "result_id",
    "result_name",
    "bodypart_id",
    "bodypart_name",
)


@dataclass(frozen=True, slots=True)
class SpadlAction:
    """One on-ball action in the canonical pitch frame (see ``contracts.pitch``).

    ``action_id`` is the stable on-ball evidence key for downstream stages;
    ``original_event_id`` links back to the raw feed record.
    """

    game_id: str
    original_event_id: str
    action_id: int
    period_id: int
    time_seconds: float
    team_id: str
    player_id: str
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    type_name: str
    result_name: str
    bodypart_name: str

    def __post_init__(self) -> None:
        if self.type_name not in ACTION_TYPES:
            raise ValueError(f"unknown SPADL type {self.type_name!r}")
        if self.result_name not in RESULTS:
            raise ValueError(f"unknown SPADL result {self.result_name!r}")
        if self.bodypart_name not in BODYPARTS:
            raise ValueError(f"unknown SPADL bodypart {self.bodypart_name!r}")

    @property
    def type_id(self) -> int:
        return ACTION_TYPES.index(self.type_name)

    @property
    def result_id(self) -> int:
        return RESULTS.index(self.result_name)

    @property
    def bodypart_id(self) -> int:
        return BODYPARTS.index(self.bodypart_name)

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row.update(type_id=self.type_id, result_id=self.result_id, bodypart_id=self.bodypart_id)
        return {col: row[col] for col in SPADL_COLUMNS}

    @classmethod
    def from_row(cls, row: Any) -> SpadlAction:
        """Build from a SPADL table row (mapping or pandas namedtuple/Series)."""
        get = row.get if hasattr(row, "get") else lambda k: getattr(row, k)
        return cls(
            game_id=str(get("game_id")),
            original_event_id=str(get("original_event_id")),
            action_id=int(get("action_id")),
            period_id=int(get("period_id")),
            time_seconds=float(get("time_seconds")),
            team_id=str(get("team_id")),
            player_id=str(get("player_id")),
            start_x=float(get("start_x")),
            start_y=float(get("start_y")),
            end_x=float(get("end_x")),
            end_y=float(get("end_y")),
            type_name=str(get("type_name")),
            result_name=str(get("result_name")),
            bodypart_name=str(get("bodypart_name")),
        )
