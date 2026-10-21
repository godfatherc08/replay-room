"""Moment export: the one self-contained JSON bundle the 3D viewer loads.

A bundle is the ``CausalAccount`` plus everything needed to *show* it, and
nothing that decides anything:

* ``pitch``: dimensions and frame conventions (canonical: metres, origin at
  the bottom-left corner, home attacks +x);
* ``teams``: rosters (ids, names, shirt numbers, positions) with home/away side;
* ``frames`` / ``tracks``: every tracking frame of the moment window, and per
  object (players and the ball) its observed ``x, y, vx, vy`` per frame
  (``null`` where the object is missing from a frame; never filled in);
* ``events``: the SPADL actions the viewer draws (the chain, the turnover, and
  every action the account cites), each with the window frame it aligns with;
* ``match``: teams, the score when the moment began, and the match clock
  (``period_offset_s`` turns a period time into elapsed match time);
* ``goalkeepers``: the goalkeepers' player ids (drawn in a distinct colour);
* ``display``: per contribution, title / subtitle / unit / time / match clock
  (``render.display``), all read off the account;
* ``narration``: the Build 6 narration of this account (validated), or null;
* ``match_moments``: every moment exported with this one (for the timeline);
* ``key_spot``: where the key event happened and the radius scale Build 4's
  off-ball track measured space at (``attribution.off_ball.SPOT_SIGMA``);
* ``jumps``: one per contribution, in rank order, the frame the camera jumps
  to. An off-ball fact jumps to its first cited frame; an on-ball fact to the
  frame aligned with its cited event (Build 3's nearest-frame rule). An event
  outside the window is clamped to the nearest window frame and marked
  ``in_window: false``.

Deterministic: same account + match -> byte-identical bundle.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np

from replay_room.attribution.off_ball import SPOT_SIGMA
from replay_room.attribution.store import ACCOUNTS_DIR
from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.pitch import BALL_ID, PITCH_LENGTH, PITCH_WIDTH
from replay_room.explain.schema import Narration
from replay_room.ingest.loader import Match
from replay_room.render.display import contribution_display, match_clock, score_before
from replay_room.metrics.pass_value import frame_ids_at

BUNDLE_VERSION = "2"


def _r(v: float) -> float | None:
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 2)


def bundle_path(account: CausalAccount, root: str | Path = ACCOUNTS_DIR) -> Path:
    return Path(root) / account.game_id / f"{account.moment.moment_id}.bundle.json"


def moment_entry(account: CausalAccount, match: Match) -> dict[str, Any]:
    m = account.moment
    return {"moment_id": m.moment_id, "type": m.type, "period_id": m.period_id, "t_event": round(m.t_event, 2),
            "realized": account.outcome.realized, "match_clock": match_clock(match.meta, m.period_id, m.t_event)}


def export_moment(account: CausalAccount, match: Match, narration: Narration | None = None,
                  moments: Iterable[CausalAccount] = ()) -> dict[str, Any]:
    m = account.moment
    w = m.window
    window = match.tracking[(match.tracking["frame_id"] >= w.frame_start) & (match.tracking["frame_id"] <= w.frame_end)]
    frames = window.drop_duplicates("frame_id").sort_values("frame_id")
    frame_ids = frames["frame_id"].astype(int).tolist()
    if frame_ids != list(range(w.frame_start, w.frame_end + 1)):
        raise ValueError(f"{m.moment_id}: tracking window {w.frame_start}..{w.frame_end} is not contiguous")
    col = {fid: k for k, fid in enumerate(frame_ids)}

    objects, tracks = [], {}
    for oid, rows in window.groupby("player_id", sort=True):
        team = str(rows["team_id"].iloc[0])
        objects.append({"id": str(oid), "team_id": None if oid == BALL_ID else team,
                        "kind": "ball" if oid == BALL_ID else "player"})
        series = {k: [None] * len(frame_ids) for k in ("x", "y", "vx", "vy")}
        for r in rows.itertuples(index=False):
            k = col[int(r.frame_id)]
            for name in series:
                series[name][k] = _r(getattr(r, name))
        tracks[str(oid)] = series

    by_id = match.actions.set_index("action_id", drop=False)
    cited = {r.action_id for c in account.contributions for r in c.evidence if r.kind == "event"}
    wanted = set(m.chain_action_ids) | cited | {m.outcome_ref.action_id}
    if m.turnover_event_ref is not None:
        wanted.add(m.turnover_event_ref.action_id)
    rows = by_id.loc[sorted(wanted)]
    aligned = frame_ids_at(match.tracking, rows["period_id"], rows["time_seconds"])
    events = []
    for r, fid in zip(rows.itertuples(index=False), aligned):
        inside = w.frame_start <= int(fid) <= w.frame_end
        events.append({
            "action_id": int(r.action_id), "original_event_id": str(r.original_event_id),
            "type": str(r.type_name), "result": str(r.result_name), "player_id": str(r.player_id),
            "team_id": str(r.team_id), "t": _r(r.time_seconds),
            "frame_id": int(np.clip(fid, w.frame_start, w.frame_end)), "in_window": inside,
            "start": [_r(r.start_x), _r(r.start_y)], "end": [_r(r.end_x), _r(r.end_y)],
        })
    event_frame = {e["action_id"]: (e["frame_id"], e["in_window"]) for e in events}

    jumps = []
    for c in account.contributions:
        frame_refs = [r for r in c.evidence if r.kind == "frame"]
        if frame_refs:
            jumps.append({"contribution_id": c.contribution_id, "frame_id": frame_refs[0].frame_id,
                          "source": "frame", "in_window": True})
        else:
            fid, inside = event_frame[c.evidence[0].action_id]
            jumps.append({"contribution_id": c.contribution_id, "frame_id": fid, "source": "event",
                          "in_window": inside})

    teams = []
    for side, t in (("home", match.meta.home_team), ("away", match.meta.away_team)):
        teams.append({"team_id": t.team_id, "name": t.name, "short_name": t.short_name, "side": side,
                      "players": [{"player_id": p.player_id, "name": p.name, "shirt_number": p.shirt_number,
                                   "position": p.position} for p in t.players]})
    meta = match.meta
    offset = sum(p.end_seconds - p.start_seconds for p in meta.periods if p.period_id < m.period_id)
    team = lambda t: {"team_id": t.team_id, "name": t.name, "short_name": t.short_name}  # noqa: E731
    return {
        "bundle_version": BUNDLE_VERSION,
        "account": account.model_dump(mode="json"),
        "pitch": {"length": PITCH_LENGTH, "width": PITCH_WIDTH, "units": "m",
                  "origin": "bottom-left corner", "x_axis": "along the touchline; the home team attacks +x",
                  "frame_rate_hz": match.meta.frame_rate_hz},
        "teams": teams,
        "frames": {"period_id": w.period_id, "frame_ids": frame_ids,
                   "timestamps": [_r(t) for t in frames["timestamp"]]},
        "objects": objects,
        "tracks": tracks,
        "events": events,
        "match": {
            "game_id": meta.game_id, "competition": meta.competition,
            "home": team(meta.home_team), "away": team(meta.away_team),
            "score_before": score_before(match.actions, meta, m.period_id, m.t_event),
            "period_offset_s": offset,
            "duration_s": sum(p.end_seconds - p.start_seconds for p in meta.periods),
            "moment_clock": match_clock(meta, m.period_id, m.t_event),
        },
        "goalkeepers": sorted(p.player_id for t in (meta.home_team, meta.away_team) for p in t.players
                              if p.position == "GK"),
        "display": contribution_display(account, meta),
        "narration": narration.model_dump(mode="json") if narration is not None else None,
        "match_moments": sorted((moment_entry(a, match) for a in moments),
                                key=lambda e: (e["period_id"], e["t_event"], e["moment_id"])),
        "key_spot": {"x": _r(by_id.at[m.key_event_ref.action_id, "start_x"]),
                     "y": _r(by_id.at[m.key_event_ref.action_id, "start_y"]), "sigma_m": SPOT_SIGMA},
        "jumps": jumps,
    }


def dumps(bundle: dict[str, Any]) -> str:
    return json.dumps(bundle, separators=(",", ":"), ensure_ascii=False) + "\n"


def write_bundles(accounts: Iterable[CausalAccount], match: Match, root: str | Path = ACCOUNTS_DIR,
                  narrations: dict[str, Narration] | None = None) -> list[Path]:
    """One bundle per account next to it, plus ``<root>/index.json`` listing every bundle under root.

    ``narrations``: moment_id -> its validated narration (omitted moments get none).
    """
    accounts = list(accounts)
    narrations = narrations or {}
    paths = []
    for account in accounts:
        path = bundle_path(account, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        bundle = export_moment(account, match, narrations.get(account.moment.moment_id), accounts)
        path.write_text(dumps(bundle), encoding="utf-8", newline="\n")
        paths.append(path)
    write_index(root)
    return paths


def write_index(root: str | Path = ACCOUNTS_DIR) -> Path:
    root = Path(root)
    entries = []
    for path in sorted(root.glob("*/*.bundle.json")):
        a = json.loads(path.read_text(encoding="utf-8"))["account"]
        entries.append({"moment_id": a["moment"]["moment_id"], "type": a["moment"]["type"],
                        "game_id": a["game_id"], "realized": a["outcome"]["realized"],
                        "bundle": path.relative_to(root).as_posix()})
    index = root / "index.json"
    index.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8", newline="\n")
    return index

