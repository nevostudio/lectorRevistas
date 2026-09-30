"""
webapp.py
---------
Interfaz web de NEVO · Extractor de Anunciantes.

Reutiliza intacto todo el backend (pipeline.py + core/*) y le pone delante la
interfaz rediseñada que vive en la carpeta web/. No añade dependencias: usa
solo la libreria estandar (http.server). Al lanzarlo, abre la app en una
ventana nativa si esta disponible pywebview; si no, en el navegador.

Lanzar con:  python webapp.py
"""

from __future__ import annotations

import os
import io
import sys
import json
import time
import uuid
import socket
import tempfile
import threading
import webbrowser
import mimetypes
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import run_extraction, export_results          # noqa: E402
from core.detector import review_flag_label                  # noqa: E402
from core import config                                       # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, "web")
OUT_DIR = os.path.join(ROOT, "output")

# --------------------------------------------------------------------------- #
# Estado global del trabajo de extraccion (app local de un solo usuario)
# --------------------------------------------------------------------------- #
_LOCK = threading.Lock()
_EXPORT_LOCK = threading.Lock()
JOB = {
    "state": "idle",        # idle | running | done | error
    "step": -1,             # 0..6 fase actual; 7 = todo hecho
    "messages": [],         # log en vivo
    "error": None,
    "result": None,         # dict de run_extraction (advertisers, pages, meta)
    "summary": {"total": 0, "flagged": 0},
    "exported": False,
    "export_response": None,
    "job_id": None,
}
_UPLOADS: dict[str, str] = {}   # token -> ruta del PDF subido


def _reset_job():
    with _LOCK:
        job_id = uuid.uuid4().hex
        JOB.update(state="running", step=0, messages=[], error=None,
                   result=None, summary={"total": 0, "flagged": 0},
                   exported=False, export_response=None, job_id=job_id)
        return job_id


def _start_job() -> str | None:
    """Comprueba y crea un trabajo bajo el mismo bloqueo."""
    with _LOCK:
        if JOB["state"] in ("running", "exporting"):
            return None
        job_id = uuid.uuid4().hex
        JOB.update(state="running", step=0, messages=[], error=None,
                   result=None, summary={"total": 0, "flagged": 0},
                   exported=False, export_response=None, job_id=job_id)
        return job_id


def _phase_for(msg: str, current: int) -> int:
    """Mapea (de forma robusta y solo-creciente) un mensaje de progreso del
    backend a una de las 7 fases visuales del front."""
    m = (msg or "").lower()
    step = current

    def up(n):
        nonlocal step
        if n > step:
            step = n

    if "iniciando" in m:
        up(0)
    if any(k in m for k in ("descarg", "flipbook", "viewer", "playwright",
                            "pdf local", "obten", "navegad")):
        up(1)
    if any(k in m for k in ("pagina", "página", "render", "imagen", "ocr")):
        up(2)
    if any(k in m for k in ("comprobacion previa", "comprobación previa",
                            "fuente preparada", "fuente es parcial")):
        up(3)
    detection_started = not any(
        k in m for k in ("ia no iniciada", "no se ha consumido credito"))
    if detection_started and any(
            k in m for k in ("analiz", "pliego", "claude", "detect",
                             "heurist", "heuríst")):
        up(4)
    if "anunciantes detectados" in m:
        up(5)
    if any(k in m for k in ("marcad", "revision", "revisión", "dedup",
                            "consolid")):
        up(6)
    if "terminado" in m:
        up(6)
    return step


def _progress(msg: str):
    with _LOCK:
        JOB["messages"].append(msg)
        if len(JOB["messages"]) > 250:
            JOB["messages"] = JOB["messages"][-250:]
        JOB["step"] = _phase_for(msg, JOB["step"])


def _adv_to_item(a, index: int) -> dict:
    return {
        "index": index,
        "brand": getattr(a, "brand", "") or "",
        "sector": getattr(a, "sector", "") or "",
        "website": getattr(a, "website", "") or "",
        "email": getattr(a, "email", "") or "",
        "phone": getattr(a, "phone", "") or "",
        "ad_size": getattr(a, "ad_size", "") or "",
        "confidence": float(getattr(a, "confidence", 0) or 0),
        "method": getattr(a, "method", "") or "",
        "pages": list(getattr(a, "pages", []) or []),
        "review_flag": getattr(a, "review_flag", "") or "",
        "review_label": review_flag_label(getattr(a, "review_flag", "") or ""),
    }


# --------------------------------------------------------------------------- #
# Worker de extraccion
# --------------------------------------------------------------------------- #
def _extract_worker(params: dict, job_id: str | None = None):
    url = (params.get("url") or "").strip() or None
    mode = params.get("mode") or "gratis"
    use_ai = mode == "ia"
    given_key = (params.get("api_key") or "").strip()
    api_key = given_key or config.api_key() or None
    remember = bool(params.get("remember"))

    pdf_path = None
    token = params.get("pdf_token")
    if token and token in _UPLOADS and os.path.exists(_UPLOADS[token]):
        pdf_path = _UPLOADS[token]

    try:
        # Un fallo guardando preferencias no puede dejar el trabajo bloqueado.
        try:
            if url:
                config.set_last_url(url)
            if use_ai:
                if remember and given_key:
                    config.remember_api_key(given_key)
                elif not remember:
                    config.forget_api_key()
        except OSError as e:
            _progress(f"AVISO: no se pudieron guardar las preferencias: {e}")

        result = run_extraction(
            url=url, pdf_path=pdf_path, use_ai=use_ai,
            api_key=api_key, run_ocr=True, progress=_progress,
        )
        if not result.get("ok"):
            with _LOCK:
                if job_id is None or JOB.get("job_id") == job_id:
                    JOB.update(state="error", result=result,
                               error=result.get("error", "Extracción fallida"))
            return
        advertisers = result["advertisers"]
        flagged = [a for a in advertisers if getattr(a, "review_flag", "")]
        if result.get("analysis_status") == "parcial" and not advertisers:
            with _LOCK:
                if job_id is None or JOB.get("job_id") == job_id:
                    JOB.update(
                        state="error", result=result,
                        error=("El análisis quedó parcial y no produjo "
                               "anunciantes. Revisa las páginas pendientes."),
                    )
            return
        with _LOCK:
            if job_id is not None and JOB.get("job_id") != job_id:
                return
            JOB["result"] = result
            JOB["summary"] = {
                "total": len(advertisers),
                "flagged": len(flagged),
                "analysis_status": result.get("analysis_status", "completo"),
            }
            JOB["step"] = 7
            JOB["state"] = "done"
        # Si no hay dudosos, exportamos directamente (como la app de escritorio).
        if not flagged and result.get("analysis_status") == "completo":
            _do_export([], job_id=job_id)
    except Exception as e:  # noqa: BLE001
        with _LOCK:
            if job_id is None or JOB.get("job_id") == job_id:
                JOB.update(state="error", error=str(e))


# --------------------------------------------------------------------------- #
# Exportacion (aplica decisiones de revision y genera entregables)
# --------------------------------------------------------------------------- #
def _do_export(decisions: list, job_id: str | None = None) -> dict:
    """Exporta una sola vez por trabajo; reintentos devuelven lo ya creado."""
    with _EXPORT_LOCK:
        with _LOCK:
            current_id = JOB.get("job_id")
            if job_id is not None and current_id != job_id:
                raise RuntimeError("El trabajo de revisión ya no está activo.")
            if JOB.get("exported") and JOB.get("export_response"):
                return copy.deepcopy(JOB["export_response"])
            result = JOB.get("result")
            if not result:
                raise RuntimeError("No hay una extracción que exportar.")
            advertisers = copy.deepcopy(result["advertisers"])
            meta = copy.deepcopy(result["meta"])
            meta["export_id"] = current_id or uuid.uuid4().hex
            JOB["state"] = "exporting"

        dropped = set()
        for d in decisions:
            i = d.get("index")
            if not isinstance(i, int) or not (0 <= i < len(advertisers)):
                continue
            a = advertisers[i]
            fields = d.get("fields") or {}
            for k in ("brand", "sector", "website", "email", "phone", "ad_size"):
                if k in fields and fields[k] is not None:
                    setattr(a, k, str(fields[k]).strip())
            if d.get("state") == "drop":
                dropped.add(i)

        kept = [a for i, a in enumerate(advertisers) if i not in dropped]
        kept.sort(key=lambda x: (-float(getattr(x, "confidence", 0) or 0),
                                 (getattr(x, "brand", "") or "").lower()))

        try:
            os.makedirs(OUT_DIR, exist_ok=True)
            paths = export_results(kept, meta, OUT_DIR, progress=_progress)
            response = {"paths": paths, "n": len(kept), "job_id": current_id}
            with _LOCK:
                if JOB.get("job_id") != current_id:
                    raise RuntimeError(
                        "El trabajo cambió durante la exportación.")
                JOB["result"]["advertisers"] = kept
                JOB["result"]["meta"] = meta
                JOB["exported"] = True
                JOB["export_response"] = copy.deepcopy(response)
                JOB["state"] = "done"
        except Exception:
            with _LOCK:
                if JOB.get("job_id") == current_id:
                    JOB["state"] = "done"
            raise
        html_path = paths.get("html")
        if html_path:
            try:
                webbrowser.open("file://" + os.path.abspath(html_path))
            except Exception:  # noqa: BLE001
                pass
        return response


# --------------------------------------------------------------------------- #
# Biblioteca
# --------------------------------------------------------------------------- #
def _library_issues() -> list:
    from core.library import Library
    with Library() as lib:
        rows = lib.list_issues()
    # prev = nº de anunciantes del número anterior (mismo título, más antiguo).
    by_title: dict[str, list] = {}
    for r in sorted(rows, key=lambda r: (r.get("fecha_analisis") or "")):
        by_title.setdefault(r.get("titulo") or "Revista", []).append(r)
    prev_map = {}
    for _title, lst in by_title.items():
        for i, r in enumerate(lst):
            prev_map[r["id"]] = lst[i - 1]["n_anunciantes"] if i > 0 else None

    out = []
    for r in rows:
        numero = (r.get("numero") or "").strip()
        paginas = r.get("paginas")
        modo = (r.get("modo") or "").strip()
        sub_bits = []
        if paginas:
            sub_bits.append(f"{paginas} págs")
        if modo:
            sub_bits.append(modo)
        date = (r.get("fecha_analisis") or "")[:16].replace("T", " ")
        out.append({
            "id": r["id"],
            "n": "#" + (numero if numero else str(r["id"])),
            "name": r.get("titulo") or "Revista",
            "sub": " · ".join(sub_bits),
            "count": r.get("n_anunciantes") or 0,
            "prev": prev_map.get(r["id"]),
            "date": date,
        })
    return out


def _library_compare(id_a: int, id_b: int) -> dict:
    import datetime
    from core.library import Library
    from core.compare_report import export_comparison_html
    with Library() as lib:
        cmp = lib.compare_issues(id_a, id_b)
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(OUT_DIR, f"comparativa_{stamp}.html")
    export_comparison_html(cmp, path)
    try:
        webbrowser.open("file://" + os.path.abspath(path))
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "path": path}


def _library_view(issue_id: int) -> dict:
    from core.library import Library
    with Library() as lib:
        ads = lib.get_advertisers(issue_id)
    return {"advertisers": [
        {"brand": a.get("brand", ""), "sector": a.get("sector", "")}
        for a in ads]}


# --------------------------------------------------------------------------- #
# Subida de PDF (multipart/form-data minimo, sin dependencias)
# --------------------------------------------------------------------------- #
def _parse_multipart_pdf(body: bytes, content_type: str) -> str | None:
    if "boundary=" not in content_type:
        return None
    boundary = content_type.split("boundary=", 1)[1].strip().strip('"')
    sep = ("--" + boundary).encode()
    for part in body.split(sep):
        if b"Content-Disposition" not in part:
            continue
        head, _, data = part.partition(b"\r\n\r\n")
        if b'name="pdf"' not in head:
            continue
        data = data.rstrip(b"\r\n")
        if not data:
            continue
        fd, path = tempfile.mkstemp(suffix=".pdf", prefix="nevo_")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path
    return None


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "NEVO/1.0"

    def log_message(self, *_a):  # silenciar logging por request
        pass

    # ---- helpers ---- #
    def _json(self, obj, code=200):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _send_file(self, path: str):
        if not os.path.isfile(path):
            self.send_error(404, "No encontrado")
            return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # ---- GET ---- #
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "":
            return self._send_file(os.path.join(WEB_DIR, "index.html"))

        if path == "/api/config":
            return self._json({
                "last_url": config.last_url(),
                "has_key": bool(config.api_key()),
            })

        if path == "/api/status":
            with _LOCK:
                msgs = JOB["messages"][-60:]
                return self._json({
                    "state": JOB["state"],
                    "step": JOB["step"],
                    "message": msgs[-1] if msgs else "",
                    "messages": msgs,
                    "summary": JOB["summary"],
                    "error": JOB["error"],
                    "job_id": JOB["job_id"],
                })

        if path == "/api/review":
            with _LOCK:
                result = JOB.get("result")
                exported = JOB.get("exported")
                job_id = JOB.get("job_id")
            items = []
            meta = {}
            if result and not exported:
                meta = result.get("meta", {}) or {}
                include_all = result.get("analysis_status") == "parcial"
                for i, a in enumerate(result["advertisers"]):
                    if include_all or getattr(a, "review_flag", ""):
                        items.append(_adv_to_item(a, i))
            return self._json({"items": items, "meta": meta,
                               "job_id": job_id, "exported": exported})

        if path == "/api/page":
            try:
                n = int(qs.get("n", ["-1"])[0])
            except ValueError:
                return self.send_error(400, "n inválido")
            with _LOCK:
                result = JOB.get("result")
            pages = (result or {}).get("pages") or []
            for p in pages:
                if getattr(p, "number", None) == n:
                    img = getattr(p, "image_path", "")
                    if img and os.path.exists(img):
                        return self._send_file(img)
            return self.send_error(404, "Página no disponible")

        if path == "/api/library":
            try:
                return self._json({"issues": _library_issues()})
            except Exception as e:  # noqa: BLE001
                return self._json({"error": str(e)}, 500)

        if path == "/api/library/view":
            try:
                issue_id = int(qs.get("id", ["0"])[0])
                return self._json(_library_view(issue_id))
            except Exception as e:  # noqa: BLE001
                return self._json({"error": str(e)}, 500)

        # estaticos de web/
        return self._serve_static(path)

    def _serve_static(self, path: str):
        rel = path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR):
            return self.send_error(403, "Prohibido")
        return self._send_file(full)

    # ---- POST ---- #
    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/extract":
            params = self._read_json()
            job_id = _start_job()
            if job_id is None:
                return self._json({"error": "Ya hay una extracción en curso."}, 409)
            threading.Thread(target=_extract_worker, args=(params, job_id),
                             daemon=True).start()
            return self._json({"ok": True, "job_id": job_id})

        if path == "/api/upload":
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b""
            ctype = self.headers.get("Content-Type", "")
            try:
                saved = _parse_multipart_pdf(body, ctype)
            except Exception as e:  # noqa: BLE001
                return self._json({"error": str(e)}, 400)
            if not saved:
                return self._json({"error": "No se recibió ningún PDF."}, 400)
            token = uuid.uuid4().hex
            _UPLOADS[token] = saved
            return self._json({"token": token})

        if path == "/api/export":
            data = self._read_json()
            try:
                res = _do_export(data.get("decisions") or [],
                                 job_id=data.get("job_id"))
                return self._json(res)
            except Exception as e:  # noqa: BLE001
                return self._json({"error": str(e)}, 500)

        if path == "/api/library/compare":
            data = self._read_json()
            try:
                res = _library_compare(int(data["id_a"]), int(data["id_b"]))
                return self._json(res)
            except Exception as e:  # noqa: BLE001
                return self._json({"error": str(e)}, 500)

        return self.send_error(404, "No encontrado")


# --------------------------------------------------------------------------- #
# Lanzador
# --------------------------------------------------------------------------- #
def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    port = _free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    print(f"NEVO en marcha · {url}")

    # Ventana nativa si hay pywebview; si no, navegador por defecto.
    try:
        import webview  # type: ignore
        window = webview.create_window("NEVO · Inteligencia competitiva",
                                       url, width=1180, height=820,
                                       min_size=(960, 680))
        webview.start()
        httpd.shutdown()
    except ImportError:
        webbrowser.open(url)
        print("Ventana en el navegador. Cierra esta terminal (Ctrl+C) para parar.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            httpd.shutdown()


if __name__ == "__main__":
    main()
