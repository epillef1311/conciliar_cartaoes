from __future__ import annotations

from datetime import date
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
from conciliacao.integrations.velo.exceptions import VeloSchemaError
from conciliacao.integrations.velo.service import VeloIntegrationService
from conciliacao.integrations.velo.testing import FakeVeloTransport, json_response


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


def _service(
    tmp_path: Path, autocomplete_payload
) -> tuple[VeloIntegrationService, FakeVeloTransport]:
    transport = FakeVeloTransport({"autoCompletarOperadora": json_response(autocomplete_payload)})
    client = VeloClient(
        _config(tmp_path),
        token_provider=StaticTokenProvider("token-teste-nao-real"),
        transport=transport,
    )
    return VeloIntegrationService(client), transport


def test_resolves_all_known_ids_with_normalization_and_controlled_typo(tmp_path: Path):
    service, _transport = _service(
        tmp_path,
        [
            {"id": 81, "descricao": " Cartão\u00a0de Crédito - CIELO "},
            {"id": 86, "descricao": "Cartao de Debito - Cielo"},
            {"id": 91, "descricao": "pix - cielo"},
            {"id": 44, "descricao": "Cartão de Crédito - QuickPay"},
            {"id": 51, "descricao": "Cartão de Dédido - Quickpay"},
            {"id": 42, "descricao": "Pix - Quickpay"},
        ],
    )

    result = service.resolver_formas_recebimento()

    assert result.ids_por_categoria[CategoriaFiltroVelo.CIELO_CREDITO] == 81
    assert result.ids_por_categoria[CategoriaFiltroVelo.QUICKPAY_DEBITO] == 51
    assert any(aviso.codigo == "VELO_CORRECAO_CONTROLADA_FORMA" for aviso in result.avisos)


def test_missing_unknown_and_empty_autocomplete_use_configured_fallback(tmp_path: Path):
    missing_service, _ = _service(
        tmp_path,
        [{"id": 81, "descricao": "Cartão de Crédito - Cielo"}],
    )
    unknown_service, _ = _service(
        tmp_path,
        [{"id": 999, "descricao": "Forma Desconhecida"}],
    )
    empty_service, _ = _service(tmp_path, [])

    missing = missing_service.resolver_formas_recebimento()
    unknown = unknown_service.resolver_formas_recebimento()
    empty = empty_service.resolver_formas_recebimento()

    assert missing.ids_por_categoria[CategoriaFiltroVelo.QUICKPAY_PIX] == 42
    assert any(aviso.codigo == "VELO_FALLBACK_FORMA_RECEBIMENTO" for aviso in missing.avisos)
    assert any(aviso.codigo == "VELO_FORMA_DESCONHECIDA" for aviso in unknown.avisos)
    assert len(empty.ids_por_categoria) == 6


def test_duplicated_or_conflicting_autocomplete_ids_raise_schema_error(tmp_path: Path):
    duplicate_category, _ = _service(
        tmp_path,
        [
            {"id": 81, "descricao": "Cartão de Crédito - Cielo"},
            {"id": 82, "descricao": "Credito Cielo"},
        ],
    )
    duplicated_id, _ = _service(
        tmp_path,
        [
            {"id": 81, "descricao": "Cartão de Crédito - Cielo"},
            {"id": 81, "descricao": "Cartão de Débito - Cielo"},
        ],
    )

    with pytest.raises(VeloSchemaError):
        duplicate_category.resolver_formas_recebimento()
    with pytest.raises(VeloSchemaError):
        duplicated_id.resolver_formas_recebimento()


def test_consulting_all_categories_preserves_counts_without_matching(tmp_path: Path):
    fixtures = Path("tests/fixtures/api")
    config = _config(tmp_path)
    from conciliacao.integrations.velo.testing import FixtureVeloTransport

    transport = FixtureVeloTransport(fixtures, config)
    client = VeloClient(config, token_provider=StaticTokenProvider(), transport=transport)
    service = VeloIntegrationService(client)

    result = service.consultar_todas(
        data_inicio=date(2026, 7, 14),
        data_fim=date(2026, 7, 15),
    )

    assert len(result.registros_por_categoria[CategoriaFiltroVelo.CIELO_CREDITO]) == 3
    assert len(result.registros_por_categoria[CategoriaFiltroVelo.QUICKPAY_DEBITO]) == 0
    assert result.total_registros == 11
    assert len(transport.calls) == 7
