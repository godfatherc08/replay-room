# Replay Room viewer

A static Babylon.js app that replays one moment in 3D from its bundle and tells it on the pitch, beat by beat,
as the agents planned and wrote it. Every word, number, meter and overlay is a bundle field (account, plan,
match context, the Critic-checked telling, meaning, match info); what the bundle lacks is left out, never
filled in.

* **Bundles** come from the exporter: `python -m replay_room.render data/fixtures/synthetic_match_01`
  writes `data/accounts/<game>/<moment>.bundle.json` (bundle v4) and `data/accounts/index.json`, embedding
  the framing plan, the match context and the telling (the Foundry agents when configured, else the rule plan
  and the deterministic composer; Critic-checked either way). The dev server and
  `vite build` serve that folder as static files (`BUNDLES_DIR` overrides it).
* **Dev harness** (no backend), from the repo root with the project venv active:

  ```
  python -m replay_room.render data/fixtures/synthetic_match_01
  cd viewer && npm install && npm run dev
  ```

  Open `http://localhost:5173/`. Query parameters: `?moment=<moment_id>` (default: the first prevented
  moment), `&mode=fan`, `&view=explore`, `&jump=<contribution_id>` (Explore, at that fact),
  `&step=<n>` (Story, at step n), `&play=1` (start the analysis), `&stadium=0` (the bare pitch),
  `?bundle=<path>`.
* **Screenshots** (visual verification): with the dev server up, `npm run shots -- <outDir>` drives the
  installed Microsoft Edge headlessly (playwright-core, no browser download; `SHOTS_CHANNEL=chrome` for
  Chrome) and captures the hero moment: ready, a story step, the ribbon mid-play, the counterfactual
  climax, Fan vs Analyst, an Explore jump, a close-up of the figures, the defensive flaw told through its
  computed link, the match-context beat, the bare pitch, and a keyboard probe (Space must not scroll).
* **Deploy**: `npm run build` writes `dist/` (app and bundles): an Azure Static Web Apps app as is
  (`staticwebapp.config.json`).
* **Tests**: `npm test` (vitest; the scene test runs Babylon's NullEngine headless; `styles.test.ts`
  enforces the type scale), `npm run typecheck`.

What it shows:

* **Story** (default). The moment opens on a title card over the paused pitch: the class, the outcome
  ("A goal that didn't happen"), the telling's headline, the outcome as a probability gauge, and **Play
  analysis**. Playing walks the bundle's `story`, which is the Analyst's framing plan as told: the build-up,
  the lead (the account's headline), then the defensive flaw it points at (told through its computed link
  when the engine measured one: whose run went past whom, which zone that opened, which pass used it), a
  match-context beat where this moment deviates from the match ("their back line 16 m from goal, against a
  norm of 9 m"), the outcome (why it was a chance, and what made it), and the counterfactual. Each step
  replays a short lead-in into its frame, puts its players in focus (ringed; everyone else fades), floats one
  name tag, eases the camera onto them, draws that step's overlay alone, and shows one caption and one meter.
  Steps advance every 3 s (the climax beats stay longer; the speed control scales it), by hand with ◀ / ▶,
  or with the keyboard: **Space** plays / pauses (it never scrolls the page), **← / →** step.
* **Evidence on demand.** Every claim proves itself. The step card is compact and docked bottom-left: the
  claim in one or two lines and its evidence status ("✓ Evidence · 1 event · frame 2419"); "Why" expands the
  rest of the telling and what was measured. Clicking the claim (or a fact in the chain) opens its proof: the
  clock seeks to the proof's frame, every player it involves is ringed and named (everyone else dims), the
  camera closes in, and the panel lists what was measured, with the number and its meaning ("Jordan Novak's
  position gave up space worth +0.012 of a scoring chance at the shot spot"), the players and their roles,
  the frames, and the feed's own event ids (`ev00220`). All of it is the bundle's `proofs`, read off the
  account by the exporter; Fan shows the same proof in words, with the records but no metrics.
* **Three layers of depth** (`docs/evidence-treatise.md`). L1, the claim: one line and its evidence status.
  L2, the evidence (click the claim): the players, the frame, the exact measured number with its rank and
  share ("VAEP +0.087: the largest of the 8 facts that built the chance, 58% of the 0.152 xG chance"), the
  feed's event ids. L3, **Go deeper**: the deep passage (where each player stood against their average in
  that phase, with its confidence; distances; the attacking team's pitch-control swing at the shooting spot;
  a marking, held or broken) and, on the pitch, only that beat's positional evidence: the control surface
  fading over the swing, average-position ghosts with deviation arrows, the marking in green or red, the key
  distance. Each layer toggles from the legend; numbers on the pitch in Analyst only.
* **The Match Timeline** (bottom): MATCH TIMELINE with `<current> / <total>`; Replay progress (the amber
  play disc, the amber seek bar, Drag to seek, the speed); Match events, one dot per event of the window,
  coloured by kind (pass / build-up, defensive error, shot / outcome) with its legend and ticks, a dot seeking
  to its event and opening its proof; and the selected moment with its claim and outcome metric.
* **The causal-chain ribbon** under the pitch: one node per beat with the role icon, a ring in the team's
  colour and a bar for the fact's normalized |effect| (green helped the chance, red cost it); the lead
  carries the accent ring, the defensive flaw a red one; computed links and context have their own icons;
  the outcome and the better option close the chain. A fill sweeps along it as the
  story plays and the current node pulses. Clicking a node shows that step.
* **Explore**: free scrubbing and orbiting; the panel's chain lists every fact (click one: the clock seeks to
  its frame, its players are focused and its overlay drawn).
* **Analyst / Fan** (orthogonal to both): two registers of the same telling. Analyst captions may weave
  in a computed number as meaning, and the raw metric shows as small secondary text (`VAEP +0.087`,
  `xG 0.152`); Fan captions are written without numbers or jargon, and Fan never shows a raw metric (the
  outcome is a band: "A good chance").
* **Players**: one stylized figure built from primitives (near-white matte body, team-coloured shirt and
  shorts; goalkeepers in their own colour) drawn as 22 thin instances, turned to face their observed
  velocity, moved along the observed tracking (Hermite on the feed's velocities; a gap is crossed in a
  straight line and drawn darker; nothing is extrapolated). Capsules if the figure cannot be built.
* **On-pitch vocabulary** (collapsible legend): dashed yellow = pass / movement, solid red = shot, cyan =
  threat zone (the space at the key spot Build 4 measured), amber = a defender's own path in a computed link
  and the back line here (dashed white: where it usually stands), solid white = the option chosen, dashed
  green = the better option, amber ring = in focus. No floating metric tags; only the decision's two options
  are labelled (with their values in Analyst).
* **Stadium**: procedural tiered stands with a low-detail crowd, floodlight towers and a night sky, so the
  pitch does not float in a void (`src/stadium.ts`; decorative, off with `&stadium=0`).
* **Timeline**: a match strip with every exported moment (click to open), and the replay window's scrubber
  with a marker per fact.

Type scale (`src/styles.css`): display 20px, title 15px, body 13px, label 11px, micro 10px; weights
600 / 500 / 400; an 8px spacing grid.

It renders what the agents planned and wrote and the Critic passed; it never ranks, computes or writes prose.
