# Replay Room

**Replay Room replays a football match's key moments in 3D and explains why each one happened, with every
claim traced to the match's own data.**

Pick a goal, a big chance or a turnover, and Replay Room rebuilds it as an explorable 3D scene from the
players' tracked positions. Then it tells you why the moment happened: who built the chance, which
defender's run or lapse opened the space, and whether a better pass was on. Every sentence points at a
specific event or tracking frame you can jump to on the pitch. Nothing is made up. A deterministic causal
engine computes the facts. AI agents decide how to tell them to an analyst or a fan, and a code-based
Critic rejects anything the engine did not compute.

▶ **[Demo video](https://youtu.be/3CeD7jcq4k0)** · Built for the Microsoft × Premier League "Inside the Game" hackathon.

## What it does

- **Finds the talking points.** It detects goals, big chances saved, turnovers to shots and penalties
  from the event stream. Offsides, VAR calls, injuries and substitutions are listed with the reason they
  are *not* explained.
- **Replays them in 3D.** Players and the ball are drawn along their real positions and velocities in
  Babylon.js. You can pause, orbit, scrub, or let **Story mode** walk you through the moment beat by beat.
- **Shows the evidence.** Click any claim to see its proof: the frame, the players involved, the number
  that was measured, and the feed's own event ids. **Go deeper** draws the positional evidence on the
  pitch: who controlled the space, where players stood against their usual position, and which marking
  held or broke.
- **Tells it like a studio.** Five agents (Scout, Analyst, Storyteller, Critic, Editor) turn the computed
  account into a connected story, with a trace of every step.
- **Personalizes the telling.** The **Analyst** register gives exact figures. The **Fan** register gives
  the same story with no numbers or jargon. You can also set a club focus, a player focus, and a language
  (Azure AI Translator). Every edition is re-checked so the facts never change.

## Under the hood: two technical standouts

### 1. A multi-agent studio that cannot hallucinate

> **Agents orchestrate; they never invent causality. The engine computes every fact and every causal link.**

```
  feed (Fabric Eventhouse via Azure MCP, or the local fixture)
     │
  Scout ──────── detect_moments ──► menu of moments (explainable / described only)
     ▼
  Replay Room engine — an MCP server: detect_moments · attribute · match_context · narrate
     │
  Analyst      (Foundry + Agent Framework, calls the engine's MCP tools)  → a plan made only of fact ids
  Critic       every id must resolve to a computed fact     ── reject → re-plan ×3 → rule plan
  Storyteller  (Foundry + Agent Framework, structured output)  → analyst + fan text per beat
  Critic       every name, number and causal word checked   ── reject → retell ×3 → deterministic composer
  Editor       register · club / player focus · Azure AI Translator (re-checked)
     ▼
  bundle → 3D viewer
```

- **The Analyst can only point at facts.** Its plan is a list of ids, and an id that no engine tool
  returned fails the Critic. A test plants an invented fact and checks that it is refused.
- **The Critic is code, not a model.** It checks that a beat names only its own players, states only
  numbers the engine computed (at the precision written), and uses causal language ("ran past", "opened")
  only where the engine *measured* that link on the tracking.
- **Every model step has a deterministic floor** (a rule plan and a template composer). The whole
  pipeline runs offline, and CI runs it that way. The trace records which path was taken and why.

### 2. A metric layer built on published football research

The "why" is credit assignment over real analytics models, trained and validated on held-out games, not
a model's opinion:

| Model | Research | Used for |
|---|---|---|
| **VAEP** | Decroos et al., *Actions Speak Louder than Goals*, KDD 2019 (Best Paper) | The value of every on-ball action. It ships only if both of its models clear AUC ≥ 0.70 on held-out games; otherwise delta-xT is used. |
| **Expected Threat (xT)** | Karun Singh, 2018 | Zone threat, which values moves, regains and receiving points |
| **Expected Goals (xG)** | geometric shot model | The value of the chance being explained |
| **Pitch control** | Fernández & Bornn, *Wide Open Spaces*, 2018; Spearman, *Beyond Expected Goals*, 2018 | Who controlled the shooting spot, frame by frame, from positions and velocities |
| **Pass completion** | tracking features at the pass instant | The "better option existed" counterfactual |

These feed a **two-track causal account**:

- **On-ball:** each action's VAEP or delta-xT change in the attacking team's scoring probability.
- **Off-ball:** each player's share of pitch control at the shooting spot, recomputed with that player
  removed. This is how a defender's lapse is measured as space conceded or a broken marking.

A fact becomes evidence only if its effect clears a threshold, and it is bound to an event id or a
tracking frame. Off-ball causal links (`decoy_run`, `dragged_out`, `run_past`, `lost_man`) are measured
on the tracking. The counterfactual compares the chosen action to the options that were actually
available in that frame.

### Microsoft technology in the pipeline

| Technology | Role |
|---|---|
| **Microsoft Foundry** + **Microsoft Agent Framework** | Run the Analyst and Storyteller (`FoundryChatClient`, structured outputs, Entra ID auth). |
| **MCP**: the engine as an MCP server | The engine's four tools over stdio or Streamable HTTP. The Analyst calls them as its tool (`MCPStdioTool`). |
| **Azure MCP Server** | Reads the match feed from a **Fabric Eventhouse** (Kusto) and stored accounts from **Cosmos DB**. |
| **Azure AI Translator** / **Azure AI Content Safety** | The Editor's language step / the Critic's final safety screen. |
| **Babylon.js** | The 3D viewer. It builds as a static site for **Azure Static Web Apps**. |
| **GitHub Actions** | CI: tests, MCP smoke test, agents end to end, bundle export, viewer build. |

Each Azure service is used when configured and falls back to a local path when it is not. The full
breakdown of what is live and what is a fallback is in the spec.

**Read more:** [Technical Specification](REPLAY_ROOM_TECHNICAL_SPEC.md) ·
[ADR 0001: agency around a deterministic core](docs/adr/0001-agency-around-a-deterministic-core.md) ·
[Viewer guide](viewer/README.md)

## Run it locally

You need **Python 3.11 or 3.12** and **Node.js 18+** (developed on Node 22). The synthetic match and the
trained models are in the repo, so there is nothing to download or train.

**1. Install** (from the repo root):

```
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS / Linux: source .venv/bin/activate)
python -m pip install -e ".[dev]"
```

**2. Build the moments.** This step detects the moments, runs the attribution, runs the agents, and
writes one viewer bundle per moment to `data/accounts/`:

```
python -m replay_room.render data/fixtures/synthetic_match_02
```

`synthetic_match_02` (game `SYN-0055`) is the demo match, with 8 explained moments. `data/accounts/` is
git-ignored, so run this after every clone. Without Foundry configured, the agents use their
deterministic floors and the Critic checks the result either way, so this works offline. Add
`--narration template` to skip Foundry explicitly.

**3. Start the viewer:**

```
cd viewer
npm install
npm run dev
```

**4. Open** <http://localhost:5173/>. Press **Play analysis** (or **Space**) for the guided story, or
switch to **Explore** to scrub freely. **←/→** step between beats, and the picker (top right) opens the
other moments.

| Try | URL |
|---|---|
| The hero moment: a computed link and a better option that existed | <http://localhost:5173/?moment=SYN-0055-big_chance_saved-2> |
| …playing straight away | <http://localhost:5173/?moment=SYN-0055-big_chance_saved-2&play=1> |
| …in Fan mode | <http://localhost:5173/?moment=SYN-0055-big_chance_saved-2&mode=fan> |
| A goal | <http://localhost:5173/?moment=SYN-0055-goal-1> |
| A turnover to a shot | <http://localhost:5173/?moment=SYN-0055-turnover_to_shot-1> |

Other parameters: `&step=<n>`, `&view=explore`, `&jump=<contribution_id>`, `&stadium=0`.

**5. Watch the agents work** (prints the Scout's menu, the trace of every agent hop, and both editions):

```
python -m replay_room.agents                       # the hero moment
python -m replay_room.agents --via-mcp             # reach the engine through its MCP server
python -m replay_room.agents --focus-team NBR --focus-player EPA-11 --language fr
```

### Live narration with Microsoft Foundry

```
python -m pip install -e ".[foundry]"
az login
```

Then set the environment variables and re-run the render:

```
# macOS / Linux (bash)
export FOUNDRY_PROJECT_ENDPOINT="https://<resource>.services.ai.azure.com/api/projects/<project>"
export FOUNDRY_MODEL_DEPLOYMENT="<a deployment that supports structured outputs>"

# Windows (PowerShell)
$env:FOUNDRY_PROJECT_ENDPOINT = "https://<resource>.services.ai.azure.com/api/projects/<project>"
$env:FOUNDRY_MODEL_DEPLOYMENT = "<deployment>"

python -m replay_room.render data/fixtures/synthetic_match_02
```

Optional: `FOUNDRY_TEMPERATURE` (default `0.4`). Tellings are cached in `data/narrations/` and re-checked
by the Critic before reuse.

Other optional services, each with a local fallback:

| Service | Environment variables |
|---|---|
| Azure AI Translator | `AZURE_TRANSLATOR_KEY`, `AZURE_TRANSLATOR_REGION` |
| Azure AI Content Safety | `CONTENT_SAFETY_ENDPOINT`, `CONTENT_SAFETY_KEY` |
| Fabric Eventhouse (via Azure MCP, needs `npx`) | `EVENTHOUSE_CLUSTER_URI`, `EVENTHOUSE_DATABASE`, `EVENTHOUSE_TABLE` |
| Cosmos DB (via Azure MCP) | `COSMOS_ACCOUNT`, `COSMOS_DATABASE`, `COSMOS_CONTAINER` |

### Troubleshooting

* **"No bundles found"**: step 2 has not been run. The dev server serves `data/accounts/`; set
  `BUNDLES_DIR` to serve another folder.
* **Port 5173 in use**: `npm run dev -- --port 5180`.
* **A blank pitch**: the viewer needs WebGL, so check that hardware acceleration is on.
* **Old data after a re-export**: reload the page.

## Other commands

```
python -m pytest                          # Python tests (CI: .github/workflows/ci.yml)
python -m replay_room.mcp_server          # the engine as an MCP server (stdio; --http for Streamable HTTP)
python -m replay_room.mcp_server.smoke    # an MCP client lists and calls every tool
python -m replay_room.metrics.train       # retrain the metric models on the 200-match corpus
cd viewer && npm test                     # viewer tests
cd viewer && npm run build                # static site in viewer/dist/ (Azure Static Web Apps)
```

The full command list (replay clock, detect, metrics, attribution, explain, fixtures) is in `CLAUDE.md`.
