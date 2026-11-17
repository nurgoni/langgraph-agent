"""`evals/` hanya bicara ke service lewat `client/` dan `schema/` (AGENTS.md § Batas layer)."""

import ast
import sys
from pathlib import Path

import agent_service.evals

EVALS_DIR = Path(agent_service.evals.__file__).parent
ALLOWED_THIRD_PARTY = {"httpx", "pydantic", "pydantic_settings", "yaml"}
ALLOWED_OWN_PACKAGES = ("agent_service.evals", "agent_service.client", "agent_service.schema")


def imported_modules(source_file: Path) -> set[str]:
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def is_allowed(module: str) -> bool:
    root = module.split(".")[0]
    if root in sys.stdlib_module_names or root in ALLOWED_THIRD_PARTY:
        return True
    return any(module == own or module.startswith(own + ".") for own in ALLOWED_OWN_PACKAGES)


def test_evals_use_only_client_and_schema() -> None:
    sources = [*sorted(EVALS_DIR.glob("*.py")), EVALS_DIR.parent / "run_evals.py"]
    violations: list[str] = []
    for source_file in sources:
        for module in sorted(imported_modules(source_file)):
            if not is_allowed(module):
                violations.append(f"{source_file.name}: {module}")

    assert violations == []
