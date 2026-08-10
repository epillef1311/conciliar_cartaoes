"""Auditoria local de respostas brutas da API Velo."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from conciliacao.integrations.velo.categories import CategoriaFiltroVelo
from conciliacao.integrations.velo.config import VeloAuditConfig, VeloQueryConfig
from conciliacao.integrations.velo.exceptions import VeloAuditError


class VeloAuditWriter:
    def __init__(
        self,
        config: VeloAuditConfig,
        *,
        now: datetime | None = None,
        execution_id: str | None = None,
    ) -> None:
        self.config = config
        self.executed_at = now or datetime.now(ZoneInfo("America/Sao_Paulo"))
        directory_name = execution_id or self.executed_at.strftime("%Y%m%d_%H%M%S")
        self.execution_dir = config.raw_directory / directory_name

    def enabled(self) -> bool:
        return self.config.save_raw_responses

    def save_json(self, filename: str, payload: Any) -> Path | None:
        if not self.enabled():
            return None
        if not filename.endswith(".json") or "/" in filename or "\\" in filename:
            raise VeloAuditError(
                "Nome de arquivo de auditoria invalido.",
                endpoint="audit",
                context={"filename": filename},
            )
        self.execution_dir.mkdir(parents=True, exist_ok=True)
        final_path = self.execution_dir / filename
        temp_path = final_path.with_suffix(f"{final_path.suffix}.tmp")
        try:
            serialized = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            json.loads(serialized)
            temp_path.write_text(serialized + "\n", encoding="utf-8")
            temp_path.replace(final_path)
        except Exception as exc:
            if temp_path.exists():
                temp_path.unlink()
            raise VeloAuditError(
                "Falha ao salvar resposta bruta da API Velo.",
                endpoint="audit",
                context={"path": str(final_path)},
                cause=exc,
            ) from exc
        return final_path

    def save_metadata(
        self,
        *,
        period_start: Any,
        period_end: Any,
        query: VeloQueryConfig,
        categories_requested: tuple[CategoriaFiltroVelo, ...],
    ) -> Path | None:
        payload = {
            "executed_at": self.executed_at.isoformat(),
            "period_start": str(period_start),
            "period_end": str(period_end),
            "intervalo_dia": query.intervalo_dia,
            "is_compensado": query.is_compensado,
            "categories_requested": [category.value for category in categories_requested],
        }
        return self.save_json("metadata.json", payload)
