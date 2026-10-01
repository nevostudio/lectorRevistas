import base64
from types import SimpleNamespace

import pytest

import pipeline
from core.checkpoint import JobWorkspace
from core.detector import AIDetector, DEFAULT_AI_MODEL
from core.pages import PageBuilder


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_workspace_estable_reutiliza_el_pdf_sin_guardar_credenciales(tmp_path):
    source = tmp_path / "revista.pdf"
    source.write_bytes(b"%PDF-1.7\ncontenido estable")
    root = tmp_path / "jobs"

    first = JobWorkspace(pdf_path=str(source), root=str(root), resume=True)
    copied = first.copy_local_pdf(str(source))
    first.save_source(
        kind="pdf", pdf_path=copied, image_paths=[], page_numbers=[],
        page_manifest=[], expected_pages=None, viewer=None, notes=[],
    )
    second = JobWorkspace(pdf_path=str(source), root=str(root), resume=True)

    assert first.job_id == second.job_id
    assert second.load_source()["pdf_path"] == copied
    assert "api" not in (root / first.job_id / "source.json").read_text(
        encoding="utf-8").lower()


def test_empezar_de_cero_crea_otro_trabajo(tmp_path):
    source = tmp_path / "revista.pdf"
    source.write_bytes(b"%PDF-1.7\ncontenido")
    root = tmp_path / "jobs"

    first = JobWorkspace(pdf_path=str(source), root=str(root), resume=False)
    second = JobWorkspace(pdf_path=str(source), root=str(root), resume=False)

    assert first.job_id != second.job_id


def test_paginas_y_ocr_se_recuperan_sin_reprocesar(tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    image = workdir / "page1.png"
    image.write_bytes(_PNG_1X1)
    messages = []
    first = PageBuilder(str(workdir), progress=messages.append)
    first._ocr = lambda _path: "texto ya extraido"

    original = first.from_images([str(image)], run_ocr=True)

    second = PageBuilder(str(workdir), progress=messages.append)
    second._ocr = lambda _path: (_ for _ in ()).throw(
        AssertionError("no debe repetir OCR"))
    restored = second.from_images([str(image)], run_ocr=True)

    assert restored[0].ocr_text == original[0].ocr_text
    assert any("recuperada" in message for message in messages)


def _ai_detector(checkpoint_dir, response_text):
    detector = object.__new__(AIDetector)
    detector.model = DEFAULT_AI_MODEL
    detector.checkpoint_dir = str(checkpoint_dir)
    detector.usage = {"input": 0, "output": 0,
                      "cache_write": 0, "cache_read": 0}
    detector.resumed_usage = {"input": 0, "output": 0,
                              "cache_write": 0, "cache_read": 0}
    detector.resumed_spreads = 0
    detector.failed_spreads = []
    detector.partial_spreads = []
    detector.invalid_items = []
    detector._progress = lambda _message: None
    detector._encode_image = lambda _path: ("image/png", "")
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=response_text)])

    def call(*_args):
        detector.usage["input"] += 100
        detector.usage["output"] += 20
        return response, False

    detector._call_with_retry = call
    return detector


def test_pliego_ia_se_recupera_sin_segunda_llamada(tmp_path):
    image = tmp_path / "page1.png"
    image.write_bytes(_PNG_1X1)
    page = SimpleNamespace(number=1, image_path=str(image), text="apoyo")
    response = (
        '{"anuncios":[{"marca":"Marca","pagina":1,"web":"",'
        '"email":"","telefono":"","sector":"Climatizacion",'
        '"tamano":"pagina completa","confianza":0.9}]}'
    )
    checkpoint = tmp_path / "analysis"
    first = _ai_detector(checkpoint, response)

    first_result = first._analyze_spread([page])

    second = _ai_detector(checkpoint, response)
    second._call_with_retry = lambda *_args: (_ for _ in ()).throw(
        AssertionError("no debe llamar a Claude"))
    restored = second._analyze_spread([page])

    assert [item.brand for item in first_result] == ["Marca"]
    assert [item.brand for item in restored] == ["Marca"]
    assert second.resumed_spreads == 1
    assert second.usage["input"] == 100
    assert second.resumed_usage["output"] == 20


def test_checkpoint_antiguo_parcial_se_recalcula(tmp_path):
    image = tmp_path / "page38.png"
    image.write_bytes(_PNG_1X1)
    page = SimpleNamespace(number=38, image_path=str(image), text="apoyo")
    response = (
        '{"anuncios":[{"marca":"ABB","pagina":38,"web":"",'
        '"email":"","telefono":"","sector":"Electricidad",'
        '"tamano":"publirreportaje","confianza":0.8}]}'
    )
    checkpoint = tmp_path / "analysis"
    detector = _ai_detector(checkpoint, response)
    legacy_path = detector._spread_checkpoint_path(
        detector._spread_signature([page], legacy=True))
    checkpoint.mkdir()
    import json
    with open(legacy_path, "w", encoding="utf-8") as stream:
        json.dump({
            "version": 1,
            "model": DEFAULT_AI_MODEL,
            "pages": [38],
            "advertisers": [],
            "usage": {"input": 50, "output": 10,
                      "cache_write": 0, "cache_read": 0},
            "invalid_items": [{"reason": "campos corregidos"}],
            "partial": True,
        }, stream)

    result = detector._analyze_spread([page])

    assert [item.brand for item in result] == ["ABB"]
    assert detector.resumed_spreads == 0
    assert detector.usage["input"] == 100


def test_checkpoint_antiguo_completo_se_conserva(tmp_path):
    image = tmp_path / "page1.png"
    image.write_bytes(_PNG_1X1)
    page = SimpleNamespace(number=1, image_path=str(image), text="apoyo")
    checkpoint = tmp_path / "analysis"
    detector = _ai_detector(checkpoint, '{"anuncios":[]}')
    legacy_path = detector._spread_checkpoint_path(
        detector._spread_signature([page], legacy=True))
    checkpoint.mkdir()
    import json
    with open(legacy_path, "w", encoding="utf-8") as stream:
        json.dump({
            "version": 1,
            "model": DEFAULT_AI_MODEL,
            "pages": [1],
            "advertisers": [{
                "brand": "Marca conservada", "pages": [1], "website": "",
                "email": "", "phone": "", "sector": "", "ad_size": "",
                "confidence": 0.9, "method": "ia", "notes": "",
                "review_flag": "",
            }],
            "usage": {"input": 50, "output": 10,
                      "cache_write": 0, "cache_read": 0},
            "invalid_items": [],
            "partial": False,
        }, stream)
    detector._call_with_retry = lambda *_args: (_ for _ in ()).throw(
        AssertionError("no debe llamar a Claude"))

    result = detector._analyze_spread([page])

    assert [item.brand for item in result] == ["Marca conservada"]
    assert detector.resumed_spreads == 1


def test_pipeline_reutiliza_pdf_y_paginas_renderizadas(tmp_path):
    fitz = pytest.importorskip("fitz")
    pdf = tmp_path / "revista.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Visita ejemplo.com")
    document.save(str(pdf))
    document.close()
    workspace_root = tmp_path / "jobs"
    first_messages = []
    second_messages = []

    first = pipeline.run_extraction(
        pdf_path=str(pdf), run_ocr=False,
        workspace_root=str(workspace_root), progress=first_messages.append,
    )
    second = pipeline.run_extraction(
        pdf_path=str(pdf), run_ocr=False,
        workspace_root=str(workspace_root), progress=second_messages.append,
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["meta"]["fuente_reanudada"] is True
    assert any("recuperada" in message for message in second_messages)
