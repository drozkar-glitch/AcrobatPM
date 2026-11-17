# STAVITEL_WIN_APP: AcrobatPM
# © 2026 Created by Pavel Mareš
import ctypes
import os
import sys
from typing import List, Optional, Tuple

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QAction, QActionGroup, QIcon, QImage, QKeySequence, QPainter, QPixmap
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.canvas_view import PDFCanvasScrollArea, ToolMode
from src.dialogs import (
    EditTextDialog,
    FormFieldsDialog,
    OcrResultDialog,
    SignaturePadDialog,
    StampDialog,
    get_win11_stylesheet,
    is_windows_dark_mode,
)
from src.pdf_engine import PDFDocumentSession


def resource_path(rel_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel_path)


class DocumentTab(QWidget):
    def __init__(self, session: PDFDocumentSession, parent_win: "AcrobatPMWindow"):
        super().__init__(parent_win)
        self.win = parent_win
        self.session = session
        self.current_page: int = 0
        self.zoom: float = 1.25
        self.search_hits: List[Tuple[int, Tuple[float, float, float, float], str]] = []
        self.search_idx: int = -1

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.thumb_list = QListWidget(self.splitter)
        self.thumb_list.setIconSize(QSize(104, 144))
        self.thumb_list.setMinimumWidth(148)
        self.thumb_list.setMaximumWidth(210)
        self.thumb_list.setSpacing(6)
        self.thumb_list.currentRowChanged.connect(self._on_thumb_selected)
        self.thumb_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.thumb_list.customContextMenuRequested.connect(self._show_thumb_menu)

        self.canvas = PDFCanvasScrollArea(self.splitter)
        self.canvas.rectToolTriggered.connect(self.win.on_canvas_rect_tool)
        self.canvas.pointToolTriggered.connect(self.win.on_canvas_point_tool)
        self.canvas.inkToolTriggered.connect(self.win.on_canvas_ink_tool)
        self.canvas.zoomRequest.connect(self.win.step_zoom)
        self.canvas.pageStepRequest.connect(self._step_page)
        self.canvas.filesDropped.connect(self.win.open_dropped_files)

        self.splitter.addWidget(self.thumb_list)
        self.splitter.addWidget(self.canvas)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        lay.addWidget(self.splitter)

        self.rebuild_thumbnails()
        self.render_active_page()

    def rebuild_thumbnails(self) -> None:
        self.thumb_list.blockSignals(True)
        self.thumb_list.clear()
        for i in range(self.session.page_count):
            rgba, w, h, stride = self.session.render_page_rgba(i, zoom=0.22)
            qimg = QImage(rgba, w, h, stride, QImage.Format.Format_RGBA8888).copy()
            item = QListWidgetItem(QIcon(QPixmap.fromImage(qimg)), f"Strana {i + 1}")
            self.thumb_list.addItem(item)
        self.current_page = min(max(0, self.current_page), max(0, self.session.page_count - 1))
        if self.session.page_count > 0:
            self.thumb_list.setCurrentRow(self.current_page)
        self.thumb_list.blockSignals(False)

    def refresh_single_thumbnail(self, idx: int) -> None:
        if 0 <= idx < self.thumb_list.count():
            rgba, w, h, stride = self.session.render_page_rgba(idx, zoom=0.22)
            qimg = QImage(rgba, w, h, stride, QImage.Format.Format_RGBA8888).copy()
            self.thumb_list.item(idx).setIcon(QIcon(QPixmap.fromImage(qimg)))

    def render_active_page(self) -> None:
        if self.session.page_count == 0:
            self.canvas.surface.clear_surface()
            return
        self.current_page = min(max(0, self.current_page), self.session.page_count - 1)
        dpr = max(1.0, self.devicePixelRatioF())
        rgba, w, h, stride = self.session.render_page_rgba(self.current_page, zoom=self.zoom * dpr)
        self.canvas.surface.set_rendered_page(rgba, w, h, stride, self.zoom, dpr)
        self.canvas.set_tool_mode(self.win.active_tool)
        self.win.update_status_and_titles()

    def go_to_page(self, idx: int, highlight_rect: Optional[Tuple[float, float, float, float]] = None) -> None:
        if 0 <= idx < self.session.page_count:
            self.current_page = idx
            self.thumb_list.blockSignals(True)
            self.thumb_list.setCurrentRow(idx)
            self.thumb_list.blockSignals(False)
            self.render_active_page()
            self.canvas.set_search_highlight(highlight_rect)

    def _on_thumb_selected(self, row: int) -> None:
        if 0 <= row < self.session.page_count and row != self.current_page:
            self.current_page = row
            self.canvas.set_search_highlight(None)
            self.render_active_page()

    def _step_page(self, delta: int) -> None:
        target = self.current_page + delta
        if 0 <= target < self.session.page_count:
            self.go_to_page(target)
            vbar = self.canvas.verticalScrollBar()
            vbar.setValue(vbar.minimum() if delta > 0 else vbar.maximum())

    def _show_thumb_menu(self, pos) -> None:
        item = self.thumb_list.itemAt(pos)
        if not item:
            return
        idx = self.thumb_list.row(item)
        self.go_to_page(idx)
        menu = QMenu(self)
        menu.addAction("🔃 Otočit doprava (+90°)", lambda: self.win.rotate_current(90))
        menu.addAction("🔄 Otočit doleva (-90°)", lambda: self.win.rotate_current(-90))
        menu.addSeparator()
        menu.addAction("⬆️ Posunout stranu výš", lambda: self.win.move_current_page(-1))
        menu.addAction("⬇️ Posunout stranu níž", lambda: self.win.move_current_page(1))
        menu.addAction("➕ Vložit prázdnou stranu za tuto", self.win.insert_blank_after_current)
        menu.addSeparator()
        menu.addAction("✂️ Uložit tuto stranu zvlášť...", self.win.extract_pages_dialog)
        menu.addAction("🗑️ Smazat tuto stranu", self.win.delete_current_page)
        menu.exec(self.thumb_list.mapToGlobal(pos))


class AcrobatPMWindow(QMainWindow):
    def __init__(self, initial_files: Optional[List[str]] = None):
        super().__init__()
        self.setWindowTitle("AcrobatPM – Profesionální PDF Editor pro Windows 11")
        self.resize(1360, 880)
        self.setAcceptDrops(True)

        ico_file = resource_path(os.path.join("assets", "app.ico"))
        if os.path.isfile(ico_file):
            self.setWindowIcon(QIcon(ico_file))

        self.dark_mode: bool = is_windows_dark_mode()
        self.active_tool: str = ToolMode.VIEW
        self._pending_image_bytes: Optional[bytes] = None
        self._pending_stamp: Tuple[str, Tuple[float, float, float]] = ("SCHVÁLENO", (0.82, 0.12, 0.12))

        self._build_menus()
        self._build_toolbars()
        self._build_central_tabs()
        self._build_statusbar()
        self.apply_theme()

        opened = False
        for p in initial_files or []:
            if os.path.isfile(p):
                self.open_file_path(p)
                opened = True
        if not opened:
            self.create_new_blank_tab()

    def apply_theme(self) -> None:
        QApplication.instance().setStyleSheet(get_win11_stylesheet(self.dark_mode))

    def toggle_theme(self) -> None:
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    def current_tab(self) -> Optional[DocumentTab]:
        w = self.tabs.currentWidget()
        return w if isinstance(w, DocumentTab) else None

    def _build_menus(self) -> None:
        mb = self.menuBar()

        m_file = mb.addMenu("&Soubor")
        act_new = QAction("📄 Nový prázdný PDF", self, shortcut=QKeySequence.StandardKey.New, triggered=self.create_new_blank_tab)
        act_open = QAction("📂 Otevřít PDF...", self, shortcut=QKeySequence.StandardKey.Open, triggered=self.open_pdf_dialog)
        act_save = QAction("💾 Uložit", self, shortcut=QKeySequence.StandardKey.Save, triggered=self.save_current)
        act_save_as = QAction("💾 Uložit jako...", self, shortcut=QKeySequence("Ctrl+Shift+S"), triggered=self.save_current_as)
        act_print = QAction("🖨️ Tisk...", self, shortcut=QKeySequence.StandardKey.Print, triggered=self.print_current)
        act_img2pdf = QAction("🖼️ Vytvořit PDF z obrázků...", self, triggered=self.images_to_pdf_dialog)
        act_pdf2img = QAction("📤 Exportovat stránky do PNG / JPG...", self, triggered=self.export_images_dialog)
        act_exit = QAction("✖ Ukončit", self, shortcut=QKeySequence("Alt+F4"), triggered=self.close)
        m_file.addActions([act_new, act_open, act_save, act_save_as])
        m_file.addSeparator()
        m_file.addActions([act_img2pdf, act_pdf2img, act_print])
        m_file.addSeparator()
        m_file.addAction(act_exit)

        m_edit = mb.addMenu("&Úpravy")
        m_edit.addAction(QAction("↩ Zpět", self, shortcut=QKeySequence.StandardKey.Undo, triggered=self.undo_current))
        m_edit.addAction(QAction("↪ Vpřed", self, shortcut=QKeySequence.StandardKey.Redo, triggered=self.redo_current))
        m_edit.addSeparator()
        m_edit.addAction(QAction("🔍 Najít v dokumentu", self, shortcut=QKeySequence.StandardKey.Find, triggered=lambda: self.search_input.setFocus()))

        m_pages = mb.addMenu("S&tránky")
        m_pages.addAction("🔗 Připojit další PDF soubory...", self.merge_pdfs_dialog)
        m_pages.addAction("✂️ Extrahovat vybrané stránky...", self.extract_pages_dialog)
        m_pages.addAction("📑 Rozdělit dokument po 1 straně do složky...", self.split_all_pages_dialog)
        m_pages.addSeparator()
        m_pages.addAction("➕ Vložit prázdnou stranu", self.insert_blank_after_current)
        m_pages.addAction(QAction("🗑️ Smazat aktuální stranu", self, shortcut=QKeySequence("Ctrl+Delete"), triggered=self.delete_current_page))

        m_sec = mb.addMenu("&Nástroje a zabezpečení")
        m_sec.addAction("📝 Vyplnit formulářová pole na straně...", self.fill_forms_dialog)
        m_sec.addAction("💧 Přidat vodoznak na všechny strany...", self.watermark_dialog)
        m_sec.addAction("🔢 Očíslovat všechny stránky", self.number_pages_action)
        m_sec.addSeparator()
        m_sec.addAction("🗜️ Zkomprimovat velikost PDF...", self.compress_pdf_dialog)
        m_sec.addAction("🔐 Zaheslovat PDF (AES-256)...", self.protect_pdf_dialog)
        m_sec.addAction("🔓 Uložit odemčenou kopii bez hesla...", self.unlock_pdf_dialog)
        m_sec.addSeparator()
        m_sec.addAction("🔎 Přečíst text ze skenu (OCR)...", self.ocr_current_page)

    def _build_toolbars(self) -> None:
        tb1 = QToolBar("Hlavní nástroje", self)
        tb1.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb1)

        tb1.addAction("📂 Otevřít", self.open_pdf_dialog)
        tb1.addAction("💾 Uložit", self.save_current)
        tb1.addAction("🖨️ Tisk", self.print_current)
        tb1.addSeparator()
        tb1.addAction("↩ Zpět", self.undo_current)
        tb1.addAction("↪ Vpřed", self.redo_current)
        tb1.addSeparator()

        tb1.addAction("➖", lambda: self.step_zoom(1 / 1.15))
        self.zoom_btn = QPushButton("125%", self)
        self.zoom_btn.setToolTip("Kliknutím vrátíš měřítko na 100 %")
        self.zoom_btn.clicked.connect(lambda: self.set_exact_zoom(1.0))
        tb1.addWidget(self.zoom_btn)
        tb1.addAction("➕", lambda: self.step_zoom(1.15))
        tb1.addAction("↔ Šířka", self.fit_page_width)
        tb1.addSeparator()

        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        tool_defs = [
            ("🖐 Posun", ToolMode.VIEW, "Posouvání stránky myší"),
            ("✏️ Přepsat text", ToolMode.EDIT_TEXT, "Klikni nebo označ řádek v PDF pro přepsání"),
            ("🔤 Vložit text", ToolMode.ADD_TEXT, "Klikni kamkoliv na stránku pro vepsání nového textu"),
            ("🖍 Zvýraznit", ToolMode.HIGHLIGHT, "Tažením myši zvýrazníš text"),
            ("🖊 Podtrhnout", ToolMode.UNDERLINE, "Tažením myši podtrhneš text"),
            ("❌ Přeškrtnout", ToolMode.STRIKEOUT, "Tažením myši přeškrtneš text"),
            ("✍️ Kreslit", ToolMode.INK, "Volné kreslení perem do stránky"),
            ("✒️ Podpis", ToolMode.SIGN, "Nakresli nebo vlož průhledný podpis a umísti ho na stránku"),
            ("🖼 Obrázek", ToolMode.IMAGE, "Vyber obrázek z disku a tažením ho vlož do PDF"),
            ("🔖 Razítko", ToolMode.STAMP, "Vyber razítko a kliknutím ho otiskni do stránky"),
            ("⬛ Začernit", ToolMode.REDACT, "Trvale a nevratně odstraní citlivý text pod černým polem"),
        ]
        self.tool_actions = {}
        for label, mode_id, tip in tool_defs:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setToolTip(tip)
            if mode_id == ToolMode.VIEW:
                act.setChecked(True)
            act.triggered.connect(lambda _, m=mode_id: self.activate_tool(m))
            self.tool_group.addAction(act)
            tb1.addAction(act)
            self.tool_actions[mode_id] = act

        tb1.addSeparator()
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("🔍 Hledat v PDF...")
        self.search_input.setFixedWidth(165)
        self.search_input.returnPressed.connect(self.find_next)
        tb1.addWidget(self.search_input)
        tb1.addAction("Další", self.find_next)
        tb1.addAction("🌓", self.toggle_theme)

        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        tb2 = QToolBar("Stránky a konverze", self)
        tb2.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb2)

        tb2.addAction("🔄 Doleva", lambda: self.rotate_current(-90))
        tb2.addAction("🔃 Doprava", lambda: self.rotate_current(90))
        tb2.addAction("⬆️ Výš", lambda: self.move_current_page(-1))
        tb2.addAction("⬇️ Níž", lambda: self.move_current_page(1))
        tb2.addAction("➕ Strana", self.insert_blank_after_current)
        tb2.addAction("🗑️ Smazat str.", self.delete_current_page)
        tb2.addSeparator()
        tb2.addAction("🔗 Spojit PDF", self.merge_pdfs_dialog)
        tb2.addAction("✂️ Extrahovat", self.extract_pages_dialog)
        tb2.addAction("📑 Rozdělit", self.split_all_pages_dialog)
        tb2.addSeparator()
        tb2.addAction("📝 Formulář", self.fill_forms_dialog)
        tb2.addAction("💧 Vodoznak", self.watermark_dialog)
        tb2.addAction("🔢 Číslovat", self.number_pages_action)
        tb2.addAction("🗜️ Komprese", self.compress_pdf_dialog)
        tb2.addAction("🔐 Heslo", self.protect_pdf_dialog)
        tb2.addAction("🖼️ Z obrázků", self.images_to_pdf_dialog)
        tb2.addAction("📤 Do PNG/JPG", self.export_images_dialog)
        tb2.addAction("🔎 OCR", self.ocr_current_page)

    def _build_central_tabs(self) -> None:
        self.tabs = QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab_index)
        self.tabs.currentChanged.connect(lambda _: self.update_status_and_titles())
        self.setCentralWidget(self.tabs)

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self.hint_label = QLabel("Připraveno • Přetáhni sem PDF soubor nebo klikni na Otevřít", self)
        self.page_label = QLabel("Strana 1 / 1", self)
        self.copy_label = QLabel("© 2026 Created by Pavel Mareš", self)
        sb.addWidget(self.hint_label, 1)
        sb.addPermanentWidget(self.page_label)
        sb.addPermanentWidget(QLabel("  •  ", self))
        sb.addPermanentWidget(self.copy_label)

    # --- OTEVÍRÁNÍ, UKLÁDÁNÍ A TISK ---

    def create_new_blank_tab(self) -> None:
        sess = PDFDocumentSession()
        tab = DocumentTab(sess, self)
        idx = self.tabs.addTab(tab, sess.display_name)
        self.tabs.setCurrentIndex(idx)
        self.update_status_and_titles()

    def open_pdf_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Otevřít PDF dokumenty", "", "PDF dokumenty (*.pdf)")
        for p in paths:
            self.open_file_path(p)

    def open_dropped_files(self, paths: List[str]) -> None:
        imgs = [p for p in paths if p.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))]
        pdfs = [p for p in paths if p.lower().endswith(".pdf")]
        for p in pdfs:
            self.open_file_path(p)
        if imgs:
            sess = PDFDocumentSession.create_from_images(imgs)
            tab = DocumentTab(sess, self)
            self.tabs.setCurrentIndex(self.tabs.addTab(tab, "Z obrázků.pdf"))

    def open_file_path(self, path: str) -> None:
        try:
            sess = PDFDocumentSession(file_path=path)
            if sess.needs_password:
                pw, ok = QInputDialog.getText(self, "Zaheslované PDF", f"Zadej heslo pro otevření „{os.path.basename(path)}“:", QLineEdit.EchoMode.Password)
                if not ok or not sess.unlock(pw):
                    QMessageBox.warning(self, "Přístup odepřen", "Nesprávné heslo k PDF souboru.")
                    sess.close()
                    return
            tab = DocumentTab(sess, self)
            idx = self.tabs.addTab(tab, sess.display_name)
            self.tabs.setCurrentIndex(idx)
            self.update_status_and_titles()
        except Exception as exc:
            QMessageBox.critical(self, "Chyba otevření", f"Soubor nelze otevřít:\n{exc}")

    def save_current(self) -> bool:
        tab = self.current_tab()
        if not tab:
            return False
        if not tab.session.file_path:
            return self.save_current_as()
        try:
            tab.session.save()
            self.update_status_and_titles()
            self.hint_label.setText(f"✔ Uloženo: {tab.session.file_path}")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Chyba uložení", f"Nelze přepsat soubor (zkus Uložit jako):\n{exc}")
            return False

    def save_current_as(self) -> bool:
        tab = self.current_tab()
        if not tab:
            return False
        suggested = tab.session.file_path or "upraveny_dokument.pdf"
        out, _ = QFileDialog.getSaveFileName(self, "Uložit PDF jako", suggested, "PDF dokument (*.pdf)")
        if not out:
            return False
        try:
            tab.session.save(out)
            self.update_status_and_titles()
            self.hint_label.setText(f"✔ Uloženo do: {out}")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Chyba uložení", str(exc))
            return False

    def print_current(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        painter = QPainter(printer)
        for i in range(tab.session.page_count):
            if i > 0:
                printer.newPage()
            rgba, w, h, stride = tab.session.render_page_rgba(i, zoom=3.0)
            qimg = QImage(rgba, w, h, stride, QImage.Format.Format_RGBA8888)
            rect = painter.viewport()
            scaled = qimg.size().scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
            painter.setViewport(rect.x(), rect.y(), scaled.width(), scaled.height())
            painter.setWindow(qimg.rect())
            painter.drawImage(0, 0, qimg)
        painter.end()

    def close_tab_index(self, idx: int) -> bool:
        w = self.tabs.widget(idx)
        if isinstance(w, DocumentTab) and w.session.modified:
            ans = QMessageBox.question(
                self,
                "Neuložené změny",
                f"Dokument „{w.session.display_name}“ obsahuje neuložené úpravy. Uložit před zavřením?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            )
            if ans == QMessageBox.StandardButton.Cancel:
                return False
            if ans == QMessageBox.StandardButton.Yes:
                self.tabs.setCurrentIndex(idx)
                if not self.save_current():
                    return False
        if isinstance(w, DocumentTab):
            w.session.close()
        self.tabs.removeTab(idx)
        if self.tabs.count() == 0:
            self.create_new_blank_tab()
        return True

    def closeEvent(self, event) -> None:
        while self.tabs.count() > 0:
            w = self.tabs.widget(0)
            if isinstance(w, DocumentTab) and not w.session.modified and self.tabs.count() == 1:
                w.session.close()
                break
            if not self.close_tab_index(0):
                event.ignore()
                return
        event.accept()

    # --- NÁSTROJE PLÁTNA A INTERAKCE ---

    def activate_tool(self, mode: str) -> None:
        if mode == ToolMode.SIGN:
            dlg = SignaturePadDialog(self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self.tool_actions[ToolMode.VIEW].setChecked(True)
                mode = ToolMode.VIEW
            else:
                self._pending_image_bytes = dlg.get_png_bytes()
                if not self._pending_image_bytes:
                    self.tool_actions[ToolMode.VIEW].setChecked(True)
                    mode = ToolMode.VIEW
        elif mode == ToolMode.IMAGE:
            path, _ = QFileDialog.getOpenFileName(self, "Vyber obrázek pro vložení", "", "Obrázky (*.png *.jpg *.jpeg *.webp *.bmp)")
            if not path:
                self.tool_actions[ToolMode.VIEW].setChecked(True)
                mode = ToolMode.VIEW
            else:
                with open(path, "rb") as f:
                    self._pending_image_bytes = f.read()
        elif mode == ToolMode.STAMP:
            dlg = StampDialog(self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self.tool_actions[ToolMode.VIEW].setChecked(True)
                mode = ToolMode.VIEW
            else:
                self._pending_stamp = dlg.get_stamp()

        self.active_tool = mode
        tab = self.current_tab()
        if tab:
            tab.canvas.set_tool_mode(mode)
        hints = {
            ToolMode.VIEW: "Režim prohlížení • Posouvej stránku myší, Ctrl + kolečko mění zoom",
            ToolMode.EDIT_TEXT: "Přepsání textu • Klikni na řádek nebo označ obdélník kolem textu, který chceš přepsat",
            ToolMode.ADD_TEXT: "Vložení textu • Klikni na místo na stránce, kam chceš dopsat nový text",
            ToolMode.SIGN: "Podpis připraven • Klikni nebo tažením vyznač obdélník pro umístění podpisu",
            ToolMode.IMAGE: "Obrázek připraven • Tažením myši vyznač oblast pro vložení obrázku",
            ToolMode.STAMP: f"Razítko „{self._pending_stamp[0]}“ • Klikni do stránky pro otištění",
            ToolMode.REDACT: "Trvalé začernění • Označ oblast, ze které se nenávratně vymažou citlivá data",
        }
        self.hint_label.setText(hints.get(mode, "Aktivní anotační nástroj • Tažením myši označ oblast na stránce"))

    def on_canvas_rect_tool(self, mode: str, rect_pdf: Tuple[float, float, float, float]) -> None:
        tab = self.current_tab()
        if not tab:
            return
        pg = tab.current_page
        if mode == ToolMode.EDIT_TEXT:
            info = tab.session.inspect_text_in_rect(pg, rect_pdf)
            target_rect = info.rect if (info and (rect_pdf[2] - rect_pdf[0]) < 8) else (info.rect if info else rect_pdf)
            dlg = EditTextDialog(self, info=info, is_replace=True)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                txt, sz, col, bold, white_bg = dlg.get_result()
                tab.session.replace_text_in_rect(pg, target_rect, txt, fontsize=sz, color_rgb=col, bold=bold, bg_override=(1.0, 1.0, 1.0) if white_bg else None)
        elif mode in (ToolMode.HIGHLIGHT, ToolMode.UNDERLINE, ToolMode.STRIKEOUT):
            col = (1.0, 0.92, 0.23) if mode == ToolMode.HIGHLIGHT else ((0.12, 0.45, 0.88) if mode == ToolMode.UNDERLINE else (0.86, 0.15, 0.15))
            tab.session.add_markup_in_rect(pg, rect_pdf, mode=mode, color_rgb=col)
        elif mode == ToolMode.REDACT:
            tab.session.redact_permanent(pg, rect_pdf)
        elif mode in (ToolMode.SIGN, ToolMode.IMAGE) and self._pending_image_bytes:
            tab.session.insert_image_bytes(pg, rect_pdf, self._pending_image_bytes)
            self.tool_actions[ToolMode.VIEW].setChecked(True)
            self.activate_tool(ToolMode.VIEW)
        else:
            return

        tab.refresh_single_thumbnail(pg)
        tab.render_active_page()

    def on_canvas_point_tool(self, mode: str, px: float, py: float) -> None:
        tab = self.current_tab()
        if not tab:
            return
        pg = tab.current_page
        if mode == ToolMode.ADD_TEXT:
            dlg = EditTextDialog(self, info=None, is_replace=False)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                txt, sz, col, bold, white_bg = dlg.get_result()
                tab.session.add_free_text(pg, px, py, txt, fontsize=sz, color_rgb=col, bold=bold, fill_bg=(1.0, 1.0, 1.0) if white_bg else None)
        elif mode == ToolMode.STAMP:
            lbl, col = self._pending_stamp
            tab.session.add_stamp_badge(pg, px, py, lbl, color_rgb=col)
            self.tool_actions[ToolMode.VIEW].setChecked(True)
            self.activate_tool(ToolMode.VIEW)
        tab.refresh_single_thumbnail(pg)
        tab.render_active_page()

    def on_canvas_ink_tool(self, points: List[Tuple[float, float]]) -> None:
        tab = self.current_tab()
        if not tab:
            return
        tab.session.add_ink_stroke(tab.current_page, points)
        tab.refresh_single_thumbnail(tab.current_page)
        tab.render_active_page()

    # --- ZOOM, ZPĚT/VPŘED, HLEDÁNÍ A OPERACE SE STRÁNKAMI ---

    def step_zoom(self, factor: float) -> None:
        tab = self.current_tab()
        if tab:
            self.set_exact_zoom(max(0.35, min(4.0, tab.zoom * factor)))

    def set_exact_zoom(self, z: float) -> None:
        tab = self.current_tab()
        if tab:
            tab.zoom = z
            self.zoom_btn.setText(f"{int(round(z * 100))}%")
            tab.render_active_page()

    def fit_page_width(self) -> None:
        tab = self.current_tab()
        if tab and tab.session.page_count > 0:
            pw, _ = tab.session.get_page_size(tab.current_page)
            avail = max(300, tab.canvas.viewport().width() - 56)
            self.set_exact_zoom(max(0.4, min(3.5, avail / max(1.0, pw))))

    def undo_current(self) -> None:
        tab = self.current_tab()
        if tab and tab.session.undo():
            tab.rebuild_thumbnails()
            tab.render_active_page()

    def redo_current(self) -> None:
        tab = self.current_tab()
        if tab and tab.session.redo():
            tab.rebuild_thumbnails()
            tab.render_active_page()

    def find_next(self) -> None:
        tab = self.current_tab()
        q = self.search_input.text().strip()
        if not tab or not q:
            return
        hits = tab.session.search_document(q)
        if not hits:
            self.hint_label.setText(f"Výraz „{q}“ nebyl v dokumentu nalezen.")
            tab.canvas.set_search_highlight(None)
            return
        if tab.search_hits != hits:
            tab.search_hits = hits
            tab.search_idx = 0
        else:
            tab.search_idx = (tab.search_idx + 1) % len(hits)
        pg, rect, _ = tab.search_hits[tab.search_idx]
        tab.go_to_page(pg, highlight_rect=rect)
        self.hint_label.setText(f"🔍 Nalezen výskyt {tab.search_idx + 1} z {len(hits)}")

    def rotate_current(self, deg: int) -> None:
        tab = self.current_tab()
        if tab:
            tab.session.rotate_page(tab.current_page, deg)
            tab.refresh_single_thumbnail(tab.current_page)
            tab.render_active_page()

    def move_current_page(self, delta: int) -> None:
        tab = self.current_tab()
        if not tab:
            return
        dst = tab.current_page + delta
        if 0 <= dst < tab.session.page_count:
            tab.session.move_page(tab.current_page, dst)
            tab.current_page = dst
            tab.rebuild_thumbnails()
            tab.render_active_page()

    def insert_blank_after_current(self) -> None:
        tab = self.current_tab()
        if tab:
            tab.current_page = tab.session.insert_blank_page(tab.current_page)
            tab.rebuild_thumbnails()
            tab.render_active_page()

    def delete_current_page(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        try:
            tab.session.delete_pages([tab.current_page])
            tab.rebuild_thumbnails()
            tab.render_active_page()
        except ValueError as exc:
            QMessageBox.warning(self, "Smazání strany", str(exc))

    def merge_pdfs_dialog(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Vyber PDF soubory pro připojení na konec dokumentu", "", "PDF (*.pdf)")
        if paths:
            tab.session.append_pdf_files(paths)
            tab.rebuild_thumbnails()
            tab.render_active_page()

    def extract_pages_dialog(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        total = tab.session.page_count
        raw, ok = QInputDialog.getText(self, "Extrahovat stránky", f"Zadej čísla stran (1–{total}), např. 1, 3-5:", text=str(tab.current_page + 1))
        if not ok or not raw.strip():
            return
        indices: List[int] = []
        for part in raw.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-", 1)
                if a.strip().isdigit() and b.strip().isdigit():
                    for n in range(int(a), int(b) + 1):
                        if 1 <= n <= total:
                            indices.append(n - 1)
            elif part.isdigit() and 1 <= int(part) <= total:
                indices.append(int(part) - 1)
        if not indices:
            return
        out, _ = QFileDialog.getSaveFileName(self, "Uložit vybrané stránky jako", "vybrane_strany.pdf", "PDF (*.pdf)")
        if out:
            tab.session.extract_pages_to_file(indices, out)
            self.hint_label.setText(f"✔ Extrahováno {len(indices)} stran do {out}")

    def split_all_pages_dialog(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        folder = QFileDialog.getExistingDirectory(self, "Vyber složku pro uložení jednotlivých stran")
        if folder:
            cnt = tab.session.split_all_pages_to_folder(folder)
            QMessageBox.information(self, "Hotovo", f"Dokument byl rozdělen na {cnt} samostatných PDF souborů.")

    def fill_forms_dialog(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        fields = tab.session.get_page_form_fields(tab.current_page)
        if not fields:
            QMessageBox.information(self, "Formulář", "Na této stránce nejsou žádná interaktivní formulářová pole (použij nástroj 🔤 Vložit text).")
            return
        dlg = FormFieldsDialog(fields, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            tab.session.update_form_fields(tab.current_page, dlg.get_updated_values())
            tab.refresh_single_thumbnail(tab.current_page)
            tab.render_active_page()

    def watermark_dialog(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        txt, ok = QInputDialog.getText(self, "Vodoznak", "Text vodoznaku přes všechny stránky:", text="DŮVĚRNÉ")
        if ok and txt.strip():
            tab.session.add_watermark_all_pages(txt.strip())
            tab.rebuild_thumbnails()
            tab.render_active_page()

    def number_pages_action(self) -> None:
        tab = self.current_tab()
        if tab:
            tab.session.add_page_numbers()
            tab.rebuild_thumbnails()
            tab.render_active_page()

    def compress_pdf_dialog(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        out, _ = QFileDialog.getSaveFileName(self, "Uložit zkomprimované PDF", "zkomprimovano.pdf", "PDF (*.pdf)")
        if out:
            before, after = tab.session.save_compressed(out)
            pct = max(0, round((1 - after / max(1, before)) * 100))
            QMessageBox.information(self, "Komprese dokončena", f"Původní velikost: {before // 1024} KB\nNová velikost: {after // 1024} KB (úspora {pct} %)")

    def protect_pdf_dialog(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        pw, ok = QInputDialog.getText(self, "Zaheslovat PDF (AES-256)", "Zadej heslo pro otevření souboru:", QLineEdit.EchoMode.Password)
        if not ok or not pw:
            return
        out, _ = QFileDialog.getSaveFileName(self, "Uložit zaheslované PDF", "chrany_dokument.pdf", "PDF (*.pdf)")
        if out:
            tab.session.save_with_password(out, pw)
            QMessageBox.information(self, "Zabezpečeno", f"Zaheslované PDF bylo uloženo do:\n{out}")

    def unlock_pdf_dialog(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        out, _ = QFileDialog.getSaveFileName(self, "Uložit odemčené PDF bez hesla", "odemceny_dokument.pdf", "PDF (*.pdf)")
        if out:
            tab.session.save_unlocked(out)
            QMessageBox.information(self, "Odemčeno", f"Kopie bez hesla uložena do:\n{out}")

    def images_to_pdf_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Vyber obrázky pro složení do PDF", "", "Obrázky (*.png *.jpg *.jpeg *.webp *.bmp)")
        if paths:
            self.open_dropped_files(paths)

    def export_images_dialog(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        folder = QFileDialog.getExistingDirectory(self, "Vyber složku pro export stránek do PNG")
        if folder:
            cnt = tab.session.export_images(folder, fmt="png", dpi=200)
            QMessageBox.information(self, "Export dokončen", f"Uloženo {cnt} stránek ve vysokém rozlišení PNG.")

    def ocr_current_page(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        try:
            txt = tab.session.run_ocr_page(tab.current_page)
            OcrResultDialog(txt, tab.current_page + 1, self).exec()
        except Exception as exc:
            QMessageBox.warning(self, "OCR čtení skenu", str(exc))

    def update_status_and_titles(self) -> None:
        tab = self.current_tab()
        if not tab:
            return
        idx = self.tabs.indexOf(tab)
        if idx >= 0:
            self.tabs.setTabText(idx, tab.session.display_name)
        self.page_label.setText(f"Strana {tab.current_page + 1} / {tab.session.page_count}")
        self.zoom_btn.setText(f"{int(round(tab.zoom * 100))}%")

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.open_dropped_files(paths)


def main() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("cz.mares.acrobatpm")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("AcrobatPM")
    win = AcrobatPMWindow(initial_files=sys.argv[1:])
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
