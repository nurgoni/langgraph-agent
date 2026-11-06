from pydantic import JsonValue

from agent_service.client.errors import AgentClientError


def test_error_keeps_status_and_detail() -> None:
    detail: JsonValue = [{"loc": ["body", "message"], "msg": "too short"}]

    error = AgentClientError("Request failed", status_code=422, detail=detail)

    assert (str(error), error.status_code, error.detail) == ("Request failed", 422, detail)


def test_connection_error_has_no_status() -> None:
    error = AgentClientError("Connection refused")

    assert error.status_code is None
    assert error.detail is None
