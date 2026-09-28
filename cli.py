"""
cli.py
------
Interfaz de linea de comandos para analizar una revista sin abrir la GUI.
Util para automatizar, para servidores sin pantalla y para procesar por lotes.

Ejemplos:
    python cli.py --url https://ejemplo.com/revista
    python cli.py --pdf revista.pdf --ia
    python cli.py --url https://ejemplo.com/revista --ia --titulo "Promateriales" --numero 121
    python cli.py --url https://ejemplo.com/revista --min-confianza 0.5 --no-biblioteca

La clave de IA se toma de --api-key, de la variable ANTHROPIC_API_KEY o de la
config guardada (en ese orden). En modo IA es obligatoria.
"""

from __future__ import annotations

import sys
import argparse

from pipeline import run_extraction, export_results
from core import config


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Extractor de anunciantes de revistas (Nevo).")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="URL de la revista (visor online o PDF)")
    src.add_argument("--pdf", help="Ruta a un PDF local")

    ap.add_argument("--ia", action="store_true",
                    help="Usa analisis visual con Claude (requiere clave)")
    ap.add_argument("--api-key", help="Clave de API de Anthropic")
    ap.add_argument("--no-ocr", action="store_true",
                    help="Desactiva el OCR en modo gratis")
    ap.add_argument("--titulo", help="Titulo de la revista (para la biblioteca)")
    ap.add_argument("--numero", help="Numero/edicion de la revista")
    ap.add_argument("--outdir", default="output", help="Carpeta de salida")
    ap.add_argument("--min-confianza", type=float, default=0.0,
                    help="Descarta anunciantes por debajo de este umbral (0-1)")
    ap.add_argument("--no-biblioteca", action="store_true",
                    help="No guardar el analisis en la biblioteca local")
    args = ap.parse_args(argv)

    api_key = args.api_key or config.api_key()
    if args.ia and not api_key:
        ap.error("El modo IA necesita una clave: usa --api-key, define "
                 "ANTHROPIC_API_KEY o guardala desde la app.")

    result = run_extraction(
        url=args.url,
        pdf_path=args.pdf,
        use_ai=args.ia,
        api_key=api_key or None,
        run_ocr=not args.no_ocr,
    )
    if not result.get("ok"):
        print("ERROR:", result.get("error", "fallo desconocido"),
              file=sys.stderr)
        return 1

    meta = result["meta"]
    if args.titulo:
        meta["titulo"] = args.titulo
    if args.numero:
        meta["numero"] = args.numero
    if args.url:
        config.set_last_url(args.url)

    paths = export_results(
        result["advertisers"], meta, outdir=args.outdir,
        min_confidence=args.min_confianza,
        save_library=not args.no_biblioteca,
    )

    print("\nEntregables:")
    for k in ("html", "xlsx", "csv", "json"):
        if paths.get(k):
            print(f"  {k.upper():5} {paths[k]}")
    if paths.get("issue_id"):
        print(f"  Biblioteca: numero #{paths['issue_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
