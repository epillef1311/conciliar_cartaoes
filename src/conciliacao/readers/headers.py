"""Localizacao conservadora de tabelas por combinacoes de cabecalhos."""

from collections.abc import Sequence
from dataclasses import dataclass

from conciliacao.readers.exceptions import CabecalhoAmbiguoError, CabecalhoNaoEncontradoError
from conciliacao.utils.text import normalize_text


@dataclass(frozen=True, slots=True)
class RegraCabecalho:
    nome: str
    alternativas: tuple[str, ...]

    @property
    def alternativas_normalizadas(self) -> set[str]:
        return {normalize_text(value).comparavel for value in self.alternativas}


@dataclass(frozen=True, slots=True)
class LinhaParaBusca:
    local: str
    numero_linha: int
    valores: Sequence[object]


@dataclass(frozen=True, slots=True)
class CabecalhoEncontrado:
    local: str
    numero_linha: int
    indices: dict[str, int]
    valores: Sequence[object]


def localizar_cabecalho(
    linhas: Sequence[LinhaParaBusca], regras: Sequence[RegraCabecalho], *, arquivo: str
) -> CabecalhoEncontrado:
    """Retorna somente uma linha que contenha todas as colunas obrigatorias."""
    candidatos = [
        candidato for linha in linhas if (candidato := _avaliar_linha(linha, regras)) is not None
    ]
    if not candidatos:
        esperados = ", ".join(regra.alternativas[0] for regra in regras)
        raise CabecalhoNaoEncontradoError(
            "cabecalho transacional nao encontrado",
            arquivo=arquivo,
            cabecalho_esperado=esperados,
        )
    if len(candidatos) > 1:
        locais = ", ".join(f"{item.local}:{item.numero_linha}" for item in candidatos)
        raise CabecalhoAmbiguoError(
            f"multiplos cabecalhos candidatos encontrados: {locais}", arquivo=arquivo
        )
    return candidatos[0]


def _avaliar_linha(
    linha: LinhaParaBusca, regras: Sequence[RegraCabecalho]
) -> CabecalhoEncontrado | None:
    indices: dict[str, int] = {}
    for index, value in enumerate(linha.valores):
        if not isinstance(value, str):
            continue
        normalizado = normalize_text(value).comparavel
        for regra in regras:
            if regra.nome not in indices and normalizado in regra.alternativas_normalizadas:
                indices[regra.nome] = index
    if len(indices) != len(regras):
        return None
    return CabecalhoEncontrado(
        local=linha.local,
        numero_linha=linha.numero_linha,
        indices=indices,
        valores=linha.valores,
    )
