"""Exportador Excel do relatorio QuickPay sem API e sem matching."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from conciliacao.processors.quickpay_processor import (
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
]

STATUS_PENDENTE = "PENDENTE DE CONCILIAÇÃO COM SISTEMA"
SHEET_NAME = "Conciliação"
MONEY_FORMAT = r'\R\$\ * #,##0.00;[Red]\-\R\$\ * #,##0.00'
PERCENT_FORMAT = "0.00%"
DATE_FORMAT = "dd/mm/yyyy"
TIME_FORMAT = "hh:mm"


@dataclass(frozen=True, slots=True)
class QuickPayExportResult:
    caminho_saida: Path
    total_row: int
    ultima_linha_transacao: int
    validacao_saida_ok: bool


class QuickPayExporter:
    def exportar(
        self,
        relatorio: QuickPayRelatorioProcessado,
        *,
        diretorio_saida: str | Path,
        sobrescrever: bool = False,
    ) -> QuickPayExportResult:
        output_dir = Path(diretorio_saida)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = _resolver_saida(
            output_dir
            / f"QUICKPAY_CONCILIACAO_{relatorio.data_inicio.isoformat()}_A_"
            f"{relatorio.data_fim.isoformat()}.xlsx",
            sobrescrever=sobrescrever,
        )

        workbook = Workbook()
        worksheet = cast(Worksheet, workbook.active)
        if worksheet is None:
            raise ValueError("nao foi possivel criar a aba Conciliação")
        worksheet.title = SHEET_NAME
        _escrever_planilha(worksheet, relatorio)
        workbook.save(output_path)
        workbook.close()

        result = QuickPayExportResult(
            caminho_saida=output_path,
            total_row=3 + len(relatorio.linhas),
            ultima_linha_transacao=2 + len(relatorio.linhas),
            validacao_saida_ok=False,
        )
        _validar_exportacao(output_path, relatorio, result)
        return QuickPayExportResult(
            caminho_saida=result.caminho_saida,
            total_row=result.total_row,
            ultima_linha_transacao=result.ultima_linha_transacao,
            validacao_saida_ok=True,
        )


def _escrever_planilha(worksheet: Worksheet, relatorio: QuickPayRelatorioProcessado) -> None:
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

    for index, linha in enumerate(relatorio.linhas, start=3):
        _escrever_linha(worksheet, index, linha)
    _escrever_total_geral(worksheet, relatorio)
    _aplicar_estilo(worksheet, relatorio, 3 + len(relatorio.linhas))


def _escrever_linha(worksheet: Worksheet, row: int, linha: QuickPayLinhaProcessada) -> None:
    transacao = linha.transacao
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
        linha.recebido_banco,
        None,
        None,
        STATUS_PENDENTE,
    ]
    for column, value in enumerate(values, start=1):
        worksheet.cell(row, column, value)


def _escrever_total_geral(worksheet: Worksheet, relatorio: QuickPayRelatorioProcessado) -> None:
    total_row = 3 + len(relatorio.linhas)
    last_transaction = total_row - 1
    worksheet.cell(total_row, 5, "TOTAL")
    for column in (6, 7, 8, 9, 10, 12):
        letter = get_column_letter(column)
        worksheet.cell(total_row, column, f"=SUM({letter}3:{letter}{last_transaction})")


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
        for numeric_column in (6, 7, 8, 9, 10, 12, 14):
            worksheet.cell(row_number, numeric_column).number_format = MONEY_FORMAT
        worksheet.cell(row_number, 11).number_format = PERCENT_FORMAT

    for row_number, linha in enumerate(relatorio.linhas, start=3):
        if linha.diferenca_taxa != Decimal("0.00"):
            worksheet.cell(row_number, 10).fill = _warning_fill()
        if linha.transacao.valor_bruto == Decimal("0.00"):
            worksheet.cell(row_number, 11).fill = _warning_fill()

    for total_column in (5, 6, 7, 8, 9, 10, 12):
        worksheet.cell(total_row, total_column).font = Font(bold=True)
        worksheet.cell(total_row, total_column).border = _total_border()

    worksheet.freeze_panes = "A3"
    worksheet.auto_filter.ref = f"A2:O{total_row}"


def _validar_exportacao(
    path: Path, relatorio: QuickPayRelatorioProcessado, result: QuickPayExportResult
) -> None:
    workbook = load_workbook(path, read_only=False, data_only=False)
    try:
        if workbook.sheetnames != [SHEET_NAME]:
            raise ValueError("arquivo QuickPay gerado deve conter somente a aba Conciliação")
        worksheet = workbook[SHEET_NAME]
        headers = [worksheet.cell(2, column).value for column in range(1, 16)]
        if headers != QUICKPAY_HEADERS:
            raise ValueError("cabecalhos QuickPay gerados nao coincidem com o layout final")
        if worksheet.max_column != 15:
            raise ValueError("arquivo QuickPay gerado deve conter exatamente 15 colunas")
        if result.ultima_linha_transacao != 2 + len(relatorio.linhas):
            raise ValueError("quantidade de transacoes QuickPay exportadas invalida")
        _validar_formulas(worksheet, relatorio, result)
        _validar_valores(worksheet, relatorio, result)
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
    for column in (6, 7, 8, 9, 10, 12):
        letter = get_column_letter(column)
        expected_total = f"=SUM({letter}3:{letter}{last})"
        if worksheet.cell(total, column).value != expected_total:
            raise ValueError(f"formula total QuickPay invalida em {letter}{total}")


def _validar_valores(
    worksheet: Worksheet, relatorio: QuickPayRelatorioProcessado, result: QuickPayExportResult
) -> None:
    bruto = Decimal("0.00")
    taxa = Decimal("0.00")
    liquido = Decimal("0.00")
    recebido = Decimal("0.00")
    for row, linha in enumerate(relatorio.linhas, start=3):
        bruto += Decimal(str(worksheet.cell(row, 6).value))
        taxa += Decimal(str(worksheet.cell(row, 7).value))
        liquido += Decimal(str(worksheet.cell(row, 8).value))
        recebido += Decimal(str(worksheet.cell(row, 12).value))
        if Decimal(str(worksheet.cell(row, 12).value)) != linha.recebido_banco:
            raise ValueError(f"valor recebido QuickPay nao preservado na linha {row}")
        if worksheet.cell(row, 13).value is not None or worksheet.cell(row, 14).value is not None:
            raise ValueError(f"colunas Sistema devem permanecer vazias na linha {row}")
        if worksheet.cell(row, 15).value != STATUS_PENDENTE:
            raise ValueError(f"status QuickPay invalido na linha {row}")

    if result.total_row != 3 + len(relatorio.linhas):
        raise ValueError("linha de total QuickPay invalida")
    if quantize_money(bruto) != relatorio.resumo.total_bruto:
        raise ValueError("total bruto QuickPay exportado diverge do processamento")
    if quantize_money(taxa) != relatorio.resumo.total_taxa:
        raise ValueError("total taxa QuickPay exportado diverge do processamento")
    if quantize_money(liquido) != relatorio.resumo.total_liquido:
        raise ValueError("total liquido QuickPay exportado diverge do processamento")
    if quantize_money(recebido) != relatorio.resumo.total_recebido_banco:
        raise ValueError("total recebido no banco QuickPay diverge do processamento")


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


def _yellow_fill() -> PatternFill:
    return PatternFill(fill_type="solid", fgColor="FFFFC000")


def _warning_fill() -> PatternFill:
    return PatternFill(fill_type="solid", fgColor="FFFFF2CC")


def _thin_border() -> Border:
    side = Side(style="thin", color="FF808080")
    return Border(left=side, right=side, top=side, bottom=side)


def _total_border() -> Border:
    side = Side(style="thin", color="FF000000")
    return Border(top=Side(style="medium", color="FF000000"), bottom=side)
