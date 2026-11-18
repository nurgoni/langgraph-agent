"""Entrypoint: `python -m agent_service.run_sandbox_runner` menjalankan service `sandbox-runner`.

Dipakai di container compose `sandbox-runner` (Linux, dengan `docker.sock`), bukan di host dev.
"""

import uvicorn

from agent_service.core.logging_config import configure_logging
from agent_service.sandbox.runner import SandboxRunnerSettings, create_runner_app


def main() -> None:
    """Baca `SandboxRunnerSettings` dari env, lalu jalankan runner dengan uvicorn.

    Function, bukan class: entrypoint CLI (AGENTS.md § Class vs Function).

    Raises:
        pydantic.ValidationError: Jika `SANDBOX_TOKEN` kosong atau terlalu pendek.
    """
    settings = SandboxRunnerSettings()
    configure_logging(settings.log_level)
    # log_config=None: uvicorn memakai root logger dari configure_logging, bukan config-nya sendiri.
    app = create_runner_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)


if __name__ == "__main__":
    main()
