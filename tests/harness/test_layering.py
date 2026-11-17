"""`harness/` tidak boleh meng-import `agents/`, `service/`, `schema/`, `client/`, atau `ui/`."""

import ast
from pathlib import Path

import agent_service.harness

HARNESS_DIR = Path(agent_service.harness.__file__).parent
FORBIDDEN_PREFIXES = (
    "agent_service.agents",
    "agent_service.service",
    "agent_service.schema",
    "agent_service.client",
    "agent_service.ui",
    "langchain.",
    "deepagents",
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


def test_harness_does_not_import_agents_service_or_outer_layers() -> None:
    violations: list[str] = []
    for source_file in sorted(HARNESS_DIR.rglob("*.py")):
        for module in sorted(imported_modules(source_file)):
            if module.startswith(FORBIDDEN_PREFIXES) or module == "langchain":
                violations.append(f"{source_file.name}: {module}")

    assert violations == []
