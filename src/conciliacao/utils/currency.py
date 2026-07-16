"""Conversoes e calculos monetarios baseados exclusivamente em Decimal."""

import re
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from math import isfinite

from conciliacao.domain.exceptions import MonetarioError

CENTAVOS = Decimal("0.01")
PERCENTUAL_QUANTUM = Decimal("0.0001")
_BRL_PATTERN = re.compile(r"^[+-]?(?:(?:\d{1,3}(?:\.\d{3})+)|\d+)(?:,\d+)?$")
_DECIMAL_PATTERN = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


def quantize_money(value: Decimal) -> Decimal:
    """Aplica o arredondamento financeiro explicito para centavos."""
    return value.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def parse_money(value: object) -> Decimal:
    """Converte valores de planilha e textos brasileiros em Decimal com dois centavos."""
    if value is None or isinstance(value, bool):
        raise MonetarioError("valor monetario ausente ou invalido")

    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, int):
        parsed = Decimal(value)
    elif isinstance(value, float):
        if not isfinite(value):
            raise MonetarioError("valor numerico nao finito")
        parsed = Decimal(str(value))
    elif isinstance(value, str):
        parsed = _parse_money_text(value)
    else:
        raise MonetarioError(f"tipo monetario nao suportado: {type(value).__name__}")

    if not parsed.is_finite():
        raise MonetarioError("valor monetario nao finito")
    return quantize_money(parsed)


def sum_money(values: Iterable[Decimal | int | float | str]) -> Decimal:
    """Soma em ordem de entrada, com cada parcela normalizada em centavos."""
    total = Decimal("0.00")
    for value in values:
        total += parse_money(value)
    return quantize_money(total)


def gross_minus_net(gross_amount: object, net_amount: object) -> Decimal:
    """Retorna Valor bruto - Valor liquido."""
    return quantize_money(parse_money(gross_amount) - parse_money(net_amount))


def fee_difference(fee: object, gross_amount: object, net_amount: object) -> Decimal:
    """Retorna Taxa - (Valor bruto - Valor liquido)."""
    return quantize_money(abs(parse_money(fee)) - gross_minus_net(gross_amount, net_amount))


def fee_percentage(gross_amount: object, net_amount: object) -> Decimal | None:
    """Retorna 1 - (liquido / bruto), ou None quando o bruto for zero.

    Percentuais usam quatro casas no dominio para preservar duas casas quando exibidos
    como porcentagem no Excel; valores monetarios continuam sempre em centavos.
    """
    gross = parse_money(gross_amount)
    net = parse_money(net_amount)
    if gross == Decimal("0.00"):
        return None
    return (Decimal("1") - (net / gross)).quantize(PERCENTUAL_QUANTUM, rounding=ROUND_HALF_UP)


def _parse_money_text(value: str) -> Decimal:
    normalized = value.replace("\u00a0", " ").strip()
    normalized = normalized.replace(" ", "")
    normalized = re.sub(r"^([+-]?)R\$", r"\1", normalized, flags=re.IGNORECASE)
    if not normalized:
        raise MonetarioError("valor monetario vazio")

    if "," in normalized:
        if not _BRL_PATTERN.fullmatch(normalized):
            raise MonetarioError(f"texto monetario invalido: {value!r}")
        normalized = normalized.replace(".", "").replace(",", ".")
    elif not _DECIMAL_PATTERN.fullmatch(normalized):
        raise MonetarioError(f"texto monetario invalido: {value!r}")

    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise MonetarioError(f"texto monetario invalido: {value!r}") from exc
