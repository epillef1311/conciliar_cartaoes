from __future__ import annotations

from decimal import Decimal

import pytest

from conciliacao.domain.exceptions import MonetarioError
from conciliacao.utils.currency import (
    fee_difference,
    fee_percentage,
    gross_minus_net,
    parse_money,
    sum_money,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.234,56", Decimal("1234.56")),
        ("R$ 1.234,56", Decimal("1234.56")),
        ("-R$ 67,69", Decimal("-67.69")),
        (126.83, Decimal("126.83")),
    ],
)
def test_parse_money_accepts_brazilian_and_excel_values(raw, expected):
    assert parse_money(raw) == expected


def test_parse_money_rejects_invalid_text():
    with pytest.raises(MonetarioError, match="invalido"):
        parse_money("R$ sem valor")


def test_cielo_negative_fee_is_normalized_for_fee_difference():
    assert fee_difference("-5,03", "126,83", "121,77") == Decimal("-0.03")


def test_quickpay_positive_fee_is_preserved_in_calculation():
    assert fee_difference("5,03", "126,83", "121,77") == Decimal("-0.03")


def test_one_cent_difference_is_not_erased():
    assert gross_minus_net("100,00", "99,99") == Decimal("0.01")


def test_fee_percentage_uses_ratio_and_preserves_excel_display_precision():
    assert fee_percentage("126,83", "121,77") == Decimal("0.0399")


def test_fee_percentage_avoids_division_by_zero():
    assert fee_percentage("0,00", "0,00") is None


def test_sum_money_is_deterministic_and_quantized():
    assert sum_money(["0,10", "0,20", "0,30"]) == Decimal("0.60")
