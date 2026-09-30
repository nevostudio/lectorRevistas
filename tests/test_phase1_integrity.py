import json
import os
import threading
import base64
from types import SimpleNamespace

import pytest

import pipeline
import webapp
import core.report as report_module
from core.detector import AIDetector, Advertiser
from core.report import export_all


def _detector(response_text, *, truncated=False):
    detector = object.__new__(AIDetector)
    detector.failed_spreads = []
    detector.partial_spreads = []
    detector.invalid_items = []
    detector.usage = {"input": 0, "output": 0,
                      "cache_write": 0, "cache_read": 0}
    detector._progress = lambda _message: None
    detector._encode_image = lambda _path: ("image/png", "")
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=response_text)])
    detector._call_with_retry = lambda *_args: (response, truncated)
    return detector


def _page(number=1, image_path="ficticia.png"):
    return SimpleNamespace(number=number, image_path=image_path, text="")


def test_confianza_cero_se_conserva_y_telefono_numerico_no_rompe():
    detector = _detector(
        '{"anuncios":[{"marca":"Ejemplo","pagina":1,'
        '"telefono":912345678,"confianza":0}]}')

    result = detector._analyze_spread([_page()])

    assert len(result) == 1
    assert result[0].confidence == 0.0
    assert result[0].phone == "912345678"
    assert detector.failed_spreads == []


def test_json_vacio_valido_no_se_marca_como_fallo():
    detector = _detector('{ "anuncios" : [ ] }')

    assert detector._analyze_spread([_page()]) == []
    assert detector.failed_spreads == []
    assert detector.partial_spreads == []


def test_respuesta_truncada_conserva_resultados_y_marca_parcial():
    detector = _detector(
        '{"anuncios":[{"marca":"Completo","pagina":1,'
        '"confianza":0.7},{"marca":"Cort', truncated=True)

    result = detector._analyze_spread([_page()])

    assert [item.brand for item in result] == ["Completo"]
    assert detector.partial_spreads == [[1]]


def test_todas_las_paginas_ia_fallidas_no_devuelven_exito(monkeypatch, tmp_path):
    pdf = tmp_path / "revista.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    image = tmp_path / "pagina.png"
    image.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
        "+A8AAQUBAScY42YAAAAASUVORK5CYII="))

    class FakeFetcher:
        def __init__(self, **_kwargs):
            self.workdir = str(tmp_path / "work")

    class FakeBuilder:
        def __init__(self, *_args, **_kwargs):
            pass

        def from_pdf(self, *_args, **_kwargs):
            return [_page(1, str(image)), _page(2, str(image))]

    def fake_detect(_pages, **kwargs):
        kwargs["telemetry"].update(failed_spreads=[[1], [2]])
        return [], "ia"

    monkeypatch.setattr(pipeline, "MagazineFetcher", FakeFetcher)
    monkeypatch.setattr(pipeline, "PageBuilder", FakeBuilder)
    monkeypatch.setattr(pipeline, "detect_advertisers", fake_detect)

    result = pipeline.run_extraction(pdf_path=str(pdf), use_ai=True,
                                     progress=lambda _message: None)

    assert result["ok"] is False
    assert result["analysis_status"] == "fallido"
    assert result["meta"]["cobertura"]["paginas_no_analizadas"] == [1, 2]


def test_revista_sin_paginas_no_llega_al_detector(monkeypatch, tmp_path):
    pdf = tmp_path / "vacia.pdf"
    pdf.write_bytes(b"%PDF-1.7")

    class FakeFetcher:
        def __init__(self, **_kwargs):
            self.workdir = str(tmp_path / "work")

    class FakeBuilder:
        def __init__(self, *_args, **_kwargs):
            pass

        def from_pdf(self, *_args, **_kwargs):
            return []

    monkeypatch.setattr(pipeline, "MagazineFetcher", FakeFetcher)
    monkeypatch.setattr(pipeline, "PageBuilder", FakeBuilder)
    monkeypatch.setattr(
        pipeline, "detect_advertisers",
        lambda *_args, **_kwargs: pytest.fail("no debe ejecutarse"),
    )

    result = pipeline.run_extraction(pdf_path=str(pdf),
                                     progress=lambda _message: None)

    assert result["ok"] is False
    assert result["analysis_status"] == "fallido"
    assert result["meta"]["cobertura"]["paginas_totales"] == 0


def test_exportaciones_consecutivas_tienen_rutas_unicas(tmp_path):
    advertiser = Advertiser("Empresa ficticia", confidence=0.8)
    meta = {"titulo": "Revista ficticia", "estado_analisis": "completo"}

    first = export_all([advertiser], str(tmp_path), meta)
    second = export_all([advertiser], str(tmp_path), meta)

    assert first["json"] != second["json"]
    assert os.path.exists(first["json"])
    assert os.path.exists(second["json"])
    assert json.loads((tmp_path / os.path.basename(first["json"])).read_text(
        encoding="utf-8"))[
        "anunciantes"][0]["brand"] == "Empresa ficticia"


def test_exportacion_interrumpida_no_publica_archivos_incompletos(
        monkeypatch, tmp_path):
    advertiser = Advertiser("Empresa ficticia", confidence=0.8)
    monkeypatch.setattr(
        report_module, "export_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("fallo simulado")),
    )

    with pytest.raises(RuntimeError, match="fallo simulado"):
        export_all([advertiser], str(tmp_path), {"titulo": "Prueba"})

    assert list(tmp_path.iterdir()) == []


def test_exportacion_web_es_idempotente(monkeypatch, tmp_path):
    calls = []

    def fake_export(advertisers, meta, _outdir, progress=None):
        calls.append(([a.brand for a in advertisers], dict(meta)))
        return {"html": str(tmp_path / "informe.html")}

    monkeypatch.setattr(webapp, "export_results", fake_export)
    monkeypatch.setattr(webapp.webbrowser, "open", lambda _url: None)
    monkeypatch.setattr(webapp, "OUT_DIR", str(tmp_path))
    job_id = webapp._reset_job()
    with webapp._LOCK:
        webapp.JOB["state"] = "done"
        webapp.JOB["result"] = {
            "advertisers": [Advertiser("Uno"), Advertiser("Dos")],
            "meta": {"estado_analisis": "completo"},
        }

    first = webapp._do_export([{"index": 0, "state": "drop"}], job_id)
    second = webapp._do_export([{"index": 0, "state": "drop"}], job_id)

    assert first == second
    assert first["n"] == 1
    assert len(calls) == 1


def test_no_se_inicia_otro_trabajo_durante_exportacion(monkeypatch, tmp_path):
    started = threading.Event()
    release = threading.Event()

    def slow_export(*_args, **_kwargs):
        started.set()
        assert release.wait(timeout=2)
        return {"html": str(tmp_path / "informe.html")}

    monkeypatch.setattr(webapp, "export_results", slow_export)
    monkeypatch.setattr(webapp.webbrowser, "open", lambda _url: None)
    monkeypatch.setattr(webapp, "OUT_DIR", str(tmp_path))
    job_id = webapp._reset_job()
    with webapp._LOCK:
        webapp.JOB["state"] = "done"
        webapp.JOB["result"] = {
            "advertisers": [Advertiser("Uno")],
            "meta": {"estado_analisis": "completo"},
        }

    worker = threading.Thread(target=webapp._do_export, args=([], job_id))
    worker.start()
    assert started.wait(timeout=2)
    assert webapp._start_job() is None
    release.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert webapp.JOB["state"] == "done"


def test_error_de_preferencias_no_deja_job_en_ejecucion(monkeypatch):
    job_id = webapp._reset_job()
    monkeypatch.setattr(webapp.config, "api_key", lambda: "")
    monkeypatch.setattr(webapp.config, "set_last_url",
                        lambda _url: (_ for _ in ()).throw(OSError("sin permiso")))
    monkeypatch.setattr(webapp, "run_extraction", lambda **_kwargs: {
        "ok": False,
        "error": "fallo controlado",
        "analysis_status": "fallido",
        "advertisers": [],
        "pages": [],
        "meta": {},
    })

    webapp._extract_worker({"url": "https://example.test"}, job_id)

    assert webapp.JOB["state"] == "error"
    assert webapp.JOB["error"] == "fallo controlado"
