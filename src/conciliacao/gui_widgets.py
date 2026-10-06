"""Componentes visuais da interface, sem regras financeiras ou acesso à rede."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPaintEvent, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 14px; color: #203252; }
QWidget#window, QScrollArea, QWidget#content { background: #f3f8f6; }
QScrollArea { border: none; }
QFrame#card { background: #ffffff; border: 1px solid #e2ebe7; border-radius: 12px; }
QLabel { background: transparent; border: none; }
QLabel#title { color: #075334; font-size: 32px; font-weight: 700; }
QLabel#subtitle { color: #687991; font-size: 20px; font-weight: 600; }
QLabel#heading { font-size: 18px; font-weight: 700; }
QLabel#muted { color: #7688a4; }
QLabel#fileLabel { font-size: 15px; font-weight: 600; }
QLabel#period { color: #008344; font-size: 21px; font-weight: 700; }
QFrame#periodBox { background: #ecf9f3; border: none; border-radius: 9px; }
QLabel#statusTitle { color: #075334; font-size: 24px; font-weight: 700; }
QLabel#statusTitle[tone='error'] { color: #b23e35; }
QLabel#statusTitle[tone='warning'] { color: #966114; }
QLabel#statusDetail { color: #536782; font-size: 15px; }
QFrame#fileBox { background: #ffffff; border: 1px solid #cdd7e3; border-radius: 6px; }
QFrame#fileBox[selected='true'] { border-color: #abcdbb; }
QLineEdit { background: transparent; border: none; padding: 0; font-size: 14px; }
QLineEdit:disabled { color: #7f8b9d; }
QPushButton { background: #f7f9fc; border: 1px solid #cdd7e3; border-radius: 6px;
    padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: #edf5f0; border-color: #78b593; }
QPushButton:pressed { background: #dceddf; }
QPushButton:focus { border: 2px solid #008747; }
QPushButton:disabled { color: #99a6b7; background: #f1f4f6; border-color: #e0e6eb; }
QPushButton[selected='true'] { color: #008044; border-color: #209963; background: #f4fbf7; }
QPushButton#clear { border: none; background: transparent; padding: 0; font-size: 19px; }
QPushButton#start { color: white; font-size: 20px; border: none; border-radius: 7px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #009254,stop:1 #006d43); }
QPushButton#start:hover { background: #009654; }
QPushButton#start:pressed { background: #005d39; }
QPushButton#start:disabled { background: #a3c9b6; color: #edf7f1; }
QPushButton#disclosure { background: transparent; border: none; text-align: left;
    padding: 0; font-size: 17px; font-weight: 700; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 22px; height: 22px; border: 1px solid #9daaBC;
    border-radius: 5px; background: white; }
QCheckBox::indicator:checked { background: #00854b; border-color: #00854b; }
QProgressBar { border: none; background: #e1e8ef; border-radius: 7px; height: 14px; }
QProgressBar::chunk { background: #9ed8bd; border-radius: 7px; }
QPlainTextEdit { background: #f5f7fa; border: 1px solid #d5dfe7; border-radius: 6px;
    padding: 7px; font-family: Consolas, 'Courier New'; font-size: 12px; }
QToolTip { background: #ffffff; color: #203252; border: 1px solid #cdd7e3; padding: 6px; }
"""

_PATHS = {
    "file": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h4M9 12h6M9 16h6"/>',
    "folder": '<path d="M3 6h6l2 3h10v11H3z"/>',
    "refresh": '<path d="M20 9a8 8 0 0 0-14-3L3 9m0-5v5h5M4 15a8 8 0 0 0 14 3l3-3m0 5v-5h-5"/>',
    "check": '<circle cx="12" cy="12" r="10" fill="currentColor" stroke="none"/>'
    '<path d="m7 12 3 3 7-7" stroke="white"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/>'
    '<path d="M7 2v6M17 2v6M3 10h18M7 14h2M13 14h2M7 18h2M13 18h2"/>',
    "settings": '<path d="m9 3-1 3-3 1 1 3-2 2 2 2-1 3 3 1 1 3h6'
    'l1-3 3-1-1-3 2-2-2-2 1-3-3-1-1-3z"/>'
    '<circle cx="12" cy="12" r="3"/>',
    "bars": '<path d="M5 13v8M12 4v17M19 9v12" stroke-width="5"/>',
    "play": '<path d="m7 3 14 9-14 9z" fill="currentColor" stroke="none"/>',
}


def icon(name: str, color: str = "#008344", size: int = 26) -> QIcon:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        f'viewBox="0 0 24 24" color="{color}" fill="none" stroke="currentColor" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f"{_PATHS[name]}</svg>"
    )
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(svg.encode()).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    result = QLabel(text)
    result.setObjectName(name)
    result.setWordWrap(wrap)
    result.setTextFormat(Qt.TextFormat.PlainText)
    return result


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 17, 20, 17)
    layout.setSpacing(12)
    return frame, layout


def heading(text: str, name: str) -> QHBoxLayout:
    row = QHBoxLayout()
    image = QLabel()
    image.setPixmap(icon(name, size=28).pixmap(28, 28))
    image.setFixedSize(32, 32)
    row.addWidget(image)
    row.addSpacing(6)
    row.addWidget(label(text, "heading"))
    row.addStretch()
    return row


class Header(QWidget):
    def __init__(self, logo: Path) -> None:
        super().__init__()
        self.setMinimumHeight(116)
        row = QHBoxLayout(self)
        row.setContentsMargins(22, 10, 22, 10)
        if logo.is_file():
            image = QLabel()
            image.setPixmap(
                QPixmap(str(logo)).scaled(
                    120,
                    102,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            image.setFixedWidth(132)
            row.addWidget(image)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        titles.addStretch()
        titles.addWidget(label("Conciliação de Cartões", "title"))
        titles.addWidget(label("Cielo • QuickPay • Velo", "subtitle"))
        titles.addStretch()
        row.addLayout(titles)
        row.addStretch()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        for offset, color in ((0, "#e3f2e9"), (90, "#d6ece1")):
            path = QPainterPath()
            path.moveTo(width * 0.48 + offset, height)
            path.cubicTo(width * 0.68, 0, width * 0.72, height * 1.4, width, -30 + offset)
            path.lineTo(width, height)
            path.closeSubpath()
            painter.fillPath(path, QColor(color))
        painter.end()


class FileSelector(QWidget):
    textChanged = Signal(str)

    def __init__(self, dialog_title: str) -> None:
        super().__init__()
        self._path = ""
        self.dialog_title = dialog_title
        self.setFixedHeight(42)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        self.box = QFrame()
        self.box.setObjectName("fileBox")
        inner = QHBoxLayout(self.box)
        inner.setContentsMargins(12, 0, 8, 0)
        self.indicator = QLabel()
        inner.addWidget(self.indicator)
        self.display = QLineEdit()
        self.display.setReadOnly(True)
        self.display.setPlaceholderText("Nenhum arquivo selecionado")
        inner.addWidget(self.display, 1)
        self.clear_button = QPushButton("×")
        self.clear_button.setObjectName("clear")
        self.clear_button.setFixedSize(26, 30)
        self.clear_button.setAccessibleName(f"Remover: {dialog_title}")
        self.clear_button.clicked.connect(lambda: self.setText(""))
        inner.addWidget(self.clear_button)
        row.addWidget(self.box, 1)
        self.select_button = QPushButton()
        self.select_button.setFixedSize(135, 42)
        self.select_button.setIconSize(QSize(22, 22))
        self.select_button.clicked.connect(self._select)
        self.select_button.setAccessibleName(dialog_title)
        row.addWidget(self.select_button)
        self.box.setMinimumHeight(42)
        self.setText("")

    def text(self) -> str:
        return self._path

    def setText(self, path: str) -> None:
        changed = path != self._path
        self._path = path
        self.display.setText(Path(path).name if path else "")
        self.display.setToolTip(path)
        self.display.setCursorPosition(0)
        self.indicator.setPixmap(
            icon("check" if path else "file", "#008344" if path else "#99a4b2", 23).pixmap(23, 23)
        )
        self.clear_button.setVisible(bool(path))
        self.select_button.setText("Trocar" if path else "Selecionar")
        self.select_button.setIcon(
            icon("refresh" if path else "folder", "#008344" if path else "#203252", 22)
        )
        for widget in (self.box, self.select_button):
            widget.setProperty("selected", bool(path))
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        if changed:
            self.textChanged.emit(path)

    def _select(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            self.dialog_title,
            self._path,
            "Planilhas Excel (*.xlsx *.xls);;Todos os arquivos (*.*)",
        )
        if selected:
            self.setText(selected)


class DisclosureButton(QPushButton):
    """Cabeçalho recolhível com seta alinhada à direita, sem espaços artificiais."""

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#203252"), 2))
        x, y = self.width() - 14, self.height() // 2
        offset = -4 if self.isChecked() else 4
        painter.drawLine(x - 5, y, x, y + offset)
        painter.drawLine(x, y + offset, x + 5, y)
        painter.end()


class ActivityIndicator(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(68, 68)
        self.angle = 0
        self.active = False
        self.tone = "idle"
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        self.angle = (self.angle - 12) % 360
        self.update()

    def set_state(self, active: bool, tone: str = "idle") -> None:
        self.active, self.tone = active, tone
        if active:
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(8, 8, 52, 52)
        pen = QPen(QColor("#daebe3"), 7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawEllipse(rect)
        color = {"error": "#b23e35", "warning": "#b98121"}.get(self.tone, "#008344")
        painter.setPen(QPen(QColor(color), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if self.active:
            painter.drawArc(rect, self.angle * 16, 110 * 16)
        elif self.tone == "success":
            painter.drawLine(23, 34, 31, 42)
            painter.drawLine(31, 42, 47, 26)
        elif self.tone in ("error", "warning"):
            painter.drawLine(34, 22, 34, 36)
            painter.drawPoint(34, 46)
        else:
            painter.drawArc(rect, 45 * 16, 90 * 16)
        painter.end()
