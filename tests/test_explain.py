import io
import json
import os
import re

import pytest

from replay_room.explain import narrate, validate
from replay_room.explain.__main__ import main
from replay_room.explain.brief import brief
from replay_room.explain.compose import compose
from replay_room.explain.foundry import SYSTEM_PROMPT, FoundryConfig, FoundryStoryteller
from replay_room.explain.narrate import MAX_ATTEMPTS, UngroundedNarration, as_story
from replay_room.explain.schema import MODEL_OUTPUT_SCHEMA, Narration, StoryOutput
from replay_room.framing import rules_plan

HERO = "SYN-0007-big_chance_saved-3"


@pytest.fixture
def hero(all_accounts):
    return all_accounts[HERO]


@pytest.fixture
def hero_ctx(all_contexts):
    return all_contexts[HERO]


@pytest.fixture
def hero_plan(hero, hero_ctx):
    return rules_plan(hero, hero_ctx)


def _good(account, plan, context) -> dict:
    """A model-style telling that is grounded (the composer's, reworded)."""
    s = compose(account, plan, context).model_dump(mode="json")
    s["headline"] = "In short: " + s["headline"]
    return s


def _beat(plan, kind):
    return next(i for i, b in enumerate(plan.beats) if b.kind == kind)


# --------------------------------------------------------------------------- the composer reads like language


def test_every_moment_is_told_in_plain_connected_english(all_accounts, all_contexts):
    for mid, a in all_accounts.items():
        plan = rules_plan(a, all_contexts[mid])
        story = compose(a, plan, all_contexts[mid])
        assert validate(story, a, plan, all_contexts[mid]) == [], mid
        for b in story.beats:
            for text in (b.text, b.fan):
                assert "effect" not in text and "_" not in text  # no template fragments ("effect +0.015")
                assert not re.search(r"(about|roughly|nearly|most valuable)", text)  # exact, not vague
                words = text.lower().replace(",", "").replace(".", "").split()
                assert all(words.count(w) <= 2 for w in ("space",)), text  # no "space ... space ... space"
            assert not any(ch.isdigit() for ch in b.fan)


def test_the_hero_story_points_at_the_flaw_through_its_link(hero, hero_ctx, hero_plan):
    story = compose(hero, hero_plan, hero_ctx)
    flaw = story.beats[_beat(hero_plan, "flaw")]
    assert "Ferraro runs straight past Jordan Novak" in flaw.fan and "the middle of the box" in flaw.fan
    context = story.beats[_beat(hero_plan, "context")]
    assert context.fan == "Northbridge's back line is standing much higher than usual."
    assert "16.3 m from their own goal line here, against a match median of 9.2 m over 12 defending spells" in         context.text
    outcome = story.beats[_beat(hero_plan, "outcome")]  # the fan's last word explains why it was a chance
    assert outcome.fan.startswith("A goal that didn't happen: Ferraro had a good chance from the middle of the box")
    assert "it came from the space Novak gave up" in outcome.fan


def test_the_analyst_register_shows_its_ranking_exactly(hero, hero_ctx, hero_plan):
    story = compose(hero, hero_plan, hero_ctx)
    first = story.beats[0].text
    assert first.endswith("VAEP +0.087: the largest of the 8 facts that built the chance, 58% of the 0.152 xG chance "
                          "(next: +0.037).")
    cf = story.beats[-1].text
    assert "worth 0.169 against 0.097 for the pass to Ferraro, with a 77% chance of arriving" in cf


def test_a_goal_is_told_from_the_scoring_side(all_accounts, all_contexts):
    a = all_accounts["SYN-0007-goal-3"]
    story = compose(a, rules_plan(a, all_contexts["SYN-0007-goal-3"]), all_contexts["SYN-0007-goal-3"])
    assert story.headline_fan == "Larsen's interception makes the goal for Eastport, after Hale's mistake."
    assert "goalkick" not in story.headline and "goal kick" in " ".join(b.fan for b in story.beats)


# --------------------------------------------------------------------------- the Critic's text rules


def test_critic_catches_planted_hallucinations(hero, hero_ctx, hero_plan):
    good = _good(hero, hero_plan, hero_ctx)
    assert validate(good, hero, hero_plan, hero_ctx) == []
    cases = {
        "an invented player": (1, "text", "Smith keeps the move going with a pass.", "'Smith'"),
        "an invented number": (0, "text", "Sam Adeyemi's pass is worth 0.731 of the chance.", "0.731"),
        "a player from another beat": (1, "fan", "Drew Brandt passes to Novak.", "who is not in this beat's facts"),
        "a goal that never was": (_beat(hero_plan, "lead"), "fan", "Ferraro misses, and the goal is gone.",
                                  "frames it as a goal"),
        "a vague magnitude": (0, "text", "Sam Adeyemi's pass is worth about half the chance.", "vague"),
        "a bare assertion": (0, "text", "Sam Adeyemi's pass is the most valuable action.", "vague or asserted"),
        "a flipped team": (0, "text", "Northbridge's Sam Adeyemi plays the pass.", "puts Sam Adeyemi on Northbridge"),
        "an invented share": (0, "text", "Sam Adeyemi's pass: 64% of the chance.", "64%"),
        "an uncomputed link": (1, "fan", "Brandt's pass drags Novak out of position.", "asserts a causal link"),
        "a scoring claim": (_beat(hero_plan, "lead"), "fan", "Ferraro scores.", "says the chance was scored"),
        "numbers in the fan register": (0, "fan", "Sam Adeyemi's pass is worth 15% of the chance.", "fan register"),
        "jargon in the fan register": (0, "fan", "Sam Adeyemi's pass adds VAEP.", "jargon"),
    }
    for name, (i, field, text, expected) in cases.items():
        bad = json.loads(json.dumps(good))
        bad["beats"][i][field] = text
        errors = validate(bad, hero, hero_plan, hero_ctx)
        assert any(expected in e for e in errors), (name, errors)


def test_link_language_is_allowed_where_the_engine_computed_a_link(hero, hero_ctx, hero_plan):
    good = _good(hero, hero_plan, hero_ctx)
    i = _beat(hero_plan, "flaw")  # this flaw beat carries the computed run_past link
    assert hero_plan.beats[i].link_id == "LNBR-05" and "runs straight past" in good["beats"][i]["text"]
    assert validate(good, hero, hero_plan, hero_ctx) == []


def test_critic_checks_shape_and_order(hero, hero_ctx, hero_plan):
    good = _good(hero, hero_plan, hero_ctx)
    swapped = json.loads(json.dumps(good))
    swapped["beats"][0], swapped["beats"][1] = swapped["beats"][1], swapped["beats"][0]
    assert "in that order" in validate(swapped, hero, hero_plan, hero_ctx)[0]
    assert "story schema" in validate({"headline": "x"}, hero, hero_plan, hero_ctx)[0]


def test_numbers_match_at_the_precision_written(hero, hero_ctx, hero_plan):
    good = _good(hero, hero_plan, hero_ctx)
    i = _beat(hero_plan, "outcome")
    for text, ok in (("Rated 15% before the shot.", True), ("Rated 0.15 before the shot.", True),
                     ("Rated 16% before the shot.", False), ("Rated 0.2 before the shot.", False)):
        bad = json.loads(json.dumps(good))
        bad["beats"][i]["text"] = text
        assert (validate(bad, hero, hero_plan, hero_ctx) == []) is ok, text


def test_model_output_schema_is_strict():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(MODEL_OUTPUT_SCHEMA)
    assert set(MODEL_OUTPUT_SCHEMA["properties"]) == {"headline", "headline_fan", "beats"}


# --------------------------------------------------------------------------- Foundry Storyteller (mocked)


class FakeStoryteller:
    """Stands in for the Foundry Storyteller: returns queued outputs, records the briefs and feedback."""

    model = "test-model"

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def render(self, material, feedback=()):
        self.calls.append((material, list(feedback)))
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def test_foundry_telling_is_checked_and_cites_the_tool_records(hero, hero_ctx, hero_plan, tmp_path):
    fake = FakeStoryteller(_good(hero, hero_plan, hero_ctx))
    n = narrate(hero, context=hero_ctx, plan=hero_plan, renderer=fake, cache_dir=tmp_path)
    assert (n.source, n.attempts, n.model) == ("foundry", 1, "test-model@prompt-v4")
    assert n.headline.startswith("In short: ")
    (material, feedback), = fake.calls
    assert material == brief(hero, hero_plan, hero_ctx) and feedback == []
    flaw = n.beats[_beat(hero_plan, "flaw")]
    assert {r.frame_id for r in flaw.refs if r.kind == "frame"} == {2354, 2419}  # copied from the link, not the model


def test_rejected_telling_is_regenerated_with_feedback(hero, hero_ctx, hero_plan, tmp_path):
    bad = _good(hero, hero_plan, hero_ctx)
    bad["beats"][2]["text"] = "Then Smith scored."
    fake = FakeStoryteller(bad, _good(hero, hero_plan, hero_ctx))
    n = narrate(hero, context=hero_ctx, plan=hero_plan, renderer=fake, cache_dir=tmp_path)
    assert n.source == "foundry" and n.attempts == 2 and len(n.rejections) == 1
    assert any("'Smith'" in e for e in fake.calls[1][1])
    assert "Smith" not in n.headline + " ".join(b.text for b in n.beats)


def test_persistent_hallucination_falls_back_to_the_composer(hero, hero_ctx, hero_plan, tmp_path):
    bad = _good(hero, hero_plan, hero_ctx)
    bad["beats"][1]["fan"] = "Brandt's pass drags Novak out of the box."
    fake = FakeStoryteller(*[bad] * MAX_ATTEMPTS)
    n = narrate(hero, context=hero_ctx, plan=hero_plan, renderer=fake, cache_dir=tmp_path)
    assert n.source == "template" and n.attempts == MAX_ATTEMPTS and len(n.rejections) == MAX_ATTEMPTS
    assert "passed the Critic" in n.fallback_reason
    assert not (tmp_path / hero.game_id).exists()  # a fallback is not cached as the model's telling


def test_foundry_errors_and_missing_config_fall_back(hero, hero_ctx, tmp_path, monkeypatch):
    n = narrate(hero, context=hero_ctx, renderer=FakeStoryteller(ConnectionError("no route")), cache_dir=tmp_path)
    assert n.source == "template" and "ConnectionError" in n.fallback_reason
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    n = narrate(hero, context=hero_ctx, cache_dir=tmp_path)
    assert n.source == "template" and "FOUNDRY_PROJECT_ENDPOINT" in n.fallback_reason


def test_cache_replays_and_is_keyed_by_account_and_plan(hero, hero_ctx, hero_plan, tmp_path):
    fake = FakeStoryteller(_good(hero, hero_plan, hero_ctx))
    first = narrate(hero, context=hero_ctx, plan=hero_plan, renderer=fake, cache_dir=tmp_path)
    again = narrate(hero, context=hero_ctx, plan=hero_plan, renderer=fake, cache_dir=tmp_path)
    assert again == first and len(fake.calls) == 1
    no_context = rules_plan(hero)  # a different plan: not the cached telling
    fake2 = FakeStoryteller(_good(hero, no_context, None))
    narrate(hero, plan=no_context, renderer=fake2, cache_dir=tmp_path)
    assert len(fake2.calls) == 1


def test_an_unchecked_plan_is_never_told(hero, hero_ctx, hero_plan):
    bad = hero_plan.model_copy(update={"beats": hero_plan.beats[:-3] + hero_plan.beats[-2:]})  # no lead beat
    with pytest.raises(UngroundedNarration, match="refused the plan"):
        narrate(hero, "template", context=hero_ctx, plan=bad)


def test_storyteller_runs_an_agent_framework_turn(monkeypatch):
    seen = {}

    def fake_run(client, name, instructions, message, schema, temperature, tools=None):
        seen.update(name=name, instructions=instructions, message=message, schema=schema, temperature=temperature)
        return {"headline": "h", "headline_fan": "h", "beats": []}

    monkeypatch.setattr("replay_room.explain.foundry.run_structured", fake_run)
    teller = FoundryStoryteller(FoundryConfig("https://x.services.ai.azure.com/api/projects/p", "m", 0.4), client=object())
    teller.render({"beats": []}, ["fix this"])
    assert seen["name"] == "Storyteller" and seen["instructions"] == SYSTEM_PROMPT and seen["schema"] is StoryOutput
    assert "REJECTED" in seen["message"] and "fix this" in seen["message"] and seen["temperature"] == 0.4


def test_cli_template(tmp_path, hero):
    path = tmp_path / "a.json"
    path.write_text(hero.model_dump_json(), encoding="utf-8")
    out = io.StringIO()
    assert main([str(path), "--mode", "template"], out=out) == 0
    text = out.getvalue()
    assert text.startswith(f"{HERO}  [prevented]  plan: rules  source: template")
    assert "HEADLINE: A goal that didn't happen" in text and "[counterfactual]" in text
    out = io.StringIO()
    main([str(path), "--mode", "template", "--json"], out=out)
    assert Narration.model_validate(json.loads(out.getvalue())[0]).moment_id == hero.moment.moment_id


# --------------------------------------------------------------------------- live Foundry (opt-in)


@pytest.mark.skipif(os.environ.get("REPLAY_ROOM_FOUNDRY_IT") != "1",
                    reason="live Foundry test: set REPLAY_ROOM_FOUNDRY_IT=1 plus FOUNDRY_PROJECT_ENDPOINT and "
                           "FOUNDRY_MODEL_DEPLOYMENT, after az login")
def test_live_foundry_telling_is_grounded(hero, hero_ctx, hero_plan, tmp_path):
    n = narrate(hero, context=hero_ctx, plan=hero_plan, cache_dir=tmp_path)
    assert n.source == "foundry", n.fallback_reason
    assert validate(as_story(n), hero, hero_plan, hero_ctx) == []


def test_the_deep_passage_is_positional_and_checked(hero, hero_ctx, hero_plan):
    story = compose(hero, hero_plan, hero_ctx)
    flaw = story.beats[_beat(hero_plan, "flaw")]
    assert "Novak is 16.8 m higher up the pitch than their average in this phase of play (medium confidence, " \
           "12 possessions)" in flaw.deep
    assert "pitch control of the middle of the box goes from 0.33 to 0.41 over 6.5 s" in flaw.deep
    assert flaw.deep.endswith("The chance it all builds, worth 0.152 xG, is denied.")  # the outcome's framing
    assert "Novak is much higher up the pitch than usual" in flaw.deep_fan and not re.search(r"\d", flaw.deep_fan)
    bad = json.loads(json.dumps(_good(hero, hero_plan, hero_ctx)))
    i = _beat(hero_plan, "flaw")
    bad["beats"][i]["deep"] = flaw.deep.replace("16.8 m", "6.2 m")  # an invented deviation
    assert any("6.2" in e for e in validate(bad, hero, hero_plan, hero_ctx))


def test_a_beat_draws_only_its_own_marking(all_accounts, all_contexts):
    from replay_room.explain.compose import beat_positions
    from replay_room.framing import Facts

    a, ctx = all_accounts["SYN-0007-turnover_to_shot-1"], all_contexts["SYN-0007-turnover_to_shot-1"]
    plan, facts = rules_plan(a, ctx), Facts(a, ctx)
    marking = {b.contribution_id: beat_positions(facts, ctx, b, facts.players(b))[2] for b in plan.beats
               if b.contribution_id}
    assert marking["sNBR-02"] is not None and not marking["sNBR-02"].held  # Sam Brandt loses Adeyemi: drawn red
    assert marking["a12"] is None  # Novak's lost pass is on-ball: his off-ball marking is another beat's evidence
