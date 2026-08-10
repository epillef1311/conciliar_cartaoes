from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from conciliacao.integrations.velo.authentication import StaticTokenProvider
from conciliacao.integrations.velo.categories import CategoriaFiltroVelo
from conciliacao.integrations.velo.client import VeloClient
from conciliacao.integrations.velo.config import (
    VeloApiConfig,
    VeloAuditConfig,
    VeloEndpointsConfig,
    VeloQueryConfig,
    VeloRetriesConfig,
    VeloTimeoutsConfig,
)
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
from conciliacao.integrations.velo.testing import FakeVeloTransport, json_response, text_response


def _config(tmp_path: Path) -> VeloApiConfig:
    return VeloApiConfig(
        base_url="https://api.example.invalid",
        endpoints=VeloEndpointsConfig(
            autocomplete_operadoras="/autoCompletarOperadora",
            conciliacao_recebidos="/listarConciliacaoCartaoRecebido",
        ),
        query=VeloQueryConfig(intervalo_dia=-1, is_compensado=0),
        formas_recebimento_fallback={
            CategoriaFiltroVelo.CIELO_CREDITO: 81,
            CategoriaFiltroVelo.CIELO_DEBITO: 86,
            CategoriaFiltroVelo.CIELO_PIX: 91,
            CategoriaFiltroVelo.QUICKPAY_CREDITO: 44,
            CategoriaFiltroVelo.QUICKPAY_DEBITO: 51,
            CategoriaFiltroVelo.QUICKPAY_PIX: 42,
        },
        timeouts=VeloTimeoutsConfig(connect_seconds=10, read_seconds=30),
        retries=VeloRetriesConfig(enabled=False, max_attempts=1),
        audit=VeloAuditConfig(save_raw_responses=False, raw_directory=tmp_path),
    )


def _valid_record(**overrides):
    payload = {
        "contaPacotePagamentoUnicoId": "CC-001",
        "operadoraId": 81,
        "operadora": "Cielo",
        "cadastroCaixaId": "CX-1",
        "formaRecebimentoId": 81,
        "formaRecebimento": "Cartão de Crédito - Cielo",
        "tipoCartao": "Visa",
        "valor": "126.83",
        "valorTaxaCartao": "0.00",
        "dataVencimento": "2026-07-15",
        "dataCadastro": "2026-07-14",
        "campoExtraFuturo": "preservado",
    }
    payload.update(overrides)
    return payload


def _client(tmp_path: Path, response) -> tuple[VeloClient, FakeVeloTransport]:
    transport = FakeVeloTransport({"listarConciliacaoCartaoRecebido": response})
    client = VeloClient(
        _config(tmp_path),
        token_provider=StaticTokenProvider("token-teste-nao-real"),
        transport=transport,
    )
    return client, transport


def test_conciliation_request_uses_documented_params_and_preserves_records(tmp_path: Path):
    records = [_valid_record(), _valid_record(contaPacotePagamentoUnicoId="CC-002")]
    client, transport = _client(tmp_path, json_response(records))

    result = client.consultar_conciliacao(
        categoria=CategoriaFiltroVelo.CIELO_CREDITO,
        filtro_forma_recebimento_id=81,
        data_inicio=date(2026, 7, 14),
        data_fim=date(2026, 7, 15),
    )

    call = transport.calls[0]
    assert call.params == {
        "operadoraId": 81,
        "intervaloDia": -1,
        "dataInicio": "2026-07-14",
        "dataFim": "2026-07-15",
        "isCompensado": 0,
    }
    assert call.timeout == (10, 30)
    assert len(result) == 2
    assert [record.id_sistema for record in result] == ["CC-001", "CC-002"]
    assert result[0].valor == Decimal("126.83")
    assert result[0].valor_taxa_cartao == Decimal("0.00")
    assert not isinstance(result[0].valor, float)
    assert result[0].dados_originais is not None
    assert result[0].dados_originais["campoExtraFuturo"] == "preservado"


def test_empty_conciliation_response_is_valid(tmp_path: Path):
    client, _transport = _client(tmp_path, json_response([]))

    assert client.consultar_conciliacao(
        categoria=CategoriaFiltroVelo.CIELO_PIX,
        filtro_forma_recebimento_id=91,
        data_inicio=date(2026, 7, 14),
        data_fim=date(2026, 7, 14),
    ) == []


def test_conciliation_record_accepts_integer_auxiliary_action(tmp_path: Path):
    client, _transport = _client(tmp_path, json_response([_valid_record(acao=1)]))

    result = client.consultar_conciliacao(
        categoria=CategoriaFiltroVelo.CIELO_CREDITO,
        filtro_forma_recebimento_id=81,
        data_inicio=date(2026, 7, 14),
        data_fim=date(2026, 7, 14),
    )

    assert len(result) == 1


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        ([_valid_record(contaPacotePagamentoUnicoId=None)], "Registro de conciliacao"),
        ([_valid_record(valor="abc")], "Registro de conciliacao"),
        ([_valid_record(valor=float("nan"))], "Registro de conciliacao"),
        ([_valid_record(dataCadastro="14/07/2026")], "Registro de conciliacao"),
        ([_valid_record(dataVencimento="data")], "Registro de conciliacao"),
        ({"erro": "objeto"}, "lista JSON"),
    ],
)
def test_invalid_contract_payloads_raise_schema_error(
    tmp_path: Path, payload, expected_message: str
):
    client, _transport = _client(tmp_path, json_response(payload))

    with pytest.raises(VeloSchemaError) as exc_info:
        client.consultar_conciliacao(
            categoria=CategoriaFiltroVelo.CIELO_CREDITO,
            filtro_forma_recebimento_id=81,
            data_inicio=date(2026, 7, 14),
            data_fim=date(2026, 7, 14),
        )

    assert expected_message in str(exc_info.value)
    assert "token-teste-nao-real" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (400, VeloBadRequestError),
        (401, VeloAuthenticationError),
        (403, VeloAuthorizationError),
        (404, VeloEndpointNotFoundError),
        (429, VeloRateLimitError),
        (500, VeloServerError),
        (503, VeloServerError),
    ],
)
def test_http_errors_are_mapped_without_retry_or_token_leak(
    tmp_path: Path, status_code: int, expected_error: type[Exception]
):
    client, transport = _client(tmp_path, json_response({"erro": "x"}, status_code=status_code))

    with pytest.raises(expected_error) as exc_info:
        client.consultar_conciliacao(
            categoria=CategoriaFiltroVelo.CIELO_CREDITO,
            filtro_forma_recebimento_id=81,
            data_inicio=date(2026, 7, 14),
            data_fim=date(2026, 7, 14),
        )

    assert len(transport.calls) == 1
    assert "token-teste-nao-real" not in str(exc_info.value)


def test_transport_timeout_and_connection_errors_are_mapped(tmp_path: Path):
    timeout_client = VeloClient(
        _config(tmp_path),
        token_provider=StaticTokenProvider("token-teste-nao-real"),
        transport=FakeVeloTransport(timeout=True),
    )
    connection_client = VeloClient(
        _config(tmp_path),
        token_provider=StaticTokenProvider("token-teste-nao-real"),
        transport=FakeVeloTransport(connection_error=True),
    )

    with pytest.raises(VeloTimeoutError):
        timeout_client.autocomplete_operadoras()
    with pytest.raises(VeloConnectionError):
        connection_client.autocomplete_operadoras()


def test_invalid_content_type_and_malformed_json_are_invalid_responses(tmp_path: Path):
    html_client, _ = _client(
        tmp_path,
        text_response("<html></html>", content_type="text/html"),
    )
    malformed_client, _ = _client(tmp_path, text_response("{malformado"))

    with pytest.raises(VeloInvalidResponseError):
        html_client.consultar_conciliacao(
            categoria=CategoriaFiltroVelo.CIELO_CREDITO,
            filtro_forma_recebimento_id=81,
            data_inicio=date(2026, 7, 14),
            data_fim=date(2026, 7, 14),
        )
    with pytest.raises(VeloInvalidResponseError):
        malformed_client.consultar_conciliacao(
            categoria=CategoriaFiltroVelo.CIELO_CREDITO,
            filtro_forma_recebimento_id=81,
            data_inicio=date(2026, 7, 14),
            data_fim=date(2026, 7, 14),
        )
