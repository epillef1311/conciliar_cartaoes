from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from pathlib import Path

from conciliacao.domain.enums import Modalidade, Operadora, OrigemRegistro
from conciliacao.domain.models import TransacaoOperadora
from conciliacao.readers.models import FormatoArquivo, MetadadosArquivo, ResultadoLeitura
from conciliacao.utils.text import normalize_text
from conciliacao.validators.cielo_validator import CieloValidator


def _cielo_tx(
    *,
    linha: int = 11,
    tipo: str = "Venda crédito",
    forma: str = "Crédito à vista",
    bandeira: str | None = "Visa",
    bruto: Decimal = Decimal("126.83"),
    taxa: Decimal = Decimal("-5.06"),
    liquido: Decimal = Decimal("121.77"),
    modalidade: Modalidade | None = Modalidade.CREDITO,
    tid: str | None = "TID-1",
    codigo_venda: str | None = None,
    nsu_doc: str | None = None,
    totalizador: dict[str, object] | None = None,
) -> TransacaoOperadora:
    valores = {
        "Data de pagamento (A)": date(2026, 7, 14),
        "Tipo de lançamento (B)": tipo,
        "Forma de pagamento (C)": forma,
        "Bandeira (D)": bandeira,
        "Valor bruto (E)": bruto,
        "Taxa/tarifa (F)": taxa,
        "Valor líquido (G)": liquido,
        "Data da venda (H)": date(2026, 7, 13),
        "Hora da venda (I)": time(11, 35),
        "TID (J)": tid,
        "NSU/DOC (K)": nsu_doc,
        "Código da venda (L)": codigo_venda,
    }
    raw = {
        "valores": valores,
        "campos_cielo": {
            "tid": tid,
            "nsu_doc": nsu_doc,
            "codigo_venda": codigo_venda,
        },
        "data_pagamento": date(2026, 7, 14),
    }
    if totalizador is not None:
        raw["totalizador_cielo"] = totalizador
    return TransacaoOperadora(
        identificador_origem=codigo_venda or tid or nsu_doc,
        operadora=Operadora.CIELO,
        modalidade=modalidade,
        bandeira=bandeira,
        data_venda=date(2026, 7, 13),
        hora_venda=time(11, 35),
        data_recebimento=date(2026, 7, 14),
        valor_bruto=bruto,
        valor_liquido=liquido,
        taxa_normalizada=abs(taxa),
        taxa_original=taxa,
        origem_arquivo=OrigemRegistro.CIELO,
        linha_original=linha,
        celulas_origem={
            "Tipo de lançamento (B)": f"B{linha}",
            "Forma de pagamento (C)": f"C{linha}",
            "Bandeira (D)": f"D{linha}",
            "Valor bruto (E)": f"E{linha}",
            "Taxa/tarifa (F)": f"F{linha}",
            "Valor líquido (G)": f"G{linha}",
        },
        dados_originais=raw,
    )


def _resultado(*txs: TransacaoOperadora, headers: list[str] | None = None) -> ResultadoLeitura:
    cabecalhos = headers or [
        "Data de pagamento",
        "Tipo de lançamento",
        "Forma de pagamento",
        "Bandeira",
        "Valor bruto",
        "Taxa/tarifa",
        "Valor líquido",
        "Data da venda",
    ]
    return ResultadoLeitura(
        caminho_arquivo=Path("cielo.xlsx"),
        formato_detectado=FormatoArquivo.XLSX,
        nome_aba_ou_tabela="Recebiveis_cielo_detalhe1",
        cabecalhos_originais=cabecalhos,
        cabecalhos_normalizados=[normalize_text(header).comparavel for header in cabecalhos],
        transacoes=list(txs),
        metadados_arquivo=MetadadosArquivo(tamanho_bytes=10, modificado_em_ns=1),
        hash_sha256="abc",
    )


def _codigos(resultado) -> set[str]:
    return {erro.codigo for erro in resultado.erros} | {aviso.codigo for aviso in resultado.avisos}


def test_cielo_valid_file_and_negative_fee():
    result = CieloValidator().validar(_resultado(_cielo_tx()))

    assert result.valido
    assert result.totais_calculados["total_bruto"] == Decimal("126.83")
    assert result.totais_calculados["total_taxas_originais"] == Decimal("-5.06")


def test_cielo_missing_required_header():
    result = CieloValidator().validar(_resultado(_cielo_tx(), headers=["Valor bruto"]))

    assert not result.valido
    assert "CIELO_DATA_PAGAMENTO_AUSENTE" in _codigos(result)


def test_cielo_invalid_transaction_type():
    tx = _cielo_tx(tipo="Venda voucher", modalidade=None)
    result = CieloValidator().validar(_resultado(tx))

    assert not result.valido
    assert "CIELO_TIPO_LANCAMENTO_DESCONHECIDO" in _codigos(result)


def test_cielo_incoherent_payment_form():
    tx = _cielo_tx(tipo="Venda crédito", forma="Débito à vista")
    result = CieloValidator().validar(_resultado(tx))

    assert not result.valido
    assert "CIELO_FORMA_PAGAMENTO_INCOERENTE" in _codigos(result)


def test_cielo_positive_fee_warns_but_financial_rule_may_pass():
    tx = _cielo_tx(taxa=Decimal("5.06"))
    result = CieloValidator().validar(_resultado(tx))

    assert result.valido
    assert "CIELO_TAXA_POSITIVA" in _codigos(result)


def test_cielo_one_cent_difference_and_fee_greater_than_gross():
    diff = CieloValidator().validar(_resultado(_cielo_tx(liquido=Decimal("121.78"))))
    high_fee = CieloValidator().validar(
        _resultado(_cielo_tx(bruto=Decimal("5.00"), taxa=Decimal("-5.01"), liquido=Decimal("0.00")))
    )

    assert "CIELO_INCONSISTENCIA_FINANCEIRA" in _codigos(diff)
    assert "CIELO_TAXA_MAIOR_QUE_BRUTO" in _codigos(high_fee)


def test_cielo_totalizer_correct_and_divergent():
    ok = CieloValidator().validar(
        _resultado(
            _cielo_tx(
                totalizador={
                    "quantidade_lancamentos": 1,
                    "valor_bruto": "126,83",
                    "taxa_tarifa": "-5,06",
                    "valor_liquido": "121,77",
                }
            )
        )
    )
    bad = CieloValidator().validar(
        _resultado(
            _cielo_tx(
                totalizador={
                    "quantidade_lancamentos": 1,
                    "valor_bruto": "126,84",
                    "taxa_tarifa": "-5,06",
                    "valor_liquido": "121,77",
                }
            )
        )
    )

    assert ok.valido
    assert "CIELO_TOTALIZADOR_BRUTO_DIVERGENTE" in _codigos(bad)


def test_cielo_tid_duplicate_and_possible_duplicate_combination():
    duplicate_id = CieloValidator().validar(_resultado(_cielo_tx(linha=11), _cielo_tx(linha=12)))
    possible = CieloValidator().validar(
        _resultado(_cielo_tx(linha=11, tid=None), _cielo_tx(linha=12, tid=None))
    )

    assert "CIELO_TID_DUPLICADO" in _codigos(duplicate_id)
    assert "CIELO_POSSIVEL_DUPLICIDADE" in _codigos(possible)


def test_cielo_period_warnings_and_pix_or_card_brand_rules():
    outside = CieloValidator().validar(
        _resultado(_cielo_tx()),
        data_inicio=date(2026, 7, 14),
        data_fim=date(2026, 7, 14),
    )
    pix = CieloValidator().validar(
        _resultado(
            _cielo_tx(
                tipo="Venda Pix",
                forma="Pix",
                bandeira="Pix",
                modalidade=Modalidade.PIX,
            )
        )
    )
    no_brand = CieloValidator().validar(_resultado(_cielo_tx(bandeira=None)))

    assert outside.valido
    assert outside.periodo_encontrado.quantidade_fora_periodo == 1
    assert "TRANSACOES_FORA_DO_PERIODO" in _codigos(outside)
    assert pix.valido
    assert "CIELO_CARTAO_SEM_BANDEIRA" in _codigos(no_brand)


def test_cielo_preserves_distinct_installments_of_same_sale():
    first = _cielo_tx(linha=11, codigo_venda="VENDA-1", nsu_doc="NSU-1")
    second = _cielo_tx(linha=12, codigo_venda="VENDA-1", nsu_doc="NSU-1")
    first.dados_originais["campos_cielo"]["numero_parcela"] = "01"
    second.dados_originais["campos_cielo"]["numero_parcela"] = "02"
    reading = _resultado(first, second)
    result = CieloValidator().validar(reading)
    assert result.valido
    assert len(reading.transacoes) == 2
    assert result.totais_calculados["total_bruto"] == Decimal("253.66")


def test_cielo_same_installment_still_fails_with_line_numbers():
    first = _cielo_tx(linha=11, codigo_venda="VENDA-1", nsu_doc="NSU-1")
    second = _cielo_tx(linha=12, codigo_venda="VENDA-1", nsu_doc="NSU-1")
    first.dados_originais["campos_cielo"]["numero_parcela"] = "01"
    second.dados_originais["campos_cielo"]["numero_parcela"] = "1"
    result = CieloValidator().validar(_resultado(first, second))
    assert not result.valido
    duplicate = next(
        error for error in result.erros if error.codigo == "CIELO_CODIGO_VENDA_DUPLICADO"
    )
    assert "[11, 12]" in duplicate.mensagem
    assert duplicate.linha == 11


def test_cielo_missing_installment_is_not_inferred():
    first = _cielo_tx(linha=11, codigo_venda="VENDA-1")
    second = _cielo_tx(linha=12, codigo_venda="VENDA-1")
    first.dados_originais["campos_cielo"]["numero_parcela"] = "01"
    result = CieloValidator().validar(_resultado(first, second))
    assert "CIELO_CODIGO_VENDA_DUPLICADO" in _codigos(result)
