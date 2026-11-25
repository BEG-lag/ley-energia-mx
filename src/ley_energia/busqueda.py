"""Búsqueda híbrida con fusión de rangos recíprocos (RRF ponderado).

Señales:
- ``lexica``: BM25 de FTS5 sobre raíces en español (más equivalencias 2014 a 2025).
- ``vectorial``: coseno contra los embeddings locales.
- ``articulo``: coincidencia exacta de la clave del artículo ("8" nunca trae el "80").
- ``documento``: la consulta nombra una ley o un instrumento (por sigla, alias o título).

Cada resultado trae lo necesario para citar: documento, artículo, vigencia y liga oficial.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

import numpy as np

from . import texto
from .config import AVISO_LEGAL

K_RRF = 60
PESOS = {"lexica": 1.0, "vectorial": 0.6, "articulo": 2.5, "documento": 0.9}


TIPOS = ("ley", "reglamento", "dacg")


@dataclass
class Filtros:
    tipo: str | None = None
    emisor: str | None = None
    doc_ids: list[str] | None = None
    incluir_abrogados: bool = False
    fecha: str | None = None  # régimen vigente en esta fecha (AAAA-MM-DD)

    def __post_init__(self) -> None:
        # Una fecha mal escrita no puede devolver en silencio otro régimen.
        if self.fecha:
            try:
                self.fecha = dt.date.fromisoformat(self.fecha.strip()).isoformat()
            except ValueError as e:
                raise ValueError(f"fecha inválida {self.fecha!r}: usa AAAA-MM-DD") from e
        else:
            self.fecha = None
        if self.tipo:
            self.tipo = self.tipo.strip().lower()
            if self.tipo not in TIPOS:
                raise ValueError(f"tipo inválido {self.tipo!r}: usa ley, reglamento o dacg")
        else:
            self.tipo = None


@dataclass
class Resultado:
    fragmento_id: int
    doc: dict[str, Any]
    clave: str | None
    etiqueta: str
    ruta: list[str]
    texto: str
    puntaje: float
    senales: dict[str, int] = field(default_factory=dict)

    @property
    def cita(self) -> str:
        return citar(self.doc, self.etiqueta)

    def a_dict(self, *, max_caracteres: int | None = None) -> dict[str, Any]:
        cuerpo = self.texto
        if max_caracteres and len(cuerpo) > max_caracteres:
            cuerpo = cuerpo[:max_caracteres].rsplit(" ", 1)[0] + " [...]"
        return {
            "cita": self.cita,
            "documento": self.doc["titulo"],
            "documento_id": self.doc["id"],
            "tipo": self.doc["tipo"],
            "emisor": self.doc["emisor"],
            "etiqueta": self.etiqueta,
            "clave": self.clave,
            "ruta": self.ruta,
            "texto": cuerpo,
            "vigente": self.doc["abrogada_desde"] is None,
            "abrogada_desde": self.doc["abrogada_desde"],
            "sustituido_por": self.doc["sustituido_por"],
            "nota_vigencia": self.doc["nota_vigencia"],
            "fecha_pub": self.doc["fecha_pub"],
            "url_oficial": self.doc["url_oficial"],
            "puntaje": round(self.puntaje, 5),
            "senales": self.senales,
        }


def _vigente_en(doc: dict[str, Any], fecha: str) -> bool:
    inicio = doc["vigor_desde"] or doc["fecha_pub"]
    if fecha < inicio:
        return False
    return doc["abrogada_desde"] is None or fecha < doc["abrogada_desde"]


class Buscador:
    """Motor de búsqueda sobre un índice abierto (sólo lectura)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con
        self.docs: dict[str, dict[str, Any]] = {}
        for fila in con.execute("SELECT * FROM documentos"):
            d = dict(fila)
            d["alias"] = json.loads(d["alias"])
            self.docs[d["id"]] = d
        self.meta = {r["clave"]: r["valor"] for r in con.execute("SELECT * FROM meta")}
        self._patrones = self._compilar_nombres()

    # ------------------------------------------------------------------ nombres de documentos

    def _compilar_nombres(self) -> list[tuple[str, re.Pattern[str], bool]]:
        """(doc_id, patrón, es_sigla) para reconocer documentos en la consulta."""
        patrones: list[tuple[str, re.Pattern[str], bool]] = []
        for d in self.docs.values():
            nombres = [d["titulo"], *d["alias"]]
            if d["tipo"] == "reglamento":
                ley = next(
                    (
                        x
                        for x in self.docs.values()
                        if x["tipo"] == "ley" and d["titulo"].endswith(x["titulo"])
                    ),
                    None,
                )
                if ley:
                    # "Reglamento de la LSE", "Reglamento de la Ley de la CFE"...
                    for nombre_ley in [*ley["alias"], ley["abreviatura"]]:
                        if nombre_ley:
                            nombres += [
                                f"reglamento de la {nombre_ley}",
                                f"reglamento {nombre_ley}",
                            ]
            for nombre in nombres:
                norm = texto.normalizar(nombre)
                patrones.append(
                    (d["id"], re.compile(rf"(?<![a-z0-9ñ]){re.escape(norm)}(?![a-z0-9ñ])"), False)
                )
            if d["abreviatura"] and "/" not in d["abreviatura"]:
                # Las siglas se reconocen sólo en mayúsculas para no confundir "lh" o "lie".
                sigla = re.escape(d["abreviatura"])
                patrones.append((d["id"], re.compile(rf"\b{sigla}\b"), True))
            elif d["abreviatura"]:
                patrones.append((d["id"], re.compile(re.escape(d["abreviatura"])), True))
        return patrones

    def detectar_documentos(self, consulta: str) -> list[str]:
        """Documentos nombrados en la consulta; gana el nombre más largo si se traslapan."""
        # Mismo largo en las dos versiones: las posiciones de siglas y nombres se comparan bien.
        sin_acentos = texto.quitar_acentos(consulta)
        norm = sin_acentos.lower()
        hallazgos: list[tuple[int, int, str]] = []
        for doc_id, patron, es_sigla in self._patrones:
            objetivo = sin_acentos if es_sigla else norm
            for m in patron.finditer(objetivo):
                hallazgos.append((m.start(), m.end(), doc_id))
        hallazgos.sort(key=lambda h: (h[0], -(h[1] - h[0])))
        elegidos: list[str] = []
        fin = -1
        for inicio, termino, doc_id in hallazgos:
            if inicio < fin:
                continue  # traslapado con un nombre más largo que ya ganó
            fin = termino
            if doc_id not in elegidos:
                elegidos.append(doc_id)
        return elegidos

    # ------------------------------------------------------------------ filtros

    def _permitidos(self, filtros: Filtros, nombrados: list[str]) -> set[str]:
        ids = set(self.docs)
        if filtros.doc_ids:
            ids &= set(filtros.doc_ids)
        if filtros.tipo:
            ids = {i for i in ids if self.docs[i]["tipo"] == filtros.tipo}
        if filtros.emisor:
            e = texto.normalizar(filtros.emisor)
            ids = {
                i
                for i in ids
                if e in texto.normalizar(self.docs[i]["emisor"])
                or e == texto.normalizar(_sigla_emisor(self.docs[i]["emisor"]))
            }
        if filtros.fecha:
            fecha = filtros.fecha
            ids = {i for i in ids if _vigente_en(self.docs[i], fecha)}
        elif not filtros.incluir_abrogados:
            ids = {i for i in ids if self.docs[i]["abrogada_desde"] is None or i in nombrados}
        return ids

    # ------------------------------------------------------------------ señales

    def _lexica(self, consulta: str, permitidos: set[str], limite: int) -> list[int]:
        raices = list(dict.fromkeys(texto.raices(consulta)))
        frases = [texto.texto_indexable(f) for f in texto.expandir(consulta)]
        terminos = [f'"{r}"' for r in raices] + [f'"{f}"' for f in frases if f]
        if not terminos:
            return []
        expresion = " OR ".join(terminos)
        # El filtro va dentro del SQL, antes del LIMIT: si no, un filtro estrecho (una fecha,
        # un tipo) se queda sin candidatos aunque existan.
        marcas = ",".join("?" * len(permitidos))
        filas = self.con.execute(
            "SELECT f.id FROM fts JOIN fragmentos f ON f.id = fts.rowid "
            f"WHERE fts MATCH ? AND f.doc_id IN ({marcas}) "
            "ORDER BY bm25(fts, 1.0, 0.6) LIMIT ?",
            (expresion, *sorted(permitidos), limite),
        ).fetchall()
        return [r["id"] for r in filas]

    @cached_property
    def _matriz(self) -> tuple[np.ndarray, np.ndarray, list[str]]:
        filas = self.con.execute(
            "SELECT id, doc_id, vector FROM fragmentos WHERE vector IS NOT NULL ORDER BY id"
        ).fetchall()
        if not filas:
            return np.zeros((0, 0), np.float32), np.zeros(0, np.int64), []
        matriz = np.vstack([np.frombuffer(r["vector"], dtype=np.float32) for r in filas])
        ids = np.array([r["id"] for r in filas], dtype=np.int64)
        return matriz, ids, [r["doc_id"] for r in filas]

    def _vectorial(self, consulta: str, permitidos: set[str], limite: int) -> list[int]:
        matriz, ids, doc_ids = self._matriz
        if matriz.size == 0:
            return []
        from .embeddings import vectorizar

        q = vectorizar([consulta])[0]
        sims = matriz @ q
        mascara = np.array([d in permitidos for d in doc_ids])
        sims = np.where(mascara, sims, -2.0)
        mejores = np.argsort(-sims)[:limite]
        return [int(ids[i]) for i in mejores if sims[i] > -2.0]

    def _por_articulo(
        self, claves: list[str], docs: list[str], permitidos: set[str], orden_base: list[int]
    ) -> list[int]:
        marcas = ",".join("?" * len(claves))
        filas = self.con.execute(
            f"SELECT id, doc_id FROM fragmentos WHERE clave IN ({marcas}) ORDER BY doc_id, orden",
            claves,
        ).fetchall()
        candidatos = [(r["id"], r["doc_id"]) for r in filas if r["doc_id"] in permitidos]
        if docs:
            candidatos = [c for c in candidatos if c[1] in docs]
        posicion = {fid: i for i, fid in enumerate(orden_base)}
        prioridad = {d: i for i, d in enumerate(docs)}
        candidatos.sort(key=lambda c: (prioridad.get(c[1], 99), posicion.get(c[0], 10**6), c[0]))
        return [c[0] for c in candidatos]

    def _por_documento(
        self, docs: list[str], permitidos: set[str], orden_base: list[int], limite: int
    ) -> list[int]:
        docs = [d for d in docs if d in permitidos]
        if not docs:
            return []
        ranking = [fid for fid in orden_base if self._doc_de(fid) in docs]
        if len(ranking) < limite:
            marcas = ",".join("?" * len(docs))
            extra = self.con.execute(
                f"SELECT id FROM fragmentos WHERE doc_id IN ({marcas}) ORDER BY orden LIMIT ?",
                (*docs, limite),
            ).fetchall()
            ranking += [r["id"] for r in extra if r["id"] not in ranking]
        return ranking[:limite]

    @cached_property
    def _doc_por_fragmento(self) -> dict[int, str]:
        return {r["id"]: r["doc_id"] for r in self.con.execute("SELECT id, doc_id FROM fragmentos")}

    def _doc_de(self, fid: int) -> str:
        return self._doc_por_fragmento[fid]

    # ------------------------------------------------------------------ API

    def buscar(
        self,
        consulta: str,
        *,
        k: int = 10,
        filtros: Filtros | None = None,
        vectores: bool = True,
    ) -> list[Resultado]:
        consulta = consulta.strip()[:500]
        if not consulta:
            return []
        filtros = filtros or Filtros()
        nombrados = self.detectar_documentos(consulta)
        permitidos = self._permitidos(filtros, nombrados)
        if not permitidos:
            return []
        claves = texto.detectar_articulos(consulta)
        limite = max(100, k * 10)

        senales: dict[str, list[int]] = {"lexica": self._lexica(consulta, permitidos, limite)}
        if vectores:
            senales["vectorial"] = self._vectorial(consulta, permitidos, limite)
        base = _fusionar({n: s for n, s in senales.items()}, PESOS)
        orden_base = [fid for fid, _ in base]
        if claves:
            senales["articulo"] = self._por_articulo(claves, nombrados, permitidos, orden_base)
        if nombrados:
            senales["documento"] = self._por_documento(nombrados, permitidos, orden_base, limite)

        fusion = _fusionar(senales, PESOS)[:k]
        return [self._resultado(fid, puntaje, senales) for fid, puntaje in fusion]

    def _resultado(self, fid: int, puntaje: float, senales: dict[str, list[int]]) -> Resultado:
        fila = self.con.execute("SELECT * FROM fragmentos WHERE id = ?", (fid,)).fetchone()
        rangos = {n: s.index(fid) + 1 for n, s in senales.items() if fid in s}
        return Resultado(
            fragmento_id=fid,
            doc=self.docs[fila["doc_id"]],
            clave=fila["clave"],
            etiqueta=fila["etiqueta"],
            ruta=json.loads(fila["ruta"]),
            texto=fila["texto"],
            puntaje=puntaje,
            senales=rangos,
        )

    def articulo(self, doc_id: str, clave: str) -> list[Resultado]:
        """Texto completo de un artículo (todas sus partes)."""
        doc_id = self.resolver_documento(doc_id) or doc_id
        clave = _clave_desde_texto(clave)
        filas = self.con.execute(
            "SELECT id FROM fragmentos WHERE doc_id = ? AND clave = ? ORDER BY orden",
            (doc_id, clave),
        ).fetchall()
        return [self._resultado(r["id"], 1.0, {}) for r in filas]

    def resolver_documento(self, nombre: str) -> str | None:
        """Acepta id, sigla o nombre y devuelve el id del documento."""
        if nombre in self.docs:
            return nombre
        baja = nombre.strip().lower()
        for d in self.docs.values():
            if d["abreviatura"] and d["abreviatura"].lower() == baja:
                return str(d["id"])
        detectados = self.detectar_documentos(nombre)
        return detectados[0] if detectados else None

    def indice_de(self, doc_id: str) -> list[dict[str, Any]]:
        filas = self.con.execute(
            "SELECT clave, etiqueta, ruta FROM fragmentos WHERE doc_id = ? ORDER BY orden",
            (doc_id,),
        ).fetchall()
        vistos: set[str] = set()
        salida = []
        for r in filas:
            etiqueta = re.sub(r" \(parte \d+ de \d+\)$", "", r["etiqueta"])
            llave = f"{r['clave']}|{etiqueta}"
            if llave in vistos:
                continue
            vistos.add(llave)
            salida.append(
                {"clave": r["clave"], "etiqueta": etiqueta, "ruta": json.loads(r["ruta"])}
            )
        return salida

    def linaje(self, doc_id: str) -> dict[str, Any]:
        """Cadena de sustituciones hacia atrás y hacia adelante."""
        doc_id = self.resolver_documento(doc_id) or doc_id
        if doc_id not in self.docs:
            raise KeyError(doc_id)
        adelante = []
        actual = self.docs[doc_id]
        while actual["sustituido_por"]:
            actual = self.docs[actual["sustituido_por"]]
            adelante.append(_resumen(actual))
        atras = [_resumen(d) for d in self.docs.values() if d["sustituido_por"] == doc_id]
        return {
            "documento": _resumen(self.docs[doc_id]),
            "sustituye_a": atras,
            "sustituido_por": adelante,
        }


def nombre_corto(doc: dict[str, Any]) -> str:
    """Sigla, primer alias o título: lo que se usa en una cita."""
    if doc.get("abreviatura"):
        return str(doc["abreviatura"])
    if doc.get("alias"):
        return str(doc["alias"][0])
    return str(doc["titulo"])


def citar(doc: dict[str, Any], etiqueta: str) -> str:
    """'LSE, artículo 20'; 'DACG de autoconsumo, disposición 1.2'."""
    if re.match(r"^(Artículo|Disposición|Transitorio)\b", etiqueta):
        etiqueta = etiqueta[0].lower() + etiqueta[1:]
    return f"{nombre_corto(doc)}, {etiqueta}"


def _resumen(d: dict[str, Any]) -> dict[str, Any]:
    return {
        k: d[k]
        for k in (
            "id",
            "titulo",
            "abreviatura",
            "tipo",
            "fecha_pub",
            "abrogada_desde",
            "base",
            "url_oficial",
        )
    }


def _sigla_emisor(emisor: str) -> str:
    return "".join(p[0] for p in emisor.split() if p[0].isupper())


_DISPOSICION = re.compile(r"^\d{1,2}\.\d{1,2}(?:\.\d{1,2})?$")


def _clave_desde_texto(valor: str) -> str:
    """'20', 'artículo 20', '8 bis', '1.2', 'segundo transitorio' o una clave completa."""
    valor = " ".join(valor.strip().split())
    if _DISPOSICION.match(valor):
        return valor
    norm = texto.normalizar(valor)
    if norm.startswith("transitorio") and "(" in norm:
        return norm  # clave completa de un transitorio de decreto, tal como la da la búsqueda
    for intento in (valor, f"artículo {valor}"):
        detectadas = texto.detectar_articulos(intento)
        if detectadas:
            return detectadas[0]
    return norm


def _fusionar(senales: dict[str, list[int]], pesos: dict[str, float]) -> list[tuple[int, float]]:
    puntajes: dict[int, float] = {}
    for nombre, ranking in senales.items():
        peso = pesos.get(nombre, 1.0)
        for posicion, fid in enumerate(ranking, 1):
            puntajes[fid] = puntajes.get(fid, 0.0) + peso / (K_RRF + posicion)
    return sorted(puntajes.items(), key=lambda kv: (-kv[1], kv[0]))


AVISO = AVISO_LEGAL
