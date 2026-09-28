import os
import tempfile

import pytest

from core.library import Library


def _ad(brand, sector="", pages=(1,), web="", conf=0.9):
    return {"brand": brand, "sector": sector, "pages": list(pages),
            "website": web, "email": "", "phone": "", "ad_size": "",
            "confidence": conf, "method": "ia"}


@pytest.fixture
def lib():
    path = tempfile.mktemp(suffix=".db")
    library = Library(path)
    yield library
    library.close()
    os.remove(path)


def test_guardar_y_listar(lib):
    iid = lib.save_issue({"titulo": "Mag", "numero": "1"},
                         [_ad("Roca"), _ad("Simon")])
    issues = lib.list_issues()
    assert len(issues) == 1
    assert issues[0]["id"] == iid
    assert issues[0]["n_anunciantes"] == 2


def test_comparar_nuevos_perdidos_recurrentes(lib):
    a = lib.save_issue({"titulo": "Mag", "numero": "1"},
                       [_ad("Roca"), _ad("Simon"), _ad("Cosentino")])
    b = lib.save_issue({"titulo": "Mag", "numero": "2"},
                       [_ad("Roca"), _ad("Simon"), _ad("Porcelanosa")])
    cmp = lib.compare_issues(a, b)
    assert [x["brand"] for x in cmp["nuevos"]] == ["Porcelanosa"]
    assert [x["brand"] for x in cmp["perdidos"]] == ["Cosentino"]
    assert {x["brand"] for x in cmp["recurrentes"]} == {"Roca", "Simon"}
    assert cmp["fidelidad"] == pytest.approx(2 / 3)


def test_comparar_fusiona_variantes_de_la_misma_marca(lib):
    a = lib.save_issue({"numero": "1"}, [_ad("ROCA")])
    b = lib.save_issue({"numero": "2"}, [_ad("Roca")])
    cmp = lib.compare_issues(a, b)
    # Misma marca canonica -> recurrente, no nuevo/perdido.
    assert len(cmp["recurrentes"]) == 1
    assert not cmp["nuevos"] and not cmp["perdidos"]


def test_historico_de_anunciante(lib):
    lib.save_issue({"titulo": "Mag", "numero": "1"}, [_ad("Roca")])
    lib.save_issue({"titulo": "Mag", "numero": "2"}, [_ad("Roca, S.A.")])
    hist = lib.advertiser_history("Roca")
    assert len(hist) == 2


def test_share_of_voice_agrupa_por_categoria(lib):
    iid = lib.save_issue({"numero": "1"}, [
        _ad("A", "Alimentacion / Quesos"),
        _ad("B", "Alimentacion / Carnes"),
        _ad("C", "Bebidas / vinos"),
    ])
    sov = dict(lib.share_of_voice(iid))
    assert sov["Alimentacion"] == 2
    assert sov["Bebidas"] == 1


def test_borrar_issue(lib):
    iid = lib.save_issue({"numero": "1"}, [_ad("Roca")])
    lib.delete_issue(iid)
    assert lib.list_issues() == []
