"""Shared pytest fixtures. Feature-specific fixtures live next to their tests."""

import ipaddress
import socket
from collections.abc import Iterator

import pytest

INTEGRATION_MARKER = "integration"
LOCALHOST_NAME = "localhost"


class NetworkAccessError(RuntimeError):
    """Unit test mencoba membuka koneksi ke host di luar loopback."""


def _is_loopback(address: object) -> bool:
    """Cek apakah alamat `connect()` menuju loopback.

    Args:
        address: Argumen `address` milik `socket.connect`, biasanya tuple `(host, port)`.

    Returns:
        True jika host adalah `localhost` atau IP loopback.
    """
    if not isinstance(address, tuple) or not address:
        return False
    host = str(address[0])
    if host == LOCALHOST_NAME:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def block_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Gagalkan setiap koneksi keluar di unit test (AGENTS.md § Testing).

    Loopback tetap diizinkan karena event loop asyncio di Windows memakainya secara internal.
    Test bertanda `integration` dikecualikan.
    """
    if request.node.get_closest_marker(INTEGRATION_MARKER) is not None:
        yield
        return
    original_connect = socket.socket.connect

    def guarded_connect(sock: socket.socket, address: object) -> None:
        if not _is_loopback(address):
            raise NetworkAccessError(f"network access is blocked in unit tests: {address!r}")
        original_connect(sock, address)  # pyrefly: ignore[bad-argument-type]

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    yield
