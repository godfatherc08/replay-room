import copy
import io
import json
import os
import warnings
from types import SimpleNamespace

import pytest

from replay_room.attribution.engine import attribute_match
from replay_room.explain import narrate, validate
from replay_room.explain.__main__ import main
from replay_room.explain.brief import brief, narration_order
from replay_room.explain.foundry import SYSTEM_PROMPT, FoundryConfig, FoundryRenderer
from replay_room.explain.narrate import MAX_ATTEMPTS
from replay_room.explain.schema import MODEL_OUTPUT_SCHEMA, ModelNarration, Narration
from replay_room.explain.template import render_template


@pytest.fixture(scope="module")
def accounts(match):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        return {a.moment.moment_id: a for a in attribute_match(match)}


@pytest.fixture
def hero(accounts):
    return accounts["SYN-0007-big_chance_saved-3"]


def _good(account) -> dict:
    """A model-style narration that is grounded (built from the template, reworded)."""
    n = render_template(account).model_dump(mode="json")
    n["headline_text"] = "In short: " + n["headline_text"]
    return n


class FakeClient:
    """Stands in for the Foundry OpenAI client: returns queued outputs, records requests."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return SimpleNamespace(output_text=json.dumps(out), status="completed")


def _renderer(*outputs, temperature=0.2):
    client = FakeClient(outputs)
    return FoundryRenderer(FoundryConfig("https://example.services.ai.azure.com/api/projects/p", "test-model",
                                         temperature), client), client


# --------------------------------------------------------------------------- the gate


def test_validator_catches_planted_hallucinations(hero):
    good = _good(hero)
    assert validate(good, hero) == []
    planted = {
        "ref not in the account": ("ref", "event:9999", "cites 'event:9999'"),
        "ref of another contribution": ("ref", "frame:2416", "cites 'frame:2416'"),
        "invented player id": ("text", "EPA-99 played it through.", "EPA-99, who is not in the account"),
        "invented player name": ("text", "Marcus Rashford played it through.", "names 'Marcus'"),
        "invented team": ("text", "Arsenal never recovered.", "names 'Arsenal'"),
        "invented number": ("text", "It was worth 0.42.", "states 0.42"),
        "wrong metric": ("metric", {"name": "effect", "value": 0.2}, "effect=0.2"),
        "unknown metric": ("metric", {"name": "speed_kmh", "value": 30.0}, "metric 'speed_kmh'"),
        "goal that wasn't": ("text", "He scored from close range.", "says the chance was scored"),
        "wrong role": ("role", "assist", "role 'assist'"),
    }
    for name, (field, value, message) in planted.items():
        bad = copy.deepcopy(good)
        bad["sentences"][1][field] = value
        errors = validate(bad, hero)
        assert any(message in e for e in errors), (name, errors)


def test_validator_checks_shape_and_order(hero):
    good = _good(hero)
    swapped = copy.deepcopy(good)
    swapped["sentences"][0], swapped["sentences"][1] = swapped["sentences"][1], swapped["sentences"][0]
    assert any("in that order" in e for e in validate(swapped, hero))
    short = copy.deepcopy(good)
    short["sentences"].pop()
    assert any("in that order" in e for e in validate(short, hero))
    assert any("narration schema" in e for e in validate({"headline_text": "x"}, hero))
    bad_head = copy.deepcopy(good)
    bad_head["headline_text"] = "Liverpool would have won it 3-1."
    errors = validate(bad_head, hero)
    assert any("headline" in e and "'Liverpool'" in e for e in errors) and any("states 3" in e for e in errors)


def test_scoring_language_on_a_chance_that_did_not_score(hero):
    def errs(text):
        return [e for e in validate({**_good(hero), "headline_text": text}, hero) if "scored" in e]
    for claim in ("He scored from close range.", "It was converted.", "The shot went into the net."):
        assert errs(claim), claim
    for fine in ("The miss denied a scoring chance.", "The shot didn't go into the net.",
                 "It was never scored.", "He failed to convert, and it was not netted."):
        assert errs(fine) == [], fine


def test_numbers_match_at_the_precision_written(hero):
    v = hero.outcome.value  # 0.152
    for text in (f"worth {v:.3f}", f"worth {v:.2f}", f"worth {100 * v:.0f}%", f"worth {100 * v:.1f}%"):
        assert validate({**_good(hero), "headline_text": text}, hero) == [], text
    for text in ("worth 0", "worth 0.2", "worth 0.9", "worth 16%"):
        assert validate({**_good(hero), "headline_text": text}, hero), text


# --------------------------------------------------------------------------- the floor


def test_template_is_always_grounded(accounts):
    for a in accounts.values():
        n = narrate(a, "template")
        assert n.source == "template" and validate(render_template(a), a) == []
        assert [s.contribution_id for s in n.sentences] == narration_order(a)
        cited = {r for c in a.contributions for r in c.evidence}
        assert all(s.ref in cited for s in n.sentences)


def test_prevented_leads_with_what_stopped_it(accounts):
    for a in accounts.values():
        n = narrate(a, "template")
        assert n.framing == ("realized" if a.outcome.realized else "prevented")
        assert n.sentences[0].contribution_id == a.headline_contribution_id and n.sentences[0].headline
        if not a.outcome.realized:
            assert n.headline_text.startswith("A goal that didn't happen")
            assert a.headline.kind == "chance_denied" and n.sentences[0].role == "prevention"
    saved = narrate(accounts["SYN-0007-big_chance_saved-1"], "template")
    assert "denied by" in saved.headline_text and "keeper save" in saved.headline_text


def test_schema_refs_and_timestamps(hero):
    n = narrate(hero, "template")
    assert Narration.model_validate_json(n.model_dump_json()) == n
    for s in n.sentences:
        assert s.t == (s.ref.time_seconds if s.ref.kind == "event" else s.ref.timestamp)
    cues = n.timed_overlay
    assert sorted(c.sentence_index for c in cues) == list(range(len(n.sentences)))
    assert [c.t_start for c in cues] == sorted(c.t_start for c in cues)
    assert all(c.t_end > c.t_start for c in cues)
    for c in cues:
        s = n.sentences[c.sentence_index]
        assert (c.frame_id is not None) == (s.ref.kind == "frame") and c.text == s.text


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


# --------------------------------------------------------------------------- Foundry path (mocked)


def test_foundry_request_carries_only_the_account(hero, tmp_path):
    renderer, client = _renderer(_good(hero))
    n = narrate(hero, renderer=renderer, cache_dir=tmp_path)
    assert (n.source, n.attempts, n.model) == ("foundry", 1, "test-model@prompt-v1")
    assert n.headline_text.startswith("In short: ")
    (req,) = client.requests
    assert req["instructions"] == SYSTEM_PROMPT and req["model"] == "test-model" and req["temperature"] == 0.2
    assert req["text"]["format"] == {"type": "json_schema", "name": "narration", "schema": MODEL_OUTPUT_SCHEMA,
                                     "strict": True}
    sent = json.loads(req["input"].split("ACCOUNT:\n", 1)[1])
    assert sent == json.loads(json.dumps(brief(hero)))  # the brief, nothing else


def test_rejected_output_is_regenerated_with_feedback(hero, tmp_path):
    bad = _good(hero)
    bad["sentences"][2]["text"] = "Then Smith scored."
    renderer, client = _renderer(bad, _good(hero))
    n = narrate(hero, renderer=renderer, cache_dir=tmp_path)
    assert n.source == "foundry" and n.attempts == 2 and len(n.rejections) == 1
    assert "REJECTED" in client.requests[1]["input"] and "'Smith'" in client.requests[1]["input"]
    assert "Smith" not in n.headline_text + " ".join(s.text for s in n.sentences)  # only in the recorded rejection


def test_persistent_hallucination_falls_back_to_the_template(hero, tmp_path):
    bad = _good(hero)
    bad["sentences"][0]["ref"] = "event:1"
    renderer, client = _renderer(*[bad] * MAX_ATTEMPTS)
    n = narrate(hero, renderer=renderer, cache_dir=tmp_path)
    assert n.source == "template" and n.attempts == MAX_ATTEMPTS and len(n.rejections) == MAX_ATTEMPTS
    assert "passed validation" in n.fallback_reason
    assert validate(render_template(hero), hero) == []
    assert not (tmp_path / hero.game_id).exists()  # a fallback is not cached as the model's narration


def test_foundry_errors_and_missing_config_fall_back(hero, tmp_path, monkeypatch):
    renderer, _ = _renderer(ConnectionError("no route to host"))
    n = narrate(hero, renderer=renderer, cache_dir=tmp_path)
    assert n.source == "template" and "ConnectionError" in n.fallback_reason
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    n = narrate(hero, cache_dir=tmp_path)
    assert n.source == "template" and "FOUNDRY_PROJECT_ENDPOINT" in n.fallback_reason


def test_cache_replays_and_is_keyed_by_account(hero, accounts, tmp_path):
    renderer, client = _renderer(_good(hero))
    first = narrate(hero, renderer=renderer, cache_dir=tmp_path)
    again = narrate(hero, renderer=renderer, cache_dir=tmp_path)  # no queued output left: must come from cache
    assert again == first and len(client.requests) == 1
    other = accounts["SYN-0007-goal-1"]
    renderer2, client2 = _renderer(_good(other))
    narrate(other, renderer=renderer2, cache_dir=tmp_path)
    assert len(client2.requests) == 1
    renderer3, client3 = _renderer(_good(hero))
    narrate(hero, renderer=renderer3, cache_dir=tmp_path, refresh=True)
    assert len(client3.requests) == 1


def test_temperature_can_be_omitted(hero, tmp_path):
    renderer, client = _renderer(_good(hero), temperature=None)
    narrate(hero, renderer=renderer, cache_dir=tmp_path)
    assert "temperature" not in client.requests[0]


def test_cli_template(tmp_path, hero):
    path = tmp_path / "a.json"
    path.write_text(hero.model_dump_json(), encoding="utf-8")
    out = io.StringIO()
    assert main([str(path), "--mode", "template"], out=out) == 0
    text = out.getvalue()
    assert text.startswith("SYN-0007-big_chance_saved-3  [prevented]  source: template")
    assert "HEADLINE: A goal that didn't happen" in text and "timed overlay:" in text
    out = io.StringIO()
    main([str(path), "--mode", "template", "--json"], out=out)
    assert Narration.model_validate(json.loads(out.getvalue())[0]).moment_id == hero.moment.moment_id


# --------------------------------------------------------------------------- live Foundry (opt-in)


@pytest.mark.skipif(os.environ.get("REPLAY_ROOM_FOUNDRY_IT") != "1",
                    reason="live Foundry test: set REPLAY_ROOM_FOUNDRY_IT=1 plus FOUNDRY_PROJECT_ENDPOINT and "
                           "FOUNDRY_MODEL_DEPLOYMENT, after az login")
def test_live_foundry_narration_is_grounded(hero, tmp_path):
    n = narrate(hero, cache_dir=tmp_path)
    assert n.source == "foundry", n.fallback_reason
    assert validate(ModelNarration(headline_text=n.headline_text, sentences=tuple(
        {"contribution_id": s.contribution_id, "ref": f"{s.ref.kind}:{getattr(s.ref, 'action_id', None) or s.ref.frame_id}",
         "role": s.role, "text": s.text, "metric": s.metric} for s in n.sentences)), hero) == []
