from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from conciliacao.cli import main


def test_version_command(capsys):
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert "conciliacao 0.1.0" in captured.out


def test_processar_dry_run_accepts_valid_dates(capsys):
    exit_code = main(
        [
            "processar",
            "--data-inicio",
            "2026-07-13",
            "--data-fim",
            "2026-07-13",
            "--arquivo-cielo",
            "data/input/cielo.xlsx",
            "--arquivo-quickpay",
            "data/input/quickpay.xlsx",
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Argumentos validos" in captured.out


def test_processar_rejects_inverted_period(capsys):
    exit_code = main(
        [
            "processar",
            "--data-inicio",
            "2026-07-14",
            "--data-fim",
            "2026-07-13",
            "--arquivo-cielo",
            "data/input/cielo.xlsx",
            "--arquivo-quickpay",
            "data/input/quickpay.xlsx",
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "data-fim nao pode ser anterior" in captured.out


def test_processar_rejects_token_argument():
    parser = main
    try:
        parser(["processar", "--token", "segredo"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("CLI nao deve aceitar --token")


def test_validar_quickpay_reports_invalid_file(capsys):
    exit_code = main(
        [
            "validar-quickpay",
            "--arquivo",
            "tests/fixtures/quickpay/quickpay_html.xls",
            "--data-inicio",
            "2026-07-13",
            "--data-fim",
            "2026-07-13",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "QUICKPAY" in captured.out
    assert "QUICKPAY_COLUNA_RECEBIDO_AUSENTE" in captured.out


def test_validar_combined_shows_both_results(capsys):
    exit_code = main(
        [
            "validar",
            "--arquivo-cielo",
            "tests/fixtures/cielo/cielo_valido.xlsx",
            "--arquivo-quickpay",
            "tests/fixtures/quickpay/quickpay_html.xls",
            "--data-inicio",
            "2026-07-13",
            "--data-fim",
            "2026-07-13",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "CIELO" in captured.out
    assert "QUICKPAY" in captured.out


def test_gerar_cielo_creates_report(tmp_path, capsys):
    exit_code = main(
        [
            "gerar-cielo",
            "--arquivo",
            "tests/fixtures/cielo/cielo_valido.xlsx",
            "--data-inicio",
            "2026-07-13",
            "--data-fim",
            "2026-07-13",
            "--saida",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "RELATORIO CIELO GERADO" in captured.out
    assert "Transacoes incluidas: 2" in captured.out
    assert (tmp_path / "CIELO_CONCILIACAO_2026-07-13_A_2026-07-13.xlsx").exists()


def test_gerar_quickpay_creates_report(tmp_path, capsys):
    exit_code = main(
        [
            "gerar-quickpay",
            "--arquivo",
            "tests/fixtures/quickpay/quickpay_valido.xlsx",
            "--data-inicio",
            "2026-07-13",
            "--data-fim",
            "2026-07-13",
            "--saida",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "RELATORIO QUICKPAY GERADO" in captured.out
    assert "Transacoes incluidas: 2" in captured.out
    assert (tmp_path / "QUICKPAY_CONCILIACAO_2026-07-13_A_2026-07-13.xlsx").exists()


def test_testar_integracao_velo_uses_fixtures_without_real_calls(tmp_path, capsys):
    exit_code = main(
        [
            "testar-integracao-velo",
            "--fixtures",
            "tests/fixtures/api",
            "--data-inicio",
            "2026-07-14",
            "--data-fim",
            "2026-07-15",
            "--auditoria-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "SIMULACAO DA INTEGRACAO VELO" in captured.out
    assert "Cielo credito: 3 registros" in captured.out
    assert "QuickPay debito: 0 registros" in captured.out
    assert "Chamadas reais realizadas: 0" in captured.out
    assert next(tmp_path.glob("*/metadata.json")).exists()


def test_processar_modo_simulado_com_cielo_usa_fixtures(tmp_path, capsys):
    exit_code = main(
        [
            "processar",
            "--modo-simulado",
            "--fixtures-api",
            "tests/fixtures/api",
            "--data-inicio",
            "2026-07-13",
            "--data-fim",
            "2026-07-13",
                "--arquivo-cielo",
                "tests/fixtures/cielo/cielo_valido.xlsx",
                "--saida",
                str(tmp_path),
                "--diretorio-planilhas",
                str(tmp_path / "planilhas"),
                "--salvar-auditoria",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "CONCILIACAO FINALIZADA COM SUCESSO" in captured.out
    assert "Chamadas reais realizadas: 0" in captured.out
    assert (
        tmp_path
        / "planilhas"
        / datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
        / "cielo"
        / "CIELO_CONCILIACAO_2026-07-13_A_2026-07-13.xlsx"
    ).exists()


def test_testar_matching_cielo_and_quickpay_use_local_fixtures(capsys):
    cielo_code = main(
        [
            "testar-matching",
            "--operadora",
            "cielo",
            "--fixtures",
            "tests/fixtures/matching",
        ]
    )
    quickpay_code = main(
        [
            "testar-matching",
            "--operadora",
            "quickpay",
            "--fixtures",
            "tests/fixtures/matching",
            "--sistema-extra",
        ]
    )

    captured = capsys.readouterr()
    assert cielo_code == 0
    assert quickpay_code == 0
    assert "SIMULACAO DE MATCHING" in captured.out
    assert "CONCILIACAO CIELO" in captured.out
    assert "CONCILIACAO QUICKPAY" in captured.out
    assert "Conciliadas: 10" in captured.out
    assert "Nao encontradas na operadora: 1" in captured.out
    assert "Chamadas reais realizadas: 0" in captured.out
    assert "Token solicitado: nao" in captured.out
