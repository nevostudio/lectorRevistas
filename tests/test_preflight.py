import base64
from types import SimpleNamespace

import pipeline
from core.preflight import check_source


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _image(tmp_path, name="page.png"):
    path = tmp_path / name
    path.write_bytes(_PNG_1X1)
    return str(path)


def _page(number, path):
    return SimpleNamespace(number=number, image_path=path, text="")


def test_pdf_completo_queda_listo(tmp_path):
    image = _image(tmp_path)

    result = check_source(
        kind="pdf",
        pages=[_page(1, image), _page(2, image)],
        page_manifest=[],
        local_pdf=True,
    )

    assert result.ready
    assert result.source_type == "PDF local"
    assert result.expected_pages == 2
    assert result.obtained_pages == 2


def test_hueco_en_lector_por_imagenes_bloquea_analisis(tmp_path):
    image = _image(tmp_path)
    manifest = [
        {"page_number": 1, "status": "ok"},
        {"page_number": 2, "status": "failed"},
        {"page_number": 3, "status": "ok"},
    ]

    result = check_source(
        kind="images",
        pages=[_page(1, image), _page(3, image)],
        page_manifest=manifest,
        viewer="Visor de prueba",
        expected_pages=3,
    )

    assert not result.ready
    assert result.missing_pages == [2]
    assert result.failed_pages == [2]


def test_imagen_ausente_se_marca_como_fuente_incompleta(tmp_path):
    result = check_source(
        kind="images",
        pages=[_page(1, str(tmp_path / "ausente.png"))],
        page_manifest=[],
    )

    assert not result.ready
    assert result.unreadable_pages == [1]


def test_total_desconocido_no_bloquea_si_lo_obtenido_es_valido(tmp_path):
    image = _image(tmp_path)

    result = check_source(
        kind="images",
        pages=[_page(1, image)],
        page_manifest=[],
    )

    assert result.ready
    assert result.expected_pages is None
    assert result.completeness_known is False
    assert result.warnings


def test_total_inferido_detecta_huecos_sin_afirmar_completitud(tmp_path):
    image = _image(tmp_path)
    manifest = [
        {"page_number": 1, "status": "ok"},
        {"page_number": 3, "status": "ok"},
    ]

    result = check_source(
        kind="images",
        pages=[_page(1, image), _page(3, image)],
        page_manifest=manifest,
    )

    assert not result.ready
    assert result.expected_pages == 3
    assert result.completeness_known is False
    assert result.missing_pages == [2]


def test_pipeline_no_llama_ia_si_la_fuente_esta_incompleta(
        monkeypatch, tmp_path):
    pdf = tmp_path / "revista.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    image = _image(tmp_path)

    class FakeFetcher:
        def __init__(self, **_kwargs):
            self.workdir = str(tmp_path / "work")

    class FakeBuilder:
        def __init__(self, *_args, **_kwargs):
            pass

        def from_pdf(self, *_args, **_kwargs):
            return [_page(1, image), _page(3, image)]

    monkeypatch.setattr(pipeline, "MagazineFetcher", FakeFetcher)
    monkeypatch.setattr(pipeline, "PageBuilder", FakeBuilder)
    monkeypatch.setattr(
        pipeline,
        "detect_advertisers",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("no debe llamar a la IA")),
    )

    result = pipeline.run_extraction(
        pdf_path=str(pdf), use_ai=True, api_key="clave-simulada",
        progress=lambda _message: None,
        workspace_root=str(tmp_path / "jobs"),
    )

    assert result["ok"] is False
    assert result["meta"]["comprobacion_fuente"]["status"] == "incompleta"
    assert "No se ha usado la API de Claude" in result["error"]
