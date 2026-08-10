"""Enumeracoes usadas pelos registros normalizados."""

from enum import StrEnum


class Operadora(StrEnum):
    CIELO = "CIELO"
    QUICKPAY = "QUICKPAY"


class Modalidade(StrEnum):
    CREDITO = "CREDITO"
    DEBITO = "DEBITO"
    PIX = "PIX"


class StatusConciliacao(StrEnum):
    CONCILIADO = "CONCILIADO"
    DIVERGENCIA_DE_VALOR = "DIVERGENCIA_DE_VALOR"
    DIVERGENCIA_DE_QUANTIDADE = "DIVERGENCIA_DE_QUANTIDADE"
    NAO_ENCONTRADO_NO_SISTEMA = "NAO_ENCONTRADO_NO_SISTEMA"
    NAO_ENCONTRADO_NA_OPERADORA = "NAO_ENCONTRADO_NA_OPERADORA"
    CORRESPONDENCIA_AMBIGUA = "CORRESPONDENCIA_AMBIGUA"
    PENDENTE_DE_DADOS = "PENDENTE_DE_DADOS"


class SeveridadeAlerta(StrEnum):
    INFO = "INFO"
    AVISO = "AVISO"
    ERRO = "ERRO"
    CRITICO = "CRITICO"


class OrigemRegistro(StrEnum):
    CIELO = "CIELO"
    QUICKPAY = "QUICKPAY"
    VELO_API = "VELO_API"
