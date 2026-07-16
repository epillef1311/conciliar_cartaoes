from __future__ import annotations

from datetime import date, datetime

import pytest

from conciliacao.domain.exceptions import DataError
from conciliacao.utils.dates import SYSTEM_PRIMARY_DATE_FIELD, parse_date, validate_period


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-07-13", date(2026, 7, 13)),
        ("13/07/2026", date(2026, 7, 13)),
        (datetime(2026, 7, 13, 11, 35), date(2026, 7, 13)),
        (date(2026, 7, 13), date(2026, 7, 13)),
        (46216, date(2026, 7, 13)),
    ],
)
def test_parse_date_accepts_supported_formats(raw, expected):
    assert parse_date(raw) == expected


def test_parse_date_rejects_invalid_date():
    with pytest.raises(DataError, match="data invalida"):
        parse_date("31/02/2026")


def test_validate_period_rejects_inverted_dates():
    with pytest.raises(DataError, match="inicial"):
        validate_period("2026-07-14", "2026-07-13")


def test_system_uses_data_cadastro_as_primary_date():
    assert SYSTEM_PRIMARY_DATE_FIELD == "dataCadastro"
