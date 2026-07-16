"""Modelos de resultado das validacoes de arquivos."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator

from conciliacao.domain.enums import Operadora, SeveridadeAlerta
from conciliacao.domain.models import AlertaValidacao, ModeloDominio
from conciliacao.utils.currency import parse_money


class PeriodoEncontrado(ModeloDominio):
    menor_data_venda: date | None = None
    maior_data_venda: date | None = None
    quantidade_dentro_periodo: int = Field(default=0, ge=0)
    quantidade_fora_periodo: int = Field(default=0, ge=0)


class ResultadoValidacao(ModeloDominio):
    arquivo_validado: Path
    operadora: Operadora
    valido: bool
    quantidade_transacoes: int = Field(ge=0)
    quantidade_erros: int = Field(ge=0)
    quantidade_avisos: int = Field(ge=0)
    erros: list[AlertaValidacao] = Field(default_factory=list)
    avisos: list[AlertaValidacao] = Field(default_factory=list)
    totais_calculados: dict[str, Any] = Field(default_factory=dict)
    periodo_encontrado: PeriodoEncontrado = Field(default_factory=PeriodoEncontrado)
    metadados_validacao: dict[str, Any] = Field(default_factory=dict)

    @field_validator("totais_calculados", mode="before")
    @classmethod
    def normalize_decimal_totals(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        return _normalize_decimal_values(value)


def _normalize_decimal_values(value: Any) -> Any:
    if isinstance(value, Decimal):
        return parse_money(value)
    if isinstance(value, dict):
        return {key: _normalize_decimal_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_decimal_values(item) for item in value]
    return value


def resultado_invalido(
    *,
    arquivo: str | Path,
    operadora: Operadora,
    alerta: AlertaValidacao,
    metadados: dict[str, Any] | None = None,
) -> ResultadoValidacao:
    erros = (
        [alerta]
        if alerta.severidade in {SeveridadeAlerta.ERRO, SeveridadeAlerta.CRITICO}
        else []
    )
    avisos = [alerta] if alerta.severidade is SeveridadeAlerta.AVISO else []
    return ResultadoValidacao(
        arquivo_validado=Path(arquivo),
        operadora=operadora,
        valido=False,
        quantidade_transacoes=0,
        quantidade_erros=len(erros),
        quantidade_avisos=len(avisos),
        erros=erros,
        avisos=avisos,
        metadados_validacao=metadados or {},
    )
