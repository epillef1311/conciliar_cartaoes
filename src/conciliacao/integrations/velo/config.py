"""Carregamento da configuracao da API Velo."""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from conciliacao.domain.exceptions import ConfiguracaoError
from conciliacao.integrations.velo.categories import CategoriaFiltroVelo

DEFAULT_CONFIG_PATH = Path("config/velo_api.yaml")


@dataclass(frozen=True, slots=True)
class VeloEndpointsConfig:
    autocomplete_operadoras: str
    conciliacao_recebidos: str


@dataclass(frozen=True, slots=True)
class VeloQueryConfig:
    intervalo_dia: int
    is_compensado: int


@dataclass(frozen=True, slots=True)
class VeloTimeoutsConfig:
    connect_seconds: int
    read_seconds: int

    @property
    def as_tuple(self) -> tuple[int, int]:
        return (self.connect_seconds, self.read_seconds)


@dataclass(frozen=True, slots=True)
class VeloRetriesConfig:
    enabled: bool
    max_attempts: int


@dataclass(frozen=True, slots=True)
class VeloAuditConfig:
    save_raw_responses: bool
    raw_directory: Path


@dataclass(frozen=True, slots=True)
class VeloApiConfig:
    base_url: str
    endpoints: VeloEndpointsConfig
    query: VeloQueryConfig
    formas_recebimento_fallback: dict[CategoriaFiltroVelo, int]
    timeouts: VeloTimeoutsConfig
    retries: VeloRetriesConfig
    audit: VeloAuditConfig


def load_velo_api_config(path: str | Path = DEFAULT_CONFIG_PATH) -> VeloApiConfig:
    config_path = Path(path)
    if (
        config_path == DEFAULT_CONFIG_PATH
        and not config_path.is_file()
        and getattr(sys, "frozen", False)
    ):
        config_path = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / config_path
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfiguracaoError(f"configuracao Velo nao encontrada: {config_path}") from exc
    if not isinstance(raw, dict):
        raise ConfiguracaoError("configuracao Velo deve ser um objeto YAML")
    return _parse_config(raw)


def _parse_config(raw: dict[str, Any]) -> VeloApiConfig:
    base_url = _required_str(raw, "base_url").rstrip("/")
    endpoints_raw = _required_dict(raw, "endpoints")
    query_raw = _required_dict(raw, "query")
    timeouts_raw = raw.get("timeouts")
    retries_raw = raw.get("retries") or {}
    audit_raw = raw.get("audit") or {}

    if not isinstance(retries_raw, dict) or not isinstance(audit_raw, dict):
        raise ConfiguracaoError("retries e audit devem ser objetos YAML")
    if timeouts_raw is None and "timeout_seconds" in raw:
        timeout_seconds = _as_positive_int(raw["timeout_seconds"], "timeout_seconds")
        timeouts_raw = {"connect_seconds": timeout_seconds, "read_seconds": timeout_seconds}
    if not isinstance(timeouts_raw, dict):
        raise ConfiguracaoError("timeouts deve ser um objeto YAML")

    endpoints = VeloEndpointsConfig(
        autocomplete_operadoras=_endpoint_path(endpoints_raw, "autocomplete_operadoras"),
        conciliacao_recebidos=_endpoint_path(endpoints_raw, "conciliacao_recebidos"),
    )
    query = VeloQueryConfig(
        intervalo_dia=int(query_raw.get("intervalo_dia", -1)),
        is_compensado=int(query_raw.get("is_compensado", 0)),
    )
    timeouts = VeloTimeoutsConfig(
        connect_seconds=_as_positive_int(timeouts_raw.get("connect_seconds"), "connect_seconds"),
        read_seconds=_as_positive_int(timeouts_raw.get("read_seconds"), "read_seconds"),
    )
    retries = VeloRetriesConfig(
        enabled=bool(retries_raw.get("enabled", False)),
        max_attempts=max(1, int(retries_raw.get("max_attempts", 1))),
    )
    audit = VeloAuditConfig(
        save_raw_responses=bool(audit_raw.get("save_raw_responses", False)),
        raw_directory=Path(str(audit_raw.get("raw_directory", "data/api_raw"))),
    )
    fallbacks = _fallbacks(_required_dict(raw, "formas_recebimento_fallback"))
    return VeloApiConfig(
        base_url=base_url,
        endpoints=endpoints,
        query=query,
        formas_recebimento_fallback=fallbacks,
        timeouts=timeouts,
        retries=retries,
        audit=audit,
    )


def _fallbacks(raw: dict[str, Any]) -> dict[CategoriaFiltroVelo, int]:
    fallbacks: dict[CategoriaFiltroVelo, int] = {}
    for categoria in CategoriaFiltroVelo:
        raw_value = raw.get(categoria.config_key)
        if raw_value is None:
            raise ConfiguracaoError(f"fallback ausente para {categoria.config_key}")
        fallbacks[categoria] = _as_positive_int(raw_value, categoria.config_key)
    return fallbacks


def _required_dict(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ConfiguracaoError(f"configuracao Velo invalida: {key} ausente ou invalido")
    return value


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfiguracaoError(f"configuracao Velo invalida: {key} ausente ou vazio")
    return value.strip()


def _endpoint_path(raw: dict[str, Any], key: str) -> str:
    value = _required_str(raw, key)
    if not value.startswith("/"):
        raise ConfiguracaoError(f"endpoint {key} deve iniciar com /")
    return value


def _as_positive_int(value: object, key: str) -> int:
    if isinstance(value, bool) or value is None:
        raise ConfiguracaoError(f"configuracao Velo invalida: {key} deve ser inteiro")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError as exc:
            raise ConfiguracaoError(
                f"configuracao Velo invalida: {key} deve ser inteiro"
            ) from exc
    else:
        raise ConfiguracaoError(f"configuracao Velo invalida: {key} deve ser inteiro")
    if parsed <= 0:
        raise ConfiguracaoError(f"configuracao Velo invalida: {key} deve ser positivo")
    return parsed
