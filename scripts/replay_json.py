"""
replay_json.py
--------------
Re-procesa un analisis YA hecho (un JSON de output/) con el codigo nuevo,
SIN volver a llamar a la API. Sirve para probar el pipeline actual
(Excel rebrandeado, informe HTML, guardado en la biblioteca, comparativas)
usando datos reales ya validados.

Uso:
    python scripts/replay_json.py output/anunciantes_XXXX.json
    python scripts/replay_json.py output/anunciantes_XXXX.json --titulo "Promateriales" --numero 121
    python scripts/replay_json.py output/anunciantes_XXXX.json --no-library

No gasta nada de API: solo lee el JSON y regenera los entregables.
"""

from __future__ import annotations

import os
import sys
import json
import argparse

# Permite ejecutar desde la raiz del proyecto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import export_results  # noqa: E402


def load(path: str):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return {}, data
    meta = data.get("meta", {}) or {}
    ads = data.get("anunciantes", data.get("advertisers", [])) or []
    return meta, ads


def main():
    ap = argparse.ArgumentParser(description="Replay de un JSON ya analizado.")
    ap.add_argument("json_path", help="Ruta al JSON de output/")
    ap.add_argument("--titulo", help="Sobrescribe el titulo de la revista")
    ap.add_argument("--numero", help="Numero/edicion de la revista")
    ap.add_argument("--outdir", default="output", help="Carpeta de salida")
    ap.add_argument("--no-library", action="store_true",
                    help="No guardar en la biblioteca")
    args = ap.parse_args()

    meta, ads = load(args.json_path)
    if args.titulo:
        meta["titulo"] = args.titulo
    if args.numero:
        meta["numero"] = args.numero

    print(f"== REPLAY (sin API) ==")
    print(f"Fuente JSON ....... {args.json_path}")
    print(f"Revista ........... {meta.get('titulo','Revista')}"
          f" #{meta.get('numero','')}".rstrip(" #"))
    print(f"Modo original ..... {meta.get('modo','?')}")
    print(f"Anunciantes ....... {len(ads)}")
    print("-" * 48)

    paths = export_results(
        ads, meta, outdir=args.outdir,
        progress=lambda m: print("  " + m),
        save_library=not args.no_library,
    )
    print("-" * 48)
    print("Entregables generados:")
    for k in ("html", "xlsx", "csv", "json"):
        if paths.get(k):
            print(f"  {k.upper():5} -> {paths[k]}")
    if paths.get("issue_id"):
        print(f"  Biblioteca: numero #{paths['issue_id']}")


if __name__ == "__main__":
    main()
