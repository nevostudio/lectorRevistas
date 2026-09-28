"""
web_preview.py (solo desarrollo)
--------------------------------
Arranca el servidor web de NEVO en un puerto fijo y siembra datos de ejemplo
en la pantalla de Revisión, para poder ver/capturar el rediseño sin lanzar una
extracción real. No forma parte de la app.

Uso:  python scripts/web_preview.py [puerto]
"""

from __future__ import annotations

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import webapp  # noqa: E402
from core.detector import Advertiser  # noqa: E402
from core.detector import mark_for_review  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

CAP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "capturas")


def _seed():
    ads = [
        Advertiser(brand="Eurofred", pages=[12], website="eurofred.com",
                   sector="Climatización industrial", ad_size="Página completa",
                   confidence=0.48, method="ia"),
        Advertiser(brand="Distribuciones García", pages=[24],
                   website="distgarcia.es", email="info@distgarcia.es",
                   sector="Material de obra", ad_size="Media página",
                   confidence=0.55, method="ia"),
        Advertiser(brand="Café del Sur", pages=[31], phone="955 000 000",
                   sector="Hostelería", ad_size="Faldón",
                   confidence=0.62, method="ia"),
        Advertiser(brand="Hostelco", pages=[5], website="hostelco.com",
                   sector="Equipamiento", ad_size="Doble página",
                   confidence=0.51, method="ia"),
    ]
    # forzamos flags de revisión
    mark_for_review(ads, "Proarquitectura")
    for a in ads:
        if not a.review_flag:
            a.review_flag = "low_conf"
    pages = [types.SimpleNamespace(number=n,
             image_path=os.path.join(CAP, f"_pagina_{n}.png"))
             for n in (5, 12, 24, 31)]
    webapp.JOB.update(
        state="done", step=6,
        result={"advertisers": ads, "pages": pages,
                "meta": {"titulo": "Proarquitectura · #206",
                         "modo": "IA (analisis visual)", "paginas": 48}},
        summary={"total": 53, "flagged": len(ads)}, exported=False,
    )


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7799
    _seed()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), webapp.Handler)
    print(f"preview en http://127.0.0.1:{port}/")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
