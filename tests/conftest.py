from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def _block_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def guarded_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("Testes nao podem acessar rede real; injete um transporte fake.")

    monkeypatch.setattr(socket, "socket", guarded_socket)
