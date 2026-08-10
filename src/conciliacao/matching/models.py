"""Modelos do resultado de matching, independentes de Excel e API HTTP."""

from decimal import Decimal
from enum import StrEnum

from pydantic import Field, field_validator

from conciliacao.domain.enums import Operadora, StatusConciliacao
from conciliacao.domain.models import (
    AlertaValidacao,
    ModeloDominio,
    RegistroSistema,
    TransacaoOperadora,
)
from conciliacao.integrations.velo.categories import CategoriaFiltroVelo
from conciliacao.utils.currency import parse_money


class NivelConfiancaMatching(StrEnum):
    EXATO_COM_BANDEIRA = "EXATO_COM_BANDEIRA"
    EXATO_SEM_BANDEIRA = "EXATO_SEM_BANDEIRA"
    AGREGADO_UNICO = "AGREGADO_UNICO"
    AGREGADO_REPETIDO = "AGREGADO_REPETIDO"
    AMBIGUO = "AMBIGUO"
    NAO_CORRESPONDIDO = "NAO_CORRESPONDIDO"


class ResultadoIndividualMatching(ModeloDominio):
    transacao_operadora: TransacaoOperadora | None = None
    registro_sistema: RegistroSistema | None = None
    status: StatusConciliacao
    valor_operadora: Decimal | None = None
    valor_sistema: Decimal | None = None
    diferenca: Decimal | None = None
    chave_utilizada: str
    nivel_confianca: NivelConfiancaMatching
    motivo: str
    identificador_grupo: str
    correspondencia_individual_comprovada: bool = False
    correspondencia_atribuida_deterministicamente: bool = False
    alertas: list[AlertaValidacao] = Field(default_factory=list)

    @field_validator("valor_operadora", "valor_sistema", "diferenca", mode="before")
    @classmethod
    def normalize_money(cls, value: object | None) -> Decimal | None:
        if value is None:
            return None
        return parse_money(value)


class ResultadoAgregadoMatching(ModeloDominio):
    chave_grupo: str
    quantidade_operadora: int = Field(ge=0)
    quantidade_sistema: int = Field(ge=0)
    quantidade_conciliada: int = Field(ge=0)
    excedente_operadora: int = Field(ge=0)
    excedente_sistema: int = Field(ge=0)
    total_operadora: Decimal
    total_sistema: Decimal
    diferenca_total: Decimal
    status: StatusConciliacao
    nivel_especificidade: NivelConfiancaMatching
    alertas: list[AlertaValidacao] = Field(default_factory=list)

    @field_validator("total_operadora", "total_sistema", "diferenca_total", mode="before")
    @classmethod
    def normalize_totals(cls, value: object) -> Decimal:
        return parse_money(value)


class ResumoConciliacaoOperadora(ModeloDominio):
    operadora: Operadora
    transacoes_operadora: int = Field(ge=0)
    registros_sistema: int = Field(ge=0)
    conciliados: int = Field(ge=0)
    nao_encontrados_no_sistema: int = Field(ge=0)
    nao_encontrados_na_operadora: int = Field(ge=0)
    divergencias_quantidade: int = Field(ge=0)
    divergencias_valor: int = Field(ge=0)
    ambiguidades: int = Field(ge=0)
    pendencias_dados: int = Field(ge=0)
    total_bruto_operadora: Decimal
    total_sistema: Decimal
    total_conciliado: Decimal
    diferenca_total: Decimal
    categorias_consultadas: set[CategoriaFiltroVelo] = Field(default_factory=set)
    categorias_ausentes: set[CategoriaFiltroVelo] = Field(default_factory=set)

    @field_validator(
        "total_bruto_operadora", "total_sistema", "total_conciliado", "diferenca_total",
        mode="before",
    )
    @classmethod
    def normalize_totals(cls, value: object) -> Decimal:
        return parse_money(value)


class ResultadoConciliacaoOperadora(ModeloDominio):
    operadora: Operadora
    individuais: tuple[ResultadoIndividualMatching, ...]
    agregados: tuple[ResultadoAgregadoMatching, ...]
    resumo: ResumoConciliacaoOperadora


class ResultadoGeralMatching(ModeloDominio):
    cielo: ResultadoConciliacaoOperadora | None = None
    quickpay: ResultadoConciliacaoOperadora | None = None
