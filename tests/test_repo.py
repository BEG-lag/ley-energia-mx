"""Reglas del repositorio: sin guion largo, sin llaves, web sin terceros ni scripts en línea."""

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _archivos_texto() -> list[Path]:
    salida = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    exts = {
        ".py",
        ".md",
        ".yaml",
        ".yml",
        ".json",
        ".html",
        ".css",
        ".js",
        ".toml",
        ".svg",
        ".txt",
        ".cff",
    }
    return [RAIZ / f for f in salida if Path(f).suffix in exts and (RAIZ / f).is_file()]


def test_sin_guion_largo() -> None:
    con = [
        str(p.relative_to(RAIZ))
        for p in _archivos_texto()
        if "corpus/textos" not in str(p)
        and chr(0x2014) in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert con == []


def test_sin_llaves_de_servicios() -> None:
    patron = re.compile(
        r"sk-ant-[A-Za-z0-9_-]{8,}|ANTHROPIC_API_KEY|VOYAGE_API_KEY|ghp_[A-Za-z0-9]{20,}"
    )
    con = [
        str(p.relative_to(RAIZ))
        for p in _archivos_texto()
        if p.name != "test_repo.py"
        and patron.search(p.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert con == []


def test_web_sin_terceros_ni_scripts_en_linea() -> None:
    html = (RAIZ / "web" / "index.html").read_text(encoding="utf-8")
    assert re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html) == []
    externos = re.findall(r'<(?:script|link)[^>]+(?:src|href)="(https?://[^"]+)"', html)
    assert [u for u in externos if "beg-lag.github.io" not in u] == []
    assert ' style="' not in html
    js = "".join(
        (RAIZ / "web" / "js" / n).read_text(encoding="utf-8") for n in ("app.js", "motor.js")
    )
    assert re.search(r"\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML|document\.write", js) is None
    assert re.findall(r"fetch\(\s*[\"'`]https?://", js) == []
