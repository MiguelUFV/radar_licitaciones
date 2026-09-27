"""Reglas de decisión v1. Congeladas: para cambiarlas se crea `v2.py`.

Cada requisito extraído del pliego se compara con lo que el radar sabe de la empresa, que es
**solo su perfil y su cifra de negocio pública**. De ahí sale uno de tres resultados:

- `cumple` — se puede demostrar con lo que hay.
- `no_cumple` — se puede demostrar que **no**. Es el único que descarta una licitación, y por
  eso solo lo produce el volumen de negocios, que es una comparación de dos números.
- `no_se_puede_saber` — ni una cosa ni otra. No descarta: la licitación va a revisión con el
  requisito ya localizado y citado, que es la mitad del trabajo hecho.

**Por qué casi todo acaba en `no_se_puede_saber`:** porque es la verdad. El radar no sabe qué
trabajos ha hecho la empresa ni qué certificaciones tiene si su web no lo dice. Inventarse un
«cumple» sería exactamente el tipo de decisión que este proyecto no quiere tomar.

**Lo que se podría hacer y no se hace:** la base de datos tiene las adjudicaciones que ganó cada
empresa, así que para `trabajos_similares` se podría mirar si ya ha hecho trabajos parecidos.
No se mira. Esos contratos son la verdad de referencia con la que se mide el radar: usarlos
para decidir sería escribir la respuesta en el enunciado (`docs/REGLA_SELECCION.md` §6).

**El riesgo conocido de `no_cumple`:** la cifra de negocio de estas empresas sale de intervalos
publicados y se usa el extremo inferior (`docs/SPEC.md` §9). Una empresa puede facturar más de
lo que aquí se cree, así que un «no apta» por volumen puede ser un falso negativo. Eso es
exactamente lo que mide M3, y el criterio de éxito exige M3 ≤ 5 %.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

VERSION = "v1"

APTA, NO_APTA, REVISAR = "apta", "no_apta", "revisar"
CUMPLE, NO_CUMPLE, NO_SE_SABE = "cumple", "no_cumple", "no_se_puede_saber"

# Certificaciones que se saben reconocer en un perfil. Si el pliego exige otra cosa, el
# resultado es "no se puede saber", no "no cumple".
CERTIFICACIONES = re.compile(
    r"ISO[\s/]*(?:IEC[\s/]*)?(\d{4,5})|"
    r"(Esquema Nacional de Seguridad|ENS)|(EMAS)|(PCI[\s-]?DSS)",
    re.I,
)


@dataclass
class Motivo:
    tipo: str
    resultado: str
    texto: str  # explicación en castellano, para la ficha
    cita: str = ""
    pagina: int | None = None


@dataclass
class Decision:
    veredicto: str
    motivos: list[Motivo] = field(default_factory=list)
    version: str = VERSION

    @property
    def bloqueos(self) -> list[Motivo]:
        return [m for m in self.motivos if m.resultado == NO_CUMPLE]


def sin_tildes(texto: str) -> str:
    plano = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in plano if unicodedata.category(c) != "Mn")


def euros(cantidad: float) -> str:
    return f"{cantidad:,.0f} €".replace(",", ".")


def certificaciones_de(texto: str) -> list[str]:
    """Las certificaciones nombradas en un texto, normalizadas (ISO 9001, ENS…)."""
    encontradas = []
    for m in CERTIFICACIONES.finditer(texto or ""):
        if m.group(1):
            encontradas.append(f"ISO {m.group(1)}")
        elif m.group(2):
            encontradas.append("ENS")
        elif m.group(3):
            encontradas.append("EMAS")
        elif m.group(4):
            encontradas.append("PCI DSS")
    return sorted(set(encontradas))


def la_tiene_el_perfil(certificacion: str, perfil: str) -> bool:
    if certificacion in ("ENS", "EMAS", "PCI DSS"):
        return certificacion in certificaciones_de(perfil)
    numero = certificacion.split()[-1]
    return any(c.endswith(numero) for c in certificaciones_de(perfil))


def volumen(requisito, empresa: dict) -> Motivo:
    cifra = empresa.get("cifra_negocio")
    exigido = requisito.importe_eur
    comun = {"tipo": requisito.tipo, "cita": requisito.cita, "pagina": requisito.pagina}
    if exigido is None:
        return Motivo(
            resultado=NO_SE_SABE,
            texto=f"El pliego exige volumen de negocio pero sin cifra clara: {requisito.exigencia}",
            **comun,
        )
    if cifra is None:
        return Motivo(
            resultado=NO_SE_SABE,
            texto=(
                f"El pliego pide {euros(exigido)} de volumen anual y no consta la cifra de negocio "
                "de la empresa, así que no se puede comparar."
            ),
            **comun,
        )
    if float(cifra) >= exigido:
        return Motivo(
            resultado=CUMPLE,
            texto=(
                f"El pliego pide {euros(exigido)} de volumen anual y la empresa declara "
                f"{euros(float(cifra))}."
            ),
            **comun,
        )
    return Motivo(
        resultado=NO_CUMPLE,
        texto=(
            f"El pliego pide {euros(exigido)} de volumen anual y de la empresa consta "
            f"{euros(float(cifra))} ({empresa.get('cifra_fuente') or 'fuente sin anotar'})."
        ),
        **comun,
    )


def certificacion(requisito, empresa: dict) -> Motivo:
    comun = {"tipo": requisito.tipo, "cita": requisito.cita, "pagina": requisito.pagina}
    pedidas = certificaciones_de(f"{requisito.exigencia} {requisito.cita}")
    perfil = empresa.get("perfil") or ""
    if not pedidas:
        return Motivo(
            resultado=NO_SE_SABE,
            texto=f"El pliego exige una certificación que no se sabe reconocer: {requisito.exigencia}",
            **comun,
        )
    tiene = [c for c in pedidas if la_tiene_el_perfil(c, perfil)]
    faltan = [c for c in pedidas if c not in tiene]
    if not faltan:
        return Motivo(
            resultado=CUMPLE,
            texto=f"El pliego exige {', '.join(pedidas)} y el perfil de la empresa la declara.",
            **comun,
        )
    return Motivo(
        resultado=NO_SE_SABE,
        texto=(
            f"El pliego exige {', '.join(faltan)} y el perfil no dice que la tenga. Puede tenerla "
            "y no publicarla: hay que comprobarlo antes de descartar."
        ),
        **comun,
    )


def sin_solvencia(requisito, empresa: dict) -> Motivo:
    del empresa
    return Motivo(
        tipo=requisito.tipo,
        resultado=CUMPLE,
        texto=f"El pliego no exige solvencia económica: {requisito.exigencia}",
        cita=requisito.cita,
        pagina=requisito.pagina,
    )


def a_mano(mensaje: str):
    """Un requisito que el radar no puede resolver, con el motivo escrito para la persona."""

    def regla(requisito, empresa: dict) -> Motivo:
        del empresa
        return Motivo(
            tipo=requisito.tipo,
            resultado=NO_SE_SABE,
            texto=f"{mensaje}: {requisito.exigencia}",
            cita=requisito.cita,
            pagina=requisito.pagina,
        )

    return regla


REGLAS = {
    "volumen_negocios": volumen,
    "certificaciones": certificacion,
    "no_se_exige": sin_solvencia,
    "trabajos_similares": a_mano(
        "Hay que comprobar a mano los trabajos similares; el radar no mira los contratos que la "
        "empresa ganó, porque son la verdad con la que se le mide"
    ),
    "clasificacion": a_mano("Hay que comprobar la clasificación empresarial en el registro oficial"),
    "habilitacion": a_mano("Hay que comprobar la habilitación exigida"),
    "adscripcion": a_mano("Hay que comprobar los medios que hay que adscribir al contrato"),
    "remite": a_mano("El pliego remite a otro documento, que hay que abrir"),
}


def evaluar(requisitos: list, empresa: dict) -> Decision:
    """Apta, no apta o revisar, con un motivo citado por requisito."""
    if not requisitos:
        return Decision(
            veredicto=REVISAR,
            motivos=[
                Motivo(
                    tipo="ninguno",
                    resultado=NO_SE_SABE,
                    texto=(
                        "No se ha podido leer ningún requisito del pliego con su cita, así que no "
                        "se decide nada: hay que mirarlo a mano."
                    ),
                )
            ],
        )

    motivos = [REGLAS[r.tipo](r, empresa) for r in requisitos if r.tipo in REGLAS]
    if any(m.resultado == NO_CUMPLE for m in motivos):
        return Decision(veredicto=NO_APTA, motivos=motivos)
    if motivos and all(m.resultado == CUMPLE for m in motivos):
        return Decision(veredicto=APTA, motivos=motivos)
    return Decision(veredicto=REVISAR, motivos=motivos)
