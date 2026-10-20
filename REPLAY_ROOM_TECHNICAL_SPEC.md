# Replay Room — Technical Specification (v0.2)

**Project:** The Synthetic Match Insights Engine for Premier League Studio (Microsoft × Premier League "Inside the Game" Hackathon)
**Author:** Chimaobi · **Date:** 2026-10-20 · **Status:** build-ordered draft
**v0.2 change:** the synthetic feed carries **player positions and position changes (velocity)**. Off-ball claims are now grounded, 3D positions are **observed not modeled**, and the counterfactual what-if is promoted from stretch to core. Stage 4 and §3/§5 updated accordingly.

---

## 0. The one architectural principle that wins or loses this

The Reactor reference session splits the system into **deterministic code** and **Foundry (LLM) logic**. Take that split seriously — it is the whole game:

> **Causality and numbers are computed deterministically. The language model only verbalizes a pre-computed account. It never decides *why* anything happened.**

Why this is the winning bet:

- The product's claim is "explain *why* a moment happened." If an LLM free-writes the "why," it hallucinates plausible-but-false tactical stories, and judges and football fans can smell generic punditry instantly. That is how most of the 391 other entries will lose.
- If instead the "why" is a ranked, evidence-linked account produced by **value-function credit assignment plus spatial (pitch-control) reasoning** on real positions, and the LLM is a *renderer* of that account, every sentence is traceable to an event, a frame, and a number. That is the moat.

Hard wall: **stages 1–4 and the analytic part of 7 are deterministic; only stage 6 touches a model, and it is constrained to narrate stage-4 output.**

### Build order and five-stage mapping

| # | Component | Spec stage | Deterministic / Model |
|---|---|---|---|
| 1 | Event ingest + replay clock | (a) ingest | Deterministic |
| 2 | Moment detector (goals first) | (b) interpret | Deterministic |
| 3 | Metric layer (xT / VAEP / xG + spatial) | (b) interpret | Deterministic (ML models, no generation) |
| 4 | Causal attribution + evidence trace | (c) explain — *the edge* | Deterministic |
| 5 | 3D moment viewer | (d) render | Deterministic |
| 6 | Explanation renderer | (c)+(d) | **Model (grounded)** |
| 7 | Personalization modes | (e) personalize | Deterministic view-transforms (+ model render) |

### Azure service map

| Stage | Microsoft / Azure service | Role |
|---|---|---|
| Ingest (1) | **Fabric Real-Time Intelligence — Eventstream** (or Azure Event Hubs) | Capture the synthetic event + tracking feed as a stream |
| Store/query (1–3) | **Fabric Eventhouse (KQL database)** | Time-series store; fast temporal + spatial queries |
| Detect (2) | **KQL querysets + Data Activator** (or Azure Functions) | Possession-chain + moment triggers |
| Models (3) | **Azure Machine Learning** | Train/register/deploy xT, VAEP, xG, pass, pitch-control models |
| Attribution (4) | Python service on **Azure Container Apps (ACA)** | Deterministic credit assignment + spatial attribution; no model |
| State (4) | **Azure Cosmos DB** | Store the structured causal account per moment |
| 3D render (5) | **Babylon.js** (open-source WebGL/WebGPU engine originated at Microsoft) on **Azure Static Web Apps** / ACA | Faithful explorable 3D scene from real positions |
| Explanation (6) | **Microsoft Foundry — Foundry Agent Service** (Responses API, `azure-ai-projects`) + a Foundry model; **Foundry IQ** grounding | Narrate the account under a JSON schema |
| Personalize (7) | Foundry prompt variants + frontend view state; (stretch) **Azure AI Translator** | Analyst vs casual, club/player focus, language |
| Auth | **Microsoft Entra ID** (+ Entra Agent ID) | Identity |
| Dev | **GitHub + GitHub Copilot** | Repo, CI, pair-programming |

> **Prefer ACA over AKS** everywhere. Solo ⇒ no Kubernetes overhead.

---

## 1. Event ingest + replay clock

**What it does.** Reads the synthetic feed — **on-ball events + per-frame player positions and velocities** — and plays it back against a scrubbable clock.

**Approach.**
- **Normalize on-ball events to SPADL** (Soccer Player Action Description Language, from the VAEP paper): `(game, team, player, start_x, start_y, end_x, end_y, type, result, bodypart, time)`. The `socceraction` library (ML-KULeuven) ships SPADL converters, xT and VAEP.
- **Keep the tracking frames alongside** — a time-indexed table of every player's `(x, y, vx, vy)`. SPADL drives the value models; the tracking table drives the spatial models (§3e) and the 3D render (§5).
- **Replay** = order by timestamp, emit on a pausable/seekable clock; replay the log through the stream to behave "live."

**Microsoft tools.** Fabric **Eventstream** ingests; **Eventhouse/KQL** stores both events and tracking frames (KQL is strong at the temporal/spatial joins you'll need). Azure Event Hubs + in-memory replay is the lighter alternative.

**Data contract.** Events as above; tracking as `(timestamp, player_id, team_id, x, y, vx, vy)`. Match metadata. **Confirmed:** positions + position-changes are present, so off-ball reasoning is grounded.

---

## 2. Moment detector (goals first)

**What it does.** Flags talking points and captures the **possession chain** (+ the tracking window around it) leading into each.

**Approach.**
- **Segment into possessions** (needed by xT/VAEP anyway).
- **MVP = goals only.** The goal is trivial to flag; the *moment* is the chain + the ~10–15s tracking window before it.
- **Detection** = temporal/threshold rules over computed state (shot after a possession-value spike, pressure/possession swing), as **KQL queries + Data Activator**, or Azure Functions.

**Why.** The chain + its tracking window is the unit stages 4–5 operate on.

---

## 3. Metric layer — the valuation primitives

Computes the **cited numbers** every explanation points at. On-ball value (3a–3d) plus — now — off-ball spatial value (3e).

### 3a. Expected Goals (xG)
Shot→goal probability from shot features (location, angle, body part). Logistic/GBM.

### 3b. Expected Threat (xT) — *Karun Singh, 2018* (after Sarah Rudd)
Grid over the pitch; each zone's value = probability possession there leads to a goal, learned as a Markov process iterated to convergence:
```
xT(z) = shoot_prob(z)·xG(z) + move_prob(z)·Σ_z' T(z→z')·xT(z')
move_value = xT(end_zone) − xT(start_zone)
```
`socceraction.xthreat`.

### 3c. VAEP — *Decroos, Bransen, Van Haaren, Davis, KDD 2019* (Best Paper)
Values **every** on-ball action by its change in scoring/conceding probability over the next *k* actions (two XGBoost models over SPADL states):
```
VAEP(action) = [P_score(S_after) − P_score(S_before)] − [P_concede(S_after) − P_concede(S_before)]
```
This signed delta is the raw material of stage 4's **on-ball track**.

### 3d. Pass-difficulty / completion
Pass-completion probability (distance, angle, pressure, zones) → the spec's "pass difficulty rating." GBM.

### 3e. Off-ball spatial models — *now in scope (positions + velocities present)*
Because every player's position and velocity is known each frame, the off-ball game is observable:
- **Pitch control** — who owns which area at each instant. Baseline: **Voronoi** regions. Better: **player-influence-area** models weighted by position, velocity, and distance to ball — **Fernández & Bornn, "Wide Open Spaces" (MIT Sloan 2018)** or **Spearman, "Beyond Expected Goals" (MIT Sloan 2018)**. Open implementations exist (Laurie Shaw / FriendsOfTracking).
- **Space value & creation/occupation** — weight controlled space by its threat (tie to xT); an off-ball run that drags a marker and opens valuable space is a creditable contribution (Fernández-Bornn space-creation measure).
- **Marking / assignment** — nearest-defender and assignment tracking: who is responsible for whom, and whether the assignment held (distance-to-man over time).
- **Velocity-derived signals** — runs (acceleration into space), tracking failures (a defender not matching his man's run/direction — "ball-watching"), and the spec's **speed/distance indicators** (section ii), essentially for free.

These feed stage 4's **off-ball track**.

**Microsoft tools.** Train/register/deploy the learned models in **Azure Machine Learning**; pitch-control is mostly closed-form geometry computed in the attribution service.

---

## 4. Causal attribution + evidence trace — **THE EDGE**

**What it does.** For a moment, produce a **ranked, evidence-linked causal account** fusing on-ball and off-ball contributions, each tied to a concrete record and a number.

### The method (and why it's defensible)

No football dataset carries a ground-truth "cause" label, so you don't *discover* causes — you **rank contributions by their measured effect on the outcome probability**, using the value and space models from §3. With positions **and** velocities available, run **two tracks and fuse them**.

**Track A — on-ball (value-delta credit assignment).**
1. Take the possession chain into the moment (§2).
2. For each on-ball action, read its **VAEP signed delta** (and/or Δ-xT) — in RL terms, the action's *advantage*: how much it moved the team's expected outcome.
3. Positive deltas = build-up contributors; the largest negative delta before a concession = the on-ball mistake.

**Track B — off-ball (spatial contribution & failure).** *(Unlocked by position + velocity metadata.)*
4. Over the moment window, compute **pitch control / space value** each frame (§3e).
5. **Attribute space outcomes to players:** an attacker who created/occupied valuable space is credited; a defender who conceded dangerous space or broke his marking assignment is debited — quantified as the change in the attacker's scoring probability attributable to that positioning (space value → threat).
6. **Locate the decisive frame** via velocities: the defender who stopped tracking his man (velocity/direction mismatch), the run that broke the line, the step-up that opened the channel.

**Fusion & ranking.** Pool all candidates — on-ball actions **and** off-ball positioning facts — and rank by **absolute marginal effect on the outcome probability**. Top positives = creators; the top negative for the conceding team = the **headline cause**, which may now be an *off-ball* fact.

**Counterfactual / what-if — now grounded.** Because positions are real, "what if another pass?" needs no invention: at the decision frame, compute the **value of each available option** from the actual positions — pass-completion probability from positions (**Spearman's physics-based pass model**) × the receiving location's value (xT / EPV, Fernández-Bornn-Cervone; SoccerMap, Fernández-Bornn). If the chosen action sits well below the best available, that's a grounded "a better option existed." **This is a core differentiator against PitchLens, not a stretch.**

**Structured causal account:**
```json
{
  "moment_id": "...",
  "type": "goal",
  "window": [63.0, 68.4],
  "contributions": [
    {"track": "on_ball",  "event_ref": "evt_412", "action": "through_ball", "player": "A9", "vaep": 0.11, "role": "assist"},
    {"track": "off_ball", "frame_ref": "frm_1890", "player": "A7", "signal": "run_in_behind",        "space_created": 0.14, "role": "space_creation"},
    {"track": "off_ball", "frame_ref": "frm_1894", "player": "D4", "signal": "stopped_tracking_runner", "space_conceded": 0.18, "role": "primary_cause"},
    {"track": "on_ball",  "event_ref": "evt_418", "action": "shot", "player": "A7", "xg": 0.41, "role": "finish"}
  ],
  "headline_cause": "frm_1894",
  "counterfactual": {"chosen": "shot", "chosen_value": 0.41, "best_alt": "square_pass_A9", "best_alt_value": 0.55},
  "evidence": {"events": ["evt_410","evt_412","evt_418"], "frames": ["frm_1890","frm_1894"]}
}
```

### How evidence is decided (the short rule)

A fact becomes **evidence iff its marginal effect on the outcome probability clears a threshold** (top-k, or a delta cutoff):
- **on-ball** facts are scored by **VAEP / Δ-xT** deltas;
- **off-ball** facts by **space-value / marking** deltas (pitch-control change attributable to that player's positioning);
- the **counterfactual** surfaces only when a better available option beats the chosen one by a margin.

Every surviving fact is **bound to a concrete record** — an **event id** for on-ball, a **timestamped position frame** for off-ball — so each sentence stage 6 writes points at something real in the data, and the 3D viewer (§5) can jump the camera to exactly that frame. Nothing enters the account on vibes; low-impact touches are filtered out by the threshold.

**Enhancement (optional):** Shapley values (SHAP) over the pooled contributions for a principled split when several share credit.

**Microsoft tools.** Pure Python on **Azure Container Apps**; **no LLM in this stage**. Persist the account in **Cosmos DB** / Eventhouse.

**Why.** This is the difference between winning and losing. Causality computed as value-delta + spatial credit assignment is correct, traceable, and un-fakeable — and with off-ball data it now reaches the claims fans actually argue (marking errors, vulnerable zones, "wrong option"), which a recap bot cannot touch.

---

## 5. 3D moment viewer (faithful)

**What it does.** Rebuilds the moment as an explorable 3D scene — pause, orbit, zoom — jumping to the exact frames the account cites.

**Approach.**
- **Babylon.js** (open-source WebGL/WebGPU engine originated at Microsoft): pitch, orbit camera, scrub timeline.
- **Positions are observed, not modeled.** Animate all players and the ball from the real per-frame positions and velocities, so the replay is faithful and the off-ball claims from §4 can be *shown* (highlight the defender who stopped tracking, the run into space, the zone that opened). Velocities give accurate motion and render the spec's speed/distance indicators directly.
- Keep it **markers, not photoreal** — a clean reconstruction, deliberately lean so it doesn't steal time from §4.

**Microsoft tools.** Babylon.js on **Azure Static Web Apps** / ACA; **Entra ID** auth.

**Why.** Core UX bet (PES-style rewind-and-rotate), now able to *visually prove* the causal account because the positions are real.

---

## 6. Explanation renderer (grounded generation)

**What it does.** Turns the §4 account into natural-language explanation + on-screen overlay + timed machine-readable output.

**Approach — the LLM is a renderer, not a reasoner.**
- Feed the model the **causal account JSON**; instruct it to narrate **only** from provided facts, carrying each `event_ref` / `frame_ref` into the sentence (the evidence trace).
- **Structured outputs** (JSON-schema-constrained): per sentence `{text, ref, metric}` → machine-readable overlay, pinned to the data.
- Anti-hallucination: low temperature; system prompt forbids any event/player/cause/position not in the account; schema constraint; **Foundry IQ** for retrieval grounding.

**Microsoft tools.** **Microsoft Foundry — Foundry Agent Service** (GA; OpenAI Responses API; `pip install azure-ai-projects`, `AIProjectClient`, `PromptAgentDefinition`) + a Foundry model with structured outputs; Entra Agent ID.

**Why.** Legibility lives here; correctness lives in §4.

---

## 7. Personalization modes (analyst vs casual)

**What it does.** Same moment, genuinely different experiences: analyst (dense metrics, full ranked chain, deltas, the counterfactual) vs casual (one plain paragraph); plus club/player focus and language.

**Approach — view-transforms over one account, not re-analysis.**
- The §4 account is the single source of truth. Personalization = different renders:
  - **Analyst** = deterministic assembly (table of contributions, VAEP/xT/space deltas, the better-option comparison) — barely needs the model.
  - **Casual** = §6 narration, short, jargon-free.
  - **Player-focus** = filter the account to that player's contributions.
  - **Club-focus** = frame from that team's perspective (sign of the deltas).
  - **Language** = translate the casual narration (Azure AI Translator or a multilingual Foundry model).

**Why.** Stage (e) is mandatory; view-transforms over one computed account make "two genuinely different experiences" cheap and correct.

---

## The data contract gate (do this the moment data downloads)

1. **Off-ball tracking — RESOLVED:** the feed carries player positions + position changes (velocity). Off-ball attribution, pitch control, and the grounded counterfactual are all in scope; 3D positions are observed.
2. **Coordinate system & units** (pitch dimensions, origin, frame rate) → needed for xT grid, pitch-control geometry, and the 3D render.
3. **Event taxonomy** → map to SPADL action types.
4. **Video feed?** The spec floats optional auto-eventing from video — **skip it** (a CV pipeline solo in days is a trap). Stay on the event + tracking stream.

---

## The winning/losing summary

**Compute the causality — on-ball value deltas and off-ball pitch-control/marking deltas on the real positions — and let the model only speak it.** With tracking available, the account reaches the claims fans actually debate (the marking error, the vulnerable zone, the wrong option), each pinned to an event id or a position frame the 3D viewer can show. That is what 391 recap bots cannot do: explain *why*, correctly, and prove it on the pitch.

---

## References

**Papers / methods**
- Decroos, Bransen, Van Haaren, Davis. *Actions Speak Louder than Goals: Valuing Player Actions in Soccer.* KDD 2019 (Best Paper). SPADL + VAEP. https://people.cs.kuleuven.be/~tom.decroos/reports/kdd19_tomd.pdf
- Karun Singh. *Introducing Expected Threat (xT).* 2018. https://karun.in/blog/expected-threat.html
- Spearman, W. *Beyond Expected Goals.* MIT Sloan 2018. Pitch control + off-ball scoring opportunity; open implementation by Laurie Shaw (FriendsOfTracking).
- Fernández, J. & Bornn, L. *Wide Open Spaces: A statistical technique for measuring space creation in professional soccer.* MIT Sloan 2018. Pitch control (player-influence areas), space occupation/creation.
- Fernández, Bornn, Cervone. *Expected Possession Value (EPV).* Space value over possessions — for the counterfactual option-value surface.
- Fernández & Bornn. *SoccerMap.* ECML-PKDD 2020. Full-pitch pass-probability/value surfaces — for ranked pass alternatives.
- `socceraction` (ML-KULeuven): SPADL, xT, VAEP. https://socceraction.readthedocs.io
- FriendsOfTracking (D. Sumpter) / Laurie Shaw: open-source tracking + pitch-control code.

**Microsoft tooling (current, 2026)**
- Microsoft Foundry (formerly Azure AI Foundry) — Foundry Agent Service GA, Foundry Models, Foundry IQ. https://learn.microsoft.com/en-us/azure/foundry/whats-new-foundry
- Microsoft Fabric Real-Time Intelligence — Eventstream, Eventhouse (KQL), Data Activator, Real-Time Hub.
- Babylon.js — https://babylonjs.com
- Azure Machine Learning, Azure Container Apps, Azure Static Web Apps, Azure Cosmos DB, Microsoft Entra ID, GitHub + GitHub Copilot.