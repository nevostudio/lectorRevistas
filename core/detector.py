"""
detector.py
-----------
Identifica anunciantes en las paginas de la revista. Es la pieza "hibrida":

  MODO GRATIS  -> heuristica + extraccion de patrones (web, telefono, email)
                  sobre el texto de cada pagina. No requiere clave ni internet.

  MODO IA      -> envia la imagen de cada pagina a la API de Claude (modelo de
                  vision) y obtiene marca, contacto, web, sector y si la pagina
                  es realmente un anuncio. Requiere ANTHROPIC_API_KEY.

Ambos modos devuelven la misma estructura (lista de Advertiser), de modo que
la capa de informe no necesita saber cual se uso.
"""

from __future__ import annotations

import os
import re
import io
import time
import json
import base64
import math
import hashlib
import copy
from dataclasses import dataclass, field, asdict

from core.checkpoint import atomic_write_json, file_sha256, read_json

try:
    import anthropic
    ANTHROPIC_SDK = True
except ImportError:
    ANTHROPIC_SDK = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Limite de la API de Anthropic: 5 MB por imagen en base64.
# Margen de seguridad: apuntamos a ~4 MB binarios (~5.4 MB base64).
MAX_IMAGE_BYTES = 4_000_000
# Lado mayor recomendado por Anthropic para vision sin perder calidad.
MAX_IMAGE_LONGSIDE = 1568

# Tokens maximos de salida por pliego. Un pliego con muchos anuncios puede
# generar un JSON largo; con 2000 se truncaba ("Unterminated string") y se
# perdia el pliego entero. 8000 da margen de sobra.
MAX_OUTPUT_TOKENS = 8000

# Reintentos ante errores transitorios de la API o JSON irreparable.
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0   # segundos: 2, 4, 8...

# Modelo por defecto y precios publicados por Anthropic por millon de tokens
# (USD). Mantener la tarifa junto al ID evita calcular costes nuevos con la
# tarifa del modelo anterior cuando se vuelva a actualizar.
DEFAULT_AI_MODEL = "claude-sonnet-5-5"
MODEL_PRICING_PER_MTOK = {
    "claude-sonnet-5-5": {
        "input":        2.00,
        "output":      10.00,
        "cache_write":  2.50,   # escritura de cache (TTL 5 min)
        "cache_read":   0.20,
    },
    "claude-sonnet-4-6": {
        "input":        3.00,
        "output":      15.00,
        "cache_write":  3.75,
        "cache_read":   0.30,
    },
}

# Permiten recuperar checkpoints creados antes de restringir el numero de
# pagina al identificador tecnico del PDF. Los completos siguen siendo validos;
# los parciales se recalculan con el contrato nuevo.
AI_CHECKPOINT_VERSION = 2
LEGACY_PROMPT_HASH = (
    "a63e7872d26c9b6b7c4ee177e2a5c09afac7c78116d7aa00f523717a3067ee07"
)
LEGACY_SCHEMA_HASH = (
    "a303e5955ae67755374ce635bbb71746a7552c5673687e8e427690ea6fad94fd"
)


# --------------------------------------------------------------------------- #
# Estructura de datos
# --------------------------------------------------------------------------- #
@dataclass
class Advertiser:
    brand: str
    pages: list[int] = field(default_factory=list)
    website: str = ""
    email: str = ""
    phone: str = ""
    sector: str = ""
    ad_size: str = ""          # "pagina completa", "media pagina"...
    confidence: float = 0.0    # 0..1
    method: str = ""           # "ia" | "heuristica"
    notes: str = ""
    review_flag: str = ""      # razones por las que conviene revisar (vacio = ok)

    def merge(self, other: "Advertiser"):
        """Funde dos detecciones de la misma marca."""
        self.pages = sorted(set(self.pages) | set(other.pages))
        for fld in ("website", "email", "phone", "sector", "ad_size"):
            if not getattr(self, fld) and getattr(other, fld):
                setattr(self, fld, getattr(other, fld))
        self.confidence = max(self.confidence, other.confidence)


# --------------------------------------------------------------------------- #
# Patrones para el modo gratis
# --------------------------------------------------------------------------- #
RE_URL = re.compile(
    r'\b((?:https?://)?(?:www\.)?[a-z0-9][a-z0-9\-]+\.(?:com|es|net|org|eu|'
    r'cat|info|io)(?:\.[a-z]{2})?)\b', re.I)
RE_EMAIL = re.compile(r'\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b', re.I)
# Telefono: 9 digitos (Espana) con separadores opcionales y prefijo opcional.
RE_PHONE = re.compile(
    r'(?<!\d)(\+?\d{1,3}[\s.\-]?)?(\d{3}[\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2}'
    r'|\d{3}[\s.\-]?\d{3}[\s.\-]?\d{3}|\d{9})(?!\d)')

# Palabras que sugieren que una pagina es publicidad y no editorial.
AD_HINTS = ("publicidad", "anuncio", "www.", "solicite informacion",
            "distribuidor oficial", "sello de calidad", "siguenos en")

# Dominios que NO son anunciantes (la propia revista, redes sociales...).
BLOCKLIST_DOMAINS = {
    "proarquitectura.es", "promateriales.com", "facebook.com",
    "twitter.com", "instagram.com", "linkedin.com", "youtube.com",
    "pinterest.com", "wordpress.org", "google.com",
}


# Sufijos de forma juridica que se eliminan al canonizar la marca.
_LEGAL_SUFFIXES = [
    "sociedad limitada", "sociedad anonima",
    "s l u", "s a u", "s l l", "s l", "s a", "s coop",
    "slu", "sau", "sll", "sl", "sa", "sccl", "scoop",
    "gmbh", "srl", "ltd", "inc", "bv", "nv", "spa", "ag",
]

_ACCENTS = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
            "ü": "u", "ñ": "n", "ç": "c", "à": "a", "è": "e"}


def canonical_brand(name: str) -> str:
    """Clave canonica para fusionar la MISMA marca escrita de varias formas.

    Conservadora a proposito: NO une marcas distintas (Simon / SimonElectric
    quedan separadas; de eso se encarga la revision manual). Solo normaliza
    mayusculas, acentos, puntuacion y la forma juridica (S.L., S.A., GmbH...).
    """
    s = (name or "").lower().strip()
    for k, v in _ACCENTS.items():
        s = s.replace(k, v)
    # Puntuacion -> espacio (Roca, S.A. -> roca s a).
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    # Quitar sufijo juridico final (el mas largo que encaje).
    for suf in _LEGAL_SUFFIXES:
        if s.endswith(" " + suf):
            s = s[: -len(suf) - 1].strip()
            break
    # Colapsar espacios sobrantes pero conservarlos (no unimos 'euro perfil'
    # con 'europerfil': eso lo decide la revision).
    return re.sub(r'\s+', ' ', s).strip()


def _brand_from_domain(domain: str) -> str:
    core = domain.lower()
    for pre in ("https://", "http://", "www."):
        core = core.replace(pre, "")
    core = core.split("/")[0].split(".")[0]
    return core.replace("-", " ").title()


# --------------------------------------------------------------------------- #
# MODO GRATIS
# --------------------------------------------------------------------------- #
class HeuristicDetector:
    """Detecta anunciantes solo con el texto. Sin coste, sin internet."""

    @staticmethod
    def _phone_digits(text: str) -> str:
        """Devuelve el primer telefono valido (9 digitos) encontrado."""
        for m in RE_PHONE.finditer(text):
            digits = re.sub(r'\D', '', m.group(0))
            # Quitar prefijo de pais si lo hubiera, quedarnos con 9 digitos.
            if len(digits) > 9:
                digits = digits[-9:]
            if len(digits) == 9 and digits[0] in "6789":
                return m.group(0).strip()
        return ""

    @staticmethod
    def _norm_brand(domain_root: str) -> str:
        """Normaliza la marca a partir del dominio, sin el TLD."""
        return domain_root.split(".")[0].replace("-", " ").strip().lower()

    def detect(self, pages) -> list[Advertiser]:
        found: dict[str, Advertiser] = {}
        for page in pages:
            text = page.text or ""
            low = text.lower()
            is_ad_like = sum(h in low for h in AD_HINTS) >= 1
            page_phone = self._phone_digits(text)
            page_emails = RE_EMAIL.findall(text)

            for m in RE_URL.finditer(text):
                domain = m.group(1).lower()
                root = domain.replace("www.", "").replace(
                    "https://", "").replace("http://", "").split("/")[0]
                if root in BLOCKLIST_DOMAINS:
                    continue
                if any(root.endswith(b) for b in BLOCKLIST_DOMAINS):
                    continue
                # Clave de fusion: el nombre sin TLD (simon.es y
                # simonelectric.com se mantienen separados, pero roca.es y
                # roca.com se funden).
                key = self._norm_brand(root)
                brand = key.title()
                adv = found.get(key) or Advertiser(
                    brand=brand, method="heuristica")
                # Preferimos el dominio mas corto/canonico como web.
                if not adv.website or len(root) < len(adv.website):
                    adv.website = root
                if page.number not in adv.pages:
                    adv.pages.append(page.number)
                if page_emails and not adv.email:
                    adv.email = page_emails[0]
                if page_phone and not adv.phone:
                    adv.phone = page_phone
                adv.confidence = 0.65 if is_ad_like else 0.4
                adv.notes = ("Pagina con aspecto de anuncio."
                             if is_ad_like else
                             "Marca mencionada; revisar si es anuncio.")
                found[key] = adv
        return self._consolidate(sorted(
            found.values(), key=lambda a: (-a.confidence, a.brand)))

    @staticmethod
    def _consolidate(advertisers: list[Advertiser]) -> list[Advertiser]:
        """Funde marcas que aparecen en la misma pagina y cuyo nombre es
        prefijo del otro (p.ej. 'Simon' y 'Simonelectric' en un mismo
        anuncio). Es la red de seguridad del modo gratis."""
        result: list[Advertiser] = []
        for adv in advertisers:
            absorbed = False
            for keep in result:
                same_page = set(adv.pages) & set(keep.pages)
                a, b = adv.brand.lower(), keep.brand.lower()
                similar = a.startswith(b) or b.startswith(a)
                if same_page and similar:
                    # Conservamos el nombre mas corto (suele ser la marca).
                    if len(adv.brand) < len(keep.brand):
                        keep.brand = adv.brand
                        keep.website = adv.website or keep.website
                    keep.merge(adv)
                    keep.notes = (keep.notes +
                                  " (marca consolidada automaticamente)")
                    absorbed = True
                    break
            if not absorbed:
                result.append(adv)
        return result


# --------------------------------------------------------------------------- #
# MODO IA
# --------------------------------------------------------------------------- #
AI_SYSTEM_PROMPT = """Eres un analista experto en publicidad de revistas \
profesionales del sector de arquitectura y construccion. Tu objetivo es \
extraer la lista MAS COMPLETA POSIBLE de anunciantes (marcas que han pagado \
por aparecer en la revista).

Recibes una o dos paginas consecutivas (un pliego) y debes enumerar TODOS \
los anuncios visibles, sea cual sea su tamano. Las revistas de este sector \
suelen tener entre 60 y 120 anunciantes; si estas detectando menos de un \
anuncio por pagina de media probablemente te estes dejando muchos.

EN LA DUDA, INCLUYELO. Es preferible incluir un falso positivo (que se podra \
revisar despues) que dejarse un anunciante real. Reporta la confianza para \
que el usuario pueda filtrar.

Cuenta como anuncio cualquier elemento que cumpla alguno de estos criterios:
1. Un bloque con logotipo de marca destacado + eslogan o frase comercial + \
datos de contacto (web/telefono/email).
2. Un recuadro o ficha con logo + descripcion de producto + datos de contacto, \
aunque ocupe solo 1/4 o 1/8 de la pagina y conviva con contenido editorial.
3. Un banner horizontal/vertical con marca + web (incluso si es solo eso).
4. Una pagina o doble pagina dominada por imagen de marca/producto.
5. PUBLIRREPORTAJES: paginas que parecen articulo pero llevan etiqueta tipo \
"Informacion comercial", "Publirreportaje", "Espacio publicitario", \
"Publicidad", o que tienen logotipo de marca grande + texto laudatorio del \
producto + datos de contacto al final.
6. DIRECTORIOS / GUIAS DE EMPRESAS al final de la revista: cada ficha de \
empresa en esos directorios es un anunciante.
7. Banners patrocinadores en cabecera o pie de pagina.

NO cuentes como anuncio:
- Titular y cuerpo editorial firmados por un redactor de la revista, sobre un \
proyecto u obra (aunque mencione marcas dentro del texto).
- Indice / sumario.
- Editorial / carta del director / staff.
- Portada principal de la revista (el titulo de la revista no es un \
anunciante).
- Fotografias de obras con pie de foto descriptivo, sin logotipo de marca \
destacado ni datos comerciales.

Devuelve SIEMPRE y UNICAMENTE un objeto JSON valido, sin texto adicional ni \
formato markdown:
{
  "anuncios": [
    {
      "marca": "nombre del anunciante",
      "pagina": numero_de_pagina,
      "web": "sitio web si aparece, o cadena vacia",
      "email": "email si aparece, o cadena vacia",
      "telefono": "telefono si aparece, o cadena vacia",
      "sector": "categoria breve del producto/servicio",
      "tamano": "doble pagina|pagina completa|media pagina|cuarto|octavo|banner|ficha|publirreportaje|directorio",
      "confianza": 0.0-1.0
    }
  ]
}

El campo "pagina" debe usar EXCLUSIVAMENTE uno de los identificadores tecnicos \
de pagina indicados en la peticion. Ignora cualquier numero impreso dentro de \
la revista: puede tener un desfase respecto al PDF. Si ocupa dos paginas, usa \
el identificador tecnico de la imagen izquierda. Si no hay anuncios, devuelve \
{"anuncios": []}. Cada anuncio debe tener marca no vacia."""


# El esquema se envia a Structured Outputs. Ademas de evitar JSON truncado o
# con tipos impredecibles, obliga al modelo a completar todos los campos que el
# validador local espera. El validador se conserva como segunda barrera.
AI_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "anuncios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "marca": {
                        "type": "string",
                        "description": "Nombre no vacio del anunciante",
                    },
                    "pagina": {
                        "type": "integer",
                        "description": "Numero de pagina, entero mayor que cero",
                    },
                    "web": {"type": "string"},
                    "email": {"type": "string"},
                    "telefono": {"type": "string"},
                    "sector": {"type": "string"},
                    "tamano": {
                        "type": "string",
                        "enum": [
                            "doble pagina", "pagina completa", "media pagina",
                            "cuarto", "octavo", "banner", "ficha",
                            "publirreportaje", "directorio",
                        ],
                    },
                    "confianza": {
                        "type": "number",
                        "description": "Confianza entre 0.0 y 1.0",
                    },
                },
                "required": [
                    "marca", "pagina", "web", "email", "telefono", "sector",
                    "tamano", "confianza",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["anuncios"],
    "additionalProperties": False,
}


class AIDetector:
    """Detecta anunciantes con el modelo de vision de Claude."""

    def __init__(self, api_key: str | None = None,
                 model: str = DEFAULT_AI_MODEL, progress=None,
                 checkpoint_dir: str | None = None):
        if not ANTHROPIC_SDK:
            raise RuntimeError(
                "El SDK de Anthropic no esta instalado. "
                "Instalalo con: pip install anthropic")
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "Falta la clave de API. Define ANTHROPIC_API_KEY o pasala "
                "en la interfaz.")
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = model
        self._progress = progress or (lambda m: None)
        self.checkpoint_dir = checkpoint_dir

        # Telemetria de la ejecucion en curso.
        self.usage = {"input": 0, "output": 0,
                      "cache_write": 0, "cache_read": 0}
        self.resumed_usage = {"input": 0, "output": 0,
                              "cache_write": 0, "cache_read": 0}
        self.resumed_spreads = 0
        self.failed_spreads: list[list[int]] = []   # pliegos no recuperados
        self.partial_spreads: list[list[int]] = []  # respuesta parcial/invalida
        self.invalid_items: list[dict] = []          # registros IA rechazados

    def log(self, msg: str):
        self._progress(msg)

    # ------------------------------------------------------------------ #
    # Coste
    # ------------------------------------------------------------------ #
    def _add_usage(self, resp):
        """Acumula los tokens de una respuesta para estimar el coste."""
        u = getattr(resp, "usage", None)
        if not u:
            return
        self.usage["input"] += getattr(u, "input_tokens", 0) or 0
        self.usage["output"] += getattr(u, "output_tokens", 0) or 0
        self.usage["cache_write"] += getattr(
            u, "cache_creation_input_tokens", 0) or 0
        self.usage["cache_read"] += getattr(
            u, "cache_read_input_tokens", 0) or 0

    def _cost_for_usage(self, usage: dict) -> float:
        prices = MODEL_PRICING_PER_MTOK.get(
            self.model, MODEL_PRICING_PER_MTOK[DEFAULT_AI_MODEL])
        return sum(usage.get(k, 0) / 1_000_000 * prices[k]
                   for k in prices)

    def estimated_cost_usd(self) -> float:
        return self._cost_for_usage(self.usage)

    def resumed_cost_usd(self) -> float:
        return self._cost_for_usage(self.resumed_usage)

    def new_cost_usd(self) -> float:
        return max(0.0, self.estimated_cost_usd() - self.resumed_cost_usd())

    def cost_summary(self) -> str:
        c = self.estimated_cost_usd()
        resumed = self.resumed_cost_usd()
        prefix = f"Coste estimado: ${c:.3f}"
        if self.resumed_spreads:
            prefix += (f" · reutilizado: ${resumed:.3f} · nuevo: "
                       f"${self.new_cost_usd():.3f}")
        return (prefix + " "
                f"(in {self.usage['input']:,} · out {self.usage['output']:,} "
                f"· cache_w {self.usage['cache_write']:,} "
                f"· cache_r {self.usage['cache_read']:,} tokens)")

    @staticmethod
    def _output_schema(page_nums: list[int]) -> dict:
        """Restringe la pagina a los IDs tecnicos del pliego actual.

        La numeracion impresa suele empezar varias hojas despues de la portada.
        El enum evita que el modelo confunda esa numeracion editorial con el
        indice real del PDF que utiliza el resto del programa.
        """
        schema = copy.deepcopy(AI_OUTPUT_SCHEMA)
        page_schema = schema["properties"]["anuncios"]["items"][
            "properties"]["pagina"]
        page_schema["enum"] = list(page_nums)
        page_schema["description"] = (
            "Identificador tecnico del PDF. Debe ser uno de: "
            + ", ".join(str(number) for number in page_nums)
        )
        return schema

    def _spread_signature(self, spread_pages: list,
                          *, legacy: bool = False) -> str:
        page_nums = [page.number for page in spread_pages]
        if legacy:
            version = 1
            prompt_hash = LEGACY_PROMPT_HASH
            schema_hash = LEGACY_SCHEMA_HASH
        else:
            version = AI_CHECKPOINT_VERSION
            prompt_hash = hashlib.sha256(
                AI_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
            schema_hash = hashlib.sha256(json.dumps(
                self._output_schema(page_nums), sort_keys=True,
                separators=(",", ":")).encode("utf-8")).hexdigest()
        payload = {
            "version": version,
            "model": self.model,
            "prompt": prompt_hash,
            "schema": schema_hash,
            "pages": [{
                "number": page.number,
                "image": file_sha256(page.image_path),
                "text": hashlib.sha256(
                    (page.text or "").encode("utf-8")).hexdigest(),
            } for page in spread_pages],
        }
        return hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()

    def _spread_checkpoint_path(self, signature: str) -> str | None:
        checkpoint_dir = getattr(self, "checkpoint_dir", None)
        if not checkpoint_dir:
            return None
        return os.path.join(checkpoint_dir, f"spread-{signature}.json")

    def _load_spread_checkpoint(self, spread_pages: list,
                                page_nums: list[int]) -> list[Advertiser] | None:
        if not getattr(self, "checkpoint_dir", None):
            return None
        payload = None
        legacy = False
        for is_legacy in (False, True):
            path = self._spread_checkpoint_path(
                self._spread_signature(spread_pages, legacy=is_legacy))
            candidate = read_json(path) if path else None
            expected_version = 1 if is_legacy else AI_CHECKPOINT_VERSION
            if candidate and candidate.get("version") == expected_version:
                # Los checkpoints antiguos parciales incluyen numeros de pagina
                # editoriales corregidos de forma ambigua. Se recalculan.
                if is_legacy and candidate.get("partial"):
                    continue
                payload = candidate
                legacy = is_legacy
                break
        if not payload:
            return None
        advertisers = payload.get("advertisers")
        usage = payload.get("usage")
        if not isinstance(advertisers, list) or not isinstance(usage, dict):
            return None
        try:
            restored = [Advertiser(**item) for item in advertisers]
        except (TypeError, ValueError):
            return None
        for key in self.usage:
            value = usage.get(key, 0)
            if isinstance(value, int) and value >= 0:
                self.usage[key] += value
                self.resumed_usage[key] += value
        if payload.get("partial"):
            self._record_spread(self.partial_spreads, page_nums)
        cached_invalid = payload.get("invalid_items") or []
        if isinstance(cached_invalid, list):
            self.invalid_items.extend(
                item for item in cached_invalid if isinstance(item, dict))
        self.resumed_spreads += 1
        suffix = " (checkpoint anterior valido)" if legacy else ""
        self.log(f"IA: pliego {page_nums} recuperado{suffix}; no genera "
                 "coste nuevo.")
        return restored

    def _save_spread_checkpoint(self, spread_pages: list,
                                advertisers: list[Advertiser],
                                usage: dict, invalid_items: list[dict],
                                partial: bool) -> None:
        if not getattr(self, "checkpoint_dir", None):
            return
        path = self._spread_checkpoint_path(
            self._spread_signature(spread_pages))
        if not path:
            return
        try:
            atomic_write_json(path, {
                "version": AI_CHECKPOINT_VERSION,
                "model": self.model,
                "pages": [page.number for page in spread_pages],
                "advertisers": [asdict(item) for item in advertisers],
                "usage": {key: int(usage.get(key, 0)) for key in self.usage},
                "invalid_items": list(invalid_items),
                "partial": bool(partial),
            })
        except OSError as exc:
            # La respuesta ya se ha pagado y es util: un fallo local al guardar
            # el checkpoint no debe descartarla ni activar el fallback gratis.
            self.log(f"AVISO: no se pudo guardar el checkpoint del pliego "
                     f"{[page.number for page in spread_pages]}: {exc}")

    @staticmethod
    def _encode_image(path: str) -> tuple[str, str]:
        """Codifica la imagen para enviarla a la API de Claude.

        Reescala y recomprime si hace falta para mantenerse por debajo del
        limite de 5 MB de la API y dentro del lado mayor recomendado.
        Devuelve (media_type, base64_data).
        """
        # Si PIL no esta disponible, intentamos enviar el fichero tal cual
        # (puede fallar para imagenes grandes).
        if not PIL_AVAILABLE:
            with open(path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode()
            media = ("image/png" if path.lower().endswith(".png")
                     else "image/jpeg")
            return media, data

        img = Image.open(path)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        # 1) Redimensionar si el lado mayor supera el limite recomendado.
        w, h = img.size
        long_side = max(w, h)
        if long_side > MAX_IMAGE_LONGSIDE:
            scale = MAX_IMAGE_LONGSIDE / long_side
            new_size = (int(w * scale), int(h * scale))
            img = img.resize(new_size, Image.LANCZOS)

        # 2) Comprimir a JPEG, bajando calidad si supera el tamano maximo.
        for quality in (90, 82, 75, 65, 55):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            raw = buf.getvalue()
            if len(raw) <= MAX_IMAGE_BYTES:
                break
        return "image/jpeg", base64.standard_b64encode(raw).decode()

    # ------------------------------------------------------------------ #
    # Llamada robusta a la API
    # ------------------------------------------------------------------ #
    def _system_blocks(self):
        """System prompt como bloque con cache_control para reutilizar el
        prefijo (el prompt es identico en los ~60 pliegos -> cache hit)."""
        return [{
            "type": "text",
            "text": AI_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }]

    def _call_with_retry(self, content, page_nums):
        """Llama a la API con reintentos y backoff. Devuelve (resp, truncated)
        o (None, False) si se agotan los reintentos."""
        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    system=self._system_blocks(),
                    messages=[{"role": "user", "content": content}],
                    output_config={
                        "format": {
                            "type": "json_schema",
                            "schema": self._output_schema(page_nums),
                        },
                    },
                )
                self._add_usage(resp)
                truncated = getattr(resp, "stop_reason", "") == "max_tokens"
                if truncated:
                    self.log(f"IA: pliego {page_nums} devolvio respuesta "
                             f"truncada (intentare reparar el JSON).")
                return resp, truncated
            except Exception as e:  # noqa: BLE001
                last_err = e
                wait = RETRY_BACKOFF_BASE ** attempt
                self.log(f"IA: error en pliego {page_nums} "
                         f"(intento {attempt}/{MAX_RETRIES}): {e}. "
                         f"Reintento en {wait:.0f}s...")
                time.sleep(wait)
        self.log(f"IA: pliego {page_nums} fallo tras {MAX_RETRIES} "
                 f"intentos ({last_err}).")
        return None, False

    @staticmethod
    def _parse_ads_payload(raw: str) -> tuple[list, bool]:
        """Devuelve (anuncios, json_valido).

        `json_valido` permite distinguir una respuesta valida sin anuncios de
        una respuesta rota. Si el JSON esta truncado se rescatan los objetos
        completos, pero el segundo valor queda a False.
        """
        raw = re.sub(r'^```(?:json)?|```$', '', raw, flags=re.M).strip()
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict) or not isinstance(
                    payload.get("anuncios"), list):
                return [], False
            return payload["anuncios"], True
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

        # Rescatar objetos completos de una respuesta truncada.
        objs = []
        stack: list[int] = []
        in_str = False
        esc = False
        for i, ch in enumerate(raw):
            if esc:
                esc = False
                continue
            if ch == "\\" and in_str:
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                stack.append(i)
            elif ch == "}":
                if not stack:
                    continue
                start = stack.pop()
                try:
                    item = json.loads(raw[start:i + 1])
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if isinstance(item, dict) and item.get("marca"):
                    objs.append(item)
        return objs, False

    @staticmethod
    def _parse_ads_json(raw: str) -> list:
        """Extrae la lista de anuncios de la respuesta, reparando JSON
        truncado si hace falta. Devuelve la lista de dicts 'anuncios'."""
        return AIDetector._parse_ads_payload(raw)[0]

    @staticmethod
    def _clean_text(value, *, required: bool = False) -> tuple[str, bool]:
        """Normaliza texto del modelo y devuelve (valor, valido)."""
        if value is None:
            return "", not required
        if isinstance(value, str):
            value = value.strip()
            return value, bool(value) if required else True
        if not required and isinstance(value, (int, float)) \
                and not isinstance(value, bool):
            return str(value).strip(), True
        return "", False

    @staticmethod
    def _clean_confidence(value) -> tuple[float, bool]:
        """Valida 0..1 preservando el cero; nunca inventa una confianza alta."""
        if isinstance(value, bool) or value is None:
            return 0.0, False
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0, False
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            return 0.0, False
        return confidence, True

    @staticmethod
    def _record_spread(target: list[list[int]], page_nums: list[int]):
        if page_nums not in target:
            target.append(list(page_nums))

    def _analyze_spread(self, spread_pages: list) -> list[Advertiser]:
        """Analiza un pliego de 1 o 2 paginas consecutivas y devuelve la lista
        de anunciantes detectados en cualquiera de ellas."""
        content: list = []
        page_nums = [p.number for p in spread_pages]
        cached = self._load_spread_checkpoint(spread_pages, page_nums)
        if cached is not None:
            return cached

        usage_before = dict(self.usage)
        invalid_start = len(self.invalid_items)

        def finish(result: list[Advertiser]) -> list[Advertiser]:
            spread_usage = {
                key: self.usage[key] - usage_before[key]
                for key in self.usage
            }
            self._save_spread_checkpoint(
                spread_pages,
                result,
                spread_usage,
                self.invalid_items[invalid_start:],
                page_nums in self.partial_spreads,
            )
            return result

        for p in spread_pages:
            media, data = self._encode_image(p.image_path)
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": media, "data": data}})

        text_support = "\n\n".join(
            f"--- Pagina {p.number} (texto):\n{(p.text or '')[:1200]}"
            for p in spread_pages
        )
        if len(spread_pages) == 2:
            instr = (f"Analiza este pliego de la revista. La primera imagen "
                     f"es la pagina {page_nums[0]} (izquierda) y la segunda "
                     f"la pagina {page_nums[1]} (derecha). Enumera TODOS los "
                     f"anuncios presentes en ambas paginas, indicando para "
                     f"cada uno en que pagina aparece.")
        else:
            instr = (f"Analiza la pagina {page_nums[0]} de la revista y "
                     f"enumera TODOS los anuncios presentes (puede haber "
                     f"varios, de cualquier tamano).")
        content.append({"type": "text",
                        "text": f"{instr}\n\nTexto detectado (apoyo):\n"
                                f"{text_support}"})

        resp, truncated = self._call_with_retry(content, page_nums)
        if resp is None:
            self._record_spread(self.failed_spreads, page_nums)
            return []

        raw = "".join(b.text for b in resp.content
                      if getattr(b, "type", "") == "text").strip()
        items, valid_payload = self._parse_ads_payload(raw)
        if truncated or not valid_payload:
            self._record_spread(self.partial_spreads, page_nums)
        if not items:
            if not valid_payload:
                self.log(f"IA: pliego {page_nums} sin JSON valido.")
            return finish([])

        out: list[Advertiser] = []
        valid_pages = set(page_nums)
        for item in items:
            if not isinstance(item, dict):
                self.invalid_items.append({"pages": page_nums,
                                           "reason": "registro no es objeto"})
                self._record_spread(self.partial_spreads, page_nums)
                continue
            brand, brand_ok = self._clean_text(item.get("marca"), required=True)
            if not brand_ok:
                self.invalid_items.append({"pages": page_nums,
                                           "reason": "marca invalida"})
                self._record_spread(self.partial_spreads, page_nums)
                continue
            item_partial = False
            try:
                page_value = item.get("pagina")
                pg = int(page_value) if page_value is not None else page_nums[0]
            except (TypeError, ValueError):
                pg = page_nums[0]
                item_partial = True
            if pg not in valid_pages:
                pg = page_nums[0]
                item_partial = True

            fields = {}
            for source, target in (("web", "website"), ("email", "email"),
                                   ("telefono", "phone"), ("sector", "sector"),
                                   ("tamano", "ad_size")):
                fields[target], valid = self._clean_text(item.get(source))
                item_partial = item_partial or not valid
            confidence, confidence_ok = self._clean_confidence(
                item.get("confianza"))
            item_partial = item_partial or not confidence_ok
            if item_partial:
                self._record_spread(self.partial_spreads, page_nums)
                self.invalid_items.append({"pages": page_nums,
                                           "brand": brand,
                                           "reason": "campos corregidos"})
            out.append(Advertiser(
                brand=brand,
                pages=[pg],
                website=fields["website"],
                email=fields["email"],
                phone=fields["phone"],
                sector=fields["sector"],
                ad_size=fields["ad_size"],
                confidence=confidence,
                method="ia",
                notes=("Detectado por analisis visual con IA."
                       if not item_partial else
                       "Detectado por IA; revisar campos incompletos."),
            ))
        return finish(out)

    @staticmethod
    def _build_spreads(pages: list) -> list[list]:
        """Agrupa paginas en pliegos. La portada (pagina 1) va sola; despues
        se emparejan 2-3, 4-5, 6-7... Si la ultima queda suelta, va sola."""
        if not pages:
            return []
        spreads = [[pages[0]]]
        i = 1
        while i < len(pages):
            if i + 1 < len(pages):
                spreads.append([pages[i], pages[i + 1]])
                i += 2
            else:
                spreads.append([pages[i]])
                i += 1
        return spreads

    def detect(self, pages) -> list[Advertiser]:
        merged: dict[str, Advertiser] = {}
        spreads = self._build_spreads(pages)
        for idx, spread in enumerate(spreads, 1):
            nums = "+".join(str(p.number) for p in spread)
            self.log(f"IA analizando pliego {idx}/{len(spreads)} "
                     f"(pagina {nums})...")
            advs = self._analyze_spread(spread)
            for adv in advs:
                key = canonical_brand(adv.brand) or adv.brand.lower().strip()
                if key in merged:
                    keep = merged[key]
                    # Adoptar el nombre mas corto/limpio como display
                    # (suele ser la marca sin sufijo juridico).
                    if len(adv.brand) < len(keep.brand):
                        keep.brand = adv.brand
                    keep.merge(adv)
                else:
                    merged[key] = adv

        # Resumen de coste de la ejecucion.
        self.log(self.cost_summary())

        # Aviso destacado si algun pliego no se pudo analizar (sin perdidas
        # silenciosas: el usuario sabe que paginas revisar a mano).
        if self.failed_spreads:
            paginas = ", ".join(
                "+".join(str(n) for n in fs) for fs in self.failed_spreads)
            self.log(f"AVISO: {len(self.failed_spreads)} pliego(s) no "
                     f"analizados (paginas {paginas}). Revisar esas paginas "
                     f"a mano: puede haber anunciantes sin detectar.")
        if self.partial_spreads:
            paginas = ", ".join(
                "+".join(str(n) for n in fs) for fs in self.partial_spreads)
            self.log(f"AVISO: respuesta parcial o invalida en paginas "
                     f"{paginas}. Revisar antes de exportar.")

        return sorted(merged.values(),
                      key=lambda a: (-a.confidence, a.brand))


# --------------------------------------------------------------------------- #
# Orquestador hibrido
# --------------------------------------------------------------------------- #
def detect_advertisers(pages, use_ai: bool = False,
                       api_key: str | None = None,
                       progress=None,
                       telemetry: dict | None = None,
                       checkpoint_dir: str | None = None
                       ) -> tuple[list[Advertiser], str]:
    """
    Devuelve (lista_anunciantes, modo_usado).

    Si use_ai es True intenta el modo IA; si falla, cae al modo gratis.
    Si se pasa un dict 'telemetry', se rellena con coste y pliegos fallidos
    de la ejecucion IA (para que el informe lo pueda mostrar).
    """
    progress = progress or (lambda m: None)
    if use_ai:
        try:
            det = AIDetector(api_key=api_key, progress=progress,
                             checkpoint_dir=checkpoint_dir)
            result = det.detect(pages)
            if telemetry is not None:
                telemetry["model"] = det.model
                telemetry["cost_usd"] = det.estimated_cost_usd()
                telemetry["new_cost_usd"] = det.new_cost_usd()
                telemetry["resumed_cost_usd"] = det.resumed_cost_usd()
                telemetry["resumed_spreads"] = det.resumed_spreads
                telemetry["usage"] = dict(det.usage)
                telemetry["failed_spreads"] = list(det.failed_spreads)
                telemetry["partial_spreads"] = list(det.partial_spreads)
                telemetry["invalid_items"] = list(det.invalid_items)
            return result, "ia"
        except Exception as e:  # noqa: BLE001
            progress(f"Modo IA no disponible ({e}). Usando modo gratis.")
            if telemetry is not None:
                telemetry["fallback_reason"] = str(e)
    result = HeuristicDetector().detect(pages)
    return result, "heuristica"


def advertisers_to_dicts(advertisers: list[Advertiser]) -> list[dict]:
    return [asdict(a) for a in advertisers]


# --------------------------------------------------------------------------- #
# Auto-flag de casos dudosos para revision humana
# --------------------------------------------------------------------------- #
def _norm(s: str) -> str:
    """Normaliza para comparar marcas: minuscula, sin espacios ni acentos."""
    s = (s or "").lower().strip()
    s = re.sub(r'[\s\-_.]+', '', s)
    # Sustituciones basicas de acentos (sin importar unicodedata).
    repl = {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ü":"u","ñ":"n"}
    for k, v in repl.items():
        s = s.replace(k, v)
    return s


def mark_for_review(advertisers: list[Advertiser],
                     magazine_title: str = "") -> int:
    """Anota los anunciantes que conviene revisar a mano y devuelve cuantos.

    Reglas (acumulables, se unen con coma):
      - low_conf : confianza < 0.70
      - magazine : la marca coincide con el nombre de la revista
      - short    : marca con menos de 3 caracteres alfanumericos
      - weird    : marca con caracteres raros (no alfanumericos ni espacios)
      - variant  : existe otra marca que es prefijo/sufijo (Simon/Simonelectric)
    """
    mag_n = _norm(magazine_title)
    # Indice rapido por marca normalizada para detectar variantes.
    norms = [(a, _norm(a.brand)) for a in advertisers]

    flagged = 0
    for a, an in norms:
        reasons: list[str] = []

        if a.confidence < 0.70:
            reasons.append("low_conf")

        if mag_n and an and (an == mag_n or an in mag_n or mag_n in an):
            reasons.append("magazine")

        alnum = re.sub(r'[^a-z0-9]', '', an)
        if len(alnum) < 3:
            reasons.append("short")

        # caracteres raros: el nombre original tiene simbolos que no sean
        # letras, digitos, espacios, &, ' o -.
        if re.search(r'[^\w\s&\'\-\.]', a.brand or "", flags=re.UNICODE):
            reasons.append("weird")

        # Variantes: otra marca cuyo nombre normalizado sea prefijo/sufijo
        # del actual (y distinto).
        for b, bn in norms:
            if b is a or not bn:
                continue
            if an != bn and (an.startswith(bn) or bn.startswith(an)):
                reasons.append("variant")
                break

        if reasons:
            # Mantener orden estable y sin duplicados.
            seen = []
            for r in reasons:
                if r not in seen:
                    seen.append(r)
            a.review_flag = ",".join(seen)
            flagged += 1
        else:
            a.review_flag = ""
    return flagged


REVIEW_REASONS_LABEL = {
    "low_conf": "Confianza baja",
    "magazine": "Coincide con el nombre de la revista",
    "short":    "Nombre demasiado corto",
    "weird":    "Caracteres extranos en el nombre",
    "variant":  "Posible variante de otra marca",
    "partial_analysis": "Procede de un analisis parcial",
}


def review_flag_label(flag: str) -> str:
    """Convierte 'low_conf,variant' en 'Confianza baja · Posible variante...'."""
    if not flag:
        return ""
    parts = [REVIEW_REASONS_LABEL.get(p, p) for p in flag.split(",") if p]
    return " · ".join(parts)
