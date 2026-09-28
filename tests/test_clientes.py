"""El alta de una empresa: lo que se le pregunta, lo que se valida y lo que lee el modelo.

DATOS DE EJEMPLO — no usar en producción.

Lo que se comprueba, en orden de importancia:

1. **Que se guarde el mismo número que se validó.** El 28-09-2026 no era así: `validar` leía
   «1.00» como un euro y `numero` lo leía como cien, así que un cliente que ponía un tope de
   1 € al día acababa con uno de 100 €. Validar una cosa y guardar otra es el peor fallo
   posible en un formulario que decide cuánto se gasta.
2. **Que el texto que lee el modelo lleve lo que la Fase 5 demostró que falta**: las marcas que
   distribuye y lo que hace aunque no sea su bandera.
3. **Que un error no borre lo que la empresa ya había escrito.**
"""

import pytest

from radar import clientes, empresas
from radar.errores import ErrorRadar

COMPLETO = {
    "nombre": "Soluciones del Norte, S.L.",
    "alias": "Empresa del Norte",
    "correo": "contratacion@ejemplo.es",
    "que_hace": "Desarrollamos software de control horario para ayuntamientos y empresas.",
    "productos": "Autodesk, PRESTO, Adobe Creative Cloud",
    "servicios": "Formación, suministro de terminales, soporte",
    "no_hace": "Obra civil, limpieza",
    "certificaciones": "ISO 9001, ISO 27001",
    "ambito": "Asturias y Cantabria",
    "cifra_negocio": "850000",
    "tope_diario_eur": "1.00",
}


# --- Los números: se guarda lo que se valida ------------------------------------------


@pytest.mark.parametrize(
    ("escrito", "esperado"),
    [
        ("1.00", 1.0),
        ("1,00", 1.0),
        ("0.07", 0.07),
        ("2", 2.0),
        ("850000", 850000.0),
        ("850.000", 850000.0),
        ("1.250.000", 1250000.0),
        ("1.234,56", 1234.56),
        ("", None),
        ("lo que sea", None),
    ],
)
def test_los_numeros_se_leen_como_los_escribe_una_persona(escrito, esperado):
    assert clientes.numero(escrito) == esperado


def test_un_tope_de_un_euro_no_se_convierte_en_cien(bd):
    # El fallo de verdad: "1.00" se guardaba como 100 porque el punto se leía como separador
    # de miles. El cliente pedía gastar un euro al día y el radar entendía cien.
    clientes.dar_de_alta(COMPLETO)
    with bd() as conexion:
        cliente = empresas.la_de(conexion, "Empresa del Norte")
    assert float(cliente["tope_diario_eur"]) == 1.0


def test_un_tope_imposible_se_rechaza_antes_de_guardarlo():
    errores = clientes.validar(clientes.limpiar({**COMPLETO, "tope_diario_eur": "500"}))
    assert "tope_diario_eur" in errores and "máximo" in errores["tope_diario_eur"]


def test_validar_y_guardar_leen_el_mismo_numero():
    # Si estas dos funciones no usan el mismo lector, se valida una cosa y se guarda otra.
    for escrito in ("1.00", "0,50", "3", "850.000"):
        valores = clientes.limpiar({**COMPLETO, "tope_diario_eur": escrito})
        errores = clientes.validar(valores)
        if not errores:
            assert clientes.numero(escrito) is not None


# --- El texto que lee el modelo -------------------------------------------------------


def test_el_perfil_lleva_las_marcas_y_lo_que_hace_de_paso():
    # Es lo que la Fase 5 midió que faltaba: 19 de los 20 contratos perdidos eran productos que
    # el perfil no nombraba.
    texto = clientes.como_lo_lee_el_modelo(clientes.limpiar(COMPLETO))
    assert "Autodesk" in texto and "PRESTO" in texto
    assert "suministro de terminales" in texto.lower()
    assert "Lo que no hace" in texto and "Obra civil" in texto


def test_un_apartado_vacio_no_se_escribe():
    texto = clientes.como_lo_lee_el_modelo(clientes.limpiar({**COMPLETO, "certificaciones": ""}))
    assert "Certificaciones" not in texto, "una sección vacía dice menos que no estar"


def test_la_cifra_se_escribe_en_euros_legibles():
    texto = clientes.como_lo_lee_el_modelo(clientes.limpiar(COMPLETO))
    assert "850.000 euros" in texto


# --- La validación --------------------------------------------------------------------


def test_sin_lo_imprescindible_no_se_da_de_alta():
    errores = clientes.validar(clientes.limpiar({"nombre": "X"}))
    for campo in ("alias", "correo", "que_hace"):
        assert campo in errores
    assert all(not e.startswith("Error") for e in errores.values())


def test_una_descripcion_de_una_linea_se_rechaza_diciendo_por_que():
    errores = clientes.validar(clientes.limpiar({**COMPLETO, "que_hace": "Informática."}))
    assert "acierta poco" in errores["que_hace"]


def test_un_correo_que_no_lo_es_se_rechaza():
    errores = clientes.validar(clientes.limpiar({**COMPLETO, "correo": "arroba.es"}))
    assert "correo" in errores


def test_dar_de_alta_con_errores_no_escribe_nada(bd):
    with pytest.raises(ErrorRadar) as fallo:
        clientes.dar_de_alta({**COMPLETO, "correo": "no"})
    assert "Traceback" not in str(fallo.value)
    with bd() as conexion, conexion.cursor() as cur:
        cur.execute("SELECT count(*) FROM clientes")
        assert cur.fetchone()[0] == 0


# --- Guardar y volver a guardar --------------------------------------------------------


def test_guardar_dos_veces_actualiza_y_no_duplica(bd):
    primero = clientes.dar_de_alta(COMPLETO)
    segundo = clientes.dar_de_alta({**COMPLETO, "productos": "Autodesk, PRESTO, Adobe, Fujitsu"})
    assert primero["nuevo"] and not segundo["nuevo"]
    with bd() as conexion:
        cliente = empresas.la_de(conexion, "Empresa del Norte")
        with conexion.cursor() as cur:
            cur.execute("SELECT count(*) FROM clientes")
            assert cur.fetchone()[0] == 1
    assert "Fujitsu" in cliente["texto"]
    assert cliente["huella"] != clientes.huella(primero["texto"]), (
        "si cambia el perfil tiene que cambiar su huella: es lo que ata una decisión a su texto"
    )


def test_una_empresa_que_no_existe_lo_dice(bd):
    with bd() as conexion, pytest.raises(ErrorRadar) as fallo:
        empresas.la_de(conexion, "Nadie")
    assert "Nadie" in str(fallo.value) and "Traceback" not in str(fallo.value)
