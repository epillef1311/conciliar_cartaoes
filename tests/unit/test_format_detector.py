from __future__ import annotations

from pathlib import Path

import pytest

from conciliacao.readers.exceptions import ArquivoVazioError, FormatoNaoSuportadoError
from conciliacao.readers.format_detector import detectar_formato
from conciliacao.readers.models import FormatoArquivo

FIXTURES = Path("tests/fixtures")


def test_detects_xlsx_despite_misleading_extension():
    path = FIXTURES / "misc/enganoso.xls.xlsx"
    assert detectar_formato(path) is FormatoArquivo.XLSX


def test_detects_html_with_xls_extension():
    path = FIXTURES / "quickpay/quickpay_html.xls"
    assert detectar_formato(path) is FormatoArquivo.HTML


def test_detects_binary_xls_signature(tmp_path: Path):
    path = tmp_path / "arquivo.xls"
    path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1conteudo-binario")
    assert detectar_formato(path) is FormatoArquivo.XLS_BINARIO


def test_rejects_empty_and_invalid_files(tmp_path: Path):
    empty = tmp_path / "vazio.xls"
    empty.write_bytes(b"")
    with pytest.raises(ArquivoVazioError):
        detectar_formato(empty)

    with pytest.raises(FormatoNaoSuportadoError):
        detectar_formato(FIXTURES / "misc/arquivo_invalido.bin")
