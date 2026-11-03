import io
import logging
from collections.abc import Iterator

import pytest

from agent_service.core.logging_config import NOISY_LOGGER_LEVEL, NOISY_LOGGERS, configure_logging


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    """Kembalikan root logger setelah test, karena `configure_logging` mengubah state global."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def test_messages_use_project_format() -> None:
    output = io.StringIO()

    configure_logging("INFO", stream=output)
    logging.getLogger("agent_service.demo").info("hello")

    assert "| INFO     | agent_service.demo | hello" in output.getvalue()


def test_messages_below_level_are_dropped() -> None:
    output = io.StringIO()

    configure_logging("WARNING", stream=output)
    logging.getLogger("agent_service.demo").info("hidden")

    assert output.getvalue() == ""


def test_noisy_library_loggers_are_quieted() -> None:
    configure_logging("DEBUG", stream=io.StringIO())

    for logger_name in NOISY_LOGGERS:
        assert logging.getLogger(logger_name).level == NOISY_LOGGER_LEVEL


def test_repeated_calls_do_not_duplicate_output() -> None:
    output = io.StringIO()

    configure_logging("INFO", stream=output)
    configure_logging("INFO", stream=output)
    logging.getLogger("agent_service.demo").info("once")

    assert output.getvalue().count("once") == 1
