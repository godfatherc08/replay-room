# Build 4 Kickoff Prompt — Causal Attribution + Evidence Trace (THE EDGE)

> Paste into a Claude Code session in the `replay-room` repo, after Build 3 (metrics) and the Build 2 class-agnostic revision are committed and green. Lives at `prompts/build-4-attribution.md`.
>
> **This is the build the whole product exists for.** Everything before it was setup; this is the moat. No LLM touches this stage. Read everything before writing a line.

---

You are the lead engineer on **Replay Room**. The pipeline now ingests, detects class-agnostic moments, and values every action and frame. Build 4 turns a valued moment into a **ranked, evidence-bound causal account** — the computed "why" that the language model will later only narrate. If this stage is correct, the product wins; if it's hand-wavy, everything downstream is confident nonsense. Treat it that way.

## Step 1 — Read, in this order

1. `CLAUDE.md` — the governing principle and the two-track engine description. **No LLM, no narration, no 3D here. Pure deterministic Python.**
2. `REPLAY_ROOM_TECHNICAL_SPEC.md` — §4 in full (two tracks, fusion, evidence, counterfactual) and the `CausalAccount` JSON example.
3. **Upstream API you consume (do not reimplement):**
   - Build 2 revision: `Moment` with `type`, `engine_eligible`, `outcome_ref` (terminal action), `chain_actions`, `window_frames`, teams. Run **only on `engine_eligible` moments.**
   - Build 3: `value_moment(...)` → every chain action carries a value delta (VAEP if it validated, else the documented Δ-xT fallback); every window frame carries a **pitch-control surface**. xG on the terminal action. Orientation already normalized (`play_left_to_right`).
4. The handoff you already wrote: attribute over **`outcome_ref`'s value**, no special case per class; for a penalty the key event is the foul and `outcome_ref` is the kick (xG ≈ 0.76); for `big_chance_saved`, `outcome_xg` is high but `outcome_scored` is false, so the headline is what *created* the chance and what *stopped* it, measured against a goal that didn't happen.

## Step 2 — Nail the semantics before coding (write it back, ~12 lines)

The hard part of Build 4 is not code, it's getting the attribution *frame* right. State these precisely:

- **Outcome value V** = the value of the moment's `outcome_ref` (the terminal action's xG/threat). Attribution is *over V*, never a hard-coded "goal = 1."
- **Beneficiary vs conceder.** The attacking team stands to realize the outcome; the defending team to prevent it. Contributions are **signed toward the beneficiary realizing the outcome.**
- **Realized vs prevented outcome.** `outcome_scored` (or equivalent) splits two framings:
  - **Realized** (goal; shot taken in turnover_to_shot; penalty) → rank who drove P(outcome) **up** (creators, attacking) and the largest **failure to prevent** (the defensive/marking lapse = candidate headline cause).
  - **Prevented** (`big_chance_saved`) → the chance was built (attacking creators still get credit) **and then denied**; the **preventing action** (save/block/last-ditch defending) is the large **defensive positive** and the natural headline. Frame explicitly as "a goal that didn't happen."
- **Evidence threshold.** A contribution enters the account only if its **marginal effect on P(outcome)** clears a cutoff (top-k and/or a delta floor). Low-impact touches are filtered out.
- **Binding.** Every surviving contribution binds to a concrete record — **event id** (on-ball) or **tracking frame** (off-ball) — so stage 6 cites it and stage 5 jumps the camera to it.

Don't code until this is written and internally consistent.

## Step 3 — The mission: Build 4 only

Produce, per `engine_eligible` moment, a populated **`CausalAccount`** (the contract drafted in Build 1). Pure deterministic Python. No model call anywhere in this stage.

Deliverables:

1. **Finalize the `CausalAccount` contract** (`src/replay_room/contracts/`): `moment_id`, `type`, `outcome` (`{ref, value, realized: bool, beneficiary_team, …}`), `contributions[]` (each: `track` on_ball/off_ball, `ref` event-id-or-frame, `player`, `team`, `signal`, `value` signed marginal effect, `role`), `headline_cause` (a contribution ref), optional `counterfactual`, and `evidence` (the event + frame refs). Keep it the stable interface Builds 5/6/7 consume.

2. **On-ball track** (`src/replay_room/attribution/on_ball.py`): read each chain action's value delta from Build 3. Positive deltas = build-up contributors (progression, key pass, assist); the largest negative delta on the conceding side before the outcome = the on-ball mistake. Each becomes a contribution bound to its **event id**.

3. **Off-ball track** (`src/replay_room/attribution/off_ball.py`): over the window frames and their pitch-control surfaces —
   - **space creation/occupation:** an attacker whose run created/occupied valuable space (control gain weighted by zone threat) → credited;
   - **space conceded / marking break:** a defender who conceded dangerous space or broke a marking assignment (nearest-defender / distance-to-man over time) → debited;
   - **decisive frame via velocity:** locate the frame where a defender stopped tracking his man (velocity/direction mismatch), the run broke the line, or the channel opened.
   Each becomes a contribution bound to its **tracking frame**. Quantify as the change in the beneficiary's scoring probability attributable to that positioning.

4. **Fusion + ranking** (`src/replay_room/attribution/fuse.py`): pool on-ball and off-ball candidates, filter by the evidence threshold, **rank by absolute marginal effect on P(outcome)**. Select `headline_cause` by the realized/prevented rule (top conceding-side negative for realized; the preventing action for prevented). Assemble the `CausalAccount`.

5. **Counterfactual** (`src/replay_room/attribution/counterfactual.py`) — *core differentiator, include if time; stub cleanly if not:* at the decision frame, value each **actually available** option from the real positions — pass-completion probability from positions × receiving-location value (xT/EPV) — and if the chosen action sits materially below the best available, emit `{chosen, chosen_value, best_alt, best_alt_value}`. Grounded in real positions, never invented.

6. **Optional Shapley** (behind a flag): SHAP over the pooled contributions for a principled shared-credit split. Don't let it block the gate.

7. **`attribute(valued_moment)` → `CausalAccount`**: the single entry point Builds 5/6/7 call. Persist accounts (local JSON now; Cosmos DB later).

8. **CLI + tests**: `python -m replay_room.attribution data/fixtures/<match>` prints, per engine_eligible moment, the ranked account — headline cause, contributions with refs and signed values, counterfactual if present. `pytest`:
   - **realized goal** — a build-up pass with high value appears as a creator; a defensive lapse is the headline cause; every contribution has a valid event-id or frame ref.
   - **turnover_to_shot** — the turnover is a conceding-side negative; the chain from regain to shot is attributed.
   - **big_chance_saved** — attacking creators credited **and** the save/block is the headline defensive positive; account is framed prevented (realized=False).
   - **penalty** — headline centers the foul (the key event), outcome value is the kick's xG.
   - **threshold** — an incidental low-impact touch is filtered out of the account.
   - **binding** — no contribution lacks a concrete ref; a frame ref lands inside the moment's window.

## Non-negotiables

- **No LLM, no narration, no 3D.** Build 4 computes the account; it does not speak it. This is the deterministic wall.
- **Attribute over `outcome_ref`'s value — one path, no per-class hard-coding.** The realized/prevented distinction is a flag on the outcome, not four code branches.
- **Every contribution is bound to a real record.** Nothing enters the account "on vibes"; the threshold enforces this.
- **Use Build 3's values as-is** (VAEP-or-documented-Δ-xT fallback, pitch-control surfaces). Don't recompute metrics here.
- **Deterministic and tested.** Same valued moment → same account.
- **Off-ball "should-have" claims carry their measured delta.** A marking-break contribution states its space-conceded number; the number is what defends the claim downstream.

## Definition of done (the Build 4 gate — the vertical-slice milestone)

- `attribute(...)` returns a populated `CausalAccount` for every engine_eligible fixture moment, across all four explained classes.
- On-ball and off-ball tracks both contribute; fusion ranks by marginal effect; `headline_cause` follows the realized/prevented rule.
- `big_chance_saved` is framed as prevented, with both the creator(s) and the preventing action present.
- Every contribution binds to an event id or an in-window frame; the threshold filters incidental touches.
- Counterfactual present or cleanly stubbed; tests pass; build committed.

## How to work

Write the semantics (Step 2) first — it's the real design. Then tested commits: **CausalAccount contract → on-ball track → off-ball track → fusion/ranking/headline → counterfactual (or stub) → `attribute` entry point + persistence → CLI/tests**. Keep each commit runnable. When the gate is met, print one full account for the richest fixture moment (ideally a `big_chance_saved` or a build-up goal) so the quality is visible, and hand off to **Build 5 (3D viewer)** and **Build 6 (grounded explanation renderer)** — both consume this `CausalAccount` and nothing else.
