from __future__ import annotations

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
    assert exit_code == 2
    assert "data-fim nao pode ser anterior" in captured.out


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
