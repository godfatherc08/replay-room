# Build 5 Revision Prompt — Viewer Visual + UX Overhaul (player models, guided UX)

> Paste into a Claude Code session in the `replay-room` repo, **after Build 6 (narration) is committed**. Revises the Build 5 viewer to match the approved mockup: humanoid player models instead of flat markers, and a UX a first-time user understands immediately. Lives at `prompts/build-5-revision-viewer-ux.md`.
>
> **Scope guard:** this is viewer polish toward a specific design, not a rebuild. The account-binding and jump-to-evidence core from Build 5 must not regress. Timebox it — it makes the demo land, but the engine's correctness is still the star.

---

You are the lead engineer on **Replay Room**. The marker viewer works but looks thin and doesn't tell a first-time user what to do. There is an approved visual design to build toward. Keep everything **bound to the account** — the new look must not introduce any fact, label, or number the account doesn't already contain.

## Step 1 — Read, in this order

1. `CLAUDE.md` — Build 5 is **render**, deterministic, lean. The viewer renders the account; it does not reason.
2. The current `viewer/` and `src/replay_room/render/export.py` — you are upgrading these, not starting over. Jump-to-evidence, the export bundle, and account-binding stay.
3. Build 6's output — the narration + timed overlay. The revised viewer now surfaces the **casual narration as the "Summary"** and can show per-sentence cited text.

## Step 2 — The design to build toward (this is the spec)

A dark, broadcast-style single-screen app. Layout:

- **Top bar:** Replay Room logo (left); centered scoreline — home badge + name, score, match clock (e.g. `63:24`); right — an **Analyst / Fan toggle**, plus settings / fullscreen / profile icons.
- **Left icon rail:** Match · Moments · Tactics · Evidence.
- **Center — the 3D pitch** (dark atmospheric green, no stadium):
  - **Humanoid player models** tinted by team (home vs away), **goalkeeper in a distinct colour**, numbers floating above each; the ball a distinct marker.
  - Overlay vocabulary with an on-pitch **legend**: dashed arrow = pass / movement; solid arrow = shot / goal attempt; translucent band = threat zone; a ring under the selected player.
  - Small controls: 2D/3D toggle (top-left), compass (top-right), a vertical camera toolbar (screenshot / rotate / zoom).
- **Right panel** (tabs: Event · Tactics · Metrics · Players):
  - **Moment header:** status dot + class (e.g. `BIG CHANCE SAVED`) + a `PREVENTED`/`REALIZED` chip + `xG 0.174 · 63:24` + a one-line plain description.
  - **Evidence & Key Moments:** a numbered vertical list; each row = title + type subtitle + **signed value** (green positive xT / red negative xG) + timestamp + chevron; the **headline row highlighted** (accent left border). Clicking a row jumps the camera to its frame (the existing jump-to-evidence).
  - **Summary** box (the Build 6 casual narration) + a "View Full Evidence Chain" action.
- **Bottom:** transport (play/pause, prev/next, speed); a **timeline scrubber** 0–90' with coloured event markers and a current-time bubble; a Live toggle; match-time readout.

Everything textual and numeric in that layout comes from the **account + narration + export bundle** — bind it, never hard-code the mockup's sample values.

## Step 3 — The mission

Deliverables:

1. **Humanoid player models (lean):**
   - Load **one** low-poly humanoid glb and **thin-instance it 22×** (one shared mesh — do not load 22 models). Tint instances by team; distinct colour for the goalkeeper; a billboarded number label above each; a selection ring under the active player.
   - Animate by **translating instances along the real per-frame positions** (orient to velocity). Per-player rigged running is **out of scope**; at most one shared idle/run cycle if time remains. "Doesn't need to look good" — plain untextured, team-tinted is the target.
   - **Asset sourcing:** use a **CC0** low-poly humanoid from **Quaternius or Kenney** (free, no login, license-clean). Do not rabbit-hole on Sketchfab/Mixamo licensing. Commit the asset under `viewer/assets/` with its licence note.
   - Fallback: if the glb path fails, degrade to a capsule-with-number so the viewer never breaks.

2. **Guided UX — the user must know what to do:**
   - On opening a moment, lead with the **moment header + one-line description + Summary** so the user instantly knows what they're seeing.
   - Make the **Evidence list the primary call-to-action** — a first-time hint (e.g. "Click an evidence item to see it on the pitch"), the headline pre-selected, hover/active states, chevrons.
   - The **legend** explains the arrow/zone vocabulary on-pitch.
   - Wire the **Analyst / Fan toggle as a shell** (Analyst = current full detail; Fan = seam for Build 7 to fill — don't build Fan mode's content here, just the toggle and a placeholder that still shows the Summary).
   - Keep transport + timeline usable: event markers on the scrubber, click-to-seek.

3. **Account binding (the honesty rule, preserved):**
   - Header class/chip/xG/time ← `account.type`, `outcome.realized`, `outcome.value`, outcome time.
   - One-line description + Summary ← Build 6 narration (casual).
   - Evidence rows ← `account.contributions` (title from signal/role, subtitle from action type, signed value, timestamp from the ref's time, chevron → jump to frame); highlighted row ← `headline_cause`.
   - Arrows ← the shot (`outcome_ref`, solid) and the counterfactual chosen-vs-better passes (dashed), with their values; threat band ← the space/pitch-control at the outcome spot.
   - **Nothing on screen is invented.** If the account lacks a field, the UI omits it — no placeholder facts.

4. **Export/bundle updates** (`render/export.py`): extend the bundle with whatever the new UI needs that isn't already there (team names/badvalues, GK identity, per-contribution display time, the narration + summary) — all derived from the account/narration, deterministic.

5. **Tests / checks:** exporter unit tests still pass and cover the new fields (every evidence row's ref exists; GK flagged; narration present). Front-end smoke: the viewer loads a bundle, instances the humanoid 22×, renders the header/evidence/summary from the bundle (not hard-coded), and clicking an evidence row still seeks + highlights. A visual check on the hero moment.

## Non-negotiables

- **Account-bound, nothing invented.** The prettier UI shows only what the account + narration contain. No sample numbers baked in.
- **Jump-to-evidence must not regress.** Clicking a contribution still seeks the clock, frames the camera, highlights the named player(s).
- **One instanced mesh, not 22 models.** Lean stays lean; the viewer must stay smooth.
- **CC0 asset, committed with licence.** No login-gated or unclear-licence models.
- **Timebox.** This is demo polish; do not let it eat engine or integration time. If something slips, the markers-era functionality must still work.
- **Fan mode is a seam, not content** — Build 7 fills it.

## Definition of done (the revision gate)

- The viewer renders **humanoid players** (one instanced CC0 mesh, team-tinted, numbered, GK distinct) moving on the real positions; degrades gracefully if the asset fails.
- The screen matches the approved layout: top scoreline, left rail, 3D pitch with legend + camera controls, right panel (moment header, evidence list with highlighted headline, Summary), bottom transport + timeline.
- All text/numbers are **bound to the account + narration**; the Analyst/Fan toggle exists (Fan = placeholder seam).
- A first-time user is guided (header + summary + evidence hint); jump-to-evidence works unchanged.
- Exporter tests pass; build committed.

## How to work

Plan and files first, then tested commits: **export bundle fields → humanoid instancing + team tint + labels → camera/legend polish → right panel (header, evidence, summary bound to data) → Analyst/Fan toggle shell + first-run hint → transport/timeline markers → tests + visual check**. Keep each commit runnable; never leave the viewer broken. When the gate is met, capture the hero moment (`big_chance_saved` + counterfactual) for the demo, and confirm the seam for **Build 7 (personalization)** — Fan mode and language plug into the toggle you wired.
