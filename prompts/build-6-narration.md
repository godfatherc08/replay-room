# Build 6 Kickoff Prompt — Grounded Explanation Renderer (Foundry-first)

> Paste into a Claude Code session in the `replay-room` repo, after Build 4 (attribution) is green; can run in parallel with Build 5. Lives at `prompts/build-6-narration.md`.
>
> **This is the ONLY stage that calls a language model.** It is the whole reason the deterministic wall exists. The model narrates the `CausalAccount` and nothing else. Read everything before writing.

---

You are the lead engineer on **Replay Room**. The engine computes the causal account; Build 6 turns it into language a human reads — and into a timed, machine-readable overlay a broadcast could render. The model is a **renderer, not a reasoner**: correctness already lives in Build 4, so Build 6's job is fluency *without introducing a single fact that isn't in the account*. Foundry is the judged integration and the riskiest piece to leave late, so prove it first.

## Step 1 — Read, in this order

1. `CLAUDE.md` — the governing principle. Build 6 is **explain/render**; it is the one place a model is allowed, and only to verbalize stage-4 output.
2. `REPLAY_ROOM_TECHNICAL_SPEC.md` — §6 (grounded generation) and §0's deterministic/LLM wall.
3. **The input you consume — only this:** the `CausalAccount` JSON (`data/accounts/...`): `contributions[]` (each with `ref`, `player`, `team`, `signal`, signed `value`, `role`), `headline_cause`, `outcome` (`ref`, `value`, `realized`, `beneficiary_team`), `counterfactual` (if present), `evidence`. Every fact already has a label, a team, a signed effect, the numbers behind it, and a record to cite. **If `outcome.realized` is false, the story is a goal that didn't happen and the headline is what stopped it.**
4. Current Microsoft Foundry usage (verify against docs — this changes): `pip install azure-ai-projects`; `AIProjectClient`; Foundry Agent Service (Responses API, GA); a Foundry model that supports **structured outputs**; Entra ID / Entra Agent ID for auth. Confirm the current SDK surface before coding rather than trusting any snippet here.

## Step 2 — State the contract (write it back, ~10 lines)

- **The model sees the account and only the account.** No raw events, no tracking, no match knowledge beyond what the account carries. The system prompt forbids introducing any event, player, team, cause, position, or number not present in the account.
- **Every output sentence cites a ref** (`event_id` or `frame`) drawn from the account, carried through as structured data.
- **Grounding is enforced after generation, not assumed.** A validator checks every cited ref exists in the account and every named player/team appears in the account; any violation → reject and regenerate (bounded retries) → else fall back to the deterministic renderer.
- **Prevented vs realized** changes the story, not the mechanism: realized → what created it + what failed to stop it (headline); prevented → what built the chance + what stopped it (headline = the preventing action), framed as a goal that didn't happen.
- Don't code until written.

## Step 3 — The mission: Build 6

Deliver, in this order — Foundry path first (the judged, riskiest integration), validator as the hard gate, thin fallback as insurance.

Deliverables:

1. **Narration schema** (`src/replay_room/explain/schema.py`): the structured output the model must return — an ordered list of `{text, ref, metric, role}` sentences plus a one-line `headline_text`, and a `timed_overlay` view: each sentence stamped with the **time of its cited event/frame** so it could drive synchronized on-screen graphics (spec stage d: "timed and machine-readable enough to be rendered as overlays"). JSON-schema-constrained.

2. **Foundry renderer** (`src/replay_room/explain/foundry.py`) — *build and prove this first:*
   - Connect via `AIProjectClient` / Foundry Agent Service with Entra auth; pick a Foundry model with structured outputs.
   - **System prompt:** you are a renderer; narrate ONLY the provided account; never introduce a fact, player, team, number, or cause not in it; one sentence per contribution in rank order, headline first; carry each `ref` into its sentence; honor `outcome.realized` for the framing. Low temperature.
   - **Structured output** against the narration schema so the model returns `{text, ref, metric, role}` per sentence, pinned to the account.
   - A tiny end-to-end smoke path: real account in → narration out → printed. This is the integration proof; get it working before anything below.

3. **Ref-validator** (`src/replay_room/explain/validate.py`) — *the hard anti-hallucination gate:* for a generated narration, assert every `ref` exists in the account's events/frames, every named player/team appears in the account, and no numeric claim contradicts the account's values (tolerance). On failure, regenerate up to N times; if still failing, drop to the deterministic fallback. **This is what makes "the model only narrates" a guarantee, not a hope** — never ship narration that hasn't passed it.

4. **Deterministic fallback** (`src/replay_room/explain/template.py`) — *thin, insurance only:* assemble one sentence per contribution directly from the account's fields (label + player + team + signed effect + ref), headline first, realized/prevented aware. Grounded by construction; no model. It is the demo safety net if Foundry is unavailable mid-demo, and the floor the validator falls back to. Keep it minimal — do not over-polish; the Foundry output is the primary artifact.

5. **`narrate(account, mode="foundry"|"template")` → validated narration + timed overlay**: single entry point Build 7 calls. Caches outputs per account (model output isn't bit-deterministic; cache so the demo and tests are stable).

6. **CLI + tests**: `python -m replay_room.explain data/accounts/<game>/<moment>.json` prints the narration (headline + cited sentences) and the timed overlay JSON. `pytest`:
   - **validator catches a planted hallucination** — a narration citing a non-existent ref or player is rejected (test the gate directly, with a stub narration).
   - **template is always grounded** — every sentence's ref exists in the account; prevented accounts framed as prevented.
   - **schema** — output conforms; each sentence carries a valid ref and a timestamp.
   - **realized vs prevented** — `big_chance_saved` narration leads with the stopping action and frames a goal that didn't happen.
   - Mock the Foundry call in unit tests (don't hit the network in CI); keep one opt-in integration test behind an env flag for the real endpoint.

## Non-negotiables

- **The model narrates the account and nothing else.** No new facts, ever. Enforced by the validator, not just the prompt.
- **Every sentence cites a real ref.** No ref, or a ref not in the account → rejected.
- **Correctness is upstream.** Build 6 does not re-rank, re-attribute, or compute metrics. If the account is wrong, fix Build 4, not the prose.
- **Honor `outcome.realized`.** Never narrate a goal that didn't happen as if it did.
- **Validated or fallback — never raw model output.** Nothing reaches Build 7 or the viewer unvalidated.
- **Confirm the current Foundry SDK surface from docs** before relying on any API shape.

## Definition of done (the Build 6 gate)

- The **Foundry renderer** produces structured, account-grounded narration for the fixture accounts (integration proven end-to-end).
- The **validator** rejects any narration citing a ref/player/number not in the account, with bounded regeneration and a fallback.
- The **deterministic fallback** always produces grounded narration with no model.
- `narrate(...)` returns validated narration + a timed overlay; prevented outcomes framed correctly; outputs cached.
- Tests pass (validator-catches-hallucination test included); build committed.

## How to work

Write the contract (Step 2) first. Then, in order: **narration schema → Foundry renderer + integration smoke (prove it) → ref-validator (the gate) → thin deterministic fallback → `narrate` entry point + cache → CLI/tests**. Keep each commit runnable. When the gate is met, print the Foundry narration for the hero moment (the `big_chance_saved` with the counterfactual) next to its account so the grounding is visibly 1:1, and hand off to **Build 7 (personalization)** — analyst mode assembles the account/overlay deterministically, casual mode uses this narration; both are view-transforms over the one account, plus language on top.
