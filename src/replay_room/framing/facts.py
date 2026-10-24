"""Resolve a plan's beats to the computed records they point at. Lookup only: nothing is derived here.

``Facts`` indexes one moment's tool outputs (the ``CausalAccount`` and, when
there is one, its ``MatchContext``). For a beat it returns the records the beat
may talk about (``records``), the evidence it cites (``refs``) and the players
it may name (``players``). The Storyteller writes from these; the Critic checks
against them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from replay_room.contracts.causal_account import CausalAccount, Contribution, Counterfactual, Link
from replay_room.contracts.context import ContextFact, MatchContext
from replay_room.contracts.plan import Beat
from replay_room.contracts.refs import EventRef, FrameRef


class UnresolvedBeat(ValueError):
    """A beat points at a record no tool returned."""


@dataclass(frozen=True)
class Facts:
    account: CausalAccount
    context: MatchContext | None = None
    contributions: dict[str, Contribution] = field(init=False)
    links: dict[str, Link] = field(init=False)
    context_facts: dict[str, ContextFact] = field(init=False)
    counterfactuals: dict[str, Counterfactual] = field(init=False)

    def __post_init__(self) -> None:
        a = self.account
        object.__setattr__(self, "contributions", {c.contribution_id: c for c in a.contributions})
        object.__setattr__(self, "links", {link.link_id: link for link in a.links})
        object.__setattr__(self, "context_facts", {f.fact_id: f for f in self.context.facts} if self.context else {})
        object.__setattr__(self, "counterfactuals", {cf.contribution_id: cf for cf in a.counterfactuals})

    # ------------------------------------------------------------------ lookups

    def contribution(self, cid: str | None) -> Contribution:
        if cid is None or cid not in self.contributions:
            raise UnresolvedBeat(f"no contribution {cid!r} in the account")
        return self.contributions[cid]

    def link(self, lid: str | None) -> Link:
        if lid is None or lid not in self.links:
            raise UnresolvedBeat(f"no link {lid!r} in the account")
        return self.links[lid]

    def context_fact(self, fid: str | None) -> ContextFact:
        if fid is None or fid not in self.context_facts:
            raise UnresolvedBeat(f"no context fact {fid!r} in the match context")
        return self.context_facts[fid]

    def counterfactual(self, cid: str | None) -> Counterfactual:
        if cid is None or cid not in self.counterfactuals:
            raise UnresolvedBeat(f"no counterfactual for {cid!r} in the account")
        return self.counterfactuals[cid]

    @property
    def scorer_id(self) -> str:
        """Who took the terminal action: its contribution's player, else the moment's key player."""
        oid = self.account.outcome.ref.action_id
        for c in self.account.contributions:
            if c.track == "on_ball" and c.kind == "action_value" and c.evidence[0].action_id == oid:
                return c.player_id
        return self.account.moment.key_player_id

    def regain_after(self, c: Contribution) -> Contribution | None:
        """When ``c`` is the moment's turnover, the contribution of the action that won the ball (the chain's first)."""
        m = self.account.moment
        if m.turnover_event_ref is None or c.track != "on_ball" or c.evidence[0] != m.turnover_event_ref \
                or not m.chain_action_ids:
            return None
        first = m.chain_action_ids[0]
        return next((x for x in self.account.contributions
                     if x.track == "on_ball" and x.kind == "action_value" and x.evidence[0].action_id == first), None)

    def enabled_by(self, link: Link) -> Contribution | None:
        return self.contributions.get(link.enabled_contribution_id) if link.enabled_contribution_id else None

    # ------------------------------------------------------------------ per beat

    def check(self, beat: Beat) -> None:
        """Raise ``UnresolvedBeat`` unless every id the beat carries resolves, for its kind."""
        if beat.kind in ("build_up", "lead", "flaw", "punish"):
            c = self.contribution(beat.contribution_id)
            if beat.link_id is not None and (beat.kind != "flaw" or
                                             self.link(beat.link_id).defender_contribution_id != c.contribution_id):
                raise UnresolvedBeat(f"beat {beat.beat_id}: link {beat.link_id!r} is not about {c.contribution_id}")
        elif beat.kind == "link":
            self.link(beat.link_id)
        elif beat.kind == "context":
            self.context_fact(beat.context_fact_id)
        elif beat.kind == "counterfactual":
            self.counterfactual(beat.contribution_id)
        for name, value in (("contribution_id", beat.contribution_id), ("link_id", beat.link_id),
                            ("context_fact_id", beat.context_fact_id)):
            if value is None:
                continue
            ok = {"contribution_id": self.contributions, "link_id": self.links,
                  "context_fact_id": self.context_facts}[name]
            if value not in ok:
                raise UnresolvedBeat(f"beat {beat.beat_id}: {name} {value!r} does not resolve")

    def refs(self, beat: Beat) -> tuple[EventRef | FrameRef, ...]:
        """The evidence a beat cites, copied from the tool outputs (each record once, in citation order)."""
        out: list[EventRef | FrameRef] = []
        for r in self._refs(beat):
            key = (r.kind, r.action_id if r.kind == "event" else r.frame_id)
            if key not in {(x.kind, x.action_id if x.kind == "event" else x.frame_id) for x in out}:
                out.append(r)
        return tuple(out)

    def _refs(self, beat: Beat) -> tuple[EventRef | FrameRef, ...]:
        self.check(beat)
        if beat.kind == "link" or beat.link_id is not None:
            link = self.link(beat.link_id)
            own = self.contribution(beat.contribution_id).evidence if beat.contribution_id else ()
            return (*own, *link.evidence, *([link.enabled] if link.enabled else []))
        if beat.kind in ("build_up", "lead", "flaw", "punish"):
            return self.contribution(beat.contribution_id).evidence
        if beat.kind == "context":
            return self.context_fact(beat.context_fact_id).evidence
        if beat.kind == "counterfactual":
            return (self.counterfactual(beat.contribution_id).decision_frame,)
        return (self.account.outcome.ref,)

    def players(self, beat: Beat, lead: str | None = None, flaw: str | None = None) -> set[str]:
        """The players a beat may name: those its own records name (and, for the outcome, who made the chance)."""
        self.check(beat)
        out: set[str] = set()
        if beat.link_id is not None:
            link = self.link(beat.link_id)
            out |= link.player_ids
            if (used := self.enabled_by(link)) is not None:
                out.add(used.player_id)
        if beat.kind in ("build_up", "lead", "flaw", "punish"):
            c = self.contribution(beat.contribution_id)
            out |= {c.player_id} | {p for r in c.evidence if r.kind == "frame" for p in r.player_ids}
            if (won := self.regain_after(c)) is not None:
                out.add(won.player_id)
            return out
        if beat.kind == "link":
            return out
        if beat.kind == "context":
            return set()
        if beat.kind == "counterfactual":
            cf = self.counterfactual(beat.contribution_id)
            chooser = self.contribution(cf.contribution_id).player_id
            named = {p.player_id for p in self.account.participants if p.player_id in cf.chosen}
            return {chooser} | named | {a.target_player_id for a in cf.alternatives if a.target_player_id}
        out = {self.scorer_id}  # outcome
        for cid in (lead, flaw):
            if cid in self.contributions:
                out.add(self.contributions[cid].player_id)
        if self.account.headline.kind == "chance_denied":
            out.add(self.account.headline.player_id)
        return out
