"""
screenshots.py
--------------
Genera capturas de cada ventana de la app (principal, biblioteca y revision)
con datos de ejemplo, para poder pasarselas a un disenador. No llama a la API
ni a internet: monta las ventanas, las renderiza y captura su region exacta con
`screencapture` (macOS).

Uso:
    python scripts/screenshots.py
Las imagenes quedan en  capturas/
"""

from __future__ import annotations

import os
import sys
import time
import types
import subprocess

import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod  # noqa: E402
from core.detector import Advertiser  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "capturas")


def _placeholder_page(path: str, label: str):
    """Crea una imagen tipo 'pagina de revista' para la previa de revision."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    w, h = 900, 1240
    img = Image.new("RGB", (w, h), "#f4f4f2")
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, w - 40, h - 40], outline="#ececea", width=3)
    d.rectangle([40, 40, w - 40, 150], fill="#0a0a0a")
    d.text((70, 80), "ANUNCIO  ·  " + label, fill="#ffffff")
    d.rectangle([70, 220, w - 70, 760], fill="#ececea")
    d.text((70, 800), "Marca de ejemplo", fill="#0a0a0a")
    d.text((70, 840), "www.ejemplo.com  ·  900 000 000", fill="#9a9a97")
    d.rectangle([w - 230, h - 130, w - 70, h - 70], fill="#ff4b00")
    img.save(path)
    return True


def _capture(win, name: str):
    win.update_idletasks()
    win.deiconify()
    win.lift()
    win.attributes("-topmost", True)
    win.update()
    time.sleep(0.6)
    win.update()
    x, y = win.winfo_rootx(), win.winfo_rooty()
    w, h = win.winfo_width(), win.winfo_height()
    out = os.path.join(OUT_DIR, name + ".png")
    subprocess.run(
        ["screencapture", "-x", f"-R{x},{y},{w},{h}", out], check=False)
    win.attributes("-topmost", False)
    print(f"  {name}.png  ({w}x{h} pt)  ->  {out}")
    return out


def _sample_flagged():
    return [
        Advertiser(brand="Eurofred", pages=[12], website="eurofred.com",
                   sector="Climatizacion industrial", ad_size="pagina",
                   confidence=0.48, method="ia",
                   review_flag="confianza_baja"),
        Advertiser(brand="Distribuciones Garcia", pages=[24],
                   website="", phone="900111222",
                   sector="Logistica y distribucion", ad_size="media",
                   confidence=0.55, method="ia",
                   review_flag="sin_web"),
        Advertiser(brand="Cafe del Sur", pages=[31], website="cafedelsur.es",
                   sector="Bebidas / cafe", ad_size="pagina",
                   confidence=0.62, method="ia",
                   review_flag="posible_editorial"),
        Advertiser(brand="Hostelco", pages=[5], website="hostelco.com",
                   sector="Hosteleria y restauracion", ad_size="doble",
                   confidence=0.51, method="ia",
                   review_flag="confianza_baja"),
    ]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    placeholders = {}
    for n in (5, 12, 24, 31):
        p = os.path.join(OUT_DIR, f"_pagina_{n}.png")
        if _placeholder_page(p, f"PAGINA {n}"):
            placeholders[n] = p

    pages = [types.SimpleNamespace(number=n,
                                   image_path=placeholders.get(n, ""))
             for n in (5, 12, 24, 31)]

    # --- 1. Ventana principal ---------------------------------------------
    a = appmod.App()
    a.geometry("+80+60")
    # Mostramos el modo IA para que se vea el campo de clave y la casilla.
    a.mode.set("ia")
    a._toggle_key()
    _capture(a, "01_principal")

    # --- 2. Biblioteca ----------------------------------------------------
    lib = appmod.LibraryWindow(a)
    lib.geometry("+120+90")
    _capture(lib, "02_biblioteca")
    try:
        lib.lib.close()
    except Exception:  # noqa: BLE001
        pass
    lib.destroy()

    # --- 3. Revision de casos dudosos -------------------------------------
    rev = appmod.ReviewWindow(a, _sample_flagged(), pages,
                              on_done=lambda *_: None)
    rev.geometry("+100+70")
    _capture(rev, "03_revision")
    rev.grab_release()
    rev.destroy()

    a.destroy()
    print("\nCapturas en:", OUT_DIR)


if __name__ == "__main__":
    main()
