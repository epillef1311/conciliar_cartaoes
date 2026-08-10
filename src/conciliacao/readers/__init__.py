"""Leitores de arquivos de operadoras, sempre em modo somente leitura."""

from conciliacao.readers.cielo_reader import ler_cielo
from conciliacao.readers.format_detector import detectar_formato
from conciliacao.readers.models import FormatoArquivo, ResultadoLeitura
from conciliacao.readers.quickpay_reader import ler_quickpay

__all__ = [
    "FormatoArquivo",
    "ResultadoLeitura",
    "detectar_formato",
    "ler_cielo",
    "ler_quickpay",
]
