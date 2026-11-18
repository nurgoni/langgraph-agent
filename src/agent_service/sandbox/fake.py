"""`FakeSandbox`: sandbox palsu untuk test, tanpa Docker dan tanpa menjalankan kode apa pun."""

from collections.abc import Callable

from agent_service.sandbox.model import ExecutionRequest, ExecutionResult

type ResultFactory = Callable[[ExecutionRequest], ExecutionResult]


class FakeSandbox:
    """Mencatat setiap permintaan dan menjawab dengan hasil yang ditentukan test.

    >>> import asyncio
    >>> sandbox = FakeSandbox(lambda request: ExecutionResult(exit_code=0, stdout="ok"))
    >>> result = asyncio.run(sandbox.execute(ExecutionRequest(language="python", code="x")))
    >>> result.stdout, len(sandbox.requests)
    ('ok', 1)
    """

    def __init__(self, respond: ResultFactory) -> None:
        """Inisialisasi sandbox palsu.

        Args:
            respond: Pembuat hasil untuk setiap permintaan.
        """
        self._respond = respond
        self.requests: list[ExecutionRequest] = []

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Catat permintaan, lalu kembalikan hasil dari `respond`."""
        self.requests.append(request)
        return self._respond(request)
