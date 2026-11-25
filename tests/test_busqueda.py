from ley_energia.busqueda import Buscador, Filtros


def test_articulo_exacto_primero(buscador: Buscador) -> None:
    r = buscador.buscar("artículo 8 LSE", k=5)
    assert (r[0].doc["id"], r[0].clave) == ("lse", "8")
    assert not any(x.doc["id"] == "lse" and x.clave == "80" for x in r)


def test_sigla_de_reglamento(buscador: Buscador) -> None:
    assert buscador.detectar_documentos("Reglamento de la LSH artículo 116") == ["reg-lsh"]


def test_nombre_mas_largo_gana(buscador: Buscador) -> None:
    assert buscador.detectar_documentos("Reglamento de la Ley del Sector Eléctrico") == ["reg-lse"]


def test_sin_abrogados_por_omision(buscador: Buscador) -> None:
    r = buscador.buscar("permisos de generación de energía eléctrica", k=10)
    assert all(x.doc["abrogada_desde"] is None for x in r)


def test_abrogada_nombrada_se_incluye(buscador: Buscador) -> None:
    r = buscador.buscar("artículo 17 LIE", k=3)
    assert (r[0].doc["id"], r[0].clave) == ("lie", "17")


def test_regimen_temporal(buscador: Buscador) -> None:
    r = buscador.buscar("permisos de generación", k=10, filtros=Filtros(fecha="2020-01-01"))
    ids = {x.doc["id"] for x in r}
    assert "lie" in ids and "lse" not in ids


def test_resultado_trae_cita_y_vigencia(buscador: Buscador) -> None:
    d = buscador.buscar("artículo 30 LSE", k=1)[0].a_dict()
    assert d["cita"] == "LSE, artículo 30"
    assert d["vigente"] is True and d["url_oficial"].startswith("https://")


def test_leer_articulo_y_linaje(buscador: Buscador) -> None:
    partes = buscador.articulo("LSE", "30")
    assert partes and "autoconsumo" in partes[0].texto.lower()
    lin = buscador.linaje("LIE")
    assert lin["sustituido_por"][0]["id"] == "lse"
    assert {d["id"] for d in buscador.linaje("lse")["sustituye_a"]} == {"lie"}


def test_consulta_vacia(buscador: Buscador) -> None:
    assert buscador.buscar("   ") == []


import pytest  # noqa: E402


def test_leer_disposicion_y_variantes(buscador: Buscador) -> None:
    assert buscador.articulo("dacg-cne-autoconsumo", "1.2")[0].clave == "1.2"
    assert buscador.articulo("RLSE", "1.2") == []
    assert buscador.articulo("LSE", "artículo 30")[0].clave == "30"
    assert buscador.articulo("LIE", "segundo transitorio")[0].clave == "transitorio segundo"


def test_filtros_invalidos_fallan_en_voz_alta() -> None:
    with pytest.raises(ValueError, match="fecha"):
        Filtros(fecha="2025-3-1")
    with pytest.raises(ValueError, match="fecha"):
        Filtros(fecha="01/03/2025")
    with pytest.raises(ValueError, match="tipo"):
        Filtros(tipo="norma")
    assert Filtros(tipo="Ley").tipo == "ley"


def test_filtro_estrecho_no_se_queda_sin_candidatos(buscador: Buscador) -> None:
    r = buscador.buscar(
        "energía eléctrica", k=5, filtros=Filtros(tipo="reglamento", fecha="2015-01-01")
    )
    assert r and {x.doc["id"] for x in r} == {"reg-lih"}


def test_detecta_nombres_comunes_y_texto_nfd(buscador: Buscador) -> None:
    import unicodedata

    assert buscador.detectar_documentos("artículo 2 de la Ley de la CNE") == ["lcne"]
    assert buscador.detectar_documentos("reglamento de la Ley de la CFE") == ["reg-lepecfe"]
    nfd = unicodedata.normalize("NFD", "Regulación según el Reglamento de la LSE")
    assert buscador.detectar_documentos(nfd) == ["reg-lse"]


def test_transitorios_con_cita_unica(buscador: Buscador) -> None:
    """Cada clave de un documento es una sola unidad (sus partes comparten etiqueta base)."""
    unidades: dict[tuple[str, str], set[str]] = {}
    for doc_id, clave, etiqueta in buscador.con.execute(
        "SELECT doc_id, clave, etiqueta FROM fragmentos WHERE clave IS NOT NULL"
    ):
        unidades.setdefault((doc_id, clave), set()).add(etiqueta.split(" (parte")[0])
    assert [k for k, v in unidades.items() if len(v) > 1] == []
