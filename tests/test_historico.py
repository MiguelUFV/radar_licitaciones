"""Carga histórica desde los zip mensuales.

El zip de prueba se arma aquí con una entrada real, para no bajar 137 MB en cada test.
"""

import io
import zipfile

import pytest
from conftest import BAJA_REAL, ClienteFalso, entrada, pagina

from radar import historico
from radar.errores import ErrorRadar


def zip_de_prueba(paginas: dict[str, bytes]) -> bytes:
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, contenido in paginas.items():
            z.writestr(nombre, contenido)
    return memoria.getvalue()


def test_los_meses_se_generan_en_orden_y_cambian_de_ano():
    assert historico.meses("2025-11", "2026-02") == ["2025-11", "2025-12", "2026-01", "2026-02"]
    assert historico.meses("2025-01", "2025-01") == ["2025-01"]
    assert len(historico.meses("2025-01", "2026-08")) == 20


def test_un_rango_al_reves_se_avisa_sin_traza():
    with pytest.raises(ErrorRadar) as fallo:
        historico.meses("2026-08", "2025-01")
    assert "posterior" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)


def test_la_url_del_mes_es_la_del_zip_de_la_plataforma():
    assert historico.url_del_mes("2025-01").endswith("Completo3_202501.zip")


def preparar(monkeypatch, contenido: bytes) -> None:
    monkeypatch.setattr(historico, "crear_cliente", ClienteFalso)
    monkeypatch.setattr(historico.almacen, "buscar_por_url", lambda *a, **kw: None)
    monkeypatch.setattr(historico, "descargar", lambda url, cliente, **kw: contenido)


def test_carga_las_entradas_de_todos_los_atom_del_zip(bd, almacen_temporal, monkeypatch):
    datos = zip_de_prueba(
        {
            "pagina_1.atom": pagina([entrada("https://ejemplo.es/1", "2025-01-05T10:00:00.000+01:00")]),
            "pagina_2.atom": pagina(
                [entrada("https://ejemplo.es/2", "2025-01-06T10:00:00.000+01:00")], bajas=BAJA_REAL
            ),
            "leeme.txt": b"esto no es una pagina del feed",
        }
    )
    preparar(monkeypatch, datos)

    resumen = historico.cargar("2025-01", "2025-01")
    assert resumen["licitaciones"] == 2
    assert resumen["entradas"] == 2  # el .txt no cuenta

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "SELECT ficheros_atom, entradas, licitaciones FROM historico_meses WHERE mes = %s", ("2025-01",)
        )
        assert cur.fetchone() == (2, 2, 2)
        cur.execute("SELECT count(*) FROM bajas")
        assert cur.fetchone()[0] == 1


def test_un_mes_ya_cargado_no_se_vuelve_a_bajar(bd, almacen_temporal, monkeypatch):
    datos = zip_de_prueba(
        {"p1.atom": pagina([entrada("https://ejemplo.es/1", "2025-01-05T10:00:00.000+01:00")])}
    )
    preparar(monkeypatch, datos)
    historico.cargar("2025-01", "2025-01")

    def no_deberia_bajarse(url, cliente, **kw):
        raise AssertionError("se ha vuelto a bajar un mes que ya estaba cargado")

    monkeypatch.setattr(historico, "descargar", no_deberia_bajarse)
    segunda = historico.cargar("2025-01", "2025-01")
    assert segunda["saltados"] == 1
    assert segunda["licitaciones"] == 0


def test_la_entrada_historica_se_puede_recuperar_del_zip(bd, almacen_temporal, monkeypatch):
    # No se copia el XML a la base: la prueba de que eso no pierde nada es poder sacarlo otra vez.
    datos = zip_de_prueba(
        {"p1.atom": pagina([entrada("https://ejemplo.es/1", "2025-01-05T10:00:00.000+01:00")])}
    )
    preparar(monkeypatch, datos)
    historico.cargar("2025-01", "2025-01")

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT raw_fichero, miembro, posicion, xml FROM stg_entradas")
        sha, miembro, posicion, xml = cur.fetchone()
    assert xml is None
    assert miembro == "p1.atom"

    original = historico.entrada_original(sha, miembro, posicion)
    assert "<id>https://ejemplo.es/1</id>" in original


def test_un_zip_sin_paginas_del_feed_avisa_con_claridad(bd, almacen_temporal, monkeypatch):
    preparar(monkeypatch, zip_de_prueba({"leeme.txt": b"nada util"}))
    with pytest.raises(ErrorRadar) as fallo:
        historico.cargar("2025-01", "2025-01")
    assert "no trae ninguna página" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)


def test_el_mes_que_falla_no_queda_como_cargado(bd, almacen_temporal, monkeypatch):
    preparar(monkeypatch, zip_de_prueba({"leeme.txt": b"nada util"}))
    with pytest.raises(ErrorRadar):
        historico.cargar("2025-01", "2025-01")

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM historico_meses")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT estado FROM ejecuciones WHERE tipo = 'historica'")
        assert cur.fetchone()[0] == "error"


def test_de_los_meses_posteriores_solo_interesan_las_adjudicaciones_del_estudio():
    from radar.feed import Licitacion

    conocido = Licitacion("https://ejemplo.es/1", None, None, None, None, None, adjudicatario_nif="B123")
    ajeno = Licitacion("https://ejemplo.es/9", None, None, None, None, None, adjudicatario_nif="B123")
    sin_ganador = Licitacion("https://ejemplo.es/1", None, None, None, None, None)
    conocidos = {"https://ejemplo.es/1"}

    # Dentro del periodo de estudio entra todo.
    assert historico.interesa(sin_ganador, True, set()) is True
    # Fuera, solo el expediente conocido y ya adjudicado.
    assert historico.interesa(conocido, False, conocidos) is True
    assert historico.interesa(ajeno, False, conocidos) is False
    assert historico.interesa(sin_ganador, False, conocidos) is False


def test_la_ventana_deja_fuera_lo_que_no_es_del_estudio(bd, almacen_temporal, monkeypatch):
    dentro = zip_de_prueba(
        {"p1.atom": pagina([entrada("https://ejemplo.es/1", "2025-01-05T10:00:00.000+01:00")])}
    )
    preparar(monkeypatch, dentro)
    historico.cargar("2025-01", "2025-01", ventana=("2025-01", "2025-01"))

    # Un mes posterior con un expediente distinto: no se guarda.
    fuera = zip_de_prueba(
        {"p1.atom": pagina([entrada("https://ejemplo.es/otro", "2025-02-05T10:00:00.000+01:00")])}
    )
    preparar(monkeypatch, fuera)
    resumen = historico.cargar("2025-02", "2025-02", ventana=("2025-01", "2025-01"))
    assert resumen["licitaciones"] == 0

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM licitaciones")
        assert cur.fetchone()[0] == 1


def test_el_mes_anota_lo_que_hay_en_la_base_no_lo_que_inserto_esta_pasada(bd, almacen_temporal, monkeypatch):
    # Si una carga se corta a la mitad y se relanza, la segunda pasada solo anade lo que
    # faltaba. El mes tiene que seguir diciendo cuantas licitaciones tiene, no cuantas ha
    # metido esa pasada.
    datos = zip_de_prueba(
        {"p1.atom": pagina([entrada("https://ejemplo.es/1", "2025-01-05T10:00:00.000+01:00")])}
    )
    preparar(monkeypatch, datos)
    historico.cargar("2025-01", "2025-01")
    historico.cargar("2025-01", "2025-01", rehacer=True)

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT entradas, licitaciones FROM historico_meses WHERE mes = '2025-01'")
        assert cur.fetchone() == (1, 1)


def test_no_se_abre_un_fichero_que_se_hincha_al_descomprimirse(bd, almacen_temporal, monkeypatch):
    # Un zip pequeno cuyo contenido ocupa cientos de megas al abrirlo. Se para antes de
    # leerlo, no despues de quedarse sin memoria.
    monkeypatch.setattr(historico, "MAXIMO_POR_FICHERO", 1024)
    relleno = pagina([entrada("https://ejemplo.es/1", "2025-01-05T10:00:00.000+01:00")]) + b" " * 5000
    preparar(monkeypatch, zip_de_prueba({"p1.atom": relleno}))

    with pytest.raises(ErrorRadar) as fallo:
        historico.cargar("2025-01", "2025-01")
    assert "al descomprimirse" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM licitaciones")
        assert cur.fetchone()[0] == 0
