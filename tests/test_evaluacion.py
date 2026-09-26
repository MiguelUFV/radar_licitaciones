"""M1 y M2 de los filtros de referencia, con un escenario montado a mano.

El escenario es pequeño y las cifras se pueden comprobar con los dedos: si la medición no da
eso, la medición está mal.
"""

import pytest

from radar.errores import ErrorRadar
from radar.evaluacion import baselines

GANADORA = "B00000001"
OTRA = "B00000002"

# entry_id, cpv, fecha de publicacion, quien gano
ESCENARIO = [
    ("e1", ["72253000"], "2025-03-01", GANADORA),  # informatica, la gana: la ven los dos filtros
    ("e2", ["30213000"], "2025-03-02", GANADORA),  # equipos informaticos: el filtro A no lo ve
    ("e3", ["48000000"], "2025-03-03", GANADORA),  # software: lo ven los dos
    ("e4", ["45000000"], "2025-03-04", OTRA),  # obra, de otra empresa
    ("e5", ["72100000"], "2025-03-04", None),  # informatica sin adjudicar
]


def montar(conexion) -> None:
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
            " VALUES (repeat('b', 64), 'feed', 'https://ejemplo.es/f', 'x', 1, now())"
            " ON CONFLICT DO NOTHING"
        )
        for numero, (entry, cpv, fecha, ganador) in enumerate(ESCENARIO):
            cur.execute(
                "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
                " VALUES (repeat('b', 64), %s, %s, %s) RETURNING id",
                (numero, entry, f"{fecha}T10:00:00+01:00"),
            )
            stg = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada, cpv)"
                " VALUES (%s, %s, %s, %s) RETURNING id",
                (entry, f"{fecha}T10:00:00+01:00", stg, cpv),
            )
            licitacion = cur.fetchone()[0]
            if ganador:
                cur.execute(
                    "INSERT INTO adjudicaciones (licitacion, adjudicatario, es_pyme) VALUES (%s, %s, true)",
                    (licitacion, ganador),
                )
        cur.execute(
            "INSERT INTO perfiles (alias, nif, rol, adjudicaciones, de_informatica, semilla,"
            " regla_sha256) VALUES ('Empresa A', %s, 'desarrollo', 3, 3, '1', repeat('c', 64))",
            (GANADORA,),
        )
    conexion.commit()


def test_el_filtro_tipico_no_ve_los_contratos_publicados_bajo_otro_cpv(bd):
    with bd() as conexion:
        montar(conexion)

    resultados = medir_con(["72", "48"])
    m1 = next(r for r in resultados if r["metrica"] == "M1")
    # De los 3 contratos que gano, el filtro 72/48 solo ve 2: el de equipos (CPV 30) se pierde.
    assert m1["detalle"] == {"ganados": 3, "en_la_lista": 2, "rol": "desarrollo"}
    assert m1["valor"] == pytest.approx(0.6667, abs=0.0001)


def test_un_filtro_mas_ancho_los_ve_todos(bd):
    with bd() as conexion:
        montar(conexion)

    resultados = medir_con(["72", "48", "30"])
    m1 = next(r for r in resultados if r["metrica"] == "M1")
    assert m1["valor"] == 1.0


def test_el_volumen_se_cuenta_por_dia_publicado(bd):
    with bd() as conexion:
        montar(conexion)

    resultados = medir_con(["72", "48"])
    m2 = next(r for r in resultados if r["metrica"] == "M2")
    # Pasan e1, e3 y e5 (tres licitaciones) repartidas en 4 dias con publicaciones.
    assert m2["detalle"]["licitaciones_que_pasan"] == 3
    assert m2["detalle"]["dias_con_publicaciones"] == 4
    assert m2["valor"] == pytest.approx(0.75)


def test_la_cifra_queda_guardada_con_el_commit_y_el_comando(bd):
    with bd() as conexion:
        montar(conexion)
    medir_con(["72", "48"])

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "SELECT metrica, variante, alias, comando, git_commit FROM eval_resultados ORDER BY metrica"
        )
        filas = cur.fetchall()
    assert [f[0] for f in filas] == ["M1", "M2"]
    assert filas[0][2] == "Empresa A"
    assert "radar.evaluacion.baselines" in filas[0][3]


def test_sin_carga_historica_lo_dice_sin_traza(bd):
    with pytest.raises(ErrorRadar) as fallo:
        medir_con(["72"])
    assert "carga histórica" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)


def test_sin_empresas_seleccionadas_lo_dice(bd):
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
            " VALUES (repeat('b', 64), 'feed', 'https://ejemplo.es/f', 'x', 1, now())"
        )
        cur.execute(
            "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
            " VALUES (repeat('b', 64), 0, 'e1', '2025-03-01T10:00:00+01:00') RETURNING id"
        )
        stg = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada, cpv)"
            " VALUES ('e1', '2025-03-01T10:00:00+01:00', %s, %s)",
            (stg, ["72000000"]),
        )
        conexion.commit()

    with pytest.raises(ErrorRadar) as fallo:
        medir_con(["72"])
    assert "regla" in str(fallo.value)


def medir_con(prefijos: list[str]) -> list[dict]:
    return baselines.medir("2025-01-01", "2025-07-01", {"baseline_a": {None: prefijos}})


def test_se_mide_con_el_cpv_que_estaba_publicado_no_con_el_de_despues(bd):
    # Un expediente que sale con CPV de obra y al adjudicarse aparece con CPV de informatica.
    # Medir con la version ultima seria hacer trampa: el filtro no pudo ver eso a tiempo.
    with bd() as conexion:
        montar(conexion)
        with conexion.cursor() as cur:
            cur.execute(
                "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
                " VALUES (repeat('b', 64), 99, 'e4', '2025-05-01T10:00:00+01:00') RETURNING id"
            )
            stg = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada, cpv)"
                " VALUES ('e4', '2025-05-01T10:00:00+01:00', %s, %s) RETURNING id",
                (stg, ["72253000"]),
            )
            cur.execute(
                "INSERT INTO adjudicaciones (licitacion, adjudicatario, es_pyme) VALUES (%s, %s, true)",
                (cur.fetchone()[0], GANADORA),
            )
        conexion.commit()

    resultados = medir_con(["72", "48"])
    m1 = next(r for r in resultados if r["metrica"] == "M1")
    # Ahora gano 4, y el filtro sigue viendo 2: e4 se publico como obra (CPV 45).
    assert m1["detalle"]["ganados"] == 4
    assert m1["detalle"]["en_la_lista"] == 2


def test_cada_empresa_se_mide_con_su_propio_filtro(bd):
    # El filtro B sale del perfil de cada empresa, asi que es distinto para cada una. Si se
    # juntan todos en uno, a cada empresa se le mide con el filtro de las demas y tanto el
    # recall como el volumen salen inflados.
    with bd() as conexion:
        montar(conexion)
        with conexion.cursor() as cur:
            cur.execute(
                "INSERT INTO perfiles (alias, nif, rol, adjudicaciones, de_informatica, semilla,"
                " regla_sha256) VALUES ('Empresa B', %s, 'test', 1, 1, '1', repeat('c', 64))",
                (OTRA,),
            )
            conexion.commit()

    resultados = baselines.medir(
        "2025-01-01",
        "2025-07-01",
        {"baseline_b": {"Empresa A": ["72", "48"], "Empresa B": ["45"]}},
    )

    m1 = {r["alias"]: r for r in resultados if r["metrica"] == "M1"}
    # Empresa A gano 3 contratos y su filtro (72/48) ve 2.
    assert m1["Empresa A"]["detalle"]["ganados"] == 3
    assert m1["Empresa A"]["detalle"]["en_la_lista"] == 2
    # Empresa B gano 1 (de obra) y su filtro (45) lo ve.
    assert m1["Empresa B"]["detalle"] == {"ganados": 1, "en_la_lista": 1, "rol": "test"}

    # Y el volumen tambien es de cada una: no es el mismo numero para las dos.
    m2 = {r["alias"]: r["detalle"]["licitaciones_que_pasan"] for r in resultados if r["metrica"] == "M2"}
    assert m2["Empresa A"] == 3
    assert m2["Empresa B"] == 1


def test_una_adjudicacion_posterior_al_corte_no_cuenta(bd):
    # Sin esto, cargar un mes mas cambiaria el resultado de una medicion ya publicada.
    with bd() as conexion:
        montar(conexion)
        with conexion.cursor() as cur:
            cur.execute(
                "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
                " VALUES (repeat('b', 64), 50, 'e5', '2026-10-01T10:00:00+01:00') RETURNING id"
            )
            stg = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada, cpv)"
                " VALUES ('e5', '2026-10-01T10:00:00+01:00', %s, %s) RETURNING id",
                (stg, ["72100000"]),
            )
            cur.execute(
                "INSERT INTO adjudicaciones (licitacion, adjudicatario, es_pyme) VALUES (%s, %s, true)",
                (cur.fetchone()[0], GANADORA),
            )
            conexion.commit()

    con_corte = baselines.medir("2025-01-01", "2025-07-01", {"baseline_a": {None: ["72", "48"]}})
    sin_corte = baselines.medir(
        "2025-01-01", "2025-07-01", {"baseline_a": {None: ["72", "48"]}}, corte="2027-01-01"
    )
    assert next(r for r in con_corte if r["metrica"] == "M1")["detalle"]["ganados"] == 3
    assert next(r for r in sin_corte if r["metrica"] == "M1")["detalle"]["ganados"] == 4
