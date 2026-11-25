"""Descarga y extracción de texto de las fuentes oficiales.

Tres formatos:
- ``leyes-mx``: Markdown de https://github.com/BEG-lag/leyes-mx (ya limpio y con jerarquía).
- ``pdf``: PDF de la Cámara de Diputados (leyes abrogadas y reglamentos).
- ``dof``: nota del Diario Oficial de la Federación en HTML.

Las descargas se guardan en ``data/cache`` para no volver a pedir lo mismo.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import (
    DIR_CACHE,
    DIR_LEYES_MX,
    PAUSA_ENTRE_DESCARGAS,
    URL_LEYES_MX,
    USER_AGENT,
)
from .fuentes import Documento


@dataclass
class TextoFuente:
    formato: str  # "markdown" o "texto"
    contenido: str
    sha256: str
    origen: str


_ultima_descarga = 0.0


def _descargar(url: str, destino: Path, *, refrescar: bool = False) -> bytes:
    global _ultima_descarga
    if destino.exists() and not refrescar:
        return destino.read_bytes()
    espera = PAUSA_ENTRE_DESCARGAS - (time.monotonic() - _ultima_descarga)
    if espera > 0:
        time.sleep(espera)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120, follow_redirects=True) as c:
        for intento in range(3):
            try:
                r = c.get(url)
                r.raise_for_status()
                break
            except httpx.HTTPError:
                if intento == 2:
                    raise
                time.sleep(3 * (intento + 1))
    _ultima_descarga = time.monotonic()
    destino.write_bytes(r.content)
    return r.content


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


# ---------------------------------------------------------------------------
# leyes-mx
# ---------------------------------------------------------------------------


def _leyes_mx(doc: Documento, refrescar: bool) -> TextoFuente:
    # El origen registrado es siempre la URL pública, se lea de la copia local o de la red.
    url = URL_LEYES_MX.format(slug=doc.url_fuente)
    local = DIR_LEYES_MX / "leyes" / f"{doc.url_fuente}.md"
    if local.exists() and not refrescar:
        datos = local.read_bytes()
    else:
        datos = _descargar(url, DIR_CACHE / f"{doc.id}.md", refrescar=refrescar)
    contenido = datos.decode("utf-8")
    return TextoFuente("markdown", contenido, _sha(contenido.encode("utf-8")), url)


# ---------------------------------------------------------------------------
# PDF de la Cámara de Diputados
# ---------------------------------------------------------------------------

# Encabezados y pies que la Cámara repite en cada página.
_RUIDO_PDF = [
    re.compile(r"^\s*CÁMARA DE DIPUTADOS DEL H\. CONGRESO DE LA UNIÓN\s*$", re.I),
    re.compile(r"^\s*Secretaría General\s*$", re.I),
    re.compile(r"^\s*Secretaría de Servicios Parlamentarios\s*$", re.I),
    re.compile(r"^\s*(Última|Ultima) [Rr]eforma (publicada )?DOF.*$"),
    re.compile(r"^\s*\d+\s+de\s+\d+\s*$"),
    re.compile(r"^\s*[A-Za-zÁÉÍÓÚáéíóúñ ]{0,40}DOF \d{2}-\d{2}-\d{4}\s*$"),
    re.compile(r"^\s*ABROGADA\s*$"),
    re.compile(r"^\s*TEXTO VIGENTE\s*$"),
]


def _extraer_pdf(datos: bytes) -> str:
    import pymupdf

    paginas: list[str] = []
    with pymupdf.open(stream=datos, filetype="pdf") as pdf:
        for pagina in pdf:
            paginas.append(pagina.get_text("text"))
    titulo_repetido = _linea_repetida(paginas)
    lineas: list[str] = []
    for texto in paginas:
        for linea in texto.splitlines():
            if any(p.match(linea) for p in _RUIDO_PDF):
                continue
            if titulo_repetido and linea.strip() == titulo_repetido:
                continue
            lineas.append(linea.rstrip())
    return _reflujo("\n".join(lineas))


def _linea_repetida(paginas: list[str]) -> str | None:
    """Título que aparece como encabezado en la mayoría de las páginas."""
    if len(paginas) < 4:
        return None
    conteo: dict[str, int] = {}
    for texto in paginas:
        for linea in texto.splitlines()[:6]:
            linea = linea.strip()
            if len(linea) > 12 and linea.isupper():
                conteo[linea] = conteo.get(linea, 0) + 1
    if not conteo:
        return None
    linea, veces = max(conteo.items(), key=lambda kv: kv[1])
    return linea if veces >= len(paginas) * 0.6 else None


_INICIO_BLOQUE = re.compile(
    r"^(?:Art[íi]culo\s+\d|ART[ÍI]CULO\s+\d|T[ÍI]TULO\s|CAP[ÍI]TULO\s|Cap[íi]tulo\s+[IVXLC\d]|SECCI[ÓO]N\s|Secci[óo]n\s"
    r"|LIBRO\s|TRANSITORIOS?\b|Transitorios?\b|[IVXL]+\.\s|[a-z]\)\s|\d+\.\s|\d+\.\d+|[A-ZÁÉÍÓÚÑ]{4,}\.?-)"
)


def _reflujo(texto: str) -> str:
    """Une líneas partidas por el ancho de página; conserva los saltos con sentido."""
    salida: list[str] = []
    for linea in texto.splitlines():
        limpia = linea.strip()
        if not limpia:
            if salida and salida[-1] != "":
                salida.append("")
            continue
        if (
            salida
            and salida[-1] != ""
            and not _INICIO_BLOQUE.match(limpia)
            and not salida[-1].endswith((".", ":", ";"))
        ):
            salida[-1] = f"{salida[-1]} {limpia}"
        else:
            salida.append(limpia)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(salida)).strip()


def _pdf(doc: Documento, refrescar: bool) -> TextoFuente:
    datos = _descargar(doc.url_fuente, DIR_CACHE / f"{doc.id}.pdf", refrescar=refrescar)
    contenido = _extraer_pdf(datos)
    return TextoFuente("texto", contenido, _sha(contenido.encode("utf-8")), doc.url_fuente)


# ---------------------------------------------------------------------------
# Nota del DOF
# ---------------------------------------------------------------------------


def _extraer_dof(html: bytes) -> str:
    from bs4 import BeautifulSoup

    texto_html = html.decode("latin-1", errors="replace")
    sopa = BeautifulSoup(texto_html, "lxml")
    nodo = sopa.find(id="DivDetalleNota")
    if nodo is None:
        raise ValueError("la nota del DOF no trae DivDetalleNota")
    for basura in nodo.find_all(["style", "script", "img"]):
        basura.decompose()
    for br in nodo.find_all("br"):
        br.replace_with("\n")
    # El DOF publica cada párrafo como un <div> (o <p>) hoja; las tablas, como <td>.
    bloques: list[str] = []
    for el in nodo.find_all(["div", "p", "td", "li"]):
        if el.find(["div", "p", "td", "li"]):
            continue
        # Sin separador: el DOF parte palabras en varios <span> ("ten" + "sión").
        t = " ".join(el.get_text("").split())
        if t:
            bloques.append(t)
    if not bloques:
        bloques = [" ".join(nodo.get_text("\n").split())]
    return "\n".join(bloques)


def _dof(doc: Documento, refrescar: bool) -> TextoFuente:
    datos = _descargar(doc.url_fuente, DIR_CACHE / f"{doc.id}.html", refrescar=refrescar)
    # El hash va sobre el texto extraído: la página del DOF cambia a diario (tipo de cambio en
    # la barra lateral) aunque la nota sea la misma.
    contenido = _extraer_dof(datos)
    return TextoFuente("texto", contenido, _sha(contenido.encode("utf-8")), doc.url_fuente)


def obtener(doc: Documento, *, refrescar: bool = False) -> TextoFuente:
    """Texto completo de un documento según su formato de fuente."""
    if doc.formato == "leyes-mx":
        return _leyes_mx(doc, refrescar)
    if doc.formato == "pdf":
        return _pdf(doc, refrescar)
    if doc.formato == "dof":
        return _dof(doc, refrescar)
    raise ValueError(f"formato desconocido: {doc.formato}")
