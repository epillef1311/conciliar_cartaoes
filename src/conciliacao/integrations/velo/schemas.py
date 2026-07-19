"""Schemas tipados das respostas da API Velo."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from conciliacao.domain.exceptions import DataError, MonetarioError
from conciliacao.utils.currency import parse_money


class VeloApiModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    def raw_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", by_alias=True)
        if self.model_extra:
            payload.update(self.model_extra)
        return payload


class FormaRecebimentoApi(VeloApiModel):
    id: int
    descricao: str

    @model_validator(mode="before")
    @classmethod
    def normalize_known_shapes(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "id" not in data:
            for key in ("formaRecebimentoId", "operadoraId", "value"):
                if key in data:
                    data["id"] = data[key]
                    break
        if "descricao" not in data:
            for key in ("descricao", "nome", "formaRecebimento", "operadora", "label", "text"):
                if key in data:
                    data["descricao"] = data[key]
                    break
        return data


class RegistroConciliacaoApi(VeloApiModel):
    eleva_usuario_id: int | str | None = Field(default=None, alias="elevaUsuarioId")
    eleva_empresa_id: int | str | None = Field(default=None, alias="elevaEmpresaId")
    acao: str | None = None
    forcar_acao: bool | str | None = Field(default=None, alias="forcarAcao")
    total_registros: int | None = Field(default=None, alias="totalRegistros")
    conta_pacote_pagamento_unico_id: str | int = Field(alias="contaPacotePagamentoUnicoId")
    operadora_id: int | None = Field(default=None, alias="operadoraId")
    operadora: str
    cadastro_caixa_id: str | int | None = Field(default=None, alias="cadastroCaixaId")
    forma_recebimento_id: int | None = Field(default=None, alias="formaRecebimentoId")
    forma_recebimento: str = Field(alias="formaRecebimento")
    tipo_cartao: str | int | None = Field(default=None, alias="tipoCartao")
    valor: Decimal
    valor_taxa_cartao: Decimal | None = Field(default=None, alias="valorTaxaCartao")
    data_vencimento: date = Field(alias="dataVencimento")
    data_cadastro: date = Field(alias="dataCadastro")
    categoria_taxa_id: int | str | None = Field(default=None, alias="categoriaTaxaId")
    centro_custo_taxa_id: int | str | None = Field(default=None, alias="centroCustoTaxaId")

    @field_validator("valor", "valor_taxa_cartao", mode="before")
    @classmethod
    def normalize_money(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        try:
            return parse_money(value)
        except MonetarioError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("data_cadastro", "data_vencimento", mode="before")
    @classmethod
    def normalize_api_date(cls, value: object) -> date:
        try:
            return parse_api_date(value)
        except DataError as exc:
            raise ValueError(str(exc)) from exc


def parse_api_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise DataError(f"tipo de data da API nao suportado: {type(value).__name__}")
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise DataError(f"data da API invalida: {value!r}") from exc
