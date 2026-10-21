# Replay Room viewer (Build 5)

A static Babylon.js front-end that replays one moment in 3D from its bundle and proves the causal
account on the pitch. Markers, not models: discs with shirt numbers in team colours, a ball, a pitch to scale.

* **Bundles** come from the exporter: `python -m replay_room.render data/fixtures/synthetic_match_01`
  writes `data/accounts/<game>/<moment>.bundle.json` and `data/accounts/index.json`. The dev server and
  `vite build` serve that folder as static files (`BUNDLES_DIR` overrides it).
* **Dev harness** (no backend, no Azure), from the repo root with the project venv active:

  ```
  python -m replay_room.render data/fixtures/synthetic_match_01
  cd viewer && npm install && npm run dev
  ```

  Open `http://localhost:5173/`. Query parameters: `?moment=<moment_id>` picks a moment (default: the first
  prevented one), `&jump=<contribution_id>` opens on a contribution, `?bundle=<path>` loads one bundle file.
* **Deploy**: `npm run build` writes `dist/` (app + bundles); it is an Azure Static Web Apps app as is
  (`staticwebapp.config.json`).
* **Tests**: `npm test` (vitest; the scene test runs Babylon's NullEngine headless), `npm run typecheck`.

What it shows, and only from the bundle:

* every player and the ball from the observed tracking (Hermite between 10 Hz samples using the feed's
  velocities; a gap is crossed in a straight line and drawn dimmed; nothing is extrapolated);
* the account's contributions, headline first: clicking one pauses, seeks to its jump frame (off-ball:
  the cited frame; on-ball: the frame aligned with the cited event), rings the players it names, draws
  its overlay and frames the camera on it;
* overlays: an on-ball action as an arrow from where it started to where it ended; a run as its trail and
  velocity; space created or conceded as the shaded spot Build 4 measured (radius 2 x `sigma_m`); a marking
  break as the line from the defender to the man he stopped tracking; the counterfactual as chosen (grey,
  dashed) vs better (green) arrows from the ball, labelled with their values;
* the outcome always: the shot's track ending in a goal, or (prevented) in an orange "denied" cross at
  the save or the miss, with a banner saying so.

It renders the account; it never ranks, computes or writes prose.
