import pytest

from ley_energia import corpus, fuentes
from ley_energia.fuentes import Manifiesto, validar


def test_manifiesto_valido_y_con_textos() -> None:
    m = fuentes.cargar()
    assert len(m.documentos) >= 30
    assert corpus.faltantes(m) == []


def test_cada_abrogado_tiene_sustituto_vigente() -> None:
    m = fuentes.cargar()
    por_id = m.por_id()
    for d in m.documentos:
        if d.sustituido_por:
            assert por_id[d.sustituido_por].vigente, d.id


def test_vigencia_en_fecha() -> None:
    m = fuentes.cargar().por_id()
    assert m["lie"].vigente_en("2020-01-01")
    assert not m["lie"].vigente_en("2025-03-19")
    assert m["lse"].vigente_en("2025-03-19")
    assert not m["lse"].vigente_en("2025-03-18")


def test_validar_rechaza_sustituto_inexistente() -> None:
    m = fuentes.cargar()
    malo = m.documentos[0].__class__(
        **{
            **m.documentos[0].__dict__,
            "id": "x",
            "sustituido_por": "no-existe",
            "abrogada_desde": "2030-01-01",
        }
    )
    with pytest.raises(ValueError, match="no existe"):
        validar(Manifiesto(corte=m.corte, documentos=[*m.documentos, malo]))


def test_linaje_sin_huecos_ni_traslapes() -> None:
    m = fuentes.cargar()
    por_id = m.por_id()
    for d in m.documentos:
        if d.sustituido_por:
            assert por_id[d.sustituido_por].inicio_vigencia == d.abrogada_desde, d.id
    assert not por_id["dacg-cre-almacenamiento"].vigente_en("2026-04-17")
    assert not por_id["dacg-cne-almacenamiento"].vigente_en("2026-04-16")
