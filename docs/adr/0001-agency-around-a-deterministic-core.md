# ADR 0001: Agency around a deterministic core

* Status: accepted
* Date: 2026-10-24
* Context: the agentic push (`prompts/agentic-push.md`)

## Context

Replay Room explains football moments. The hackathon rewards an agentic system (Microsoft Agent Framework,
Foundry, MCP), and the product needs language a fan follows. But a language model asked *why* a goal
happened produces fluent, confident, wrong punditry. Judges and fans spot it at once. The project's one
principle (`CLAUDE.md`) is that causality is computed deterministically and the model only puts it into words.

That leaves us with a tension. We want agents that decide things (what to tell, in what order, for whom),
but no agent may decide what is true.

## Decision

Put the agents **around** the engine, never inside it. They split the work as follows:

| Layer | What it does | Who does it |
|---|---|---|
| Facts and causal links | moments, VAEP/xT/xG, pitch control, attribution, the off-ball links (who ran past whom, which zone they left, which action used it), match-context baselines | **The engine.** Deterministic code: `attribution`, `context`. |
| Tool surface | `detect_moments`, `attribute`, `match_context`, `narrate` | **An MCP server** (`mcp_server`), with no logic of its own. |
| Selection and order | which facts to tell, in what order, with what emphasis | **Analyst** agent (Foundry model), checked against a rule plan |
| Words | connected English in an analyst register and a fan register | **Storyteller** agent (Foundry model), with the deterministic composer as its floor |
| Verification | every beat resolves to a computed record; every name, number and link in the text is in the tool output | **Critic**: code, not a model |
| Adaptation | register, club and player focus, language | **Editor** (Translator), re-checked by the Critic |
| Menu | which moments exist, described and never explained | **Scout** (deterministic) |

The rules that make this hold:

1. **Agents point; they do not author.** A framing plan is a list of ids (contribution, link, context fact,
   counterfactual). Any id that no tool returned fails to resolve, and the Critic rejects the plan. This is
   how an invented fact or link gets refused. There is a test for it: `tests/test_agents.py::test_a_planted_invented_fact_is_rejected_by_the_critic`.
2. **Links are computed or absent.** A causal connection between two players ("ran past Novak into the space
   he left") is only ever stated when `attribution.links` measured it on the tracking. Without one, the facts
   are told side by side. Outside a beat that carries a link, the Critic rejects link language ("drags",
   "runs past", "opened", "because").
3. **Each beat speaks for its own records.** A passage may name only the players in its beat's records, and
   state only numbers the tools computed, at the precision written.
4. **The Critic is code.** It cannot be argued with. A rejected model output is regenerated with the
   violations fed back, up to three times, and then the deterministic floor is used. Raw model output is never
   shown.
5. **Every agent has a deterministic floor**: the rule plan, the composer, local sources. The demo runs
   with no Foundry, no Azure and no network, and the trace says which floor was used and why.
6. **Context is supporting, never causal.** Match-context baselines come from the same match. Each carries
   its sample size and a confidence grade. Below a minimum sample there is no baseline. The plan may tell a
   context fact only where it deviates, and only after the attacking lead.

## Consequences

* The model can make the telling better (order, emphasis, phrasing) but cannot make it wrong. The worst a
  bad model run does is fall back to the rules.
* The deterministic composer carries real weight. It has to read well on its own, because offline it is the
  product. It is tested for template fragments, repetition and numbers in the fan register.
* Engine changes stay in deterministic code and are validated before the agents wrap them. Phase 1 of the
  push changed `attribution`/`context` only; phases 2 and 3 touched no engine module.
* The MCP server is a real seam. The Analyst can fetch the account and context itself through it (Agent
  Framework `MCPStdioTool`), the orchestrator can reach the engine over it (`--via-mcp`), and other MCP
  clients can use the same tools.
* Cost: two model calls per moment at most, plus their retries. Accounts and tellings are cached by content
  hash.

## Alternatives considered

* **The model reasons over raw events.** Rejected: ungrounded, unverifiable, and the punditry failure we exist
  to avoid.
* **The model writes; the Critic only checks numbers.** Rejected: names and causal connectives are where
  hallucinations hide ("Brandt dragged Novak out"). The Critic checks per beat, on names and links too.
* **No agents, only the composer.** Simpler and already grounded. But it gives up register adaptation, club
  focus and translation, and the hackathon scores the agentic layer. The composer stays as the floor.
