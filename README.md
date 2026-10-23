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

**2. Export the moments** the viewer plays (detect → attribute → narrate → bundle):

```
python -m replay_room.render data/fixtures/synthetic_match_01
```

This writes one bundle per moment to `data/accounts/` (it is git-ignored, so run this after every clone).
Narration uses Microsoft Foundry when it is configured (see below); otherwise it falls back to the
validated template narration automatically, so this step works offline.

**3. Start the viewer:**

```
cd viewer
npm install
npm run dev
```

**4. Open** <http://localhost:5173/>. It opens the first prevented moment on its title card: press
**Play analysis** to watch the guided story, or switch to **Explore** to scrub and click freely. The
moment picker (top right) opens the match's other moments.

Useful links:

| What | URL |
|---|---|
| The hero moment (with the counterfactual) | <http://localhost:5173/?moment=SYN-0007-big_chance_saved-3> |
| …playing straight away | <http://localhost:5173/?moment=SYN-0007-big_chance_saved-3&play=1> |
| …in Fan mode | <http://localhost:5173/?moment=SYN-0007-big_chance_saved-3&mode=fan> |
| …at a given story step (1-based) | <http://localhost:5173/?moment=SYN-0007-big_chance_saved-3&step=11> |
| A goal | <http://localhost:5173/?moment=SYN-0007-goal-1> |

Other parameters: `&view=explore`, `&jump=<contribution_id>` (Explore, at that fact). The viewer's own
README (`viewer/README.md`) describes everything on screen.

### Optional: model narration (Microsoft Foundry)

```
python -m pip install -e ".[foundry]"
az login
set FOUNDRY_PROJECT_ENDPOINT=<your project endpoint>      # macOS / Linux: export ...
set FOUNDRY_MODEL_DEPLOYMENT=<your model deployment>
python -m replay_room.render data/fixtures/synthetic_match_01
```

Narrations are cached in `data/narrations/` and validated against the account before they are used.

### Troubleshooting

* **"No bundles found"** in the viewer: step 2 has not been run (or wrote elsewhere). The dev server
  serves `data/accounts/`; set `BUNDLES_DIR` to serve another folder.
* **Port 5173 in use**: `npm run dev -- --port 5180`, then open that port.
* **A blank pitch**: the viewer needs WebGL; check that hardware acceleration is on in the browser.
* **Re-exported but the viewer shows old data**: reload the page (bundles are static files).

## Other commands

```
python -m pytest                     # Python tests
cd viewer && npm test                # viewer tests
cd viewer && npm run build           # static site in viewer/dist/ (Azure Static Web Apps)
cd viewer && npm run shots -- out    # with the dev server up: headless screenshots of the hero moment
```

The full command list (replay clock, detect, metrics, attribution, explain, fixtures) is in `CLAUDE.md`.
