"""Embeddings locales (ONNX vía fastembed). Sin llaves ni servicios externos.

El modelo se descarga una vez de Hugging Face y queda en ``~/.cache/ley-energia-mx/modelos``.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

import numpy as np

from .config import DIR_MODELOS, MODELO_EMBEDDINGS


@lru_cache(maxsize=1)
def _modelo():  # type: ignore[no-untyped-def]
    from fastembed import TextEmbedding

    DIR_MODELOS.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(MODELO_EMBEDDINGS, cache_dir=str(DIR_MODELOS))


def vectorizar(textos: Iterable[str], *, lote: int = 64) -> np.ndarray:
    """Vectores normalizados (norma 1) en float32, uno por texto."""
    lista = list(textos)
    if not lista:
        return np.zeros((0, 0), dtype=np.float32)
    vecs = np.array(list(_modelo().embed(lista, batch_size=lote)), dtype=np.float32)
    normas = np.linalg.norm(vecs, axis=1, keepdims=True)
    normas[normas == 0] = 1.0
    return vecs / normas


def texto_para_vector(titulo: str, etiqueta: str, ruta: list[str], texto: str) -> str:
    """Lo que se vectoriza de cada fragmento: contexto primero, luego el cuerpo."""
    contexto = " > ".join(ruta[-2:])
    return f"{titulo}. {etiqueta}. {contexto}. {texto}"[:1200]
