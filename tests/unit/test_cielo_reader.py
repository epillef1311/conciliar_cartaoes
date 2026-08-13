from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from shutil import copyfile
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from conciliacao.domain.enums import Modalidade, Operadora
from conciliacao.readers.cielo_reader import ler_cielo
from conciliacao.readers.exceptions import CabecalhoNaoEncontradoError
from conciliacao.utils.file_hash import sha256_file

FIXTURES = Path("tests/fixtures/cielo")


def test_reads_cielo_with_header_after_introductory_rows_without_modifying_source():
    source = FIXTURES / "cielo_valido.xlsx"
    before_hash = sha256_file(source)
    before_modified = source.stat().st_mtime_ns

    result = ler_cielo(source)

    assert result.nome_aba_ou_tabela == "Recebiveis_cielo_detalhe1"
    assert len(result.transacoes) == 2
    assert result.hash_sha256 == before_hash
    assert source.stat().st_mtime_ns == before_modified
    assert result.transacoes[0].operadora is Operadora.CIELO
    assert result.transacoes[0].modalidade is Modalidade.CREDITO
    assert result.transacoes[0].taxa_original == Decimal("-5.03")
    assert result.transacoes[0].taxa_normalizada == Decimal("5.03")
    assert result.transacoes[0].linha_original == 4
    assert result.transacoes[0].celulas_origem["Data de pagamento (A)"] == "A4"
    assert result.transacoes[0].dados_originais["campos_cielo"]["tid"] == "TID-1"


def test_rejects_cielo_without_transaction_header():
    with pytest.raises(CabecalhoNaoEncontradoError):
        ler_cielo(FIXTURES / "cielo_sem_cabecalho.xlsx")


def test_reads_xlsx_with_xls_extension_and_invalid_declared_dimensions(tmp_path: Path):
    source = FIXTURES / "cielo_valido.xlsx"
    report = tmp_path / "relatorio_cielo.xls"
    copyfile(source, report)
    _declarar_dimensao_invalida(report)
    before_hash = sha256_file(report)
    before_modified = report.stat().st_mtime_ns

    result = ler_cielo(report)

    assert len(result.transacoes) == 2
    assert result.nome_aba_ou_tabela == "Recebiveis_cielo_detalhe1"
    assert result.hash_sha256 == before_hash
    assert report.stat().st_mtime_ns == before_modified


def _declarar_dimensao_invalida(path: Path) -> None:
    """Simula exportacao cujo XML declara somente a coluna A como usada."""
    with ZipFile(path) as archive:
        arquivos = {name: archive.read(name) for name in archive.namelist()}

    sheet_name = "xl/worksheets/sheet1.xml"
    sheet_xml = arquivos[sheet_name]
    marker = b"><x:sheetFormatPr"
    assert marker in sheet_xml
    arquivos[sheet_name] = sheet_xml.replace(
        marker,
        b'><x:dimension ref="A1:A1"/><x:sheetFormatPr',
        1,
    )

    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in arquivos.items():
            archive.writestr(name, content)
