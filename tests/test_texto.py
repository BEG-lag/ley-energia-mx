from ley_energia import texto


def test_normalizar_quita_acentos_y_conserva_enie() -> None:
    assert texto.normalizar("Energía Eléctrica, AÑO") == "energia electrica, año"


def test_raices_unifican_genero_y_numero() -> None:
    assert texto.raiz("electrica") == texto.raiz("electricos")


def test_detecta_articulo_sin_confundir_8_con_80() -> None:
    assert texto.detectar_articulos("artículo 8 de la LSE") == ["8"]
    assert texto.detectar_articulos("art. 80 LSE") == ["80"]


def test_detecta_sufijos_y_ordinales() -> None:
    assert texto.detectar_articulos("artículo 10 bis") == ["10 bis"]
    assert texto.detectar_articulos("artículo 4o de la Ley de la ASEA") == ["4"]
    assert texto.detectar_articulos("artículos 1º") == ["1"]


def test_detecta_transitorios_y_disposiciones() -> None:
    assert texto.detectar_articulos("transitorio segundo de la LSE") == ["transitorio segundo"]
    assert texto.detectar_articulos("décimo transitorio") == ["transitorio decimo"]
    assert texto.detectar_articulos("disposición 1.2 de la DACG") == ["1.2"]


def test_equivalencias_del_regimen_2014() -> None:
    assert "autoconsumo" in texto.expandir("¿Qué pasó con el autoabasto?")
    assert texto.expandir("permisos de transporte") == []


def test_quitar_acentos_conserva_longitud_y_mayusculas() -> None:
    import unicodedata

    nfd = unicodedata.normalize("NFD", "Regulación según el Reglamento de la LSE")
    salida = texto.quitar_acentos(nfd)
    assert salida == "Regulacion segun el Reglamento de la LSE"
    assert len(salida) == len(unicodedata.normalize("NFC", nfd))
    assert texto.quitar_acentos("Año") == "Año"
