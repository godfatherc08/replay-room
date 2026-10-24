# Replay Room

A football match turned into its talking-point moments, each rebuilt as an explorable 3D replay that
explains **why** it happened, grounded in the match's own events and tracking. Causality is computed
deterministically; a language model only narrates the computed account. Design and rules: `CLAUDE.md`;
full detail: `REPLAY_ROOM_TECHNICAL_SPEC.md`.

## See it locally

You need **Python 3.11 or 3.12** and **Node.js 18+** (developed on Node 22). The synthetic match and the
trained metric models are in the repo, so nothing else has to be downloaded or trained.

**1. Install the Python pipeline** (from the repo root):

```
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS / Linux: source .venv/bin/activate)
python -m pip install -e ".[dev]"
```

**2. Export the moments** the viewer plays (detect → attribute + match context → Analyst plan → Storyteller ⇄
Critic → Editor → bundle):

```
python -m replay_room.render data/fixtures/synthetic_match_01
```

This writes one bundle per moment to `data/accounts/` (it is git-ignored, so run this after every clone).
The Analyst and Storyteller use Microsoft Foundry when it is configured (see below). Without it, they fall
back to the rule plan and the deterministic composer, and the Critic checks the result either way, so this
step works offline.

**3. Start the viewer:**

```
cd viewer
npm install
npm run dev
```

**4. Open** <http://localhost:5173/>. It opens the first prevented moment on its title card. Press
**Play analysis** (or **Space**) to watch the guided story, or switch to **Explore** to scrub and click
freely. **Space** plays and pauses; **←/→** step between beats. The moment picker (top right) opens the
match's other moments.

Useful links:

| What | URL |
|---|---|
| The hero moment (with the counterfactual) | <http://localhost:5173/?moment=SYN-0007-big_chance_saved-3> |
| …playing straight away | <http://localhost:5173/?moment=SYN-0007-big_chance_saved-3&play=1> |
| …in Fan mode | <http://localhost:5173/?moment=SYN-0007-big_chance_saved-3&mode=fan> |
| …at a given story step (1-based) | <http://localhost:5173/?moment=SYN-0007-big_chance_saved-3&step=11> |
| A goal | <http://localhost:5173/?moment=SYN-0007-goal-1> |

Other parameters: `&view=explore`, `&jump=<contribution_id>` (Explore, at that fact), `&stadium=0` (the
bare pitch). The viewer's own README (`viewer/README.md`) describes everything on screen.

**See the agents work:** `python -m replay_room.agents` prints the Scout's menu, the trace of every agent
hop, and the fan and analyst editions of the hero moment. `--via-mcp` reaches the engine through its MCP
server; `--focus-team NBR`, `--focus-player EPA-11` and `--language fr` exercise the Editor.

### Optional: the model agents (Microsoft Foundry + Agent Framework)

```
python -m pip install -e ".[foundry]"
az login
set FOUNDRY_PROJECT_ENDPOINT=<your project endpoint>      # macOS / Linux: export ...
set FOUNDRY_MODEL_DEPLOYMENT=<your model deployment>
python -m replay_room.render data/fixtures/synthetic_match_01
```

Tellings are cached in `data/narrations/` and re-checked by the Critic before they are used.

### Troubleshooting

* **"No bundles found"** in the viewer: step 2 has not been run (or wrote elsewhere). The dev server
  serves `data/accounts/`; set `BUNDLES_DIR` to serve another folder.
* **Port 5173 in use**: `npm run dev -- --port 5180`, then open that port.
* **A blank pitch**: the viewer needs WebGL; check that hardware acceleration is on in the browser.
* **Re-exported but the viewer shows old data**: reload the page (bundles are static files).

## Agentic architecture

The engine computes the facts and the causal links. The agents select, order, emphasize, verify and adapt
them. No agent, the Analyst included, ever authors a fact or a causal link that the engine did not compute.
The reasoning is in [ADR 0001](docs/adr/0001-agency-around-a-deterministic-core.md).

```
  feed (Fabric Eventhouse via Azure MCP, or the fixture)
        │
     Scout ── detect_moments ──► described menu (explainable / described only: offside, VAR, red card …)
        │ user picks a moment
        ▼
  ┌──────────── Replay Room engine: MCP server (stdio / Streamable HTTP) ─────────────┐
  │ attribute      → CausalAccount: ranked, evidence-bound facts, the headline and   │
  │                  the supporting defensive flaw, computed off-ball links          │
  │ match_context  → per-match baselines for the defending team + this deviation     │
  │ narrate        → a Critic-checked telling                                        │
  └───────────────────────────────────────────────────────────────────────────────────┘
        │
     Analyst (Foundry, Agent Framework; may call the MCP tools itself)
        │  framing plan = ordered ids: attack leads, then the flaw (told through its link), then context
     Critic ── plan check: every id resolves, framing rules hold ── reject → re-plan ×3 → rule plan
        │
     Storyteller (Foundry) ⇄ Critic ── names/numbers/links per beat, fan register number-free
        │                      reject → retell ×3 → deterministic composer
     Editor ── analyst / fan register · club focus · player focus · Azure AI Translator (re-checked)
        │
     bundle → 3D viewer (Story Mode plays the plan)          accounts ↔ Cosmos DB via Azure MCP (or local)
```

| Agent | Grounded by | Model | Deterministic floor |
|---|---|---|---|
| Scout | `detect_moments` + the stream | none | — |
| Analyst | `attribute`, `match_context` | Foundry (Agent Framework, structured output; MCP tools) | `framing.rules_plan` |
| Storyteller | the checked plan, resolved to records | Foundry (Agent Framework, structured output) | `explain.compose` |
| Critic | the tool outputs | none (code) | — |
| Editor | the checked telling | Azure AI Translator (optional) | English, same text |

What runs where, honestly:

* **Always** (offline, in CI): the engine, the MCP server (a real client calls every tool over stdio),
  the Scout, the rule plan, the composer, the Critic and the Editor's registers and focus.
* **When configured**: the Foundry Analyst and Storyteller (`FOUNDRY_*`), Azure AI Translator
  (`AZURE_TRANSLATOR_KEY`), Content Safety (`CONTENT_SAFETY_*`), the Fabric Eventhouse stream
  (`EVENTHOUSE_*`) and Cosmos DB (`COSMOS_ACCOUNT`), the last two through the Azure MCP server
  (`npx @azure/mcp`). Each one that is missing falls back, and the trace records why.

## Other commands

```
python -m pytest                     # Python tests (CI: .github/workflows/ci.yml)
python -m replay_room.agents         # the agents end to end, with the trace
python -m replay_room.mcp_server     # the engine as an MCP server (stdio; --http for Streamable HTTP)
python -m replay_room.mcp_server.smoke   # an MCP client lists and calls every tool
cd viewer && npm test                # viewer tests
cd viewer && npm run build           # static site in viewer/dist/ (Azure Static Web Apps)
cd viewer && npm run shots -- out    # with the dev server up: headless screenshots of the hero moment
```

The full command list (replay clock, detect, metrics, attribution, explain, fixtures) is in `CLAUDE.md`.
