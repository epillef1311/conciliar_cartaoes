"""Normalizacao conservadora de texto para comparacoes."""

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TextoNormalizado:
    original: str
    comparavel: str


def normalize_text(value: str) -> TextoNormalizado:
    """Preserva o texto original e produz uma chave comparavel sem acentos.

    A funcao nao substitui termos nem infere modalidade; divergencias semanticas
    continuam visiveis para as etapas de validacao e matching.
    """
    if not isinstance(value, str):
        raise TypeError("o texto a normalizar deve ser uma string")

    with_regular_spaces = value.replace("\u00a0", " ")
    collapsed = " ".join(with_regular_spaces.split())
    without_accents = "".join(
        character
        for character in unicodedata.normalize("NFKD", collapsed)
        if not unicodedata.combining(character)
    )
    comparable = re.sub(r"\s+", " ", without_accents).strip().casefold()
    return TextoNormalizado(original=value, comparavel=comparable)
