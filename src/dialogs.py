# © 2026 Created by Pavel Mareš
from datetime import date
import os
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QBuffer, QIODevice, QPointF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.pdf_engine import FormFieldInfo, TextLineInfo, float_rgb_to_hex, hex_to_float_rgb


def is_windows_dark_mode() -> bool:
    try:
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorScheme"):
            scheme = hints.colorScheme()
            if scheme == Qt.ColorScheme.Dark:
                return True
            if scheme == Qt.ColorScheme.Light:
                return False
    except Exception:
        pass
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            val, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
            return int(val) == 0
    except Exception:
        return True


def get_win11_stylesheet(dark: bool) -> str:
    if dark:
        return """
        QMainWindow, QDialog, QWidget { background-color: #0f172a; color: #f1f5f9; font-family: 'Segoe UI'; font-size: 13px; }
        QToolBar { background-color: #1e293b; border-bottom: 1px solid #334155; spacing: 5px; padding: 6px; }
        QToolButton, QPushButton { background-color: #1e293b; color: #f1f5f9; border: 1px solid #334155; border-radius: 8px; padding: 6px 11px; font-weight: 600; }
        QToolButton:hover, QPushButton:hover { background-color: #334155; border-color: #38bdf8; }
        QToolButton:checked { background-color: #0284c7; border-color: #38bdf8; color: #ffffff; }
        QLineEdit, QPlainTextEdit, QDoubleSpinBox, QComboBox, QListWidget { background-color: #1e293b; color: #f8fafc; border: 1px solid #334155; border-radius: 8px; padding: 6px; }
        QTabWidget::pane { border: 1px solid #334155; background: #0b1120; }
        QTabBar::tab { background: #1e293b; color: #94a3b8; padding: 8px 16px; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 3px; font-weight: 600; }
        QTabBar::tab:selected { background: #0284c7; color: #ffffff; }
        QScrollArea { background-color: #0b1120; border: none; }
        QStatusBar { background-color: #1e293b; color: #cbd5e1; border-top: 1px solid #334155; }
        """
    return """
    QMainWindow, QDialog, QWidget { background-color: #f8fafc; color: #0f172a; font-family: 'Segoe UI'; font-size: 13px; }
    QToolBar { background-color: #ffffff; border-bottom: 1px solid #e2e8f0; spacing: 5px; padding: 6px; }
    QToolButton, QPushButton { background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 8px; padding: 6px 11px; font-weight: 600; }
    QToolButton:hover, QPushButton:hover { background-color: #f1f5f9; border-color: #0284c7; }
    QToolButton:checked { background-color: #0284c7; border-color: #0369a1; color: #ffffff; }
    QLineEdit, QPlainTextEdit, QDoubleSpinBox, QComboBox, QListWidget { background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 8px; padding: 6px; }
    QTabWidget::pane { border: 1px solid #cbd5e1; background: #e2e8f0; }
    QTabBar::tab { background: #e2e8f0; color: #475569; padding: 8px 16px; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 3px; font-weight: 600; }
    QTabBar::tab:selected { background: #0284c7; color: #ffffff; }
    QScrollArea { background-color: #e2e8f0; border: none; }
    QStatusBar { background-color: #ffffff; color: #334155; border-top: 1px solid #e2e8f0; }
    """


class EditTextDialog(QDialog):
    def __init__(self, parent=None, info: Optional[TextLineInfo] = None, is_replace: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Přepsat text v PDF" if is_replace else "Vložit nový text do PDF")
        self.resize(480, 300)

        self.color_hex = float_rgb_to_hex(info.color_rgb) if info else "#000000"

        lay = QVBoxLayout(self)
        hint = QLabel(
            "Původní řádek bude čistě vymazán při zachování barvy pozadí a nahrazen novým textem:"
            if is_replace
            else "Zadej text pro vložení na kliknuté místo (podporuje více řádků i plnou češtinu):"
        )
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.editor = QPlainTextEdit(self)
        self.editor.setPlainText(info.text if info else "")
        self.editor.selectAll()
        lay.addWidget(self.editor, 1)

        row = QHBoxLayout()
        row.addWidget(QLabel("Velikost písma:"))
        self.size_spin = QDoubleSpinBox(self)
        self.size_spin.setRange(5.0, 96.0)
        self.size_spin.setSingleStep(0.5)
        self.size_spin.setValue(round(info.fontsize, 1) if info else 11.5)
        row.addWidget(self.size_spin)

        self.bold_chk = QCheckBox("Tučné", self)
        self.bold_chk.setChecked(info.is_bold if info else False)
        row.addWidget(self.bold_chk)

        self.col_btn = QPushButton("Barva písma", self)
        self._update_col_btn()
        self.col_btn.clicked.connect(self._pick_color)
        row.addWidget(self.col_btn)
        lay.addLayout(row)

        self.white_bg_chk = QCheckBox("Podložit bílým štítkem (zakryje podklad)", self)
        self.white_bg_chk.setChecked(False)
        lay.addWidget(self.white_bg_chk)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _update_col_btn(self) -> None:
        self.col_btn.setStyleSheet(f"background-color: {self.color_hex}; color: #ffffff; font-weight: 700; padding: 6px 12px; border-radius: 8px;")

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(self.color_hex), self, "Vyber barvu textu")
        if c.isValid():
            self.color_hex = c.name()
            self._update_col_btn()

    def get_result(self) -> Tuple[str, float, Tuple[float, float, float], bool, bool]:
        return (
            self.editor.toPlainText(),
            float(self.size_spin.value()),
            hex_to_float_rgb(self.color_hex),
            self.bold_chk.isChecked(),
            self.white_bg_chk.isChecked(),
        )


class _SignPadArea(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(500, 190)
        self.img = QImage(500, 190, QImage.Format.Format_ARGB32)
        self.img.fill(Qt.GlobalColor.transparent)
        self.pen_color = QColor("#1d4ed8")
        self._last_pt: Optional[QPointF] = None
        self.has_ink = False

    def clear_pad(self) -> None:
        self.img.fill(Qt.GlobalColor.transparent)
        self.has_ink = False
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#ffffff"))
        p.setPen(QPen(QColor("#cbd5e1"), 1.5, Qt.PenStyle.DashLine))
        p.drawLine(24, 145, 476, 145)
        p.drawImage(0, 0, self.img)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_pt = event.position()
            self.has_ink = True

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._last_pt is not None:
            cur = event.position()
            ip = QPainter(self.img)
            ip.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(self.pen_color, 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            ip.setPen(pen)
            ip.drawLine(self._last_pt, cur)
            ip.end()
            self._last_pt = cur
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._last_pt = None


class SignaturePadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vlastnoruční podpis do PDF")
        self._loaded_bytes: Optional[bytes] = None
        self._saved_sig_path = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AcrobatPM", "podpis.png")

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Podepiš se myší nebo perem (průhledné pozadí), případně načti uložený podpis:"))
        self.pad = _SignPadArea(self)
        lay.addWidget(self.pad, alignment=Qt.AlignmentFlag.AlignCenter)

        tools = QHBoxLayout()
        for title, hex_c in [("Modrá propiska", "#1d4ed8"), ("Černá", "#0f172a"), ("Červená", "#dc2626")]:
            b = QPushButton(title, self)
            b.clicked.connect(lambda _, c=hex_c: setattr(self.pad, "pen_color", QColor(c)))
            tools.addWidget(b)

        clr_btn = QPushButton("Smazat", self)
        clr_btn.clicked.connect(self._clear_all)
        tools.addWidget(clr_btn)
        lay.addLayout(tools)

        file_row = QHBoxLayout()
        load_img_btn = QPushButton("📂 Načíst obrázek podpisu / razítka...", self)
        load_img_btn.clicked.connect(self._load_external)
        file_row.addWidget(load_img_btn)

        if os.path.isfile(self._saved_sig_path):
            saved_btn = QPushButton("⚡ Použít můj uložený podpis", self)
            saved_btn.clicked.connect(self._use_saved)
            file_row.addWidget(saved_btn)
        lay.addLayout(file_row)

        self.remember_chk = QCheckBox("Uložit tento podpis pro příští použití jedním kliknutím", self)
        self.remember_chk.setChecked(True)
        lay.addWidget(self.remember_chk)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _clear_all(self) -> None:
        self._loaded_bytes = None
        self.pad.clear_pad()

    def _load_external(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Vyber obrázek podpisu", "", "Obrázky (*.png *.jpg *.jpeg *.webp)")
        if path:
            with open(path, "rb") as f:
                self._loaded_bytes = f.read()
            self.accept()

    def _use_saved(self) -> None:
        if os.path.isfile(self._saved_sig_path):
            with open(self._saved_sig_path, "rb") as f:
                self._loaded_bytes = f.read()
            self.accept()

    def get_png_bytes(self) -> Optional[bytes]:
        if self._loaded_bytes:
            return self._loaded_bytes
        if not self.pad.has_ink:
            return None
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        self.pad.img.save(buf, "PNG")
        raw = bytes(buf.data())
        if self.remember_chk.isChecked():
            try:
                os.makedirs(os.path.dirname(self._saved_sig_path), exist_ok=True)
                with open(self._saved_sig_path, "wb") as f:
                    f.write(raw)
            except Exception:
                pass
        return raw


class StampDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vložit razítko")
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.combo = QComboBox(self)
        self.combo.setEditable(True)
        today = date.today().strftime("%d.%m.%Y")
        self.combo.addItems([f"SCHVÁLENO {today}", f"ZAPLACENO {today}", "ORIGINÁL", "KOPIE", "STORNO", "DŮVĚRNÉ"])
        form.addRow("Text razítka:", self.combo)

        self.col_combo = QComboBox(self)
        self.col_combo.addItems(["Červená", "Zelená", "Modrá", "Černá"])
        form.addRow("Barva razítka:", self.col_combo)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def get_stamp(self) -> Tuple[str, Tuple[float, float, float]]:
        palette = {
            "Červená": (0.82, 0.12, 0.12),
            "Zelená": (0.08, 0.58, 0.28),
            "Modrá": (0.10, 0.36, 0.78),
            "Černá": (0.12, 0.15, 0.20),
        }
        return (self.combo.currentText().strip() or "SCHVÁLENO", palette.get(self.col_combo.currentText(), (0.82, 0.12, 0.12)))


class FormFieldsDialog(QDialog):
    def __init__(self, fields: List[FormFieldInfo], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vyplnit PDF formulář na aktuální straně")
        self.resize(500, 420)
        self.widgets_by_xref: Dict[int, QWidget] = {}

        lay = QVBoxLayout(self)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form = QFormLayout(inner)

        for f in fields:
            if f.choice_values:
                cb = QComboBox(inner)
                cb.setEditable(True)
                cb.addItems(f.choice_values)
                cb.setCurrentText(f.field_value)
                form.addRow(f.field_label + ":", cb)
                self.widgets_by_xref[f.xref] = cb
            else:
                le = QLineEdit(f.field_value, inner)
                form.addRow(f.field_label + ":", le)
                self.widgets_by_xref[f.xref] = le

        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def get_updated_values(self) -> Dict[int, str]:
        out: Dict[int, str] = {}
        for xref, w in self.widgets_by_xref.items():
            if isinstance(w, QComboBox):
                out[xref] = w.currentText()
            elif isinstance(w, QLineEdit):
                out[xref] = w.text()
        return out


class OcrResultDialog(QDialog):
    def __init__(self, extracted_text: str, page_num: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Rozpoznaný text ze skenu (OCR – strana {page_num})")
        self.resize(580, 440)
        lay = QVBoxLayout(self)

        self.txt = QPlainTextEdit(self)
        self.txt.setPlainText(extracted_text or "(Na stránce nebyl rozpoznán žádný čitelný text.)")
        lay.addWidget(self.txt, 1)

        row = QHBoxLayout()
        cp_btn = QPushButton("📋 Zkopírovat do schránky", self)
        cp_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.txt.toPlainText()))
        row.addWidget(cp_btn)

        sv_btn = QPushButton("💾 Uložit jako .TXT...", self)
        sv_btn.clicked.connect(self._save_txt)
        row.addWidget(sv_btn)

        close_btn = QPushButton("Zavřít", self)
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        lay.addLayout(row)

    def _save_txt(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Uložit OCR text", "rozpoznany_text.txt", "Textový soubor (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.txt.toPlainText())
