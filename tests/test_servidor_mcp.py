import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ley_energia import indice, mcp_server, servidor
from ley_energia.busqueda import Buscador


@pytest.fixture()
def app(monkeypatch: pytest.MonkeyPatch, ruta_indice: Path) -> TestClient:
    b = Buscador(indice.abrir(ruta_indice))
    monkeypatch.setattr(servidor, "_buscador", lambda: b)
    return TestClient(servidor.crear_app())


def test_api_busca_y_manda_cabeceras(app: TestClient) -> None:
    r = app.get("/api/buscar", params={"q": "artículo 20 LSE", "k": 3})
    assert r.status_code == 200
    assert r.json()["resultados"][0]["cita"] == "LSE, artículo 20"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_api_valida_entradas(app: TestClient) -> None:
    assert app.get("/api/buscar", params={"q": "x" * 501}).status_code == 422
    assert app.get("/api/buscar", params={"q": "a", "fecha": "ayer"}).status_code == 422
    assert app.get("/api/buscar", params={"q": "a", "k": 999}).status_code == 422
    assert app.get("/api/buscar", params={"q": "a", "fecha": "2025-02-30"}).status_code == 422
    assert (
        app.get("/api/estado").json()["modo"] == "lexico"
    )  # el índice de prueba no tiene vectores


def test_api_sin_endpoints_de_escritura(app: TestClient) -> None:
    assert app.post("/api/buscar", params={"q": "a"}).status_code == 405
    assert app.post("/api/monitor/run").status_code in (404, 405)


def test_mcp_herramientas(monkeypatch: pytest.MonkeyPatch, ruta_indice: Path) -> None:
    b = Buscador(indice.abrir(ruta_indice))
    monkeypatch.setattr(mcp_server, "_buscador", lambda: b)

    async def correr() -> None:
        nombres = {t.name for t in await mcp_server.servidor.list_tools()}
        assert nombres == {"buscar", "leer_articulo", "documento", "linaje", "catalogo"}
        r = await mcp_server.servidor.call_tool(
            "leer_articulo", {"documento": "LSE", "articulo": "30"}
        )
        datos = json.loads(r.content[0].text)
        assert datos["cita"] == "LSE, artículo 30"
        assert "No constituye opinión legal" in datos["aviso"]
        r = await mcp_server.servidor.call_tool("buscar", {"consulta": "zzzz qqqq"})
        assert json.loads(r.content[0].text)["resultados"] == []
        r = await mcp_server.servidor.call_tool(
            "buscar", {"consulta": "permisos", "fecha": "2025-3-1"}
        )
        assert "fecha inválida" in json.loads(r.content[0].text)["error"]
        r = await mcp_server.servidor.call_tool(
            "leer_articulo", {"documento": "dacg-cne-autoconsumo", "articulo": "1.2"}
        )
        assert json.loads(r.content[0].text)["clave"] == "1.2"

    asyncio.run(correr())
