from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from pathlib import Path

import pytest

from conciliacao.domain.enums import Modalidade, Operadora, OrigemRegistro
from conciliacao.domain.models import TransacaoOperadora
from conciliacao.processors.cielo_processor import CieloProcessingError, CieloProcessor
from conciliacao.readers.models import FormatoArquivo, MetadadosArquivo, ResultadoLeitura
from conciliacao.utils.text import normalize_text
from conciliacao.validators.cielo_validator import CieloValidator


def _tx(
    *,
    linha: int,
    venda: date = date(2026, 7, 13),
    pagamento: date = date(2026, 7, 14),
    hora: time = time(11, 35),
    modalidade: Modalidade = Modalidade.CREDITO,
    tipo: str = "Venda credito",
    forma: str = "Credito a vista",
    bandeira: str = "Visa",
    bruto: Decimal = Decimal("100.00"),
    taxa: Decimal = Decimal("-3.00"),
    liquido: Decimal = Decimal("97.00"),
) -> TransacaoOperadora:
    return TransacaoOperadora(
        identificador_origem=f"TX-{linha}",
        operadora=Operadora.CIELO,
        modalidade=modalidade,
        bandeira=bandeira,
        data_venda=venda,
        hora_venda=hora,
        data_recebimento=pagamento,
        valor_bruto=bruto,
        valor_liquido=liquido,
        taxa_normalizada=abs(taxa),
        taxa_original=taxa,
        origem_arquivo=OrigemRegistro.CIELO,
        linha_original=linha,
        dados_originais={
            "valores": {
                "Tipo de lancamento (A)": tipo,
                "Forma de pagamento (B)": forma,
            }
        },
    )


def _resultado(*transacoes: TransacaoOperadora) -> ResultadoLeitura:
    headers = [
        "Data de pagamento",
        "Tipo de lancamento",
        "Forma de pagamento",
        "Bandeira",
        "Valor bruto",
        "Taxa/tarifa",
        "Valor liquido",
        "Data da venda",
    ]
    return ResultadoLeitura(
        caminho_arquivo=Path("cielo.xlsx"),
        formato_detectado=FormatoArquivo.XLSX,
        nome_aba_ou_tabela="Recebiveis_cielo_detalhe1",
        cabecalhos_originais=headers,
        cabecalhos_normalizados=[normalize_text(header).comparavel for header in headers],
        transacoes=list(transacoes),
        metadados_arquivo=MetadadosArquivo(tamanho_bytes=10, modificado_em_ns=1),
        hash_sha256="abc",
    )


def _processar(resultado: ResultadoLeitura, inicio: date, fim: date):
    validacao = CieloValidator().validar(resultado, data_inicio=inicio, data_fim=fim)
    assert validacao.valido
    return CieloProcessor().processar(resultado, validacao, data_inicio=inicio, data_fim=fim)


def test_filters_period_and_counts_outside_transactions():
    result = _processar(
        _resultado(
            _tx(linha=11, venda=date(2026, 7, 12)),
            _tx(linha=12, venda=date(2026, 7, 13)),
        ),
        date(2026, 7, 13),
        date(2026, 7, 13),
    )

    assert result.resumo.transacoes_lidas == 2
    assert result.resumo.transacoes_incluidas == 1
    assert result.resumo.transacoes_fora_periodo == 1
    assert result.transacoes[0].linha_original == 12


def test_orders_credit_debit_and_pix_after_cards():
    result = _processar(
        _resultado(
            _tx(
                linha=13,
                modalidade=Modalidade.PIX,
                tipo="Venda Pix",
                forma="Pix",
                bandeira="Pix",
                hora=time(9, 0),
                bruto=Decimal("20.00"),
                taxa=Decimal("-0.20"),
                liquido=Decimal("19.80"),
            ),
            _tx(
                linha=12,
                modalidade=Modalidade.DEBITO,
                tipo="Venda debito",
                forma="Debito a vista",
                hora=time(8, 0),
            ),
            _tx(linha=11, modalidade=Modalidade.CREDITO, hora=time(10, 0)),
        ),
        date(2026, 7, 13),
        date(2026, 7, 13),
    )

    assert [transaction.linha_original for transaction in result.transacoes] == [11, 12, 13]
    assert result.resumo.blocos_cartao == 1
    assert result.resumo.blocos_pix == 1
    assert result.blocos[-1].tipo == "PIX"


def test_creates_dynamic_card_blocks_by_payment_date_and_one_pix_block():
    result = _processar(
        _resultado(
            _tx(linha=11, pagamento=date(2026, 7, 14)),
            _tx(linha=12, pagamento=date(2026, 7, 15)),
            _tx(
                linha=13,
                pagamento=date(2026, 7, 14),
                modalidade=Modalidade.PIX,
                tipo="Venda Pix",
                forma="Pix",
                bandeira="Pix",
                bruto=Decimal("10.00"),
                taxa=Decimal("-0.10"),
                liquido=Decimal("9.90"),
            ),
        ),
        date(2026, 7, 13),
        date(2026, 7, 13),
    )

    assert [(block.tipo, block.inicio_indice, block.fim_indice) for block in result.blocos] == [
        ("CARTAO", 0, 0),
        ("CARTAO", 1, 1),
        ("PIX", 2, 2),
    ]


def test_zero_gross_is_reported_and_invalid_financial_difference_blocks_processing():
    zero = _processar(
        _resultado(
            _tx(
                linha=11,
                bruto=Decimal("0.00"),
                taxa=Decimal("0.00"),
                liquido=Decimal("0.00"),
            )
        ),
        date(2026, 7, 13),
        date(2026, 7, 13),
    )

    assert zero.resumo.valor_bruto_zero == 1

    leitura = _resultado(_tx(linha=12, liquido=Decimal("96.99")))
    validacao = CieloValidator().validar(leitura)
    assert not validacao.valido
    with pytest.raises(CieloProcessingError):
        CieloProcessor().processar(
            leitura,
            validacao,
            data_inicio=date(2026, 7, 13),
            data_fim=date(2026, 7, 13),
        )
