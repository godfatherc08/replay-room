# TIMELINE.md — Replay Room build plan

**Start:** 2026-10-20 (evening) · **Submission:** 2026-10-27, 11:59 PM PT ≈ **2026-10-28, 07:59 Lagos** · **Solo build.**

## Guiding rules

- **Thin vertical slice first.** By end of Day 3 there is a working path from a fixture match → a goal → a real causal account printed as JSON. Everything after deepens and surfaces that slice.
- **Stage 4 (causal attribution) gets the most time** — it is the edge. Protect it.
- **Every day ends with something that runs** and is committed. No day ends on a broken build.
- **Develop against synthetic fixtures** so progress never blocks on Innovation Studio data access; swap the real feed in via the loader when it lands.
- Deploy on **ACA**, not AKS. Add Azure services only when a stage needs them.

## Day-by-day

### Day 0 — Mon→Tue 20 Oct (tonight)
**Scaffold + Build 1 kickoff.**
- Init repo, `pyproject`, layout from `CLAUDE.md`, commit `CLAUDE.md` / `TIMELINE.md`.
- **Build 1 (ingest + replay clock):** loader for events + tracking; normalize on-ball events to SPADL; tracking table `(t, player, team, x, y, vx, vy)`; a tiny **synthetic fixture generator** (one short match) to develop against.
- Verify the data contract if real data is available (coords, units, frame rate, taxonomy).
- **Gate:** `replay <fixture>` streams events + frames on a pausable/seekable clock. Tests pass.

### Day 1 — Wed 21 Oct
**Finish Build 1, start Build 2.**
- Harden the replay clock (seek, pause, speed); define the shared **type contracts** (SPADL action, tracking frame, and a first draft of the **causal-account JSON**).
- **Build 2 (moment detector, goals only):** possession-chain segmentation; detect goals and capture the chain + ~10–15 s tracking window.
- **Gate:** for a fixture match, the system emits goal moments, each with its chain and tracking window.

### Day 2 — Thu 22 Oct
**Build 3 — metric layer.**
- xG (shot model); **xT** and **VAEP** via `socceraction`; pass-difficulty/completion.
- **Pitch control:** Voronoi baseline first, then player-influence (Fernández-Bornn / Spearman); space value tied to xT.
- **Gate:** every action carries a VAEP/Δ-xT delta; every frame yields a pitch-control surface. Numbers sanity-checked.

### Day 3 — Fri 23 Oct  ·  ★ vertical-slice milestone
**Build 4 — causal attribution (THE EDGE).**
- On-ball track (value-delta credit assignment) + off-ball track (space/marking deltas) → **fuse and rank** by marginal effect on goal probability.
- Emit the **evidence-bound causal account** (headline cause, contributions, evidence refs). Grounded counterfactual if time permits.
- Persist accounts (Cosmos DB or local JSON for now).
- **Gate (vertical slice):** fixture goal → a correct, evidence-linked causal account as JSON, every fact bound to an event id or tracking frame.

### Day 4 — Sat 24 Oct
**Build 5 (3D viewer) + start Build 6.**
- **Babylon.js** viewer: pitch, player/ball markers animated from real positions, orbit camera, scrub timeline; **jump-to-evidence-frame** from the account.
- **Build 6 start:** Foundry Agent Service wired; schema-constrained narration of the account (narrate only from provided facts; carry refs).
- **Gate:** a goal moment plays back in 3D; a first grounded narration prints from the account.

### Day 5 — Sun 25 Oct
**Finish Build 6, Build 7.**
- Lock anti-hallucination (low temp, schema, "only from the account"); emit timed machine-readable overlay output.
- **Build 7 (personalization):** analyst (dense metrics + deltas + counterfactual) vs casual (plain narration); club/player focus = filter the account; (stretch) language.
- **Gate:** same moment renders as two genuinely different experiences from one account.

### Day 6 — Mon 26 Oct
**End-to-end integration + deploy.**
- Wire 1→7 into one run over a full fixture (and real data if available); deploy services to **ACA**, viewer to **Static Web Apps**; Entra ID.
- Harden the demo path on 2–3 strong goal moments.
- **Gate:** one command / one URL runs the full pipeline on a goal and shows the 3D + explanation + both viewer modes.

### Day 7 — Tue 27 Oct  ·  submission day
**Polish, record, submit.**
- README + architecture diagram; 3-minute demo video on the best goal moment; tighten copy.
- **Link the GitHub project to the challenge on Innovation Studio. Submit well before 11:59 PM PT (≈ 07:59 Lagos, 28 Oct).**
- **Gate:** submitted. Buffer the morning of 28 Oct for any last fix.

## Critical-path risks & buffers

- **Stage 4 overruns** → it has Day 3 alone; if slipping, ship the on-ball track first (already strong) and add the off-ball track next. Don't let 4 eat 5–7.
- **Azure provisioning lag** → the whole pipeline runs locally on fixtures; cloud is additive, not blocking. Deploy is Day 6, not the critical path.
- **Real data lands late / schema differs** → the loader + fixtures absorb this; only the contract-mapping changes, not the pipeline.
- **3D scope creep** → markers only; if the viewer slips, a 2D top-down fallback still demos the account.

## One-line status per day (fill in as you go)

- Day 0: …
- Day 1: …
- Day 2: …
- Day 3: …
- Day 4: …
- Day 5: …
- Day 6: …
- Day 7: …