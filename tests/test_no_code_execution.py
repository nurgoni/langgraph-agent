"""NFR-10 (acceptance F37): tidak ada `exec`/`eval`/subprocess di proses service.

Kode buatan model hanya boleh dijalankan lewat `Sandbox` (container terpisah). Test ini membaca
AST setiap modul di layer yang berjalan di proses service, jadi panggilan baru yang melanggar
langsung gagal di CI.
"""

import ast
from pathlib import Path

import pytest

import agent_service

PACKAGE_DIR = Path(agent_service.__file__).parent
CHECKED_LAYERS = ("service", "agents", "harness", "sandbox")
FORBIDDEN_BUILTINS = frozenset({"exec", "eval", "compile", "__import__"})
FORBIDDEN_MODULES = frozenset({"subprocess", "pty", "multiprocessing"})
FORBIDDEN_OS_PREFIXES = ("system", "popen", "exec", "spawn", "fork", "posix_spawn")
FORBIDDEN_ASYNCIO_CALLS = frozenset({"create_subprocess_exec", "create_subprocess_shell"})


def violations_in(source: str) -> list[str]:
    """Pemanggilan atau import terlarang di satu modul, sebagai `baris: deskripsi`."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        description = _forbidden(node)
        if description is not None:
            found.append(f"{getattr(node, 'lineno', 0)}: {description}")
    return found


def _forbidden(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id if node.func.id in FORBIDDEN_BUILTINS else None
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return _forbidden_attribute(node.value.id, node.attr)
    if isinstance(node, ast.Import):
        names = [alias.name.split(".")[0] for alias in node.names]
        return next((f"import {name}" for name in names if name in FORBIDDEN_MODULES), None)
    if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        root = node.module.split(".")[0]
        return f"from {node.module} import" if root in FORBIDDEN_MODULES else None
    return None


def _forbidden_attribute(owner: str, attribute: str) -> str | None:
    if owner == "os" and attribute.startswith(FORBIDDEN_OS_PREFIXES):
        return f"os.{attribute}"
    if owner == "asyncio" and attribute in FORBIDDEN_ASYNCIO_CALLS:
        return f"asyncio.{attribute}"
    return None


@pytest.mark.parametrize("layer", CHECKED_LAYERS)
def test_service_process_never_executes_code(layer: str) -> None:
    violations: list[str] = []
    for source_file in sorted((PACKAGE_DIR / layer).rglob("*.py")):
        for violation in violations_in(source_file.read_text(encoding="utf-8")):
            violations.append(f"{source_file.relative_to(PACKAGE_DIR)}:{violation}")

    assert violations == []


@pytest.mark.parametrize(
    "source",
    [
        "eval(code)",
        "exec(code)",
        "import subprocess",
        "from subprocess import run",
        "os.system('ls')",
        "os.execvp('sh', [])",
        "await asyncio.create_subprocess_shell('ls')",
    ],
)
def test_checker_detects_forbidden_calls(source: str) -> None:
    assert violations_in(f"async def f():\n    {source}\n") != []
