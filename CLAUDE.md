# CLAUDE.md — Replay Room

> Operating manual for this repo. Read this in full at the start of every session before writing code.

## What this is

**Replay Room** is a 3D, moment-first match-intelligence product for the Microsoft × Premier League "Inside the Game" hackathon (solo entry; submission **27 Oct 2026, 11:59 PM PT**). It turns a football match into its handful of **talking-point moments** (goals first), rebuilds each as an explorable 3D replay, and explains **why** it happened — grounded in the match's own events and player tracking.

Challenge: build one pipeline with five stages — **ingest → interpret → explain → render → personalize** — on *synthetic, football-realistic* data. A submission that only generates metrics has no audience; one that only personalizes has nothing to personalize. We do the whole pipeline, with **explanation depth** and **analyst-vs-casual personalization** as the two differentiators.

## The one principle that governs every decision

> **Causality is computed deterministically. The language model only verbalizes a pre-computed account. It never decides *why* anything happened.**

This is a hard architectural wall:

- **Stages 1–4 and the analytic half of stage 7 are deterministic.** No LLM touches causality, attribution, or numbers.
- **Only stage 6 calls a model**, and it is constrained to narrate stage-4 output under a strict schema, with every sentence citing an event id or a tracking frame.

Why: an LLM asked to explain football invents fluent, confident, wrong punditry — which judges and fans detect instantly. Our "why" is value-function credit assignment + pitch-control reasoning on real positions, so every claim is traceable and un-fakeable. **If you ever find yourself asking the model to reason about causes, stop — that logic belongs in deterministic code.**

## MVP scope — build order (do these in order)

| # | Component | Stage | Nature |
|---|---|---|---|
| **1** | **Event ingest + replay clock** | ingest | Deterministic |
| 2 | Moment detector (**goals only** for MVP) | interpret | Deterministic |
| 3 | Metric layer (xT, VAEP, xG, pitch control) | interpret | Deterministic ML |
| 4 | **Causal attribution + evidence trace** *(the edge)* | explain | Deterministic |
| 5 | 3D moment viewer (Babylon.js, lean) | render | Deterministic |
| 6 | Explanation renderer (Foundry, grounded) | explain/render | **Model** |
| 7 | Personalization (analyst vs casual, club/player, language) | personalize | Deterministic views + model render |

**Scope discipline:** one moment class (goals) end-to-end beats all classes half-done. 3D is **markers, not photoreal**. Depth over breadth. **Stretch only if the MVP is solid:** multilingual, grounded what-if (ranked real alternatives), synthetic-data augmenter.

## Architecture: the two-track attribution engine

For each moment, stage 4 produces a ranked, evidence-bound **causal account** by fusing two tracks:

- **On-ball track** — each action's **VAEP** signed delta (and Δ-xT): how much it moved scoring-minus-conceding probability.
- **Off-ball track** — **pitch-control / space-value** and **marking** deltas from the per-frame positions + velocities: who created/occupied valuable space, who conceded it or broke a marking assignment.

A fact enters the account only if its **marginal effect on goal probability** clears a threshold. Each surviving fact is bound to a concrete record (**event id** for on-ball, **tracking frame** for off-ball) so stage 6 can cite it and stage 5 can jump the camera to it. Optional: Shapley (SHAP) for shared-credit splits. The counterfactual ("a better option existed") compares the chosen action to the value of the *actually available* options from the real positions.

## Tech stack

- **Language:** Python (pipeline, attribution, models). TypeScript/JS for the 3D viewer.
- **Analytics libs:** [`socceraction`](https://socceraction.readthedocs.io) (SPADL, xT, VAEP), xgboost/scikit-learn, numpy/pandas; pitch control is closed-form geometry (Voronoi baseline → player-influence model).
- **3D:** Babylon.js (WebGL/WebGPU) on Azure Static Web Apps.
- **Azure:** Fabric Real-Time Intelligence (Eventstream / Eventhouse-KQL / Data Activator) for ingest+detect; Azure ML for the models; **Azure Container Apps (ACA)** to host services; Cosmos DB for the causal account; Microsoft Foundry (Foundry Agent Service, structured outputs) for stage 6; Entra ID for auth.
- **Deploy on ACA, never AKS.** Solo = no Kubernetes overhead.
- **Dev:** GitHub + GitHub Copilot.

## Data contract

The synthetic feed has two parts:

- **On-ball events** → normalize to **SPADL**: `(game, team, player, start_x, start_y, end_x, end_y, type, result, bodypart, time)`.
- **Tracking frames** → `(timestamp, player_id, team_id, x, y, vx, vy)` for every player + ball.

**Confirmed:** positions **and** velocities are present, so off-ball attribution, pitch control, and the grounded counterfactual are all in scope; 3D positions are **observed, not modeled**.

**Verify the moment real data arrives:** coordinate system, units, pitch dimensions, origin, frame rate, and the event taxonomy (→ map to SPADL types). **Do not** build auto-eventing from a video feed — a CV pipeline solo in days is a trap. Stay on the event + tracking stream.

## Proposed repo layout

replay-room/
CLAUDE.md # this file
TIMELINE.md # day-by-day plan
prompts/ # kickoff prompts per build stage
data/
fixtures/ # synthetic sample match(es) for dev before platform data
schema/ # the verified data contract (fill in from real feed)
src/replay_room/
ingest/ # Build 1: load feed, normalize to SPADL, tracking table
replay/ # Build 1: the replay clock (pause/seek, emit “as they happen”)
detect/ # Build 2: possession chains + moment (goal) detection
metrics/ # Build 3: xT, VAEP, xG, pass, pitch control
attribution/ # Build 4: two-track fusion → causal account (THE EDGE)
render/ # Build 5: 3D viewer assets / data feed
explain/ # Build 6: Foundry renderer (grounded narration)
personalize/ # Build 7: view transforms over the account
contracts/ # shared types: SPADL action, tracking frame, causal account
tests/
viewer/ # Babylon.js front-end (Static Web App)
infra/ # ACA / Azure deploy (added when a stage needs the cloud)
pyproject.toml


## Working rules for the agent

1. **Respect the deterministic/LLM wall** (see the governing principle). Causality is never an LLM call.
2. **Build strictly in order 1→7.** Do not scaffold or stub later stages beyond their shared *type contracts*.
3. **The causal-account JSON is the single contract** between the deterministic core and everything downstream (stages 5, 6, 7 all consume it). Define it early and keep it stable.
4. **Develop against fixtures.** Build a tiny synthetic event+tracking generator so the pipeline runs before/without Innovation Studio data; make the loader swap real data in cleanly.
5. **Every stage ships something runnable** with tests before the next begins.
6. **Lean 3D.** Markers and camera, not photorealism. Correctness of the account beats visual polish.
7. **Keep it solo-sized.** Prefer local in-memory replay + ACA over heavyweight cloud wiring; add Azure services only when a stage actually needs them.

## Key references

- VAEP — Decroos et al., *Actions Speak Louder than Goals*, KDD 2019 (SPADL + VAEP).
- xT — Karun Singh, *Introducing Expected Threat*, 2018.
- Pitch control — Fernández & Bornn, *Wide Open Spaces* (2018); Spearman, *Beyond Expected Goals* (2018). Open implementations: FriendsOfTracking / Laurie Shaw.
- Full detail: `REPLAY_ROOM_TECHNICAL_SPEC.md`.

## Commands

```
install:      .venv/Scripts/python -m pip install -e ".[dev]"     (Python 3.11-3.12; socceraction 1.5.3 needs multimethod<2)
run replay:   python -m replay_room.replay data/fixtures/synthetic_match_01 --speed 4
              (--start/--end take timeline seconds or pPERIOD:SECONDS, e.g. p2:30; --instant ignores wall time;
               keys: space pause, +/- speed, f/b seek 10 s, q quit)
detect:       python -m replay_room.detect data/fixtures/synthetic_match_01 [--classes goal,penalty|all|flagged] [--json] [--stream]
              (default: the explained classes goal, turnover_to_shot, big_chance_saved, penalty; --stream is goals only)
train:        python -m replay_room.metrics.train      (builds/caches the 200-match corpus in data/corpus/, writes data/models/)
metrics:      python -m replay_room.metrics data/fixtures/synthetic_match_01 [--frame-every 5]
attribute:    python -m replay_room.attribution data/fixtures/synthetic_match_01 [--classes ...] [--json] [--save [DIR]]
              (one CausalAccount per engine-eligible moment; --save writes data/accounts/<game>/<moment>.json)
render:       python -m replay_room.render data/fixtures/synthetic_match_01   (accounts + viewer bundles in data/accounts/)
viewer:       cd viewer && npm install && npm run dev   (http://localhost:5173/?moment=<id>&jump=<contribution>; npm test)
gen fixture:  python -m replay_room.ingest.generator --seed 7 --out data/fixtures/synthetic_match_01
schema:       python -m replay_room.contracts      (regenerates data/schema/causal_account.schema.json)
test:         python -m pytest
```
