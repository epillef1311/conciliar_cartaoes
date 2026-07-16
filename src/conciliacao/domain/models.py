"""Modelos tipados e serializaveis usados entre as etapas da conciliacao."""

from datetime import date, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from conciliacao.domain.enums import (
    Modalidade,
    Operadora,
    OrigemRegistro,
    SeveridadeAlerta,
    StatusConciliacao,
)
from conciliacao.utils.currency import parse_money


class ModeloDominio(BaseModel):
    """Configuracao compartilhada para modelos de dominio."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TransacaoOperadora(ModeloDominio):
    identificador_origem: str | None = None
    operadora: Operadora
    modalidade: Modalidade | None = None
    bandeira: str | None = None
    data_venda: date
    hora_venda: time | None = None
    data_recebimento: date | None = None
    numero_parcelas: int | None = Field(default=None, ge=1)
    valor_bruto: Decimal
    valor_liquido: Decimal
    taxa_normalizada: Decimal
    taxa_original: Decimal
    origem_arquivo: OrigemRegistro
    linha_original: int = Field(ge=1)
    celulas_origem: dict[str, str] = Field(default_factory=dict)
    dados_originais: dict[str, Any] | None = None

    @field_validator("valor_bruto", "valor_liquido", "taxa_original", mode="before")
    @classmethod
    def normalize_monetary_value(cls, value: object) -> Decimal:
        return parse_money(value)

    @field_validator("taxa_normalizada", mode="before")
    @classmethod
    def normalize_fee(cls, value: object) -> Decimal:
        return abs(parse_money(value))


class RegistroSistema(ModeloDominio):
    conta_pacote_pagamento_unico_id: str = Field(alias="contaPacotePagamentoUnicoId")
    operadora: str
    forma_recebimento: str
    tipo_cartao: str | int | None = None
    valor: Decimal
    data_cadastro: date = Field(alias="dataCadastro")
    data_vencimento: date | None = Field(default=None, alias="dataVencimento")
    cadastro_caixa_id: str | None = Field(default=None, alias="cadastroCaixaId")
    identificadores_api: dict[str, Any] = Field(default_factory=dict)

    @field_validator("valor", mode="before")
    @classmethod
    def normalize_value(cls, value: object) -> Decimal:
        return parse_money(value)


class AlertaValidacao(ModeloDominio):
    codigo: str
    mensagem: str
    severidade: SeveridadeAlerta
    arquivo: str | None = None
    aba: str | None = None
    linha: int | None = Field(default=None, ge=1)
    coluna: str | None = None
    celula: str | None = None
    valor_recebido: Any | None = None
    contexto_adicional: dict[str, Any] = Field(default_factory=dict)


class ResultadoConciliacao(ModeloDominio):
    transacao_operadora: TransacaoOperadora | None = None
    registro_sistema: RegistroSistema | None = None
    status: StatusConciliacao
    valor_operadora: Decimal | None = None
    valor_sistema: Decimal | None = None
    diferenca: Decimal | None = None
    quantidade_operadora: int = Field(default=0, ge=0)
    quantidade_sistema: int = Field(default=0, ge=0)
    chave_agrupamento: str | None = None
    motivo: str | None = None
    alertas: list[AlertaValidacao] = Field(default_factory=list)

    @field_validator("valor_operadora", "valor_sistema", "diferenca", mode="before")
    @classmethod
    def normalize_optional_monetary_value(cls, value: object | None) -> Decimal | None:
        if value is None:
            return None
        return parse_money(value)
