from __future__ import annotations

import os
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from conciliacao.gui import ConciliacaoWindow, WorkflowThread
from conciliacao.gui_widgets import FileSelector
from conciliacao.workflow import ReconciliationCommand, ReconciliationWorkflow, identificar_periodo


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app):
    widget = ConciliacaoWindow()
    yield widget
    widget.preview_timer.stop()
    widget.activity.timer.stop()
    widget.deleteLater()
    app.processEvents()


def test_file_selection_keeps_full_path_and_displays_filename(app):
    selector = FileSelector("Selecionar arquivo")
    path = "C:/pasta com espaços/planilha QuickPay.xlsx"
    selector.setText(path)
    assert selector.text() == path
    assert selector.display.text() == "planilha QuickPay.xlsx"
    assert selector.select_button.text() == "Trocar"
    selector.clear_button.click()
    assert selector.text() == ""
    assert selector.select_button.text() == "Selecionar"


def test_login_has_indeterminate_progress_and_error_stops_animation(window):
    window._progress("login", (date(2026, 9, 30), date(2026, 10, 1)))
    assert window.status.text() == "Aguardando login na Velo"
    assert "30/09/2026" in window.period.text()
    assert window.progress_bar.maximum() == 0
    assert window.activity.timer.isActive()
    window._failed("Falha de leitura")
    assert window.status.property("tone") == "error"
    assert window.progress_bar.maximum() == 100
    assert not window.activity.timer.isActive()
    assert window.logs_toggle.isChecked()


def test_collapse_preserves_audit_selection(window):
    window.salvar_auditoria.setChecked(True)
    window.advanced_toggle.setChecked(False)
    assert window.salvar_auditoria.isHidden()
    assert window.salvar_auditoria.isChecked()
    window.logs_toggle.setChecked(False)
    assert window.log.isHidden()


def test_preview_uses_real_dates_and_writes_no_outputs(tmp_path, monkeypatch):
    source = Path("tests/fixtures/quickpay/quickpay_valido.xlsx").resolve()
    contents = source.read_bytes()
    monkeypatch.chdir(tmp_path)
    command = ReconciliationCommand(arquivo_quickpay=source)
    start, end = identificar_periodo(command)
    assert start <= end
    assert start.year == 2026
    assert source.read_bytes() == contents
    assert list(tmp_path.iterdir()) == []


def test_simulated_completion_has_real_report_buttons_and_summary(window, tmp_path):
    command = ReconciliationCommand(
        arquivo_cielo=Path("tests/fixtures/cielo/cielo_valido.xlsx"),
        diretorio_saida=tmp_path / "output",
        diretorio_planilhas=tmp_path / "planilhas",
        modo_simulado=True,
        diretorio_fixtures_api=Path("tests/fixtures/api"),
        salvar_auditoria=False,
    )
    events = []
    result = ReconciliationWorkflow(
        progress_callback=lambda stage, period: events.append((stage, period)),
    ).executar(command)
    assert events[0][0] == "leitura"
    assert events[1][1] == identificar_periodo(command)
    assert events[-1][0] == "resumos"
    window._completed(result)
    assert window._result_paths == [result.resultado_cielo.arquivo_saida.resolve()]
    assert not window.activity.timer.isActive()
    assert "CIELO" in window.log.toPlainText()


def test_worker_login_reports_stages_without_exposing_token(app, monkeypatch):
    import conciliacao.gui as gui

    monkeypatch.setattr(gui, "capture_token_from_visible_chrome", lambda **kwargs: "fake-session")
    worker = WorkflowThread(cielo="", quickpay="", recebimentos="", salvar_auditoria=False)
    events = []
    worker.progress.connect(lambda stage, period: events.append((stage, period)))
    assert worker._capture() == "fake-session"
    assert events == [("login", None), ("consulta", None)]


@pytest.mark.parametrize("fail", [False, True])
def test_worker_discards_session_after_success_or_failure(app, monkeypatch, fail):
    import conciliacao.gui as gui
    from conciliacao.integrations.velo.manual_login import ManualLoginTokenProvider

    source = str(Path("tests/fixtures/cielo/cielo_valido.xlsx").resolve())
    providers = []

    class RecordingProvider(ManualLoginTokenProvider):
        def __init__(self, capture):
            super().__init__(capture)
            providers.append(self)

    class FakeWorkflow:
        def __init__(self, *, token_provider, **kwargs):
            self.provider = token_provider

        def executar(self, command):
            self.provider.get_token()
            if fail:
                raise ValueError("Falha controlada")
            return object()

    monkeypatch.setattr(gui, "ManualLoginTokenProvider", RecordingProvider)
    monkeypatch.setattr(gui, "ReconciliationWorkflow", FakeWorkflow)
    monkeypatch.setattr(gui, "capture_token_from_visible_chrome", lambda **kwargs: "fake-session")
    worker = WorkflowThread(cielo=source, quickpay="", recebimentos="", salvar_auditoria=False)
    messages = []
    worker.log_message.connect(messages.append)
    worker.failed.connect(messages.append)
    worker.run()
    assert len(providers) == 1
    assert providers[0]._token is None
    assert "fake-session" not in "\n".join(messages)
