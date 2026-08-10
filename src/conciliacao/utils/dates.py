"""Normalizacao de datas sem depender de leitura de arquivos."""

import re
from datetime import date, datetime
from numbers import Real

from openpyxl.utils.datetime import from_excel

from conciliacao.domain.exceptions import DataError

SYSTEM_PRIMARY_DATE_FIELD = "dataCadastro"
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BR_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def parse_date(value: object) -> date:
    """Aceita data ISO, data brasileira, objetos date/datetime e serial do Excel."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return _parse_date_text(value)
    if isinstance(value, Real) and not isinstance(value, bool):
        try:
            excel_value = from_excel(value)
        except (TypeError, ValueError) as exc:
            raise DataError(f"data serial do Excel invalida: {value!r}") from exc
        if isinstance(excel_value, datetime):
            return excel_value.date()
        if isinstance(excel_value, date):
            return excel_value
    raise DataError(f"tipo de data nao suportado: {type(value).__name__}")


def validate_period(start: object, end: object) -> tuple[date, date]:
    """Normaliza e valida um periodo inclusivo de data de venda."""
    start_date = parse_date(start)
    end_date = parse_date(end)
    if start_date > end_date:
        raise DataError("data inicial nao pode ser posterior a data final")
    return start_date, end_date


def _parse_date_text(value: str) -> date:
    raw = value.strip()
    if _ISO_DATE.fullmatch(raw):
        format_value = "%Y-%m-%d"
    elif _BR_DATE.fullmatch(raw):
        format_value = "%d/%m/%Y"
    else:
        raise DataError(f"formato de data invalido: {value!r}")

    try:
        return datetime.strptime(raw, format_value).date()
    except ValueError as exc:
        raise DataError(f"data invalida: {value!r}") from exc
