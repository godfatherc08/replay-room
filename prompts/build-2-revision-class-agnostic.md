# Build 2 Revision Prompt — Make the Moment Detector Class-Agnostic

> Paste into a Claude Code session in the `replay-room` repo. This revises Build 2's detector and the `Moment` contract to handle multiple moment classes through one path, so the attribution engine (Build 4) is broad from the start instead of retrofitted. Lives at `prompts/build-2-revision-class-agnostic.md`.
>
> **Context:** Build 1, Build 2 (goals-only), and Build 3 (metrics: xT/Δ-xT, xG, pitch control, VAEP-or-fallback) are done or finishing. xG now exists, so xG-thresholded detection is available.

---

You are the lead engineer on **Replay Room**. Goals-only is too narrow: 2–3 goals per match is 2–3 demos, and a penalty/deflection goal has a one-action chain that starves the whole "why." The engine (chain + window + outcome value) is class-agnostic by nature, so we make detection broad while keeping explanation disciplined. Read before you refactor.

## Step 1 — Read, in this order

1. `CLAUDE.md` — re-anchor on the governing principle and the deterministic wall.
2. Build 2's current code: the `Moment` contract, `segment_possessions`, `possession_index`, `detect_goal_moments`. You are extending these, not rewriting them — goal detection must keep working byte-for-byte.
3. Build 3's API: the **xG model** and `value_moment(...)`. The new detectors reuse xG; do not reimplement it.

## Step 2 — The governing distinction (write it back before coding)

In ~8 lines, state this rule and confirm you'll enforce it:

> **A moment belongs to the attribution engine iff its "why" is a question about scoring probability over space and actions.** Those are **explained** classes. Moments whose "why" is about rules, discipline, or officiating are **flagged** — detected and surfaced as talking points, but they get **no causal account** (the engine would hallucinate a tactical reason). We do not fake-explain them.

- **Explained classes (run full Build 4 engine):** `goal`, `turnover_to_shot`, `big_chance_saved`, `penalty`.
- **Flagged classes (detect + surface only, no attribution):** `offside`, `var_decision`, `injury`, `substitution`. **Red cards are excluded entirely for the MVP** — do not detect them.

Goals remain the **hero** class for the demo; the others prove breadth.

## Step 3 — The mission: class-agnostic detection

Extend the detector so every explained moment reduces to the same shape — `(chain_actions, window_frames, key_event, outcome_terminal_action)` — and flows through one downstream path.

Deliverables:

1. **`Moment` contract revision** (`src/replay_room/contracts/`):
   - `type: MomentClass` — enum over the explained + flagged classes above.
   - `engine_eligible: bool` — `True` for explained classes, `False` for flagged. Build 4 runs only on `engine_eligible` moments.
   - `outcome_ref` — the moment's **terminal action** (the goal, the shot, the saved shot, the penalty award) whose **value defines the outcome** Build 4 attributes over. This is the key generalization: the outcome is no longer hard-coded "goal = 1," it's the terminal action's threat/xG.
   - Keep the existing fields (`chain_actions`, `window_frames`, `key_event_ref`, teams, bounds). Goal moments populate them exactly as today.

2. **Keep `detect_goal_moments` intact**, and add a dispatcher `detect_moments(actions, frames, meta, classes=...)` that runs the requested detectors and returns a unified, time-sorted list of `Moment`s. Default to all explained classes; allow selecting a subset (goals-only for a focused demo).

3. **New explained-class detectors** (`src/replay_room/detect/`), each emitting the common `Moment` shape:
   - **`turnover_to_shot`** — a shot occurring within **N seconds of a regain/turnover** by the shooting team. Chain = from the regain to the shot; window = the pre-shot tracking window (same ~10–15 s logic, variable-length as before). Terminal action = the shot. *(Structural + optionally xG-weighted; works without xG but xG sets the "was it dangerous" bar.)*
   - **`big_chance_saved`** — a **shot with xG above a threshold that did not score** (saved/blocked/off-target-from-a-big-chance). Uses the Build 3 **xG model**. Terminal = the shot; the "outcome" is the *prevented* goal, so Build 4 will frame the headline around what created the chance and what denied it. Polarity note for Build 4 handoff: the terminal value is high xG but the realized outcome is a non-goal.
   - **`penalty`** — a penalty awarded. Chain = the build-up into the box and the foul; terminal = the penalty (fixed high xG ≈ 0.76). Keep simple.

4. **Flagged-class detectors** (lightweight): detect `offside`, `var_decision`, `injury`, `substitution` from the event stream and emit `Moment`s with `engine_eligible=False`, `chain`/`window` optional. No valuation, no attribution — they exist so the timeline is complete and the demo can show the system *declining* to fake-explain them.

5. **Thresholds as named constants** — turnover→shot seconds, big-chance xG cutoff, window length. Tunable, documented.

6. **CLI + tests**:
   - `python -m replay_room.detect data/fixtures/<match> --classes goal,turnover_to_shot,big_chance_saved,penalty` lists all detected moments with class, chain length, window bounds, `engine_eligible`, and terminal action.
   - `pytest`: goal detection unchanged (regression — same count, same chains as before the refactor); turnover→shot fires on a known regain-then-shot sequence; big_chance_saved fires on a high-xG non-goal and **not** on a low-xG shot; flagged classes carry `engine_eligible=False`; the dispatcher returns a correctly time-sorted unified list.

## Non-negotiables

- **Goal detection must not regress.** Existing goal moments come out identical. Add a regression test that asserts this.
- **One shape, one path.** Every explained moment is `(chain, window, key_event, outcome_terminal_action)`. No per-class branches downstream — the generalization lives in `outcome_ref`, and Build 4 will attribute over *that*, not over a hard-coded goal.
- **No red cards. No fake explanations.** Flagged classes get detected and surfaced, never a causal account.
- **Reuse Build 3's xG** for big_chance_saved; don't reimplement.
- **Still deterministic and tested.** Same input → same moments.

## Definition of done (the revision gate)

- `Moment` carries `type`, `engine_eligible`, and `outcome_ref`; goals populate it unchanged.
- `detect_moments(...)` returns a unified list across `goal`, `turnover_to_shot`, `big_chance_saved`, `penalty` (+ flagged classes marked ineligible).
- Goal regression test passes; new detectors pass their fixture tests.
- Build committed.

## How to work

Plan and files first, then tested commits: **`Moment` contract + `MomentClass` enum → dispatcher → turnover_to_shot → big_chance_saved (uses xG) → penalty → flagged detectors → CLI/tests (goal regression first)**. When the gate is met, summarize the moments found on the fixture by class, and confirm the handoff to **Build 4**: it consumes `engine_eligible` moments and attributes credit over each moment's `outcome_ref` value (generic outcome, not hard-coded goal) — with a note on the `big_chance_saved` polarity (high terminal xG, non-goal realized outcome).
