import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "LoginTest" / "consultar_relatorios_test.py"
SPEC = importlib.util.spec_from_file_location("consultar_relatorios_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
consultar_relatorios_test = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consultar_relatorios_test)


def test_parse_date_accepts_iso_date() -> None:
    assert consultar_relatorios_test.parse_date("2026-08-03") == date(2026, 8, 3)


def test_parse_date_rejects_non_iso_date() -> None:
    with pytest.raises(Exception, match="AAAA-MM-DD"):
        consultar_relatorios_test.parse_date("03/08/2026")


def test_read_token_rejects_empty_file(tmp_path: Path) -> None:
    token_file = tmp_path / "token.txt"
    token_file.write_text(" ", encoding="utf-8")

    with pytest.raises(RuntimeError, match="vazio"):
        consultar_relatorios_test.read_token(token_file)


def test_categories_are_grouped_by_operator() -> None:
    assert [category.value for category in consultar_relatorios_test.categorias_cielo()] == [
        "CIELO_CREDITO",
        "CIELO_DEBITO",
        "CIELO_PIX",
    ]
    assert [category.value for category in consultar_relatorios_test.categorias_quickpay()] == [
        "QUICKPAY_CREDITO",
        "QUICKPAY_DEBITO",
        "QUICKPAY_PIX",
    ]


def test_call_timing_recorder_does_not_persist_header_values(tmp_path: Path) -> None:
    path = tmp_path / "calls.json"
    recorder = consultar_relatorios_test.CallTimingRecorder(path)

    recorder.record(
        url="https://api.example.test/listar",
        params={"operadoraId": 86},
        duration_ms=125,
        primeiro_byte_ms=100,
        status_http=200,
        error=None,
    )

    entries = json.loads(path.read_text(encoding="utf-8"))
    assert len(entries) == 1
    assert entries[0]["horario"]
    assert entries[0]["endpoint"] == "/listar"
    assert entries[0]["operadora_id"] == 86
    assert entries[0]["duracao_ms"] == 125
    assert entries[0]["primeiro_byte_ms"] == 100
    assert entries[0]["status_http"] == 200
    assert entries[0]["erro"] is None
