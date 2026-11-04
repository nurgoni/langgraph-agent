import ast
import sys
from pathlib import Path

import agent_service.ui

UI_DIR = Path(agent_service.ui.__file__).parent
ALLOWED_THIRD_PARTY = {"streamlit", "pydantic", "pydantic_settings"}
ALLOWED_OWN_PACKAGES = ("agent_service.ui", "agent_service.client", "agent_service.schema")


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


def test_ui_talks_to_service_only_through_client() -> None:
    violations: list[str] = []
    for source_file in sorted(UI_DIR.glob("*.py")):
        for module in sorted(imported_modules(source_file)):
            if not is_allowed(module):
                violations.append(f"{source_file.name}: {module}")

    assert violations == []
