import pipeline
from core.fetcher import MagazineFetcher
from core.pages import PageBuilder


class FakeResponse:
    def __init__(self, content=b"", content_type="application/octet-stream",
                 url="https://example.test/recurso"):
        self.content = content
        self.headers = {"Content-Type": content_type}
        self.url = url
        self.text = content.decode("utf-8", errors="ignore")

    def raise_for_status(self):
        return None


def test_pdf_directo_se_detecta_por_firma(monkeypatch, tmp_path):
    fetcher = MagazineFetcher(workdir=str(tmp_path))
    response = FakeResponse(b"%PDF-1.7\ncontenido", "application/octet-stream")
    monkeypatch.setattr(fetcher, "_get_static_response", lambda _url: response)

    result = fetcher.fetch("https://example.test/descarga?id=42")

    assert result.ok
    assert result.kind == "pdf"
    with open(result.pdf_path, "rb") as exported:
        assert exported.read().startswith(b"%PDF-")


def test_enlace_pdf_con_query_conserva_parametros():
    html = '<a href="/numero.pdf?token=abc&amp;download=1">Abrir</a>'

    found = MagazineFetcher._find_pdf_in_html(html, "https://example.test/x")

    assert found == "https://example.test/numero.pdf?token=abc&download=1"


def test_detecta_3d_flipbook_autoalojado():
    html = '<div class="fb3d-thumbnail">Revista</div>'

    url, name = MagazineFetcher._find_embedded_viewer(
        html, "https://revista.test/numero-20")

    assert url == "https://revista.test/numero-20"
    assert name == "3D FlipBook"


def test_imagenes_se_ordenan_por_numero_y_conservan_huecos(
        monkeypatch, tmp_path):
    fetcher = MagazineFetcher(workdir=str(tmp_path))
    urls = [
        "https://cdn.test/page10.jpg",
        "https://cdn.test/page2.jpg",
        "https://cdn.test/page1.jpg",
    ]
    monkeypatch.setattr(
        fetcher.session, "get",
        lambda url, **_kwargs: FakeResponse(
            ("imagen-" + url).encode(), "image/jpeg", url),
    )

    ordered = sorted(urls, key=fetcher._image_sort_key)
    paths = fetcher._download_images(ordered)

    assert [m["page_number"] for m in fetcher._last_image_manifest] == [1, 2, 10]
    assert [p.rsplit("page_", 1)[1] for p in paths] == [
        "001.jpg", "002.jpg", "010.jpg"]


def test_page_builder_respeta_numeracion_original(tmp_path):
    builder = PageBuilder(str(tmp_path), progress=lambda _message: None)
    builder._ocr = lambda _path: ""
    one = tmp_path / "uno.jpg"
    ten = tmp_path / "diez.jpg"
    one.write_bytes(b"imagen-uno")
    ten.write_bytes(b"imagen-diez")

    pages = builder.from_images([str(one), str(ten)],
                                run_ocr=False, page_numbers=[1, 10])

    assert [page.number for page in pages] == [1, 10]


def test_lee_total_de_paginas_desde_contador_del_visor():
    class Element:
        def inner_text(self, **_kwargs):
            return "12 / 166"

        def get_attribute(self, _name):
            return None

    class Page:
        frames = []

        def query_selector_all(self, selector):
            return [Element()] if selector == "[class*='page-count']" else []

    assert MagazineFetcher._detect_expected_pages(Page()) == 166


def test_imagen_duplicada_queda_registrada_en_manifiesto(monkeypatch, tmp_path):
    fetcher = MagazineFetcher(workdir=str(tmp_path))
    urls = ["https://cdn.test/page1.jpg", "https://cdn.test/page2.jpg"]
    monkeypatch.setattr(
        fetcher.session, "get",
        lambda url, **_kwargs: FakeResponse(b"misma-imagen", "image/jpeg", url),
    )

    paths = fetcher._download_images(urls)

    assert len(paths) == 1
    assert fetcher._last_image_manifest[1]["status"] == "duplicate"
    assert fetcher._last_image_manifest[1]["duplicate_of"] == 1


def test_hueco_de_origen_convierte_cobertura_en_parcial():
    coverage = pipeline._build_coverage(
        3, "heuristica", {"source_failed_pages": [[2]]})

    assert coverage["estado"] == "parcial"
    assert coverage["paginas_analizadas"] == 2
    assert coverage["paginas_no_analizadas"] == [2]
