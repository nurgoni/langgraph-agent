import pytest

from agent_service.agents.errors import (
    AgentError,
    AgentNotFoundError,
    AgentUnavailableError,
    DuplicateAgentError,
)


@pytest.mark.parametrize(
    ("error_class", "expected_message"),
    [
        (AgentNotFoundError, "Agent 'x' not found"),
        (AgentUnavailableError, "Agent 'x' is unavailable"),
        (DuplicateAgentError, "Agent 'x' is already registered"),
    ],
)
def test_errors_carry_agent_id_and_message(
    error_class: type[AgentError], expected_message: str
) -> None:
    error = error_class("x")  # pyrefly: ignore[missing-argument]

    assert isinstance(error, AgentError)
    assert error.agent_id == "x"
    assert str(error) == expected_message
