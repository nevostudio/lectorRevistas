"""Persistencia local para reanudar descargas, paginas y analisis.

Los trabajos viven en ``.magazine_work`` (excluido de Git). El identificador
se deriva de la URL o del contenido del PDF, nunca de la clave de API. Todos
los JSON se publican de forma atomica para sobrevivir a un cierre inesperado.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from urllib.parse import urlsplit, urlunsplit


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_WORK_ROOT = os.path.join(_PROJECT_ROOT, ".magazine_work")
CHECKPOINT_VERSION = 1


def atomic_write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = f"{path}.{uuid.uuid4().hex}.tmp"
    try:
        with open(temp, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def read_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as stream:
            payload = json.load(stream)
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    # El fragmento solo representa estado visual del lector. Conservamos el
    # query porque puede identificar una edicion o recurso distinto.
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                       parts.path, parts.query, ""))


def _safe_relative(workdir: str, path: str) -> str:
    absolute = os.path.abspath(path)
    root = os.path.abspath(workdir)
    if os.path.commonpath([absolute, root]) != root:
        raise ValueError("El archivo del checkpoint queda fuera del trabajo.")
    return os.path.relpath(absolute, root)


def _resolve_relative(workdir: str, value: str | None) -> str | None:
    if not value:
        return None
    candidate = os.path.abspath(os.path.join(workdir, value))
    root = os.path.abspath(workdir)
    if os.path.commonpath([candidate, root]) != root:
        return None
    return candidate


class JobWorkspace:
    """Carpeta estable de una revista y sus checkpoints."""

    def __init__(self, *, url: str | None = None,
                 pdf_path: str | None = None, resume: bool = True,
                 root: str | None = None):
        if pdf_path and os.path.isfile(pdf_path):
            identity = "pdf:" + file_sha256(pdf_path)
            self.source_kind = "pdf"
        elif url:
            identity = "url:" + _normalise_url(url)
            self.source_kind = "url"
        else:
            raise ValueError("Hay que indicar una URL o un PDF local.")

        base_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        self.job_id = base_id if resume else f"{base_id}-{uuid.uuid4().hex[:8]}"
        self.root = os.path.abspath(root or DEFAULT_WORK_ROOT)
        self.workdir = os.path.join(self.root, self.job_id)
        self.resume = bool(resume)
        self.source_file = os.path.join(self.workdir, "source.json")
        self.analysis_dir = os.path.join(self.workdir, "analysis")
        os.makedirs(self.workdir, exist_ok=True)

    def copy_local_pdf(self, source_path: str) -> str:
        target = os.path.join(self.workdir, "source.pdf")
        if not os.path.isfile(target) or \
                os.path.getsize(target) != os.path.getsize(source_path):
            temp = target + ".copying"
            try:
                shutil.copy2(source_path, temp)
                os.replace(temp, target)
            finally:
                if os.path.exists(temp):
                    os.remove(temp)
        return target

    def save_source(self, *, kind: str, pdf_path: str | None,
                    image_paths: list[str], page_numbers: list[int],
                    page_manifest: list[dict], expected_pages: int | None,
                    viewer: str | None, notes: list[str]) -> None:
        payload = {
            "version": CHECKPOINT_VERSION,
            "kind": kind,
            "pdf_path": (_safe_relative(self.workdir, pdf_path)
                         if pdf_path else None),
            "image_paths": [
                _safe_relative(self.workdir, path) for path in image_paths
            ],
            "page_numbers": list(page_numbers),
            "page_manifest": list(page_manifest),
            "expected_pages": expected_pages,
            "viewer": viewer,
        }
        atomic_write_json(self.source_file, payload)

    def load_source(self) -> dict | None:
        if not self.resume:
            return None
        payload = read_json(self.source_file)
        if not payload or payload.get("version") != CHECKPOINT_VERSION:
            return None
        kind = payload.get("kind")
        pdf_path = _resolve_relative(self.workdir, payload.get("pdf_path"))
        image_paths = [
            _resolve_relative(self.workdir, value)
            for value in (payload.get("image_paths") or [])
        ]
        if kind == "pdf":
            if not pdf_path or not os.path.isfile(pdf_path):
                return None
        elif kind == "images":
            if not image_paths or any(
                    not path or not os.path.isfile(path)
                    for path in image_paths):
                return None
        else:
            return None
        return {
            "kind": kind,
            "pdf_path": pdf_path,
            "image_paths": image_paths,
            "page_numbers": list(payload.get("page_numbers") or []),
            "page_manifest": list(payload.get("page_manifest") or []),
            "expected_pages": payload.get("expected_pages"),
            "viewer": payload.get("viewer"),
            "notes": [],
        }
