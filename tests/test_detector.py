from core.detector import canonical_brand, AIDetector


def test_canonical_normaliza_mayusculas_acentos_y_forma_juridica():
    assert canonical_brand("ROCA") == "roca"
    assert canonical_brand("Roca, S.A.") == "roca"
    assert canonical_brand("Cosentino S.L.") == "cosentino"
    assert canonical_brand("  Símon  ") == "simon"


def test_canonical_es_conservadora():
    # No debe fusionar marcas distintas con palabras anadidas.
    assert canonical_brand("Simon") != canonical_brand("Simon Electric")
    assert canonical_brand("Euro Perfil") != canonical_brand("Europerfil")


def test_parse_json_perfecto():
    raw = '{"anuncios":[{"marca":"Roca"},{"marca":"Simon"}]}'
    objs = AIDetector._parse_ads_json(raw)
    assert [o["marca"] for o in objs] == ["Roca", "Simon"]


def test_parse_json_truncado_recupera_objetos_completos():
    # JSON cortado a la mitad (el bug original perdia TODO el pliego).
    raw = ('{"anuncios":[{"marca":"Roca","web":"roca.com"},'
           '{"marca":"Simon","web":"sim')
    objs = AIDetector._parse_ads_json(raw)
    marcas = [o["marca"] for o in objs]
    assert "Roca" in marcas  # al menos el objeto completo se recupera


def test_parse_json_con_fences():
    raw = '```json\n{"anuncios":[{"marca":"Roca"}]}\n```'
    objs = AIDetector._parse_ads_json(raw)
    assert objs and objs[0]["marca"] == "Roca"


def test_parse_json_vacio_o_basura():
    assert AIDetector._parse_ads_json("") == []
    assert AIDetector._parse_ads_json("no soy json") == []


def test_parse_ignora_llaves_dentro_de_strings():
    raw = '{"anuncios":[{"marca":"A {raro}","nota":"texto con } llave"}]}'
    objs = AIDetector._parse_ads_json(raw)
    assert objs and objs[0]["marca"] == "A {raro}"
