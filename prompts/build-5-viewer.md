# Build 5 Kickoff Prompt — 3D Moment Viewer (faithful, lean)

> Paste into a Claude Code session in the `replay-room` repo, after Build 4 (attribution) is committed and green. Lives at `prompts/build-5-viewer.md`.
>
> **Context:** `attribute(...)` produces a valid `CausalAccount` for all explained moments; accounts save to `data/accounts/<game>/<moment>.json`. Build 5 makes a moment *visible and explorable*, and lets a viewer see the causal account **proven on the pitch**. It is deterministic rendering — no LLM, no narration text (that's Build 6).

---

You are the lead engineer on **Replay Room**. The engine computes *why*; Build 5 lets a human *see* it — pause, rotate, zoom a moment, and jump the camera to the exact frame each fact cites. This is the core UX bet (PES-style rewind-and-rotate) and the visual spine of the demo. Keep it **lean: markers, not photorealism.** Read before you build.

## Step 1 — Read, in this order

1. `CLAUDE.md` — the governing principle; Build 5 is **render (stage d)**, deterministic, lean 3D. No LLM, no narration.
2. `REPLAY_ROOM_TECHNICAL_SPEC.md` — §5 (3D viewer).
3. **The data you consume:**
   - The `CausalAccount` JSON (`data/accounts/...`): `contributions[]` each with a `ref` (event id or frame), `player`, `team`, `signal`, signed `value`, `role`; `headline_cause`; `evidence.frames` = **the camera jump points**; `counterfactual` if present (chosen vs best-alt, at a decision frame); `outcome` with `realized`.
   - The tracking frames for the moment window: `(t, player_id, team_id, x, y, vx, vy)` for every player + ball.
   - The handoff facts from Build 4: every off-ball fact and counterfactual frame lies **inside the moment window** and names its players; `evidence.frames` is the ordered list of jump points.

## Step 2 — Confirm scope (write it back, briefly)

In ~8 lines: what Build 5 renders (a faithful marker-based 3D replay of the window, animated from the real positions, with the account's facts shown as on-pitch overlays and camera jumps) and what it must **not** do — no narration/text generation (Build 6), no re-attribution, no new metrics, no photoreal assets. Note the one data need: a clean export the viewer loads (account + window tracking). Don't code until written.

## Step 3 — The mission: Build 5 only

Build the viewer and the thin data bridge it needs. Faithful because positions are observed, not modeled; lean because the account's correctness is the star, not the graphics.

Deliverables:

1. **Moment export** (`src/replay_room/render/export.py`): one JSON bundle per moment the viewer loads — the `CausalAccount` + the window tracking frames (downsampled if needed) + pitch metadata (dimensions, origin, orientation). Deterministic; written next to the account. This is the only Python Build 5 adds; everything else is the front-end.

2. **The viewer** (`viewer/`, Babylon.js, deployable to Azure Static Web Apps, runnable locally):
   - **Pitch + markers.** A flat pitch to scale; each player a labelled marker (team colour + jersey/id), the ball a distinct marker. Animate all from the real per-frame positions; use velocities for smooth motion. No stadium, no player models.
   - **Camera + transport.** Orbit/rotate/zoom camera; a scrub **timeline** with play/pause/seek/speed over the window.
   - **Jump-to-evidence.** A panel lists the account's contributions (headline first), each showing player, team, signal, signed value. Clicking one **moves the clock to its frame, orbits/frames the camera on it, and highlights the named player(s)** — the literal "prove it on the pitch." `evidence.frames` drives the jump points.
   - **Show the off-ball facts visually.** At a fact's frame, render what the number means: the run into space (a velocity arrow / trail), the space created or conceded (a shaded region near the outcome spot), the marking break (a line between defender and the man he stopped tracking). Keep it schematic but legible.
   - **Show the counterfactual.** When present, at the decision frame draw the **chosen** option and the **better** option as two arrows from the ball, labelled with their values (e.g. chosen 0.113 vs best-alt 0.206). This is the sharpest visual; make it clear.
   - **Prevented vs realized.** If `outcome.realized` is false, make the framing visible (e.g. the shot track ending at the save, headline = what stopped it). Don't imply a goal that didn't happen.

3. **Dev harness**: load a saved account + its export and play it with no backend — `npm run dev` (or equivalent) opens the viewer on a chosen moment. A tiny fixture-driven path so you can iterate without Azure.

4. **Tests / checks**: unit-test the exporter (bundle has the account, the window frames, pitch meta; every `evidence.frame` exists in the exported frames; every contribution's player exists in the tracking). For the front-end, a smoke check that the viewer loads a bundle, renders the markers, and that clicking a contribution seeks to its frame (a lightweight component/integration test is enough — don't over-invest in UI testing on the clock).

## Non-negotiables

- **Markers, not photoreal.** Discs/spheres with ids and team colours, a flat pitch, orbit camera, scrubber. No stadium, no models, no textures. Correctness of the shown facts beats polish.
- **Faithful to real positions.** Animate only from the observed tracking; never invent positions. If a frame is missing, interpolate visibly-honestly, don't fabricate.
- **The viewer renders the account; it does not reason.** No re-ranking, no new metrics, no narration text. It *shows* what Build 4 computed.
- **Every jump target is real.** Camera jumps only to frames in `evidence.frames`; highlighted players are the ones the contribution names.
- **Deterministic export.** Same account + window → same bundle.
- **Deployable to Static Web Apps, runnable locally.** Keep it a static front-end + JSON bundles; no heavy backend.

## Definition of done (the Build 5 gate)

- `export(...)` writes a self-contained bundle (account + window tracking + pitch meta) per moment.
- The viewer loads a bundle and plays the moment in 3D: pitch, player/ball markers from real positions, orbit camera, scrub timeline.
- Clicking a contribution (headline first) seeks to its frame, frames the camera, and highlights the named player(s).
- Off-ball facts render schematically (run / space / marking line); the counterfactual draws chosen-vs-better when present; prevented outcomes read as prevented.
- Runs locally via the dev harness; exporter tests pass; build committed.

## How to work

Plan and files first, then tested commits: **exporter → viewer scaffold (pitch + markers + animation) → camera/transport → contribution panel + jump-to-evidence → off-ball + counterfactual overlays → prevented/realized framing → dev harness + tests**. Keep each commit runnable. When the gate is met, record a short screen capture of the hero moment (ideally the `big_chance_saved` with the counterfactual) for the demo, and hand off to **Build 6 (grounded narration)** — which consumes the same `CausalAccount` and turns each fact into a cited sentence to show alongside this viewer.

> **Recommended interleave before Build 6:** apply the headline-proximity patch to Build 4 — select the headline by `|value| × recency` (normalized position in the window; last ≈ 1.0, first ≈ low), body still ranked by pure |value|. It stops weak early-cause headlines (goal kicks, won-back touches) from leading, which is exactly what both the viewer caption and Build 6's narration will surface first. Headline-only change; contributions and their values do not move.
