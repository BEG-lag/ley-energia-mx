"""Textos troceados del corpus (``corpus/textos/<id>.json``), versionados en git.

Separar la descarga (``actualizar``, necesita red) del índice (``indexar``, no la necesita)
hace que el índice se pueda reconstruir igual en cualquier máquina y en CI.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from . import chunker, ingesta
from .config import DIR_TEXTOS
from .fuentes import Documento, Manifiesto


def ruta(doc_id: str) -> Path:
    return DIR_TEXTOS / f"{doc_id}.json"


def actualizar(doc: Documento, *, refrescar: bool = False) -> dict[str, Any]:
    """Descarga (o lee de caché), trocea y guarda el texto de un documento."""
    fuente = ingesta.obtener(doc, refrescar=refrescar)
    fragmentos = chunker.trocear(fuente.contenido, fuente.formato)
    anterior = leer(doc.id)
    extraido = (
        anterior["extraido"]
        if anterior and anterior.get("sha256") == fuente.sha256
        else dt.date.today().isoformat()
    )
    datos = {
        "id": doc.id,
        "origen": fuente.origen,
        "sha256": fuente.sha256,
        "extraido": extraido,
        "fragmentos": [f.a_dict() for f in fragmentos],
    }
    DIR_TEXTOS.mkdir(parents=True, exist_ok=True)
    ruta(doc.id).write_text(
        json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return datos


def leer(doc_id: str) -> dict[str, Any] | None:
    archivo = ruta(doc_id)
    if not archivo.exists():
        return None
    datos: dict[str, Any] = json.loads(archivo.read_text(encoding="utf-8"))
    return datos


def faltantes(manifiesto: Manifiesto) -> list[str]:
    return [d.id for d in manifiesto.documentos if not ruta(d.id).exists()]
