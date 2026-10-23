# Replay Room viewer (Build 5)

A static Babylon.js app that replays one moment in 3D from its bundle and walks the causal account on the
pitch, step by step. Every word, number, meter and overlay is a bundle field (account, meaning, story,
Build 6 narration, match info); what the bundle lacks is left out, never filled in.

* **Bundles** come from the exporter: `python -m replay_room.render data/fixtures/synthetic_match_01`
  writes `data/accounts/<game>/<moment>.bundle.json` (bundle v3) and `data/accounts/index.json`, embedding
  the Build 6 narration (Foundry when configured, else the validated template). The dev server and
  `vite build` serve that folder as static files (`BUNDLES_DIR` overrides it).
* **Dev harness** (no backend), from the repo root with the project venv active:

  ```
  python -m replay_room.render data/fixtures/synthetic_match_01
  cd viewer && npm install && npm run dev
  ```

  Open `http://localhost:5173/`. Query parameters: `?moment=<moment_id>` (default: the first prevented
  moment), `&mode=fan`, `&view=explore`, `&jump=<contribution_id>` (Explore, at that fact),
  `&step=<n>` (Story, at step n), `&play=1` (start the analysis), `?bundle=<path>`.
* **Screenshots** (visual verification): with the dev server up, `npm run shots -- <outDir>` drives the
  installed Microsoft Edge headlessly (playwright-core, no browser download; `SHOTS_CHANNEL=chrome` for
  Chrome) and captures the hero moment: ready, a story step, the ribbon mid-play, the counterfactual
  climax, Fan vs Analyst, an Explore jump and a close-up of the figures.
* **Deploy**: `npm run build` writes `dist/` (app and bundles): an Azure Static Web Apps app as is
  (`staticwebapp.config.json`).
* **Tests**: `npm test` (vitest; the scene test runs Babylon's NullEngine headless; `styles.test.ts`
  enforces the type scale), `npm run typecheck`.

What it shows:

* **Story** (default). The moment opens on a title card over the paused pitch: the class, the outcome
  ("A goal that didn't happen"), the narration's headline line, the outcome as a probability gauge, and
  **Play analysis**. Playing walks the bundle's `story`: the other contributions in time order, then the
  headline, then the outcome, then the counterfactual. Each step replays a short lead-in into its frame,
  puts its players in focus (ringed; everyone else fades), floats one name tag, eases the camera onto them,
  draws that step's overlay alone, and shows one caption with the fact's gloss and meter. Steps advance
  every 3 s (the climax beats stay longer; the speed control scales it), or by hand with ◀ / ▶.
* **The causal-chain ribbon** under the pitch: one node per step with the role icon, a ring in the team's
  colour and a bar for the fact's normalized |effect| (green helped the chance, red cost it); the headline
  carries the accent ring; the outcome and the better option close the chain. A fill sweeps along it as the
  story plays and the current node pulses. Clicking a node shows that step.
* **Explore**: free scrubbing and orbiting; the panel's chain lists every fact (click one: the clock seeks to
  its frame, its players are focused and its overlay drawn).
* **Analyst / Fan** (orthogonal to both): every value is a meter plus plain words. Analyst adds the raw
  metric as small secondary text (`VAEP +0.087`, `xG 0.152`); Fan never shows a raw metric: the outcome is
  a band ("A good chance"), and a narration sentence that quotes a number is replaced by its plain line.
* **Players**: one stylized figure built from primitives (near-white matte body, team-coloured shirt and
  shorts; goalkeepers in their own colour) drawn as 22 thin instances, turned to face their observed
  velocity, moved along the observed tracking (Hermite on the feed's velocities; a gap is crossed in a
  straight line and drawn darker; nothing is extrapolated). Capsules if the figure cannot be built.
* **On-pitch vocabulary** (collapsible legend): dashed yellow = pass / movement, solid red = shot, cyan =
  threat zone (the space at the key spot Build 4 measured), solid white = the option chosen, dashed green =
  the better option, amber ring = in focus. No floating metric tags; only the decision's two options are
  labelled (with their values in Analyst).
* **Timeline**: a match strip with every exported moment (click to open), and the replay window's scrubber
  with a marker per fact.

Type scale (`src/styles.css`): display 20px, title 15px, body 13px, label 11px, micro 10px; weights
600 / 500 / 400; an 8px spacing grid.

It renders the account; it never ranks, computes or writes prose.
