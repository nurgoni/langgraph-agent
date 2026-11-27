"""`datasource/` hanya bergantung pada `core/`: tidak mengenal agent, harness, service, atau API."""

import ast
from pathlib import Path

import agent_service.datasource
from agent_service.core import constants
from agent_service.schema import datasources

DATASOURCE_DIR = Path(agent_service.datasource.__file__).parent
FORBIDDEN_PREFIXES = (
    "agent_service.agents",
    "agent_service.harness",
    "agent_service.service",
    "agent_service.schema",
    "agent_service.client",
    "agent_service.ui",
    "agent_service.sandbox",
    "langchain",
    "langgraph",
)


def imported_modules(source_file: Path) -> set[str]:
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def test_datasource_imports_only_core_and_libraries() -> None:
    violations: list[str] = []
    for source_file in sorted(DATASOURCE_DIR.rglob("*.py")):
        for module in sorted(imported_modules(source_file)):
            if module.startswith(FORBIDDEN_PREFIXES):
                violations.append(f"{source_file.name}: {module}")

    assert violations == []


def test_schema_copy_of_the_data_source_id_rule_matches_core() -> None:
    assert datasources.DATA_SOURCE_ID_PATTERN == constants.DATA_SOURCE_ID_PATTERN
    assert datasources.DATA_SOURCE_ID_MAX_LENGTH == constants.DATA_SOURCE_ID_MAX_LENGTH
