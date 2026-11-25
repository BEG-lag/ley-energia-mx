"""Índice en un solo archivo SQLite: documentos, fragmentos, FTS5 y vectores.

No necesita servidor ni extensiones: la parte léxica usa FTS5 (incluido en SQLite) sobre
raíces en español, y la parte vectorial guarda los vectores como BLOB y los compara en numpy
(el corpus cabe holgado en memoria).
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from . import corpus, embeddings, texto
from .config import MODELO_EMBEDDINGS, RUTA_INDICE
from .fuentes import Manifiesto

ESQUEMA = """
CREATE TABLE meta (clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE TABLE documentos (
    id TEXT PRIMARY KEY,
    titulo TEXT NOT NULL,
    abreviatura TEXT,
    alias TEXT NOT NULL,           -- JSON
    tipo TEXT NOT NULL,
    emisor TEXT NOT NULL,
    fecha_pub TEXT NOT NULL,
    vigor_desde TEXT,
    abrogada_desde TEXT,
    sustituido_por TEXT,
    base TEXT,
    nota_vigencia TEXT,
    url_oficial TEXT NOT NULL,
    origen TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    extraido TEXT NOT NULL,
    fragmentos INTEGER NOT NULL
);
CREATE TABLE fragmentos (
    id INTEGER PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documentos(id),
    orden INTEGER NOT NULL,
    clave TEXT,
    etiqueta TEXT NOT NULL,
    ruta TEXT NOT NULL,            -- JSON
    texto TEXT NOT NULL,
    vector BLOB
);
CREATE INDEX fragmentos_doc ON fragmentos(doc_id, orden);
CREATE INDEX fragmentos_clave ON fragmentos(clave);
CREATE VIRTUAL TABLE fts USING fts5(cuerpo, contexto, tokenize = 'unicode61 remove_diacritics 2');
"""


def construir(
    manifiesto: Manifiesto,
    destino: Path = RUTA_INDICE,
    *,
    con_vectores: bool = True,
    avance: bool = False,
) -> dict[str, int]:
    """Arma el índice desde ``corpus/textos``. Determinista: mismo corpus, mismo índice."""
    faltan = corpus.faltantes(manifiesto)
    if faltan:
        raise FileNotFoundError(
            f"faltan textos de {len(faltan)} documentos ({', '.join(faltan[:5])}...); "
            "corre `ley-energia actualizar`"
        )
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(".tmp")
    temporal.unlink(missing_ok=True)
    con = sqlite3.connect(temporal)
    con.executescript(ESQUEMA)

    filas: list[tuple[int, str, str, list[str], str, str]] = []
    siguiente = 1
    for doc in manifiesto.documentos:
        datos = corpus.leer(doc.id)
        assert datos is not None
        frags = datos["fragmentos"]
        con.execute(
            "INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                doc.id,
                doc.titulo,
                doc.abreviatura,
                json.dumps(list(doc.alias), ensure_ascii=False),
                doc.tipo,
                doc.emisor,
                doc.fecha_pub,
                doc.vigor_desde,
                doc.abrogada_desde,
                doc.sustituido_por,
                doc.base,
                doc.nota_vigencia,
                doc.url_oficial,
                datos["origen"],
                datos["sha256"],
                datos["extraido"],
                len(frags),
            ),
        )
        contexto_doc = " ".join(doc.nombres())
        for f in frags:
            fid = siguiente
            siguiente += 1
            con.execute(
                "INSERT INTO fragmentos (id, doc_id, orden, clave, etiqueta, ruta, texto) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    fid,
                    doc.id,
                    f["orden"],
                    f["clave"],
                    f["etiqueta"],
                    json.dumps(f["ruta"], ensure_ascii=False),
                    f["texto"],
                ),
            )
            contexto = f"{contexto_doc} {f['etiqueta']} {' '.join(f['ruta'])}"
            con.execute(
                "INSERT INTO fts (rowid, cuerpo, contexto) VALUES (?,?,?)",
                (fid, texto.texto_indexable(f["texto"]), texto.texto_indexable(contexto)),
            )
            filas.append((fid, doc.titulo, f["etiqueta"], f["ruta"], f["texto"], doc.id))

    if con_vectores:
        lote = 256
        for i in range(0, len(filas), lote):
            parte = filas[i : i + lote]
            vecs = embeddings.vectorizar(
                embeddings.texto_para_vector(t, e, r, x) for _, t, e, r, x, _ in parte
            )
            con.executemany(
                "UPDATE fragmentos SET vector = ? WHERE id = ?",
                [(v.tobytes(), fid) for v, (fid, *_rest) in zip(vecs, parte, strict=True)],
            )
            if avance:
                print(f"  vectores {min(i + lote, len(filas))}/{len(filas)}", flush=True)

    meta = {
        "corte": manifiesto.corte,
        "construido": dt.date.today().isoformat(),
        "documentos": str(len(manifiesto.documentos)),
        "fragmentos": str(len(filas)),
        "modelo": MODELO_EMBEDDINGS if con_vectores else "",
        "version": "1",
    }
    con.executemany("INSERT INTO meta VALUES (?,?)", meta.items())
    con.commit()
    con.execute("VACUUM")
    con.close()
    temporal.replace(destino)
    return {"documentos": len(manifiesto.documentos), "fragmentos": len(filas)}


def abrir(ruta: Path = RUTA_INDICE) -> sqlite3.Connection:
    if not ruta.exists():
        raise FileNotFoundError(f"no existe el índice {ruta}; corre `uv run ley-energia indexar`")
    uri = f"{ruta.resolve().as_uri()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con
