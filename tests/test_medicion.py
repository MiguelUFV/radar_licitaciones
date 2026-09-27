"""La medición del "después": recall, volumen y el intervalo de confianza.

DATOS DE EJEMPLO — no usar en producción. El escenario es pequeño a propósito: las cifras se
pueden comprobar con los dedos, y si la medición no da eso, la medición está mal.

Lo que se comprueba, en orden de importancia:

1. **El veredicto sale del intervalo, no de la diferencia.** Una diferencia positiva con un
   intervalo que cruza el 0 es «no concluyente», y ahí es donde es fácil hacer trampa sin querer.
2. **El bootstrap es pareado**: compara los dos métodos sobre el mismo contrato.
3. **Los contratos ganados se trían primero**, porque son los que deciden la tesis y el
   presupuesto puede cortar la tanda.
"""

import pytest

from radar.errores import ErrorRadar
from radar.evaluacion import agente

GANADORA = "B00000001"
OTRA = "B00000002"

# entry_id, cpv, fecha, quién ganó
ESCENARIO = [
    ("m1", ["72253000"], "2025-03-01", GANADORA),  # informática: la ven los dos
    ("m2", ["30213000"], "2025-03-01", GANADORA),  # equipos: el filtro 72/48 no la ve
    ("m3", ["79500000"], "2025-03-02", GANADORA),  # apoyo administrativo: tampoco
    ("m4", ["45000000"], "2025-03-02", OTRA),  # obra, de otra empresa
    ("m5", ["72100000"], "2025-03-03", None),  # informática sin adjudicar
]


def montar(conexion, decisiones: dict[str, str]) -> None:
    """El escenario, con el triaje ya guardado: medir no llama al modelo."""
    ids = {}
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_ficheros (sha256, tipo, url, ruta, bytes, descargado_en)"
            " VALUES (repeat('e', 64), 'feed', 'https://ejemplo.es/f', 'x', 1, now())"
            " ON CONFLICT DO NOTHING"
        )
        for numero, (entrada, cpv, fecha, ganador) in enumerate(ESCENARIO):
            cur.execute(
                "INSERT INTO stg_entradas (raw_fichero, posicion, entry_id, entry_updated)"
                " VALUES (repeat('e', 64), %s, %s, %s) RETURNING id",
                (numero, entrada, f"{fecha}T10:00:00+01:00"),
            )
            stg = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO licitaciones (entry_id, entry_updated, stg_entrada, objeto, cpv)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (entrada, f"{fecha}T10:00:00+01:00", stg, f"Objeto {entrada}", cpv),
            )
            ids[entrada] = cur.fetchone()[0]
            if ganador:
                cur.execute(
                    "INSERT INTO adjudicaciones (licitacion, adjudicatario, es_pyme) VALUES (%s, %s, true)",
                    (ids[entrada], ganador),
                )
        cur.execute(
            "INSERT INTO perfiles (alias, nif, rol, adjudicaciones, de_informatica, semilla,"
            " regla_sha256, texto, texto_sha256, congelado_en)"
            " VALUES ('Empresa C', %s, 'test', 3, 3, '1', repeat('c', 64), 'perfil', repeat('a', 64),"
            " now())",
            (GANADORA,),
        )
        for entrada, decision in decisiones.items():
            cur.execute(
                "INSERT INTO triajes (licitacion, alias, modelo, por_llamada, prompt_version,"
                " decision, motivo) VALUES (%s, 'Empresa C', %s, %s, %s, %s, 'x')",
                (
                    ids[entrada],
                    agente.VARIANTE["modelo"],
                    agente.VARIANTE["por_llamada"],
                    "triaje_v1",
                    decision,
                ),
            )
    conexion.commit()


# --- El veredicto, que es donde es fácil engañarse ------------------------------------


def test_una_diferencia_positiva_con_intervalo_que_cruza_el_cero_no_concluye():
    # Es el caso peligroso: la diferencia anima, el intervalo dice que no se puede afirmar.
    assert agente.veredicto_de({"diferencia": 0.2, "ic_inferior": -0.1, "ic_superior": 0.4}) == (
        "no concluyente"
    )


def test_solo_se_sostiene_si_el_intervalo_entero_es_positivo():
    assert agente.veredicto_de({"diferencia": 0.2, "ic_inferior": 0.05, "ic_superior": 0.4}) == ("sostenida")


def test_se_refuta_si_el_intervalo_entero_es_negativo():
    assert agente.veredicto_de({"diferencia": -0.2, "ic_inferior": -0.4, "ic_superior": -0.05}) == (
        "refutada"
    )


def test_sin_datos_no_hay_veredicto():
    assert agente.veredicto_de({"diferencia": None}) == "sin datos"


# --- El bootstrap ---------------------------------------------------------------------


def test_si_los_dos_metodos_aciertan_lo_mismo_la_diferencia_es_cero_y_el_intervalo_tambien():
    filas = [{"agente": 1, "baseline_a": 1} for _ in range(20)]
    salida = agente.bootstrap(filas, "baseline_a")
    assert salida["diferencia"] == 0.0
    assert salida["ic_inferior"] == salida["ic_superior"] == 0.0


def test_si_el_agente_gana_siempre_el_intervalo_no_toca_el_cero():
    filas = [{"agente": 1, "baseline_a": 0} for _ in range(20)]
    salida = agente.bootstrap(filas, "baseline_a")
    assert salida["diferencia"] == 1.0 and salida["ic_inferior"] > 0
    assert agente.veredicto_de(salida) == "sostenida"


def test_con_un_solo_contrato_de_diferencia_el_intervalo_cruza_el_cero():
    # 10 contratos, el agente ve uno más. Es justo lo que no se puede afirmar con n pequeño.
    filas = [{"agente": 1, "baseline_a": 1} for _ in range(9)]
    filas.append({"agente": 1, "baseline_a": 0})
    salida = agente.bootstrap(filas, "baseline_a")
    assert salida["diferencia"] == 0.1
    assert salida["ic_inferior"] == 0.0, "con un contrato no se puede excluir el 0"
    assert agente.veredicto_de(salida) == "no concluyente"


def test_el_bootstrap_sale_igual_dos_veces():
    filas = [{"agente": i % 2, "baseline_a": (i + 1) % 3} for i in range(30)]
    assert agente.bootstrap(filas, "baseline_a") == agente.bootstrap(filas, "baseline_a")


def test_el_bootstrap_es_pareado_no_dos_medias_sueltas():
    # Mismos recalls marginales (3 de 4 cada uno), pero en un caso aciertan los mismos contratos
    # y en el otro se cruzan. Pareado, el intervalo del segundo es mas ancho.
    juntos = [
        {"agente": 1, "baseline_a": 1},
        {"agente": 1, "baseline_a": 1},
        {"agente": 1, "baseline_a": 1},
        {"agente": 0, "baseline_a": 0},
    ]
    cruzados = [
        {"agente": 1, "baseline_a": 1},
        {"agente": 1, "baseline_a": 1},
        {"agente": 1, "baseline_a": 0},
        {"agente": 0, "baseline_a": 1},
    ]
    a, b = agente.bootstrap(juntos, "baseline_a"), agente.bootstrap(cruzados, "baseline_a")
    assert a["diferencia"] == b["diferencia"] == 0.0
    ancho_a = a["ic_superior"] - a["ic_inferior"]
    ancho_b = b["ic_superior"] - b["ic_inferior"]
    assert ancho_a == 0.0 and ancho_b > 0.0


# --- Sobre la base de datos ----------------------------------------------------------


def test_el_recall_del_agente_y_de_los_dos_baselines_salen_del_mismo_contrato(bd):
    with bd() as conexion:
        # El agente ve los tres ganados; el filtro 72/48 solo el primero.
        montar(conexion, {"m1": "si", "m2": "duda", "m3": "si", "m4": "no", "m5": "no"})
        datos = agente.indicadores(
            conexion,
            "Empresa C",
            GANADORA,
            {"baseline_a": ["72", "48"]},
            "2025-01-01",
            "2025-07-01",
            "2026-09-01",
        )
    assert len(datos["contratos"]) == 3
    assert agente.recall(datos["contratos"], "agente") == 1.0
    assert agente.recall(datos["contratos"], "baseline_a") == pytest.approx(1 / 3)
    # Los no ganados solo sirven para el volumen, y ninguno de los dos pasa aquí.
    assert datos["no_ganados_triados"] == 2 and datos["no_ganados_que_pasan"] == 0


def test_una_duda_cuenta_como_estar_en_la_lista(bd):
    with bd() as conexion:
        montar(conexion, {"m1": "duda", "m2": "no", "m3": "no", "m4": "no", "m5": "no"})
        datos = agente.indicadores(
            conexion, "Empresa C", GANADORA, {}, "2025-01-01", "2025-07-01", "2026-09-01"
        )
    assert agente.recall(datos["contratos"], "agente") == pytest.approx(1 / 3)


def test_un_contrato_todavia_sin_triar_no_cuenta_ni_a_favor_ni_en_contra(bd):
    with bd() as conexion:
        montar(conexion, {"m1": "si"})  # m2 y m3 sin triar
        datos = agente.indicadores(
            conexion, "Empresa C", GANADORA, {}, "2025-01-01", "2025-07-01", "2026-09-01"
        )
    assert len(datos["contratos"]) == 1
    assert datos["ganados_totales"] == 3, "los tres ganados se cuentan, pero solo uno está triado"


def test_los_contratos_ganados_se_trian_primero(bd):
    with bd() as conexion:
        montar(conexion, {})
        tareas = agente.plan(conexion, "test", "2025-01-01", "2025-07-01", "2026-09-01", 2)
    pendientes = tareas[0]["pendientes"]
    ganados = [i for i, lic in enumerate(pendientes) if lic["ganado"]]
    no_ganados = [i for i, lic in enumerate(pendientes) if not lic["ganado"]]
    assert ganados and max(ganados) < min(no_ganados), "un corte por presupuesto perdería M2, no M1"


def test_sin_nada_triado_lo_dice_sin_traza(bd):
    with bd() as conexion:
        montar(conexion, {})
    with pytest.raises(ErrorRadar) as fallo:
        agente.medir("test")
    assert "no hay M1 que medir" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)


def test_lo_ya_triado_no_se_vuelve_a_triar(bd):
    with bd() as conexion:
        montar(conexion, {"m1": "si"})
        tareas = agente.plan(conexion, "test", "2025-01-01", "2025-07-01", "2026-09-01", 2)
    pendientes = [lic["entry_id"] for lic in tareas[0]["pendientes"]]
    assert "m1" not in pendientes


def test_el_informe_se_puede_imprimir_en_la_consola_de_windows(bd, capsys):
    # La consola de Windows es cp1252: una flecha o una comilla tipografica rompen el informe
    # entero justo al final, cuando ya se ha pagado la medicion. Paso el 26-09 con radar.estado
    # y volvio a pasar el 27-09 con este informe, con 263 triajes ya pagados.
    with bd() as conexion:
        montar(conexion, {"m1": "si", "m2": "duda", "m3": "no", "m4": "no", "m5": "no"})
    agente.informe("test", "comando de prueba")
    salida = capsys.readouterr().out
    assert "TESIS" in salida
    salida.encode("cp1252")  # si esto lanza, el informe no se puede imprimir en Windows


# --- El informe que se regenera solo, que es la puerta de salida de la fase -------------


def fila(metrica, variante, valor, **extra) -> dict:
    base = {
        "metrica": metrica,
        "variante": variante,
        "alias": extra.get("alias"),
        "valor": valor,
        "ic_inferior": extra.get("ic_inferior"),
        "ic_superior": extra.get("ic_superior"),
        "n": extra.get("n", 10),
        "detalle": extra.get("detalle", {}),
        "git_commit": "abc1234",
        "comando": "uv run python -m radar.evaluacion.agente",
        "calculada_en": None,
    }
    return base


def test_el_informe_dice_no_concluyente_cuando_el_intervalo_cruza_el_cero(tmp_path):
    from radar.evaluacion import __main__ as informe

    filas = [
        fila(
            "M1_diferencia",
            "agente_menos_baseline_a_test",
            0.075,
            ic_inferior=-0.15,
            ic_superior=0.30,
            n=40,
            detalle={"recall_agente": 0.775, "recall_baseline": 0.70, "veredicto": "no concluyente"},
        )
    ]
    destino = informe.escribir(filas, tmp_path / "fase5.md")
    texto = destino.read_text(encoding="utf-8")
    assert "No concluyente" in texto
    assert "[-15.0 %, 30.0 %]" in texto
    assert "NO CONCLUYENTE" in texto


def test_el_informe_no_se_inventa_lo_que_falta(tmp_path):
    from radar.evaluacion import __main__ as informe

    destino = informe.escribir([fila("M1", "agente_test", 0.5, alias="Empresa C")], tmp_path / "f.md")
    texto = destino.read_text(encoding="utf-8")
    assert "## Lo que falta por medir" in texto
    for pendiente in ("M3", "M4", "M6"):
        assert pendiente in texto
    assert "Sin medir" in texto


def test_solo_se_sostiene_la_tesis_si_gana_a_los_dos_baselines(tmp_path):
    from radar.evaluacion import __main__ as informe

    gana = fila(
        "M1_diferencia",
        "agente_menos_baseline_a_test",
        0.2,
        ic_inferior=0.05,
        ic_superior=0.35,
        detalle={"veredicto": "sostenida"},
    )
    empata = fila(
        "M1_diferencia",
        "agente_menos_baseline_b_test",
        0.0,
        ic_inferior=-0.1,
        ic_superior=0.1,
        detalle={"veredicto": "no concluyente"},
    )
    assert informe.veredicto_global([gana]) == "sostenida frente a los dos baselines"
    assert informe.veredicto_global([gana, empata]) == (
        "sostenida frente a un baseline y no concluyente frente al otro"
    )
    del tmp_path


def test_el_informe_lleva_el_commit_de_cada_cifra(tmp_path):
    from radar.evaluacion import __main__ as informe

    destino = informe.escribir([fila("M1", "agente_test", 0.5, alias="Empresa C")], tmp_path / "f.md")
    assert "abc1234" in destino.read_text(encoding="utf-8")
