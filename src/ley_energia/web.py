"""Exporta los datos que usa la web estática (GitHub Pages) en ``web/datos``.

- ``catalogo.json``: documentos, linaje, nombres reconocibles y metadatos del corte.
- ``indice.json``: índice invertido BM25 sobre raíces, para buscar en el navegador sin servidor.
- ``docs/<id>.json``: fragmentos completos de cada documento, para leer por artículo.

Las raíces se calculan aquí con el mismo Snowball que usa el índice SQLite; el navegador sólo
consulta el mapa palabra a raíz, así que las dos búsquedas tokenizan igual.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from typing import Any

from . import texto
from .busqueda import Buscador, citar
from .config import AVISO_LEGAL, DIR_WEB_DATOS
from .evaluacion import RUTA_RESULTADOS

EXTRACTO = 320


def _escribir(nombre: str, datos: Any) -> int:
    ruta = DIR_WEB_DATOS / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    contenido = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    ruta.write_text(contenido, encoding="utf-8")
    return len(contenido.encode("utf-8"))


def exportar(b: Buscador) -> dict[str, int]:
    if DIR_WEB_DATOS.exists():
        shutil.rmtree(DIR_WEB_DATOS)
    total = 0

    docs = []
    for d in b.docs.values():
        nombres = [texto.normalizar(n) for n in [d["titulo"], *d["alias"]]]
        docs.append(
            {
                "id": d["id"],
                "titulo": d["titulo"],
                "abreviatura": d["abreviatura"],
                "alias": d["alias"],
                "tipo": d["tipo"],
                "emisor": d["emisor"],
                "fecha_pub": d["fecha_pub"],
                "vigor_desde": d["vigor_desde"],
                "abrogada_desde": d["abrogada_desde"],
                "sustituido_por": d["sustituido_por"],
                "base": d["base"],
                "nota_vigencia": d["nota_vigencia"],
                "url_oficial": d["url_oficial"],
                "fragmentos": d["fragmentos"],
                "articulos": 0,
                "nombres": nombres,
            }
        )

    fragmentos: list[dict[str, Any]] = []
    postings: dict[str, list[float]] = {}
    palabras: dict[str, str] = {}
    longitudes: list[int] = []
    filas = b.con.execute(
        "SELECT f.id, f.doc_id, f.orden, f.clave, f.etiqueta, f.ruta, f.texto, d.titulo, "
        "d.abreviatura FROM fragmentos f JOIN documentos d ON d.id = f.doc_id "
        "ORDER BY f.doc_id, f.orden"
    ).fetchall()
    por_doc: dict[str, list[dict[str, Any]]] = {}
    for idx, r in enumerate(filas):
        ruta = json.loads(r["ruta"])
        fragmentos.append(
            {
                "d": r["doc_id"],
                "o": r["orden"],
                "c": r["clave"],
                "e": r["etiqueta"],
                "x": r["texto"][:EXTRACTO],
            }
        )
        por_doc.setdefault(r["doc_id"], []).append(
            {"o": r["orden"], "c": r["clave"], "e": r["etiqueta"], "r": ruta, "t": r["texto"]}
        )
        # Mismo contexto y peso que la columna "contexto" de FTS5 (bm25 1.0 cuerpo, 0.6 contexto).
        d = b.docs[r["doc_id"]]
        nombres_doc = " ".join([d["titulo"], *(d["alias"] or []), d["abreviatura"] or ""])
        contexto = f"{nombres_doc} {r['etiqueta']} {' '.join(ruta)}"
        cuerpo = [texto.raiz(p) for p in texto.tokens(r["texto"])]
        extra = [texto.raiz(p) for p in texto.tokens(contexto)]
        for p in texto.tokens(r["texto"]) + texto.tokens(contexto):
            palabras[p] = texto.raiz(p)
        raices = cuerpo + extra
        pesos: Counter[str] = Counter(cuerpo)
        for raiz_ctx in extra:
            pesos[raiz_ctx] += 0.6  # type: ignore[assignment]
        longitudes.append(len(raices))
        for raiz, tf in pesos.items():
            postings.setdefault(raiz, []).extend((idx, round(tf, 1)))

    articulos = Counter(
        f["d"] for f in fragmentos if f["c"] and not str(f["c"]).startswith("transitorio")
    )
    for d in docs:
        d["articulos"] = (
            len(
                {
                    f["c"]
                    for f in fragmentos
                    if f["d"] == d["id"] and f["c"] and not str(f["c"]).startswith("transitorio")
                }
            )
            if articulos.get(d["id"])
            else 0
        )

    evaluacion = None
    if RUTA_RESULTADOS.exists():
        res = json.loads(RUTA_RESULTADOS.read_text(encoding="utf-8"))["resumen"]
        evaluacion = {
            "casos": res["casos"],
            "recall_at_k": f"{res['recall_at_k']:.2f}",
            "mrr": f"{res['mrr']:.2f}",
        }
    catalogo = {
        "meta": {**b.meta, "aviso": AVISO_LEGAL, "evaluacion": evaluacion},
        "documentos": docs,
    }
    total += _escribir("catalogo.json", catalogo)
    total += _escribir(
        "indice.json",
        {
            "fragmentos": fragmentos,
            "longitudes": longitudes,
            "postings": postings,
            "palabras": {p: r for p, r in palabras.items() if p != r},
            "vacias": sorted(texto.STOPWORDS),
            "equivalencias": {
                viejo: [texto.raices(n) for n in nuevos]
                for viejo, nuevos in texto.EQUIVALENCIAS.items()
            },
        },
    )
    for doc_id, frs in por_doc.items():
        d = b.docs[doc_id]
        total += _escribir(
            f"docs/{doc_id}.json",
            {
                "id": doc_id,
                "titulo": d["titulo"],
                "fragmentos": [{**f, "cita": citar(d, f["e"])} for f in frs],
            },
        )
    return {"documentos": len(docs), "bytes": total}
