"""Lectura y validación del manifiesto `corpus/fuentes.yaml`."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import RUTA_FUENTES

TIPOS = ("ley", "reglamento", "dacg")
FORMATOS = ("leyes-mx", "pdf", "dof")


@dataclass(frozen=True)
class Documento:
    id: str
    titulo: str
    tipo: str
    emisor: str
    fecha_pub: str
    formato: str
    url_fuente: str
    url_oficial: str
    abreviatura: str | None = None
    alias: tuple[str, ...] = ()
    vigor_desde: str | None = None
    abrogada_desde: str | None = None
    sustituido_por: str | None = None
    base: str | None = None
    nota_vigencia: str | None = None

    @property
    def vigente(self) -> bool:
        return self.abrogada_desde is None

    @property
    def inicio_vigencia(self) -> str:
        return self.vigor_desde or self.fecha_pub

    def vigente_en(self, fecha: str) -> bool:
        """¿Estaba en vigor en `fecha` (AAAA-MM-DD)?"""
        if fecha < self.inicio_vigencia:
            return False
        return self.abrogada_desde is None or fecha < self.abrogada_desde

    def nombres(self) -> list[str]:
        """Título, sigla y alias: todo lo que puede aparecer en una consulta."""
        return [self.titulo, *([self.abreviatura] if self.abreviatura else []), *self.alias]


@dataclass
class Manifiesto:
    corte: str
    documentos: list[Documento] = field(default_factory=list)

    def por_id(self) -> dict[str, Documento]:
        return {d.id: d for d in self.documentos}


def _fecha(valor: Any, campo: str, doc_id: str) -> str | None:
    if valor is None:
        return None
    texto = str(valor)
    try:
        dt.date.fromisoformat(texto)
    except ValueError as e:
        raise ValueError(f"{doc_id}: {campo} no es una fecha AAAA-MM-DD: {texto!r}") from e
    return texto


def cargar(ruta: Path = RUTA_FUENTES) -> Manifiesto:
    """Lee y valida el manifiesto. Falla con un mensaje claro si algo no cuadra."""
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    docs: list[Documento] = []
    for raw in datos["documentos"]:
        doc_id = raw["id"]
        fuente = raw["fuente"]
        doc = Documento(
            id=doc_id,
            titulo=raw["titulo"],
            tipo=raw["tipo"],
            emisor=raw["emisor"],
            fecha_pub=_fecha(raw["fecha_pub"], "fecha_pub", doc_id) or "",
            formato=fuente["formato"],
            url_fuente=fuente["url"],
            url_oficial=raw["url_oficial"],
            abreviatura=raw.get("abreviatura"),
            alias=tuple(raw.get("alias") or ()),
            vigor_desde=_fecha(raw.get("vigor_desde"), "vigor_desde", doc_id),
            abrogada_desde=_fecha(raw.get("abrogada_desde"), "abrogada_desde", doc_id),
            sustituido_por=raw.get("sustituido_por"),
            base=raw.get("base"),
            nota_vigencia=raw.get("nota_vigencia"),
        )
        docs.append(doc)
    manifiesto = Manifiesto(
        corte=_fecha(datos["corte"], "corte", "manifiesto") or "", documentos=docs
    )
    validar(manifiesto)
    return manifiesto


def validar(m: Manifiesto) -> None:
    ids = [d.id for d in m.documentos]
    repetidos = {i for i in ids if ids.count(i) > 1}
    if repetidos:
        raise ValueError(f"ids repetidos en el manifiesto: {sorted(repetidos)}")
    por_id = m.por_id()
    for d in m.documentos:
        if d.tipo not in TIPOS:
            raise ValueError(f"{d.id}: tipo desconocido {d.tipo!r}")
        if d.formato not in FORMATOS:
            raise ValueError(f"{d.id}: formato desconocido {d.formato!r}")
        if not d.url_oficial.startswith("https://"):
            raise ValueError(f"{d.id}: url_oficial debe ser https")
        if d.sustituido_por and d.sustituido_por not in por_id:
            raise ValueError(f"{d.id}: sustituido_por apunta a {d.sustituido_por!r}, que no existe")
        if d.abrogada_desde and not d.sustituido_por:
            raise ValueError(f"{d.id}: abrogado sin sustituido_por")
        if d.sustituido_por and not d.abrogada_desde:
            raise ValueError(f"{d.id}: tiene sustituido_por pero no abrogada_desde")
        if d.abrogada_desde and d.abrogada_desde <= d.fecha_pub:
            raise ValueError(f"{d.id}: abrogada_desde anterior a fecha_pub")
        if d.fecha_pub > m.corte:
            raise ValueError(f"{d.id}: publicado después del corte del corpus")
        if d.vigor_desde and d.vigor_desde < d.fecha_pub:
            raise ValueError(f"{d.id}: vigor_desde anterior a fecha_pub")
        if d.sustituido_por and d.abrogada_desde:
            sucesor = por_id[d.sustituido_por]
            if sucesor.inicio_vigencia != d.abrogada_desde:
                # Sin hueco ni traslape: el día que deja de regir uno empieza el otro.
                raise ValueError(
                    f"{d.id}: abrogada_desde {d.abrogada_desde} no coincide con el inicio de "
                    f"vigencia de {sucesor.id} ({sucesor.inicio_vigencia})"
                )
