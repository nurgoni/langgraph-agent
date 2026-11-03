from agent_service.agents.catalog import DEFAULT_AGENT_ID, create_default_agents


def test_default_agent_is_in_catalog() -> None:
    agent_ids = [agent.agent_id for agent in create_default_agents()]

    assert DEFAULT_AGENT_ID in agent_ids


def test_agent_ids_are_unique() -> None:
    agent_ids = [agent.agent_id for agent in create_default_agents()]

    assert len(agent_ids) == len(set(agent_ids))


def test_each_call_returns_new_instances() -> None:
    first, second = create_default_agents(), create_default_agents()

    assert all(a is not b for a, b in zip(first, second, strict=True))
