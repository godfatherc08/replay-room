# Replay Room viewer (Build 5)

A static Babylon.js app that replays one moment in 3D from its bundle and proves the causal account on
the pitch: a broadcast-style screen with a top scoreline, a left rail, the 3D pitch, an evidence panel and
a timeline. Every word and number on screen is a bundle field (account, display rows, Build 6 narration,
match info); what the bundle lacks is left out, never filled in.

* **Bundles** come from the exporter: `python -m replay_room.render data/fixtures/synthetic_match_01`
  writes `data/accounts/<game>/<moment>.bundle.json` (bundle v2) and `data/accounts/index.json`, embedding
  the Build 6 narration (Foundry when configured, else the validated template). The dev server and
  `vite build` serve that folder as static files (`BUNDLES_DIR` overrides it).
* **Dev harness** (no backend), from the repo root with the project venv active:

  ```
  python -m replay_room.render data/fixtures/synthetic_match_01
  cd viewer && npm install && npm run dev
  ```

  Open `http://localhost:5173/`. Query parameters: `?moment=<moment_id>` (default: the first prevented
  moment), `&jump=<contribution_id>` (default: the headline), `&mode=fan`, `?bundle=<path>`.
* **Deploy**: `npm run build` writes `dist/` (app, player model, bundles): an Azure Static Web Apps app as
  is (`staticwebapp.config.json`).
* **Tests**: `npm test` (vitest; the scene test runs Babylon's NullEngine headless), `npm run typecheck`.

What it shows:

* **Players**: one CC0 humanoid (`assets/`, Kenney) drawn as 22 thin instances, tinted by side (home red,
  away blue, goalkeepers lime), numbered, turned to face their observed velocity, moved along the observed
  tracking (Hermite on the feed's velocities; a gap is crossed in a straight line and drawn darker; nothing
  is extrapolated). Capsules if the model cannot load.
* **Evidence panel** (Event tab): the moment header (class, PREVENTED/REALIZED, V, match clock, the
  narration's headline line), the evidence list in story order with the headline highlighted and
  pre-selected (click a row: the clock seeks to its frame, the camera frames it, its players get a ring,
  its overlay is drawn), and the summary (the narration's first sentences, plus the full cited chain).
  Tactics (counterfactuals), Metrics (the numbers behind each fact) and Players tabs read the same account.
* **On-pitch vocabulary** (legend): dashed yellow = pass / movement, solid red = shot, cyan = threat zone
  (the space at the key spot Build 4 measured), dashed green = the better option, yellow ring = selected.
* **Timeline**: a match strip with every exported moment (click to open), and the replay window's scrubber
  with a marker per piece of evidence. "Live" is disabled: this is a replay, no live feed is connected.
* **Fan mode** is the seam for Build 7 (personalization): today it shows the header and summary only.

It renders the account; it never ranks, computes or writes prose.
