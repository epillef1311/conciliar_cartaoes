"""Transportes HTTP injetaveis para a API Velo."""

from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import requests


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    text: str


class HttpTransport(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, object] | None,
        timeout: object,
    ) -> HttpResponse:
        """Executa GET. Testes devem injetar um transporte fake."""


class UrlLibTransport:
    """Transporte real reservado para etapa futura com token autorizado."""

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, object] | None,
        timeout: object,
    ) -> HttpResponse:
        final_url = _url_with_params(url, params)
        request = Request(final_url, headers=headers, method="GET")
        timeout_seconds = _timeout_seconds(timeout)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                body = response.read().decode("utf-8")
                return HttpResponse(
                    status_code=response.status,
                    headers=dict(response.headers.items()),
                    text=body,
                )
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return HttpResponse(
                status_code=exc.code,
                headers=dict(exc.headers.items()),
                text=body,
            )
        except TimeoutError:
            raise
        except URLError:
            raise


class RequestsSessionTransport:
    """Transporte sequencial com conexao HTTPS persistente."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, object] | None,
        timeout: object,
    ) -> HttpResponse:
        try:
            response = self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=timeout,
            )
        except requests.Timeout as exc:
            raise TimeoutError("Tempo limite da API Velo excedido.") from exc
        except requests.RequestException as exc:
            raise URLError("Falha de conexao com a API Velo.") from exc
        return HttpResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            text=response.text,
        )

    def close(self) -> None:
        self.session.close()


def _url_with_params(url: str, params: dict[str, object] | None) -> str:
    if not params:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(params)}"


def _timeout_seconds(timeout: object) -> float:
    if isinstance(timeout, tuple) and timeout:
        return float(max(timeout))
    if isinstance(timeout, int | float):
        return float(timeout)
    return 30.0
