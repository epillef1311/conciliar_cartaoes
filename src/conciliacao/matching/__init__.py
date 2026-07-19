"""Matching deterministico entre operadoras e registros do sistema."""

from conciliacao.matching.models import (
    NivelConfiancaMatching,
    ResultadoAgregadoMatching,
    ResultadoConciliacaoOperadora,
    ResultadoGeralMatching,
    ResultadoIndividualMatching,
)
from conciliacao.matching.reconciliation import ReconciliationService
from conciliacao.matching.summaries import formatar_resultado_matching

__all__ = [
    "NivelConfiancaMatching",
    "ReconciliationService",
    "ResultadoAgregadoMatching",
    "ResultadoConciliacaoOperadora",
    "ResultadoGeralMatching",
    "ResultadoIndividualMatching",
    "formatar_resultado_matching",
]
