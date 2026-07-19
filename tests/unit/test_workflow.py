from __future__ import annotations

import json
from pathlib import Path

from openpyxl import load_workbook
from pydantic import ValidationError

from conciliacao.exporters.quickpay_exporter import SHEET_NAME
from conciliacao.integrations.velo.testing import FakeVeloTransport, text_response
from conciliacao.workflow import (
    ReconciliationCommand,
    ReconciliationWorkflow,
    WorkflowMode,
    WorkflowStatus,
)


def test_workflow_simulado_processa_ambas_operadoras_e_preenche_quickpay(tmp_path):
    api_dir = _api_fixtures(tmp_path)
    output_dir = tmp_path / "output"
    command = ReconciliationCommand(
        data_inicio="2026-07-13",
        data_fim="2026-07-13",
        arquivo_cielo=Path("tests/fixtures/cielo/cielo_valido.xlsx"),
        arquivo_quickpay=Path("tests/fixtures/quickpay/quickpay_valido.xlsx"),
        diretorio_saida=output_dir,
        modo_simulado=True,
        diretorio_fixtures_api=api_dir,
        salvar_auditoria=True,
        identificador_execucao="20260719_120000_teste1",
    )

    result = ReconciliationWorkflow().executar(command)

    assert result.status_geral is WorkflowStatus.SUCESSO
    assert result.codigo_saida == 0
    assert result.modo is WorkflowMode.SIMULADO
    assert result.resultado_cielo is not None
    assert result.resultado_quickpay is not None
    assert result.resultado_cielo.resumo_matching["resumo"]["conciliados"] == 2
    assert result.resultado_quickpay.resumo_matching["resumo"]["conciliados"] == 2
    assert result.resultado_cielo.hash_preservado
    assert result.resultado_quickpay.hash_preservado
    assert result.resultado_cielo.arquivo_saida is not None
    assert result.resultado_quickpay.arquivo_saida is not None
    assert result.resultado_cielo.arquivo_saida.exists()
    assert result.resultado_quickpay.arquivo_saida.exists()
    assert (output_dir / "execucoes" / command.identificador_execucao / "resumo.json").exists()
    assert (Path("data/api_raw") / command.identificador_execucao / "metadata.json").exists()

    workbook = load_workbook(result.resultado_quickpay.arquivo_saida, data_only=False)
    try:
        worksheet = workbook[SHEET_NAME]
        assert worksheet.cell(3, 13).value == 194
        assert worksheet.cell(3, 14).value == 0
        assert worksheet.cell(3, 15).value == "CONCILIADO"
        assert worksheet.cell(4, 13).value == 126.83
        assert worksheet.cell(4, 14).value == 0
        assert worksheet.cell(4, 15).value == "CONCILIADO"
    finally:
        workbook.close()

    combined = _combined_text(result.logs + result.arquivos_de_auditoria)
    assert "Authorization" not in combined
    assert "Bearer" not in combined
    assert "token-teste-nao-real" not in combined


def test_workflow_somente_cielo_nao_exige_quickpay(tmp_path):
    command = ReconciliationCommand(
        data_inicio="2026-07-13",
        data_fim="2026-07-13",
        arquivo_cielo=Path("tests/fixtures/cielo/cielo_valido.xlsx"),
        diretorio_saida=tmp_path / "output",
        modo_simulado=True,
        diretorio_fixtures_api=_api_fixtures(tmp_path),
        salvar_auditoria=False,
        identificador_execucao="20260719_120000_cielo",
    )

    result = ReconciliationWorkflow().executar(command)

    assert result.status_geral is WorkflowStatus.SUCESSO
    assert result.resultado_cielo is not None
    assert result.resultado_quickpay is None
    assert result.resultado_cielo.arquivo_saida is not None
    assert result.resultado_cielo.arquivo_saida.exists()


def test_workflow_quickpay_invalida_nao_bloqueia_cielo(tmp_path):
    command = ReconciliationCommand(
        data_inicio="2026-07-13",
        data_fim="2026-07-13",
        arquivo_cielo=Path("tests/fixtures/cielo/cielo_valido.xlsx"),
        arquivo_quickpay=Path("tests/fixtures/quickpay/quickpay_html.xls"),
        diretorio_saida=tmp_path / "output",
        modo_simulado=True,
        diretorio_fixtures_api=_api_fixtures(tmp_path),
        salvar_auditoria=False,
        identificador_execucao="20260719_120000_parcial",
    )

    result = ReconciliationWorkflow().executar(command)

    assert result.status_geral is WorkflowStatus.SUCESSO_PARCIAL
    assert result.codigo_saida == 2
    assert result.resultado_cielo is not None
    assert result.resultado_cielo.status is WorkflowStatus.SUCESSO
    assert result.resultado_cielo.arquivo_saida is not None
    assert result.resultado_quickpay is not None
    assert result.resultado_quickpay.status is WorkflowStatus.FALHA
    assert "QUICKPAY_COLUNA_RECEBIDO_AUSENTE" in result.resultado_quickpay.erros


def test_workflow_falha_categoria_api_marca_pendente_sem_bloquear_excel(tmp_path):
    api_dir = _api_fixtures(tmp_path, omit={"cielo_pix.json"})
    command = ReconciliationCommand(
        data_inicio="2026-07-13",
        data_fim="2026-07-13",
        arquivo_cielo=Path("tests/fixtures/cielo/cielo_valido.xlsx"),
        diretorio_saida=tmp_path / "output",
        modo_simulado=True,
        diretorio_fixtures_api=api_dir,
        salvar_auditoria=False,
        identificador_execucao="20260719_120000_apiparcial",
    )

    result = ReconciliationWorkflow().executar(command)

    assert result.status_geral is WorkflowStatus.SUCESSO_PARCIAL
    assert result.resultado_cielo is not None
    assert result.resultado_cielo.status is WorkflowStatus.SUCESSO_PARCIAL
    assert result.resultado_cielo.resumo_matching["resumo"]["conciliados"] == 1
    assert result.resultado_cielo.resumo_matching["resumo"]["pendencias_dados"] == 1
    assert "CIELO_PIX" in result.resultado_api.categorias_com_erro
    assert result.resultado_cielo.arquivo_saida is not None
    assert result.resultado_cielo.arquivo_saida.exists()


def test_workflow_erro_401_nao_gera_relatorio_e_retorna_codigo_autenticacao(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("VELO_BEARER_TOKEN", "token-teste-nao-real")
    transport = FakeVeloTransport(
        {
            "autoCompletarOperadora": text_response(
                '{"erro":"unauthorized"}',
                status_code=401,
            )
        }
    )
    command = ReconciliationCommand(
        data_inicio="2026-07-13",
        data_fim="2026-07-13",
        arquivo_cielo=Path("tests/fixtures/cielo/cielo_valido.xlsx"),
        diretorio_saida=tmp_path / "output",
        identificador_execucao="20260719_120000_auth",
    )

    result = ReconciliationWorkflow(transport=transport).executar(command)

    assert result.status_geral is WorkflowStatus.FALHA
    assert result.codigo_saida == 4
    assert result.resultado_cielo is None
    assert not list((tmp_path / "output" / "cielo").glob("*.xlsx"))
    assert "token-teste-nao-real" not in _combined_text(result.logs)


def test_workflow_command_rejeita_sem_arquivo():
    try:
        ReconciliationCommand(data_inicio="2026-07-13", data_fim="2026-07-13")
    except ValidationError as exc:
        assert "informe pelo menos um arquivo" in str(exc)
    else:
        raise AssertionError("comando sem arquivos deveria falhar")


def _api_fixtures(tmp_path: Path, *, omit: set[str] | None = None) -> Path:
    omit = omit or set()
    api_dir = tmp_path / "api"
    api_dir.mkdir()
    payloads = {
        "autocomplete_operadoras.json": [
            {"id": 81, "descricao": "Cartao de Credito - Cielo"},
            {"id": 86, "descricao": "Cartao de Debito - Cielo"},
            {"id": 91, "descricao": "Pix - Cielo"},
            {"id": 44, "descricao": "Cartao de Credito - Quickpay"},
            {"id": 51, "descricao": "Cartao de Dedido - Quickpay"},
            {"id": 42, "descricao": "Pix - Quickpay"},
        ],
        "cielo_credito.json": [
            _registro("CC-001", "Cielo", "Cartao de Credito - Cielo", "Visa", "126.83", 81),
        ],
        "cielo_pix.json": [
            _registro("CP-001", "Cielo", "Pix - Cielo", "Pix", "2.90", 91),
        ],
        "quickpay_credito.json": [
            _registro("QC-001", "QuickPay", "Cartao de Credito - Quickpay", "Visa", "126.83", 44),
            _registro(
                "QC-002",
                "QuickPay",
                "Cartao de Credito - Quickpay",
                "Mastercard",
                "194.00",
                44,
            ),
        ],
    }
    for filename, payload in payloads.items():
        if filename in omit:
            continue
        (api_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return api_dir


def _registro(
    ident: str,
    operadora: str,
    forma: str,
    tipo: str,
    valor: str,
    forma_id: int,
) -> dict[str, object]:
    return {
        "contaPacotePagamentoUnicoId": ident,
        "operadoraId": forma_id,
        "operadora": operadora,
        "cadastroCaixaId": f"CX-{ident}",
        "formaRecebimentoId": forma_id,
        "formaRecebimento": forma,
        "tipoCartao": tipo,
        "valor": valor,
        "valorTaxaCartao": "0.00",
        "dataVencimento": "2026-07-14",
        "dataCadastro": "2026-07-13",
        "campoExtra": "anonimo",
    }


def _combined_text(paths: list[Path]) -> str:
    chunks = []
    for path in paths:
        if path.exists() and path.is_file():
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)
