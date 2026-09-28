"""
pipeline.py
-----------
Une todas las fases en una sola llamada reutilizable, tanto por la interfaz
grafica como por la linea de comandos.
"""

from __future__ import annotations

import os

from core.fetcher import MagazineFetcher
from core.pages import PageBuilder
from core.detector import detect_advertisers, mark_for_review
from core.report import export_all
from core.logs import tee


def run_extraction(url: str | None = None,
                    pdf_path: str | None = None,
                    use_ai: bool = False,
                    api_key: str | None = None,
                    run_ocr: bool = True,
                    progress=None) -> dict:
    """
    Ejecuta solo la extraccion (fases 1-3). NO exporta informes.

    Devuelve un dict con paginas, anunciantes (ya anotados con review_flag),
    metadatos y rutas internas. La GUI puede mostrar primero la revision de
    casos dudosos y, al terminar, llamar a export_results().
    """
    progress = tee(progress or (lambda m: print(m)))
    progress("== Iniciando extraccion ==")

    fetcher = MagazineFetcher(progress=progress)
    workdir = fetcher.workdir
    meta = {"url": url or "", "modo": "", "titulo": "Revista", "paginas": "—"}

    # --- Fase 1: conseguir la revista -------------------------------------
    if pdf_path and os.path.exists(pdf_path):
        progress(f"Usando PDF local: {pdf_path}")
        kind, src_pdf, src_imgs, viewer = "pdf", pdf_path, [], None
    else:
        if not url:
            raise ValueError("Hay que indicar una URL o un PDF local.")
        res = fetcher.fetch(url)
        kind = res.kind
        src_pdf = res.pdf_path
        src_imgs = res.image_paths
        viewer = res.viewer
        for note in res.notes:
            progress("· " + note)
        if not res.ok:
            return {"ok": False, "error": "No se pudo obtener la revista.",
                    "notes": res.notes, "workdir": workdir}

    # --- Fase 2: construir paginas ----------------------------------------
    builder = PageBuilder(workdir, progress=progress)
    if kind == "pdf":
        pages = builder.from_pdf(src_pdf, run_ocr=run_ocr and not use_ai)
    else:
        pages = builder.from_images(src_imgs, run_ocr=run_ocr)
    meta["paginas"] = len(pages)
    progress(f"Total de paginas a analizar: {len(pages)}")

    # --- Fase 3: detectar anunciantes -------------------------------------
    telemetry: dict = {}
    advertisers, modo = detect_advertisers(
        pages, use_ai=use_ai, api_key=api_key, progress=progress,
        telemetry=telemetry)
    meta["modo"] = ("IA (analisis visual)" if modo == "ia"
                    else "Heuristica (modo gratis)")
    if telemetry.get("cost_usd") is not None:
        meta["coste_usd"] = telemetry["cost_usd"]
    if telemetry.get("failed_spreads"):
        meta["pliegos_fallidos"] = telemetry["failed_spreads"]
    progress(f"Anunciantes detectados: {len(advertisers)}")

    # --- Fase 3.5: marcar dudosos para revision manual --------------------
    n_flag = mark_for_review(advertisers, meta.get("titulo", ""))
    if n_flag:
        progress(f"{n_flag} anunciante(s) marcado(s) para revision manual.")

    return {
        "ok": True,
        "advertisers": advertisers,
        "pages": pages,
        "meta": meta,
        "viewer": viewer,
        "workdir": workdir,
    }


def export_results(advertisers, meta: dict, outdir: str = "output",
                    progress=None, min_confidence: float = 0.0,
                    save_library: bool = True) -> dict:
    """Genera los entregables (HTML, CSV, JSON). Llamar tras la revision.

    min_confidence: si > 0, descarta anunciantes por debajo de ese umbral.
    Por defecto 0.0 (exporta todo: prioridad de cobertura sobre precision).
    save_library: si True, guarda el analisis en la biblioteca local (SQLite)
    para poder comparar numeros e historicos mas adelante.
    """
    progress = tee(progress or (lambda m: print(m)))
    if min_confidence > 0:
        before = len(advertisers)
        advertisers = [a for a in advertisers
                       if getattr(a, "confidence", 0) >= min_confidence]
        dropped = before - len(advertisers)
        if dropped:
            progress(f"Filtrados {dropped} anunciantes por debajo de "
                     f"confianza {min_confidence:.0%}.")
    paths = export_all(advertisers, outdir, meta)
    progress(f"Informe HTML: {paths['html']}")
    if paths.get("xlsx"):
        progress(f"Excel: {paths['xlsx']}")
    progress(f"CSV: {paths['csv']}")
    progress(f"JSON: {paths['json']}")

    if save_library:
        try:
            from core.library import save_analysis
            issue_id = save_analysis(meta, advertisers)
            paths["issue_id"] = issue_id
            progress(f"Guardado en la biblioteca (numero #{issue_id}).")
        except Exception as e:  # noqa: BLE001
            progress(f"AVISO: no se pudo guardar en la biblioteca: {e}")

    progress("== Proceso terminado ==")
    return paths


def run_pipeline(url: str | None = None,
                 pdf_path: str | None = None,
                 use_ai: bool = False,
                 api_key: str | None = None,
                 run_ocr: bool = True,
                 outdir: str = "output",
                 progress=None) -> dict:
    """Wrapper de compatibilidad: extraccion + export sin revision manual."""
    result = run_extraction(url=url, pdf_path=pdf_path, use_ai=use_ai,
                             api_key=api_key, run_ocr=run_ocr,
                             progress=progress)
    if not result.get("ok"):
        return result
    paths = export_results(result["advertisers"], result["meta"], outdir,
                            progress=progress)
    result["paths"] = paths
    # No exponemos las paginas en el wrapper antiguo (compatibilidad).
    result.pop("pages", None)
    return result
