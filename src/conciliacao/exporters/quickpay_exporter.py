"""Exportador Excel do relatorio QuickPay sem API e sem matching."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from conciliacao.domain.enums import Modalidade, StatusConciliacao
from conciliacao.matching.models import ResultadoConciliacaoOperadora, ResultadoIndividualMatching
from conciliacao.processors.quickpay_processor import (
    QuickPayGrupoBancario,
    QuickPayLinhaProcessada,
    QuickPayRelatorioProcessado,
)
from conciliacao.utils.currency import quantize_money

QUICKPAY_HEADERS = [
    "Data da venda",
    "Data de recebimento",
    "Número de Parcelas",
    "Bandeira",
    "Tipo de pagamento",
    "Valor da Venda",
    "Taxa",
    "Valor líquido",
    "Bruto-Líquido",
    "Diferença",
    "Porcentagem",
    "RECEBIDO NO BANCO QUICKPAY",
    "Sistema",
    "Diferença Sistema",
    "Status",
    "Soma Valor da Venda",
    "Soma Valor Líquido",
]

STATUS_PENDENTE = "PENDENTE DE CONCILIAÇÃO COM SISTEMA"
SHEET_NAME = "Conciliação"
BANK_SHEET_NAME = "Conciliação Bancária"
MATCHING_SHEET_NAME = "Conciliação QuickPay × Velo"
MATCHING_HEADERS = [
    "Origem",
    "Linha QuickPay",
    "Data da venda",
    "Bandeira",
    "Valor QuickPay",
    "Valor Velo",
    "Diferença",
    "Status",
    "Nível de confiança",
]
STATUS_LABELS = {
    StatusConciliacao.CONCILIADO: "CONCILIADO",
    StatusConciliacao.DIVERGENCIA_DE_VALOR: "DIVERGENCIA DE VALOR",
    StatusConciliacao.DIVERGENCIA_DE_QUANTIDADE: "DIVERGENCIA DE QUANTIDADE",
    StatusConciliacao.NAO_ENCONTRADO_NO_SISTEMA: "NAO ENCONTRADO NO SISTEMA",
    StatusConciliacao.NAO_ENCONTRADO_NA_OPERADORA: "NAO ENCONTRADO NA OPERADORA",
    StatusConciliacao.CORRESPONDENCIA_AMBIGUA: "CORRESPONDENCIA AMBIGUA",
    StatusConciliacao.PENDENTE_DE_DADOS: "PENDENTE DE DADOS",
}
MONEY_FORMAT = r"\R\$\ * #,##0.00;[Red]\-\R\$\ * #,##0.00"
PERCENT_FORMAT = "0.00%"
DATE_FORMAT = "dd/mm/yyyy"
TIME_FORMAT = "hh:mm"


@dataclass(frozen=True, slots=True)
class QuickPayExportResult:
    caminho_saida: Path
    total_row: int
    ultima_linha_transacao: int
    subtotal_rows: tuple[int, ...]
    validacao_saida_ok: bool


class QuickPayExporter:
    def exportar(
        self,
        relatorio: QuickPayRelatorioProcessado,
        *,
        diretorio_saida: str | Path,
        sobrescrever: bool = False,
        matching: ResultadoConciliacaoOperadora | None = None,
    ) -> QuickPayExportResult:
        output_dir = Path(diretorio_saida)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = _resolver_saida(
            output_dir / f"QUICKPAY_CONCILIACAO_{relatorio.data_inicio.isoformat()}_A_"
            f"{relatorio.data_fim.isoformat()}.xlsx",
            sobrescrever=sobrescrever,
        )

        workbook = Workbook()
        worksheet = cast(Worksheet, workbook.active)
        if worksheet is None:
            raise ValueError("nao foi possivel criar a aba Conciliação")
        worksheet.title = SHEET_NAME
        _escrever_planilha(worksheet, relatorio, matching=matching)
        if matching is not None:
            _escrever_comparacao_velo(workbook.create_sheet(MATCHING_SHEET_NAME), matching)
        if relatorio.grupos_bancarios:
            _escrever_conciliacao_bancaria(
                workbook.create_sheet(BANK_SHEET_NAME), relatorio.grupos_bancarios
            )
        workbook.save(output_path)
        workbook.close()

        result = QuickPayExportResult(
            caminho_saida=output_path,
            total_row=3 + len(relatorio.linhas),
            ultima_linha_transacao=2 + len(relatorio.linhas),
            subtotal_rows=_linhas_subtotal_bloco(relatorio),
            validacao_saida_ok=False,
        )
        _validar_exportacao(output_path, relatorio, result, matching=matching)
        return QuickPayExportResult(
            caminho_saida=result.caminho_saida,
            total_row=result.total_row,
            ultima_linha_transacao=result.ultima_linha_transacao,
            subtotal_rows=result.subtotal_rows,
            validacao_saida_ok=True,
        )


def _escrever_planilha(
    worksheet: Worksheet,
    relatorio: QuickPayRelatorioProcessado,
    *,
    matching: ResultadoConciliacaoOperadora | None,
) -> None:
    worksheet["A1"] = relatorio.titulo
    worksheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(QUICKPAY_HEADERS))
    worksheet.row_dimensions[1].height = 24
    worksheet.row_dimensions[2].height = 34

    for column, header in enumerate(QUICKPAY_HEADERS, start=1):
        cell = worksheet.cell(2, column, header)
        cell.fill = _yellow_fill()
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _thin_border()

    matching_por_linha = _matching_por_linha(matching)
    for index, linha in enumerate(relatorio.linhas, start=3):
        _escrever_linha(
            worksheet,
            index,
            linha,
            matching_por_linha.get(linha.transacao.linha_original),
        )
    _escrever_subtotais_bloco(worksheet, relatorio)
    _escrever_total_geral(worksheet, relatorio)
    _aplicar_estilo(worksheet, relatorio, 3 + len(relatorio.linhas))


def _escrever_linha(
    worksheet: Worksheet,
    row: int,
    linha: QuickPayLinhaProcessada,
    matching: ResultadoIndividualMatching | None,
) -> None:
    transacao = linha.transacao
    sistema, diferenca_sistema, status = _campos_sistema(transacao.valor_bruto, matching)
    values = [
        transacao.data_venda,
        transacao.data_recebimento,
        transacao.numero_parcelas,
        transacao.bandeira,
        linha.tipo_pagamento,
        transacao.valor_bruto,
        transacao.taxa_original,
        transacao.valor_liquido,
        f"=F{row}-H{row}",
        f"=G{row}-I{row}",
        f'=IF(F{row}=0,"",1-(H{row}/F{row}))',
        linha.recebido_banco
        if linha.recebido_banco is not None
        else ("VER ABA CONCILIAÇÃO BANCÁRIA" if linha.grupo_bancario else "NÃO INFORMADO"),
        sistema,
        diferenca_sistema,
        status,
    ]
    for column, value in enumerate(values, start=1):
        worksheet.cell(row, column, value)


def _escrever_total_geral(worksheet: Worksheet, relatorio: QuickPayRelatorioProcessado) -> None:
    total_row = 3 + len(relatorio.linhas)
    last_transaction = total_row - 1
    worksheet.cell(total_row, 5, "TOTAL")
    for column in (6, 7, 8, 9, 10, 13, 14):
        letter = get_column_letter(column)
        worksheet.cell(total_row, column, f"=SUM({letter}3:{letter}{last_transaction})")
    worksheet.cell(
        total_row,
        12,
        f"=SUM('{BANK_SHEET_NAME}'!F3:F{2 + len(relatorio.grupos_bancarios)})"
        if relatorio.grupos_bancarios
        else (
            f"=SUM(L3:L{last_transaction})"
            if relatorio.resumo.total_recebido_banco is not None
            else "CONFERÊNCIA BANCÁRIA NÃO REALIZADA: RECEBIMENTOS NÃO INFORMADOS OU INCOMPLETOS"
        ),
    )


def _escrever_conciliacao_bancaria(
    worksheet: Worksheet, grupos: tuple[QuickPayGrupoBancario, ...]
) -> None:
    headers = [
        "Data de recebimento",
        "Bandeira",
        "Modalidade",
        "Transações",
        "Líquido QuickPay",
        "Recebido no banco",
        "Diferença",
        "Status",
    ]
    worksheet.append(["COMPARAÇÃO DOS RECEBIMENTOS BANCÁRIOS QUICKPAY"])
    worksheet.merge_cells("A1:H1")
    worksheet.append(headers)
    for grupo in grupos:
        worksheet.append(
            [
                grupo.data_recebimento,
                grupo.bandeira,
                grupo.modalidade.value.title(),
                grupo.quantidade_transacoes,
                grupo.total_liquido_quickpay,
                grupo.valor_recebido_banco,
                grupo.diferenca_banco,
                grupo.status,
            ]
        )
    for cell in worksheet[1]:
        cell.font = Font(bold=True, size=12)
    for cell in worksheet[2]:
        cell.fill = _yellow_fill()
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = _thin_border()
    for row in range(3, worksheet.max_row + 1):
        worksheet.cell(row, 1).number_format = DATE_FORMAT
        for col in (5, 6, 7):
            worksheet.cell(row, col).number_format = MONEY_FORMAT
        for col in range(1, 9):
            worksheet.cell(row, col).border = _thin_border()
    widths = {"A": 20, "B": 18, "C": 16, "D": 14, "E": 20, "F": 21, "G": 16, "H": 22}
    for column_letter, width in widths.items():
        worksheet.column_dimensions[column_letter].width = width
    worksheet.freeze_panes = "A3"


def _escrever_comparacao_velo(
    worksheet: Worksheet, matching: ResultadoConciliacaoOperadora
) -> None:
    """Replica a estrutura da segunda aba Cielo para a conciliação QuickPay."""
    worksheet.sheet_view.showGridLines = False
    worksheet.merge_cells("A1:I1")
    worksheet["A1"] = "CONCILIAÇÃO QUICKPAY × VELO"
    worksheet["A1"].font = Font(bold=True, size=14, color="FFFFFFFF")
    worksheet["A1"].fill = PatternFill(fill_type="solid", fgColor="FF1F4E78")
    worksheet["A1"].alignment = Alignment(horizontal="center", vertical="center")
    worksheet.row_dimensions[1].height = 26
    worksheet.merge_cells("A2:I2")
    worksheet["A2"] = "Comparação gerada pelo workflow de conciliação Velo."
    worksheet["A2"].font = Font(italic=True, color="FF44546A")

    headers = [
        "Transações QuickPay",
        "Registros Velo",
        "Conciliadas",
        "Somente QuickPay",
        "Somente Velo",
        "Ambiguidades",
    ]
    values = [
        matching.resumo.transacoes_operadora,
        matching.resumo.registros_sistema,
        matching.resumo.conciliados,
        matching.resumo.nao_encontrados_no_sistema,
        matching.resumo.nao_encontrados_na_operadora,
        matching.resumo.ambiguidades,
    ]
    for column, value in enumerate(headers, start=1):
        cell = worksheet.cell(4, column, value)
        cell.fill = PatternFill(fill_type="solid", fgColor="FFD9EAF7")
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
        cell.border = _thin_border()
    for column, value in enumerate(values, start=1):
        cell = worksheet.cell(5, column, value)
        cell.alignment = Alignment(horizontal="center")
        cell.border = _thin_border()

    for column, value in enumerate(MATCHING_HEADERS, start=1):
        cell = worksheet.cell(7, column, value)
        cell.fill = PatternFill(fill_type="solid", fgColor="FF5B9BD5")
        cell.font = Font(bold=True, color="FFFFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _thin_border()
    for row, item in enumerate(matching.individuais, start=8):
        transacao = item.transacao_operadora
        registro = item.registro_sistema
        if transacao is None and registro is None:
            raise ValueError("resultado de matching sem transacao QuickPay ou registro Velo")
        origem = "QuickPay" if transacao is not None else "Somente Velo"
        values = [
            origem,
            None if transacao is None else transacao.linha_original,
            transacao.data_venda if transacao is not None else registro.data_cadastro,
            transacao.bandeira if transacao is not None else registro.tipo_cartao,
            item.valor_operadora,
            item.valor_sistema,
            item.diferenca,
            item.status.value.replace("_", " "),
            item.nivel_confianca.value.replace("_", " "),
        ]
        for column, value in enumerate(values, start=1):
            cell = worksheet.cell(row, column, value)
            cell.border = _thin_border()
            cell.alignment = Alignment(vertical="center")
        for column in (5, 6, 7):
            worksheet.cell(row, column).number_format = MONEY_FORMAT
        worksheet.cell(row, 3).number_format = DATE_FORMAT
        worksheet.cell(row, 8).fill = PatternFill(
            fill_type="solid",
            fgColor="FFE2F0D9" if item.status is StatusConciliacao.CONCILIADO else "FFFCE4D6",
        )
    for column, width in {
        "A": 16,
        "B": 15,
        "C": 15,
        "D": 16,
        "E": 15,
        "F": 15,
        "G": 15,
        "H": 34,
        "I": 26,
    }.items():
        worksheet.column_dimensions[column].width = width
    worksheet.freeze_panes = "A8"


def _aplicar_estilo(
    worksheet: Worksheet, relatorio: QuickPayRelatorioProcessado, total_row: int
) -> None:
    worksheet["A1"].font = Font(bold=True, size=12)
    worksheet["A1"].fill = _yellow_fill()
    worksheet["A1"].alignment = Alignment(horizontal="left", vertical="center", wrap_text=False)

    widths = {
        "A": 16,
        "B": 18,
        "C": 14,
        "D": 16,
        "E": 18,
        "F": 15,
        "G": 13,
        "H": 15,
        "I": 15,
        "J": 14,
        "K": 13,
        "L": 27,
        "M": 15,
        "N": 18,
        "O": 34,
        "P": 20,
        "Q": 20,
    }
    for column_letter, width in widths.items():
        worksheet.column_dimensions[column_letter].width = width

    for cells in worksheet.iter_rows(
        min_row=3, max_row=total_row, min_col=1, max_col=len(QUICKPAY_HEADERS)
    ):
        for cell in cells:
            cell.border = _thin_border()
            cell.alignment = Alignment(vertical="center", wrap_text=True)

    for row_number in range(3, total_row + 1):
        worksheet.cell(row_number, 1).number_format = DATE_FORMAT
        worksheet.cell(row_number, 2).number_format = DATE_FORMAT
        for numeric_column in (6, 7, 8, 9, 10, 12, 13, 14, 16, 17):
            worksheet.cell(row_number, numeric_column).number_format = MONEY_FORMAT
        worksheet.cell(row_number, 11).number_format = PERCENT_FORMAT

    _aplicar_cores_linhas(worksheet, relatorio)

    for total_column in (5, 6, 7, 8, 9, 10, 12, 13, 14):
        worksheet.cell(total_row, total_column).font = Font(bold=True)
        worksheet.cell(total_row, total_column).border = _total_border()

    worksheet.freeze_panes = "A3"
    worksheet.auto_filter.ref = f"A2:Q{total_row}"


def _validar_exportacao(
    path: Path,
    relatorio: QuickPayRelatorioProcessado,
    result: QuickPayExportResult,
    *,
    matching: ResultadoConciliacaoOperadora | None,
) -> None:
    workbook = load_workbook(path, read_only=False, data_only=False)
    try:
        expected_sheets = [SHEET_NAME]
        if matching is not None:
            expected_sheets.append(MATCHING_SHEET_NAME)
        if relatorio.grupos_bancarios:
            expected_sheets.append(BANK_SHEET_NAME)
        if workbook.sheetnames != expected_sheets:
            raise ValueError("abas QuickPay geradas nao coincidem com o modo de conciliacao")
        worksheet = workbook[SHEET_NAME]
        headers = [worksheet.cell(2, column).value for column in range(1, 18)]
        if headers != QUICKPAY_HEADERS:
            raise ValueError("cabecalhos QuickPay gerados nao coincidem com o layout final")
        if worksheet.max_column != 17:
            raise ValueError("arquivo QuickPay gerado deve conter exatamente 17 colunas")
        if result.ultima_linha_transacao != 2 + len(relatorio.linhas):
            raise ValueError("quantidade de transacoes QuickPay exportadas invalida")
        _validar_formulas(worksheet, relatorio, result)
        _validar_valores(worksheet, relatorio, result, matching=matching)
        if matching is not None:
            _validar_comparacao_velo(workbook[MATCHING_SHEET_NAME], matching)
        if relatorio.grupos_bancarios:
            _validar_conciliacao_bancaria(workbook[BANK_SHEET_NAME], relatorio)
        _validar_erros_formula(worksheet)
    finally:
        workbook.close()


def _validar_formulas(
    worksheet: Worksheet, relatorio: QuickPayRelatorioProcessado, result: QuickPayExportResult
) -> None:
    for row in range(3, result.ultima_linha_transacao + 1):
        expected = {
            9: f"=F{row}-H{row}",
            10: f"=G{row}-I{row}",
            11: f'=IF(F{row}=0,"",1-(H{row}/F{row}))',
        }
        for column, formula in expected.items():
            if worksheet.cell(row, column).value != formula:
                raise ValueError(f"formula QuickPay invalida em {get_column_letter(column)}{row}")

    total = result.total_row
    last = result.ultima_linha_transacao
    for column in (6, 7, 8, 9, 10, 13, 14):
        letter = get_column_letter(column)
        expected_total = f"=SUM({letter}3:{letter}{last})"
        if worksheet.cell(total, column).value != expected_total:
            raise ValueError(f"formula total QuickPay invalida em {letter}{total}")
    expected_bank = (
        f"=SUM('{BANK_SHEET_NAME}'!F3:F{2 + len(relatorio.grupos_bancarios)})"
        if relatorio.grupos_bancarios
        else (
            f"=SUM(L3:L{last})"
            if relatorio.resumo.total_recebido_banco is not None
            else "CONFERÊNCIA BANCÁRIA NÃO REALIZADA: RECEBIMENTOS NÃO INFORMADOS OU INCOMPLETOS"
        )
    )
    if worksheet.cell(total, 12).value != expected_bank:
        raise ValueError(f"formula total QuickPay invalida em L{total}")
    _validar_subtotais_bloco(worksheet, relatorio, result)
    _validar_cores_linhas(worksheet, relatorio)


def _validar_valores(
    worksheet: Worksheet,
    relatorio: QuickPayRelatorioProcessado,
    result: QuickPayExportResult,
    *,
    matching: ResultadoConciliacaoOperadora | None,
) -> None:
    bruto = Decimal("0.00")
    taxa = Decimal("0.00")
    liquido = Decimal("0.00")
    recebido = Decimal("0.00")
    matching_por_linha = _matching_por_linha(matching)
    for row, linha in enumerate(relatorio.linhas, start=3):
        bruto += Decimal(str(worksheet.cell(row, 6).value))
        taxa += Decimal(str(worksheet.cell(row, 7).value))
        liquido += Decimal(str(worksheet.cell(row, 8).value))
        if linha.recebido_banco is not None:
            recebido += Decimal(str(worksheet.cell(row, 12).value))
        if (
            linha.recebido_banco is not None
            and Decimal(str(worksheet.cell(row, 12).value)) != linha.recebido_banco
        ):
            raise ValueError(f"valor recebido QuickPay nao preservado na linha {row}")
        expected = _campos_sistema(
            linha.transacao.valor_bruto,
            matching_por_linha.get(linha.transacao.linha_original),
        )
        if _money_cell(worksheet.cell(row, 13).value) != expected[0]:
            raise ValueError(f"valor de Sistema QuickPay invalido na linha {row}")
        if _money_cell(worksheet.cell(row, 14).value) != expected[1]:
            raise ValueError(f"Diferenca Sistema QuickPay invalida na linha {row}")
        if worksheet.cell(row, 15).value != expected[2]:
            raise ValueError(f"status QuickPay invalido na linha {row}")

    if result.total_row != 3 + len(relatorio.linhas):
        raise ValueError("linha de total QuickPay invalida")
    if quantize_money(bruto) != relatorio.resumo.total_bruto:
        raise ValueError("total bruto QuickPay exportado diverge do processamento")
    if quantize_money(taxa) != relatorio.resumo.total_taxa:
        raise ValueError("total taxa QuickPay exportado diverge do processamento")
    if quantize_money(liquido) != relatorio.resumo.total_liquido:
        raise ValueError("total liquido QuickPay exportado diverge do processamento")
    if (
        not relatorio.grupos_bancarios
        and relatorio.resumo.total_recebido_banco is not None
        and quantize_money(recebido) != relatorio.resumo.total_recebido_banco
    ):
        raise ValueError("total recebido no banco QuickPay diverge do processamento")


def _validar_conciliacao_bancaria(
    worksheet: Worksheet, relatorio: QuickPayRelatorioProcessado
) -> None:
    if worksheet.max_row != 2 + len(relatorio.grupos_bancarios):
        raise ValueError("quantidade de grupos bancarios QuickPay invalida")
    total_banco = Decimal("0.00")
    for row, grupo in enumerate(relatorio.grupos_bancarios, start=3):
        if (
            _money_cell(worksheet.cell(row, 5).value) != grupo.total_liquido_quickpay
            or _money_cell(worksheet.cell(row, 6).value) != grupo.valor_recebido_banco
            or _money_cell(worksheet.cell(row, 7).value) != grupo.diferenca_banco
        ):
            raise ValueError(f"comparacao bancaria QuickPay invalida na linha {row}")
        total_banco += grupo.valor_recebido_banco
    if quantize_money(total_banco) != relatorio.resumo.total_recebido_banco:
        raise ValueError("total bancario QuickPay diverge do processamento")


def _validar_comparacao_velo(worksheet: Worksheet, matching: ResultadoConciliacaoOperadora) -> None:
    headers = [worksheet.cell(7, column).value for column in range(1, 10)]
    if headers != MATCHING_HEADERS:
        raise ValueError("cabecalhos da comparacao QuickPay Velo nao coincidem com o layout")
    resumo = [worksheet.cell(5, column).value for column in range(1, 7)]
    esperado = [
        matching.resumo.transacoes_operadora,
        matching.resumo.registros_sistema,
        matching.resumo.conciliados,
        matching.resumo.nao_encontrados_no_sistema,
        matching.resumo.nao_encontrados_na_operadora,
        matching.resumo.ambiguidades,
    ]
    if resumo != esperado or worksheet.max_row != 7 + len(matching.individuais):
        raise ValueError("comparacao QuickPay Velo diverge do matching")


def _validar_erros_formula(worksheet: Worksheet) -> None:
    error_tokens = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A")
    for row in worksheet.iter_rows():
        for cell in row:
            value = str(cell.value)
            if any(token in value for token in error_tokens):
                raise ValueError(f"formula QuickPay com erro estrutural em {cell.coordinate}")


def _resolver_saida(path: Path, *, sobrescrever: bool) -> Path:
    if sobrescrever or not path.exists():
        return path
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.stem}_{suffix}{path.suffix}")


def _matching_por_linha(
    matching: ResultadoConciliacaoOperadora | None,
) -> dict[int, ResultadoIndividualMatching]:
    if matching is None:
        return {}
    result: dict[int, ResultadoIndividualMatching] = {}
    for item in matching.individuais:
        transacao = item.transacao_operadora
        if transacao is not None:
            result[transacao.linha_original] = item
    return result


def _campos_sistema(
    valor_operadora: Decimal,
    matching: ResultadoIndividualMatching | None,
) -> tuple[Decimal | None, Decimal | None, str]:
    if matching is None:
        return None, None, STATUS_PENDENTE
    status = STATUS_LABELS[matching.status]
    if matching.registro_sistema is not None and matching.status in {
        StatusConciliacao.CONCILIADO,
        StatusConciliacao.DIVERGENCIA_DE_VALOR,
    }:
        sistema = matching.registro_sistema.valor
        return sistema, quantize_money(valor_operadora - sistema), status
    return None, None, status


def _money_cell(value: object) -> Decimal | None:
    if value is None:
        return None
    return quantize_money(Decimal(str(value)))


def _blocos_subtotal(relatorio: QuickPayRelatorioProcessado) -> tuple[tuple[int, int], ...]:
    """Repete os blocos Cielo: data da venda e modalidade de pagamento."""
    blocos: list[tuple[int, int]] = []
    inicio = 3
    chave_atual: tuple[date, Modalidade | None] | None = None
    for row, linha in enumerate(relatorio.linhas, start=3):
        chave = (linha.transacao.data_venda, linha.transacao.modalidade)
        if chave_atual is None:
            chave_atual = chave
            inicio = row
        elif chave != chave_atual:
            blocos.append((inicio, row - 1))
            inicio = row
            chave_atual = chave
    if chave_atual is not None:
        blocos.append((inicio, 2 + len(relatorio.linhas)))
    return tuple(blocos)


def _linhas_subtotal_bloco(relatorio: QuickPayRelatorioProcessado) -> tuple[int, ...]:
    return tuple(end for _, end in _blocos_subtotal(relatorio))


def _escrever_subtotais_bloco(worksheet: Worksheet, relatorio: QuickPayRelatorioProcessado) -> None:
    for start_row, end_row in _blocos_subtotal(relatorio):
        worksheet.cell(end_row, 16, _formula_subtotal_bloco(start_row, end_row, "F"))
        worksheet.cell(end_row, 17, _formula_subtotal_bloco(start_row, end_row, "H"))


def _validar_subtotais_bloco(
    worksheet: Worksheet,
    relatorio: QuickPayRelatorioProcessado,
    result: QuickPayExportResult,
) -> None:
    expected_blocks = {end: start for start, end in _blocos_subtotal(relatorio)}
    if tuple(sorted(expected_blocks)) != result.subtotal_rows:
        raise ValueError("linhas de subtotal QuickPay nao coincidem com os blocos")
    last = result.ultima_linha_transacao
    for row in range(3, last + 1):
        start = expected_blocks.get(row)
        if start is None:
            values = (worksheet.cell(row, 16).value, worksheet.cell(row, 17).value)
            if any(value is not None for value in values):
                raise ValueError(f"subtotal QuickPay inesperado na linha {row}")
            continue
        expected = {
            16: _formula_subtotal_bloco(start, row, "F"),
            17: _formula_subtotal_bloco(start, row, "H"),
        }
        for column, formula in expected.items():
            if worksheet.cell(row, column).value != formula:
                raise ValueError(f"subtotal QuickPay invalido em {get_column_letter(column)}{row}")


def _formula_subtotal_bloco(start_row: int, end_row: int, value_column: str) -> str:
    return f"=SUM({value_column}{start_row}:{value_column}{end_row})"


def _aplicar_cores_linhas(worksheet: Worksheet, relatorio: QuickPayRelatorioProcessado) -> None:
    """Aplica à QuickPay as cores por modalidade usadas no layout Cielo."""
    dias_credito = {
        dia: indice
        for indice, dia in enumerate(
            sorted(
                {
                    linha.transacao.data_venda
                    for linha in relatorio.linhas
                    if linha.transacao.modalidade is Modalidade.CREDITO
                }
            )
        )
    }
    for row, linha in enumerate(relatorio.linhas, start=3):
        color = _cor_linha_quickpay(linha, dias_credito)
        fill = PatternFill(fill_type="solid", fgColor=f"FF{color}")
        for column in range(1, len(QUICKPAY_HEADERS) + 1):
            worksheet.cell(row, column).fill = fill


def _validar_cores_linhas(worksheet: Worksheet, relatorio: QuickPayRelatorioProcessado) -> None:
    dias_credito = {
        dia: indice
        for indice, dia in enumerate(
            sorted(
                {
                    linha.transacao.data_venda
                    for linha in relatorio.linhas
                    if linha.transacao.modalidade is Modalidade.CREDITO
                }
            )
        )
    }
    for row, linha in enumerate(relatorio.linhas, start=3):
        expected = f"FF{_cor_linha_quickpay(linha, dias_credito)}"
        if worksheet.cell(row, 1).fill.fgColor.rgb != expected:
            raise ValueError(f"cor da linha QuickPay invalida na linha {row}")


def _cor_linha_quickpay(linha: QuickPayLinhaProcessada, dias_credito: dict[date, int]) -> str:
    modalidade = linha.transacao.modalidade
    if modalidade is Modalidade.PIX:
        return "FFFF99"
    if modalidade is Modalidade.DEBITO:
        return "33CCCC"
    return "C0C0C0" if dias_credito[linha.transacao.data_venda] % 2 == 0 else "FFFFFF"


def _yellow_fill() -> PatternFill:
    return PatternFill(fill_type="solid", fgColor="FFFFC000")


def _thin_border() -> Border:
    side = Side(style="thin", color="FF808080")
    return Border(left=side, right=side, top=side, bottom=side)


def _total_border() -> Border:
    side = Side(style="thin", color="FF000000")
    return Border(top=Side(style="medium", color="FF000000"), bottom=side)
