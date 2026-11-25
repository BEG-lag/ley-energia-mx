"""Normalización, stemming y detección de referencias en consultas.

Todo lo que compara texto (índice, búsqueda, catálogo para la web) pasa por aquí para que
la indexación y la consulta usen exactamente las mismas reglas.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import snowballstemmer

_STEMMER = snowballstemmer.stemmer("spanish")

# Palabras vacías: no aportan a la búsqueda léxica y sólo inflan el índice.
STOPWORDS: frozenset[str] = frozenset(
    """a al algo algunas algunos ante antes como con contra cual cuales cuando de del desde donde
    dos el ella ellas ellos en entre era eran es esa esas ese eso esos esta estas este esto estos
    fue fueron ha han hasta la las le les lo los mas me mi mientras muy nada ni no nos o otra
    otras otro otros para pero poco por porque que quien quienes se sea sean segun ser si sin
    sino sobre son su sus tal tambien tan tanto te tiene tienen todo todos tras tu un una unas
    uno unos y ya qué cuál cuáles dice dicen articulo articulos art""".split()  # noqa: SIM905
)

_PALABRA = re.compile(r"[a-z0-9ñ]+")


def quitar_acentos(texto: str) -> str:
    """Quita acentos sin cambiar mayúsculas ni la longitud del texto (en forma NFC).

    Conserva la ñ. Como cada carácter da exactamente uno, las posiciones de una coincidencia
    en el texto sin acentos sirven también en el original.
    """
    salida = []
    for c in unicodedata.normalize("NFC", texto):
        if c in "ñÑ":
            salida.append(c)
            continue
        base = "".join(x for x in unicodedata.normalize("NFD", c) if not unicodedata.combining(x))
        salida.append(base if len(base) == 1 else c)
    return "".join(salida)


def normalizar(texto: str) -> str:
    """Minúsculas y sin acentos (conserva la ñ). Misma longitud que el texto en NFC."""
    return quitar_acentos(texto).lower()


@lru_cache(maxsize=200_000)
def raiz(palabra: str) -> str:
    """Raíz Snowball de una palabra ya normalizada."""
    if palabra.isdigit():
        return palabra
    return str(_STEMMER.stemWord(palabra))


def tokens(texto: str, *, quitar_vacias: bool = True) -> list[str]:
    """Palabras normalizadas de un texto."""
    palabras = _PALABRA.findall(normalizar(texto))
    if quitar_vacias:
        return [p for p in palabras if p not in STOPWORDS and len(p) > 1]
    return palabras


def raices(texto: str) -> list[str]:
    """Raíces de las palabras significativas de un texto, en orden."""
    return [raiz(p) for p in tokens(texto)]


def texto_indexable(texto: str) -> str:
    """Cadena de raíces separadas por espacio, lista para FTS5."""
    return " ".join(raices(texto))


# ---------------------------------------------------------------------------
# Artículos
# ---------------------------------------------------------------------------

_SUFIJOS = r"(?:\s*(?:bis|ter|qu[aá]ter|quinquies|sexies))?"
_ART_EN_CONSULTA = re.compile(
    rf"\b(?:art[íi]culos?|arts?\.?)\s*(\d{{1,4}})\s*[oº°]?\.?{_SUFIJOS}(?![a-z0-9])",
    re.IGNORECASE,
)
_ART_SUFIJO = re.compile(
    rf"\b(?:art[íi]culos?|arts?\.?)\s*\d{{1,4}}\s*[oº°]?\.?({_SUFIJOS})", re.IGNORECASE
)


def clave_articulo(numero: str, sufijo: str = "") -> str:
    """Clave canónica de un artículo: '8', '20 bis'. Nunca confunde 8 con 80."""
    sufijo = normalizar(sufijo).strip()
    numero = str(int(numero))
    return f"{numero} {sufijo}" if sufijo else numero


ORDINAL = (
    r"(?:(?:d[ée]cimo|vig[ée]simo|trig[ée]simo)\s+)?(?:primero|segundo|tercero|cuarto|quinto|sexto"
    r"|s[ée]ptimo|octavo|noveno|d[ée]cimo|und[ée]cimo|duod[ée]cimo|vig[ée]simo|trig[ée]simo|[úu]nico)"
)
_TRANSITORIO_EN_CONSULTA = re.compile(
    rf"\btransitorio\s+({ORDINAL})\b|\b({ORDINAL})\s+transitorio\b", re.IGNORECASE
)
_DISPOSICION_EN_CONSULTA = re.compile(r"\b(?:disposici[oó]n|numeral)\s+(\d{1,2}\.\d{1,2})\b", re.I)


def detectar_articulos(consulta: str) -> list[str]:
    """Claves citadas en la consulta: 'artículo 20', 'art. 8 bis', 'transitorio segundo',
    'disposición 1.2'."""
    claves: list[str] = []
    for m in _TRANSITORIO_EN_CONSULTA.finditer(consulta):
        ordinal = " ".join(normalizar(m.group(1) or m.group(2)).split())
        claves.append(f"transitorio {ordinal}")
    for m in _DISPOSICION_EN_CONSULTA.finditer(consulta):
        claves.append(m.group(1))
    for m in _ART_EN_CONSULTA.finditer(consulta):
        texto = m.group(0)
        suf = _ART_SUFIJO.match(texto)
        sufijo = suf.group(1) if suf else ""
        clave = clave_articulo(m.group(1), sufijo)
        if clave not in claves:
            claves.append(clave)
    return claves


# ---------------------------------------------------------------------------
# Vocabulario del régimen anterior (LIE 2014) y del nuevo (reforma 2025)
# ---------------------------------------------------------------------------

# Consultas con términos del régimen de 2014 fallan contra las leyes de 2025 si sólo se
# busca la coincidencia literal. Se agregan las frases equivalentes a la parte léxica.
EQUIVALENCIAS: dict[str, list[str]] = {
    "usuario final": ["usuario calificado"],
    "usuarios finales": ["usuarios calificados"],
    "venta directa": ["suministro calificado", "comercializadora"],
    "abasto aislado": ["autoconsumo aislado"],
    "autoabasto": ["autoconsumo"],
    "cre": ["comision nacional de energia"],
    "comision reguladora de energia": ["comision nacional de energia"],
    "cnh": ["comision nacional de energia"],
    "comision nacional de hidrocarburos": ["comision nacional de energia"],
    "empresa productiva del estado": ["empresa publica del estado"],
}


def expandir(consulta: str) -> list[str]:
    """Frases equivalentes para la parte léxica de la búsqueda."""
    norm = " " + re.sub(r"[^a-z0-9ñ]+", " ", normalizar(consulta)) + " "
    extras: list[str] = []
    for viejo, nuevos in EQUIVALENCIAS.items():
        if f" {viejo} " in norm:
            extras.extend(n for n in nuevos if n not in extras)
    return extras
