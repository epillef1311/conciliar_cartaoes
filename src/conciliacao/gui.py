"""Interface Windows para o workflow completo de conciliação."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices, QFontDatabase, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplashScreen,
    QVBoxLayout,
    QWidget,
)

from conciliacao.gui_widgets import (
    STYLE,
    ActivityIndicator,
    DisclosureButton,
    FileSelector,
    Header,
    card,
    heading,
    icon,
    label,
)
from conciliacao.integrations.velo.manual_login import (
    ManualLoginTokenProvider,
    capture_token_from_visible_chrome,
)
from conciliacao.workflow import (
    ReconciliationCommand,
    ReconciliationWorkflow,
    WorkflowResult,
    WorkflowStatus,
    _safe_error,
    formatar_resumo_workflow,
    identificar_periodo,
)


def _base_directory() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()


def _resource_path(relative: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", _base_directory())) / relative


class PeriodThread(QThread):
    identified = Signal(object)
    failed = Signal(str)

    def __init__(self, paths: tuple[str, str]) -> None:
        super().__init__()
        self.paths = paths

    def run(self) -> None:
        try:
            command = ReconciliationCommand(
                arquivo_cielo=Path(self.paths[0]) if self.paths[0] else None,
                arquivo_quickpay=Path(self.paths[1]) if self.paths[1] else None,
            )
            self.identified.emit(identificar_periodo(command))
        except Exception as exc:
            self.failed.emit(_safe_error(exc))


class WorkflowThread(QThread):
    completed = Signal(object)
    failed = Signal(str)
    log_message = Signal(str)
    progress = Signal(str, object)

    def __init__(
        self, *, cielo: str, quickpay: str, recebimentos: str, salvar_auditoria: bool
    ) -> None:
        super().__init__()
        self.cielo = cielo
        self.quickpay = quickpay
        self.recebimentos = recebimentos
        self.salvar_auditoria = salvar_auditoria

    def _capture(self) -> str:
        self.progress.emit("login", None)
        token = capture_token_from_visible_chrome()
        self.progress.emit("consulta", None)
        return token

    def run(self) -> None:
        provider = ManualLoginTokenProvider(capture=self._capture)
        result: WorkflowResult | None = None
        failure: str | None = None
        try:
            base = _base_directory()
            command = ReconciliationCommand(
                arquivo_cielo=Path(self.cielo) if self.cielo else None,
                arquivo_quickpay=Path(self.quickpay) if self.quickpay else None,
                arquivo_recebimentos_quickpay=Path(self.recebimentos)
                if self.recebimentos
                else None,
                diretorio_saida=base / "output",
                diretorio_planilhas=base / "planilhas",
                salvar_auditoria=self.salvar_auditoria,
            )
            result = ReconciliationWorkflow(
                token_provider=provider,
                log_callback=self.log_message.emit,
                progress_callback=self.progress.emit,
            ).executar(command)
        except Exception as exc:
            failure = _safe_error(exc)
        finally:
            provider.clear()
        if failure is not None:
            self.failed.emit(failure)
        elif result is not None:
            self.completed.emit(result)


class ConciliacaoWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        if "Segoe UI" not in QFontDatabase.families():
            fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
            for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "consola.ttf"):
                QFontDatabase.addApplicationFont(str(fonts / name))
        self.workflow_thread: WorkflowThread | None = None
        self.period_thread: PeriodThread | None = None
        self._running = False
        self._result_paths: list[Path] = []
        self.setWindowTitle("Conciliação de Cartões — Frigorífico Candeias")
        self.setObjectName("window")
        self.setMinimumSize(960, 680)
        self.resize(1280, 820)
        self.setStyleSheet(STYLE)
        logo = _resource_path("assets/frigorifico-candeias-logo-cortada.png")
        if logo.is_file():
            self.setWindowIcon(QIcon(str(logo)))
        self._build(logo)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(250)
        self.preview_timer.timeout.connect(self._preview_period)
        for field in (self.cielo, self.quickpay):
            field.textChanged.connect(self._files_changed)

    def _build(self, logo: Path) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(Header(logo))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 10, 18, 16)
        layout.setSpacing(12)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        top = QHBoxLayout()
        top.setSpacing(12)
        files, files_layout = card()
        files_layout.addLayout(heading("Arquivos para conciliação", "file"))
        files_layout.addWidget(
            label(
                "Selecione os arquivos necessários para realizar a conciliação.",
                "muted",
                True,
            )
        )
        form = QGridLayout()
        form.setHorizontalSpacing(15)
        form.setVerticalSpacing(18)
        self.cielo = FileSelector("Selecione a planilha Cielo")
        self.quickpay = FileSelector("Selecione a planilha QuickPay")
        self.recebimentos = FileSelector("Selecione a planilha auxiliar confirmada")
        self.recebimentos.setToolTip(
            "Opcional: sem recebimentos, a conciliação com a Velo continua normalmente; "
            "a conferência bancária fica pendente. Use somente a planilha auxiliar com "
            "data, bandeira, modalidade e valor confirmados pelo usuário."
        )
        for row, (text, field) in enumerate(
            (
                ("Arquivo Cielo", self.cielo),
                ("Arquivo QuickPay", self.quickpay),
                ("Recebimentos bancários\nQuickPay (opcional)", self.recebimentos),
            )
        ):
            name = label(text, "fileLabel", True)
            name.setMinimumWidth(190)
            name.setMaximumWidth(190)
            form.addWidget(name, row, 0)
            form.addWidget(field, row, 1)
        form.setColumnStretch(1, 1)
        files_layout.addSpacing(5)
        files_layout.addLayout(form)
        files_layout.addStretch()
        top.addWidget(files, 7)

        sidebar = QVBoxLayout()
        sidebar.setSpacing(12)
        period_card, period_layout = card()
        period_card.setMinimumWidth(320)
        period_layout.addLayout(heading("Período identificado", "calendar"))
        period_box = QFrame()
        period_box.setObjectName("periodBox")
        box_layout = QVBoxLayout(period_box)
        box_layout.setContentsMargins(12, 15, 12, 15)
        self.period = label("Selecione as planilhas", "period", True)
        self.period.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box_layout.addWidget(self.period)
        note = label("Débito considera a data de recebimento.", "statusDetail", True)
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box_layout.addWidget(note)
        period_layout.addWidget(period_box)
        sidebar.addWidget(period_card, 1)

        advanced, advanced_layout = card()
        self.advanced_toggle = DisclosureButton("Opções avançadas")
        self.advanced_toggle.setObjectName("disclosure")
        self.advanced_toggle.setIcon(icon("settings"))
        self.advanced_toggle.setIconSize(QSize(25, 25))
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setChecked(True)
        advanced_layout.addWidget(self.advanced_toggle)
        self.salvar_auditoria = QCheckBox("Salvar respostas da Velo para auditoria")
        self.salvar_auditoria.setToolTip(
            "Guarda as respostas brutas em data/api_raw/, fora do Git."
        )
        advanced_layout.addWidget(self.salvar_auditoria)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        sidebar.addWidget(advanced)
        top.addLayout(sidebar, 3)
        layout.addLayout(top)

        self.start_button = QPushButton("  Iniciar conciliação")
        self.start_button.setObjectName("start")
        self.start_button.setIcon(icon("play", "#ffffff", 30))
        self.start_button.setIconSize(QSize(30, 30))
        self.start_button.setMinimumHeight(54)
        self.start_button.clicked.connect(self._start)
        layout.addWidget(self.start_button)

        status_card, status_layout = card()
        status_layout.addLayout(heading("Status da conciliação", "bars"))
        status_row = QHBoxLayout()
        status_row.setSpacing(24)
        self.activity = ActivityIndicator()
        status_row.addWidget(self.activity)
        status_text = QVBoxLayout()
        status_text.setSpacing(6)
        self.status = label("Pronto para começar", "statusTitle", True)
        self.status_detail = label(
            "Selecione um arquivo Cielo ou QuickPay para iniciar.",
            "statusDetail",
            True,
        )
        status_text.addWidget(self.status)
        status_text.addWidget(self.status_detail)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(14)
        status_text.addWidget(self.progress_bar)
        status_row.addLayout(status_text, 1)
        status_layout.addLayout(status_row)
        self.results = QWidget()
        self.results_layout = QHBoxLayout(self.results)
        self.results_layout.setContentsMargins(92, 4, 0, 0)
        status_layout.addWidget(self.results)
        self.results.hide()
        layout.addWidget(status_card)

        logs_card, logs_layout = card()
        self.logs_toggle = DisclosureButton("Detalhes da execução")
        self.logs_toggle.setObjectName("disclosure")
        self.logs_toggle.setIcon(icon("file"))
        self.logs_toggle.setCheckable(True)
        self.logs_toggle.setChecked(True)
        self.logs_toggle.toggled.connect(self._toggle_logs)
        logs_layout.addWidget(self.logs_toggle)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("O andamento da conciliação será exibido aqui.")
        self.log.setMinimumHeight(85)
        self.log.setMaximumBlockCount(3000)
        logs_layout.addWidget(self.log, 1)
        layout.addWidget(logs_card, 1)

    def _toggle_advanced(self, expanded: bool) -> None:
        self.salvar_auditoria.setVisible(expanded)

    def _toggle_logs(self, expanded: bool) -> None:
        self.log.setVisible(expanded)

    def _files_changed(self, path: str) -> None:
        self.period.setText(
            "Identificando período…" if self._paths() != ("", "") else "Selecione as planilhas"
        )
        self.period.setToolTip("")
        self.preview_timer.start()

    def _paths(self) -> tuple[str, str]:
        return self.cielo.text(), self.quickpay.text()

    def _preview_period(self) -> None:
        if self._running or self._paths() == ("", ""):
            return
        if self.period_thread is not None:
            return
        worker = PeriodThread(self._paths())
        self.period_thread = worker
        worker.identified.connect(lambda value: self._preview_result(worker, value, ""))
        worker.failed.connect(lambda error: self._preview_result(worker, None, error))
        worker.finished.connect(self._preview_finished)
        worker.start()

    def _preview_result(
        self,
        worker: PeriodThread,
        periodo: tuple[date, date] | None,
        error: str,
    ) -> None:
        if not self._running and worker.paths == self._paths():
            if periodo is not None:
                self._set_period(periodo)
            else:
                self.period.setText("Confira as planilhas")
                self.period.setToolTip(error)

    def _preview_finished(self) -> None:
        worker = self.period_thread
        self.period_thread = None
        if worker is not None:
            changed = worker.paths != self._paths()
            worker.deleteLater()
            if changed:
                self.preview_timer.start()

    def _set_period(self, periodo: tuple[date, date]) -> None:
        self.period.setText(f"{periodo[0]:%d/%m/%Y}  →  {periodo[1]:%d/%m/%Y}")
        self.period.setToolTip("Período calculado pelas datas das planilhas selecionadas.")

    def _set_status(
        self, title: str, detail: str, *, active: bool = False, tone: str = "idle"
    ) -> None:
        self.status.setText(title)
        self.status.setProperty("tone", tone)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status_detail.setText(detail)
        self.activity.set_state(active, tone)
        self.progress_bar.setRange(0, 0 if active else 100)
        self.progress_bar.setValue(100 if tone in ("success", "warning") else 0)

    def _progress(self, stage: str, periodo: tuple[date, date] | None) -> None:
        if periodo is not None:
            self._set_period(periodo)
        stages = {
            "leitura": ("Lendo as planilhas", "Validando os arquivos e identificando o período."),
            "login": (
                "Aguardando login na Velo",
                "Faça o login na janela do Chrome para continuar.",
            ),
            "consulta": ("Consultando a Velo", "Buscando os registros do período identificado."),
            "cielo": ("Conciliando Cielo", "Conferindo as transações e gerando o relatório Cielo."),
            "quickpay": (
                "Conciliando QuickPay",
                "Conferindo as transações e gerando o relatório QuickPay.",
            ),
            "resumos": (
                "Finalizando os relatórios",
                "Salvando os resumos e os arquivos da execução.",
            ),
        }
        if stage in stages:
            self._set_status(*stages[stage], active=True)

    def _start(self) -> None:
        if self._running or (self.workflow_thread is not None and self.workflow_thread.isRunning()):
            return
        if not self.cielo.text() and not self.quickpay.text():
            QMessageBox.critical(
                self, "Arquivos necessários", "Selecione pelo menos um arquivo Cielo ou QuickPay."
            )
            return
        self._running = True
        self.preview_timer.stop()
        for widget in (
            self.cielo,
            self.quickpay,
            self.recebimentos,
            self.salvar_auditoria,
            self.start_button,
        ):
            widget.setEnabled(False)
        self.start_button.setText("  Conciliação em andamento")
        self.results.hide()
        self.log.clear()
        self._append_log("CONCILIAÇÃO INICIADA")
        self._append_log(f"Arquivo Cielo: {self.cielo.text() or '(não informado)'}")
        self._append_log(f"Arquivo QuickPay: {self.quickpay.text() or '(não informado)'}")
        self.period.setText("Identificando período…")
        self._progress("leitura", None)
        self.workflow_thread = WorkflowThread(
            cielo=self.cielo.text(),
            quickpay=self.quickpay.text(),
            recebimentos=self.recebimentos.text(),
            salvar_auditoria=self.salvar_auditoria.isChecked(),
        )
        self.workflow_thread.completed.connect(self._completed)
        self.workflow_thread.failed.connect(self._failed)
        self.workflow_thread.log_message.connect(self._append_log)
        self.workflow_thread.progress.connect(self._progress)
        self.workflow_thread.finished.connect(self._workflow_finished)
        self.workflow_thread.start()

    def _workflow_finished(self) -> None:
        self._running = False
        for widget in (
            self.cielo,
            self.quickpay,
            self.recebimentos,
            self.salvar_auditoria,
            self.start_button,
        ):
            widget.setEnabled(True)
        self.start_button.setText("  Iniciar conciliação")
        if self.workflow_thread is not None:
            self.workflow_thread.deleteLater()
            self.workflow_thread = None

    def _completed(self, result: WorkflowResult) -> None:
        self._append_result_summary(result)
        failed = result.status_geral is WorkflowStatus.FALHA
        partial = result.status_geral is WorkflowStatus.SUCESSO_PARCIAL
        self._set_status(
            "Conciliação não concluída"
            if failed
            else "Concluída com pendências"
            if partial
            else "Conciliação concluída",
            "Confira os erros nos detalhes da execução."
            if failed
            else "Confira o resumo e os relatórios gerados abaixo.",
            tone="error" if failed else "warning" if partial else "success",
        )
        if self.period.text() == "Identificando período…":
            self.period.setText("Período não identificado")
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        self._result_paths = []
        for name, operator in (
            ("Cielo", result.resultado_cielo),
            ("QuickPay", result.resultado_quickpay),
        ):
            if operator is not None and operator.arquivo_saida is not None:
                path = operator.arquivo_saida.resolve()
                button = QPushButton(f"Abrir relatório {name}")
                button.clicked.connect(lambda checked=False, target=path: self._open_path(target))
                self.results_layout.addWidget(button)
                self._result_paths.append(path)
        if self._result_paths:
            folder = QPushButton("Abrir pasta de resultados")
            folder.clicked.connect(lambda: self._open_path(_base_directory() / "planilhas"))
            self.results_layout.addWidget(folder)
            self.results_layout.addStretch()
            self.results.show()
        if failed or partial:
            self.logs_toggle.setChecked(True)

    def _open_path(self, path: Path) -> None:
        if not path.exists() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(self, "Arquivo indisponível", f"Não foi possível abrir: {path}")

    def _failed(self, message: str) -> None:
        self._append_log(f"FALHA: {message}")
        self._set_status("Não foi possível concluir", message, tone="error")
        if self.period.text() == "Identificando período…":
            self.period.setText("Período não identificado")
        self.logs_toggle.setChecked(True)

    def _append_log(self, message: str) -> None:
        self.log.appendPlainText(f"{datetime.now():%H:%M:%S}  {message}")
        scrollbar = self.log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._running or self.period_thread is not None:
            event.ignore()
            QMessageBox.information(
                self,
                "Execução em andamento",
                "Aguarde a execução terminar antes de fechar a janela.",
            )
            return
        event.accept()

    def _append_result_summary(self, result: WorkflowResult) -> None:
        self._append_log(formatar_resumo_workflow(result))
        quickpay = result.resultado_quickpay
        if (
            quickpay is not None
            and (quickpay.resumo_processamento or {}).get("conferencia_bancaria") == "NAO_REALIZADA"
        ):
            self._append_log(
                "Conferência bancária QuickPay não realizada: "
                "recebimentos não informados ou incompletos."
            )
        for message in result.erros_globais:
            self._append_log(f"Erro global: {message}")
        for message in result.avisos_globais:
            self._append_log(f"Aviso: {message}")


def main() -> None:
    os.chdir(_base_directory())
    app = QApplication(sys.argv)
    logo = _resource_path("assets/frigorifico-candeias-logo-cortada.png")
    splash: QSplashScreen | None = None
    if logo.is_file():
        splash_pixmap = QPixmap(str(logo)).scaledToWidth(
            420, Qt.TransformationMode.SmoothTransformation
        )
        splash = QSplashScreen(splash_pixmap)
        splash.show()
        app.processEvents()
    window = ConciliacaoWindow()
    if "--verificar-interface" in sys.argv:
        if splash is not None:
            splash.finish(window)
        window.show()
        QTimer.singleShot(200, app.quit)
    elif splash is None:
        window.show()
    else:
        QTimer.singleShot(900, lambda: _show_main_window(splash, window))
    sys.exit(app.exec())


def _show_main_window(splash: QSplashScreen, window: ConciliacaoWindow) -> None:
    window.show()
    splash.finish(window)


if __name__ == "__main__":
    main()
