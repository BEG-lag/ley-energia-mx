"""Web local: la misma página del sitio público más la búsqueda híbrida completa.

Escucha sólo en 127.0.0.1 por omisión, no tiene endpoints que escriban ni disparen procesos y
manda cabeceras de seguridad con una CSP estricta (la página no carga nada de terceros).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.staticfiles import StaticFiles

from . import indice
from .busqueda import Buscador, Filtros
from .config import AVISO_LEGAL, DIR_WEB

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
    "form-action 'none'"
)
CABECERAS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
FECHA = r"^\d{4}-\d{2}-\d{2}$"


@lru_cache(maxsize=1)
def _buscador() -> Buscador:
    return Buscador(indice.abrir())


def _modo(b: Buscador) -> str:
    return "hibrido" if b.meta.get("modelo") else "lexico"


def crear_app() -> FastAPI:
    app = FastAPI(title="ley-energia-mx", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def seguridad(request: Request, call_next):  # type: ignore[no-untyped-def]
        respuesta: Response = await call_next(request)
        respuesta.headers.update(CABECERAS)
        return respuesta

    @app.get("/api/estado")
    def estado() -> dict[str, Any]:
        b = _buscador()
        return {"modo": _modo(b), "meta": b.meta, "aviso": AVISO_LEGAL}

    @app.get("/api/buscar")
    def buscar(
        q: Annotated[str, Query(min_length=1, max_length=500)],
        k: Annotated[int, Query(ge=1, le=30)] = 10,
        tipo: Annotated[str | None, Query(pattern="^(ley|reglamento|dacg)$")] = None,
        emisor: Annotated[str | None, Query(max_length=80)] = None,
        abrogados: bool = False,
        fecha: Annotated[str | None, Query(pattern=FECHA)] = None,
    ) -> dict[str, Any]:
        try:
            filtros = Filtros(tipo=tipo, emisor=emisor, incluir_abrogados=abrogados, fecha=fecha)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        b = _buscador()
        res = b.buscar(q, k=k, filtros=filtros)
        return {"modo": _modo(b), "resultados": [r.a_dict(max_caracteres=900) for r in res]}

    @app.get("/api/articulo")
    def articulo(
        doc: Annotated[str, Query(max_length=80)],
        clave: Annotated[str, Query(max_length=80)],
    ) -> dict[str, Any]:
        partes = _buscador().articulo(doc, clave)
        if not partes:
            raise HTTPException(404, "artículo no encontrado")
        base = partes[0].a_dict()
        base["texto"] = "\n\n".join(p.texto for p in partes)
        return base

    app.mount("/", StaticFiles(directory=DIR_WEB, html=True), name="web")
    return app
