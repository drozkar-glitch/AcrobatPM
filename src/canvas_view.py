# © 2026 Created by Pavel Mareš
from typing import List, Optional, Tuple
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPixmap, QWheelEvent
from PyQt6.QtWidgets import QScrollArea, QWidget


class ToolMode:
    VIEW = "view"
    EDIT_TEXT = "edit_text"
    ADD_TEXT = "add_text"
    HIGHLIGHT = "highlight"
    UNDERLINE = "underline"
    STRIKEOUT = "strikeout"
    INK = "ink"
    REDACT = "redact"
    SIGN = "sign"
    IMAGE = "image"
    STAMP = "stamp"


class _PageSurface(QWidget):
    def __init__(self, parent_scroll: "PDFCanvasScrollArea"):
        super().__init__(parent_scroll)
        self.scroll = parent_scroll
        self.pixmap_item: Optional[QPixmap] = None
        self.dpr: float = 1.0
        self.zoom: float = 1.25
        self.tool_mode: str = ToolMode.VIEW
        self.search_rect_pdf: Optional[Tuple[float, float, float, float]] = None

        self._dragging_rect: bool = False
        self._panning: bool = False
        self._pan_start = QPointF()
        self._drag_start = QPointF()
        self._drag_current = QPointF()
        self._ink_points_px: List[QPointF] = []
        self.ink_preview_color = QColor("#dc2626")

        self.setMouseTracking(True)

    def set_rendered_page(self, rgba_bytes: bytes, w: int, h: int, stride: int, zoom: float, dpr: float) -> None:
        self.zoom = zoom
        self.dpr = max(1.0, dpr)
        qimg = QImage(rgba_bytes, w, h, stride, QImage.Format.Format_RGBA8888).copy()
        pix = QPixmap.fromImage(qimg)
        pix.setDevicePixelRatio(self.dpr)
        self.pixmap_item = pix
        logical_w = int(round(w / self.dpr)) + 36
        logical_h = int(round(h / self.dpr)) + 36
        self.setFixedSize(max(200, logical_w), max(200, logical_h))
        self.update()

    def clear_surface(self) -> None:
        self.pixmap_item = None
        self.search_rect_pdf = None
        self.setFixedSize(400, 300)
        self.update()

    def _page_origin(self) -> Tuple[float, float]:
        if not self.pixmap_item:
            return (18.0, 18.0)
        pw = self.pixmap_item.width() / self.dpr
        ph = self.pixmap_item.height() / self.dpr
        ox = max(18.0, (self.width() - pw) / 2.0)
        oy = max(18.0, (self.height() - ph) / 2.0)
        return (ox, oy)

    def widget_to_pdf(self, pt: QPointF) -> Tuple[float, float]:
        ox, oy = self._page_origin()
        return ((pt.x() - ox) / self.zoom, (pt.y() - oy) / self.zoom)

    def pdf_rect_to_widget(self, r: Tuple[float, float, float, float]) -> QRectF:
        ox, oy = self._page_origin()
        x0, y0, x1, y1 = r
        return QRectF(ox + x0 * self.zoom, oy + y0 * self.zoom, (x1 - x0) * self.zoom, (y1 - y0) * self.zoom)

    def set_tool_mode(self, mode: str) -> None:
        self.tool_mode = mode
        if mode == ToolMode.VIEW:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif mode in (ToolMode.EDIT_TEXT, ToolMode.ADD_TEXT):
            self.setCursor(Qt.CursorShape.IBeamCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        if not self.pixmap_item:
            return

        ox, oy = self._page_origin()
        pw = self.pixmap_item.width() / self.dpr
        ph = self.pixmap_item.height() / self.dpr

        painter.fillRect(QRectF(ox + 4, oy + 6, pw, ph), QColor(0, 0, 0, 75))
        painter.drawPixmap(int(round(ox)), int(round(oy)), self.pixmap_item)
        painter.setPen(QPen(QColor(148, 163, 184, 110), 1.0))
        painter.drawRect(QRectF(ox, oy, pw, ph))

        if self.search_rect_pdf:
            sr = self.pdf_rect_to_widget(self.search_rect_pdf)
            painter.fillRect(sr.adjusted(-2, -2, 2, 2), QColor(250, 204, 21, 115))
            painter.setPen(QPen(QColor(217, 119, 6), 2.0))
            painter.drawRoundedRect(sr.adjusted(-2, -2, 2, 2), 4, 4)

        if self._dragging_rect:
            sel_rect = QRectF(self._drag_start, self._drag_current).normalized()
            col = QColor("#ef4444") if self.tool_mode == ToolMode.REDACT else QColor("#0284c7")
            fill = QColor(col.red(), col.green(), col.blue(), 48)
            painter.fillRect(sel_rect, fill)
            pen = QPen(col, 1.8, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(sel_rect)

        if len(self._ink_points_px) >= 2:
            pen = QPen(self.ink_preview_color, max(2.0, 2.2 * self.zoom), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            for i in range(1, len(self._ink_points_px)):
                painter.drawLine(self._ink_points_px[i - 1], self._ink_points_px[i])

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.pixmap_item:
            return
        pos = event.position()

        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self.tool_mode == ToolMode.VIEW
        ):
            self._panning = True
            self._pan_start = event.globalPosition()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self.tool_mode in (ToolMode.ADD_TEXT, ToolMode.STAMP):
            px, py = self.widget_to_pdf(pos)
            self.scroll.pointToolTriggered.emit(self.tool_mode, px, py)
            return

        if self.tool_mode == ToolMode.INK:
            self._ink_points_px = [pos]
            self.update()
            return

        self._dragging_rect = True
        self._drag_start = pos
        self._drag_current = pos
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            delta = event.globalPosition() - self._pan_start
            self._pan_start = event.globalPosition()
            hbar = self.scroll.horizontalScrollBar()
            vbar = self.scroll.verticalScrollBar()
            hbar.setValue(hbar.value() - int(delta.x()))
            vbar.setValue(vbar.value() - int(delta.y()))
            return

        if self._ink_points_px:
            self._ink_points_px.append(event.position())
            self.update()
            return

        if self._dragging_rect:
            self._drag_current = event.position()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            self._panning = False
            self.set_tool_mode(self.tool_mode)
            return

        if self._ink_points_px and event.button() == Qt.MouseButton.LeftButton:
            pts_pdf = [self.widget_to_pdf(p) for p in self._ink_points_px]
            self._ink_points_px.clear()
            self.update()
            if len(pts_pdf) >= 2:
                self.scroll.inkToolTriggered.emit(pts_pdf)
            return

        if self._dragging_rect and event.button() == Qt.MouseButton.LeftButton:
            self._dragging_rect = False
            r_px = QRectF(self._drag_start, event.position()).normalized()
            x0, y0 = self.widget_to_pdf(r_px.topLeft())
            x1, y1 = self.widget_to_pdf(r_px.bottomRight())
            self.update()

            if abs(x1 - x0) < 4 and abs(y1 - y0) < 4:
                if self.tool_mode == ToolMode.EDIT_TEXT:
                    self.scroll.rectToolTriggered.emit(self.tool_mode, (x0 - 2, y0 - 2, x0 + 2, y0 + 2))
                elif self.tool_mode in (ToolMode.SIGN, ToolMode.IMAGE):
                    self.scroll.rectToolTriggered.emit(self.tool_mode, (x0, y0, x0 + 165, y0 + 68))
                return

            self.scroll.rectToolTriggered.emit(self.tool_mode, (x0, y0, x1, y1))


class PDFCanvasScrollArea(QScrollArea):
    rectToolTriggered = pyqtSignal(str, tuple)
    pointToolTriggered = pyqtSignal(str, float, float)
    inkToolTriggered = pyqtSignal(list)
    zoomRequest = pyqtSignal(float)
    pageStepRequest = pyqtSignal(int)
    filesDropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.surface = _PageSurface(self)
        self.setWidget(self.surface)
        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)

    def set_tool_mode(self, mode: str) -> None:
        self.surface.set_tool_mode(mode)

    def set_search_highlight(self, rect_pdf: Optional[Tuple[float, float, float, float]]) -> None:
        self.surface.search_rect_pdf = rect_pdf
        self.surface.update()
        if rect_pdf:
            wr = self.surface.pdf_rect_to_widget(rect_pdf)
            self.ensureVisible(int(wr.center().x()), int(wr.center().y()), 80, 80)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.12 if delta > 0 else (1.0 / 1.12)
            self.zoomRequest.emit(factor)
            event.accept()
            return

        vbar = self.verticalScrollBar()
        dy = event.angleDelta().y()
        if dy < 0 and vbar.value() >= vbar.maximum():
            self.pageStepRequest.emit(1)
            event.accept()
            return
        if dy > 0 and vbar.value() <= vbar.minimum():
            self.pageStepRequest.emit(-1)
            event.accept()
            return
        super().wheelEvent(event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
