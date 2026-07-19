from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from pathlib import Path

import pytest

from conciliacao.domain.enums import Modalidade, Operadora, OrigemRegistro
from conciliacao.domain.models import TransacaoOperadora
from conciliacao.processors.quickpay_processor import QuickPayProcessingError, QuickPayProcessor
from conciliacao.readers.models import FormatoArquivo, MetadadosArquivo, ResultadoLeitura
from conciliacao.utils.text import normalize_text
from conciliacao.validators.quickpay_validator import QuickPayValidator


def _tx(
    *,
    linha: int,
    venda: date = date(2026, 7, 13),
    recebimento: date = date(2026, 7, 14),
    hora: time = time(11, 35),
    tipo: str = "Credito",
    bandeira: str = "Visa",
    bruto: Decimal = Decimal("126.83"),
    taxa: Decimal = Decimal("5.03"),
    liquido: Decimal = Decimal("121.77"),
    banco: Decimal = Decimal("121.80"),
) -> TransacaoOperadora:
    return TransacaoOperadora(
        operadora=Operadora.QUICKPAY,
        modalidade=Modalidade.CREDITO,
        bandeira=bandeira,
        data_venda=venda,
        hora_venda=hora,
        data_recebimento=recebimento,
        numero_parcelas=1,
        valor_bruto=bruto,
        valor_liquido=liquido,
        taxa_normalizada=abs(taxa),
        taxa_original=taxa,
        origem_arquivo=OrigemRegistro.QUICKPAY,
        linha_original=linha,
        celulas_origem={
            "Valor da Venda (E)": f"E{linha}",
            "Valor liquido (F)": f"F{linha}",
            "Taxa (G)": f"G{linha}",
            "RECEBIDO NO BANCO QUICKPAY (I)": f"I{linha}",
        },
        dados_originais={
            "valores": {
                "Data da venda (A)": f"{venda:%d/%m/%Y} {hora:%H:%M}",
                "Data de recebimento (B)": recebimento,
                "Numero de Parcelas (C)": 1,
                "Tipo de pagamento (D)": tipo,
                "Valor da Venda (E)": bruto,
                "Valor liquido (F)": liquido,
                "Taxa (G)": taxa,
                "Bandeira (H)": bandeira,
                "RECEBIDO NO BANCO QUICKPAY (I)": banco,
            },
            "recebido_no_banco_quickpay_normalizado": banco,
        },
    )


def _resultado(*transacoes: TransacaoOperadora) -> ResultadoLeitura:
    headers = [
        "Data da venda",
        "Data de recebimento",
        "Numero de Parcelas",
        "Tipo de pagamento",
        "Valor da Venda",
        "Valor liquido",
        "Taxa",
        "Bandeira",
        "RECEBIDO NO BANCO QUICKPAY",
    ]
    return ResultadoLeitura(
        caminho_arquivo=Path("quickpay.xlsx"),
        formato_detectado=FormatoArquivo.XLSX,
        nome_aba_ou_tabela="Lista de Transacoes",
        cabecalhos_originais=headers,
        cabecalhos_normalizados=[normalize_text(header).comparavel for header in headers],
        transacoes=list(transacoes),
        metadados_arquivo=MetadadosArquivo(tamanho_bytes=10, modificado_em_ns=1),
        hash_sha256="abc",
    )


def _processar(resultado: ResultadoLeitura, inicio: date, fim: date):
    validacao = QuickPayValidator().validar(resultado, data_inicio=inicio, data_fim=fim)
    assert validacao.valido
    return QuickPayProcessor().processar(resultado, validacao, data_inicio=inicio, data_fim=fim)


def test_filters_period_and_counts_outside_transactions():
    relatorio = _processar(
        _resultado(
            _tx(linha=11, venda=date(2026, 7, 12)),
            _tx(linha=12, venda=date(2026, 7, 13)),
        ),
        date(2026, 7, 13),
        date(2026, 7, 13),
    )

    assert relatorio.resumo.transacoes_lidas == 2
    assert relatorio.resumo.transacoes_incluidas == 1
    assert relatorio.resumo.transacoes_fora_periodo == 1
    assert relatorio.linhas[0].transacao.linha_original == 12


def test_orders_by_receipt_sale_time_type_brand_and_amount_stably():
    relatorio = _processar(
        _resultado(
            _tx(linha=14, hora=time(9, 0), bandeira="Visa", bruto=Decimal("50.00")),
            _tx(linha=11, hora=time(8, 0), bandeira="Visa", bruto=Decimal("100.00")),
            _tx(linha=13, hora=time(8, 0), tipo="Debito", bandeira="Elo", bruto=Decimal("90.00")),
            _tx(linha=12, hora=time(8, 0), bandeira="MasterCard", bruto=Decimal("80.00")),
        ),
        date(2026, 7, 13),
        date(2026, 7, 13),
    )

    assert [linha.transacao.linha_original for linha in relatorio.linhas] == [12, 11, 13, 14]


def test_calculates_money_fields_and_preserves_one_cent_difference_and_bank_line():
    relatorio = _processar(
        _resultado(
            _tx(
                linha=11,
                bruto=Decimal("100.00"),
                taxa=Decimal("3.01"),
                liquido=Decimal("97.00"),
                banco=Decimal("96.99"),
            )
        ),
        date(2026, 7, 13),
        date(2026, 7, 13),
    )

    linha = relatorio.linhas[0]
    assert linha.bruto_liquido == Decimal("3.00")
    assert linha.diferenca_taxa == Decimal("0.01")
    assert linha.porcentagem == Decimal("0.0300")
    assert linha.recebido_banco == Decimal("96.99")
    assert linha.diferenca_banco == Decimal("-0.01")
    assert relatorio.resumo.total_diferenca_taxa == Decimal("0.01")


def test_zero_gross_keeps_percentage_blank_and_generates_summary_warning():
    relatorio = _processar(
        _resultado(
            _tx(
                linha=11,
                bruto=Decimal("0.00"),
                taxa=Decimal("0.00"),
                liquido=Decimal("0.00"),
                banco=Decimal("0.00"),
            )
        ),
        date(2026, 7, 13),
        date(2026, 7, 13),
    )

    assert relatorio.linhas[0].porcentagem is None
    assert relatorio.resumo.valor_bruto_zero == 1


def test_invalid_validation_or_blocking_financial_rules_stop_processing():
    leitura = _resultado(_tx(linha=11, taxa=Decimal("-3.00")))
    validacao = QuickPayValidator().validar(leitura)

    assert not validacao.valido
    with pytest.raises(QuickPayProcessingError):
        QuickPayProcessor().processar(
            leitura,
            validacao,
            data_inicio=date(2026, 7, 13),
            data_fim=date(2026, 7, 13),
        )
