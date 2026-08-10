from __future__ import annotations

from pathlib import Path

import pytest

from conciliacao.integrations.velo.audit import VeloAuditWriter
from conciliacao.integrations.velo.authentication import VeloTokenProvider
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
from conciliacao.integrations.velo.exceptions import VeloAuthenticationError
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
        audit=VeloAuditConfig(save_raw_responses=True, raw_directory=tmp_path),
    )


def test_token_provider_rejects_missing_and_empty_values(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("VELO_BEARER_TOKEN", raising=False)
    with pytest.raises(VeloAuthenticationError) as missing:
        VeloTokenProvider().get_token()

    monkeypatch.setenv("VELO_BEARER_TOKEN", "   ")
    with pytest.raises(VeloAuthenticationError) as empty:
        VeloTokenProvider().get_token()

    assert "token-teste-nao-real" not in str(missing.value)
    assert "token-teste-nao-real" not in repr(empty.value)


def test_token_provider_returns_artificial_token_only_for_internal_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fake_token = "token-teste-nao-real"
    monkeypatch.setenv("VELO_BEARER_TOKEN", fake_token)
    provider = VeloTokenProvider()
    transport = FakeVeloTransport(
        {"autoCompletarOperadora": json_response([])},
    )

    assert provider.get_token() == fake_token
    assert fake_token not in repr(provider)

    client = VeloClient(
        _config(tmp_path),
        token_provider=provider,
        transport=transport,
        audit_writer=VeloAuditWriter(_config(tmp_path).audit),
    )
    client.autocomplete_operadoras()

    assert transport.calls[0].headers["Authorization"] == f"Bearer {fake_token}"
    audit_file = next(tmp_path.glob("*/autocomplete_operadoras.json"))
    audit_text = audit_file.read_text(encoding="utf-8")
    assert fake_token not in audit_text
    assert "Authorization" not in audit_text
