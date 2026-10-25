"""The engine as an MCP server: a real MCP client launches it over stdio, lists and calls every tool."""

import asyncio

import pytest

from replay_room.contracts.causal_account import CausalAccount
from replay_room.contracts.context import MatchContext
from replay_room.explain.schema import Narration
from replay_room.mcp_server.smoke import TOOLS, smoke


@pytest.fixture(scope="module")
def answers(fixture_dir):
    return asyncio.run(smoke("SYN-0007-goal-1", fixture_dir))


def test_the_server_lists_every_tool(answers):
    assert set(TOOLS) <= set(answers["tools"])


def test_every_tool_answers_with_its_contract(answers, all_accounts, all_contexts):
    moments = answers["detect_moments"]["moments"]
    assert {m["moment_id"] for m in moments if m["engine_eligible"]} == set(all_accounts)
    account = CausalAccount.model_validate(answers["attribute"])
    assert account == all_accounts["SYN-0007-goal-1"]  # over the wire, the same account as in-process
    assert MatchContext.model_validate(answers["match_context"]) == all_contexts["SYN-0007-goal-1"]
    n = Narration.model_validate(answers["narrate"])
    assert n.source == "template" and n.moment_id == "SYN-0007-goal-1"


def test_the_agents_reach_the_engine_over_mcp(fixture_dir, all_accounts, monkeypatch):
    from replay_room.agents.engine import McpEngine
    from replay_room.agents.orchestrator import Orchestrator
    from replay_room.agents.sources import FixtureStream

    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    with McpEngine(fixture_dir) as engine:  # opens one session, closes it cleanly from the same task
        assert set(TOOLS) <= set(engine.tools)
        orch = Orchestrator(engine, FixtureStream(fixture_dir), mode="template")
        result = orch.explain("SYN-0007-goal-1")
    assert result.account == all_accounts["SYN-0007-goal-1"]
    assert any(s.action == "attribute (mcp (stdio))" for s in orch.trace)
    assert set(result.editions) == {"analyst", "fan"}
