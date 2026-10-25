# Replay Room — Technical Specification (v1.0)

**Project:** Replay Room, for the Microsoft × Premier League "Inside the Game" hackathon (solo entry)
**Author:** Chimaobi · **Date:** 2026-10-25 · **Status:** as built (submission)

Replay Room turns a football match into its talking-point moments. It rebuilds each one as an explorable
3D replay and explains **why** it happened. The explanation is grounded in the match's own events and
player tracking. This document describes the system as it exists in the repository. Where a Microsoft
service is a configured path with a local fallback rather than a running deployment, it says so.

Two pieces of engineering carry the product:

1. **A multi-agent studio around a deterministic core** (§2). Five agents (Scout, Analyst, Storyteller,
   Critic, Editor) decide *how* a moment is told. A Critic written as code makes sure no agent ever adds
   a fact.
2. **A metric and attribution layer built on published football research** (§3): xT, VAEP, xG, a pass
   model, and player-influence pitch control. These are fused into a two-track causal account that is
   validated on held-out games and bound to event ids and tracking frames.

---

## 1. The governing rule

> **Agents orchestrate; they never invent causality. The engine computes every fact and every causal link.**

A language model asked *why* a goal happened writes fluent, confident punditry that is often wrong.
Replay Room splits the work instead:

- The **engine** computes the facts. It detects the moments, values every action, computes pitch control
  from the real positions, and runs the two-track attribution. It also measures the off-ball causal links
  and the match-context baselines. All of this is deterministic code.
- The **agents** choose which computed facts to tell, in what order, with what emphasis, in which register
  and language. A model agent's output is a list of ids, or prose that is checked against the tool
  outputs. It is never a new fact.
- The **Critic is code.** It checks every model output against the engine's outputs. A rejected output is
  regenerated with the violations fed back, up to three times. After that, a deterministic floor is used.
  Raw model output never reaches the screen.

The decision record is [ADR 0001](docs/adr/0001-agency-around-a-deterministic-core.md).

---

## 2. Standout 1 — the multi-agent architecture

### 2.1 Pipeline

```
  match feed ── Fabric Eventhouse via Azure MCP (kusto)  ─or─  fixture events.jsonl
        │
     Scout ── detect_moments ──► described menu (explainable / described only)
        │ a moment is picked
        ▼
  ┌──────── Replay Room engine, exposed as an MCP server (stdio / Streamable HTTP) ────────┐
  │ detect_moments → the match's moments, explained and flagged                            │
  │ attribute      → CausalAccount: ranked, evidence-bound facts, headline, supporting     │
  │                  flaw, computed off-ball links, grounded counterfactual                │
  │ match_context  → per-match baselines for the defending team and how this moment       │
  │                  deviates                                                              │
  │ narrate        → a Critic-checked telling                                              │
  └────────────────────────────────────────────────────────────────────────────────────────┘
        │
     Analyst  (Foundry model on Agent Framework; calls attribute + match_context over MCP)
        │  FramingPlan = ordered ids only
     Critic ── plan check ── reject → re-plan (≤3) → rule plan
        │
     Storyteller  (Foundry model on Agent Framework, structured output)
        │  analyst + fan register per beat
     Critic ── story check ── reject → retell (≤3) → deterministic composer
        │  + Azure AI Content Safety screen (when configured)
     Editor ── analyst / fan · club focus · player focus · Azure AI Translator (re-checked)
        │
     bundle JSON ──► Babylon.js 3D viewer (Story Mode plays the plan)
```

Code: `src/replay_room/agents/` (`scout`, `analyst`, `critic`, `editor`, `orchestrator`, `engine`,
`sources`, `azure`), `src/replay_room/framing/` (plan rules and plan check), `src/replay_room/explain/`
(Storyteller, composer, story check), `src/replay_room/mcp_server/`.

### 2.2 The agents

| Agent | Does | Grounded by | Model | Deterministic floor |
|---|---|---|---|---|
| **Scout** | Reads the feed in order. As the stream clock passes each detected moment, it adds the moment to a menu with a one-line description. Flagged moments (offside, VAR, injury, substitution) and red cards in the feed are *described only*, with the reason they are not explained. | `detect_moments` + the stream | none | — (is deterministic) |
| **Analyst** | Builds the `FramingPlan`: which facts, in which order, with which emphasis (`lead` / `support` / `detail`). | `attribute`, `match_context` (fetched itself over MCP, or given inline) | Foundry, via Agent Framework, structured output `PlanProposal` | `framing.rules_plan` |
| **Storyteller** | Writes each beat of the checked plan in two registers: analyst (one computed number woven in as meaning) and fan (no numbers, no jargon). Also writes an optional "deep" passage from positional facts. | the *story brief*: the plan with every record resolved, plus the composer's draft as the reference | Foundry, via Agent Framework, structured output `StoryOutput` | `explain.compose` |
| **Critic** | Checks the plan and the story. Also checks edited and translated editions, and runs the Content Safety screen. | the tool outputs | none (code) | — |
| **Editor** | Personalizes a checked telling: register, club focus (the headline from that side, re-checked), player focus (marks that player's beats `highlighted`), language. | the checked telling | Azure AI Translator (optional) | English, unchanged |

The **orchestrator** (`agents/orchestrator.py`) is plain Python. It runs Scout → pick → `attribute` +
`match_context` → Analyst → Critic → Storyteller → Critic → Content Safety → Editor. It records every hop
(agent, action, what came back, any fallback reason) in a `trace`, which `python -m replay_room.agents`
prints.

### 2.3 How "never invent" is enforced

1. **Agents point; they do not author.** A framing plan is a list of ids: contribution, link,
   context-fact and counterfactual ids. `framing.check_plan` rejects any id that no tool returned. It also
   rejects any record told twice, and any plan that breaks the framing rules:
   - the account's headline is the single lead;
   - a realized story leads with the attack before any flaw, link or context beat;
   - a `flaw` beat must be a defending-team contribution with a positive effect;
   - context appears only where it deviates;
   - there is exactly one outcome beat;
   - every computed counterfactual is told.

   `tests/test_agents.py::test_a_planted_invented_fact_is_rejected_by_the_critic` proves the refusal.
2. **Links are computed or absent.** Causal-link language ("drags", "runs past", "opened", "because", …)
   is allowed only in a beat that carries a link that `attribution.links` measured on the tracking.
   Elsewhere, facts stand side by side.
3. **Each beat speaks for its own records** (`explain.validate`):
   - a passage may name only the players in its own beat's records;
   - every number must equal a computed value, at the precision written;
   - every capitalised word must be an allowed name, team or term;
   - a player is never placed on the wrong team;
   - a moment that did not score is never called "the goal";
   - the fan register contains no digits and no metric jargon;
   - the analyst register uses no vague magnitudes ("about", "roughly").
4. **Editions keep their facts.** After editing or translation, `Critic.review_edition` checks that every
   passage still carries exactly the numbers and player names of its source. A failed check keeps the
   English.
5. **Every model step has a floor.** Rule plan, composer, local sources. The whole pipeline runs with no
   Foundry, no Azure and no network. That is how CI runs it. The trace records which floor was used and why.
6. **Context supports, never causes.** Baselines come from the same match. Each one carries its sample
   size and a confidence grade (`low` / `medium` / `high`), and there is no baseline below 5 samples.

### 2.4 The grounding loop, concretely

```
for attempt in 1..3:
    output = model(brief, feedback)          # Analyst: PlanProposal  · Storyteller: StoryOutput
    errors = critic(output, account, context) # check_plan  · validate
    if not errors: return output
    feedback = errors                         # the violations go back into the next prompt
return deterministic_floor(account, context)  # rules_plan · compose  (also Critic-checked)
```

A network error, an auth failure or a malformed response also goes straight to the floor.
Tellings are cached in `data/narrations/<game>/<moment>.<mode>.json`. The cache key covers the account's
and the plan's content hashes, the prompt version and the deployment. A cached telling is re-validated
before use, and fallbacks are never cached as `foundry` output.

---

## 3. Standout 2 — the metric layer and causal attribution, grounded in football research

The facts the agents tell come from established football-analytics methods. These are implemented,
trained and validated here, not approximated by a model. Training is
`python -m replay_room.metrics.train` on a cached 200-match synthetic corpus, loaded through the same
feed adapter a real feed uses. The games are split deterministically 60/20/20 (train/tune/test), and the
test games are scored exactly once, after every modelling choice is made.

### 3.1 The valuation primitives (`metrics/`)

| Metric | Research | What it measures | How it is built here |
|---|---|---|---|
| **Expected Threat (xT)** | Karun Singh, *Introducing Expected Threat*, 2018 | The probability that possession in a zone leads to a goal, as the fixed point of a Markov model of shooting and moving | `socceraction.xthreat`, 16×12 grid. Delta-xT is extended beyond successful moves: a failed move costs −xT(start), a regain earns +xT(location), a shot is worth xG − xT(start). Thin zones borrow the nearest supported zone at the same distance from goal. |
| **VAEP** | Decroos, Bransen, Van Haaren, Davis, *Actions Speak Louder than Goals*, KDD 2019 (Best Paper) | Every on-ball action's change in P(score) minus its change in P(concede) over the next actions | socceraction's SPADL game-state features, labels and value formula. P_score and P_concede are `HistGradientBoostingClassifier`s (the paper's gradient-boosted-tree family), chosen by Brier score on the tune games. **Shipped only if both models reach AUC ≥ 0.70 and beat the base-rate Brier score on held-out games.** Otherwise delta-xT is the authoritative on-ball signal. |
| **Expected Goals (xG)** | standard geometric shot model | Shot → goal probability | Logistic regression on distance to goal, goal-mouth angle and a header flag, validated on held-out games. Penalties use a fixed 0.76. |
| **Pass completion** | — | P(pass completes); "pass difficulty" = 1 − completion | Logistic regression on what the passer could *see* at the pass instant: the intended receiver led by their velocity, lane gap, receiver gap, and pressure. It trains only on feed-named targets. Inferring targets from where the ball ended leaks the outcome (measured: held-out AUC 0.80 inferred vs 0.64 true). |
| **Pitch control** | Fernández & Bornn, *Wide Open Spaces*, MIT Sloan 2018; Spearman, *Beyond Expected Goals*, MIT Sloan 2018 | Which team controls each point of the pitch at each instant | Closed-form, with no training. A Voronoi baseline plus a player-influence model: each player is a bivariate normal centred 0.5 s ahead along their velocity, stretched with speed and widened by distance to the ball. Control = sigmoid(Σ own − Σ opponent) on a grid. |

**Orientation guard** (`metrics/orientation.py`). xT, xG and pass value accept only left-to-right
actions. VAEP refuses them, because socceraction orients each game state itself and would otherwise flip
away actions twice. Passing the wrong frame raises a `TypeError` instead of producing silently wrong
numbers.

### 3.2 From metrics to causes — two-track attribution (`attribution/`)

No dataset carries a ground-truth "cause" label, so causes are not *discovered*. Contributions are
**ranked by their measured effect on the outcome probability**. The account explains the outcome value
**V**, the ex-ante value of the terminal action (its xG). It never uses "goal = 1". Every `effect` is a
change in the **attacking team's** P(outcome), so a defender's lapse counts as a positive effect: a
failure to prevent.

- **Track A, on-ball** (`on_ball.py`): each chain action's authoritative value (VAEP, else delta-xT),
  signed towards the attack.
  - The terminal action is valued *ex ante* with delta-xT. Its VAEP would read the realised result
    (about +0.8 for a goal) and leak the outcome into its own explanation.
  - A penalty's foul is worth V − xT at its spot.
  - A prevented outcome adds `chance_denied` (effect −V), credited to the save, block or miss.
- **Track B, off-ball** (`off_ball.py`): the attack's control of the key spot in each frame,
  `space(f) = Σ control·g / Σ g` with a Gaussian `g` around the spot. A player's share is
  `V·(space(f) − space(f without p))`, recomputed with that player's influence removed (the per-player
  sum reproduces the surface exactly, which is checked). A player's fact is the largest rise in their
  share over the window:
  - attacker: `space_creation`, with signal `run_in_behind`, `run_into_space` or `found_space`;
  - defender: `space_conceded`, or `marking_break` if they also lost their nearest attacker, bound to the
    first frame where the two separated at speed.

  Goalkeepers get no off-ball facts.
- **Fusion** (`fuse.py`): a fact is evidence only if |effect| ≥ 0.01. The top 10 by |effect| are kept,
  plus the conceding side's best failure if the cut dropped it. All facts are ranked on one scale. The
  headline and supporting beat are chosen by |effect| × recency:
  - **prevented:** the headline is `chance_denied`, supported by the failure that let the chance happen;
  - **realized:** the headline is the best attacking act, supported by the defensive flaw. The flaw takes
    the headline (`primary_cause`) only when it outscores the attacking act 2×.
- **Off-ball causal links** (`links.py`), measured on the tracking and never inferred. For each kept
  defensive off-ball fact, four patterns are tested in order:
  - `decoy_run`: a runner took the defender away from their man;
  - `dragged_out`: the defender followed a runner and vacated the zone;
  - `run_past`: an attacker ran past the defender into the space they left;
  - `lost_man`: the defender's man drifted free towards the spot.

  Each link names the marked man, the runner, the zone and the action that used the space. If no pattern
  holds, there is no link, and nobody may assert one.
- **Grounded counterfactual** (`counterfactual.py`): at the assist and finish frames, every real option is
  valued from the actual positions. A pass is worth its completion probability × xT at the receiving point
  (the receiver led by their velocity); a shot is worth xG there. A "better option existed" is emitted only
  when the best alternative beats the choice by ≥ 0.05, listing up to 3 alternatives.
- **Match context** (`context/`): defending-team baselines from the same match.
  - `counter_press`: how often they win the ball back after losing it;
  - `line_height`: metres from goal line to the deepest outfield defender;
  - `marking_distance`: how close the nearest defender was to each attacker.

  Each has a sample size, confidence, and an IQR-based deviation flag. Positional facts (positions against
  phase averages, distances, marking held or broken, control swing at the spot) feed the "deep" telling.

Shapley shares are not computed (`shapley_share` stays null).

### 3.3 The causal account — the single contract

`contracts/causal_account.py` (schema v0.6; JSON Schema in `data/schema/causal_account.schema.json`,
regenerated by `python -m replay_room.contracts`). Fields: `moment`, `outcome` (V, realized/prevented,
teams, zone), `teams`, `participants`, `headline_contribution_id`, `supporting_contribution_id`,
`contributions` (rank, track, kind, role, `action` or `signal`, player, effect, metrics, `evidence`),
`counterfactuals`, `links`, `evidence` (index of every event id and frame cited), `provenance` (models,
threshold, margin).

Invariants are enforced on construction:

- only engine-eligible moments get an account;
- every on-ball fact cites an event and every off-ball fact a frame inside the window;
- ranks run 1..n by non-increasing |effect|;
- only the headline may be `primary_cause`;
- every counterfactual beats the choice by the margin;
- every referenced player is a participant;
- every link points at a defending off-ball contribution.

The account is self-contained: the agents and the viewer may say only what is in it.

---

## 4. Microsoft integration

Each Azure dependency sits behind an interface with a local implementation. `available` / `reason`
decide which one runs, and the trace records the choice.

| Microsoft technology | What it does in the pipeline | Where | Status in the repo |
|---|---|---|---|
| **Microsoft Foundry** (project, Responses API) + **Microsoft Agent Framework** | Runs the two model agents. Each is an Agent Framework `Agent` on a `FoundryChatClient`, constrained to a pydantic schema (`response_format`) at temperature 0.4 by default. The Analyst is given the engine's MCP server as a tool (`MCPStdioTool`, allowed tools `attribute` and `match_context`) and fetches the account and context itself. | `explain/foundry.py`, `agents/analyst.py` | **Live when configured** (`FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT`, `pip install -e ".[foundry]"`). The agents are client-side Agent Framework agents calling the Foundry project. They are not registered as hosted agents in Foundry Agent Service, and orchestration is plain Python, not Agent Framework workflows. Opt-in live test: `REPLAY_ROOM_FOUNDRY_IT=1`. |
| **Microsoft Entra ID** | Authenticates the Foundry calls with `DefaultAzureCredential`: `az login` locally, a managed identity on Azure. | `explain/foundry.py` | Live with Foundry. |
| **MCP: the engine as an MCP server** | Exposes `detect_moments`, `attribute`, `match_context` and `narrate` over stdio or Streamable HTTP, with no logic of its own. The orchestrator can reach the engine through it (`McpEngine`, `--via-mcp`), the Analyst calls it as its tool, and any MCP client can use it. | `mcp_server/` | **Always on.** CI runs a real MCP client that lists and calls every tool over stdio (`mcp_server.smoke`). |
| **Azure MCP server** (`npx @azure/mcp`) | Data access for the agents. The `kusto` namespace (`kusto_query`) streams the match feed from a **Fabric Eventhouse** for the Scout. The `cosmos` namespace (`cosmos_database_container_item_query`) reads a stored causal account from **Cosmos DB**. | `agents/azure.py`, `agents/sources.py` | **Read paths, live when configured** (`EVENTHOUSE_CLUSTER_URI`, `EVENTHOUSE_DATABASE` [`EVENTHOUSE_TABLE`=`MatchEvents`]; `COSMOS_ACCOUNT` [`COSMOS_DATABASE`=`replayroom`, `COSMOS_CONTAINER`=`accounts`]; Node.js for `npx`). Otherwise it falls back to the fixture feed and `data/accounts/`. The repo does not load the Eventhouse table or write accounts to Cosmos; those are provisioned outside it. |
| **Azure AI Translator** | The Editor's language step. Every translated passage is re-checked by the Critic. | `agents/azure.py`, `agents/editor.py` | Live when configured (`AZURE_TRANSLATOR_KEY`, `AZURE_TRANSLATOR_REGION`). Otherwise English. |
| **Azure AI Content Safety** | The Critic screens the final telling (text:analyze; severity ≥ 2 flags). | `agents/azure.py`, `agents/critic.py` | Live when configured (`CONTENT_SAFETY_ENDPOINT`, `CONTENT_SAFETY_KEY`). Otherwise the screen is skipped, with the reason in the trace. |
| **Babylon.js** (open-source engine that originated at Microsoft) | The 3D moment viewer. | `viewer/` | Always on. |
| **Azure Static Web Apps** | Hosts the live viewer (Free tier, `rg-replayroom`). `deploy-swa.yml` builds `viewer/dist/` with the committed demo bundles (`viewer/demo-data/`: accounts, plans, Critic-checked tellings) and uploads it. The site is static, with no backend and no secrets. | `viewer/`, `.github/workflows/deploy-swa.yml` | **Live:** https://victorious-flower-0b0191c0f.1.azurestaticapps.net |
| **Azure Container Apps** | Hosting target for the engine's MCP server (`--http`) and the agents (managed identity for Entra). | `mcp_server/__main__.py` | **Target only.** HTTP mode exists. No container image or ACA config is in the repo. |
| **GitHub Actions** | CI on every push and PR. The engine job installs, runs the pytest suite (every agent on its floor), the MCP smoke test, the agents end to end, and the bundle export. The viewer job typechecks, tests, and builds the static site. | `.github/workflows/ci.yml` | **Live.** |

**Not used:** Azure Machine Learning (the metric models are trained locally with scikit-learn and
socceraction, and committed in `data/models/`), Fabric Eventstream and Data Activator (detection is
in-process Python), and Foundry IQ.

---

## 5. Ingest and moment detection

### 5.1 Ingest and replay clock (`ingest/`, `replay/`)

- **Feed adapter** (`ingest/adapter.py`): this is the only code that knows the raw format. It turns a
  match directory (`meta.json`, `events.jsonl`, `tracking.csv.gz`) into canonical contracts:
  - `MatchMeta`;
  - a **SPADL** action table (`game, team, player, start_x, start_y, end_x, end_y, type, result,
    bodypart, time`);
  - context events;
  - a tracking table (`timestamp, player_id, team_id, x, y, vx, vy` for every player and the ball).

  The canonical frame is metres, origin at the bottom-left corner, home attacking +x. The raw feed is
  centre-origin at 10 Hz, so the adapter does real normalisation.
- **Synthetic generator** (`ingest/generator.py`): a deterministic agent simulation. Two formations slide
  with the ball, the nearest defender presses, others mark, attackers run, and the carrier passes, shoots
  or loses duels. Events and 10 Hz tracking come from one state. Generator v2 enforces offside at the pass
  and labels deliberately mistimed runs as offside. The demo match `synthetic_match_02` (game `SYN-0055`)
  has 8 explained moments.
- **Replay clock** (`replay/clock.py`): periods on one continuous timeline. Pause, seek and speed work at
  any time, with injectable time for tests. It sees only an `IngestSource`, so a live Eventstream source
  could replace `FileReplaySource` without changes downstream.

### 5.2 Moment detection (`detect/`)

- **Possessions:** control rules, boundaries at period start, kickoff, set piece and regain. Fleeting
  contested touches are merged into the surrounding possession.
- **Explained classes:**
  - `goal`;
  - `turnover_to_shot`: a shot shortly after a regain, with a minimum xG;
  - `big_chance_saved`: a non-penalty shot with xG ≥ 0.15 that did not score;
  - `penalty`: explained through the foul that won it.

  Each explained moment has one shape: the possession chain, the tracking window (about 10 s of run-up),
  the key event and the terminal `outcome_ref`. One moment per terminal action, by a fixed claim order.
- **Flagged classes:** `offside`, `var_decision`, `injury`, `substitution`. These are surfaced but never
  explained (`engine_eligible = false`), because their "why" is officiating, not scoring probability.
- **Streaming:** `StreamingGoalDetector` runs the same pure function once a goal's window has arrived, so
  streaming and batch detection produce identical moments.

---

## 6. Render: bundle and 3D viewer

**Bundle** (`render/export.py`, deterministic and byte-identical for the same input). One JSON file per
moment. It contains:

- the `CausalAccount`;
- every tracking frame of the window, with observed `x, y, vx, vy`, never filled in;
- the cited SPADL events;
- rosters and kits;
- the `story`: the Analyst's plan as told, with each step's frame, its analyst caption and its fan text;
- `proofs`: per fact and per beat, the players, frames, feed event ids and measured number;
- `deep` positional evidence;
- the plan, the match context and the Editor's editions.

**Viewer** (`viewer/`, TypeScript + Babylon.js, static):

- **Story** mode plays the plan beat by beat: camera, focus rings, one overlay and one caption per step.
- **Explore** mode allows free scrubbing and orbiting.
- An **Analyst / Fan** toggle switches between the two registers.
- **Evidence on demand** at three layers: the claim; its proof (frame, players, number, feed event ids);
  and **Go deeper** (control surface, average-position ghosts, the marking in green or red).
- A match timeline and a causal-chain ribbon.

Players are stylised markers moved along the observed tracking. The visuals are markers, not photoreal.

---

## 7. Personalization

The account is one source of truth, and personalization is a set of views over it. None of them
re-analyses the moment.

| View | How |
|---|---|
| Analyst register | Per beat, exact numbers with their rank and share ("VAEP +0.077: the largest of the move's 5 facts, 70% of the 0.110 xG chance"). |
| Fan register | The same beats without numbers or jargon. The outcome is shown as a band ("A good chance"). |
| Club focus | The headline is told from the chosen side (`perspective_headline`) and re-checked. The beats are unchanged. |
| Player focus | The beats involving that player are marked `highlighted`. Nothing is added about them. |
| Language | Azure AI Translator, then the Critic checks that numbers and names survived. Otherwise English. |

---

## 8. Verification

- **Python:** 200+ pytest tests over contracts, detection, metrics, attribution, links, context, framing,
  the Critic, the agents (including a planted invented fact being refused), the MCP server and the bundle.
- **MCP smoke:** a real MCP client launches the server over stdio and calls every tool.
- **Agents end to end** in template mode on the hero moment (`SYN-0055-big_chance_saved-2`).
- **Viewer:** vitest (the Babylon NullEngine scene test runs headless), typecheck, and `npm run shots` for
  headless-Edge screenshots of the hero moment's Story states.

All of this runs in CI without any Azure credentials, because every agent runs on its floor.

---

## 9. Data contract and limits

- The feed is **synthetic** throughout. The models learn the simulator's football, so retrain on real
  matches when real data arrives. Adding a real feed means adding a new adapter in `ingest/adapter.py`,
  and nothing downstream changes.
- Positions and velocities are observed in the feed. The 3D replay draws them and never models them.
- The red-card *class* is not detected. The Scout only describes red cards it sees in the feed.
- There is no video or computer-vision eventing, by design.

---

## References

**Football analytics**
- Decroos, Bransen, Van Haaren, Davis. *Actions Speak Louder than Goals: Valuing Player Actions in Soccer.* KDD 2019 (Best Paper). SPADL + VAEP. https://people.cs.kuleuven.be/~tom.decroos/reports/kdd19_tomd.pdf
- Karun Singh. *Introducing Expected Threat (xT).* 2018. https://karun.in/blog/expected-threat.html
- Fernández, J. & Bornn, L. *Wide Open Spaces: A statistical technique for measuring space creation in professional soccer.* MIT Sloan Sports Analytics Conference 2018. Player-influence pitch control.
- Spearman, W. *Beyond Expected Goals.* MIT Sloan Sports Analytics Conference 2018. Pitch control; open implementation by Laurie Shaw (FriendsOfTracking).
- `socceraction` (ML-KULeuven): SPADL, xT, VAEP. https://socceraction.readthedocs.io

**Microsoft tooling**
- Microsoft Foundry: https://learn.microsoft.com/azure/ai-foundry/
- Microsoft Agent Framework (`agent-framework-core`, `agent-framework-foundry`)
- Azure MCP Server (`@azure/mcp`); Model Context Protocol (`mcp` Python SDK)
- Azure AI Translator, Azure AI Content Safety, Microsoft Fabric (Eventhouse), Azure Cosmos DB, Microsoft Entra ID
- Babylon.js: https://babylonjs.com · Azure Static Web Apps · Azure Container Apps · GitHub Actions

**In this repo:** `docs/adr/0001-agency-around-a-deterministic-core.md` (the agent/engine split),
`docs/evidence-treatise.md` (the three evidence layers), `viewer/README.md` (everything on screen).
