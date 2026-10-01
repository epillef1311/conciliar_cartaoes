"""Interface Windows para o workflow completo de conciliação."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplashScreen,
    QVBoxLayout,
    QWidget,
)

from conciliacao.integrations.velo.manual_login import ManualLoginTokenProvider
from conciliacao.workflow import ReconciliationCommand, ReconciliationWorkflow, WorkflowStatus


def _base_directory() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()


def _resource_path(relative: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", _base_directory())) / relative


class WorkflowThread(QThread):
    completed = Signal(object)
    failed = Signal(str)
    log_message = Signal(str)

    def __init__(
        self, *, cielo: str, quickpay: str, recebimentos: str, salvar_auditoria: bool
    ) -> None:
        super().__init__()
        self.cielo = cielo
        self.quickpay = quickpay
        self.recebimentos = recebimentos
        self.salvar_auditoria = salvar_auditoria

    def run(self) -> None:
        provider = ManualLoginTokenProvider()
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
            self.completed.emit(
                ReconciliationWorkflow(
                    token_provider=provider, log_callback=self.log_message.emit
                ).executar(command)
            )
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            provider.clear()


class ConciliacaoWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.thread: WorkflowThread | None = None
        self.setWindowTitle("Conciliação de Cartões — Frigorífico Candeias")
        self.setMinimumSize(920, 680)
        logo = _resource_path("assets/frigorifico-candeias-logo-cortada.png")
        if logo.is_file():
            self.setWindowIcon(QIcon(str(logo)))
        self._build(logo)

    def _build(self, logo: Path) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        header = QHBoxLayout()
        if logo.is_file():
            image = QLabel()
            image.setPixmap(
                QPixmap(str(logo)).scaledToWidth(62, Qt.TransformationMode.SmoothTransformation)
            )
            image.setFixedWidth(72)
            header.addWidget(image)
        title = QLabel("Conciliação de Cartões")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #007A35;")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        form = QFormLayout()
        self.cielo = self._file_field(form, "Arquivo Cielo", "Selecione a planilha Cielo")
        self.quickpay = self._file_field(form, "Arquivo QuickPay", "Selecione a planilha QuickPay")
        self.recebimentos = self._file_field(
            form,
            "Recebimentos bancários QuickPay (opcional)",
            "Selecione a planilha auxiliar confirmada",
        )
        self.recebimentos.setToolTip(
            "Opcional: sem recebimentos, a conciliação com a Velo continua normalmente; "
            "a conferência bancária fica pendente. "
            "Use somente a planilha auxiliar com data, bandeira, modalidade e valor confirmados."
        )
        layout.addLayout(form)
        info = QLabel(
            "Período automático: calculado pelas datas das planilhas. "
            "Débito usa a data de recebimento."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        self.salvar_auditoria = QCheckBox("Salvar auditoria de respostas da Velo")
        self.salvar_auditoria.setToolTip(
            "Guarda as respostas brutas em data/api_raw/, fora do repositório."
        )
        layout.addWidget(self.salvar_auditoria)
        self.start_button = QPushButton("Iniciar conciliação")
        self.start_button.clicked.connect(self._start)
        self.start_button.setFixedWidth(180)
        layout.addWidget(self.start_button)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separator)
        self.status = QLabel("Status: selecione os arquivos para começar.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("O andamento da conciliação será exibido aqui.")
        self.log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.log.setStyleSheet(
            "QPlainTextEdit { background: #FFFFFF; color: #202020; border: 1px solid #A0A0A0; "
            "font-family: Consolas, 'Courier New', monospace; font-size: 11px; }"
        )
        layout.addWidget(self.log, 1)

    def _file_field(self, form: QFormLayout, label: str, dialog_title: str) -> QLineEdit:
        field = QLineEdit()
        field.setReadOnly(True)
        button = QPushButton("Selecionar")
        button.clicked.connect(lambda: self._select(field, dialog_title))
        row = QHBoxLayout()
        row.addWidget(field)
        row.addWidget(button)
        form.addRow(label, row)
        return field

    def _select(self, field: QLineEdit, title: str) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, title, "", "Planilhas Excel (*.xlsx *.xls);;Todos os arquivos (*.*)"
        )
        if selected:
            field.setText(selected)

    def _start(self) -> None:
        if not self.cielo.text() and not self.quickpay.text():
            QMessageBox.critical(
                self,
                "Arquivos necessários",
                "Selecione pelo menos um arquivo Cielo ou QuickPay.",
            )
            return
        self.start_button.setEnabled(False)
        self.log.clear()
        self._append_log("CONCILIAÇÃO INICIADA")
        self._append_log(f"Arquivo Cielo: {self.cielo.text() or '(não informado)'}")
        self._append_log(f"Arquivo QuickPay: {self.quickpay.text() or '(não informado)'}")
        self._append_log("Período: calculado automaticamente pelas planilhas.")
        self._append_log("Chrome será aberto para o login manual na Velo.")
        self.status.setText("Status: preparando arquivos. Aguarde o login manual na Velo.")
        self.thread = WorkflowThread(
            cielo=self.cielo.text(),
            quickpay=self.quickpay.text(),
            recebimentos=self.recebimentos.text(),
            salvar_auditoria=self.salvar_auditoria.isChecked(),
        )
        self.thread.completed.connect(self._completed)
        self.thread.failed.connect(self._failed)
        self.thread.log_message.connect(self._append_log)
        self.thread.start()

    def _completed(self, result: object) -> None:
        assert hasattr(result, "status_geral")
        self.start_button.setEnabled(True)
        self._append_result_summary(result)
        self.status.setText(
            f"Status: concluído — {result.status_geral.value}. "
            f"Resultados em: {_base_directory() / 'planilhas'}"
        )
        if result.status_geral is WorkflowStatus.FALHA:
            QMessageBox.critical(self, "Conciliação não concluída", "Verifique o resumo e os logs.")
        else:
            QMessageBox.information(self, "Conciliação concluída", "Os relatórios foram gerados.")

    def _failed(self, message: str) -> None:
        self.start_button.setEnabled(True)
        self._append_log(f"FALHA: {message}")
        self.status.setText("Status: a conciliação não foi iniciada.")
        QMessageBox.critical(self, "Erro", message)

    def _append_log(self, message: str) -> None:
        self.log.appendPlainText(message)
        scrollbar = self.log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _append_result_summary(self, result: object) -> None:
        self._append_log("")
        self._append_log(f"CONCILIAÇÃO FINALIZADA COM {result.status_geral.value}")
        self._append_log(f"Execução: {result.identificador_execucao}")
        self._append_log(
            "Período: "
            f"{result.periodo['inicio'].strftime('%d/%m/%Y')} a "
            f"{result.periodo['fim'].strftime('%d/%m/%Y')}"
        )
        resultados = (("CIELO", result.resultado_cielo), ("QUICKPAY", result.resultado_quickpay))
        for nome, operador in resultados:
            if operador is None:
                continue
            resumo = operador.resumo_matching or {}
            self._append_log("")
            self._append_log(nome)
            self._append_log(f"Status: {operador.status.value}")
            self._append_log(f"Transações: {operador.quantidade_lida}")
            self._append_log(f"Conciliadas: {resumo.get('conciliadas', 0)}")
            self._append_log(f"Pendentes: {resumo.get('pendentes', 0)}")
            self._append_log(f"Arquivo: {operador.arquivo_saida or '(não gerado)'}")
            if (
                nome == "QUICKPAY"
                and (operador.resumo_processamento or {}).get("conferencia_bancaria")
                == "NAO_REALIZADA"
            ):
                self._append_log(
                    "Conferência bancária não realizada: "
                    "recebimentos não informados ou incompletos."
                )
            for erro in operador.erros:
                self._append_log(f"Erro: {erro}")
        for erro in result.erros_globais:
            self._append_log(f"Erro global: {erro}")


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
    if splash is None:
        window.show()
    else:
        QTimer.singleShot(900, lambda: _show_main_window(splash, window))
    sys.exit(app.exec())


def _show_main_window(splash: QSplashScreen, window: ConciliacaoWindow) -> None:
    window.show()
    splash.finish(window)


if __name__ == "__main__":
    main()
