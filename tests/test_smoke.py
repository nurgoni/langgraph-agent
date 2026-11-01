import importlib
import importlib.metadata

import pytest

import agent_service

SUBPACKAGES = ["core", "llm", "agents", "memory", "schema", "service", "client", "ui"]


def test_package_is_importable() -> None:
    assert agent_service.__name__ == "agent_service"


def test_distribution_metadata_is_installed() -> None:
    assert importlib.metadata.version("agent-service")


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_is_importable(name: str) -> None:
    module = importlib.import_module(f"agent_service.{name}")
    assert module.__doc__, f"agent_service.{name} needs a docstring describing its layer"
