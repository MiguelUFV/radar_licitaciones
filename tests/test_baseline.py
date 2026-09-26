"""El filtro CPV de referencia, aplicado como dice docs/BASELINE.md.

El vocabulario de prueba es un trozo del oficial, con códigos y descripciones reales.
"""

import pytest

from radar import baseline
from radar.errores import ErrorRadar

VOCABULARIO = {
    "03000000": "Productos de la agricultura, ganadería, pesca, silvicultura y productos afines.",
    "30000000": "Máquinas de oficina y de cálculo, equipo y suministros, excepto paquetes de software.",
    "45000000": "Trabajos de construcción.",
    "45262000": "Trabajos especiales de construcción distintos de los de tejados.",
    "48000000": "Paquetes de software y sistemas de información.",
    "48310000": "Paquetes de software de creación de documentos.",
    "72000000": "Servicios TI: consultoría, desarrollo de software, Internet y apoyo.",
    "72250000": "Servicios de sistemas y apoyo.",
    "72260000": "Servicios relacionados con el software.",
    "80000000": "Servicios de enseñanza y formación.",
}

PERFIL = """# Perfil de Empresa de prueba

## 1. Qué hace la empresa

Desarrollamos software a medida para administraciones públicas.

## 2. Servicios que ofrece

- Desarrollo de software
- Consultoría informática

## 3. A quién vende

Administración pública.

## 5. Certificaciones y homologaciones que anuncia

Certificado de construcción con hormigón para las obras de su antigua actividad.
"""


def test_el_prefijo_de_una_division_no_se_queda_en_un_digito():
    # 30000000 sin ceros finales es "3", y "3" casa con 03xxxxxx, que es agricultura. Una
    # division son dos digitos siempre.
    assert baseline.prefijos(["30000000"]) == ["30"]
    assert baseline.prefijos(["03000000"]) == ["03"]
    assert baseline.prefijos(["72250000"]) == ["7225"]


def test_un_prefijo_de_dos_digitos_no_arrastra_a_la_division_vecina():
    assert baseline.pasa_el_filtro(["03211000"], ["30"]) is False
    assert baseline.pasa_el_filtro(["30211000"], ["30"]) is True


def test_solo_cuentan_los_apartados_que_dice_el_procedimiento():
    # El procedimiento dice: apartados 1 y 2, nada mas. Si entrara el 5, este perfil traeria
    # "hormigon" y el filtro se llenaria de codigos de construccion.
    usado = baseline.parte_util(PERFIL)
    assert "Desarrollamos software" in usado
    assert "hormigon" not in baseline.sin_acentos(usado)
    assert "hormigon" not in baseline.terminos(usado)


def test_las_palabras_generales_no_cuentan_como_termino():
    encontrados = baseline.terminos("Servicios y suministros integrales para empresas del sector")
    assert encontrados == set()


def test_la_semilla_sale_de_las_palabras_del_perfil():
    semilla = baseline.codigos_semilla(baseline.parte_util(PERFIL), VOCABULARIO)
    assert "48000000" in semilla  # "software"
    assert "72000000" in semilla  # "software", "consultoria", "desarrollo"
    assert "45000000" not in semilla  # construccion: no esta en los apartados 1 y 2
    assert "03000000" not in semilla


def test_solo_entran_divisiones_y_grupos():
    assert baseline.es_division_o_grupo("72000000")
    assert baseline.es_division_o_grupo("72250000")
    assert not baseline.es_division_o_grupo("72253100")


def test_un_perfil_sin_nada_que_buscar_avisa_sin_traza():
    with pytest.raises(ErrorRadar) as fallo:
        baseline.codigos_semilla("## 1. Qué hace\n\nServicios y productos.\n", VOCABULARIO)
    assert "a qué se dedica" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)


def test_un_perfil_sin_los_apartados_del_procedimiento_avisa():
    with pytest.raises(ErrorRadar) as fallo:
        baseline.parte_util("# Mi empresa\n\nHacemos cosas.\n")
    assert "plantilla" in str(fallo.value)


def test_el_baseline_obvio_son_las_divisiones_de_informatica():
    # Baseline A: sin nada que decidir, dos numeros (docs/BASELINE.md 2).
    assert baseline.PREFIJOS_OBVIOS == ("72", "48")
    assert baseline.pasa_el_filtro(["72253200"], baseline.PREFIJOS_OBVIOS) is True
    assert baseline.pasa_el_filtro(["48000000"], baseline.PREFIJOS_OBVIOS) is True
    # Un contrato de informatica publicado bajo otro CPV: el filtro tipico no lo ve, y ahi
    # esta la tesis del proyecto.
    assert baseline.pasa_el_filtro(["30213000"], baseline.PREFIJOS_OBVIOS) is False


def test_el_baseline_amplio_se_escribe_con_las_dos_huellas(tmp_path, monkeypatch):
    monkeypatch.setattr(baseline, "vocabulario", lambda *a, **kw: VOCABULARIO)
    monkeypatch.setattr(baseline, "huella_del_vocabulario", lambda: "f" * 64)
    perfil = tmp_path / "perfil_empresa_z.md"
    perfil.write_text(PERFIL, encoding="utf-8")

    resumen = baseline.congelar(perfil, tmp_path / "baseline_z.md")
    escrito = (tmp_path / "baseline_z.md").read_text(encoding="utf-8")
    assert resumen["codigos"] >= 2
    assert "72000000" in escrito
    assert "45000000" not in escrito
    assert "Huella del perfil" in escrito
    assert "ffffffffffffffff" in escrito
