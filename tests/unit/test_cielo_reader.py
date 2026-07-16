from __future__ import annotations

from decimal import Decimal
from pathlib import Path

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
