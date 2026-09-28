"""
sectors.py
----------
La IA describe el sector de cada anunciante de forma muy especifica
("Alimentacion / Quesos", "Asesoria estrategica en restauracion"...). Eso es
util como detalle, pero rompe el reparto por sector (share of voice): cada
anunciante cae en su propio grupo de uno.

Este modulo agrupa esos sectores libres en CATEGORIAS AMPLIAS mediante palabras
clave, para que el reparto por sector sea legible. Se conserva siempre el
sector original; el grupo es un campo adicional.
"""

from __future__ import annotations

# Orden importante: gana la PRIMERA categoria cuyo keyword aparezca en el
# texto. La IA suele describir el sector como "X para hosteleria", donde
# "para hosteleria" es el publico OBJETIVO, no la actividad del anunciante.
# Por eso la actividad real (marketing, tecnologia, mobiliario...) va PRIMERO
# y "Hosteleria y restauracion" queda al final, para capturar solo lo que de
# verdad es un restaurante/bar/catering sin otra senal mas concreta.
SECTOR_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("Marketing y comunicacion", (
        "marketing", "seo", "sem ", "publicidad", "comunicacion", "agencia",
        "redes sociales", "branding", "medios", "prensa", "diseno",
    )),
    ("Tecnologia y software", (
        "software", "digital", "tecnolog", "tpv", "datos", "plataforma",
        "ecommerce", "saas", "sistema", "informatic", "aplicacion",
        "inteligencia artificial", " ia ", " app ", "web ",
    )),
    ("Servicios profesionales", (
        "asesor", "consultor", "gestor", "juridic", "legal", "abogad",
        "financ", "seguro", "formacion", "recursos humanos", "rrhh",
        "franquici", "contab", "auditor",
    )),
    ("Bebidas", (
        "bebida", "vino", "cerveza", "agua", "refresco", "cafe", "licor",
        "destil", "zumo", "bodega", "vermut", "spirit", "drink", "barril",
    )),
    ("Alimentacion", (
        "aliment", "comida", "food", "queso", "carn", "charcuter", "jamon",
        "pan", "paste", "conserva", "congelad", "fruta", "verdura", "lacte",
        "embutid", "snack", "dulce", "choco", "aceite", "salsa", "marisco",
        "pescad", "gourmet", "ultramarinos",
    )),
    ("Maquinaria y equipamiento", (
        "maquina", "equipa", "horno", "freidora", "lavavaj", "refrigera",
        "frio", "vitrina", "cafetera", "dispensador", "utillaje", "fabrica",
        "industrial",
    )),
    ("Mobiliario y decoracion", (
        "mobil", "mueble", "decora", "interioris", "menaje", "vajilla",
        "cristaleria", "ilumina", "lampar", "textil hogar",
    )),
    ("Limpieza e higiene", (
        "limpieza", "higien", "desinfec", "lavanderia", "detergente",
    )),
    ("Bano y sanitarios", (
        "sanitari", "bano", "grifer", "ducha", "fontaner",
    )),
    ("Climatizacion y energia", (
        "climatiza", "calefac", "aire acondicionado", "energ", "solar",
        "fotovolt", "ventilacion", "hvac", "caldera",
    )),
    ("Construccion y materiales", (
        "construc", "material", "ceramic", "azulejo", "pavimento", "hormig",
        "acero", "aislamiento", "fachada", "cubierta", "ladrillo", "piedra",
        "madera", "carpinter", "obra", "revestimiento",
    )),
    ("Textil y uniformes", (
        "textil", "uniforme", "ropa", "vestuario", "calzado", "moda",
    )),
    ("Logistica y distribucion", (
        "logist", "distribu", "transporte", "almacen", "reparto",
        "suministr", "mayorista",
    )),
    ("Hosteleria y restauracion", (
        "hosteler", "restaura", "catering", "gastro",
    )),
]

DEFAULT_GROUP = "Otros"
EMPTY_GROUP = "Sin sector"

_ACCENTS = str.maketrans("áéíóúüñ", "aeiouun")


def _norm(text: str) -> str:
    # Rodea de espacios para que keywords con espacio (" ia ") casen en bordes.
    return " " + (text or "").lower().translate(_ACCENTS).strip() + " "


def normalize_sector(sector: str) -> str:
    """Devuelve la categoria amplia para un sector libre.

    "" / None -> 'Sin sector'. Sin coincidencia -> 'Otros'.
    """
    if not sector or not sector.strip():
        return EMPTY_GROUP
    text = _norm(sector)
    for group, keywords in SECTOR_GROUPS:
        for kw in keywords:
            if kw in text:
                return group
    return DEFAULT_GROUP
