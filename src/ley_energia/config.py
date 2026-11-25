"""Rutas y parámetros. Nada aquí es secreto: el proyecto no usa llaves de ningún servicio."""

from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

RUTA_FUENTES = RAIZ / "corpus" / "fuentes.yaml"
DIR_TEXTOS = RAIZ / "corpus" / "textos"
DIR_WEB = RAIZ / "web"
DIR_WEB_DATOS = DIR_WEB / "datos"

DIR_DATOS = Path(os.environ.get("LEY_ENERGIA_DATOS", RAIZ / "data"))
DIR_CACHE = DIR_DATOS / "cache"
RUTA_INDICE = Path(os.environ.get("LEY_ENERGIA_INDICE", DIR_DATOS / "ley-energia.sqlite"))
DIR_MODELOS = Path(
    os.environ.get("LEY_ENERGIA_MODELOS", Path.home() / ".cache" / "ley-energia-mx" / "modelos")
)

# Carpeta local de leyes-mx (si existe se lee de ahí; si no, del repositorio público).
DIR_LEYES_MX = Path(os.environ.get("LEYES_MX_DIR", RAIZ.parent / "leyes-mx"))
URL_LEYES_MX = "https://raw.githubusercontent.com/BEG-lag/leyes-mx/main/leyes/{slug}.md"

MODELO_EMBEDDINGS = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

USER_AGENT = "ley-energia-mx/1.0 (+https://github.com/BEG-lag/ley-energia-mx)"
PAUSA_ENTRE_DESCARGAS = 1.5  # segundos, por cortesía con los sitios oficiales

AVISO_LEGAL = (
    "Información de fuentes oficiales con fines informativos. No constituye opinión legal ni "
    "asesoría fiscal; valida con la publicación oficial del DOF y con la autoridad competente."
)
