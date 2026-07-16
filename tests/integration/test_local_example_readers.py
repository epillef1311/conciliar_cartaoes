from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from conciliacao.readers.cielo_reader import ler_cielo
from conciliacao.readers.models import FormatoArquivo
from conciliacao.readers.quickpay_reader import ler_quickpay
from conciliacao.utils.currency import sum_money
from conciliacao.validators.cielo_validator import CieloValidator
from conciliacao.validators.quickpay_validator import QuickPayValidator

EXAMPLES = Path("arquivos_exemplo")
CIELO = (
    EXAMPLES / "CIELO VENDA 11.07.2026, 12.07.2026 E 13.07.2026 RECEBIMENTO 13.07.2026 .xls.xlsx"
)
QUICKPAY_HTML = EXAMPLES / "Lista de Transações.20260714094607.xls"
QUICKPAY_XLSX = EXAMPLES / "QUICKPAY VENDA 13.07.2026 RECEBIMENTO 14.07.2026 .xls.xlsx"


@pytest.mark.local
@pytest.mark.integration
@pytest.mark.skipif(not CIELO.exists(), reason="arquivo Cielo real nao esta disponivel localmente")
def test_reads_local_cielo_example_without_modifying_it():
    result = ler_cielo(CIELO)

    assert result.nome_aba_ou_tabela == "Recebiveis_cielo_detalhe1"
    assert len(result.transacoes) == 52
    assert sum_money(transaction.valor_bruto for transaction in result.transacoes) == Decimal(
        "4356.81"
    )
    assert sum_money(transaction.taxa_original for transaction in result.transacoes) == Decimal(
        "-67.69"
    )
    assert sum_money(transaction.valor_liquido for transaction in result.transacoes) == Decimal(
        "4289.12"
    )

    validation = CieloValidator().validar(result)
    assert validation.valido
    assert validation.totais_calculados["total_bruto"] == Decimal("4356.81")
    assert validation.totais_calculados["total_taxas_originais"] == Decimal("-67.69")


@pytest.mark.local
@pytest.mark.integration
@pytest.mark.skipif(
    not QUICKPAY_HTML.exists(), reason="arquivo QuickPay HTML real nao esta disponivel localmente"
)
def test_reads_local_quickpay_html_example_without_modifying_it():
    result = ler_quickpay(QUICKPAY_HTML)

    assert result.formato_detectado is FormatoArquivo.HTML
    assert len(result.transacoes) == 2
    assert result.cabecalhos_normalizados[0] == "data da venda"

    validation = QuickPayValidator().validar(result)
    assert not validation.valido
    assert {error.codigo for error in validation.erros} >= {"QUICKPAY_COLUNA_RECEBIDO_AUSENTE"}


@pytest.mark.local
@pytest.mark.integration
@pytest.mark.skipif(
    not QUICKPAY_XLSX.exists(), reason="arquivo QuickPay XLSX real nao esta disponivel localmente"
)
def test_reads_local_quickpay_xlsx_and_ignores_legacy_bank_block():
    result = ler_quickpay(QUICKPAY_XLSX)

    assert result.formato_detectado is FormatoArquivo.XLSX
    assert len(result.transacoes) == 2
    assert result.avisos_leitura[0].codigo == "COLUNA_BANCO_QUICKPAY_AUSENTE"

    validation = QuickPayValidator().validar(result)
    assert not validation.valido
    assert {error.codigo for error in validation.erros} >= {"QUICKPAY_COLUNA_RECEBIDO_AUSENTE"}
