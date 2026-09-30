# Plan de medición de la Fase 5 — el "después"

**Escrito y congelado el 27-09-2026, antes de mirar ni un contrato de las cinco empresas de test.**
El agente ya está congelado: prompts `triaje_v1` y `extraccion_v1`, reglas `v1`, modelo de triaje
decidido en D06. Nada de eso se toca a partir de aquí. Si algo hubiera que cambiar, se anota en
**Cambios** y se vuelve a medir todo.

Es el tercer documento de este tipo, después de `docs/REGLA_SELECCION.md` y `docs/BASELINE.md`. El
orden de los commits demuestra que el criterio se escribió antes de conocer el resultado.

---

## 1. Qué se decide

`docs/SPEC.md` §6 ya fijó el criterio, y aquí no se cambia, se concreta:

- **Tesis sostenida:** la diferencia de M1 (agente − filtro CPV) es positiva y su intervalo de
  confianza al 95 % por bootstrap pareado excluye el 0.
- **Tesis refutada:** la diferencia es negativa y su intervalo excluye el 0.
- **No concluyente:** cualquier otro caso. Se publica igual.

La tesis se juzga contra **los dos** baselines (A, el filtro CPV 72/48; B, el derivado del perfil). Si
gana a uno y no al otro, se dice así.

## 2. Sobre quién se mide

- **Las cinco empresas de test** (C, D, E, F y G). Las dos de desarrollo ya han servido para ajustar
  y **no** entran en la cifra que se publica; se publican aparte, marcadas como desarrollo.
- **Periodo:** licitaciones publicadas del `2025-01-01` al `2025-06-30`, adjudicaciones registradas
  hasta el `2026-08-31`. El mismo universo con el que se midió el baseline en la Fase 3: 120.656
  expedientes en 181 días con publicaciones.
- **Versión del expediente:** la más antigua de cada `entry_id`, que es la que estaba publicada
  mientras se podía presentar una oferta (D30).

## 3. Por qué una muestra y no el universo

Triar los 120.656 expedientes para las cinco empresas serían 603.280 llamadas de triaje: **243 €** al
coste medido en la Fase 4. El tope del proyecto son 2 €/día y 25 €/mes. No es una decisión de
comodidad: es que la medición completa no cabe, y forzarla sería gastar el presupuesto entero de
varios meses en una cifra que una muestra estratificada da con su intervalo.

Muestreo **estratificado**, el mismo de `docs/EXPERIMENTO_TRIAJE.md` §3:

| Estrato | Qué es | Tamaño |
|---|---|---|
| Ganados | **Todos** los expedientes que la empresa ganó de verdad en el periodo | 77 en total (C 16, D 11, E 13, F 9, G 28) |
| No ganados | Muestra al azar del resto del universo, `ORDER BY md5(entry_id \|\| '20260927')` | 88 por empresa |

**Semilla:** `20260927`, la misma del experimento del triaje. Los 88 no ganados son los mismos para
todas las empresas (solo se le quitan a cada una los que ella ganó), así que las cinco se miden sobre
las mismas licitaciones: bien para comparar, y hay que decir que sus estimaciones de volumen están
correlacionadas.

**Consecuencia para cada métrica:**

- **M1 (recall) se mide sobre el estrato completo de ganados**, sin muestrear: los 77 contratos. No es
  una estimación, es el recall exacto sobre todos los contratos que esas cinco empresas ganaron en el
  periodo.
- **M2 (volumen) es una estimación**: tasa de paso en los 88 no ganados × 666,6 licitaciones
  publicadas al día. Con 88 casos el margen es de unos ±10 puntos cuando la tasa ronda el 50 % y ±6
  cuando ronda el 10 %.

## 4. Las métricas, y en qué orden se gastan

El orden importa porque el presupuesto puede cortar una tanda: **primero lo que decide la tesis**.

| Orden | Métrica | Qué cuesta | Sobre qué |
|---|---|---|---|
| 1 | **M1** recall del agente | 77 triajes ≈ **0,04 €** | Los 77 contratos ganados |
| 2 | **M2** volumen | 440 triajes ≈ **0,18 €** | Los 88 no ganados × 5 empresas |
| 3 | **M5** citas verificadas | incluido en el 4 | Las extracciones que salgan |
| 4 | **M3** exclusiones erróneas | ≈ 77 pliegos × 0,070 € ≈ **5,4 €** | Los pliegos de los contratos ganados |
| 5 | **M7** trabajo evitado | **0 €** | Los pliegos ya descargados |
| 6 | **M8** coste | **0 €** | La tabla `llm_llamadas` |
| 7 | **M4** exactitud de extracción | **0 €** | Importe y plazo del feed frente a lo extraído |
| — | **M6** precisión (a mano) | 0 € y un rato de una persona | Muestra ciega de 40 licitaciones |

**Presupuesto de la Fase 5: 8 €**, fijado aquí y antes de empezar. Si alguna tanda lo pasa, se para y
se dice, no se sube a mitad de camino. El tope diario de `.env` (2 €) sigue mandando: la medición
tarda los días que haga falta y cada tanda es reanudable.

## 5. Cómo se calcula el intervalo de confianza

**Bootstrap pareado por contrato**, 2.000 remuestreos, semilla `20260927`:

1. La unidad es el **contrato ganado**. De cada uno se sabe si lo vio el agente y si lo vio cada
   baseline: tres indicadores 0/1 sobre el mismo contrato. Por eso es pareado; comparar dos medias
   independientes daría un intervalo más ancho de lo que corresponde.
2. Se remuestrean los 77 contratos con reemplazo, se recalcula la diferencia de recall en cada
   remuestreo, y el intervalo es el percentil 2,5 y 97,5 de esas 2.000 diferencias.
3. Se publican los tres números: recall del agente, recall del baseline y la diferencia con su
   intervalo.

Con n = 77 contratos, un contrato son 1,3 puntos de recall. El intervalo va a ser ancho y se dirá.

## 6. Qué cuenta como "lo vio el agente"

Para M1, una licitación **está en la lista corta** si el triaje la marcó `si` o `duda`. Las dos siguen
adelante y se les abre el pliego; un `no` es el final del camino.

La decisión posterior del pliego (apta / no apta / revisar) **no** entra en M1: entra en M3, que mide
justo lo contrario, cuántos contratos ganados se marcaron «no apta», que es un error demostrado
porque la empresa los ganó.

## 7. Lo que no se va a hacer, y por qué se dice antes

- **No se va a triar el universo completo**, por el §3. M2 es una estimación con su margen.
- **No se van a leer los pliegos de los no ganados.** M3 solo necesita los ganados, y leer los otros
  costaría 15 € más sin decidir nada.
- **No se van a ajustar los prompts ni las reglas con lo que salga aquí.** Si el resultado es malo, se
  publica malo. Ajustar después de ver el resultado de test convierte el test en desarrollo, y
  entonces no queda nada con lo que medir.
- **M7b (minutos cronometrados a mano) no se hace**: había que medirlo antes de la Fase 4 y no se
  hizo. El README no dará ninguna cifra de minutos.

## 8. La puerta de salida

`uv run python -m radar.evaluacion --informe` regenera el informe entero desde `eval_resultados`
**sin llamar a la API**. Otra persona con el repositorio y la base restaurada obtiene las mismas
cifras, y cada cifra lleva el commit de git con el que se calculó.

---

## Cambios

_Ninguno. Si algún día hay uno, va aquí con su fecha y su motivo, y se vuelve a medir lo que dependa
de él._

**29-09-2026 · Las cifras de este documento se escribieron con el histórico incompleto.**
El universo del estudio son los expedientes cuya **primera** publicación cae en el periodo, y la
carga histórica empezaba en 2025-01. Un expediente publicado en 2024 y actualizado dentro del
periodo parecía publicado por primera vez dentro del periodo, y entraba. Al completar 2024 esos
expedientes vuelven a su sitio y salen: el universo baja y con él el número de contratos ganados
que entran en la medición.

**No cambia nada de lo que este documento decide** —ni la muestra, ni las métricas, ni el
criterio, ni el orden del gasto—, así que el texto de arriba se queda como estaba. Lo que cambia
son las cifras que ilustran el tamaño del problema, y las nuevas están en los informes de
`docs/informes/`, que se regeneran con un comando. El hallazgo, con su alcance y la decisión que
se tomó, está en `docs/HALLAZGO_UNIVERSO.md` y en `docs/DECISIONES.md` D44.

Se ha vuelto a medir todo lo que dependía del universo, sin volver a llamar al modelo: los
triajes estaban guardados y lo único que cambia es qué expedientes cuentan.

**30-09-2026 · Ya se sabe cuánto bajó.** Completada la carga de 2024, el universo queda en
**85.769** expedientes (eran 120.656: sobraban 34.887) y los contratos ganados de las empresas de
test en **52** (eran 77). La medición rehecha está en `docs/informes/fase5_resultados.md`; el
veredicto no cambia y el margen empeora (D44).
