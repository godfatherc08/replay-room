# Agentic Push for Replay Room

> The consolidated build: engine-quality fixes, the agentic orchestration layer, and the communication/viewer polish — in dependency order. Paste into a Claude Code session in the `replay-room` repo. Lives at `prompts/agentic-push.md`.
>
> **Phased and gated. The engine work (Phase 1) must be validated before the agents wrap it (Phase 2) — agents can only present what the engine computes. Acceptance-criteria-driven: you are done only when the §final self-audit is checked against evidence.**

---

You are the lead engineer on **Replay Room**. The structure is strong but three things undersell it: the analysis is attacking-team-only and its headlines are weak; the narration reads as templated fragments, not explanation; and the viewer lacks basic affordances and environment. This push fixes all three and adds the agentic layer the hackathon scores. Read, then execute in phase order.

## The governing rule (unchanged, enforced harder here)

> **The engine computes the facts and the causal links. Agents select, order, emphasize, verify, and adapt them. No agent — including the Analyst — ever authors a fact or a causal link that the engine did not compute.**

Every defensive, off-ball, and game-context insight must be a **computed, ref-bound fact from a tool**, never an LLM inference. This is the moat.

## Priority / phase order

1. **Phase 1 — Engine quality** (headline fix; surface defensive/off-ball facts; compute marking/run→space links; stretch: match-context baseline). Validate before Phase 2.
2. **Phase 2 — Agentic orchestration** (engine as MCP server; Scout / Analyst / Storyteller / Critic / Editor on Agent Framework + Foundry; Azure MCP).
3. **Phase 3 — Communication + viewer polish** (real-language narration; spacebar pause; gated stadium).

---

## PHASE 1 — Engine quality (do first, validate before Phase 2)

The agents present engine output faithfully. Weak engine → faithfully-presented weak analysis. Fix the engine first.

**1a. Headline selection.**
- Select the headline by **|value| × recency** (recency = normalized position in the moment window; last ≈ 1.0, first ≈ low). Body of the account stays ranked by pure |value|.
- For a **scored** moment, frame around the **scoring team's decisive act** (the finish / the key pass) or a clearly-phrased defensive cause — never "goalkick fail" by the conceding team as a bare headline. A defensive-cause headline must read as "Eastport punished a Northbridge goalkick error", not "Alex Hale, goalkick fail".
- Acceptance: on the goal currently headlined "goalkick fail", the headline becomes a proximate, sensible cause.

**1b. Surface the defensive / off-ball facts (stop burying them).**
- The engine already computes off-ball defensive facts (space conceded, marking breaks). Ensure they can **co-lead** — reweight/threshold so a real defensive flaw is not pushed to mid-table beneath every small on-ball touch.
- The defensive layer is **supporting, never the main thing** — the attacking story leads and *points at* the defensive flaw.

**1c. Compute the links (grounded, not inferred).**
- Where the data supports it, compute the **causal link** behind a defensive flaw: who was marking whom (nearest-defender assignment), whose run increased a defender's distance-to-man, which vacated zone the shot/pass exploited. Emit these as linked facts: `{run: player, displaced: defender, opened_zone: z, enabled: ref}`.
- If a link cannot be computed reliably in time, present the grounded facts **adjacently** ("Brandt ran into space" + "D4 conceded space there") **without asserting a link** — never invent the connection.

**1d. Match-context baseline (STRETCH — feasibility-gated).**
- Compute per-match team/player **baselines** and flag where this moment **deviates**: pressing frequency ("regained within 3s on 14 of 16 losses this match; here 6.2s"), defensive line height, marking tightness.
- **Gate on data sufficiency:** the match must have enough events for a baseline to mean anything. If the synthetic match is too short/sparse, compute what is reliable, mark confidence, and **do not fabricate a baseline**. Do not bet the demo on this.
- Expose it as a tool (`match_context(moment)`), consumed in Phase 2 by the Analyst.

**Phase 1 gate:** headlines are sensible and proximate; defensive/off-ball facts can co-lead; links are computed where feasible (or facts shown adjacently, no invented links); match-context exists where data allows, with confidence. **Validate on several moments before starting Phase 2.**

---

## PHASE 2 — Agentic orchestration

**2a. Expose the engine as an MCP server** (`src/replay_room/mcp_server/`): `detect_moments`, `attribute`, `narrate`, and `match_context` as MCP tools — no logic changes, just a protocol surface. Smoke test: an MCP client lists and calls each and gets valid output. This is the demoable MCP-integration proof.

**2b. The agents** (Microsoft Agent Framework on Foundry Agent Service; verify live SDK surfaces first):
- **Scout** — consumes the synthetic stream; produces the **described replay menu** (engine-eligible + flagged, incl. red_card as description-only). Grounded by `detect_moments`. Never explains.
- **Analyst** (RESTORED, grounded) — for an engine-eligible moment, calls `attribute` **and** `match_context`, and assembles a **framing plan**: an ordered selection of grounded facts that **leads with the attacking move and points at the defensive flaw / context deviation as a supporting beat**. **It may only include facts the tools returned, each carrying its ref; it may choose, order, and emphasize, but never author a new fact or link.**
- **Storyteller** — turns the Analyst's framing plan into **real natural language** (Phase 3), strictly from the plan's facts.
- **Critic** — verifies every cited ref/player/number/link exists in the account/context; rejects and requests a redo on any violation; falls back to deterministic narration. The anti-hallucination guarantee.
- **Editor** — personalizes (analyst/fan register + number exposure, club/player focus, language via Azure AI Translator). Facts never change.
- **Orchestrator** — Scout → user pick → [eligible: attribute + match_context → Analyst → Storyteller ⇄ Critic → Editor] | [flagged: replay + description].

**2c. Consume Azure MCP** for Fabric/Eventhouse (stream) and Cosmos DB (accounts), with a local fallback behind the same interface so the pipeline runs if Azure isn't provisioned in time.

---

## PHASE 3 — Communication + viewer polish

**3a. Real-language narration (the core communication fix).**
- Replace templated fragments with **connected, explanatory sentences**. Current output like *"Drew Brandt (Eastport Athletic): run into space, space creation, effect +0.015"* (which says "space" three times and ends on a raw number) must become language a fan follows: *"Brandt peels off the back line into the channel — no one picks him up, and Eastport suddenly have a runner in behind."*
- **No redundancy** (don't repeat the signal as title + subtitle + gloss). **No raw number as the payload of a sentence** — weave it as meaning ("doubled the danger"), and in **Fan mode** drop the number entirely (keep the meter).
- The steps form a **connected story** (this led to that led to the chance), and where Phase 1 computed a link, the narration states it ("Brandt's run dragged the centre-back across, opening the lane Larsen ran into").
- Fan-mode final step must say more than "A half-chance" — it must explain, briefly, *why* it was a chance and what made it.
- Still 100% account/plan-bound; the Critic enforces it.

**3b. Spacebar + keyboard.**
- Spacebar toggles **play/pause** and must `preventDefault` so it does **not** scroll the page (current bug: it scrolls). Add ←/→ to step between beats. Verify space does not move the page.

**3c. Stadium / realism (GATED — ship last, must not break the demo).**
- The pitch currently floats in a black void. Add a cheap environment: simple stands / skybox backdrop, floodlighting, a low-detail crowd texture. **Never hand-model a stadium**; use a CC0 environment asset or simple procedural stands. Keep performance and the lean humanoids.
- If it slips or regresses performance, the demo must still stand without it.

## Hero-tech + dev practices

Foundry + Agent Framework (orchestration) · Azure MCP (both directions) · Fabric RTI (Scout's stream) · Azure AI Services (Translator, Content Safety on narration) · Cosmos (accounts) · ACA / Static Web Apps (hosting) · **GitHub Actions CI** · README "Agentic Architecture" section · one **ADR** (agency around a deterministic core). Each must do real work in the path.

## Non-negotiables

- **No agent authors a fact or causal link** the engine didn't compute. Defensive/context insights are computed tools, ref-bound.
- **Engine code changes only in Phase 1**, and is validated before Phase 2 wraps it.
- **Defensive/context analysis is supporting, not the main thing** — the attacking story leads and points at it.
- **The Critic enforces grounding**; unverified narration never ships.
- **Account/plan-bound throughout**; nothing on screen or in narration that isn't in the account, context, or plan.
- **Deterministic fallbacks** so the demo runs if Foundry/Azure is flaky.
- **Confirm live SDK surfaces** (Agent Framework, Foundry, Azure MCP) before wiring.

## Definition of done — self-audit (fill before reporting completion)

Table, one row per criterion, each **Pass** with evidence (test output, screenshot, or captured run):

- [ ] Headline on the former "goalkick fail" goal is now proximate and sensible; scored goals framed around the scoring team or a clearly-phrased defensive cause.
- [ ] A real defensive flaw co-leads where it is the story; defensive/context stays a supporting beat, not the main thing.
- [ ] Marking/run→space links computed where feasible; where not, facts shown adjacently with no invented link.
- [ ] Match-context facts present where data allows, with confidence; no fabricated baselines.
- [ ] Engine exposed as MCP server; a client calls each tool successfully.
- [ ] Analyst assembles a grounded framing plan (attack leads, points at defensive flaw/context) using only tool facts; a planted invented fact is rejected by the Critic.
- [ ] Narration reads as connected natural-language explanation (no templated triple-redundant fragments; no raw number as sentence payload; Fan mode jargon-free and still explanatory).
- [ ] Spacebar pauses and does NOT scroll the page; ←/→ steps.
- [ ] Stadium/environment present OR cleanly skipped with the demo intact.
- [ ] GitHub Actions CI green; README agentic section + ADR; existing tests pass; engine diff is Phase-1-only.

Any row not Pass means not done.

## How to work

Phase 1 fully (validate on several moments) → Phase 2 → Phase 3 → hero-tech/dev-practices → self-audit. Tested commits; keep each runnable; never leave the viewer or engine broken. When the self-audit is all Pass, capture an end-to-end run of the hero moment — Scout menu → pick → attribute + context → Analyst framing → Storyteller/Critic → Editor (fan + analyst) → the viewer with real narration, working spacebar, and the defensive-flaw-in-context beat — for the demo.
