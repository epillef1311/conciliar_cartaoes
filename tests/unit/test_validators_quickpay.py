from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from pathlib import Path

from conciliacao.domain.enums import Modalidade, Operadora, OrigemRegistro
from conciliacao.domain.models import TransacaoOperadora
from conciliacao.readers.models import FormatoArquivo, MetadadosArquivo, ResultadoLeitura
from conciliacao.utils.text import normalize_text
from conciliacao.validators.quickpay_validator import QuickPayValidator


def _quickpay_tx(
    *,
    linha: int = 3,
    banco: Decimal | None = Decimal("121.77"),
    banco_raw: object | None = Decimal("121.77"),
    bruto: Decimal = Decimal("126.83"),
    taxa: Decimal = Decimal("5.06"),
    liquido: Decimal = Decimal("121.77"),
    parcelas: int = 1,
) -> TransacaoOperadora:
    valores = {
        "Data da venda (A)": "13/07/2026 11:35",
        "Data de recebimento (B)": date(2026, 7, 14),
        "Número de Parcelas (C)": parcelas,
        "Tipo de pagamento (D)": "Crédito",
        "Valor da Venda (E)": bruto,
        "Valor líquido (F)": liquido,
        "Taxa (G)": taxa,
        "Bandeira (H)": "Visa",
        "RECEBIDO NO BANCO QUICKPAY (I)": banco_raw,
    }
    raw = {"valores": valores, "linha_original": linha}
    if banco is not None:
        raw["recebido_no_banco_quickpay_normalizado"] = banco
    return TransacaoOperadora(
        operadora=Operadora.QUICKPAY,
        modalidade=Modalidade.CREDITO,
        bandeira="Visa",
        data_venda=date(2026, 7, 13),
        hora_venda=time(11, 35),
        data_recebimento=date(2026, 7, 14),
        numero_parcelas=parcelas,
        valor_bruto=bruto,
        valor_liquido=liquido,
        taxa_normalizada=abs(taxa),
        taxa_original=taxa,
        origem_arquivo=OrigemRegistro.QUICKPAY,
        linha_original=linha,
        celulas_origem={
            "Valor da Venda (E)": f"E{linha}",
            "Valor líquido (F)": f"F{linha}",
            "Taxa (G)": f"G{linha}",
            "RECEBIDO NO BANCO QUICKPAY (I)": f"I{linha}",
        },
        dados_originais=raw,
    )


def _resultado(*txs: TransacaoOperadora, headers: list[str] | None = None) -> ResultadoLeitura:
    cabecalhos = headers or [
        "Data da venda",
        "Data de recebimento",
        "Número de Parcelas",
        "Tipo de pagamento",
        "Valor da Venda",
        "Valor líquido",
        "Taxa",
        "Bandeira",
        "RECEBIDO NO BANCO QUICKPAY",
    ]
    return ResultadoLeitura(
        caminho_arquivo=Path("quickpay.xlsx"),
        formato_detectado=FormatoArquivo.XLSX,
        nome_aba_ou_tabela="Lista de Transações",
        cabecalhos_originais=cabecalhos,
        cabecalhos_normalizados=[normalize_text(header).comparavel for header in cabecalhos],
        transacoes=list(txs),
        metadados_arquivo=MetadadosArquivo(tamanho_bytes=10, modificado_em_ns=1),
        hash_sha256="abc",
    )


def _codigos(resultado) -> set[str]:
    return {erro.codigo for erro in resultado.erros} | {aviso.codigo for aviso in resultado.avisos}


def test_quickpay_valid_file_with_bank_column_and_positive_fee():
    result = QuickPayValidator().validar(_resultado(_quickpay_tx()))

    assert result.valido
    assert result.totais_calculados["total_bruto"] == Decimal("126.83")
    assert result.totais_calculados["total_recebido_banco"] == Decimal("121.77")


def test_quickpay_missing_and_duplicated_bank_column():
    missing = QuickPayValidator().validar(
        _resultado(_quickpay_tx(banco=None), headers=["Data da venda", "Valor da Venda"])
    )
    duplicated = QuickPayValidator().validar(
        _resultado(
            _quickpay_tx(),
            headers=[
                "Data da venda",
                "Data de recebimento",
                "Número de Parcelas",
                "Tipo de pagamento",
                "Valor da Venda",
                "Valor líquido",
                "Taxa",
                "Bandeira",
                "RECEBIDO NO BANCO QUICKPAY",
                "RECEBIDO NO BANCO QUICKPAY",
            ],
        )
    )

    assert "QUICKPAY_COLUNA_RECEBIDO_AUSENTE" not in _codigos(missing)
    assert "QUICKPAY_COLUNA_RECEBIDO_DUPLICADA" in _codigos(duplicated)


def test_quickpay_empty_invalid_negative_and_formula_bank_values():
    empty = QuickPayValidator().validar(_resultado(_quickpay_tx(banco=None, banco_raw=None)))
    invalid = QuickPayValidator().validar(_resultado(_quickpay_tx(banco=None, banco_raw="texto")))
    negative = QuickPayValidator().validar(
        _resultado(_quickpay_tx(banco=Decimal("-1.00"), banco_raw=Decimal("-1.00")))
    )
    formula_error = QuickPayValidator().validar(
        _resultado(_quickpay_tx(banco=None, banco_raw="#DIV/0!"))
    )

    assert empty.valido
    assert "QUICKPAY_CONFERENCIA_BANCARIA_NAO_REALIZADA" in _codigos(empty)
    assert empty.totais_calculados["total_recebido_banco"] is None
    assert empty.totais_calculados["diferenca_total_banco_liquido"] is None
    assert "QUICKPAY_RECEBIDO_INVALIDO" in _codigos(invalid)
    assert "QUICKPAY_RECEBIDO_NEGATIVO" in _codigos(negative)
    assert "QUICKPAY_RECEBIDO_INVALIDO" in _codigos(formula_error)


def test_quickpay_fee_rules_one_cent_and_zero_gross():
    negative_fee = QuickPayValidator().validar(_resultado(_quickpay_tx(taxa=Decimal("-5.06"))))
    one_cent = QuickPayValidator().validar(_resultado(_quickpay_tx(taxa=Decimal("5.05"))))
    zero = QuickPayValidator().validar(
        _resultado(
            _quickpay_tx(
                bruto=Decimal("0.00"),
                taxa=Decimal("0.00"),
                liquido=Decimal("0.00"),
                banco=Decimal("0.00"),
            )
        )
    )
    high_fee = QuickPayValidator().validar(
        _resultado(
            _quickpay_tx(
                bruto=Decimal("5.00"),
                taxa=Decimal("5.01"),
                liquido=Decimal("0.00"),
                banco=Decimal("0.00"),
            )
        )
    )

    assert "QUICKPAY_TAXA_NEGATIVA" in _codigos(negative_fee)
    assert "QUICKPAY_DIFERENCA_TAXA" in _codigos(one_cent)
    assert "QUICKPAY_VALOR_BRUTO_ZERO" in _codigos(zero)
    assert zero.valido
    assert "QUICKPAY_TAXA_MAIOR_QUE_VALOR_VENDA" in _codigos(high_fee)


def test_quickpay_bank_difference_positive_and_negative():
    positive = QuickPayValidator().validar(
        _resultado(_quickpay_tx(banco=Decimal("121.78"), banco_raw=Decimal("121.78")))
    )
    negative = QuickPayValidator().validar(
        _resultado(_quickpay_tx(banco=Decimal("121.76"), banco_raw=Decimal("121.76")))
    )

    assert positive.valido
    assert negative.valido
    assert "QUICKPAY_DIFERENCA_BANCO" in _codigos(positive)
    assert "QUICKPAY_DIFERENCA_BANCO" in _codigos(negative)


def test_quickpay_possible_duplicate_and_outside_period():
    duplicate = QuickPayValidator().validar(_resultado(_quickpay_tx(), _quickpay_tx(linha=4)))
    outside = QuickPayValidator().validar(
        _resultado(_quickpay_tx()),
        data_inicio=date(2026, 7, 14),
        data_fim=date(2026, 7, 14),
    )

    assert "QUICKPAY_POSSIVEL_DUPLICIDADE" in _codigos(duplicate)
    assert outside.valido
    assert outside.periodo_encontrado.quantidade_fora_periodo == 1
    assert "TRANSACOES_FORA_DO_PERIODO" in _codigos(outside)
