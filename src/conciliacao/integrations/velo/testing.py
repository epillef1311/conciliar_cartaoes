"""Transportes simulados da Velo para testes e CLI sem internet."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conciliacao.integrations.velo.config import VeloApiConfig
from conciliacao.integrations.velo.http import HttpResponse


@dataclass(frozen=True, slots=True)
class FakeHttpCall:
    url: str
    headers: dict[str, str]
    params: dict[str, object] | None
    timeout: object


class FakeVeloTransport:
    def __init__(
        self,
        responses: dict[str, HttpResponse] | None = None,
        *,
        timeout: bool = False,
        connection_error: bool = False,
    ) -> None:
        self.responses = responses or {}
        self.timeout = timeout
        self.connection_error = connection_error
        self.calls: list[FakeHttpCall] = []

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, object] | None,
        timeout: object,
    ) -> HttpResponse:
        self.calls.append(
            FakeHttpCall(url=url, headers=dict(headers), params=params, timeout=timeout)
        )
        if self.timeout:
            raise TimeoutError("timeout simulado")
        if self.connection_error:
            raise OSError("falha de conexao simulada")
        key = _response_key(url)
        response = self.responses.get(key)
        if response is None:
            return HttpResponse(
                status_code=404,
                headers={"Content-Type": "application/json"},
                text='{"erro":"fixture nao encontrada"}',
            )
        return response


class FixtureVeloTransport:
    def __init__(self, fixtures_dir: str | Path, config: VeloApiConfig) -> None:
        self.fixtures_dir = Path(fixtures_dir)
        self.config = config
        self.calls: list[FakeHttpCall] = []
        self.filename_by_id = {
            value: category.config_key
            for category, value in config.formas_recebimento_fallback.items()
        }

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, object] | None,
        timeout: object,
    ) -> HttpResponse:
        self.calls.append(
            FakeHttpCall(url=url, headers=dict(headers), params=params, timeout=timeout)
        )
        filename = self._filename_for(url, params)
        payload = (self.fixtures_dir / filename).read_text(encoding="utf-8")
        json.loads(payload)
        return HttpResponse(
            status_code=200,
            headers={"Content-Type": "application/json; charset=utf-8"},
            text=payload,
        )

    def _filename_for(self, url: str, params: dict[str, object] | None) -> str:
        if url.endswith(self.config.endpoints.autocomplete_operadoras):
            return "autocomplete_operadoras.json"
        if url.endswith(self.config.endpoints.conciliacao_recebidos):
            raw_id = None if params is None else params.get("operadoraId")
            if not isinstance(raw_id, int | str):
                raise FileNotFoundError(f"fixture Velo sem operadoraId para {url}")
            filename = self.filename_by_id.get(int(raw_id))
            if filename is not None:
                return f"{filename}.json"
        raise FileNotFoundError(f"fixture Velo nao mapeada para {url}")


def json_response(payload: Any, *, status_code: int = 200) -> HttpResponse:
    return HttpResponse(
        status_code=status_code,
        headers={"Content-Type": "application/json"},
        text=json.dumps(payload, ensure_ascii=False),
    )


def text_response(
    text: str,
    *,
    status_code: int = 200,
    content_type: str = "application/json",
) -> HttpResponse:
    return HttpResponse(
        status_code=status_code,
        headers={"Content-Type": content_type},
        text=text,
    )


def _response_key(url: str) -> str:
    return url.rsplit("/", maxsplit=1)[-1]
