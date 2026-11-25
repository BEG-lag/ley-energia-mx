from ley_energia.chunker import trocear_markdown, trocear_texto

MD = """---
title: Ley de Prueba
---

# LEY DE PRUEBA

Texto del decreto.

## TÍTULO PRIMERO · DISPOSICIONES GENERALES

### Capítulo I · Del objeto

#### Artículo 1.

La presente Ley tiene por objeto regular la prueba.

#### Artículo 8.

Texto del artículo ocho, que es distinto del ochenta.

##### Artículo 80 Bis.

Texto del artículo ochenta bis con contenido suficiente.

## Transitorios

**Primero.-** La presente Ley entrará en vigor al día siguiente de su publicación.

**Segundo.-** Se abroga la Ley anterior publicada en el Diario Oficial de la Federación.
"""


def test_markdown_un_fragmento_por_articulo_con_ruta() -> None:
    frs = trocear_markdown(MD)
    claves = [f.clave for f in frs]
    assert claves[-4:] == ["8", "80 bis", "transitorio primero", "transitorio segundo"]
    art1 = next(f for f in frs if f.clave == "1")
    assert art1.etiqueta == "Artículo 1"
    assert art1.ruta == ["TÍTULO PRIMERO · DISPOSICIONES GENERALES", "Capítulo I · Del objeto"]
    assert "regular la prueba" in art1.texto


def test_markdown_ordinal_o() -> None:
    frs = trocear_markdown(
        "## TÍTULO\n\n#### Artículo 4o.\n\nTexto del artículo cuarto de la ley.\n"
    )
    assert [f.clave for f in frs] == ["4"]


TEXTO = """LEY DE PRUEBA
TÍTULO PRIMERO
CAPÍTULO I
Disposiciones generales
Artículo 1.- Esta ley regula la prueba de troceo por artículos.
Artículo 2.- Para efectos de esta ley se entiende por prueba lo siguiente:
I. Primera fracción;
II. Segunda fracción.
Artículo 3o.- Tercer artículo con suficiente texto para no descartarse.
TRANSITORIOS
PRIMERO.- El presente decreto entra en vigor al día siguiente.
SEGUNDO.- Se derogan las disposiciones que se opongan.
"""


def test_texto_plano_articulos_y_transitorios() -> None:
    frs = trocear_texto(TEXTO)
    assert [f.clave for f in frs] == ["1", "2", "3", "transitorio primero", "transitorio segundo"]
    assert frs[1].ruta == ["TÍTULO PRIMERO", "CAPÍTULO I · Disposiciones generales"]
    assert "II. Segunda fracción." in frs[1].texto


def test_dacg_por_disposiciones_y_anexo_separado() -> None:
    texto = (
        "ACUERDO de la Comisión por el que se emiten disposiciones.\n"
        "Capítulo 1. Disposiciones generales\n"
        "1.1 Objeto. Las presentes disposiciones regulan la materia de prueba.\n"
        "1.2 Alcance. Aplican a todas las personas permisionarias del país.\n"
        "1.3 Definiciones. Para efectos de estas disposiciones se entiende lo siguiente.\n"
        "Transitorios\n"
        "PRIMERO. El presente Acuerdo entra en vigor al día hábil siguiente.\n"
        "Anexo Único. Formatos autorizados del trámite de prueba\n"
        "Formato 1. Solicitud de permiso con datos generales de la persona.\n"
    )
    frs = trocear_texto(texto)
    claves = [f.clave for f in frs]
    assert claves[1:5] == ["1.1", "1.2", "1.3", "transitorio primero"]
    anexo = frs[-1]
    assert anexo.clave is None and anexo.ruta == [
        "Anexo Único. Formatos autorizados del trámite de prueba"
    ]


def test_parte_articulos_largos_sin_perder_clave() -> None:
    largo = "Artículo 1.- " + ("palabra " * 1200)
    frs = trocear_texto(f"TÍTULO I\n{largo}\nArtículo 2.- Otro.\nArtículo 3.- Otro más.")
    partes = [f for f in frs if f.clave == "1"]
    assert len(partes) >= 2
    assert all(len(f.texto) <= 4000 for f in partes)
    assert partes[0].etiqueta.startswith("Artículo 1 (parte 1 de")


MD_DECRETOS = """## TÍTULO PRIMERO

#### Artículo 1.

Objeto de la ley de prueba con texto suficiente.

## Transitorios

**Primero.-** La presente Ley entrará en vigor al día siguiente de su publicación.

**Segundo.-** Se abroga la ley anterior publicada en el Diario Oficial de la Federación.

**Transitorios**

**Primero.** El presente Decreto entrará en vigor el día siguiente al de su publicación.

## ARTÍCULOS TRANSITORIOS DE DECRETOS DE REFORMA

### DECRETO por el que se reforman diversas disposiciones de la Ley de Prueba.

*Publicado en el Diario Oficial de la Federación el 9 de marzo de 2021*

**ARTÍCULO PRIMERO.-** Se reforma el artículo 1 de la Ley de Prueba con un texto nuevo.

**Transitorios**

**Primero.-** El presente Decreto entrará en vigor al día siguiente de su publicación.

PUNTOS RESOLUTIVOS de la sentencia dictada por el Tribunal Pleno en la acción de prueba.

**SEGUNDO.** Se declara la invalidez del artículo 1 de la Ley de Prueba por la sentencia.
"""


def test_transitorios_por_decreto_con_clave_y_fecha_propias() -> None:
    frs = trocear_markdown(MD_DECRETOS)
    claves = [f.clave for f in frs if f.clave and f.clave.startswith("transitorio")]
    assert claves == [
        "transitorio primero",
        "transitorio segundo",
        "transitorio primero (decreto de expedicion)",
        "transitorio primero (dof 2021-03-09)",
    ]
    reforma = next(f for f in frs if f.clave == "transitorio primero (dof 2021-03-09)")
    assert reforma.etiqueta == "Transitorio primero del decreto DOF 09-03-2021"
    assert reforma.ruta[0].startswith("DECRETO por el que se reforman")
    # Ni el artículo del decreto ni el resolutivo de la sentencia son transitorios.
    textos_transitorios = " ".join(f.texto for f in frs if f.clave and "transitorio" in f.clave)
    assert "Se reforma el artículo 1" not in textos_transitorios
    assert "Se declara la invalidez" not in textos_transitorios


def test_no_borra_partes_cortas_ni_transitorios() -> None:
    largo = "Artículo 1.- " + ("palabra " * 520) + "\nX. Última fracción corta."
    texto = f"TÍTULO I\n{largo}\nArtículo 2.- Otro artículo.\nArtículo 3.- Otro más.\n"
    texto += "TRANSITORIOS\nPRIMERO.- Entra en vigor mañana.\nSEGUNDO.- Se deroga lo demás."
    frs = trocear_texto(texto)
    partes = [f for f in frs if f.clave == "1"]
    assert partes[-1].texto.endswith("Última fracción corta.")
    assert [f.clave for f in frs if f.clave and f.clave.startswith("transitorio")] == [
        "transitorio primero",
        "transitorio segundo",
    ]


def test_indice_al_inicio_se_descarta() -> None:
    texto = (
        "Capítulo 1. Generales\n1.1 Objeto.\n1.2 Alcance.\n1.3 Definiciones.\n"
        "Capítulo 1. Generales\n"
        "1.1 Objeto. Las presentes disposiciones regulan la materia de prueba con detalle.\n"
        "1.2 Alcance. Aplican a todas las personas permisionarias del país y sus representantes.\n"
        "1.3 Definiciones. Para efectos de estas disposiciones se entiende lo que sigue aquí.\n"
    )
    frs = trocear_texto(texto)
    assert [f.clave for f in frs if f.clave] == ["1.1", "1.2", "1.3"]
