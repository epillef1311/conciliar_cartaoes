"""Categorias controladas para filtros da API Velo."""

from dataclasses import dataclass
from enum import StrEnum

from conciliacao.domain.enums import Modalidade, Operadora


class CategoriaFiltroVelo(StrEnum):
    CIELO_CREDITO = "CIELO_CREDITO"
    CIELO_DEBITO = "CIELO_DEBITO"
    CIELO_PIX = "CIELO_PIX"
    QUICKPAY_CREDITO = "QUICKPAY_CREDITO"
    QUICKPAY_DEBITO = "QUICKPAY_DEBITO"
    QUICKPAY_PIX = "QUICKPAY_PIX"

    @property
    def config_key(self) -> str:
        return self.value.casefold()


@dataclass(frozen=True, slots=True)
class CategoriaFiltroInfo:
    categoria: CategoriaFiltroVelo
    operadora: Operadora
    modalidade: Modalidade
    nome_esperado: str
    aliases: tuple[str, ...]


CATEGORIAS_VELO: dict[CategoriaFiltroVelo, CategoriaFiltroInfo] = {
    CategoriaFiltroVelo.CIELO_CREDITO: CategoriaFiltroInfo(
        categoria=CategoriaFiltroVelo.CIELO_CREDITO,
        operadora=Operadora.CIELO,
        modalidade=Modalidade.CREDITO,
        nome_esperado="Cartao de Credito - Cielo",
        aliases=(
            "cartao de credito - cielo",
            "cartao credito cielo",
            "credito cielo",
            "credito - cielo",
        ),
    ),
    CategoriaFiltroVelo.CIELO_DEBITO: CategoriaFiltroInfo(
        categoria=CategoriaFiltroVelo.CIELO_DEBITO,
        operadora=Operadora.CIELO,
        modalidade=Modalidade.DEBITO,
        nome_esperado="Cartao de Debito - Cielo",
        aliases=(
            "cartao de debito - cielo",
            "cartao debito cielo",
            "debito cielo",
            "debito - cielo",
        ),
    ),
    CategoriaFiltroVelo.CIELO_PIX: CategoriaFiltroInfo(
        categoria=CategoriaFiltroVelo.CIELO_PIX,
        operadora=Operadora.CIELO,
        modalidade=Modalidade.PIX,
        nome_esperado="Pix - Cielo",
        aliases=("pix - cielo", "pix cielo"),
    ),
    CategoriaFiltroVelo.QUICKPAY_CREDITO: CategoriaFiltroInfo(
        categoria=CategoriaFiltroVelo.QUICKPAY_CREDITO,
        operadora=Operadora.QUICKPAY,
        modalidade=Modalidade.CREDITO,
        nome_esperado="Cartao de Credito - Quickpay",
        aliases=(
            "cartao de credito - quickpay",
            "cartao credito quickpay",
            "credito quickpay",
            "credito - quickpay",
        ),
    ),
    CategoriaFiltroVelo.QUICKPAY_DEBITO: CategoriaFiltroInfo(
        categoria=CategoriaFiltroVelo.QUICKPAY_DEBITO,
        operadora=Operadora.QUICKPAY,
        modalidade=Modalidade.DEBITO,
        nome_esperado="Cartao de Debito - Quickpay",
        aliases=(
            "cartao de debito - quickpay",
            "cartao debito quickpay",
            "cartao de dedido - quickpay",
            "debito quickpay",
            "debito - quickpay",
        ),
    ),
    CategoriaFiltroVelo.QUICKPAY_PIX: CategoriaFiltroInfo(
        categoria=CategoriaFiltroVelo.QUICKPAY_PIX,
        operadora=Operadora.QUICKPAY,
        modalidade=Modalidade.PIX,
        nome_esperado="Pix - Quickpay",
        aliases=("pix - quickpay", "pix quickpay"),
    ),
}


def categorias_cielo() -> tuple[CategoriaFiltroVelo, ...]:
    return (
        CategoriaFiltroVelo.CIELO_CREDITO,
        CategoriaFiltroVelo.CIELO_DEBITO,
        CategoriaFiltroVelo.CIELO_PIX,
    )


def categorias_quickpay() -> tuple[CategoriaFiltroVelo, ...]:
    return (
        CategoriaFiltroVelo.QUICKPAY_CREDITO,
        CategoriaFiltroVelo.QUICKPAY_DEBITO,
        CategoriaFiltroVelo.QUICKPAY_PIX,
    )


def todas_categorias() -> tuple[CategoriaFiltroVelo, ...]:
    return (*categorias_cielo(), *categorias_quickpay())
