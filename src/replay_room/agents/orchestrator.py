"""Orchestrator: Scout -> pick -> [explainable: attribute + match_context -> Analyst -> Storyteller <-> Critic -> Editor]
| [flagged: replay + description].

Every hop is recorded in ``trace`` (agent, what it did, what came back) so the
run can be shown end to end. The engine is reached through ``agents.engine``
(in-process or over its MCP server); the stream and account store through
``agents.sources`` (Azure via Azure MCP, or local).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from replay_room.agents.analyst import Analyst, AnalystReport
from replay_room.agents.critic import Critic
from replay_room.agents.editor import Edition, Editor, Register
from replay_room.agents.engine import Engine
from replay_room.agents.scout import MenuItem, Scout
from replay_room.agents.sources import Stream
from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.context import MatchContext
from replay_room.contracts.plan import FramingPlan
from replay_room.explain.narrate import narrate
from replay_room.explain.schema import Narration


@dataclass(frozen=True)
class Step:
    agent: str
    action: str
    detail: str


@dataclass
class Explained:
    item: MenuItem
    account: CausalAccount | None = None
    context: MatchContext | None = None
    plan: FramingPlan | None = None
    analyst: AnalystReport | None = None
    narration: Narration | None = None
    editions: dict[str, Edition] = field(default_factory=dict)
    flagged_safety: list[str] = field(default_factory=list)


class Storyteller:
    """Tells a checked plan: the Foundry model (Critic-gated, with retries) or the composer."""

    def __init__(self, mode: Literal["foundry", "template"] = "foundry", renderer=None):
        self.mode = mode
        self.renderer = renderer

    def tell(self, account: CausalAccount, plan: FramingPlan, context: MatchContext | None) -> Narration:
        return narrate(account, self.mode, context=context, plan=plan, renderer=self.renderer)


class Orchestrator:
    def __init__(self, engine: Engine, stream: Stream, *, mode: Literal["foundry", "template"] = "foundry",
                 analyst: Analyst | None = None, storyteller: Storyteller | None = None,
                 critic: Critic | None = None, editor: Editor | None = None):
        self.engine = engine
        self.stream = stream
        self.analyst = analyst or Analyst("foundry" if mode == "foundry" else "rules",
                                          match_dir=getattr(engine, "match_dir", None))
        self.storyteller = storyteller or Storyteller(mode)
        self.critic = critic or Critic()
        self.editor = editor or Editor(critic=self.critic)
        self.trace: list[Step] = []
        self.menu: list[MenuItem] = []

    def log(self, agent: str, action: str, detail: str) -> None:
        self.trace.append(Step(agent, action, detail))

    def scout(self) -> list[MenuItem]:
        scout = Scout(self.engine, self.stream)
        self.menu = scout.watch()
        explained = sum(m.explainable for m in self.menu)
        self.log("Scout", f"watched {scout.events_seen} feed events from {self.stream.name}",
                 f"menu of {len(self.menu)} moments: {explained} explainable, {len(self.menu) - explained} described only")
        return self.menu

    def explain(self, moment_id: str, registers: tuple[Register, ...] = ("analyst", "fan"), language: str = "en",
                focus_team_id: str | None = None, focus_player_id: str | None = None) -> Explained:
        if not self.menu:
            self.scout()
        item = next((m for m in self.menu if m.moment_id == moment_id), None)
        if item is None:
            raise KeyError(f"{moment_id} is not on the Scout's menu")
        self.log("User", "picked", item.description)
        if not item.explainable:
            self.log("Orchestrator", "flagged moment: replay + description only", item.why_not_explained or "")
            return Explained(item=item)

        account = self.engine.attribute(moment_id)
        self.log("Engine", f"attribute ({self.engine.name})",
                 f"headline {account.headline_contribution_id}, supporting {account.supporting_contribution_id}, "
                 f"{len(account.contributions)} facts, {len(account.links)} computed links")
        context = self.engine.match_context(moment_id)
        self.log("Engine", f"match_context ({self.engine.name})",
                 ", ".join(f"{f.kind} {'deviates' if f.deviates else 'typical'} ({f.confidence})" for f in context.facts)
                 + (f"; no baseline for {', '.join(k for k, _ in context.insufficient)}" if context.insufficient else ""))

        plan, report = self.analyst.plan(account, context)
        self.log("Analyst", f"framing plan ({report.source}, {report.attempts} model attempts)",
                 " > ".join(f"{b.kind}:{b.contribution_id or b.link_id or b.context_fact_id or ''}".rstrip(":")
                            for b in plan.beats)
                 + (f"  [fallback: {report.fallback_reason}]" if report.fallback_reason else ""))
        for k, errors in enumerate(report.rejections, start=1):
            self.log("Critic", f"rejected Analyst plan {k}", "; ".join(errors))
        refused = self.critic.review_plan(plan, account, context)
        self.log("Critic", "plan check", "passed" if not refused else "; ".join(refused))
        if refused:
            raise RuntimeError(f"plan refused: {refused}")

        narration = self.storyteller.tell(account, plan, context)
        self.log("Storyteller", f"told by {narration.source}"
                 + (f" ({narration.model}, attempt {narration.attempts})" if narration.source == "foundry" else ""),
                 narration.headline + (f"  [fallback: {narration.fallback_reason}]" if narration.fallback_reason else ""))
        for k, errors in enumerate(narration.rejections, start=1):
            self.log("Critic", f"rejected Storyteller telling {k}", "; ".join(errors))
        from replay_room.explain.narrate import as_story

        story_errors = self.critic.review_story(as_story(narration), account, plan, context)
        self.log("Critic", "story check", "passed: every name, number and link is in the tool outputs"
                 if not story_errors else "; ".join(story_errors))
        if story_errors:
            raise RuntimeError(f"story refused: {story_errors}")
        flagged, why = self.critic.screen([narration.headline, *(b.text for b in narration.beats)])
        self.log("Critic", "content safety", f"flagged {flagged}" if flagged else ("clean" if why is None else
                                                                                   f"skipped: {why}"))

        out = Explained(item=item, account=account, context=context, plan=plan, analyst=report, narration=narration,
                        flagged_safety=flagged)
        for register in registers:
            ed = self.editor.edit(narration, account, plan, context, register, language, focus_team_id, focus_player_id)
            out.editions[register] = ed
            self.log("Editor", f"{register} edition ({ed.language}, perspective {ed.perspective})",
                     ed.headline + (f"  [note: {ed.fallback_reason}]" if ed.fallback_reason else ""))
        return out
