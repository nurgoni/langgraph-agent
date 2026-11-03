import ast
import sys
from pathlib import Path

import agent_service.schema

SCHEMA_DIR = Path(agent_service.schema.__file__).parent
ALLOWED_THIRD_PARTY = {"pydantic"}
OWN_PACKAGE = "agent_service.schema"


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
    return module == OWN_PACKAGE or module.startswith(OWN_PACKAGE + ".")


def test_schema_depends_only_on_pydantic_and_stdlib() -> None:
    violations: list[str] = []
    for source_file in sorted(SCHEMA_DIR.glob("*.py")):
        for module in sorted(imported_modules(source_file)):
            if not is_allowed(module):
                violations.append(f"{source_file.name}: {module}")

    assert violations == []
