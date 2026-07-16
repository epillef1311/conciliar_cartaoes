from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from conciliacao.domain.enums import Modalidade, Operadora
from conciliacao.readers.exceptions import CabecalhoAmbiguoError, CabecalhoNaoEncontradoError
from conciliacao.readers.models import FormatoArquivo
from conciliacao.readers.quickpay_reader import ler_quickpay

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
