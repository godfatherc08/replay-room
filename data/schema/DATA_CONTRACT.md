# Data contract

> **Status: ASSUMED, NOT VERIFIED.** No Innovation Studio data has been seen yet.
> Everything under "Raw feed" describes our own synthetic feed (`synthetic-v1`).
> The canonical contract is ours and does not change. When the real feed arrives, run the
> checklist at the bottom, write a new adapter in `src/replay_room/ingest/adapter.py`,
> and record what you found here.

## 1. Canonical contract (what every stage after ingest sees)

Defined in `src/replay_room/contracts/`. Produced only by a feed adapter.

| Property | Value |
|---|---|
| Units | metres (positions), m/s (velocities), seconds (time) |
| Pitch | 105 × 68 m (socceraction SPADL default) |
| Origin | bottom-left corner; x ∈ [0, 105] along the touchline, y ∈ [0, 68] |
| Direction of play | **home attacks +x (towards x = 105) in every period**; away coordinates are absolute, not mirrored. This is socceraction's converter convention. Call `socceraction.spadl.play_left_to_right(actions, home_team_id)` before xT/VAEP. |
| Time | `time_seconds` / `timestamp` restart at 0 each period (SPADL convention). The replay clock lays periods end to end on one timeline. |
| Events and tracking | same frame, same clock: an action at `(period_id, t)` lines up with the tracking frame at that timestamp (tested: actor within 1 m of the action's start). |

### On-ball actions: SPADL table

Columns `game_id, original_event_id, action_id, period_id, time_seconds, team_id, player_id, start_x, start_y, end_x, end_y, type_id, type_name, result_id, result_name, bodypart_id, bodypart_name`. The table validates against `socceraction.spadl.SPADLSchema`. Locations are clipped to the pitch. `action_id` is 0..n-1 in time order and is the **on-ball evidence key**. `original_event_id` links back to the raw record. IDs are strings (e.g. `NBR-09`).

### Context events (not SPADL)

The challenge asks us to ingest pressure events, possession changes and match metadata. SPADL has no type for these, so they go in `ContextEvent` with `kind` ∈ `period_start, period_end, pressure, possession_change, ball_out_of_play`. `player_id` is the actor (e.g. the presser) and `target_player_id` is the player acted on (the pressed carrier).

### Tracking table

Columns `frame_id, period_id, timestamp, player_id, team_id, x, y, vx, vy`. There is one row per object per frame: all 22 players plus the ball, whose `player_id` and `team_id` are both `"ball"`. `frame_id` is unique across the match and is the **off-ball evidence key**. **Positions and velocities are both present** and are observed, not modelled. Velocities agree with frame-to-frame displacement (tested). Tracking may sit slightly off the pitch: players up to ~1 m, the ball up to ~2.5 m behind the goal line (in the net, or out for a goal kick). SPADL locations are clipped and tracking is not.

## 2. Raw feed: `synthetic-v1` (fixture format; the adapter is the only reader)

Directory with three files:

* `meta.json`: `feed_version`, `match_id`, `competition`, `pitch.{length_m,width_m}`, `coordinates`, `frame_rate_hz` (10), `periods[] {id, duration_s, home_attacks: "+x"|"-x"}`, `teams.{home,away} {id, name, formation, players[] {id, name, number, position}}`, `final_score`, `generator {version, seed, attempt}`.
* `events.jsonl`: one event per line, `{id, period, t, type, team?, player?, x?, y?, end_x?, end_y?, outcome?, body_part?, recipient?, target?, cross?}`.
* `tracking.csv.gz`: columns `frame, period, t, object, team, x, y, vx, vy`. The ball has `object = BALL` and an empty team.

Raw frame: metres, **origin at the centre spot**, y up. **Sides switch at half time** (`home_attacks` flips), as real feeds do. The adapter maps raw to canonical with `x = s·x_raw + 52.5`, `y = s·y_raw + 34`, `v = s·v_raw`, where `s = +1` if the home team attacks raw +x in that period and `-1` otherwise.

### Event type mapping (raw → SPADL)

| Raw `type` | SPADL type | Result |
|---|---|---|
| `Pass` | `pass` (`cross` if `cross: true`) | complete → success, incomplete → fail |
| `KickOff` | `pass` | as Pass |
| `GoalKick` | `goalkick` | as Pass |
| `Carry` | `dribble` | success |
| `TakeOn` | `take_on` | won → success, lost → fail |
| `Tackle` | `tackle` | won → success, lost → fail |
| `Interception` | `interception` | success |
| `Shot` | `shot` | goal → success; saved / off_target / blocked → fail |
| `KeeperSave` | `keeper_save` | success |
| `Clearance` | `clearance` | success (mapped, not generated yet) |
| `Pressure` | context `pressure` | n/a |
| `PossessionChange` | context `possession_change` | n/a |
| `BallOut` | context `ball_out_of_play` | n/a |
| `PeriodStart` / `PeriodEnd` | context `period_start` / `period_end` | n/a |

Body part: `right_foot → foot_right`, `left_foot → foot_left`, `head → head`, missing → `foot`. Any unmapped type or outcome is an **error**, never silently dropped (tested: every raw event id is accounted for).

### Fixture: `data/fixtures/synthetic_match_01`

`python -m replay_room.ingest.generator --seed 7 --out data/fixtures/synthetic_match_01` regenerates it byte-for-byte (gzip mtime is pinned). It is NBR (4-3-3, home) v EPA (4-4-2), 2 × 150 s, 10 Hz, 3,002 frames × 23 objects, final score 1-3. **It is intentionally action-dense** (about 13 shots in 5 minutes) so that later stages get several goal moments with real build-ups to work on. It is not a realistic scoring rate.

## 3. Verify when the real feed arrives

- [ ] Coordinate system: origin (centre? corner?), axis directions, y up or down
- [ ] Units: metres, cm, or normalised 0–1 / 0–100? Pitch dimensions given per match?
- [ ] Pitch size ≠ 105 × 68 → decide whether to rescale to canonical (SPADL assumes 105 × 68)
- [ ] Direction of play per period, and whether the feed already normalises it
- [ ] Frame rate (10 / 25 Hz?), timestamp format, time origin per period vs whole match
- [ ] Are velocities supplied, or must they be derived (and smoothed)? Ball z present?
- [ ] Event taxonomy → SPADL mapping table (pressure? duels? carries supplied or inferred?)
- [ ] ID types and how event player ids join to tracking object ids
- [ ] Event timestamps vs tracking timestamps: same clock? any offset?
- [ ] Missing frames or objects (players off screen / subbed), and how they are encoded
