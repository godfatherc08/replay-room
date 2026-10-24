import io
import json

import pytest

from replay_room.agents.__main__ import main
from replay_room.agents.analyst import Analyst, PlanProposal, analyst_brief
from replay_room.agents.critic import Critic
from replay_room.agents.editor import Editor
from replay_room.agents.engine import InProcessEngine
from replay_room.agents.orchestrator import Orchestrator
from replay_room.agents.scout import Scout, describe
from replay_room.agents.sources import FixtureStream, LocalAccountStore, stream_from_env, store_from_env
from replay_room.explain import narrate
from replay_room.framing import rules_plan
from replay_room.mcp_server.service import EngineService

HERO = "SYN-0007-big_chance_saved-3"


@pytest.fixture(scope="module")
def engine(match, fixture_dir):
    return InProcessEngine(svc=EngineService(fixture_dir, match=match))


def _proposal(plan, **changes) -> dict:
    beats = [b.model_dump(exclude={"beat_id"}) for b in plan.beats]
    return {"lead_contribution_id": plan.lead_contribution_id, "flaw_contribution_id": plan.flaw_contribution_id,
            "beats": beats, **changes}


# --------------------------------------------------------------------------- Analyst


def test_analyst_plan_from_a_model_is_checked(all_accounts, all_contexts):
    a, ctx = all_accounts[HERO], all_contexts[HERO]
    floor = rules_plan(a, ctx)
    reordered = _proposal(floor)
    reordered["beats"] = reordered["beats"][1:2] + reordered["beats"][:1] + reordered["beats"][2:]  # its own order
    calls = []

    def propose(account, context, feedback):
        calls.append(list(feedback))
        return reordered

    plan, report = Analyst(proposer=propose).plan(a, ctx)
    assert (plan.source, report.source, report.attempts) == ("foundry", "foundry", 1)
    assert [b.contribution_id for b in plan.beats[:2]] == ["a159", "a157"]  # the model chose; the Critic agreed
    PlanProposal.model_validate(reordered)


def test_a_planted_invented_fact_is_rejected_by_the_critic(all_accounts, all_contexts):
    a, ctx = all_accounts[HERO], all_contexts[HERO]
    floor = rules_plan(a, ctx)
    invented = _proposal(floor)
    invented["beats"].insert(0, {"kind": "link", "emphasis": "support", "contribution_id": None,
                                 "link_id": "L-brandt-dragged-novak", "context_fact_id": None})
    feedbacks = []

    def propose(account, context, feedback):
        feedbacks.append(list(feedback))
        return invented

    plan, report = Analyst(proposer=propose).plan(a, ctx)
    assert report.attempts == 3 and len(report.rejections) == 3  # rejected every time, with the reason fed back
    assert any("L-brandt-dragged-novak" in e for e in report.rejections[0])
    assert feedbacks[1] == report.rejections[0]
    assert plan == floor and report.source == "rules" and "passed the Critic" in report.fallback_reason
    assert "L-brandt-dragged-novak" not in plan.model_dump_json()


def test_analyst_falls_back_without_foundry(all_accounts, all_contexts, monkeypatch):
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    plan, report = Analyst().plan(all_accounts[HERO], all_contexts[HERO])
    assert plan.source == "rules" and "FOUNDRY_PROJECT_ENDPOINT" in report.fallback_reason

    def broken(*_):
        raise TimeoutError("model timed out")

    plan, report = Analyst(proposer=broken).plan(all_accounts[HERO], all_contexts[HERO])
    assert plan.source == "rules" and "TimeoutError" in report.fallback_reason


def test_analyst_brief_is_tool_output_only(all_accounts, all_contexts):
    a, ctx = all_accounts[HERO], all_contexts[HERO]
    b = analyst_brief(a, ctx)
    assert {c["contribution_id"] for c in b["contributions"]} == {c.contribution_id for c in a.contributions}
    assert {k["link_id"] for k in b["links"]} == {k.link_id for k in a.links}
    assert {f["fact_id"] for f in b["context"]} == {f.fact_id for f in ctx.facts}


# --------------------------------------------------------------------------- Scout


def test_scout_builds_the_described_menu_in_match_order(engine, fixture_dir):
    scout = Scout(engine, FixtureStream(fixture_dir))
    menu = scout.watch()
    assert scout.events_seen == 279 and len(menu) == 10 and all(m.explainable for m in menu)
    assert [(m.period_id, m.t) for m in menu] == sorted((m.period_id, m.t) for m in menu)
    hero = next(m for m in menu if m.moment_id == HERO)
    assert hero.description == "04:03 · Big chance for Eastport Athletic: Jordan Ferraro is denied."


def test_scout_describes_but_never_explains_flagged_moments_and_red_cards(engine):
    class Feed:
        name = "test feed"

        def events(self):
            yield {"period": 1, "t": 1.0, "type": "Pass"}
            yield {"period": 1, "t": 2.0, "type": "Foul", "team": "NBR", "player": "Sam Brandt", "card": "red"}

    menu = Scout(engine, Feed()).watch()
    red = [m for m in menu if m.type == "red_card"]
    assert len(red) == 1 and not red[0].explainable and red[0].moment_id is None
    assert "discipline" in red[0].why_not_explained
    offside = describe({"type": "offside", "team": "Northbridge FC", "player": "Drew Costa", "match_clock": "10:00"})
    assert offside == "10:00 · Offside against Northbridge FC (Drew Costa)."


# --------------------------------------------------------------------------- Editor


def test_editor_registers_and_focus(all_accounts, all_contexts):
    a, ctx = all_accounts["SYN-0007-goal-1"], all_contexts["SYN-0007-goal-1"]
    plan = rules_plan(a, ctx)
    n = narrate(a, "template", context=ctx, plan=plan)
    ed = Editor()
    fan = ed.edit(n, a, plan, ctx, "fan")
    analyst = ed.edit(n, a, plan, ctx, "analyst")
    assert [b.text for b in fan.beats] == [b.fan for b in n.beats]
    assert [b.text for b in analyst.beats] == [b.text for b in n.beats]
    assert not any(ch.isdigit() for b in fan.beats for ch in b.text)
    against = ed.edit(n, a, plan, ctx, "fan", focus_team_id="NBR", focus_player_id="NBR-05")
    assert against.perspective == "against" and against.headline == "What went wrong for Northbridge: the space Novak gave up."
    highlighted = [b.beat_id for b in against.beats if b.highlighted]
    assert highlighted == [b.beat_id for b in plan.beats if b.kind in ("flaw", "outcome")]
    assert ed.edit(n, a, plan, ctx, "fan", focus_team_id="EPA").headline == n.headline_fan


def test_editor_translation_is_checked_and_falls_back(all_accounts, all_contexts, monkeypatch):
    a, ctx = all_accounts["SYN-0007-goal-1"], all_contexts["SYN-0007-goal-1"]
    plan = rules_plan(a, ctx)
    n = narrate(a, "template", context=ctx, plan=plan)
    monkeypatch.delenv("AZURE_TRANSLATOR_KEY", raising=False)
    ed = Editor().edit(n, a, plan, ctx, "analyst", language="fr")
    assert ed.language == "en" and not ed.translated and "AZURE_TRANSLATOR_KEY" in ed.fallback_reason

    class FakeTranslator:
        available, reason = True, ""

        def __init__(self, keep_numbers):
            self.keep = keep_numbers

        def translate(self, texts, to):
            return [f"[{to}] {t}" if self.keep else f"[{to}] {t}".replace("22%", "99%") for t in texts]

    ok = Editor(translator=FakeTranslator(True)).edit(n, a, plan, ctx, "analyst", language="fr")
    assert ok.translated and ok.language == "fr" and ok.headline.startswith("[fr] ")
    tampered = Editor(translator=FakeTranslator(False)).edit(n, a, plan, ctx, "analyst", language="fr")
    assert not tampered.translated and "numbers changed" in tampered.fallback_reason


def test_critic_screen_reports_when_not_configured(monkeypatch):
    monkeypatch.delenv("CONTENT_SAFETY_ENDPOINT", raising=False)
    flagged, why = Critic().screen(["A clean sentence."])
    assert flagged == [] and "CONTENT_SAFETY_ENDPOINT" in why


# --------------------------------------------------------------------------- Orchestrator + sources


def test_orchestrator_runs_the_whole_chain(engine, fixture_dir, monkeypatch):
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    orch = Orchestrator(engine, FixtureStream(fixture_dir), mode="foundry")
    result = orch.explain(HERO, focus_player_id="EPA-11")
    agents = [s.agent for s in orch.trace]
    for name in ("Scout", "User", "Engine", "Analyst", "Critic", "Storyteller", "Editor"):
        assert name in agents
    assert agents.index("Scout") < agents.index("Analyst") < agents.index("Storyteller") < agents.index("Editor")
    checks = {s.action: s.detail for s in orch.trace if s.agent == "Critic"}
    assert checks["plan check"] == "passed" and checks["story check"].startswith("passed")
    assert set(result.editions) == {"analyst", "fan"} and result.narration.source == "template"
    assert any(b.highlighted for b in result.editions["fan"].beats)


def test_sources_fall_back_locally(fixture_dir, monkeypatch):
    monkeypatch.delenv("EVENTHOUSE_CLUSTER_URI", raising=False)
    monkeypatch.delenv("COSMOS_ACCOUNT", raising=False)
    picked = stream_from_env(fixture_dir)
    assert isinstance(picked.source, FixtureStream) and "EVENTHOUSE_CLUSTER_URI" in picked.fallback_reason
    picked = store_from_env()
    assert isinstance(picked.source, LocalAccountStore) and "COSMOS_ACCOUNT" in picked.fallback_reason


def test_cli_prints_the_end_to_end_run(monkeypatch):
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    out = io.StringIO()
    assert main(["--moment", "SYN-0007-goal-1", "--focus-team", "NBR"], out=out) == 0
    text = out.getvalue()
    assert "SCOUT MENU" in text and "TRACE" in text and "FAN EDITION (en, against)" in text
    assert "What went wrong for Northbridge" in text
    out = io.StringIO()
    main(["--moment", "SYN-0007-goal-1", "--json"], out=out)
    assert json.loads(out.getvalue())["plan"]["lead_contribution_id"] == "a35"
