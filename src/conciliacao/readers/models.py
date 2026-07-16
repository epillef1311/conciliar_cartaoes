"""Modelos comuns retornados pelos leitores."""

from enum import StrEnum
from pathlib import Path

from pydantic import Field

from conciliacao.domain.enums import SeveridadeAlerta
from conciliacao.domain.models import AlertaValidacao, ModeloDominio, TransacaoOperadora


class FormatoArquivo(StrEnum):
    XLSX = "XLSX"
    XLS_BINARIO = "XLS_BINARIO"
    HTML = "HTML"


class MetadadosArquivo(ModeloDominio):
    tamanho_bytes: int = Field(ge=0)
    modificado_em_ns: int = Field(ge=0)


class ResultadoLeitura(ModeloDominio):
    caminho_arquivo: Path
    formato_detectado: FormatoArquivo
    nome_aba_ou_tabela: str
    cabecalhos_originais: list[str]
    cabecalhos_normalizados: list[str]
    transacoes: list[TransacaoOperadora]
    avisos_leitura: list[AlertaValidacao] = Field(default_factory=list)
    metadados_arquivo: MetadadosArquivo
    hash_sha256: str


def aviso_coluna_banco_ausente(*, arquivo: Path, aba: str) -> AlertaValidacao:
    return AlertaValidacao(
        codigo="COLUNA_BANCO_QUICKPAY_AUSENTE",
        mensagem="A coluna RECEBIDO NO BANCO QUICKPAY nao foi encontrada na tabela.",
        severidade=SeveridadeAlerta.AVISO,
        arquivo=str(arquivo),
        aba=aba,
    )
