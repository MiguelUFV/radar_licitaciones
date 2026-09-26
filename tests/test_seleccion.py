"""La regla de selección, aplicada tal como está escrita en docs/REGLA_SELECCION.md.

Los NIF de aquí son inventados a propósito y no salen de este fichero: son casos límite de la
regla (una UTE, una persona física, una empresa que se llama COMPUTER), no datos.
"""

import pytest

from radar import seleccion
from radar.errores import ErrorRadar


def candidata(**cambios) -> seleccion.Candidata:
    base = {
        "nif": "B00000001",
        "nombre": "EJEMPLO SL",
        "adjudicaciones": 10,
        "de_informatica": 8,
        "siempre_pyme": True,
    }
    return seleccion.Candidata(**{**base, **cambios})


def test_una_empresa_que_cumple_todo_entra():
    assert seleccion.motivo_de_descarte(candidata()) is None


def test_descarta_a_las_personas_fisicas():
    # Los NIF de persona fisica empiezan por numero. Ademas de no ser empresas, son datos
    # personales (DATOS §7).
    assert seleccion.motivo_de_descarte(candidata(nif="12345678Z")) == "no es persona juridica"


def test_descarta_las_ute_por_el_nif_y_por_el_nombre():
    assert seleccion.motivo_de_descarte(candidata(nif="U12345678")) == "es UTE"
    assert seleccion.motivo_de_descarte(candidata(nombre="UTE OBRAS Y SERVICIOS")) == "es UTE"
    assert seleccion.motivo_de_descarte(candidata(nombre="SERVICIOS TECNICOS, U.T.E.")) == "es UTE"


def test_una_empresa_que_se_llama_computer_no_es_una_ute():
    # "COMPUTER" contiene las letras UTE. Buscar la sigla suelta y no como trozo de palabra.
    assert seleccion.motivo_de_descarte(candidata(nombre="COMPUTER SYSTEMS SL")) is None
    assert seleccion.motivo_de_descarte(candidata(nombre="EJECUTEC SOLUCIONES SA")) is None


def test_descarta_a_quien_no_consta_como_pyme():
    assert seleccion.motivo_de_descarte(candidata(siempre_pyme=False)) == "no consta como pyme"


def test_exige_ocho_adjudicaciones():
    assert seleccion.motivo_de_descarte(candidata(adjudicaciones=7, de_informatica=7))
    assert seleccion.motivo_de_descarte(candidata(adjudicaciones=8, de_informatica=6)) is None


def test_la_mitad_justa_de_informatica_no_basta():
    assert (
        seleccion.motivo_de_descarte(candidata(adjudicaciones=10, de_informatica=5))
        == "no es mayoritariamente de informatica"
    )
    assert seleccion.motivo_de_descarte(candidata(adjudicaciones=10, de_informatica=6)) is None


def test_el_sorteo_es_reproducible_y_no_depende_del_orden_de_entrada():
    nifs = [f"B0000000{n}" for n in range(9)]
    primero = seleccion.sortear(nifs)
    assert seleccion.sortear(list(reversed(nifs))) == primero
    assert seleccion.sortear(nifs, semilla=1) != primero


def test_el_sorteo_reparte_dos_y_cinco():
    desarrollo, test = seleccion.sortear([f"B0000000{n}" for n in range(9)])
    assert len(desarrollo) == 2
    assert len(test) == 5
    assert not set(desarrollo) & set(test)


def test_la_huella_de_la_regla_es_la_del_fichero():
    assert len(seleccion.huella_de_la_regla()) == 64


def sembrar(conexion, filas: list[tuple]) -> None:
    """Deja adjudicaciones ya resueltas en la base, sin pasar por el feed."""
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
            " VALUES (repeat('a', 64), 'feed', 'https://ejemplo.es/f', 'x', 1, now())"
            " ON CONFLICT DO NOTHING"
        )
        for numero, (nif, nombre, cpv, pyme) in enumerate(filas):
            cur.execute(
                "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
                " VALUES (repeat('a', 64), %s, %s, %s) RETURNING id",
                (numero, f"https://ejemplo.es/e{numero}", "2025-03-01T10:00:00+01:00"),
            )
            stg = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada, cpv)"
                " VALUES (%s, %s, %s, %s) RETURNING id",
                (f"https://ejemplo.es/e{numero}", "2025-03-01T10:00:00+01:00", stg, cpv),
            )
            licitacion = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO adjudicaciones (licitacion, adjudicatario, nombre, es_pyme)"
                " VALUES (%s, %s, %s, %s)",
                (licitacion, nif, nombre, pyme),
            )
    conexion.commit()


def poblacion() -> list[tuple]:
    filas = []
    for empresa in range(6):
        for _ in range(9):
            filas.append((f"B0000000{empresa}", f"EMPRESA {empresa} SL", ["72000000"], True))
    filas.append(("12345678Z", "PERSONA FISICA", ["72000000"], True))
    filas.append(("U11111111", "UTE ALGO", ["72000000"], True))
    return filas


def test_la_seleccion_reparte_y_deja_constancia_de_con_que_regla(bd):
    with bd() as conexion:
        sembrar(conexion, poblacion())

    resumen = seleccion.aplicar("2025-01-01", "2025-07-01", "2026-09-01")
    assert resumen["cumplen_la_regla"] == 6
    assert resumen["desarrollo"] == 2
    assert "no es persona juridica" in resumen["descartes"]

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT alias, rol, regla_sha256, semilla FROM perfiles ORDER BY alias")
        filas = cur.fetchall()
    assert [f[0] for f in filas] == [f"Empresa {c}" for c in "ABCDEF"]
    assert [f[1] for f in filas] == ["desarrollo", "desarrollo", "test", "test", "test", "test"]
    assert len(filas[0][2]) == 64
    assert filas[0][3] == "20260925"


def test_no_se_puede_volver_a_sortear_sin_decirlo(bd):
    with bd() as conexion:
        sembrar(conexion, poblacion())
    seleccion.aplicar("2025-01-01", "2025-07-01", "2026-09-01")

    with pytest.raises(ErrorRadar) as fallo:
        seleccion.aplicar("2025-01-01", "2025-07-01", "2026-09-01")
    assert "invalidaría el estudio" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)


def test_si_no_salen_suficientes_empresas_lo_dice(bd):
    with bd() as conexion:
        sembrar(
            conexion,
            [(f"B0000000{e}", f"EMPRESA {e}", ["72000000"], True) for e in range(2) for _ in range(9)],
        )

    with pytest.raises(ErrorRadar) as fallo:
        seleccion.aplicar("2025-01-01", "2025-07-01", "2026-09-01")
    assert "Amplía el periodo" in str(fallo.value)


def test_un_autonomo_con_nie_no_entra_como_empresa():
    # X, Y y Z son NIE: empiezan por letra, pero son personas. Mirar solo "es una letra"
    # los colaba en el estudio como si fueran sociedades.
    for nie in ("X1234567L", "Y1234567X", "Z1234567R"):
        assert seleccion.motivo_de_descarte(candidata(nif=nie)) == "no es persona juridica"


def test_una_persona_ya_seudonimizada_tampoco_entra():
    assert seleccion.motivo_de_descarte(candidata(nif="pf_a1b2c3")) == "no es persona juridica"


def test_las_letras_de_sociedad_si_entran():
    for letra in "ABCDEFGHJNPQRSVW":  # la U es UTE y se descarta aparte
        assert seleccion.motivo_de_descarte(candidata(nif=f"{letra}12345678")) is None
