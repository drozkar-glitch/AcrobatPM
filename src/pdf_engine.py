# © 2026 Created by Pavel Mareš
import io
import os
import shutil
from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from PIL import Image, ImageDraw, ImageFont


def get_unicode_font_path(bold: bool = False) -> Optional[str]:
    win_dir = os.environ.get("WINDIR", r"C:\Windows")
    fonts_dir = os.path.join(win_dir, "Fonts")
    candidates = (
        ["segoeuib.ttf", "arialbd.ttf", "calibrib.ttf", "tahomabd.ttf"]
        if bold
        else ["segoeui.ttf", "arial.ttf", "calibri.ttf", "tahoma.ttf"]
    )
    for name in candidates:
        full = os.path.join(fonts_dir, name)
        if os.path.isfile(full):
            return full
    return None


def int_srgb_to_float_rgb(c_int: int) -> Tuple[float, float, float]:
    r = ((c_int >> 16) & 0xFF) / 255.0
    g = ((c_int >> 8) & 0xFF) / 255.0
    b = (c_int & 0xFF) / 255.0
    return (r, g, b)


def float_rgb_to_hex(rgb: Tuple[float, float, float]) -> str:
    r = max(0, min(255, int(round(rgb[0] * 255))))
    g = max(0, min(255, int(round(rgb[1] * 255))))
    b = max(0, min(255, int(round(rgb[2] * 255))))
    return f"#{r:02x}{g:02x}{b:02x}"


def hex_to_float_rgb(hex_col: str) -> Tuple[float, float, float]:
    s = hex_col.strip().lstrip("#")
    if len(s) == 6:
        return (int(s[0:2], 16) / 255.0, int(s[2:4], 16) / 255.0, int(s[4:6], 16) / 255.0)
    return (0.0, 0.0, 0.0)


@dataclass
class TextLineInfo:
    rect: Tuple[float, float, float, float]
    text: str
    fontsize: float
    color_rgb: Tuple[float, float, float]
    is_bold: bool


@dataclass
class FormFieldInfo:
    xref: int
    field_name: str
    field_label: str
    field_type: int
    field_value: str
    rect: Tuple[float, float, float, float]
    choice_values: List[str]


class PDFDocumentSession:
    MAX_UNDO = 20

    def __init__(self, file_path: Optional[str] = None, raw_bytes: Optional[bytes] = None):
        self.file_path: Optional[str] = file_path
        self.modified: bool = False
        self.undo_stack: List[bytes] = []
        self.redo_stack: List[bytes] = []

        if raw_bytes is not None:
            self.doc = fitz.open(stream=raw_bytes, filetype="pdf")
        elif file_path is not None:
            self.doc = fitz.open(file_path)
        else:
            self.doc = fitz.open()
            self.doc.new_page(width=595, height=842)

    @property
    def needs_password(self) -> bool:
        return bool(self.doc.needs_pass)

    def unlock(self, password: str) -> bool:
        return bool(self.doc.authenticate(password))

    @property
    def page_count(self) -> int:
        return len(self.doc)

    @property
    def display_name(self) -> str:
        base = os.path.basename(self.file_path) if self.file_path else "Nový dokument.pdf"
        return f"● {base}" if self.modified else base

    def push_undo_snapshot(self) -> None:
        try:
            snap = self.doc.tobytes(garbage=0, deflate=True)
            self.undo_stack.append(snap)
            if len(self.undo_stack) > self.MAX_UNDO:
                self.undo_stack.pop(0)
            self.redo_stack.clear()
            self.modified = True
        except Exception:
            self.modified = True

    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        cur = self.doc.tobytes(garbage=0, deflate=True)
        self.redo_stack.append(cur)
        prev = self.undo_stack.pop()
        self.doc.close()
        self.doc = fitz.open(stream=prev, filetype="pdf")
        self.modified = True
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        cur = self.doc.tobytes(garbage=0, deflate=True)
        self.undo_stack.append(cur)
        nxt = self.redo_stack.pop()
        self.doc.close()
        self.doc = fitz.open(stream=nxt, filetype="pdf")
        self.modified = True
        return True

    def close(self) -> None:
        try:
            self.doc.close()
        except Exception:
            pass

    def render_page_rgba(self, page_index: int, zoom: float = 1.5) -> Tuple[bytes, int, int, int]:
        page = self.doc[page_index]
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=True)
        return bytes(pix.samples), pix.width, pix.height, pix.stride

    def get_page_size(self, page_index: int) -> Tuple[float, float]:
        r = self.doc[page_index].rect
        return (r.width, r.height)

    # --- VYHLEDÁVÁNÍ A ČTENÍ ŘÁDKŮ TEXTU PRO PŘÍMOU ÚPRAVU ---

    def search_document(self, query: str) -> List[Tuple[int, Tuple[float, float, float, float], str]]:
        q = query.strip()
        if not q:
            return []
        hits: List[Tuple[int, Tuple[float, float, float, float], str]] = []
        for idx in range(len(self.doc)):
            page = self.doc[idx]
            rects = page.search_for(q)
            for r in rects:
                clip = fitz.Rect(max(0, r.x0 - 30), max(0, r.y0 - 4), min(page.rect.width, r.x1 + 60), min(page.rect.height, r.y1 + 4))
                snippet = " ".join(page.get_text("text", clip=clip).split())
                hits.append((idx, (r.x0, r.y0, r.x1, r.y1), snippet or q))
        return hits

    def inspect_text_in_rect(self, page_index: int, rect_tuple: Tuple[float, float, float, float]) -> Optional[TextLineInfo]:
        page = self.doc[page_index]
        target = fitz.Rect(rect_tuple)
        if target.width < 3 and target.height < 3:
            target = fitz.Rect(target.x0 - 3, target.y0 - 3, target.x1 + 3, target.y1 + 3)

        d = page.get_text("dict")
        matched_lines: List[TextLineInfo] = []

        for block in d.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                lrect = fitz.Rect(line["bbox"])
                if not lrect.intersects(target):
                    continue
                spans = line.get("spans", [])
                if not spans:
                    continue
                full_txt = "".join(s.get("text", "") for s in spans).strip()
                if not full_txt:
                    continue
                first = spans[0]
                fsize = float(first.get("size", 11.0))
                col = int_srgb_to_float_rgb(int(first.get("color", 0)))
                fname = str(first.get("font", "")).lower()
                bold = ("bold" in fname) or bool(int(first.get("flags", 0)) & 16)
                matched_lines.append(TextLineInfo((lrect.x0, lrect.y0, lrect.x1, lrect.y1), full_txt, fsize, col, bold))

        if not matched_lines:
            return None
        if len(matched_lines) == 1:
            return matched_lines[0]

        u_rect = fitz.Rect(matched_lines[0].rect)
        texts = []
        for ml in matched_lines:
            u_rect |= fitz.Rect(ml.rect)
            texts.append(ml.text)
        base = matched_lines[0]
        return TextLineInfo((u_rect.x0, u_rect.y0, u_rect.x1, u_rect.y1), "\n".join(texts), base.fontsize, base.color_rgb, base.is_bold)

    def _sample_background_color(self, page, rect: fitz.Rect) -> Tuple[float, float, float]:
        try:
            pad = fitz.Rect(
                max(0, rect.x0 - 3),
                max(0, rect.y0 - 3),
                min(page.rect.width, rect.x1 + 3),
                min(page.rect.height, rect.y1 + 3),
            )
            pix = page.get_pixmap(clip=pad, matrix=fitz.Matrix(1, 1), alpha=False)
            if pix.width < 2 or pix.height < 2:
                return (1.0, 1.0, 1.0)
            samples = []
            for x in range(pix.width):
                samples.append(pix.pixel(x, 0))
                samples.append(pix.pixel(x, pix.height - 1))
            samples.sort(key=lambda p: p[0] + p[1] + p[2], reverse=True)
            top = samples[min(len(samples) - 1, max(0, len(samples) // 5))]
            return (top[0] / 255.0, top[1] / 255.0, top[2] / 255.0)
        except Exception:
            return (1.0, 1.0, 1.0)

    def _write_unicode_lines(
        self,
        page,
        x0: float,
        y0: float,
        max_width: float,
        text: str,
        fontsize: float,
        color_rgb: Tuple[float, float, float],
        bold: bool = False,
    ) -> None:
        fpath = get_unicode_font_path(bold=bold)
        lines = text.splitlines() or [""]
        if fpath:
            f_obj = fitz.Font(fontfile=fpath)
            font_alias = "F_CZ_B" if bold else "F_CZ_R"
            page.insert_font(fontname=font_alias, fontfile=fpath)
            eff_size = max(5.0, float(fontsize))
            if max_width > 20 and len(lines) == 1:
                w = f_obj.text_length(lines[0], fontsize=eff_size)
                avail = max(max_width, page.rect.width - x0 - 14)
                if w > avail and w > 0:
                    eff_size = max(5.5, eff_size * (avail / w))
            line_step = eff_size * 1.22
            cur_y = y0 + eff_size * 0.88
            for ln in lines:
                page.insert_text(fitz.Point(x0, cur_y), ln, fontname=font_alias, fontsize=eff_size, color=color_rgb)
                cur_y += line_step
        else:
            eff_size = max(6.0, float(fontsize))
            cur_y = y0 + eff_size * 0.88
            for ln in lines:
                page.insert_text(fitz.Point(x0, cur_y), ln, fontname="helv", fontsize=eff_size, color=color_rgb)
                cur_y += eff_size * 1.22

    def replace_text_in_rect(
        self,
        page_index: int,
        rect_tuple: Tuple[float, float, float, float],
        new_text: str,
        fontsize: float = 11.0,
        color_rgb: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        bold: bool = False,
        bg_override: Optional[Tuple[float, float, float]] = None,
    ) -> None:
        self.push_undo_snapshot()
        page = self.doc[page_index]
        r = fitz.Rect(rect_tuple)
        bg = bg_override if bg_override is not None else self._sample_background_color(page, r)

        redact_r = fitz.Rect(r.x0 - 0.8, r.y0 - 0.8, r.x1 + 1.2, r.y1 + 0.8) & page.rect
        page.add_redact_annot(redact_r, fill=bg)
        img_none = getattr(fitz, "PDF_REDACT_IMAGE_NONE", 0)
        try:
            page.apply_redactions(images=img_none, graphics=0)
        except TypeError:
            page.apply_redactions(images=img_none)

        if new_text.strip():
            self._write_unicode_lines(page, r.x0, r.y0, r.width, new_text, fontsize, color_rgb, bold=bold)

    def add_free_text(
        self,
        page_index: int,
        x: float,
        y: float,
        text: str,
        fontsize: float = 12.0,
        color_rgb: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        bold: bool = False,
        fill_bg: Optional[Tuple[float, float, float]] = None,
    ) -> None:
        if not text.strip():
            return
        self.push_undo_snapshot()
        page = self.doc[page_index]
        fpath = get_unicode_font_path(bold=bold)
        lines = text.splitlines()
        max_w = 40.0
        if fpath:
            f_obj = fitz.Font(fontfile=fpath)
            max_w = max(f_obj.text_length(ln, fontsize=fontsize) for ln in lines)
        else:
            max_w = max(len(ln) * fontsize * 0.55 for ln in lines)

        total_h = len(lines) * fontsize * 1.24 + 4
        if fill_bg is not None:
            box = fitz.Rect(x - 4, y - 3, x + max_w + 6, y + total_h) & page.rect
            page.draw_rect(box, color=None, fill=fill_bg)

        self._write_unicode_lines(page, x, y, 0, text, fontsize, color_rgb, bold=bold)

    # --- ANOTACE, PODPISY, RAZÍTKA A ZABEZPEČENÍ ---

    def add_markup_in_rect(
        self,
        page_index: int,
        rect_tuple: Tuple[float, float, float, float],
        mode: str = "highlight",
        color_rgb: Tuple[float, float, float] = (1.0, 0.92, 0.23),
    ) -> None:
        self.push_undo_snapshot()
        page = self.doc[page_index]
        r = fitz.Rect(rect_tuple) & page.rect
        words = page.get_text("words")
        word_rects = [fitz.Rect(w[:4]) for w in words if fitz.Rect(w[:4]).intersects(r)]
        targets = word_rects if word_rects else [r]

        for tr in targets:
            if mode == "underline":
                annot = page.add_underline_annot(tr)
                annot.set_colors(stroke=color_rgb)
                annot.update()
            elif mode == "strikeout":
                annot = page.add_strikeout_annot(tr)
                annot.set_colors(stroke=color_rgb)
                annot.update()
            else:
                annot = page.add_highlight_annot(tr)
                annot.set_colors(stroke=color_rgb)
                annot.update()

    def add_ink_stroke(
        self,
        page_index: int,
        points: List[Tuple[float, float]],
        color_rgb: Tuple[float, float, float] = (0.86, 0.15, 0.15),
        width: float = 2.2,
    ) -> None:
        if len(points) < 2:
            return
        self.push_undo_snapshot()
        page = self.doc[page_index]
        annot = page.add_ink_annot([points])
        annot.set_colors(stroke=color_rgb)
        annot.set_border(width=width)
        annot.update()

    def insert_image_bytes(
        self,
        page_index: int,
        rect_tuple: Tuple[float, float, float, float],
        img_bytes: bytes,
        keep_proportion: bool = True,
    ) -> None:
        self.push_undo_snapshot()
        page = self.doc[page_index]
        r = fitz.Rect(rect_tuple) & page.rect
        page.insert_image(r, stream=img_bytes, keep_proportion=keep_proportion, overlay=True)

    def add_stamp_badge(
        self,
        page_index: int,
        x: float,
        y: float,
        label: str,
        color_rgb: Tuple[float, float, float] = (0.82, 0.12, 0.12),
    ) -> None:
        self.push_undo_snapshot()
        page = self.doc[page_index]
        fpath = get_unicode_font_path(bold=True)
        fnt = ImageFont.truetype(fpath, 54) if fpath else ImageFont.load_default()

        tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        bb = ImageDraw.Draw(tmp).textbbox((0, 0), label.upper(), font=fnt)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        w, h = tw + 68, th + 42
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        dr = ImageDraw.Draw(im)
        col_255 = (int(color_rgb[0] * 255), int(color_rgb[1] * 255), int(color_rgb[2] * 255))
        dr.rounded_rectangle([6, 6, w - 6, h - 6], radius=18, fill=col_255 + (28,), outline=col_255 + (235,), width=7)
        dr.text(((w - tw) / 2 - bb[0], (h - th) / 2 - bb[1]), label.upper(), font=fnt, fill=col_255 + (240,))

        buf = io.BytesIO()
        im.save(buf, format="PNG")
        target = fitz.Rect(x, y, x + w * 0.34, y + h * 0.34) & page.rect
        page.insert_image(target, stream=buf.getvalue(), keep_proportion=True, overlay=True)

    def redact_permanent(
        self,
        page_index: int,
        rect_tuple: Tuple[float, float, float, float],
        fill_rgb: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> None:
        self.push_undo_snapshot()
        page = self.doc[page_index]
        r = fitz.Rect(rect_tuple) & page.rect
        page.add_redact_annot(r, fill=fill_rgb)
        page.apply_redactions()

    # --- SPRÁVA STRÁNEK, VODOZNAK, FORMULÁŘE, KOMPRESE A HESLA ---

    def rotate_page(self, page_index: int, delta_deg: int = 90) -> None:
        self.push_undo_snapshot()
        p = self.doc[page_index]
        p.set_rotation((p.rotation + delta_deg) % 360)

    def delete_pages(self, indices: List[int]) -> None:
        if len(indices) >= len(self.doc):
            raise ValueError("Nelze smazat úplně všechny stránky dokumentu.")
        self.push_undo_snapshot()
        for idx in sorted(set(indices), reverse=True):
            if 0 <= idx < len(self.doc):
                self.doc.delete_page(idx)

    def move_page(self, from_idx: int, to_idx: int) -> None:
        if from_idx == to_idx or not (0 <= from_idx < len(self.doc)) or not (0 <= to_idx < len(self.doc)):
            return
        self.push_undo_snapshot()
        self.doc.move_page(from_idx, to_idx)

    def insert_blank_page(self, after_index: int) -> int:
        self.push_undo_snapshot()
        ref = self.doc[min(max(0, after_index), len(self.doc) - 1)].rect
        ins_at = min(len(self.doc), after_index + 1)
        self.doc.new_page(pno=ins_at, width=ref.width, height=ref.height)
        return ins_at

    def append_pdf_files(self, paths: List[str]) -> None:
        self.push_undo_snapshot()
        for p in paths:
            with fitz.open(p) as src:
                self.doc.insert_pdf(src)

    def extract_pages_to_file(self, indices: List[int], out_path: str) -> None:
        out_doc = fitz.open()
        for idx in indices:
            if 0 <= idx < len(self.doc):
                out_doc.insert_pdf(self.doc, from_page=idx, to_page=idx)
        out_doc.save(out_path, garbage=4, deflate=True)
        out_doc.close()

    def split_all_pages_to_folder(self, folder_path: str, prefix: str = "strana") -> int:
        os.makedirs(folder_path, exist_ok=True)
        count = len(self.doc)
        for i in range(count):
            single = fitz.open()
            single.insert_pdf(self.doc, from_page=i, to_page=i)
            single.save(os.path.join(folder_path, f"{prefix}_{i + 1:03d}.pdf"), garbage=3, deflate=True)
            single.close()
        return count

    def add_watermark_all_pages(self, text: str, opacity: float = 0.18) -> None:
        if not text.strip():
            return
        self.push_undo_snapshot()
        fpath = get_unicode_font_path(bold=True)
        fnt = ImageFont.truetype(fpath, 92) if fpath else ImageFont.load_default()
        alpha = max(15, min(220, int(round(opacity * 255))))

        tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        bb = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=fnt)
        tw, th = bb[2] - bb[0] + 40, bb[3] - bb[1] + 40
        stamp = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        ImageDraw.Draw(stamp).text((20 - bb[0], 20 - bb[1]), text, font=fnt, fill=(100, 116, 139, alpha))
        rotated = stamp.rotate(35, expand=True, resample=Image.Resampling.BICUBIC)
        buf = io.BytesIO()
        rotated.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        for page in self.doc:
            pr = page.rect
            margin_x, margin_y = pr.width * 0.12, pr.height * 0.18
            box = fitz.Rect(margin_x, margin_y, pr.width - margin_x, pr.height - margin_y)
            page.insert_image(box, stream=png_bytes, keep_proportion=True, overlay=True)

    def add_page_numbers(self, fmt: str = "{n} / {total}") -> None:
        self.push_undo_snapshot()
        total = len(self.doc)
        fpath = get_unicode_font_path(bold=False)
        for idx, page in enumerate(self.doc):
            label = fmt.format(n=idx + 1, total=total)
            pr = page.rect
            if fpath:
                f_obj = fitz.Font(fontfile=fpath)
                w = f_obj.text_length(label, fontsize=10.0)
                page.insert_font(fontname="F_PG", fontfile=fpath)
                page.insert_text(fitz.Point((pr.width - w) / 2, pr.height - 20), label, fontname="F_PG", fontsize=10.0, color=(0.35, 0.38, 0.42))
            else:
                page.insert_text(fitz.Point(pr.width / 2 - 18, pr.height - 20), label, fontname="helv", fontsize=10.0, color=(0.35, 0.38, 0.42))

    def get_page_form_fields(self, page_index: int) -> List[FormFieldInfo]:
        page = self.doc[page_index]
        fields: List[FormFieldInfo] = []
        for w in page.widgets() or []:
            r = w.rect
            fields.append(
                FormFieldInfo(
                    xref=w.xref,
                    field_name=w.field_name or f"Pole_{w.xref}",
                    field_label=w.field_label or w.field_name or f"Pole {w.xref}",
                    field_type=w.field_type,
                    field_value=str(w.field_value or ""),
                    rect=(r.x0, r.y0, r.x1, r.y1),
                    choice_values=list(w.choice_values or []),
                )
            )
        return fields

    def update_form_fields(self, page_index: int, new_values_by_xref: dict) -> None:
        self.push_undo_snapshot()
        page = self.doc[page_index]
        for w in page.widgets() or []:
            if w.xref in new_values_by_xref:
                w.field_value = new_values_by_xref[w.xref]
                w.update()

    def export_images(self, folder_path: str, fmt: str = "png", dpi: int = 180) -> int:
        os.makedirs(folder_path, exist_ok=True)
        zoom = dpi / 72.0
        ext = "jpg" if fmt.lower() in ("jpg", "jpeg") else "png"
        for i, page in enumerate(self.doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            pix.save(os.path.join(folder_path, f"strana_{i + 1:03d}.{ext}"))
        return len(self.doc)

    @staticmethod
    def create_from_images(image_paths: List[str]) -> "PDFDocumentSession":
        out = fitz.open()
        for p in image_paths:
            with Image.open(p) as im:
                rgb = im.convert("RGB")
                buf = io.BytesIO()
                rgb.save(buf, format="JPEG", quality=92)
                w, h = rgb.size
                page = out.new_page(width=w * 72 / 96, height=h * 72 / 96)
                page.insert_image(page.rect, stream=buf.getvalue())
        raw = out.tobytes(deflate=True)
        out.close()
        sess = PDFDocumentSession(raw_bytes=raw)
        sess.modified = True
        return sess

    def save(self, target_path: Optional[str] = None) -> str:
        out = target_path or self.file_path
        if not out:
            raise ValueError("Není zvolena cílová cesta souboru.")
        same_file = bool(self.file_path and os.path.abspath(out) == os.path.abspath(self.file_path) and os.path.exists(out))
        if same_file:
            tmp_out = out + ".tmp_save"
            self.doc.save(tmp_out, garbage=3, deflate=True)
            self.doc.close()
            os.replace(tmp_out, out)
            self.doc = fitz.open(out)
        else:
            self.doc.save(out, garbage=3, deflate=True)
        self.file_path = out
        self.modified = False
        return out

    def save_compressed(self, out_path: str, quality: int = 70, target_dpi: int = 140) -> Tuple[int, int]:
        orig_size = os.path.getsize(self.file_path) if (self.file_path and os.path.exists(self.file_path)) else len(self.doc.tobytes())
        work = fitz.open(stream=self.doc.tobytes(), filetype="pdf")
        if hasattr(work, "rewrite_images"):
            try:
                work.rewrite_images(dpi_threshold=target_dpi + 30, dpi_target=target_dpi, quality=quality, lossy=True, lossless=True)
            except Exception:
                pass
        work.save(out_path, garbage=4, deflate=True, clean=True)
        work.close()
        return orig_size, os.path.getsize(out_path)

    def save_with_password(self, out_path: str, user_pw: str, owner_pw: Optional[str] = None) -> None:
        enc = getattr(fitz, "PDF_ENCRYPT_AES_256", 4)
        self.doc.save(
            out_path,
            garbage=3,
            deflate=True,
            encryption=enc,
            user_pw=user_pw,
            owner_pw=owner_pw or user_pw,
        )

    def save_unlocked(self, out_path: str) -> None:
        enc_none = getattr(fitz, "PDF_ENCRYPT_NONE", 0)
        self.doc.save(out_path, garbage=3, deflate=True, encryption=enc_none)

    def run_ocr_page(self, page_index: int) -> str:
        import pytesseract

        candidates = [
            shutil.which("tesseract"),
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        ]
        tess_bin = next((c for c in candidates if c and os.path.isfile(c)), None)
        if not tess_bin:
            raise RuntimeError(
                "Tesseract OCR nebyl v PC nalezen.\n"
                "Pro čtení naskenovaných obrázků si doinstaluj bezplatný balíček UB-Mannheim Tesseract OCR (včetně češtiny) do C:\\Program Files\\Tesseract-OCR."
            )
        pytesseract.pytesseract.tesseract_cmd = tess_bin
        pix = self.doc[page_index].get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        try:
            return pytesseract.image_to_string(im, lang="ces+eng").strip()
        except Exception:
            return pytesseract.image_to_string(im).strip()
