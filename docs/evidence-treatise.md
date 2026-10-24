# The Evidence Treatise — Deep Supporting Text & Positional Grounding

> Specification for the depth of evidence Replay Room produces and how the GPT agent must present it. The analysis is computed correctly; this document governs how it is **supported, quantified, and communicated** when a viewer goes deeper. Goes in the repo (`docs/evidence-treatise.md`). The acceptance-criteria version for the agent is in `prompts/`.

## 0. Why this exists

Shallow or vague supporting text makes correct analysis look arbitrary. A single bad line proves it:

> *"Alex Larsen wins the ball back for Eastport, and that is where the goal comes from. By VAEP it is the most valuable action in the move, worth about two-thirds of the chance."*

This fails five ways: (1) **vague** ("about two-thirds" instead of the number + comparison); (2) **wrong framing** ("the goal" in a *prevented* chance where no goal happened); (3) **asserts** ("the most valuable action") instead of **showing** the ranked evidence; (4) **no positional grounding** — the "going deeper" dimension (positions, averages, distances, space) is entirely absent; (5) **possible name/team inconsistency** the Critic failed to catch. The deep-evidence layer must make all five impossible.

**The moat rule is unchanged:** every number, position, average, distance, and event id is **computed deterministically and fed to the agent**. The agent narrates; it never invents a fact, a figure, or a causal link. The Critic verifies every one against the account.

## 1. The three layers of depth

Evidence is presented in increasing rigour; the viewer chooses how deep to go.

- **L1 — Claim (compact card).** One plain sentence + an evidence-status chip (`✓ Evidence · frame 140`). Readable at a glance, does not cover the pitch.
- **L2 — Evidence (on click).** The proof: the **involved players** (highlighted), the **frame** (camera + clock), the **measured change in plain terms with its exact number**, and the **supporting event IDs**.
- **L3 — Deep treatise (on "Why / Go deeper").** The full, rigorous account: positional context (average positions, deviations, distances), the ranked contributions shown, the spatial swing quantified, and how this fits the whole move — in connected, specific prose.

Each layer draws only on computed facts; L3 is where positional depth lives.

## 2. The computed facts that feed each layer

All deterministic, produced by the engine/tools, handed to the agent. The agent may use only these.

**On-ball (per action):**
- exact VAEP and Δ-xT (e.g. `VAEP +0.132`), not rounded-to-fractions;
- its share of the moment's outcome value (e.g. `0.132 of 0.174 = 76%`);
- its rank among the move's contributions;
- the event id(s).

**Off-ball / positional (per player, per frame) — the "going deeper" layer:**
- the player's **position** at the frame `(x, y)`;
- the player's **average position** over the match (or the available phase, with a confidence flag if the sample is short);
- the **deviation** from that average (how far, which direction — "stepped up 6.2m higher than usual");
- **distances**: to the ball, to the nearest opponent (distance-to-man), to goal;
- the **space / pitch-control value** at the outcome spot, and its **swing** over the window (e.g. "control at the shooting spot moves 0.41 → 0.68 over 1.2s");
- **marking/assignment**: who was responsible for whom, and whether it held;
- the tracking **frame id(s)**.

**Outcome:**
- `realized` (goal happened) vs `prevented` (chance denied) — governs every framing word;
- the outcome value (xG) and `beneficiary_team`.

> **Average positions need enough frames.** On a short synthetic match, compute over the available phase and **mark the figure's confidence**; never fabricate a baseline to sound rigorous.

## 3. How the agent must write supporting text (the rules)

1. **Exact, not vague.** Give the number and its comparison. "VAEP +0.132 — the move's largest contribution, 76% of its 0.174 xG." Never "about two-thirds", "roughly", "a big chunk".
2. **Frame by the outcome.** `prevented` → "the chance", "the chance that was denied", "a goal that didn't happen". **Never "the goal"** when no goal occurred. `realized` → the goal. The word must match `outcome.realized`.
3. **Show, don't assert.** Don't say "the most valuable action" — present the ranked contributions (or state the rank with its number) so the reader sees it: "largest of the six contributions (+0.132; next is +0.087)".
4. **Names and teams verbatim from the account.** Never merge first names/surnames, never flip a player's team. If the account says Casey Larsen (Northbridge), the text says exactly that, everywhere.
5. **Go positional when going deep.** L3 must reference the computed positional facts: average position, deviation, distance-to-man, the space swing. This is what makes it a treatise rather than a restated number.
6. **Connected, not fragmented.** One causal thread: what happened → the measured why → how it fits the move. No template fragments, no triple-stated signal.
7. **Complete in Fan mode too.** Fan register drops jargon and raw figures but still explains *why* fully — the depth is in the reasoning, not the vocabulary.

## 4. Anti-patterns — forbidden (each maps to a failure of the bad example)

- ❌ Vague magnitude ("about X", "roughly", "a fair bit"). → exact number + comparison.
- ❌ "the goal" (or any realized-outcome wording) in a `prevented` moment. → outcome-correct framing.
- ❌ Bare assertion of rank/importance with no number shown. → show the ranked values.
- ❌ Any player, team, number, position, average, distance, or event id **not** in the account. → grounding violation; Critic rejects.
- ❌ Inconsistent naming/team across a moment. → verbatim from account.
- ❌ L3 "depth" that just restates the VAEP number in longer prose with no positional content. → must add positions/averages/distances/space.

## 5. Rendering the positional evidence — the on-pitch visual language

Evidence is **shown on the pitch**, not just stated. This section is the catalog of visual aids the field uses to make a claim tangible as it is discussed.

### 5.0 The governing principle — contextual, synchronized, uncluttered

The failure mode is **too many overlays at once** (the cluttered-pitch problem). The rule:

- **One claim at a time.** Only the overlays that prove the **current** claim/beat are drawn; they **clear when the viewer moves on** to the next beat or claim.
- **Synchronized to the narration.** As the supporting text names a thing ("stepped up out of shape", "the space swings to Eastport", "the better ball was square"), its overlay appears in step with it.
- **Every element is a computed fact.** No overlay is decorative-as-evidence. Positions are observed; averages are confidence-flagged; each line, zone, arrow, and number maps to a value in the account.
- **Layered by depth.** L1: spotlight only. L2: the single overlay that proves the claim + its number. L3: the rich positional set — but still only what's relevant to the beat.
- **Toggleable.** The legend lets the viewer turn layers on/off; nothing is forced on.

### 5.1 Catalog of evidence visuals (grouped by what they prove)

**A. Who and where (focus)**
- **Spotlight / dim** — the players the claim names are lit; everyone else is dimmed, so the eye goes to the evidence.
- **Relevant labels only** — name just the players in the claim, not all 22.
- **Average-position ghosts + deviation arrow** — a faint marker at each relevant player's average position, with an arrow from average → actual, so "pulled out of shape / stepped up 6.2m" is *seen*.

**B. Space and threat**
- **Pitch-control surface** — the field tinted by which team controls each area (the computed control field); fade it in to show the **space**, and animate the **swing** ("0.41 → 0.68 at the shooting spot") as it happens.
- **Threat (xT) gradient** — zones shaded by danger, so "moved into a high-threat area" is visible as colour.
- **Contested-space zone** — a highlighted patch at the outcome spot (the space conceded/created), annotated with its value.

**C. Actions and options**
- **Possession-chain / ball path** — the ball's route through the move drawn as a connected path across the chain actions, so the build-up is one visible thread.
- **Pass / movement arrows** (dashed) and **shot arrow** (solid), each labelled with its value (Δ-xT / xG).
- **Counterfactual options** — at the decision frame, the **chosen** action and the **best available** option drawn as distinct arrows with their values ("chosen 0.113 vs better 0.206"). This is the sharpest single visual.
- **Movement trails + velocity** — a short trail of a player's recent path and a velocity vector, so runs and acceleration into space read physically.

**D. Defensive structure**
- **Defensive line** — the back line (offside line) drawn; highlight it **breaking** when a runner gets behind.
- **Marking links** — a line from a defender to the man they are responsible for; it turns **red when the assignment breaks** ("stopped tracking the runner"). This makes a defensive flaw literally visible.
- **Pressure indicators** — a ring or cone on a player under pressure, so "forced into the error" is grounded.

**E. Measurement annotations**
- **Distance lines** — distance-to-man / to-goal drawn with the number on it, when the distance carries the claim ("4.1m from the nearest runner").
- **Floating value tags** — the measured quantity placed at the spot it refers to (the control swing at the shooting spot, the space value in the zone) — appearing with the claim, clearing after.

### 5.2 How they combine with the depth layers

- **L1 (claim):** spotlight the named player(s); nothing else.
- **L2 (evidence):** the one overlay that proves this claim — e.g. a defensive claim draws the marking link (red if broken) + the contested-space zone + its value; a pass claim draws the pass arrow + Δ-xT; a chance claim draws the shot arrow + xG.
- **L3 (deep):** add the positional set relevant to the beat — pitch-control surface + its swing, average-position ghosts + deviation arrows, the key distance line, the counterfactual options. Rich, but still only this beat's facts, and it clears when the viewer advances.

Every visual in this catalog corresponds to a computed fact; nothing decorative is ever presented as evidence, and no two overlays are stacked so densely that the pitch stops reading.

### 5.3 The timeline / progress-bar rebuild (build exactly to this)

The old bottom scrubber (a media bar with a thumbnail rail) is replaced by a **three-tier Match Timeline** that reads as part of the evidence language, not as a video control. Build it **exactly to the reference**: a dark panel, three stacked rows, then a selected-moment card. Below is the spec, tier by tier.

**Tier 1 — Header.**
- Left: label **`MATCH TIMELINE`** (uppercase, bold).
- Right: the clock **`<selected/current> / <total>`** — e.g. `03:00 / 05:00`. First value is the current replay position (snaps to the selected moment's time); second is total match length. Monospaced-feel, muted.

**Tier 2 — Replay progress (the seek bar).**
- Left: a **circular play/pause control** (triangle in a filled yellow/amber disc); toggles playback and is kept in sync with the spacebar pause (§ the viewer's spacebar fix).
- Left label: **`Replay progress`**.
- Right: the hint **`Drag to seek`** and the **speed control `1×`**.
- The bar itself: a thin, rounded track — **amber/yellow fill** for the played portion, **dark-grey** for the remainder, draggable to scrub. One accent colour (amber) owns "progress"; it is not reused for event types.

**Tier 3 — Match events (the marker track).**
- Left label: **`Match events`**. Right hint: **`Select an event to jump to it`** (the markers are clickable; clicking seeks the replay to that event — this is the jump-to-evidence affordance surfaced on the timeline).
- A horizontal track carrying **one dot per real event**, positioned by its timestamp. Dots are **colour-coded by event type**, with a legend directly beneath:
  - 🔵 **Pass** (blue)
  - 🟠 **Defensive error** (orange)
  - 🟢 **Shot / outcome** (green)
- **Timestamp ticks** under the track at the sensible anchors (e.g. `02:53` … `03:00` … `03:05`) spanning the moment window, not the whole match — the track zooms to the selected moment's neighbourhood so the beats are legible.
- **Every dot is a computed event**: its position is the event's real timestamp, its colour its real type, and clicking it seeks to that event's frame. No decorative markers; the dot set is exactly the events in the account/export for this window.

**Tier 4 — Selected moment card (beneath the timeline).**
- A moment icon (◎) + **`Selected moment · <time>`** (e.g. `Selected moment · 03:00`).
- The **one-line claim**, verbatim from the account's headline — e.g. *"Larsen intercepts the ball after Hale's mistake."* (names/teams exact per §3.4; framing per `outcome.realized` per §3.2).
- The **outcome metric line**, from the account: *"11% chance of scoring · xG 0.110"* — the gloss + the exact figure (number discipline: meter-style gloss first, raw xG second; Fan mode drops the raw `xG 0.110` and keeps "11% chance of scoring").

**Rules that keep it account-bound and uncluttered.**
- The selected-moment card, every event dot, and both clock values are **drawn from the account/export** — nothing on the timeline is invented. A dot with no backing event, or a card claim/metric not in the account, is a grounding violation (Critic territory, § 6).
- The amber "progress" accent and the three event-type colours are a **fixed four-colour vocabulary**; don't introduce more. The event legend is always shown so the colours are never ambiguous.
- Selecting an event (Tier 3) or a moment updates the card (Tier 4) and seeks the bar (Tier 2) **together** — one selection, one synchronized state, consistent with the §5.0 "one claim at a time" rule.

**Acceptance (this subsection):** the rebuilt timeline matches the reference — `MATCH TIMELINE` + `<cur>/<total>` clock; amber Replay-progress seek bar with play control, `Drag to seek`, `1×`; a Match-events track with type-coloured, clickable dots, the Pass/Defensive-error/Shot-outcome legend, and window-scoped timestamp ticks; and a Selected-moment card with icon, `Selected moment · <time>`, the account's one-line claim, and the `<n>% chance of scoring · xG <value>` metric. Every dot and every card value is account-bound; clicking a dot seeks to its event.

## 6. The Critic's expanded checks

Beyond "every ref exists", the Critic now also rejects:
- a **framing word that contradicts `outcome.realized`** ("goal" in a prevented moment);
- a **player attributed to the wrong team**, or a name not matching the account;
- a **number that doesn't match** the account's value (within tolerance), including invented shares/percentages;
- a **positional claim** (average, deviation, distance) with no backing computed fact.
On any violation: reject, request a redo, else fall back to the deterministic composer.

## 7. Worked example — the bad line, rewritten

*Names/figures below are placeholders; the real ones come verbatim from the account — which is exactly the point.*

**L1 (claim):** "[Player] wins the ball in midfield — the turn that creates the chance." `✓ Evidence · frame 140`

**L2 (evidence):** "Interception — [Player], [Team] — frame 140. VAEP **+0.132**, the largest of the move's six contributions (76% of its 0.174 xG; next largest +0.087). Events: `evt_0138`, `evt_0140`."

**L3 (deep treatise):** "[Player] reads [Keeper]'s short distribution and steps up to intercept **6.2m higher than their average position** this phase. The regain flips possession in the middle third and opens the central channel: pitch control at the shooting spot swings **0.41 → 0.68** in [Team]'s favour over the next 1.2s, with [Defender] now **4.1m** from the nearest runner where they had been tight. It is the move's hinge — without the regain, [Team]'s scoring chance here stays near zero. The attempt that follows is ultimately **denied** (chance worth 0.174 xG, not a goal)."

Note how the rewrite fixes every failure: exact numbers + comparison, `denied`/`chance` framing (not "goal"), rank shown, positions and averages and distances and the control swing, consistent naming, and event + frame ids.

## 8. Scope note (Oct 24 → 27)

Priority order inside this: **L2 (exact number + event ids + correct framing)** is the must — it completes the "evidence unmistakable" ask and fixes the worst failures (vagueness, wrong framing, assert-not-show). **L3 positional depth (average positions, deviations, distances, space swing)** is the differentiator; build the computed positional facts first, then the agent text and the ghost-marker/deviation rendering. If the match is too short for stable averages, ship L2 fully and L3 with confidence-flagged positions.

**For the on-pitch visuals (§5), the highest-leverage few for the demo** — build these first, each synchronized to its claim and clearing after: (1) **marking links** that turn red when broken (makes a defensive flaw visible), (2) the **pitch-control surface + its swing** (makes space tangible), (3) the **counterfactual chosen-vs-better arrows** (the sharpest single visual), (4) **average-position ghosts + deviation arrows** (the "out of shape" read). The rest of the catalog is additive; do not ship all overlays on at once — the contextual/synchronized rule in §5.0 is what keeps the pitch legible.

**The timeline/progress-bar rebuild (§5.3) is a must, not additive** — it replaces the old scrubber and is visible in every demo frame. Build it to the reference exactly; it's low-risk (UI + already-computed event refs) and carries the jump-to-evidence affordance, so do it alongside L2. Its one dependency is that the export exposes, per event in the moment window, the `{time, type∈{pass, defensive_error, shot/outcome}, ref}` the dots need, plus the selected moment's headline + outcome metric for the card — all already in the account.
