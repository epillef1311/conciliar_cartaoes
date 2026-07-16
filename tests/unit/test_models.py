from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from conciliacao.domain.enums import SeveridadeAlerta, StatusConciliacao
from conciliacao.domain.models import AlertaValidacao, RegistroSistema, ResultadoConciliacao


def test_operator_transaction_normalizes_fee_and_serializes(transacao_cielo):
    assert transacao_cielo.taxa_normalizada == Decimal("5.03")
    assert transacao_cielo.taxa_original == Decimal("-5.03")
    payload = transacao_cielo.model_dump(mode="json")
    assert payload["valor_bruto"] == "126.83"
    assert payload["data_venda"] == "2026-07-13"


def test_system_record_accepts_api_aliases_and_serializes_with_aliases():
    record = RegistroSistema.model_validate(
        {
            "contaPacotePagamentoUnicoId": "18888",
            "operadora": "Pix - Cielo",
            "forma_recebimento": "PIX - Cielo",
            "tipo_cartao": 5,
            "valor": "2,90",
            "dataCadastro": "2026-07-13",
            "dataVencimento": "2026-07-14",
            "cadastroCaixaId": "77",
            "identificadores_api": {"operadoraId": 91},
        }
    )

    assert record.data_cadastro == date(2026, 7, 13)
    assert record.model_dump(mode="json", by_alias=True)["dataCadastro"] == "2026-07-13"


def test_result_and_alert_models_validate_and_serialize(transacao_cielo):
    alert = AlertaValidacao(
        codigo="VALOR_DIVERGENTE",
        mensagem="Diferenca de um centavo",
        severidade=SeveridadeAlerta.AVISO,
        linha=11,
        celula="G11",
    )
    result = ResultadoConciliacao(
        transacao_operadora=transacao_cielo,
        status=StatusConciliacao.DIVERGENCIA_DE_VALOR,
        valor_operadora="126,83",
        valor_sistema="126,82",
        diferenca="0,01",
        quantidade_operadora=1,
        quantidade_sistema=1,
        chave_agrupamento="cielo|credito|2026-07-13|126.83",
        alertas=[alert],
    )

    assert result.model_dump(mode="json")["diferenca"] == "0.01"


def test_models_reject_unknown_fields_and_invalid_rows():
    with pytest.raises(ValidationError):
        AlertaValidacao(
            codigo="X",
            mensagem="Erro",
            severidade=SeveridadeAlerta.ERRO,
            linha=0,
            inesperado=True,
        )
