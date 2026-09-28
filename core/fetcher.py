"""
fetcher.py
----------
Localiza y descarga la revista a partir de una URL pública.

La revista normalmente NO está en el HTML directo: se carga con JavaScript
mediante un visor embebido (flipbook). Este modulo intenta, en orden:

  1. Buscar un PDF directo en el HTML / peticiones de red.
  2. Detectar visores conocidos (Issuu, Calameo, FlippingBook, etc.).
  3. Renderizar la pagina con un navegador headless (Playwright) y capturar
     las imagenes de cada pagina del flipbook.

El resultado siempre es una lista de rutas a imagenes (una por pagina) o
la ruta a un PDF, en una carpeta de trabajo.
"""

from __future__ import annotations

import os
import re
import time
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests

# Playwright es opcional: si no esta instalado, avisamos con instrucciones.
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Servicios de flipbook conocidos. Cada entrada: dominio -> nombre legible.
KNOWN_VIEWERS = {
    "issuu.com": "Issuu",
    "calameo.com": "Calameo",
    "calameo.es": "Calameo",
    "flippingbook.com": "FlippingBook",
    "fliphtml5.com": "FlipHTML5",
    "joomag.com": "Joomag",
    "publuu.com": "Publuu",
    "anyflip.com": "AnyFlip",
    "ourdigitalmag.com": "OurDigitalMag",
}


@dataclass
class FetchResult:
    """Resultado de la fase de descarga."""
    source_url: str
    kind: str                       # "pdf" | "images" | "none"
    pdf_path: str | None = None
    image_paths: list[str] = field(default_factory=list)
    viewer: str | None = None       # nombre del visor detectado, si lo hay
    workdir: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.kind in ("pdf", "images") and (
            self.pdf_path is not None or len(self.image_paths) > 0
        )


class MagazineFetcher:
    def __init__(self, workdir: str | None = None, headless: bool = True,
                 progress=None):
        """
        workdir   : carpeta de trabajo. Si es None se crea una temporal.
        headless  : si False, el navegador se ve (util para depurar).
        progress  : funcion opcional progress(mensaje:str) para feedback UI.
        """
        self.workdir = workdir or tempfile.mkdtemp(prefix="revista_")
        os.makedirs(self.workdir, exist_ok=True)
        self.headless = headless
        self._progress = progress or (lambda m: None)

    def log(self, msg: str):
        self._progress(msg)

    # ------------------------------------------------------------------ #
    # Punto de entrada principal
    # ------------------------------------------------------------------ #
    def fetch(self, url: str) -> FetchResult:
        self.log(f"Analizando la pagina: {url}")
        result = FetchResult(source_url=url, kind="none", workdir=self.workdir)

        html = self._get_html_static(url)
        if html:
            # 1) PDF directo en el HTML estatico
            pdf_url = self._find_pdf_in_html(html, url)
            if pdf_url:
                self.log(f"PDF encontrado en el HTML: {pdf_url}")
                path = self._download_pdf(pdf_url)
                if path:
                    result.kind = "pdf"
                    result.pdf_path = path
                    return result

            # 2) Visor embebido conocido
            viewer_url, viewer_name = self._find_embedded_viewer(html, url)
            if viewer_url:
                result.viewer = viewer_name
                result.notes.append(
                    f"Visor detectado: {viewer_name} ({viewer_url})"
                )
                self.log(f"Visor embebido detectado: {viewer_name}")

        # 3) Render con navegador headless (lo mas fiable)
        if PLAYWRIGHT_AVAILABLE:
            self.log("Cargando la revista con navegador (puede tardar)...")
            browser_result = self._fetch_with_browser(url)
            if browser_result and browser_result.ok:
                browser_result.viewer = browser_result.viewer or result.viewer
                browser_result.notes = result.notes + browser_result.notes
                return browser_result
        else:
            result.notes.append(
                "Playwright no esta instalado: no se puede renderizar el "
                "flipbook. Instalalo con:\n"
                "    pip install playwright && playwright install chromium"
            )

        if not result.ok:
            result.notes.append(
                "No se pudo extraer la revista automaticamente. "
                "Opciones: (a) instalar Playwright, (b) descargar el PDF "
                "manualmente y usar el modo 'Archivo PDF local'."
            )
        return result

    # ------------------------------------------------------------------ #
    # Descarga estatica de HTML
    # ------------------------------------------------------------------ #
    def _get_html_static(self, url: str) -> str | None:
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT},
                              timeout=30)
            r.raise_for_status()
            return r.text
        except Exception as e:  # noqa: BLE001
            self.log(f"No se pudo descargar el HTML estatico: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Deteccion de PDF en el HTML
    # ------------------------------------------------------------------ #
    @staticmethod
    def _find_pdf_in_html(html: str, base_url: str) -> str | None:
        # Cualquier enlace .pdf
        candidates = re.findall(r'["\']([^"\']+?\.pdf)["\']', html, re.I)
        for c in candidates:
            # Evitar PDFs de documentos legales / formularios
            if any(bad in c.lower() for bad in
                   ("politica", "aviso", "privacid", "cookie")):
                continue
            return urljoin(base_url, c)
        return None

    # ------------------------------------------------------------------ #
    # Deteccion de visor embebido
    # ------------------------------------------------------------------ #
    @staticmethod
    def _find_embedded_viewer(html: str, base_url: str):
        # iframes y enlaces que apunten a servicios conocidos
        urls = re.findall(r'(?:src|href)=["\']([^"\']+)["\']', html, re.I)
        for u in urls:
            full = urljoin(base_url, u)
            host = urlparse(full).netloc.lower()
            for domain, name in KNOWN_VIEWERS.items():
                if domain in host:
                    return full, name
        return None, None

    # ------------------------------------------------------------------ #
    # Descarga de PDF
    # ------------------------------------------------------------------ #
    def _download_pdf(self, pdf_url: str) -> str | None:
        try:
            r = requests.get(pdf_url, headers={"User-Agent": USER_AGENT},
                             timeout=120, stream=True)
            r.raise_for_status()
            ctype = r.headers.get("Content-Type", "").lower()
            if "pdf" not in ctype and not pdf_url.lower().endswith(".pdf"):
                self.log(f"El recurso no parece un PDF ({ctype}).")
                return None
            path = os.path.join(self.workdir, "revista.pdf")
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
            self.log(f"PDF descargado: {os.path.getsize(path)//1024} KB")
            return path
        except Exception as e:  # noqa: BLE001
            self.log(f"Error descargando el PDF: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Render con navegador headless
    # ------------------------------------------------------------------ #
    def _fetch_with_browser(self, url: str) -> FetchResult | None:
        result = FetchResult(source_url=url, kind="none", workdir=self.workdir)
        captured_pdfs: list[str] = []
        captured_images: set[str] = set()

        def handle_response(response):
            try:
                ct = response.headers.get("content-type", "").lower()
                ru = response.url
                if "application/pdf" in ct or ru.lower().endswith(".pdf"):
                    captured_pdfs.append(ru)
                # Imagenes grandes de paginas del flipbook
                if ct.startswith("image/") and any(
                        k in ru.lower()
                        for k in ("page", "large", "slide", "/pages/")):
                    captured_images.add(ru)
            except Exception:  # noqa: BLE001
                pass

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page(user_agent=USER_AGENT,
                                    viewport={"width": 1600, "height": 1200})
            page.on("response", handle_response)

            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
            except Exception as e:  # noqa: BLE001
                self.log(f"Aviso al cargar la pagina: {e}")

            # Intentar entrar al visor "Leer Online"
            self._click_read_online(page)
            time.sleep(3)

            # Recorrer el flipbook pasando paginas para forzar la carga
            self._page_through_flipbook(page)

            # Si en algun iframe hay un PDF accesible, capturarlo
            for frame in page.frames:
                try:
                    fu = frame.url
                    if fu.lower().endswith(".pdf"):
                        captured_pdfs.append(fu)
                except Exception:  # noqa: BLE001
                    pass

            browser.close()

        # Prioridad 1: PDF capturado
        for pdf_url in captured_pdfs:
            path = self._download_pdf(pdf_url)
            if path:
                result.kind = "pdf"
                result.pdf_path = path
                result.notes.append("PDF capturado desde el visor.")
                return result

        # Prioridad 2: imagenes de paginas capturadas
        if captured_images:
            paths = self._download_images(sorted(captured_images))
            if paths:
                result.kind = "images"
                result.image_paths = paths
                result.notes.append(
                    f"{len(paths)} paginas capturadas como imagen.")
                return result

        result.notes.append(
            "El navegador cargo la pagina pero no se identificaron paginas "
            "de la revista. El visor puede requerir interaccion manual."
        )
        return result

    def _click_read_online(self, page):
        """Intenta pulsar el boton/enlace de 'Leer Online' y abrir el visor.

        Algunos plugins (ej. 3D FlipBook en modo thumbnail-lightbox) requieren
        un segundo click sobre el contenedor del libro para disparar la
        descarga real del PDF. Por eso, tras el boton inicial, se intenta un
        segundo click sobre selectores tipicos del contenedor del flipbook.
        """
        selectors = [
            "text=Leer Online", "text=Leer online", "text=LEER ONLINE",
            "a:has-text('Leer')", "[class*='flip']", "[class*='viewer']",
        ]
        first_clicked = False
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    el.click(timeout=3000)
                    self.log(f"Pulsado: {sel}")
                    time.sleep(2)
                    first_clicked = True
                    break
            except Exception:  # noqa: BLE001
                continue

        if not first_clicked:
            return

        # Segundo click: abrir el visor del flipbook (3D FlipBook lightbox).
        container_selectors = [
            "._3d-flip-book", ".fb3d-thumbnail", ".thumbnail",
            "[class*='flip-book']",
        ]
        for sel in container_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click(timeout=3000)
                    self.log(f"Visor abierto: {sel}")
                    time.sleep(2)
                    return
            except Exception:  # noqa: BLE001
                continue

    def _page_through_flipbook(self, page, max_pages: int = 80):
        """Pasa paginas del flipbook para forzar la carga de cada imagen."""
        for i in range(max_pages):
            advanced = False
            for sel in ["[class*='next']", "[aria-label*='next']",
                        "[aria-label*='Siguiente']", ".nav-next"]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.click(timeout=1500)
                        advanced = True
                        break
                except Exception:  # noqa: BLE001
                    continue
            if not advanced:
                # Probar con tecla de flecha derecha
                try:
                    page.keyboard.press("ArrowRight")
                    advanced = True
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(0.4)
            if not advanced:
                break

    def _download_images(self, urls: list[str]) -> list[str]:
        paths = []
        img_dir = os.path.join(self.workdir, "pages")
        os.makedirs(img_dir, exist_ok=True)
        for idx, u in enumerate(urls, 1):
            try:
                r = requests.get(u, headers={"User-Agent": USER_AGENT},
                                 timeout=60)
                r.raise_for_status()
                ext = ".jpg"
                if "png" in r.headers.get("Content-Type", ""):
                    ext = ".png"
                path = os.path.join(img_dir, f"page_{idx:03d}{ext}")
                with open(path, "wb") as f:
                    f.write(r.content)
                paths.append(path)
            except Exception as e:  # noqa: BLE001
                self.log(f"No se pudo descargar imagen {idx}: {e}")
        return paths


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python fetcher.py <url>")
        sys.exit(1)
    f = MagazineFetcher(progress=print)
    res = f.fetch(sys.argv[1])
    print(json.dumps({
        "kind": res.kind,
        "pdf": res.pdf_path,
        "imagenes": len(res.image_paths),
        "visor": res.viewer,
        "notas": res.notes,
    }, indent=2, ensure_ascii=False))
