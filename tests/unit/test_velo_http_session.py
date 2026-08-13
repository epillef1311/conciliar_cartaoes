from __future__ import annotations

import requests

from conciliacao.integrations.velo.http import RequestsSessionTransport


class _Response:
    status_code = 200
    headers = {"Content-Type": "application/json"}
    text = "[]"


class _Session:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.closed = False

    def get(self, url: str, **kwargs: object) -> _Response:
        self.calls.append({"url": url, **kwargs})
        return _Response()

    def close(self) -> None:
        self.closed = True


def test_requests_transport_reuses_session_without_logging_headers() -> None:
    session = _Session()
    transport = RequestsSessionTransport(session)  # type: ignore[arg-type]

    first = transport.get(
        "https://api.example.test/listar",
        headers={"Authorization": "Bearer token-teste-nao-real"},
        params={"operadoraId": 81},
        timeout=(5, 30),
    )
    second = transport.get(
        "https://api.example.test/listar",
        headers={"Authorization": "Bearer token-teste-nao-real"},
        params={"operadoraId": 86},
        timeout=(5, 30),
    )

    assert first.status_code == second.status_code == 200
    assert len(session.calls) == 2
    assert transport.session is session
    assert "token-teste-nao-real" not in repr(transport)
    transport.close()
    assert session.closed


def test_requests_transport_maps_timeout_without_secret() -> None:
    class TimeoutSession(_Session):
        def get(self, url: str, **kwargs: object) -> _Response:
            raise requests.Timeout("timeout artificial")

    transport = RequestsSessionTransport(TimeoutSession())  # type: ignore[arg-type]
    try:
        transport.get(
            "https://api.example.test/listar",
            headers={"Authorization": "Bearer token-teste-nao-real"},
            params=None,
            timeout=(5, 30),
        )
    except TimeoutError as exc:
        assert "token-teste-nao-real" not in str(exc)
    else:
        raise AssertionError("timeout deveria ser convertido")
