"""Tool kalkulator berbasis numexpr untuk pertanyaan matematika."""

import math
from typing import Final

import numexpr
from langchain_core.tools import ToolException, tool

CALCULATOR_TOOL_NAME: Final = "calculator"
# Hanya konstanta ini yang bisa dipakai di ekspresi. Global Python sengaja dikosongkan.
MATH_CONSTANTS: Final = {"pi": math.pi, "e": math.e}


@tool(CALCULATOR_TOOL_NAME)
def calculator(expression: str) -> str:
    """Evaluate a math expression with numexpr, for example "300 * 200" or "sqrt(16) + pi".

    Use this tool only for math. The input must be a single numexpr expression.
    """
    # Function, bukan class: `@tool` membaca signature dan docstring (berbahasa Inggris karena
    # dikirim ke LLM sebagai deskripsi tool). Lihat AGENTS.md § Class vs Function.
    try:
        value = numexpr.evaluate(
            expression.strip(), global_dict={}, local_dict=dict(MATH_CONSTANTS)
        )
    except (SyntaxError, KeyError, TypeError, ValueError, AttributeError) as error:
        raise ToolException(
            f"calculator({expression!r}) failed: {error}. Use a valid numeric expression."
        ) from error
    return str(value.tolist())


if __name__ == "__main__":
    print(calculator.invoke({"expression": "12 * 7"}))
    print(calculator.invoke({"expression": "sqrt(16) + pi"}))
