import pytest
from langchain_core.tools import ToolException

from agent_service.agents.tools.calculator import CALCULATOR_TOOL_NAME, calculator


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("12 * 7", "84"),
        ("  2 ** 10 ", "1024"),
        ("10 / 4", "2.5"),
        ("sqrt(16)", "4.0"),
        ("pi > 3", "True"),
    ],
)
def test_evaluates_math_expressions(expression: str, expected: str) -> None:
    assert calculator.invoke({"expression": expression}) == expected


def test_constants_are_available() -> None:
    assert float(calculator.invoke({"expression": "e"})) == pytest.approx(2.718281828)


@pytest.mark.parametrize("expression", ["12 *", "unknown_name + 1", "__import__('os')"])
def test_invalid_expression_raises_tool_exception(expression: str) -> None:
    with pytest.raises(ToolException, match="calculator"):
        calculator.invoke({"expression": expression})


def test_schema_exposes_only_expression() -> None:
    assert calculator.name == CALCULATOR_TOOL_NAME
    assert list(calculator.args) == ["expression"]
    assert "numexpr" in calculator.description
