"""Cliente somente leitura da API Velo."""

import json
from datetime import date
from json import JSONDecodeError
from typing import Any
from urllib.error import URLError

from pydantic import ValidationError

from conciliacao.domain.models import RegistroSistema
from conciliacao.integrations.velo.audit import VeloAuditWriter
from conciliacao.integrations.velo.authentication import TokenProvider, VeloTokenProvider
from conciliacao.integrations.velo.categories import CategoriaFiltroVelo
from conciliacao.integrations.velo.config import VeloApiConfig, load_velo_api_config
from conciliacao.integrations.velo.exceptions import (
    VeloAuthenticationError,
    VeloAuthorizationError,
    VeloBadRequestError,
    VeloConnectionError,
    VeloEndpointNotFoundError,
    VeloInvalidResponseError,
    VeloRateLimitError,
    VeloSchemaError,
    VeloServerError,
    VeloTimeoutError,
)
from conciliacao.integrations.velo.http import HttpResponse, HttpTransport, UrlLibTransport
from conciliacao.integrations.velo.mapper import map_registro_sistema
from conciliacao.integrations.velo.schemas import FormaRecebimentoApi, RegistroConciliacaoApi
from conciliacao.utils.dates import validate_period


class VeloClient:
    def __init__(
        self,
        config: VeloApiConfig | None = None,
        *,
        token_provider: TokenProvider | None = None,
        transport: HttpTransport | None = None,
        audit_writer: VeloAuditWriter | None = None,
    ) -> None:
        self.config = config or load_velo_api_config()
        self.token_provider = token_provider or VeloTokenProvider()
        self.transport = transport or UrlLibTransport()
        self.audit_writer = audit_writer

    def autocomplete_operadoras(self) -> list[FormaRecebimentoApi]:
        endpoint = self.config.endpoints.autocomplete_operadoras
        payload = self._get_json(
            endpoint,
            params=None,
            raw_filename="autocomplete_operadoras.json",
        )
        if not isinstance(payload, list):
            raise VeloSchemaError(
                "Resposta de autocomplete deve ser uma lista JSON.",
                endpoint=endpoint,
                context={"tipo_resposta": type(payload).__name__},
            )
        return [_parse_forma_recebimento(item, endpoint=endpoint) for item in payload]

    def consultar_conciliacao(
        self,
        *,
        categoria: CategoriaFiltroVelo,
        filtro_forma_recebimento_id: int,
        data_inicio: date,
        data_fim: date,
    ) -> list[RegistroSistema]:
        inicio, fim = validate_period(data_inicio, data_fim)
        endpoint = self.config.endpoints.conciliacao_recebidos
        # A API chama o parametro de operadoraId, mas o valor observado e o ID
        # da forma de recebimento resolvida pelo autocomplete/fallback.
        params: dict[str, object] = {
            "operadoraId": filtro_forma_recebimento_id,
            "intervaloDia": self.config.query.intervalo_dia,
            "dataInicio": inicio.isoformat(),
            "dataFim": fim.isoformat(),
            "isCompensado": self.config.query.is_compensado,
        }
        payload = self._get_json(
            endpoint,
            params=params,
            raw_filename=f"{categoria.config_key}.json",
        )
        if not isinstance(payload, list):
            raise VeloSchemaError(
                "Resposta de conciliacao deve ser uma lista JSON.",
                endpoint=endpoint,
                context={"tipo_resposta": type(payload).__name__, "categoria": categoria.value},
            )
        registros = [
            _parse_registro_sistema(item, endpoint=endpoint, categoria=categoria)
            for item in payload
        ]
        return registros

    def save_audit_metadata(
        self,
        *,
        period_start: date,
        period_end: date,
        categories_requested: tuple[CategoriaFiltroVelo, ...],
    ) -> None:
        if self.audit_writer is None:
            return
        self.audit_writer.save_metadata(
            period_start=period_start,
            period_end=period_end,
            query=self.config.query,
            categories_requested=categories_requested,
        )

    def _get_json(
        self,
        endpoint: str,
        *,
        params: dict[str, object] | None,
        raw_filename: str,
    ) -> Any:
        url = f"{self.config.base_url}{endpoint}"
        response = self._get_response(endpoint, url=url, params=params)
        self._validate_status(endpoint, response)
        self._validate_content_type(endpoint, response)
        payload = self._decode_json(endpoint, response)
        if self.audit_writer is not None:
            self.audit_writer.save_json(raw_filename, payload)
        return payload

    def _get_response(
        self, endpoint: str, *, url: str, params: dict[str, object] | None
    ) -> HttpResponse:
        token = self.token_provider.get_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            return self.transport.get(
                url,
                headers=headers,
                params=params,
                timeout=self.config.timeouts.as_tuple,
            )
        except TimeoutError as exc:
            raise VeloTimeoutError(
                "Timeout ao consultar a API Velo.", endpoint=endpoint, cause=exc
            ) from exc
        except URLError as exc:
            raise VeloConnectionError(
                "Falha de conexao ao consultar a API Velo.",
                endpoint=endpoint,
                cause=exc,
            ) from exc
        except OSError as exc:
            raise VeloConnectionError(
                "Falha de conexao ao consultar a API Velo.",
                endpoint=endpoint,
                cause=exc,
            ) from exc

    def _validate_status(self, endpoint: str, response: HttpResponse) -> None:
        status_code = response.status_code
        context = {"endpoint": endpoint, "status_code": status_code}
        if status_code == 400:
            raise VeloBadRequestError(
                "Parametros invalidos na consulta Velo.",
                endpoint=endpoint,
                status_code=status_code,
                context=context,
            )
        if status_code == 401:
            raise VeloAuthenticationError(
                "Token Bearer ausente, invalido ou expirado.",
                endpoint=endpoint,
                status_code=status_code,
            )
        if status_code == 403:
            raise VeloAuthorizationError(
                "Acesso negado pela API Velo.",
                endpoint=endpoint,
                status_code=status_code,
                context=context,
            )
        if status_code == 404:
            raise VeloEndpointNotFoundError(
                "Endpoint Velo nao encontrado.",
                endpoint=endpoint,
                status_code=status_code,
                context=context,
            )
        if status_code == 429:
            raise VeloRateLimitError(
                "Limite de requisicoes da API Velo atingido.",
                endpoint=endpoint,
                status_code=status_code,
                context=context,
            )
        if 500 <= status_code <= 599:
            raise VeloServerError(
                "Erro interno da API Velo.",
                endpoint=endpoint,
                status_code=status_code,
                context=context,
            )
        if not 200 <= status_code <= 299:
            raise VeloInvalidResponseError(
                "Status HTTP inesperado da API Velo.",
                endpoint=endpoint,
                status_code=status_code,
                context=context,
            )

    def _validate_content_type(self, endpoint: str, response: HttpResponse) -> None:
        content_type = _header_value(response.headers, "Content-Type")
        if "application/json" not in content_type.casefold():
            raise VeloInvalidResponseError(
                "Resposta Velo nao possui Content-Type JSON.",
                endpoint=endpoint,
                status_code=response.status_code,
                context={"content_type": content_type},
            )

    def _decode_json(self, endpoint: str, response: HttpResponse) -> Any:
        try:
            return json.loads(response.text)
        except JSONDecodeError as exc:
            raise VeloInvalidResponseError(
                "Resposta Velo contem JSON malformado.",
                endpoint=endpoint,
                status_code=response.status_code,
                cause=exc,
            ) from exc


def _header_value(headers: dict[str, str], key: str) -> str:
    expected = key.casefold()
    for header, value in headers.items():
        if header.casefold() == expected:
            return value
    return ""


def _parse_forma_recebimento(item: object, *, endpoint: str) -> FormaRecebimentoApi:
    try:
        return FormaRecebimentoApi.model_validate(item)
    except ValidationError as exc:
        raise VeloSchemaError(
            "Item de autocomplete Velo invalido.",
            endpoint=endpoint,
            context={"erro_schema": _safe_validation_errors(exc)},
            cause=exc,
        ) from exc


def _parse_registro_sistema(
    item: object,
    *,
    endpoint: str,
    categoria: CategoriaFiltroVelo,
) -> RegistroSistema:
    try:
        registro_api = RegistroConciliacaoApi.model_validate(item)
    except ValidationError as exc:
        raise VeloSchemaError(
            "Registro de conciliacao Velo invalido.",
            endpoint=endpoint,
            context={"categoria": categoria.value, "erro_schema": _safe_validation_errors(exc)},
            cause=exc,
        ) from exc
    return map_registro_sistema(registro_api, categoria=categoria)


def _safe_validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    safe_errors: list[dict[str, Any]] = []
    for error in exc.errors(include_url=False, include_input=False):
        safe_errors.append(
            {
                "loc": [str(item) for item in error.get("loc", ())],
                "msg": str(error.get("msg", "")),
                "type": str(error.get("type", "")),
            }
        )
    return safe_errors
