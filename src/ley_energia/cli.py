"""Línea de comandos: ``uv run ley-energia --help``."""

from __future__ import annotations

import json
import sys

import click

from . import corpus, fuentes, indice
from .busqueda import Buscador, Filtros
from .config import AVISO_LEGAL, RUTA_INDICE


def _buscador() -> Buscador:
    return Buscador(indice.abrir())


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="ley-energia-mx")
def cli() -> None:
    """Regulación energética mexicana, consultable por artículo y lista para Claude (MCP)."""


@cli.command()
@click.option("--solo", multiple=True, help="Sólo estos ids del manifiesto.")
@click.option("--refrescar", is_flag=True, help="Vuelve a descargar aunque haya caché.")
def actualizar(solo: tuple[str, ...], refrescar: bool) -> None:
    """Descarga las fuentes oficiales y guarda el texto troceado en corpus/textos."""
    m = fuentes.cargar()
    for doc in m.documentos:
        if solo and doc.id not in solo:
            continue
        datos = corpus.actualizar(doc, refrescar=refrescar)
        click.echo(f"{doc.id:44} {len(datos['fragmentos']):>4} fragmentos")


@cli.command()
@click.option("--sin-vectores", is_flag=True, help="Sólo índice léxico (más rápido).")
def indexar(sin_vectores: bool) -> None:
    """Construye data/ley-energia.sqlite desde corpus/textos (sin red, salvo el modelo)."""
    m = fuentes.cargar()
    r = indice.construir(m, con_vectores=not sin_vectores, avance=True)
    click.echo(f"Índice listo: {r['documentos']} documentos, {r['fragmentos']} fragmentos")
    click.echo(f"  {RUTA_INDICE}")


@cli.command("exportar-web")
def exportar_web_cmd() -> None:
    """Genera web/datos/ para el sitio estático."""
    from .web import exportar

    r = exportar(_buscador())
    click.echo(f"web/datos listo: {r['documentos']} documentos, {r['bytes'] // 1024} KB")


@cli.command()
@click.option("--sin-vectores", is_flag=True)
@click.pass_context
def build(ctx: click.Context, sin_vectores: bool) -> None:
    """indexar + exportar-web."""
    ctx.invoke(indexar, sin_vectores=sin_vectores)
    ctx.invoke(exportar_web_cmd)


@cli.command()
@click.argument("consulta")
@click.option("-k", default=5, show_default=True)
@click.option("--tipo", type=click.Choice(["ley", "reglamento", "dacg"]))
@click.option("--emisor")
@click.option("--abrogados", is_flag=True, help="Incluye normas abrogadas.")
@click.option("--fecha", help="Régimen vigente en esta fecha (AAAA-MM-DD).")
@click.option("--json", "como_json", is_flag=True)
def buscar(
    consulta: str,
    k: int,
    tipo: str | None,
    emisor: str | None,
    abrogados: bool,
    fecha: str | None,
    como_json: bool,
) -> None:
    """Búsqueda híbrida con cita de documento y artículo."""
    b = _buscador()
    try:
        filtros = Filtros(tipo=tipo, emisor=emisor, incluir_abrogados=abrogados, fecha=fecha)
    except ValueError as e:
        raise click.BadParameter(str(e)) from e
    res = b.buscar(consulta, k=k, filtros=filtros)
    if como_json:
        click.echo(json.dumps([r.a_dict() for r in res], ensure_ascii=False, indent=1))
        return
    for i, r in enumerate(res, 1):
        estado = (
            "vigente" if r.doc["abrogada_desde"] is None else f"abrogada {r.doc['abrogada_desde']}"
        )
        click.secho(f"{i}. {r.cita}  [{estado}]", bold=True)
        click.echo(f"   {r.doc['titulo']}")
        click.echo(f"   {' > '.join(r.ruta)}" if r.ruta else "", nl=bool(r.ruta))
        click.echo(f"   {r.texto[:280].replace(chr(10), ' ')}...")
        click.echo(f"   {r.doc['url_oficial']}\n")
    click.echo(AVISO_LEGAL, err=True)


@cli.command()
@click.argument("documento")
@click.argument("numero")
def articulo(documento: str, numero: str) -> None:
    """Texto completo de un artículo. Ej.: ley-energia articulo LSE 20"""
    b = _buscador()
    partes = b.articulo(documento, numero)
    if not partes:
        raise click.ClickException(f"no encontré el artículo {numero} en {documento}")
    click.secho(partes[0].cita.split(" (parte")[0], bold=True)
    for p in partes:
        click.echo(p.texto + "\n")
    click.echo(partes[0].doc["url_oficial"])


@cli.command()
@click.argument("documento")
def linaje(documento: str) -> None:
    """Qué sustituye y qué lo sustituyó."""
    click.echo(json.dumps(_buscador().linaje(documento), ensure_ascii=False, indent=1))


@cli.command()
def stats() -> None:
    """Resumen del índice."""
    b = _buscador()
    por_tipo: dict[str, int] = {}
    for d in b.docs.values():
        por_tipo[d["tipo"]] = por_tipo.get(d["tipo"], 0) + 1
    vig = sum(1 for d in b.docs.values() if d["abrogada_desde"] is None)
    click.echo(
        json.dumps(
            {**b.meta, "por_tipo": por_tipo, "vigentes": vig, "abrogados": len(b.docs) - vig},
            ensure_ascii=False,
            indent=1,
        )
    )


@cli.command()
@click.option("--sin-vectores", is_flag=True)
@click.option("-v", "--detalle", is_flag=True, help="Muestra cada caso.")
@click.option("--guardar", is_flag=True, help="Guarda el resumen en evaluacion/resultados.json.")
@click.option(
    "--umbral-recall",
    type=float,
    help="En vez de exigir todos los casos: falla si recall@k queda abajo de esto "
    "o si falla un caso crítico (artículo exacto, primer lugar, vigencia).",
)
@click.option("--umbral-mrr", type=float, help="Falla si el MRR queda abajo de esto.")
def evaluar(
    sin_vectores: bool,
    detalle: bool,
    guardar: bool,
    umbral_recall: float | None,
    umbral_mrr: float | None,
) -> None:
    """Corre el set de evaluación (evaluacion/golden.yaml) y reporta recall@5 y MRR."""
    from .evaluacion import RUTA_RESULTADOS, correr

    r = correr(_buscador(), vectores=not sin_vectores, detalle=detalle)
    resumen = r["resumen"]
    click.echo(json.dumps(resumen, ensure_ascii=False, indent=1))
    if guardar:
        RUTA_RESULTADOS.write_text(
            json.dumps(r, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    if umbral_recall is None and umbral_mrr is None:
        if resumen["fallos"]:
            sys.exit(1)
        return
    if resumen["fallos_criticos"]:
        sys.exit(1)
    if umbral_recall is not None and resumen["recall_at_k"] < umbral_recall:
        sys.exit(1)
    if umbral_mrr is not None and resumen["mrr"] < umbral_mrr:
        sys.exit(1)


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True)
def serve(host: str, port: int) -> None:
    """Web local con búsqueda híbrida completa."""
    import uvicorn

    from .servidor import crear_app

    uvicorn.run(crear_app(), host=host, port=port)


@cli.command()
def mcp() -> None:
    """Servidor MCP (stdio) para Claude Code y Claude Desktop."""
    from .mcp_server import main

    main()


if __name__ == "__main__":
    cli()
