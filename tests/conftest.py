"""Índice léxico del corpus real, armado una vez por sesión de pruebas (sin red ni modelo)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ley_energia import fuentes, indice
from ley_energia.busqueda import Buscador


@pytest.fixture(scope="session")
def ruta_indice(tmp_path_factory: pytest.TempPathFactory) -> Path:
    ruta = tmp_path_factory.mktemp("indice") / "prueba.sqlite"
    indice.construir(fuentes.cargar(), ruta, con_vectores=False)
    return ruta


@pytest.fixture(scope="session")
def buscador(ruta_indice: Path) -> Buscador:
    return Buscador(indice.abrir(ruta_indice))
