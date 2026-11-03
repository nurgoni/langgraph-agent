import socket

import pytest

BLOCKED_ADDRESS = ("192.0.2.1", 443)


def test_outbound_connection_is_blocked() -> None:
    with socket.socket() as sock, pytest.raises(RuntimeError, match="network access is blocked"):
        sock.connect(BLOCKED_ADDRESS)


def test_loopback_connection_is_allowed() -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        with socket.socket() as client:
            client.connect(server.getsockname())
