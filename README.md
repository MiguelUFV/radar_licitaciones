# Radar de licitaciones

Un agente que lee las licitaciones públicas nuevas de la Plataforma de Contratación del Sector
Público, abre el pliego de las que encajan con una empresa y le dice a cuáles puede presentarse,
con la cita literal y la página que lo justifican.

**La tesis del proyecto era que esto encontraría contratos que un filtro por código CPV pierde.
Se midió, y no es verdad.** Lo que sigue explica qué se construyó, qué se midió y por qué se
publica igual.

---

## El resultado, primero

Medido sobre **85.769 expedientes** del primer semestre de 2025 y los **52 contratos** que cinco
empresas ganaron de verdad en ese periodo:

| Comparación | Agente | Rival | Diferencia | IC 95 % | Veredicto |
|---|---|---|---|---|---|
| frente a un filtro por CPV 72/48 | 69,2 % | 82,7 % | −13,5 puntos | [−32,7, +5,8] | no concluyente |
| frente a un filtro derivado del perfil | 69,2 % | 88,5 % | **−19,2 puntos** | [−32,7, −7,7] | **refutada** |

De los contratos que cada empresa ganó, el agente los encuentra menos veces que un filtro por
código de actividad. El criterio para declarar la tesis sostenida estaba escrito y commiteado
**antes** de medir (`docs/PLAN_MEDICION.md`), así que el resultado se publica tal cual salió.

**La causa está medida, no supuesta.** Los 16 contratos que el agente descartó son, los 16,
productos o servicios que el perfil de la empresa no nombraba. Empresa G es partner de Autodesk
según su web, y ganó seis contratos de licencias de Adobe y cuatro de PRESTO: es una distribuidora
que vende lo que le piden. El agente razonó bien sobre una descripción incompleta. **El techo de
este sistema es el perfil, no el modelo.**

Cómo salió cada cifra: [`docs/informes/fase5_resultados.md`](docs/informes/fase5_resultados.md)
(lo genera un comando, no se edita a mano) y la lectura de esas cifras, escrita por una persona,
en [`docs/informes/fase5_diagnostico.md`](docs/informes/fase5_diagnostico.md).

## Lo que sí funciona

No todo el sistema falla. La parte que falla es el filtro de entrada; la que lee el pliego
funciona, y esas cifras no dependen del error de arriba:

| | Medido |
|---|---|
| Citas que aparecen literales en la página que dijo el modelo | **100 %** (62 de 62) |
| Páginas leídas de un pliego | **4,7** de 51,5 |
| Coste de todo el proyecto, 290 llamadas | **2,23 €** (2,56 $) |

El modelo no decide nada: extrae requisitos con su cita y su página, **Python comprueba que esa
cita aparece en esa página** antes de usarla, y una cita que no aparece se descarta. La decisión
final (apta / no apta / revisar) la toman reglas en Python, versionadas en fichero.

## Cómo funciona

```
feed/zip de PLACSP → capa raw (fichero + sha256) → staging → núcleo → agente → evaluación

                     triaje → documento → localizar → extraer → decidir → ficha
```

- **Una sola puerta a internet** (`radar/red.py`), solo a dominios de PLACSP, comprobando el
  dominio en cada redirección.
- **La capa raw es inmutable:** cada fichero se guarda por su sha256 y no se sobrescribe nunca.
  Toda fila de la base se puede remontar hasta el fichero del que salió.
- **Una sola puerta al modelo** (`radar/llm.py`), que apunta tokens, coste y presupuesto, y
  comprueba el tope **antes** de llamar contando los tokens de entrada (que es gratis).
- **Qué páginas del pliego se leen no lo decide un modelo:** se puntúan las páginas y se lee desde
  el ancla con un tope. Ese nodo es el que fija el coste.

## Cómo se midió

Lo que hace que el resultado valga algo no es el agente, es el orden de los commits:

1. **Antes de cargar un dato**, se congeló quién entra en el estudio (`docs/REGLA_SELECCION.md`).
2. **Antes de tener perfiles**, se congeló cómo se construye el rival (`docs/BASELINE.md`).
3. **Antes de mirar un contrato de las empresas de test**, se congelaron la muestra, las métricas
   y el criterio de decisión (`docs/PLAN_MEDICION.md`).
4. Los perfiles tienen un candado: el programa se para si el texto no coincide con su sha256.

Ninguno de esos documentos se edita. Si hay que cambiar uno, se añade una entrada a su apartado
**Cambios** con fecha y motivo, y se vuelve a medir lo que dependa de él. Las entradas que hay
están ahí para leerse.

Toda cifra publicada sale de `radar/evaluacion/`, es reproducible con un comando y queda en la
tabla `eval_resultados` con su `run_id` y el commit de git con el que se calculó.

**Un ejemplo de que esto sirve.** El 29-09-2026 un candado avisó de que el universo del estudio
no cuadraba: los expedientes publicados por primera vez en 2024 y actualizados en 2025 estaban
entrando como si fueran nuevos. Eran 34.887 de 120.656, casi uno de cada tres. Al corregirlo, el
recall del agente bajó de 74,0 % a 69,2 % y el de los dos rivales no se movió medio punto: **el
error favorecía a lo que este proyecto defendía.** No lo encontró ninguna revisión, lo encontró
un candado escrito unas horas antes para otra cosa. La historia completa, en
[`docs/HALLAZGO_UNIVERSO.md`](docs/HALLAZGO_UNIVERSO.md).

## Límites

Están todos en [`docs/SPEC.md`](docs/SPEC.md) §9. Los que más condicionan el resultado:

- **El perfil es el techo.** El radar sabe de la empresa lo que dice su perfil. Si el perfil está
  mal, la decisión también. Es el límite que decide el resultado de este estudio.
- **Los perfiles los escribió el modelo, no una persona.** Salen de fuentes públicas y sin mirar
  ni un contrato, pero quedan más ordenados que el perfil que escribiría un cliente real, y eso
  **favorece al radar**. Es el sesgo más importante del estudio.
- **Solo se lee el pliego administrativo (PCAP).** El pliego técnico y los anexos sueltos no se
  descargan. Si la cláusula de solvencia remite a un anexo que va en otro fichero, la ficha sale
  como «revisar» diciendo a qué anexo hay que ir.
- **Un pliego escaneado no se lee.** La rama que manda esas páginas al modelo como imagen no está
  construida. El expediente sale como «revisar» diciendo que es una imagen.
- **Una casilla marcada no se lee.** Muchos pliegos son formularios y el texto extraído no conserva
  qué casilla está marcada. Lo que sí está garantizado es que no se inventa su valor.
- **Solo PLACSP.** Varias comunidades autónomas publican en su propia plataforma y esas
  licitaciones no se ven.
- **Sesgo de selección a favor del rival:** las empresas de test se eligieron por haber ganado
  contratos de informática, lo que favorece al filtro por CPV.
- **Falta medir la precisión (M6):** nadie ha comprobado si las listas que entregan los rivales
  sirven. El filtro derivado del perfil entrega 227 licitaciones al día para una empresa, y un
  humano no las mira. La comparación es de aciertos, y el volumen del rival no lo paga nadie.
- **Esto no es un producto.** Escucha solo en el ordenador donde corre. No hay alojamiento, ni
  autenticación, ni política de datos.

## Qué haría falta para que funcionara

Está escrito en el diagnóstico, y **no se ha hecho a propósito**: ajustar el agente después de ver
el resultado de las empresas de test convierte el test en desarrollo, y entonces no queda nada con
lo que medir.

1. **Perfiles que digan lo que la empresa vende de verdad**, no solo lo que destaca en su web.
   Obliga a volver a congelar los perfiles y a medirlo todo otra vez.
2. **Un triaje que dude más:** `no` solo cuando el objeto sea de otro sector, y `duda` cuando sea
   del sector pero de otra marca. Cambiaría justo los 16 casos perdidos.

Ninguna de las dos se puede aplicar y volver a publicar sobre estas cinco empresas: haría falta un
estudio nuevo con empresas nuevas.

## Datos personales

Un adjudicatario que sea persona física se guarda seudonimizado y sin nombre. La restricción está
en la base de datos, no solo en el código. Las empresas del estudio aparecen siempre como «Empresa
A» a «Empresa G»; sus nombres, sus NIF y sus perfiles se quedan fuera del repositorio.

## Instalación

Python 3.12 con [uv](https://docs.astral.sh/uv/), Postgres y n8n en Docker. Los pasos, las cuentas
y las claves están en [`docs/ENTORNO.md`](docs/ENTORNO.md).

```bash
docker compose up -d
uv run python -m radar.diagnostico   # comprueba .env, TLS de PLACSP, Postgres, n8n
uv run python -m radar.estado        # qué hay cargado y qué necesita atención
uv run pytest
```

Los datos no se distribuyen: `data/` está fuera de git y se reconstruye desde la fuente.

## Documentación

| Documento | Qué hay dentro |
|---|---|
| [`docs/SPEC.md`](docs/SPEC.md) | Tesis, alcance, métricas, criterios de éxito y límites (§9) |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Las ocho fases y la puerta de salida de cada una |
| [`docs/DECISIONES.md`](docs/DECISIONES.md) | Cada decisión técnica y por qué, incluido lo que se descartó |
| [`docs/DATOS.md`](docs/DATOS.md) | Trazabilidad del dato de extremo a extremo |
| [`docs/informes/`](docs/informes/) | Un informe por fase, con la evidencia de su puerta de salida |

Y el proyecto entero explicado para quien no lo ha visto nunca, en PDF y en Word:
`docs/dossier_radar_de_licitaciones.pdf` y `.docx`. Los dos los genera el mismo comando, de una
sola lectura de la base, para que no puedan decir cosas distintas:

```bash
uv run --with reportlab --with python-docx python docs/dossier.py
```

## Licencia y fuente

Código bajo licencia MIT (ver [`LICENSE`](LICENSE)). Los datos son de la Plataforma de
Contratación del Sector Público (Ministerio de Hacienda), reutilizados conforme a la Ley 37/2007.
Esta reutilización no es oficial y el organismo que publica los datos no avala este proyecto.
