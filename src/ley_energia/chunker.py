"""Troceo por unidad jurídica: un fragmento por artículo, disposición o transitorio.

Cada fragmento conserva su ruta jerárquica (Título, Capítulo, Sección) para que la cita sea
precisa y la búsqueda tenga contexto. Los artículos muy largos se parten en partes numeradas
sin perder la clave del artículo.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .texto import ORDINAL, clave_articulo, normalizar

MAX_CARACTERES = 4_000


@dataclass
class Fragmento:
    orden: int
    clave: str | None  # "20", "20 bis", "1.1", "transitorio primero"; None en preámbulos
    etiqueta: str  # "Artículo 20", "Disposición 1.1", "Transitorio primero"
    ruta: list[str] = field(default_factory=list)
    texto: str = ""

    def a_dict(self) -> dict[str, object]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

# El mismo patrón de ordinales que usa la detección en consultas.
_ORDINAL = ORDINAL


def _partir(texto: str, limite: int = MAX_CARACTERES) -> list[str]:
    """Parte un texto largo en trozos por párrafo, sin cortar palabras."""
    if len(texto) <= limite:
        return [texto]
    partes: list[str] = []
    actual = ""
    for parrafo in texto.split("\n"):
        if actual and len(actual) + len(parrafo) + 1 > limite:
            partes.append(actual.strip())
            actual = ""
        while len(parrafo) > limite:
            corte = parrafo.rfind(" ", 0, limite)
            corte = corte if corte > limite // 2 else limite
            partes.append(parrafo[:corte].strip())
            parrafo = parrafo[corte:]
        actual = f"{actual}\n{parrafo}" if actual else parrafo
    if actual.strip():
        partes.append(actual.strip())
    return partes


def _emitir(
    salida: list[Fragmento], clave: str | None, etiqueta: str, ruta: list[str], texto: str
) -> None:
    texto = texto.strip()
    if not texto:
        return
    partes = _partir(texto)
    for i, parte in enumerate(partes, 1):
        etq = etiqueta if len(partes) == 1 else f"{etiqueta} (parte {i} de {len(partes)})"
        salida.append(Fragmento(len(salida), clave, etq, list(ruta), parte))


def _ordinal(texto: str) -> str:
    return " ".join(texto.lower().replace("-", " ").split())


# ---------------------------------------------------------------------------
# Transitorios: el bloque de la norma y uno por cada decreto que la reformó
# ---------------------------------------------------------------------------

_MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
_FECHA_LARGA = re.compile(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})", re.IGNORECASE)
_FECHA_DOF = re.compile(r"\bDOF\s+(\d{2})-(\d{2})-(\d{4})")


def fecha_en(texto: str) -> str | None:
    """Primera fecha del texto como AAAA-MM-DD ('9 de marzo de 2021' o 'DOF 09-03-2021')."""
    m = _FECHA_DOF.search(texto)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    for m in _FECHA_LARGA.finditer(texto):
        mes = _MESES.get(normalizar(m.group(2)))
        if mes:
            return f"{m.group(3)}-{mes:02d}-{int(m.group(1)):02d}"
    return None


class _Transitorios:
    """Rastrea en qué bloque de transitorios estamos para que cada uno tenga clave propia.

    Bloque 0: los transitorios de la norma ("transitorio segundo"). Después, cada decreto de
    reforma abre un bloque con su fecha del DOF ("transitorio segundo (dof 2021-03-09)"). Los
    artículos de un decreto ("ARTÍCULO TERCERO. Se expide...") no son transitorios: sólo se
    reconocen transitorios después de una línea "Transitorios".
    """

    def __init__(self) -> None:
        self.n = 0
        self.contexto = "Transitorios"
        self.fecha: str | None = None
        self.tipo = "norma"
        self.activo = False
        self.unidades = 0

    def abrir(self) -> None:
        self.n, self.contexto, self.fecha, self.tipo = 0, "Transitorios", None, "norma"
        self.activo, self.unidades = True, 0

    def decreto(self, encabezado: str) -> None:
        self.n += 1
        self.contexto = encabezado.strip("*# ").strip()[:160]
        self.fecha = fecha_en(encabezado)
        self.tipo = "decreto"
        self.activo, self.unidades = False, 0

    def seccion(self, encabezado: str) -> None:
        """'ARTÍCULOS TRANSITORIOS DE DECRETOS DE REFORMA': sólo un separador."""
        self.contexto = encabezado.strip("*# ").strip()[:160]
        self.activo = False

    def marca(self) -> None:
        """Línea 'Transitorios' dentro de la región."""
        if self.activo and self.unidades:
            # Segundo juego de transitorios sin decreto nuevo: los del decreto de expedición.
            self.n += 1
            if self.tipo == "norma":
                self.contexto, self.tipo = "Transitorios del decreto de expedición", "expedicion"
        self.activo, self.unidades = True, 0

    def mirar(self, linea: str) -> None:
        """'Publicado en el Diario Oficial de la Federación el 9 de marzo de 2021'."""
        limpia = linea.strip("*_ ").strip()
        if self.n > 0 and not self.activo and not self.fecha and limpia.startswith("Publicad"):
            self.fecha = fecha_en(limpia)

    def unidad(self, ordinal: str) -> tuple[str, str]:
        self.unidades += 1
        clave, etiqueta = f"transitorio {normalizar(ordinal)}", f"Transitorio {ordinal}"
        if self.n == 0:
            return clave, etiqueta
        if self.fecha:
            a, m, d = self.fecha.split("-")
            return f"{clave} (dof {self.fecha})", f"{etiqueta} del decreto DOF {d}-{m}-{a}"
        if self.tipo == "expedicion":
            return f"{clave} (decreto de expedicion)", f"{etiqueta} del decreto de expedición"
        return f"{clave} (bloque {self.n})", f"{etiqueta} (bloque {self.n})"


_PARTE = re.compile(r" \(parte \d+ de \d+\)$")


def _claves_unicas(fragmentos: list[Fragmento]) -> list[Fragmento]:
    """Si dos unidades distintas comparten clave, la segunda pasa a 'clave [2]'.

    Las partes de un mismo artículo largo son consecutivas y conservan su clave.
    """
    vistas: dict[str, int] = {}
    anterior: tuple[str | None, str] | None = None
    sufijo = ""
    for f in fragmentos:
        base = _PARTE.sub("", f.etiqueta)
        actual = (f.clave, base)
        if f.clave is None:
            anterior = actual
            continue
        parte = _PARTE.search(f.etiqueta)
        continua = parte is not None and not parte.group(0).startswith(" (parte 1 ")
        if actual != anterior or not continua:
            vistas[f.clave] = vistas.get(f.clave, 0) + 1
            n = vistas[f.clave]
            sufijo = f" [{n}]" if n > 1 else ""
        if sufijo:
            f.etiqueta = f"{base}{sufijo}{parte.group(0) if parte else ''}"
            f.clave = f"{f.clave}{sufijo}"
        anterior = actual
    return fragmentos


# ---------------------------------------------------------------------------
# Markdown de leyes-mx
# ---------------------------------------------------------------------------

_MD_TITULO = re.compile(r"^(#{1,6})\s+(.*)$")
_MD_ARTICULO = re.compile(
    r"^Art[íi]culo\s+(\d+)\s*[oº°]?\.?\s*((?:bis|ter|qu[aá]ter|quinquies|sexies)?)(?![a-z0-9])",
    re.IGNORECASE,
)
_MD_TRANSITORIO = re.compile(rf"^\*\*(?:Art[íi]culo\s+)?({_ORDINAL})\.?\s*-?\*\*", re.IGNORECASE)
_MD_MARCA = re.compile(r"^\**\s*(?:ART[ÍI]CULOS?\s+)?TRANSITORIOS?\s*\**$", re.IGNORECASE)
_MD_REFORMAS = re.compile(r"DECRETOS? DE REFORMA", re.IGNORECASE)
# Inicio de otro instrumento dentro de la región de transitorios (decreto, sentencia, acuerdo).
_INSTRUMENTO = re.compile(
    r"^(?:DECRETO|ACUERDO|RESOLUCI[ÓO]N)\s+(?:por (?:el|la) que|que|mediante)"
    r"|^(?:PUNTOS )?RESOLUTIVOS\b|^SENTENCIA\b",
    re.IGNORECASE,
)


def trocear_markdown(md: str) -> list[Fragmento]:
    """Trocea el Markdown de leyes-mx (artículos en encabezados de nivel 4 o 5)."""
    if md.startswith("---"):
        fin = md.find("\n---", 3)
        md = md[fin + 4 :] if fin != -1 else md
    salida: list[Fragmento] = []
    ruta: dict[int, str] = {}
    clave: str | None = None
    etiqueta = "Encabezado"
    buffer: list[str] = []
    en_transitorios = False
    tr = _Transitorios()
    nivel_encabezado: int | None = None  # último encabezado sin artículo: su rubro puede seguir

    def ruta_actual() -> list[str]:
        return [tr.contexto] if en_transitorios else [ruta[n] for n in sorted(ruta)]

    def vaciar() -> None:
        nonlocal buffer, nivel_encabezado
        contenido = "\n".join(buffer).strip()
        if (
            clave is None
            and nivel_encabezado is not None
            and contenido
            and "\n" not in contenido
            and len(contenido) < 200
        ):
            # "## TÍTULO · CUARTO" seguido de "DE LA TRANSMISIÓN...": es el rubro, no un fragmento.
            ruta[nivel_encabezado] = f"{ruta[nivel_encabezado]} · {contenido}"
        else:
            _emitir(salida, clave, etiqueta, ruta_actual(), contenido)
        buffer = []
        nivel_encabezado = None

    for linea in md.splitlines():
        limpia = linea.strip()
        m = _MD_TITULO.match(linea)
        if m:
            nivel, texto = len(m.group(1)), m.group(2).strip()
            art = _MD_ARTICULO.match(texto)
            if art and not en_transitorios:
                vaciar()
                clave = clave_articulo(art.group(1), art.group(2))
                etiqueta = f"Artículo {clave}"
                continue
            if nivel == 1:
                continue
            vaciar()
            if not en_transitorios and _MD_MARCA.match(texto):
                en_transitorios = True
                tr.abrir()
                clave, etiqueta = None, "Transitorios"
                continue
            if en_transitorios:
                if _MD_REFORMAS.search(texto):
                    tr.seccion(texto)
                elif _MD_MARCA.match(texto):
                    tr.marca()
                else:
                    tr.decreto(texto)
                clave, etiqueta = None, tr.contexto[:120]
                continue
            ruta = {n: t for n, t in ruta.items() if n < nivel}
            ruta[nivel] = texto
            clave, etiqueta = None, texto
            nivel_encabezado = nivel
            continue

        if en_transitorios:
            if _MD_MARCA.match(limpia):
                vaciar()
                tr.marca()
                clave, etiqueta = None, tr.contexto[:120]
                continue
            if _INSTRUMENTO.match(limpia) and len(limpia) < 300:
                vaciar()
                tr.decreto(limpia)
                clave, etiqueta = None, tr.contexto[:120]
                buffer.append(linea)
                continue
            tr.mirar(limpia)
            t = _MD_TRANSITORIO.match(limpia) if tr.activo else None
            if t:
                vaciar()
                clave, etiqueta = tr.unidad(_ordinal(t.group(1)))
        buffer.append(linea.replace("**", ""))
    vaciar()
    return _claves_unicas([f for f in salida if len(f.texto) > 20])


_TX_TITULO = re.compile(r"^(T[ÍI]TULO|LIBRO)\s+\S+.*$")
_TX_CAPITULO = re.compile(r"^(CAP[ÍI]TULO|Cap[íi]tulo)\s+[\dIVXLC]+\b.*$")
_TX_SECCION = re.compile(r"^(SECCI[ÓO]N|Secci[óo]n)\s+\S+.*$")
_TX_ARTICULO = re.compile(
    r"^(?:Art[íi]culo|ART[ÍI]CULO)\s+(\d{1,4})\s*[o°º]?\.?\s*"
    r"((?:Bis|BIS|bis|Ter|TER|ter|Qu[aá]ter|QU[AÁ]TER)?)\s*[\.\-–]",
)
_TX_DISPOSICION = re.compile(r"^(\d{1,2}\.\d{1,2})\.?\s+\S")
_TX_TRANSITORIOS = re.compile(r"^(?:ART[ÍI]CULOS\s+)?TRANSITORIOS?\b|^Transitorios?\s*$")
_TX_TRANSITORIO = re.compile(
    rf"^(?:Art[íi]culo\s+|ART[ÍI]CULO\s+)?({_ORDINAL})\s*\.?\s*[\.\-–]",
    re.IGNORECASE,
)
_TX_DECRETO = _INSTRUMENTO
_TX_REFORMAS = re.compile(r"DECRETOS? DE REFORMA", re.IGNORECASE)
_TX_ANEXO = re.compile(r"^(?:Anexo|ANEXO)\s+(?:[ÚU]nico|[ÚU]NICO|[IVXLC]+|\d+|[A-Z])\b")


def _es_rubro(linea: str) -> bool:
    """Línea corta que nombra un título o capítulo y no abre una unidad."""
    if any(
        p.match(linea)
        for p in (
            _TX_ARTICULO,
            _TX_DISPOSICION,
            _TX_CAPITULO,
            _TX_TITULO,
            _TX_SECCION,
            _TX_TRANSITORIOS,
        )
    ):
        return False
    corta_sin_cierre = len(linea) < 140 and not linea.endswith((".", ";", ":"))
    return corta_sin_cierre or (len(linea) < 80 and linea.isupper())


def _modo(lineas: list[str]) -> str:
    articulos = sum(1 for linea in lineas if _TX_ARTICULO.match(linea))
    disposiciones = sum(1 for linea in lineas if _TX_DISPOSICION.match(linea))
    if articulos >= 3:
        return "articulo"
    if disposiciones >= 3:
        return "disposicion"
    return "bloque"


def trocear_texto(texto: str) -> list[Fragmento]:
    """Trocea texto plano detectando la jerarquía legal mexicana."""
    lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
    modo = _modo(lineas)
    salida: list[Fragmento] = []
    titulo = capitulo = seccion = ""
    clave: str | None = None
    etiqueta = "Preámbulo"
    buffer: list[str] = []
    en_transitorios = False
    tr = _Transitorios()
    vistos_unidad = False
    rubro_pendiente = ""  # "capitulo", "titulo" o "seccion": la línea siguiente puede ser su rubro

    def ruta_actual() -> list[str]:
        if en_transitorios:
            return [tr.contexto]
        return [r for r in (titulo, capitulo, seccion) if r]

    def vaciar() -> None:
        nonlocal buffer
        _emitir(salida, clave, etiqueta, ruta_actual(), "\n".join(buffer))
        buffer = []

    for i, linea in enumerate(lineas):
        if (
            not en_transitorios
            and _TX_TRANSITORIOS.match(linea)
            and vistos_unidad
            and any(_TX_TRANSITORIO.match(sig) for sig in lineas[i + 1 : i + 4])
        ):
            vaciar()
            en_transitorios = True
            tr.abrir()
            clave, etiqueta = None, "Transitorios"
            continue
        if _TX_ANEXO.match(linea) and len(linea) < 160 and vistos_unidad:
            vaciar()
            en_transitorios = False
            titulo, capitulo, seccion = linea, "", ""
            clave, etiqueta = None, linea[:120]
            buffer.append(linea)
            continue
        if en_transitorios:
            if _TX_REFORMAS.search(linea) and len(linea) < 120:
                vaciar()
                tr.seccion(linea)
                clave, etiqueta = None, tr.contexto[:120]
                continue
            if _TX_DECRETO.match(linea):
                vaciar()
                tr.decreto(linea)
                clave, etiqueta = None, tr.contexto[:120]
                buffer.append(linea)
                continue
            if _TX_TRANSITORIOS.match(linea) and len(linea) < 60:
                vaciar()
                tr.marca()
                clave, etiqueta = None, tr.contexto[:120]
                continue
            tr.mirar(linea)
            t = _TX_TRANSITORIO.match(linea) if tr.activo else None
            if t:
                vaciar()
                clave, etiqueta = tr.unidad(_ordinal(t.group(1)))
            buffer.append(linea)
            continue

        if rubro_pendiente and not buffer and _es_rubro(linea):
            # "CAPÍTULO I" seguido de "Disposiciones generales": el rubro es parte del nombre.
            if rubro_pendiente == "titulo":
                titulo = f"{titulo} · {linea}"
            elif rubro_pendiente == "capitulo":
                capitulo = f"{capitulo} · {linea}"
            else:
                seccion = f"{seccion} · {linea}"
            rubro_pendiente = ""
            continue
        rubro_pendiente = ""
        if _TX_TITULO.match(linea) and len(linea) < 200:
            vaciar()
            titulo, capitulo, seccion = linea, "", ""
            clave, etiqueta = None, linea[:120]
            rubro_pendiente = "titulo"
            continue
        if _TX_CAPITULO.match(linea) and len(linea) < 200:
            vaciar()
            capitulo, seccion = linea, ""
            clave, etiqueta = None, linea[:120]
            rubro_pendiente = "capitulo"
            continue
        if _TX_SECCION.match(linea) and len(linea) < 200:
            vaciar()
            seccion = linea
            clave, etiqueta = None, linea[:120]
            rubro_pendiente = "seccion"
            continue

        if modo == "articulo":
            a = _TX_ARTICULO.match(linea)
            if a:
                vaciar()
                vistos_unidad = True
                clave = clave_articulo(a.group(1), a.group(2))
                etiqueta = f"Artículo {clave}"
        elif modo == "disposicion":
            d = _TX_DISPOSICION.match(linea)
            if d:
                vaciar()
                vistos_unidad = True
                clave = d.group(1)
                etiqueta = f"Disposición {clave}"
        buffer.append(linea)
    vaciar()
    return _sin_indices(salida)


def _sin_indices(fragmentos: list[Fragmento]) -> list[Fragmento]:
    """Quita entradas de índice: una línea corta que aparece ANTES de la unidad completa.

    Nunca toca transitorios ni partes de artículos largos, que pueden ser cortas y legítimas.
    """
    primero_largo: dict[str, int] = {}
    for i, f in enumerate(fragmentos):
        if f.clave and len(f.texto) >= 120 and f.clave not in primero_largo:
            primero_largo[f.clave] = i
    limpios = []
    for i, f in enumerate(fragmentos):
        es_indice = (
            f.clave is not None
            and not f.clave.startswith("transitorio")
            and "(parte" not in f.etiqueta
            and len(f.texto) < 120
            and "\n" not in f.texto
            and i < primero_largo.get(f.clave, -1)
        )
        if len(f.texto) > 20 and not es_indice:
            limpios.append(f)
    for i, f in enumerate(limpios):
        f.orden = i
    return _claves_unicas(limpios)


def trocear(contenido: str, formato: str) -> list[Fragmento]:
    if formato == "markdown":
        return trocear_markdown(contenido)
    return trocear_texto(contenido)
