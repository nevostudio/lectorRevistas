"""
preguntas_descubrimiento.py
---------------------------
Genera un PDF con las preguntas clave a hacerle al cliente (o a uno mismo)
antes de decidir hacia donde tirar con el producto.
"""

from __future__ import annotations

import os
import datetime
import fitz  # PyMuPDF


# --- Paleta Nevo ---
INK = (10/255, 10/255, 10/255)
ORANGE = (1.0, 75/255, 0/255)
GRAY_50 = (244/255, 244/255, 242/255)
GRAY_100 = (236/255, 236/255, 234/255)
GRAY_400 = (154/255, 154/255, 151/255)
GRAY_800 = (42/255, 42/255, 40/255)


SECTIONS = [
    ("01", "Origen del contenido", [
        "Las revistas que voy a analizar siempre vienen de una web "
        "publica, o tambien me las pasan en PDF?",
        "Si vienen de web: que webs concretas? (cada visor puede "
        "necesitar un fetcher distinto)",
        "Hay revistas en Issuu, Calameo, YUMPU, Flowpaper u otro visor "
        "de tercero? (hoy solo funciona 3D FlipBook de WordPress)",
        "Las webs llevan login o algun tipo de muro de pago?",
        "Con que frecuencia salen ediciones nuevas? "
        "(mensual / trimestral / anual)",
    ]),
    ("02", "Sector y tipo de revista", [
        "Todas las revistas son del mismo sector o cambia?",
        "Si son varios sectores: cuales? (arquitectura, moda, "
        "gastronomia, automocion...)",
        "Tamano tipico: cuantas paginas suele tener una revista?",
        "Cuantos anunciantes esperas mas o menos por revista? "
        "(60? 100? 200?)",
        "Hay anuncios pequenos importantes (fichas, faldones, "
        "publirreportajes, directorios)?",
    ]),
    ("03", "Volumen y uso", [
        "Cuantas revistas voy a procesar al mes? (10? 50? 500?)",
        "Es uso interno (yo / mi equipo) o el cliente entra con login?",
        "Cuantos clientes finales podrian usar esto a la vez?",
        "Cada cliente analiza sus propias revistas o accede a una "
        "biblioteca comun?",
    ]),
    ("04", "Resultado y entrega", [
        "El cliente quiere: descargar Excel/CSV, ver una web con tabla, "
        "integrarlo en su CRM, recibirlo por email?",
        "Necesita filtros por sector, fecha, marca, tamano del anuncio?",
        "Quiere alertas cuando aparece un anunciante nuevo o desaparece "
        "uno que estaba?",
        "Que campos son obligatorios y cuales son opcionales? "
        "(marca, web, email, telefono, sector, tamano)",
        "Quiere un enlace directo a la pagina concreta de la revista "
        "donde aparece el anuncio?",
    ]),
    ("05", "Historico y comparativas", [
        "Quiere comparar numeros entre si (anunciantes nuevos vs el "
        "numero anterior, fidelidad)?",
        "Hay que guardar el historico para analisis multi-mes / "
        "multi-ano?",
        "Quiere ver evolucion de un anunciante concreto en el tiempo "
        "(en que revistas ha aparecido)?",
        "Quiere cruces entre revistas? (\"marcas que aparecen en X "
        "pero no en Y\")",
    ]),
    ("06", "Precision y revision", [
        "Aceptamos algun falso positivo que el cliente filtre, o "
        "cero margen de error?",
        "Yo reviso antes de entregar, o el cliente lo ve \"en crudo\"?",
        "Si reviso yo: cuanto tiempo razonable puedo dedicar por revista?",
        "Si el cliente revisa: necesita la misma UI de revision o le "
        "basta el Excel?",
    ]),
    ("07", "Modelo de negocio", [
        "Cobro por revista procesada, por suscripcion mensual, o mix?",
        "El cliente paga por usar la herramienta (SaaS) o por recibir "
        "el informe ya hecho (info-as-a-service)?",
        "Precio orientativo que tienes en cabeza? (por revista / al mes)",
        "Hay limite de uso por plan? (X revistas al mes, paginas, "
        "llamadas a IA)",
    ]),
    ("08", "Branding y entrega visual", [
        "El informe va con marca Nevo o lo entregan a sus clientes? "
        "(white-label)",
        "Quieres login del cliente con su logo y colores, o todo Nevo?",
        "Necesitas exportar a un formato concreto del cliente "
        "(plantilla Excel suya, JSON especifico)?",
    ]),
    ("09", "Datos, privacidad y costes", [
        "Hay clientes que NO quieran que sus revistas pasen por una "
        "API externa (Claude)?",
        "Necesito opcion on-premise / sin API externa? "
        "(seria el modo gratis, mucho peor)",
        "Quien paga las llamadas a la API de IA? "
        "(las cargamos al precio del cliente o las absorbemos)",
        "Hay limite de coste por revista que NO podemos pasar para "
        "tener margen?",
    ]),
]


# ----------------------------------------------------------------------
def _draw_nevo_brand(page: fitz.Page, x: float, y: float):
    """Dibuja el monograma N + wordmark NEVO con la barrita naranja bajo la E."""
    # Cuadrado naranja con N
    size = 26
    page.draw_rect(fitz.Rect(x, y, x + size, y + size),
                    color=ORANGE, fill=ORANGE, width=0)
    page.insert_text((x + 7.5, y + 19), "N",
                      fontname="hebo", fontsize=18, color=(1, 1, 1))

    # Wordmark NEVO
    wx = x + size + 10
    page.insert_text((wx, y + 19), "NEVO",
                      fontname="hebo", fontsize=22, color=INK)
    # Barrita naranja bajo la E (segundo caracter): aproximamos su posicion.
    e_left = wx + 14
    e_right = wx + 27
    page.draw_rect(fitz.Rect(e_left, y + 22, e_right, y + 24.5),
                    color=ORANGE, fill=ORANGE, width=0)


def _new_page(doc: fitz.Document, w: float, h: float,
              margin: float, footer_text: str) -> fitz.Page:
    page = doc.new_page(width=w, height=h)
    # Footer.
    page.insert_text((margin, h - margin / 2 + 8),
                      footer_text, fontname="cour", fontsize=8,
                      color=GRAY_400)
    page.insert_text((w - margin - 90, h - margin / 2 + 8),
                      "NEVO.STUDIO", fontname="cour", fontsize=8,
                      color=INK)
    return page


def build_pdf(out_path: str):
    doc = fitz.open()
    W, H = fitz.paper_size("a4")  # 595 x 842
    margin = 50

    fecha = datetime.datetime.now().strftime("%d.%m.%Y").upper()
    footer = f"PREGUNTAS DE DESCUBRIMIENTO  ·  {fecha}"

    # ============== PORTADA ==============
    page = _new_page(doc, W, H, margin, footer)

    _draw_nevo_brand(page, margin, margin)

    # Kicker
    page.insert_text((margin, margin + 90),
                      "● INTELIGENCIA COMPETITIVA EN REVISTAS",
                      fontname="cour", fontsize=10, color=GRAY_400)

    # Titulo grande
    title_lines = [
        "PREGUNTAS",
        "DE DESCUBRIMIENTO",
        "AL CLIENTE.",
    ]
    ty = margin + 150
    for line in title_lines:
        page.insert_text((margin, ty), line,
                          fontname="hebo", fontsize=46, color=INK)
        ty += 52

    # Subtitulo / parrafo intro
    intro = (
        "Antes de decidir hacia donde escalar el extractor de anunciantes "
        "(soportar mas visores, mas sectores, white-label, SaaS...), "
        "responder estas preguntas con el cliente. Las respuestas marcan "
        "el roadmap real, no las suposiciones."
    )
    rect = fitz.Rect(margin, ty + 20, W - margin, ty + 130)
    page.insert_textbox(rect, intro, fontname="helv", fontsize=11.5,
                         color=GRAY_800, align=fitz.TEXT_ALIGN_LEFT)

    # Linea naranja
    page.draw_line((margin, H - margin - 50),
                    (margin + 90, H - margin - 50),
                    color=ORANGE, width=3)
    page.insert_text((margin, H - margin - 30),
                      "9 BLOQUES  ·  35+ PREGUNTAS",
                      fontname="cour", fontsize=9, color=GRAY_400)

    # ============== PAGINAS DE PREGUNTAS ==============
    for code, title, questions in SECTIONS:
        page = _new_page(doc, W, H, margin, footer)
        _draw_nevo_brand(page, margin, margin)

        # Numero gigante del bloque + titulo
        page.insert_text((margin, margin + 120), code,
                          fontname="hebo", fontsize=64, color=ORANGE)
        page.insert_text((margin + 80, margin + 80),
                          "BLOQUE",
                          fontname="cour", fontsize=10, color=GRAY_400)
        # Titulo del bloque
        page.insert_text((margin + 80, margin + 115),
                          title.upper(),
                          fontname="hebo", fontsize=26, color=INK)

        # Linea separadora
        sep_y = margin + 150
        page.draw_line((margin, sep_y), (W - margin, sep_y),
                        color=GRAY_100, width=1)

        # Preguntas
        y = sep_y + 30
        for i, q in enumerate(questions, 1):
            num = f"{int(code):02d}.{i:02d}"
            # numero mono
            page.insert_text((margin, y), num,
                              fontname="cour", fontsize=9, color=GRAY_400)
            # pregunta con wrap
            rect = fitz.Rect(margin + 60, y - 11,
                              W - margin, y + 80)
            used = page.insert_textbox(
                rect, q, fontname="helv", fontsize=11.5, color=INK,
                align=fitz.TEXT_ALIGN_LEFT)
            # Calcular altura real (aprox 14pt por linea)
            # used puede ser negativo si no cabe; lo gestionamos a ojo:
            lines_approx = max(1, int((rect.width and
                                        (len(q) / (rect.width / 6.5))) + 0.5))
            block_h = 14 * lines_approx + 8
            # linea separadora fina
            sep_y2 = y + block_h + 4
            page.draw_line((margin + 60, sep_y2),
                            (W - margin, sep_y2),
                            color=GRAY_100, width=0.5)
            y = sep_y2 + 16

            if y > H - margin - 60:
                # nueva pagina de continuacion (mismo bloque)
                page = _new_page(doc, W, H, margin, footer)
                _draw_nevo_brand(page, margin, margin)
                page.insert_text(
                    (margin, margin + 80),
                    f"BLOQUE {code} · {title.upper()}  (cont.)",
                    fontname="cour", fontsize=10, color=GRAY_400)
                page.draw_line((margin, margin + 100),
                                (W - margin, margin + 100),
                                color=GRAY_100, width=1)
                y = margin + 130

    # ============== CONTRAPORTADA / NOTAS ==============
    page = _new_page(doc, W, H, margin, footer)
    _draw_nevo_brand(page, margin, margin)

    page.insert_text((margin, margin + 100),
                      "NOTAS",
                      fontname="hebo", fontsize=46, color=INK)
    page.draw_line((margin, margin + 120),
                    (margin + 60, margin + 120),
                    color=ORANGE, width=3)

    # Lineas para escribir a mano
    y = margin + 170
    while y < H - margin - 50:
        page.draw_line((margin, y), (W - margin, y),
                        color=GRAY_100, width=0.5)
        y += 26

    doc.save(out_path)
    doc.close()


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "preguntas_descubrimiento.pdf")
    build_pdf(out)
    print(out)
