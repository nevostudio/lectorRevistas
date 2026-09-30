"""Comprobacion de integridad de la revista antes de analizarla.

Esta capa no detecta anunciantes. Comprueba que la entrada normalizada tenga
paginas legibles, numeracion coherente y, cuando la fuente declara un total,
que se hayan obtenido todas. Su resultado se puede guardar tal cual en los
metadatos del informe.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


@dataclass
class SourceCheck:
    status: str
    source_type: str
    viewer: str
    expected_pages: int | None
    obtained_pages: int
    completeness_known: bool
    missing_pages: list[int] = field(default_factory=list)
    failed_pages: list[int] = field(default_factory=list)
    unreadable_pages: list[int] = field(default_factory=list)
    duplicate_numbers: list[int] = field(default_factory=list)
    low_resolution_pages: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == "lista"

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        label = self.source_type
        if self.viewer:
            label += f" ({self.viewer})"
        if self.expected_pages is None:
            pages = f"{self.obtained_pages} paginas; total no publicado"
        else:
            pages = f"{self.obtained_pages}/{self.expected_pages} paginas"
        return f"{label} · {pages} · {self.status}"


def _positive_int(value) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _find_duplicates(numbers: list[int]) -> list[int]:
    seen = set()
    duplicates = set()
    for number in numbers:
        if number in seen:
            duplicates.add(number)
        seen.add(number)
    return sorted(duplicates)


def _inspect_image(path: str) -> tuple[str | None, bool]:
    """Devuelve (error, baja_resolucion) sin modificar la imagen."""
    if not path or not os.path.isfile(path):
        return "archivo ausente", False
    try:
        if os.path.getsize(path) <= 0:
            return "archivo vacio", False
        if not PIL_AVAILABLE:
            return None, False
        with Image.open(path) as image:
            width, height = image.size
            low_resolution = max(width, height) < 800
            image.verify()
        return None, low_resolution
    except Exception as exc:  # noqa: BLE001
        return type(exc).__name__, False


def check_source(*, kind: str, pages: list, page_manifest: list[dict] | None,
                 viewer: str | None = None,
                 expected_pages: int | None = None,
                 local_pdf: bool = False) -> SourceCheck:
    """Comprueba la fuente ya descargada y las paginas ya normalizadas."""
    manifest = page_manifest or []
    numbers = [_positive_int(getattr(page, "number", None)) for page in pages]
    page_numbers = [number for number in numbers if number is not None]
    obtained = len(pages)
    duplicate_numbers = _find_duplicates(page_numbers)

    manifest_ok = {
        number for item in manifest
        if item.get("status") == "ok"
        for number in [_positive_int(item.get("page_number"))]
        if number is not None
    }
    failed_pages = sorted({
        number for item in manifest
        if item.get("status") == "failed"
        for number in [_positive_int(item.get("page_number"))]
        if number is not None and number not in manifest_ok
    })

    declared_expected = _positive_int(expected_pages)
    expected = declared_expected
    completeness_known = kind == "pdf" or declared_expected is not None
    if kind == "pdf":
        # PyMuPDF solo devuelve la lista tras recorrer el documento completo.
        expected = obtained
    elif expected is None:
        declared_numbers = [
            number for item in manifest
            for number in [_positive_int(item.get("page_number"))]
            if number is not None
        ]
        # Si la captura empieza en 1, el mayor numero observado permite
        # detectar huecos internos aunque el visor no publique el total.
        if declared_numbers and min(declared_numbers) == 1:
            expected = max(declared_numbers)

    unreadable_pages = []
    low_resolution_pages = []
    for index, page in enumerate(pages, 1):
        number = _positive_int(getattr(page, "number", None)) or index
        error, low_resolution = _inspect_image(
            getattr(page, "image_path", ""))
        if error:
            unreadable_pages.append(number)
        elif low_resolution:
            low_resolution_pages.append(number)

    missing_pages = []
    if expected is not None:
        missing_pages = sorted(set(range(1, expected + 1)) - set(page_numbers))

    source_type = "PDF local" if local_pdf else (
        "PDF" if kind == "pdf" else "Lector por imagenes")
    blocking_reasons = []
    if not pages:
        blocking_reasons.append("No se obtuvo ninguna pagina procesable.")
    if missing_pages:
        blocking_reasons.append(
            f"Faltan {len(missing_pages)} pagina(s): "
            + ", ".join(str(number) for number in missing_pages[:20])
            + ("..." if len(missing_pages) > 20 else ""))
    if failed_pages:
        blocking_reasons.append(
            f"Fallaron {len(failed_pages)} descarga(s) de pagina.")
    if unreadable_pages:
        blocking_reasons.append(
            f"Hay {len(unreadable_pages)} imagen(es) ausentes o danadas.")
    if duplicate_numbers:
        blocking_reasons.append(
            "La numeracion contiene paginas duplicadas: "
            + ", ".join(str(number) for number in duplicate_numbers))

    warnings = []
    if not completeness_known:
        warnings.append(
            "El lector no publica el total de paginas; se valida lo obtenido.")
    if low_resolution_pages:
        warnings.append(
            f"{len(low_resolution_pages)} pagina(s) tienen baja resolucion.")

    return SourceCheck(
        status="incompleta" if blocking_reasons else "lista",
        source_type=source_type,
        viewer=viewer or "",
        expected_pages=expected,
        obtained_pages=obtained,
        completeness_known=completeness_known,
        missing_pages=missing_pages,
        failed_pages=failed_pages,
        unreadable_pages=sorted(set(unreadable_pages)),
        duplicate_numbers=duplicate_numbers,
        low_resolution_pages=sorted(set(low_resolution_pages)),
        warnings=warnings,
        blocking_reasons=blocking_reasons,
    )
