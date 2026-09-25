"""Ingesta a la base de datos.

Los tests que necesitan PostgreSQL se saltan solos si no está levantado, para que la
integración continua siga funcionando sin base de datos.
"""

import pytest

from radar import ingesta
from radar.errores import FaltaConfiguracion


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

    assert aplicar_migraciones() == []  # ya estaban aplicadas


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
