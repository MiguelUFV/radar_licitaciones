"""Congelado de los perfiles: lo que impide cambiarlos despues de medir."""

from pathlib import Path

import pytest

from radar import perfiles
from radar.errores import ErrorRadar

PERFIL = """# Perfil de Empresa A

## 1. Qué hace la empresa

Desarrolla software a medida.

## 2. Servicios que ofrece

- Desarrollo de aplicaciones

## Fuentes

- https://ejemplo.es/quienes-somos (consultada el 27-09-2026)
- https://ejemplo.es/servicios (27-09-2026)

## Firma del perfil

| Escrito el | 27-09-2026 |
"""


def sembrar_empresa(bd, alias="Empresa A", nif="B00000001") -> None:
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute(
            "INSERT INTO perfiles (alias, nif, rol, adjudicaciones, de_informatica, semilla,"
            " regla_sha256) VALUES (%s, %s, 'desarrollo', 10, 9, '1', repeat('c', 64))",
            (alias, nif),
        )
        conexion.commit()


def test_el_alias_sale_del_nombre_del_fichero(tmp_path):
    assert perfiles.alias_del_fichero(tmp_path / "perfil_empresa_a.md") == "Empresa A"
    assert perfiles.alias_del_fichero(tmp_path / "perfil_empresa_g.md") == "Empresa G"


def test_un_fichero_mal_nombrado_se_avisa_sin_traza(tmp_path):
    with pytest.raises(ErrorRadar) as fallo:
        perfiles.alias_del_fichero(tmp_path / "abaco.md")
    assert "no se llama como debe" in str(fallo.value)
    assert "Traceback" not in str(fallo.value)


def test_las_fuentes_se_extraen_para_poder_auditar():
    fuentes = perfiles.fuentes_de(PERFIL)
    assert fuentes.count("\n") == 1
    assert "quienes-somos" in fuentes


def test_un_perfil_sin_fuentes_no_se_acepta():
    sin_fuentes = PERFIL.replace("## Fuentes", "## Otra cosa")
    with pytest.raises(ErrorRadar) as fallo:
        perfiles.fuentes_de(sin_fuentes)
    assert "Fuentes" in str(fallo.value)


def test_congela_el_perfil_con_su_huella(bd, tmp_path):
    sembrar_empresa(bd)
    (tmp_path / "perfil_empresa_a.md").write_text(PERFIL, encoding="utf-8")

    resumen = perfiles.congelar(tmp_path)
    assert resumen["congelados"] == 1

    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT texto_sha256, congelado_en, fuentes FROM perfiles WHERE alias = 'Empresa A'")
        huella, cuando, fuentes = cur.fetchone()
    assert len(huella) == 64
    assert cuando is not None
    assert "ejemplo.es" in fuentes


def test_volver_a_congelar_lo_mismo_no_cambia_nada(bd, tmp_path):
    sembrar_empresa(bd)
    (tmp_path / "perfil_empresa_a.md").write_text(PERFIL, encoding="utf-8")
    perfiles.congelar(tmp_path)

    segunda = perfiles.congelar(tmp_path)
    assert segunda["congelados"] == 0
    assert segunda["ya_estaban"] == 1


def test_si_el_perfil_cambia_despues_de_congelarse_se_para(bd, tmp_path):
    # Es el control que da valor a la medicion: si el perfil se puede retocar despues, la cifra
    # publicada no significa nada.
    sembrar_empresa(bd)
    fichero = tmp_path / "perfil_empresa_a.md"
    fichero.write_text(PERFIL, encoding="utf-8")
    perfiles.congelar(tmp_path)

    fichero.write_text(
        PERFIL.replace("software a medida", "software a medida y ciberseguridad"), encoding="utf-8"
    )
    with pytest.raises(ErrorRadar) as fallo:
        perfiles.congelar(tmp_path)
    assert "ha cambiado" in str(fallo.value)
    assert "volver a medir" in str(fallo.value)

    # Y con --rehacer sí, porque a veces hay que corregir algo y entonces se vuelve a medir.
    assert perfiles.congelar(tmp_path, rehacer=True)["congelados"] == 1


def test_una_empresa_sin_sortear_no_se_puede_congelar(bd, tmp_path):
    (tmp_path / "perfil_empresa_a.md").write_text(PERFIL, encoding="utf-8")
    with pytest.raises(ErrorRadar) as fallo:
        perfiles.congelar(tmp_path)
    assert "aplicar la regla" in str(fallo.value)


def test_el_registro_versionado_no_lleva_nombres_ni_direcciones(bd, tmp_path):
    sembrar_empresa(bd)
    (tmp_path / "perfil_empresa_a.md").write_text(PERFIL, encoding="utf-8")
    perfiles.congelar(tmp_path)

    destino = tmp_path / "registro.md"
    with bd() as conexion:
        perfiles.escribir_registro(conexion, destino)
    texto = destino.read_text(encoding="utf-8")
    assert "Empresa A" in texto
    assert "B00000001" not in texto  # el NIF no sale
    assert "ejemplo.es" not in texto  # las direcciones tampoco
    assert "desarrollo" in texto


# --- La cifra de negocio, que estaba escrita en el perfil y no en la tabla ---------------
#
# El 27-09-2026 los siete perfiles estaban congelados con su cifra de negocio dentro, y la
# columna `cifra_negocio` estaba vacía en las siete filas. Consecuencia: la regla del volumen
# de negocios no podía dispararse nunca y M3 no se podía medir. Se carga del texto congelado.

FILA_CON_INTERVALO = (
    "| Campo | Valor | De dónde sale |\n"
    "|---|---|---|\n"
    "| Cifra anual de negocio | Entre 600.000 € y 1.500.000 € (intervalo) | Iberinform, 27-09-2026 |\n"
    "| Año de esa cifra | No se publica | |\n"
)


def test_de_un_intervalo_se_toma_el_extremo_inferior():
    # SPEC §9: el extremo inferior es el que menos solvencia atribuye a la empresa, así que si
    # con él el radar dice que cumple, cumple de verdad.
    importe, fuente = perfiles.cifra_de(FILA_CON_INTERVALO)
    assert importe == 600000.0
    assert "Iberinform" in fuente


def test_si_el_perfil_dice_que_no_hay_cifra_no_se_inventa():
    texto = "| Cifra anual de negocio | **No publicada** | Buscada en cuatro directorios |\n"
    importe, fuente = perfiles.cifra_de(texto)
    assert importe is None and "sin cifra pública" in fuente


def test_un_perfil_sin_esa_linea_no_da_cifra():
    assert perfiles.cifra_de("## Qué hace\nSoftware de gestión.\n") == (None, None)


def test_una_cifra_exacta_tambien_se_lee():
    importe, _ = perfiles.cifra_de("| Cifra anual de negocio | 812.450 € | Cuentas depositadas |\n")
    assert importe == 812450.0


def test_congelar_en_una_carpeta_de_pruebas_no_reescribe_el_registro_de_verdad(bd, tmp_path):
    """El 30-09-2026 `git status` sacó `docs/perfiles_congelados.md` modificado después de
    pasar los tests: `congelar()` recibía la carpeta de perfiles de prueba, pero escribía el
    registro en su ruta por defecto, que es un documento congelado y versionado. La huella no
    cambiaba, la fecha sí, y nadie lo habría notado hasta que el candado del diagnóstico
    avisara de que el documento congelado se ha tocado.
    """
    # La ruta de verdad, escrita aquí a propósito: `perfiles.PUBLICO` lo desvía la fixture
    # `ningun_test_escribe_en_docs`, y lo que se vigila es justo el fichero del repositorio.
    real = Path("docs/perfiles_congelados.md")
    de_verdad = real.read_text(encoding="utf-8")
    sembrar_empresa(bd)
    (tmp_path / "perfil_empresa_a.md").write_text(PERFIL, encoding="utf-8")

    perfiles.congelar(tmp_path, registro=tmp_path / "registro.md")

    assert real.read_text(encoding="utf-8") == de_verdad
    assert (tmp_path / "registro.md").exists()
