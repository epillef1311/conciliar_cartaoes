from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from conciliacao.integrations.velo.audit import VeloAuditWriter
from conciliacao.integrations.velo.categories import CategoriaFiltroVelo
from conciliacao.integrations.velo.config import VeloAuditConfig, VeloQueryConfig
from conciliacao.integrations.velo.exceptions import VeloAuditError


def test_audit_writer_creates_valid_json_and_metadata_without_sensitive_headers(tmp_path: Path):
    writer = VeloAuditWriter(
        VeloAuditConfig(save_raw_responses=True, raw_directory=tmp_path),
        now=datetime(2026, 7, 19, 10, 30, tzinfo=ZoneInfo("America/Sao_Paulo")),
    )

    response_path = writer.save_json("cielo_credito.json", [{"id": "CC-1", "valor": "1.00"}])
    metadata_path = writer.save_metadata(
        period_start="2026-07-14",
        period_end="2026-07-15",
        query=VeloQueryConfig(intervalo_dia=-1, is_compensado=0),
        categories_requested=(CategoriaFiltroVelo.CIELO_CREDITO,),
    )

    assert response_path is not None
    assert metadata_path is not None
    response_payload = json.loads(response_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert response_payload == [{"id": "CC-1", "valor": "1.00"}]
    assert metadata["period_start"] == "2026-07-14"
    assert metadata["period_end"] == "2026-07-15"
    assert metadata["intervalo_dia"] == -1
    assert metadata["is_compensado"] == 0
    assert metadata["categories_requested"] == ["CIELO_CREDITO"]
    combined = response_path.read_text(encoding="utf-8") + metadata_path.read_text(
        encoding="utf-8"
    )
    assert "Authorization" not in combined
    assert "Bearer" not in combined
    assert "token-teste-nao-real" not in combined


def test_audit_writer_removes_temp_file_when_atomic_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    writer = VeloAuditWriter(VeloAuditConfig(save_raw_responses=True, raw_directory=tmp_path))

    def fail_replace(self: Path, target: Path) -> Path:
        del target
        raise OSError("falha simulada")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(VeloAuditError):
        writer.save_json("quickpay_pix.json", [{"id": "QP-1"}])

    assert not list(tmp_path.glob("**/*.tmp"))
    assert not list(tmp_path.glob("**/quickpay_pix.json"))


def test_api_raw_directory_is_git_ignored():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "data/api_raw/**" in gitignore
