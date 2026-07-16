"""Deteccao de formato por assinatura e estrutura do conteudo."""

from pathlib import Path
from zipfile import BadZipFile, ZipFile

from conciliacao.readers.exceptions import (
    ArquivoCorrompidoError,
    ArquivoInexistenteError,
    ArquivoVazioError,
    FormatoNaoSuportadoError,
)
from conciliacao.readers.models import FormatoArquivo

_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ZIP_SIGNATURE = b"PK\x03\x04"
_HTML_PREFIXES = (b"<html", b"<!doctype html", b"<table")


def detectar_formato(path: str | Path) -> FormatoArquivo:
    """Reconhece XLSX, XLS binario e HTML sem confiar na extensao."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ArquivoInexistenteError(f"arquivo inexistente: {file_path}")

    try:
        with file_path.open("rb") as source:
            prefix = source.read(8192)
    except OSError as exc:
        raise ArquivoCorrompidoError(f"nao foi possivel ler o arquivo: {file_path}") from exc

    if not prefix:
        raise ArquivoVazioError(f"arquivo vazio: {file_path}")
    if prefix.startswith(_OLE_SIGNATURE):
        return FormatoArquivo.XLS_BINARIO
    if prefix.startswith(_ZIP_SIGNATURE):
        return _detectar_xlsx(file_path)

    content = prefix.lstrip(b"\xef\xbb\xbf\x00\t\r\n ").lower()
    if content.startswith(_HTML_PREFIXES):
        return FormatoArquivo.HTML
    raise FormatoNaoSuportadoError(f"formato nao suportado: {file_path}")


def _detectar_xlsx(path: Path) -> FormatoArquivo:
    try:
        with ZipFile(path) as archive:
            names = set(archive.namelist())
    except BadZipFile as exc:
        raise ArquivoCorrompidoError(f"arquivo ZIP corrompido: {path}") from exc

    expected = {"[Content_Types].xml", "xl/workbook.xml"}
    if not expected.issubset(names):
        raise FormatoNaoSuportadoError(f"arquivo ZIP nao contem uma planilha XLSX: {path}")
    return FormatoArquivo.XLSX
