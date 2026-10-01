"""
pages.py
--------
Convierte la revista (PDF o lista de imagenes) en un conjunto homogeneo de
"paginas", cada una con:
  - una imagen (PNG) para analisis visual / IA
  - el texto incrustado (si el PDF lo trae)
  - el texto por OCR (si se solicita y Tesseract esta disponible)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from core.checkpoint import atomic_write_json, read_json

# PyMuPDF (fitz) para PDF -> imagen y extraccion de texto.
try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

# OCR opcional.
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


@dataclass
class Page:
    number: int
    image_path: str
    embedded_text: str = ""
    ocr_text: str = ""

    @property
    def text(self) -> str:
        """Mejor texto disponible: el incrustado si es suficiente, si no OCR."""
        if len(self.embedded_text.strip()) > 30:
            return self.embedded_text
        return self.ocr_text or self.embedded_text


class PageBuilder:
    def __init__(self, workdir: str, dpi: int = 220, progress=None):
        self.workdir = workdir
        self.dpi = dpi
        self._progress = progress or (lambda m: None)
        self.img_dir = os.path.join(workdir, "render")
        os.makedirs(self.img_dir, exist_ok=True)

    def log(self, msg: str):
        self._progress(msg)

    def _cache_path(self, page_number: int) -> str:
        return os.path.join(self.img_dir, f"page_{page_number:03d}.json")

    @staticmethod
    def _source_marker(path: str) -> dict:
        stat = os.stat(path)
        return {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}

    def _load_cached_page(self, page_number: int, marker: dict,
                          run_ocr: bool) -> Page | None:
        payload = read_json(self._cache_path(page_number))
        if not payload or payload.get("source") != marker:
            return None
        image_value = payload.get("image_path")
        if not isinstance(image_value, str):
            return None
        image_path = os.path.abspath(os.path.join(self.workdir, image_value))
        if os.path.commonpath([image_path, os.path.abspath(self.workdir)]) != \
                os.path.abspath(self.workdir) or not os.path.isfile(image_path):
            return None
        page = Page(
            number=page_number,
            image_path=image_path,
            embedded_text=str(payload.get("embedded_text") or ""),
            ocr_text=str(payload.get("ocr_text") or ""),
        )
        if run_ocr and not payload.get("ocr_attempted"):
            page.ocr_text = self._ocr(image_path)
            self._save_page_cache(page, marker, ocr_attempted=True)
        return page

    def _save_page_cache(self, page: Page, marker: dict,
                         ocr_attempted: bool) -> None:
        atomic_write_json(self._cache_path(page.number), {
            "version": 1,
            "source": marker,
            "image_path": os.path.relpath(page.image_path, self.workdir),
            "embedded_text": page.embedded_text,
            "ocr_text": page.ocr_text,
            "ocr_attempted": bool(ocr_attempted),
        })

    def from_pdf(self, pdf_path: str, run_ocr: bool = False) -> list[Page]:
        if not FITZ_AVAILABLE:
            raise RuntimeError(
                "PyMuPDF no esta instalado. Instalalo con: pip install pymupdf"
            )
        pages: list[Page] = []
        doc = fitz.open(pdf_path)
        zoom = self.dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        self.log(f"La revista tiene {doc.page_count} paginas.")
        marker = self._source_marker(pdf_path)

        for i in range(doc.page_count):
            number = i + 1
            cached = self._load_cached_page(number, marker, run_ocr)
            if cached:
                pages.append(cached)
                self.log(f"Pagina {number}/{doc.page_count} recuperada.")
                continue
            pg = doc.load_page(i)
            pix = pg.get_pixmap(matrix=matrix)
            img_path = os.path.join(self.img_dir, f"page_{number:03d}.png")
            temp_img = os.path.join(
                self.img_dir, f"page_{number:03d}.rendering.png")
            pix.save(temp_img)
            os.replace(temp_img, img_path)
            embedded = pg.get_text("text") or ""
            page = Page(number=number, image_path=img_path,
                        embedded_text=embedded)
            if run_ocr:
                page.ocr_text = self._ocr(img_path)
            pages.append(page)
            self._save_page_cache(page, marker, ocr_attempted=run_ocr)
            self.log(f"Pagina {number}/{doc.page_count} procesada.")
        doc.close()
        return pages

    def from_images(self, image_paths: list[str], run_ocr: bool = True,
                    page_numbers: list[int] | None = None) -> list[Page]:
        if page_numbers is not None and len(page_numbers) != len(image_paths):
            raise ValueError("La numeracion no coincide con las imagenes.")
        pages: list[Page] = []
        for i, src in enumerate(image_paths, 1):
            number = page_numbers[i - 1] if page_numbers is not None else i
            marker = self._source_marker(src)
            cached = self._load_cached_page(number, marker, run_ocr)
            if cached:
                pages.append(cached)
                self.log(f"Pagina {number} ({i}/{len(image_paths)}) "
                         "recuperada.")
                continue
            ocr_text = self._ocr(src) if run_ocr else ""
            page = Page(number=number, image_path=src, ocr_text=ocr_text)
            pages.append(page)
            self._save_page_cache(page, marker, ocr_attempted=run_ocr)
            self.log(f"Pagina {number} ({i}/{len(image_paths)}) procesada.")
        return pages

    def _ocr(self, img_path: str) -> str:
        if not OCR_AVAILABLE:
            return ""
        try:
            return pytesseract.image_to_string(Image.open(img_path),
                                               lang="spa+eng")
        except Exception as e:  # noqa: BLE001
            self.log(f"OCR fallo en {os.path.basename(img_path)}: {e}")
            return ""
