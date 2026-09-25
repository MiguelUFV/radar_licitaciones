"""Lectura del feed, comprobada contra una entrada real descargada de la Plataforma.

La entrada de tests/fixtures/entrada_real.xml es un expediente público de verdad, no un
ejemplo inventado (CLAUDE.md, innegociable 2).
"""

from pathlib import Path

import pytest

from radar import feed

FIXTURE = Path(__file__).parent / "fixtures" / "entrada_real.xml"


@pytest.fixture(scope="module")
def licitacion() -> feed.Licitacion:
    return feed.parsear_entrada(FIXTURE.read_text(encoding="utf-8"))


def test_identifica_el_expediente_y_el_organo(licitacion):
    assert licitacion.entry_id.startswith("https://contrataciondelestado.es/sindicacion/")
    assert licitacion.expediente == "2026-07-SG-SEGURO SALUD"
    assert "Sociedad" in licitacion.organo


def test_lee_el_estado_aunque_la_etiqueta_lleve_prefijo_con_guion(licitacion):
    # La etiqueta real es <cbc-place-ext:ContractFolderStatusCode>. Con un prefijo sin guion
    # el campo salia vacio y toda la Fase 1 contaba mal los estados.
    assert licitacion.estado in {"PUB", "EV", "ADJ", "RES", "PRE", "ANUL"}


def test_lee_importes_cpv_y_plazo(licitacion):
    assert licitacion.importe_sin_iva == 69360.0
    assert licitacion.valor_estimado == 138720.0
    assert licitacion.cpv[0].startswith("66")
    assert licitacion.plazo_presentacion == "2026-07-16"


def test_lee_los_enlaces_a_los_documentos(licitacion):
    assert licitacion.pcap.startswith("https://contrataciondelestado.es/FileSystem/servlet/")
    assert "DocumentIdParam" in licitacion.pcap


def test_lee_el_adjudicatario(licitacion):
    assert licitacion.adjudicatario_nif == "A08169294"


def test_clasifica_la_solvencia_del_feed(licitacion):
    assert licitacion.solvencia_feed
    assert licitacion.solvencia_con_cifras is True


def test_distingue_las_licitaciones_de_informatica():
    informatica = feed.Licitacion(None, None, None, None, None, None, cpv=["72253200"])
    seguros = feed.Licitacion(None, None, None, None, None, None, cpv=["66512200"])
    assert feed.es_informatica(informatica)
    assert not feed.es_informatica(seguros)


def test_una_pagina_trae_licitaciones_y_enlace_a_la_siguiente():
    xml = (
        '<feed><link href="https://ejemplo.es/pagina2.atom" rel="next"/>'
        + FIXTURE.read_text(encoding="utf-8")
        + "</feed>"
    )
    licitaciones, siguiente = feed.parsear_pagina(xml)
    assert len(licitaciones) == 1
    assert siguiente == "https://ejemplo.es/pagina2.atom"
