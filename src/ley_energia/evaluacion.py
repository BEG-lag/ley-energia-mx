"""Evaluación de la búsqueda contra ``evaluacion/golden.yaml``: recall@k y MRR."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .busqueda import Buscador, Filtros, Resultado
from .config import RAIZ

RUTA_GOLDEN = RAIZ / "evaluacion" / "golden.yaml"
RUTA_RESULTADOS = RAIZ / "evaluacion" / "resultados.json"


def _coincide(r: Resultado, esperado: dict[str, Any]) -> bool:
    if r.doc["id"] != esperado["doc"]:
        return False
    return "clave" not in esperado or r.clave == str(esperado["clave"])


def correr(
    buscador: Buscador,
    *,
    ruta: Path = RUTA_GOLDEN,
    vectores: bool = True,
    detalle: bool = False,
) -> dict[str, Any]:
    casos = yaml.safe_load(ruta.read_text(encoding="utf-8"))["casos"]
    filas: list[dict[str, Any]] = []
    for caso in casos:
        k = caso.get("k", 5)
        f = caso.get("filtros") or {}
        filtros = Filtros(
            tipo=f.get("tipo"),
            emisor=f.get("emisor"),
            fecha=f.get("fecha"),
            incluir_abrogados=bool(f.get("incluir_abrogados")),
        )
        res = buscador.buscar(caso["consulta"], k=max(k, 10), filtros=filtros, vectores=vectores)
        top = res[:k]
        rango = next(
            (i for i, r in enumerate(res, 1) if any(_coincide(r, e) for e in caso["esperado"])),
            None,
        )
        acierto = rango is not None and rango <= k
        errores: list[str] = []
        if not acierto:
            errores.append(f"esperado fuera del top {k} (rango {rango})")
        if caso.get("primero") and rango != 1:
            errores.append("no quedó en primer lugar")
        intrusos = [r.doc["id"] for r in top if r.doc["id"] in (caso.get("ausentes") or [])]
        if intrusos:
            errores.append(f"aparecen documentos que no deben: {sorted(set(intrusos))}")
        for a in caso.get("ausentes_clave") or []:
            if any(_coincide(r, a) for r in top):
                errores.append(f"aparece {a['doc']} {a['clave']}")
        critico = bool(caso.get("primero") or caso.get("ausentes") or caso.get("ausentes_clave"))
        filas.append(
            {
                "id": caso["id"],
                "rango": rango,
                "acierto": acierto,
                "errores": errores,
                "critico": critico,
                "top": [r.cita for r in top[:3]],
            }
        )
        if detalle:
            marca = "ok " if not errores else "XX "
            print(f"{marca}{caso['id']:38} rango={rango}  {'; '.join(errores)}")
            if errores:
                for c in [r.cita for r in top[:5]]:
                    print(f"      {c}")
    n = len(filas)
    resumen = {
        "casos": n,
        "recall_at_k": round(sum(f["acierto"] for f in filas) / n, 3),
        "mrr": round(sum(1 / f["rango"] for f in filas if f["rango"]) / n, 3),
        "aprobados": sum(1 for f in filas if not f["errores"]),
        "fallos": [f["id"] for f in filas if f["errores"]],
        # Artículo exacto, primer lugar y vigencia: nunca se toleran.
        "fallos_criticos": [f["id"] for f in filas if f["errores"] and f["critico"]],
        "vectores": vectores,
    }
    return {"resumen": resumen, "casos": filas}
