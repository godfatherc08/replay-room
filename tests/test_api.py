"""The live backend: a moment told by the agents, returned as the bundle the viewer loads; CORS locked to the allow-list."""

import pytest
from starlette.testclient import TestClient

from replay_room.api import app as api

ORIGIN = "https://viewer.example"


@pytest.fixture(scope="module")
def client(fixture_dir):
    with pytest.MonkeyPatch.context() as mp:
        for var in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL_DEPLOYMENT"):
            mp.delenv(var, raising=False)  # the deterministic floors: no model in tests
        mp.setenv("ALLOWED_ORIGINS", ORIGIN)
        mp.setattr(api, "_studio", api.Studio(str(fixture_dir)))
        yield TestClient(api.create_app())


def test_healthz_lists_the_explainable_moments(client, all_accounts):
    r = client.get("/healthz")
    assert r.status_code == 200 and set(r.json()["moments"]) == set(all_accounts)


def test_a_bundle_is_the_agents_telling_of_the_engines_account(client, all_accounts):
    r = client.get("/api/bundle/SYN-0007-goal-1", headers={"Origin": ORIGIN})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == ORIGIN
    b = r.json()
    assert b["account"] == all_accounts["SYN-0007-goal-1"].model_dump(mode="json")
    assert b["narration"]["source"] == "template" and b["story"]
    assert [s["agent"] for s in b["live"]["trace"]][-2:] == ["Editor", "Editor"]


def test_unknown_moments_and_other_origins_are_refused(client):
    assert client.get("/api/bundle/SYN-0007-offside-1").status_code == 404
    r = client.get("/healthz", headers={"Origin": "https://elsewhere.example"})
    assert "access-control-allow-origin" not in r.headers
