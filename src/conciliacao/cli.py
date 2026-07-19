from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from conciliacao import __version__
from conciliacao.exporters import CieloExporter, QuickPayExporter
from conciliacao.processors import CieloProcessor, QuickPayProcessor
from conciliacao.processors.cielo_processor import CieloProcessingError
from conciliacao.processors.quickpay_processor import QuickPayProcessingError
from conciliacao.readers.cielo_reader import ler_cielo
from conciliacao.readers.quickpay_reader import ler_quickpay
from conciliacao.validators import (
    CieloValidator,
    QuickPayValidator,
    formatar_resumo_validacao,
    validar_cielo_arquivo,
    validar_quickpay_arquivo,
)
from conciliacao.validators.common_validator import PeriodoSolicitadoInvalido


def _date_value(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"data invalida: {raw!r}. Use o formato YYYY-MM-DD."
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="conciliacao",
        description="CLI da automacao de conciliacao de caixa.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    processar = subparsers.add_parser(
        "processar",
        help="Valida argumentos do processamento. Workflow completo ainda nao implementado.",
    )
    processar.add_argument("--data-inicio", required=True, type=_date_value)
    processar.add_argument("--data-fim", required=True, type=_date_value)
    processar.add_argument("--arquivo-cielo", required=True, type=Path)
    processar.add_argument("--arquivo-quickpay", required=True, type=Path)
    processar.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida argumentos sem executar processamento.",
    )

    validar_cielo = subparsers.add_parser(
        "validar-cielo",
        help="Valida somente um arquivo Cielo. Nao gera Excel nem consulta API.",
    )
    validar_cielo.add_argument("--arquivo", required=True, type=Path)
    _add_period_args(validar_cielo)

    validar_quickpay = subparsers.add_parser(
        "validar-quickpay",
        help="Valida somente um arquivo QuickPay. Nao gera Excel nem consulta API.",
    )
    validar_quickpay.add_argument("--arquivo", required=True, type=Path)
    _add_period_args(validar_quickpay)

    validar = subparsers.add_parser(
        "validar",
        help="Valida arquivos Cielo e QuickPay de forma independente.",
    )
    validar.add_argument("--arquivo-cielo", required=True, type=Path)
    validar.add_argument("--arquivo-quickpay", required=True, type=Path)
    _add_period_args(validar)

    gerar_cielo = subparsers.add_parser(
        "gerar-cielo",
        help="Gera somente o relatorio Cielo no padrao LEO. Nao consulta API.",
    )
    gerar_cielo.add_argument("--arquivo", required=True, type=Path)
    gerar_cielo.add_argument("--data-inicio", required=True, type=_date_value)
    gerar_cielo.add_argument("--data-fim", required=True, type=_date_value)
    gerar_cielo.add_argument("--saida", required=True, type=Path)
    gerar_cielo.add_argument(
        "--sobrescrever",
        action="store_true",
        help="Permite sobrescrever o arquivo de saida quando ele ja existir.",
    )

    gerar_quickpay = subparsers.add_parser(
        "gerar-quickpay",
        help="Gera somente o relatorio QuickPay. Nao consulta API.",
    )
    gerar_quickpay.add_argument("--arquivo", required=True, type=Path)
    gerar_quickpay.add_argument("--data-inicio", required=True, type=_date_value)
    gerar_quickpay.add_argument("--data-fim", required=True, type=_date_value)
    gerar_quickpay.add_argument("--saida", required=True, type=Path)
    gerar_quickpay.add_argument(
        "--sobrescrever",
        action="store_true",
        help="Permite sobrescrever o arquivo de saida quando ele ja existir.",
    )

    return parser


def _processar(args: argparse.Namespace) -> int:
    if args.data_fim < args.data_inicio:
        print("Erro: data-fim nao pode ser anterior a data-inicio.")
        return 2

    if args.dry_run:
        print("Argumentos validos. Nenhum processamento foi executado.")
        return 0

    print("Workflow de processamento ainda nao implementado nesta etapa.")
    return 2


def _add_period_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-inicio", required=False, type=_date_value)
    parser.add_argument("--data-fim", required=False, type=_date_value)


def _validar_cielo(args: argparse.Namespace) -> int:
    try:
        resultado = validar_cielo_arquivo(
            args.arquivo,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
        )
    except PeriodoSolicitadoInvalido as exc:
        print(f"Erro: {exc}")
        return 2
    print(formatar_resumo_validacao(resultado))
    return 0 if resultado.valido else 1


def _validar_quickpay(args: argparse.Namespace) -> int:
    try:
        resultado = validar_quickpay_arquivo(
            args.arquivo,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
        )
    except PeriodoSolicitadoInvalido as exc:
        print(f"Erro: {exc}")
        return 2
    print(formatar_resumo_validacao(resultado))
    return 0 if resultado.valido else 1


def _validar_ambos(args: argparse.Namespace) -> int:
    try:
        cielo = validar_cielo_arquivo(
            args.arquivo_cielo,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
        )
        quickpay = validar_quickpay_arquivo(
            args.arquivo_quickpay,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
        )
    except PeriodoSolicitadoInvalido as exc:
        print(f"Erro: {exc}")
        return 2
    print(formatar_resumo_validacao(cielo, quickpay))
    return 0 if cielo.valido and quickpay.valido else 1


def _gerar_cielo(args: argparse.Namespace) -> int:
    if args.data_fim < args.data_inicio:
        print("Erro: data-fim nao pode ser anterior a data-inicio.")
        return 2
    try:
        leitura = ler_cielo(args.arquivo)
        validacao = CieloValidator().validar(
            leitura,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
        )
        if not validacao.valido:
            print(formatar_resumo_validacao(validacao))
            return 1
        relatorio = CieloProcessor().processar(
            leitura,
            validacao,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
        )
        exportacao = CieloExporter().exportar(
            relatorio,
            diretorio_saida=args.saida,
            sobrescrever=args.sobrescrever,
        )
    except (CieloProcessingError, ValueError, OSError) as exc:
        print(f"Erro ao gerar relatorio Cielo: {exc}")
        return 1

    resumo = relatorio.resumo
    print(
        "\n".join(
            [
                "RELATORIO CIELO GERADO",
                "",
                f"Arquivo de entrada: {args.arquivo}",
                f"Arquivo de saida: {exportacao.caminho_saida}",
                "",
                f"Transacoes lidas: {resumo.transacoes_lidas}",
                f"Transacoes incluidas: {resumo.transacoes_incluidas}",
                f"Transacoes fora do periodo: {resumo.transacoes_fora_periodo}",
                "",
                f"Valor bruto: R$ {resumo.total_bruto}",
                f"Taxa/tarifa: R$ {resumo.total_taxa}",
                f"Valor liquido: R$ {resumo.total_liquido}",
                "",
                f"Blocos de cartao: {resumo.blocos_cartao}",
                f"Blocos Pix: {resumo.blocos_pix}",
                f"Validacao da saida: {'OK' if exportacao.validacao_saida_ok else 'FALHA'}",
            ]
        )
    )
    return 0


def _gerar_quickpay(args: argparse.Namespace) -> int:
    if args.data_fim < args.data_inicio:
        print("Erro: data-fim nao pode ser anterior a data-inicio.")
        return 2
    try:
        leitura = ler_quickpay(args.arquivo)
        validacao = QuickPayValidator().validar(
            leitura,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
        )
        if not validacao.valido:
            print(formatar_resumo_validacao(validacao))
            return 1
        relatorio = QuickPayProcessor().processar(
            leitura,
            validacao,
            data_inicio=args.data_inicio,
            data_fim=args.data_fim,
        )
        exportacao = QuickPayExporter().exportar(
            relatorio,
            diretorio_saida=args.saida,
            sobrescrever=args.sobrescrever,
        )
    except (QuickPayProcessingError, ValueError, OSError) as exc:
        print(f"Erro ao gerar relatorio QuickPay: {exc}")
        return 1

    resumo = relatorio.resumo
    print(
        "\n".join(
            [
                "RELATORIO QUICKPAY GERADO",
                "",
                f"Arquivo de entrada: {args.arquivo}",
                f"Arquivo de saida: {exportacao.caminho_saida}",
                "",
                f"Transacoes lidas: {resumo.transacoes_lidas}",
                f"Transacoes incluidas: {resumo.transacoes_incluidas}",
                f"Transacoes fora do periodo: {resumo.transacoes_fora_periodo}",
                "",
                f"Valor da Venda: R$ {resumo.total_bruto}",
                f"Taxa: R$ {resumo.total_taxa}",
                f"Valor liquido: R$ {resumo.total_liquido}",
                f"Bruto-Liquido: R$ {resumo.total_bruto_liquido}",
                f"Diferenca: R$ {resumo.total_diferenca_taxa}",
                f"Recebido no banco QuickPay: R$ {resumo.total_recebido_banco}",
                f"Diferenca banco-liquido: R$ {resumo.diferenca_total_banco_liquido}",
                "",
                f"Valor da Venda zero: {resumo.valor_bruto_zero}",
                f"Validacao da saida: {'OK' if exportacao.validacao_saida_ok else 'FALHA'}",
            ]
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "processar":
        return _processar(args)
    if args.command == "validar-cielo":
        return _validar_cielo(args)
    if args.command == "validar-quickpay":
        return _validar_quickpay(args)
    if args.command == "validar":
        return _validar_ambos(args)
    if args.command == "gerar-cielo":
        return _gerar_cielo(args)
    if args.command == "gerar-quickpay":
        return _gerar_quickpay(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
