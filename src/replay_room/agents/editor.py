"""Editor: personalizes a validated telling. Register, club or player focus, language. The facts never change.

* **register**: ``analyst`` takes each beat's analyst text (which may weave in a
  computed number); ``fan`` takes its fan text (no numbers, no jargon);
* **club focus**: the headline is told from that club's side (the composer's
  ``perspective_headline``, re-checked by the Critic); beats are unchanged;
* **player focus**: the beats whose records involve the player are marked
  ``highlighted`` (the viewer emphasizes them); nothing is added about the player;
* **language**: Azure AI Translator, when configured; the Critic then checks
  each translated passage kept its numbers and names, and a failed check keeps
  the English. Not configured: English, with the reason recorded.
"""

from __future__ import annotations

from typing import Literal

from replay_room.agents.azure import AzureUnavailable, Translator
from replay_room.agents.critic import Critic
from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.context import MatchContext
from replay_room.contracts.plan import FramingPlan
from replay_room.contracts.refs import _Model
from replay_room.explain.compose import perspective_headline
from replay_room.explain.schema import Narration
from replay_room.explain.validate import Grounds, check_text
from replay_room.framing.facts import Facts

Register = Literal["analyst", "fan"]


class EditedBeat(_Model):
    beat_id: str
    text: str
    highlighted: bool = False


class Edition(_Model):
    moment_id: str
    mode: Register  # the register: analyst or fan
    language: str = "en"
    focus_team_id: str | None = None
    focus_player_id: str | None = None
    perspective: Literal["neutral", "for", "against"] = "neutral"
    headline: str
    beats: tuple[EditedBeat, ...]
    translated: bool = False
    fallback_reason: str | None = None


class Editor:
    def __init__(self, translator: Translator | None = None, critic: Critic | None = None):
        self.translator = translator or Translator()
        self.critic = critic or Critic()

    def edit(self, narration: Narration, account: CausalAccount, plan: FramingPlan, context: MatchContext | None,
             register: Register = "fan", language: str = "en", focus_team_id: str | None = None,
             focus_player_id: str | None = None) -> Edition:
        if narration.moment_id != account.moment.moment_id:
            raise ValueError("the narration is for another moment")
        facts = Facts(account, context)
        headline = narration.headline if register == "analyst" else narration.headline_fan
        perspective = "neutral"
        reason = None
        if focus_team_id is not None:
            if focus_team_id not in {t.team_id for t in account.teams}:
                raise ValueError(f"{focus_team_id} is not in this moment")
            perspective = "for" if focus_team_id == account.outcome.beneficiary_team_id else "against"
            if perspective == "against":
                line = perspective_headline(account, plan, context, focus_team_id)
                players = {p for b in plan.beats if b.kind in ("lead", "flaw", "punish", "outcome")
                           for p in facts.players(b, plan.lead_contribution_id, plan.flaw_contribution_id)}
                errors = check_text(line, Grounds(account, context), "club headline", players, fan=register == "fan")
                if errors:
                    reason = f"club headline refused by the Critic: {errors}"
                else:
                    headline = line
        beats = []
        for b in narration.beats:
            beat = next(x for x in plan.beats if x.beat_id == b.beat_id)
            on = focus_player_id is not None and focus_player_id in facts.players(
                beat, plan.lead_contribution_id, plan.flaw_contribution_id)
            beats.append(EditedBeat(beat_id=b.beat_id, text=b.text if register == "analyst" else b.fan, highlighted=on))
        edition = Edition(moment_id=narration.moment_id, mode=register, focus_team_id=focus_team_id,
                          focus_player_id=focus_player_id, perspective=perspective, headline=headline,
                          beats=tuple(beats), fallback_reason=reason)
        if language == "en":
            return edition
        return self.translate(edition, language, {p.name for p in account.participants}
                              | {t.name for t in account.teams})

    def translate(self, edition: Edition, language: str, names: set[str]) -> Edition:
        source = [edition.headline, *(b.text for b in edition.beats)]
        if not self.translator.available:
            return edition.model_copy(update={"fallback_reason": self.translator.reason})
        try:
            out = self.translator.translate(source, language)
        except (AzureUnavailable, OSError, ValueError) as e:
            return edition.model_copy(update={"fallback_reason": f"translation failed: {e}"})
        errors = self.critic.review_edition(source, out, names)
        if errors:
            return edition.model_copy(update={"fallback_reason": f"translation refused by the Critic: {errors}"})
        beats = tuple(b.model_copy(update={"text": t}) for b, t in zip(edition.beats, out[1:]))
        return edition.model_copy(update={"language": language, "headline": out[0], "beats": beats,
                                          "translated": True})
