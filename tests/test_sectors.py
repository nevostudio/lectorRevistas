from core.sectors import normalize_sector, EMPTY_GROUP, DEFAULT_GROUP


def test_vacio_y_none():
    assert normalize_sector("") == EMPTY_GROUP
    assert normalize_sector("   ") == EMPTY_GROUP
    assert normalize_sector(None) == EMPTY_GROUP


def test_categorias_basicas():
    assert normalize_sector("Alimentacion / Quesos") == "Alimentacion"
    assert normalize_sector("Bebidas / distribucion") == "Bebidas"
    assert normalize_sector("Sanitarios y griferia") == "Bano y sanitarios"


def test_actividad_gana_a_publico_objetivo():
    # "para hosteleria" es el publico, no la actividad: debe ganar la actividad.
    assert (normalize_sector("Agencia SEO / marketing para hosteleria")
            == "Marketing y comunicacion")
    assert (normalize_sector("Asistente digital para food service")
            == "Tecnologia y software")
    assert (normalize_sector("Asesoria estrategica en restauracion")
            == "Servicios profesionales")


def test_hosteleria_solo_cuando_es_el_negocio():
    assert (normalize_sector("Restaurante / bar de tapas")
            == "Hosteleria y restauracion")
    assert (normalize_sector("Servicio de catering para eventos")
            == "Hosteleria y restauracion")


def test_inclasificable_cae_en_otros():
    assert normalize_sector("Algo rarisimo inclasificable") == DEFAULT_GROUP
