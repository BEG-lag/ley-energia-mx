# ley-energia-mx

Regulación energética mexicana consultable por artículo, con vigencia y linaje, y servidor MCP
para Claude. Español mexicano en código, comentarios y documentos (salvo `README.md`, en inglés).
Nunca usar el guion largo (U+2014): una prueba lo revisa.

## Reglas

- **Sin llaves.** El proyecto no llama a APIs de pago ni lee llaves. Claude entra por MCP con la
  suscripción de quien lo usa. No agregues SDK de Anthropic, Voyage ni similares.
- **Fuente oficial siempre.** Todo documento se declara en `corpus/fuentes.yaml` con su URL oficial.
  Fechas de publicación, entrada en vigor y abrogación se verifican en el DOF o en los transitorios
  del instrumento; si no se pudo verificar, no se inventa: se omite el campo o se anota en el PR.
- **El corpus se versiona.** `corpus/textos/*.json` es la salida de `ley-energia actualizar`; no
  se edita a mano. `data/` y `web/datos/` se generan y no van a git.
- **La web no carga terceros** ni usa scripts en línea (CSP `default-src 'self'`) y arma el DOM con
  nodos de texto, nunca `innerHTML` con datos.
- **Sólo lectura.** El servidor local escucha en 127.0.0.1 y no tiene endpoints que escriban.

## Flujo

```bash
uv sync
uv run ley-energia actualizar            # descarga y trocea (red)
uv run ley-energia indexar               # índice SQLite con vectores locales
uv run ley-energia evaluar -v            # 40 casos; debe pasar todo
uv run ley-energia exportar-web          # web/datos para el sitio
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

Para agregar un documento: entrada en el manifiesto, `actualizar --solo <id>`, `indexar`,
`evaluar`, y un caso nuevo en `evaluacion/golden.yaml` verificado contra el texto oficial.

## Mapa

| Ruta | Qué hace |
| --- | --- |
| `corpus/fuentes.yaml` | Manifiesto: documentos, fuentes, vigencia y linaje |
| `src/ley_energia/ingesta.py` | Descarga y extracción (leyes-mx, PDF de Diputados, notas del DOF) |
| `src/ley_energia/chunker.py` | Troceo por artículo, disposición, transitorio y anexo |
| `src/ley_energia/indice.py` | SQLite: documentos, fragmentos, FTS5 y vectores |
| `src/ley_energia/busqueda.py` | Búsqueda híbrida (RRF), filtros de vigencia, linaje |
| `src/ley_energia/mcp_server.py` | Servidor MCP: herramientas y prompts |
| `src/ley_energia/servidor.py` | Web local con API de sólo lectura |
| `src/ley_energia/web.py` | Exporta los datos del sitio estático |
| `web/` | Sitio (GitHub Pages) |
| `evaluacion/golden.yaml` | Set de evaluación |
| `audits/` | Auditoría del prototipo de abril de 2026 y cifras del después |
