from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from conciliacao import __version__
from conciliacao.validators import (
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

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
