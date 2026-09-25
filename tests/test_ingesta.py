"""Ingesta a la base de datos.

Los tests que necesitan PostgreSQL se saltan solos si no está levantado, para que la
integración continua siga funcionando sin base de datos.
"""

import contextlib
import pathlib

import pytest
from conftest import BAJA_REAL, entrada, pagina

from radar import feed, ingesta
from radar.errores import ErrorRadar, FaltaConfiguracion


def hay_base_de_datos() -> bool:
    try:
        from radar.bd import conectar

        with conectar() as conexion, conexion.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


necesita_bd = pytest.mark.skipif(not hay_base_de_datos(), reason="PostgreSQL no está levantado")


def test_interpreta_la_bandera_de_pyme():
    assert ingesta._bandera("true") is True
    assert ingesta._bandera("false") is False
    assert ingesta._bandera(None) is None


def test_sin_base_de_datos_el_mensaje_es_legible(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "")
    monkeypatch.setattr("radar.bd.load_dotenv", lambda *a, **k: None)
    from radar.bd import cadena_conexion

    with pytest.raises(FaltaConfiguracion) as fallo:
        cadena_conexion()
    assert "POSTGRES_PASSWORD" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)


@necesita_bd
def test_las_migraciones_son_repetibles():
    from radar.bd import aplicar_migraciones

    aplicar_migraciones()
    assert aplicar_migraciones() == []  # la segunda vez ya no queda ninguna pendiente


@necesita_bd
def test_cada_licitacion_se_remonta_a_su_fichero_descargado():
    from radar.bd import conectar

    with conectar() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM licitaciones")
        if cur.fetchone()[0] == 0:
            pytest.skip("todavía no se ha ingerido nada")
        cur.execute(
            "SELECT count(*) FROM licitaciones l"
            " JOIN stg_entradas s ON s.id = l.stg_entrada"
            " JOIN raw_ficheros r ON r.sha256 = s.raw_fichero"
            " WHERE r.sha256 IS NULL"
        )
        assert cur.fetchone()[0] == 0


@necesita_bd
def test_no_hay_versiones_duplicadas_de_la_misma_licitacion():
    from radar.bd import conectar

    with conectar() as conexion, conexion.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM ("
            " SELECT entry_id, entry_updated FROM licitaciones"
            " GROUP BY 1, 2 HAVING count(*) > 1) AS duplicadas"
        )
        assert cur.fetchone()[0] == 0


# --- Cursor: por donde se quedo la ultima pasada ---------------------------------------


def test_una_entrada_del_cambio_de_hora_no_se_pierde():
    # El 25-10-2026 el reloj pasa de +02:00 a +01:00. Comparando el texto, "02:30" parece
    # anterior a "03:00" y la entrada se descartaria, aunque es media hora posterior.
    cursor = feed.momento("2026-10-25T03:00:00.000+02:00")  # 01:00 UTC
    assert ingesta.es_anterior("2026-10-25T02:30:00.000+01:00", cursor) is False  # 01:30 UTC
    assert ingesta.es_anterior("2026-10-25T02:50:00.000+02:00", cursor) is True  # 00:50 UTC


def test_sin_cursor_previo_no_se_descarta_nada():
    assert ingesta.es_anterior("2026-09-05T10:00:00.000+02:00", None) is False


def feed_de_tres_paginas(monkeypatch):
    """Tres paginas encadenadas, de la mas reciente a la mas antigua."""
    urls = [feed.FEED_PERFILES, "https://ejemplo.es/pagina2.atom", "https://ejemplo.es/pagina3.atom"]
    fechas = [
        "2026-09-05T10:00:00.000+02:00",
        "2026-09-04T10:00:00.000+02:00",
        "2026-09-03T10:00:00.000+02:00",
    ]
    paginas = {
        url: pagina(
            [entrada(f"https://ejemplo.es/licitacion/{n}", fechas[n])],
            siguiente=urls[n + 1] if n + 1 < len(urls) else None,
        )
        for n, url in enumerate(urls)
    }
    monkeypatch.setattr(ingesta, "crear_cliente", contextlib.nullcontext)
    monkeypatch.setattr(ingesta, "descargar", lambda url, cliente, **kw: paginas[url])
    monkeypatch.setattr(ingesta.almacen, "buscar_por_url", lambda *a, **kw: None)
    return paginas


def sembrar_cursor(bd, fecha: str) -> None:
    """Deja el cursor donde lo habria dejado una pasada anterior."""
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO cursor_feed (fuente, ultima_fecha) VALUES ('placsp_643', %s)"
            " ON CONFLICT (fuente) DO UPDATE SET ultima_fecha = EXCLUDED.ultima_fecha",
            (feed.momento(fecha),),
        )
        conexion.commit()


def test_el_cursor_no_avanza_si_quedan_paginas_por_recorrer(bd, almacen_temporal, monkeypatch):
    # El caso real: el PC pasa el fin de semana apagado, el lunes se acumulan mas paginas de
    # las que caben en una pasada. Si el cursor salta igualmente a lo mas reciente, lo que
    # quedo por debajo (y es posterior al cursor viejo) no se lee nunca mas.
    feed_de_tres_paginas(monkeypatch)
    sembrar_cursor(bd, "2026-09-02T10:00:00.000+02:00")

    corta = ingesta.ingerir(1, "manual")
    assert corta["licitaciones_nuevas"] == 1
    assert corta["completa"] is False

    larga = ingesta.ingerir(3, "manual")
    assert larga["completa"] is True

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM licitaciones")
        assert cur.fetchone()[0] == 3


def test_la_primera_pasada_garantiza_lo_posterior_a_lo_mas_antiguo_que_leyo(
    bd, almacen_temporal, monkeypatch
):
    # Sin cursor previo no hay nada que alcanzar, asi que la pasada nunca se completaria y el
    # cursor no se movería jamas. La primera deja el punto en lo mas antiguo que ha leido.
    feed_de_tres_paginas(monkeypatch)

    primera = ingesta.ingerir(2, "manual")
    assert primera["completa"] is False
    assert primera["licitaciones_nuevas"] == 2

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT ultima_fecha FROM cursor_feed")
        assert cur.fetchone()[0] == feed.momento("2026-09-04T10:00:00.000+02:00")

    # La segunda pasada ya se completa: alcanza lo conocido en la segunda pagina.
    segunda = ingesta.ingerir(3, "manual")
    assert segunda["completa"] is True
    assert segunda["licitaciones_nuevas"] == 0


def test_repetir_la_pasada_completa_no_duplica_nada(bd, almacen_temporal, monkeypatch):
    feed_de_tres_paginas(monkeypatch)
    ingesta.ingerir(3, "manual")
    segunda = ingesta.ingerir(3, "manual")
    assert segunda["licitaciones_nuevas"] == 0

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM licitaciones")
        assert cur.fetchone()[0] == 3


def test_un_fallo_inesperado_deja_la_ejecucion_marcada_como_error(bd, almacen_temporal, monkeypatch):
    # Un fallo que no sea de los previstos tambien tiene que cerrar la ejecucion: si no,
    # queda "en_curso" para siempre y nadie se entera de que la ingesta se paro.
    def revienta(*args, **kwargs):
        raise ValueError("el servidor ha devuelto algo que no es XML")

    monkeypatch.setattr(ingesta, "crear_cliente", contextlib.nullcontext)
    monkeypatch.setattr(ingesta.almacen, "buscar_por_url", lambda *a, **kw: None)
    monkeypatch.setattr(ingesta, "descargar", revienta)

    with pytest.raises(ErrorRadar) as fallo:
        ingesta.ingerir(1, "manual")
    assert "Traceback" not in str(fallo.value)

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT estado, mensaje FROM ejecuciones")
        estado, mensaje = cur.fetchone()
    assert estado == "error"
    assert mensaje and "Traceback" not in mensaje


def test_las_licitaciones_anuladas_quedan_registradas(bd, almacen_temporal, monkeypatch):
    anulada = "https://contrataciondelestado.es/sindicacion/licitacionesPerfilContratante/20499474"
    paginas = {
        feed.FEED_PERFILES: pagina([entrada(anulada, "2026-09-05T10:00:00.000+02:00")], bajas=BAJA_REAL)
    }
    monkeypatch.setattr(ingesta, "crear_cliente", contextlib.nullcontext)
    monkeypatch.setattr(ingesta, "descargar", lambda url, cliente, **kw: paginas[url])
    monkeypatch.setattr(ingesta.almacen, "buscar_por_url", lambda *a, **kw: None)

    resumen = ingesta.ingerir(1, "manual")
    assert resumen["bajas"] == 1

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT motivo FROM bajas WHERE entry_id = %s", (anulada,))
        assert cur.fetchone()[0] == "ANULADA"
        cur.execute("SELECT anulada FROM v_licitaciones_vigentes WHERE entry_id = %s", (anulada,))
        assert cur.fetchone()[0] is True


def test_los_lotes_se_guardan_con_su_licitacion(bd, almacen_temporal, monkeypatch):
    con_lotes = (pathlib.Path("tests/fixtures/entrada_con_lotes.xml")).read_text(encoding="utf-8")
    paginas = {feed.FEED_PERFILES: pagina([con_lotes])}
    monkeypatch.setattr(ingesta, "crear_cliente", contextlib.nullcontext)
    monkeypatch.setattr(ingesta, "descargar", lambda url, cliente, **kw: paginas[url])
    monkeypatch.setattr(ingesta.almacen, "buscar_por_url", lambda *a, **kw: None)

    ingesta.ingerir(1, "manual")

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT numero, objeto, importe FROM lotes ORDER BY numero")
        filas = cur.fetchall()
    assert len(filas) == 2
    assert filas[0][1] == "Fiesta de la Vendimia"
    assert float(filas[1][2]) == 16550.0
