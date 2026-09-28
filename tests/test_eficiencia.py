"""M9 y M10: el trabajo que cuesta cada acierto.

DATOS DE EJEMPLO — no usar en producción.

La definición está congelada en `docs/METRICA_EFICIENCIA.md` y estos tests comprueban que el
código hace lo que ese documento dice, no lo que convendría que dijera. Lo que más importa:

1. **Que M2 salga del conjunto comparable.** Hay dos conjuntos de volúmenes en `eval_resultados`
   con denominadores distintos, y mezclarlos da un número que no significa nada.
2. **Que el veredicto aplique la regla escrita antes** (3 de 5 empresas), y no la que salga bien.
3. **Que un método que no encuentra ningún contrato no tenga M9 «infinita»**, sino ninguna.
"""

import pytest

from radar.evaluacion import eficiencia

DIAS = eficiencia.DIAS_CON_PUBLICACIONES


# --- La aritmética, contra el documento ------------------------------------------------


def test_m9_son_las_licitaciones_que_pasan_por_cada_contrato_encontrado():
    # 10 licitaciones al día durante el periodo, y encuentra 5 contratos de 10 (recall 0,5).
    assert eficiencia.m9(0.5, 10.0, 10) == pytest.approx(10 * DIAS / 5)


def test_un_metodo_que_no_encuentra_nada_no_tiene_m9_infinita():
    # Dividir entre cero daría infinito, y un infinito en una tabla se lee como un número.
    assert eficiencia.m9(0.0, 10.0, 10) is None


def test_m10_recorta_el_recall_del_rival_en_proporcion_al_volumen():
    # El rival acierta el 90 % entregando 300 al día; el agente entrega 100. Mirando un tercio
    # de su lista al azar, se espera un tercio de sus aciertos.
    assert eficiencia.m10(0.9, 300.0, 100.0) == pytest.approx(0.3)


def test_a_un_rival_mas_pequeno_que_el_agente_no_se_le_regala_recall():
    # Si el rival ya entrega menos que el agente, no se le recorta ni se le amplía: el tope es 1.
    assert eficiencia.m10(0.8, 10.0, 100.0) == pytest.approx(0.8)


# --- La regla de decisión, tal y como se escribió --------------------------------------


def m9_de(alias: str, agente: float, a: float, b: float) -> list[dict]:
    return [
        {"metrica": "M9", "variante": "agente_test", "alias": alias, "valor": agente},
        {"metrica": "M9", "variante": "baseline_a", "alias": alias, "valor": a},
        {"metrica": "M9", "variante": "baseline_b", "alias": alias, "valor": b},
    ]


def test_el_veredicto_exige_las_tres_de_cinco_que_pedia_el_documento():
    # Gana en dos: no llega. El documento pide «3 de 5 o más», escrito antes de ver nada.
    dos = m9_de("C", 10, 20, 30) + m9_de("D", 10, 20, 30)
    tres = [
        {"metrica": "M9", "variante": v, "alias": a, "valor": x}
        for a in "EFG"
        for v, x in (("agente_test", 99), ("baseline_a", 20), ("baseline_b", 30))
    ]
    assert "solo gana" in eficiencia.veredicto(dos + tres)

    gana_tres = m9_de("C", 10, 20, 30) + m9_de("D", 10, 20, 30) + m9_de("E", 10, 20, 30)
    pierde_dos = [
        {"metrica": "M9", "variante": v, "alias": a, "valor": x}
        for a in "FG"
        for v, x in (("agente_test", 99), ("baseline_a", 20), ("baseline_b", 30))
    ]
    assert "menos licitaciones" in eficiencia.veredicto(gana_tres + pierde_dos)


def test_el_veredicto_no_esconde_que_m1_sigue_refutada():
    gana = [x for a in "CDE" for x in m9_de(a, 10, 20, 30)]
    assert "M1 sigue refutada" in eficiencia.veredicto(gana)


# --- De dónde salen los números --------------------------------------------------------


def montar(conexion) -> None:
    """Las dos clases de fila de M2 que hay en la base: la comparable y la que no lo es."""
    with conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO perfiles (alias, nif, rol, adjudicaciones, de_informatica, semilla,"
            " regla_sha256) VALUES ('Empresa C', 'B00000001', 'test', 16, 16, '1', repeat('a', 64))"
        )
        comun = ("2025-01-01", "2025-07-01", "x", "cmd")
        cur.execute(
            "INSERT INTO eval_resultados (metrica, variante, alias, periodo_desde, periodo_hasta,"
            " valor, n, git_commit, comando) VALUES ('M1', 'agente_test', 'Empresa C', %s, %s,"
            " 0.5, 16, %s, %s)",
            comun,
        )
        for variante, recall in (("baseline_a", 0.625), ("baseline_b", 0.5625)):
            cur.execute(
                "INSERT INTO eval_resultados (metrica, variante, alias, periodo_desde,"
                " periodo_hasta, valor, n, git_commit, comando) VALUES ('M1', %s, 'Empresa C',"
                " %s, %s, %s, 16, %s, %s)",
                (variante, *comun[:2], recall, *comun[2:]),
            )
        # La comparable: el volumen del agente, con los dos rivales en su detalle.
        cur.execute(
            "INSERT INTO eval_resultados (metrica, variante, alias, periodo_desde, periodo_hasta,"
            " valor, n, detalle, git_commit, comando) VALUES ('M2', 'agente_test', 'Empresa C',"
            ' %s, %s, 7.5751, 88, \'{"volumen_baselines_al_dia": {"baseline_a": 30.3,'
            ' "baseline_b": 68.18}}\', %s, %s)',
            comun,
        )
        # La que NO lo es: medida en la Fase 3 sobre el universo entero.
        cur.execute(
            "INSERT INTO eval_resultados (metrica, variante, alias, periodo_desde, periodo_hasta,"
            " valor, n, git_commit, comando) VALUES ('M2', 'baseline_a', 'Empresa C', %s, %s,"
            " 49.9061, 120656, %s, %s)",
            comun,
        )
    conexion.commit()


def test_el_volumen_sale_del_conjunto_comparable_y_no_del_otro(bd):
    # `eval_resultados` tiene dos M2 de baseline_a para la misma empresa: 30,3 al día (medida
    # sobre la misma base que el agente) y 49,9 (medida en la Fase 3 sobre el universo entero).
    # Dividir el recall por el volumen equivocado da un número que no significa nada.
    with bd() as conexion:
        montar(conexion)
        empresas = eficiencia.leer(conexion)
    assert empresas["Empresa C"]["volumen"]["baseline_a"] == 30.3, (
        "se ha colado el volumen de la Fase 3, que no es comparable con el del agente"
    )
    assert empresas["Empresa C"]["volumen"]["agente"] == pytest.approx(7.5751)
    assert empresas["Empresa C"]["contratos"] == 16


def test_de_punta_a_punta_sobre_la_base(bd):
    with bd() as conexion:
        montar(conexion)
        resultados = eficiencia.calcular(eficiencia.leer(conexion))
    m9 = {r["variante"]: r["valor"] for r in resultados if r["metrica"] == "M9"}
    # 7,5751 al día × 181 días / (0,5 × 16 contratos) = 171,4
    assert m9["agente_test"] == pytest.approx(7.5751 * DIAS / 8, rel=1e-3)
    assert m9["agente_test"] < m9["baseline_a"] < m9["baseline_b"]
    m10 = {r["variante"]: r["valor"] for r in resultados if r["metrica"] == "M10"}
    assert m10["agente_test"] == pytest.approx(0.5), "al agente no se le recorta su propia lista"
    assert m10["baseline_b"] < m10["baseline_a"] < m10["agente_test"]


def test_sin_mediciones_previas_lo_dice_sin_traza(bd):
    with bd() as conexion:
        assert eficiencia.leer(conexion) == {}
