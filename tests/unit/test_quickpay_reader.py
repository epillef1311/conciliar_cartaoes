from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from conciliacao.domain.enums import Modalidade, Operadora
from conciliacao.readers.exceptions import CabecalhoAmbiguoError, CabecalhoNaoEncontradoError
from conciliacao.readers.models import FormatoArquivo
from conciliacao.readers.quickpay_reader import _criar_transacao, ler_quickpay

FIXTURES = Path("tests/fixtures/quickpay")


def test_reads_quickpay_xlsx_with_nbsp_headers_and_bank_column():
    result = ler_quickpay(FIXTURES / "quickpay_valido.xlsx")

    assert result.formato_detectado is FormatoArquivo.XLSX
    assert "\u00a0" in result.cabecalhos_originais[0]
    assert result.cabecalhos_normalizados[0] == "data da venda"
    assert not result.avisos_leitura
    assert len(result.transacoes) == 2
    first = result.transacoes[0]
    assert first.operadora is Operadora.QUICKPAY
    assert first.modalidade is Modalidade.CREDITO
    assert first.hora_venda is not None
    assert first.dados_originais["recebido_no_banco_quickpay_normalizado"] == Decimal("121.80")
    assert first.celulas_origem["Valor da Venda\u00a0 (E)"] == "E3"


def test_reads_quickpay_html_and_warns_when_bank_column_is_missing():
    result = ler_quickpay(FIXTURES / "quickpay_html.xls")

    assert result.formato_detectado is FormatoArquivo.HTML
    assert len(result.transacoes) == 2
    assert result.transacoes[0].linha_original == 2
    assert result.transacoes[0].valor_bruto == Decimal("126.83")
    assert [warning.codigo for warning in result.avisos_leitura] == [
        "COLUNA_BANCO_QUICKPAY_AUSENTE"
    ]


def test_rejects_legacy_bank_block_outside_the_transaction_table():
    result = ler_quickpay(FIXTURES / "quickpay_legado.xlsx")

    assert len(result.transacoes) == 2
    assert result.avisos_leitura[0].codigo == "COLUNA_BANCO_QUICKPAY_AUSENTE"
    assert "recebido_no_banco_quickpay_normalizado" not in result.transacoes[0].dados_originais


def test_rejects_missing_or_ambiguous_quickpay_table():
    with pytest.raises(CabecalhoNaoEncontradoError):
        ler_quickpay(FIXTURES / "quickpay_sem_tabela.xlsx")
    with pytest.raises(CabecalhoAmbiguoError):
        ler_quickpay(FIXTURES / "quickpay_tabelas_ambiguas.xlsx")


def test_preserves_missing_installments_without_inventing_a_value():
    headers = [
        "Data da venda",
        "Data de recebimento",
        "Número de Parcelas",
        "Bandeira",
        "Tipo de pagamento",
        "Valor da Venda",
        "Taxa",
        "Valor líquido",
        "RECEBIDO NO BANCO QUICKPAY",
    ]
    transaction = _criar_transacao(
        values=[
            "17/07/2026 16:17",
            "20/07/2026",
            None,
            "Visa",
            "Débito",
            "134.12",
            "3.99",
            "131.45",
            "131.45",
        ],
        row_number=3,
        headers=headers,
        indices={
            "data_venda": 0,
            "data_recebimento": 1,
            "numero_parcelas": 2,
            "bandeira": 3,
            "tipo_pagamento": 4,
            "valor_venda": 5,
            "taxa": 6,
            "valor_liquido": 7,
        },
        banco_index=8,
        arquivo=Path("quickpay.xlsx"),
        aba="Conciliação",
    )

    assert transaction.numero_parcelas is None
    assert transaction.modalidade is Modalidade.DEBITO
