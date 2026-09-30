# Experimento del triaje — cómo se elige el modelo (D06)

**Escrito y congelado el 27-09-2026, antes de hacer una sola llamada de triaje.** Igual que con la
regla de selección y con el baseline: si el criterio se escribiera después de ver los números, el
resultado no valdría nada. El orden de los commits lo demuestra.

---

## 1. Qué se decide aquí

`docs/DECISIONES.md` D06 dejó el modelo del triaje sin decidir, a propósito: «se decide con el
experimento de la Fase 4, `claude-opus-5` con esfuerzo bajo frente a `claude-haiku-4-5`, sobre las
empresas de desarrollo, por M1 y coste. También se prueba agrupar unas 20 licitaciones por llamada».

Esto es ese experimento. Decide dos cosas:

1. **Qué modelo hace el triaje** (el filtro barato que mira objeto y CPV y decide si merece la pena
   abrir el pliego).
2. **Cuántas licitaciones van en cada llamada**, una o veinte.

## 2. Las tres variantes

| Variante | Modelo | Esfuerzo | Licitaciones por llamada |
|---|---|---|---|
| `haiku_lote20` | `claude-haiku-4-5` | no admite esfuerzo | 20 |
| `haiku_individual` | `claude-haiku-4-5` | no admite esfuerzo | 1 |
| `opus_lote20` | `claude-opus-5` | `low` | 20 |

Falta a propósito `opus_individual`: si agrupar sale bien con Haiku, la comparación que importa es
Haiku contra Opus con el mismo agrupamiento, y una cuarta variante con Opus multiplicaría el coste
del experimento sin decidir nada nuevo.

Las tres usan **el mismo prompt** (`radar/prompts/triaje_v1.md`) y ven **lo mismo**: el perfil
congelado de la empresa y, de cada licitación, solo lo que estaba publicado en el feed mientras el
plazo seguía abierto (objeto, órgano, CPV y tipo de contrato). Nunca el adjudicatario, y tampoco
el importe: el triaje juzga la materia del contrato, no si le encaja el tamaño.

## 3. La muestra

- **Empresas:** solo las **dos de desarrollo** (Empresa A y Empresa B). Las cinco de test no se
  tocan hasta la Fase 5 (`docs/REGLA_SELECCION.md` §4).
- **Periodo:** licitaciones publicadas entre `2025-01-01` y `2025-06-30`, con adjudicaciones
  registradas hasta `2026-08-31`. El mismo universo con el que se midió el baseline, para que las
  cifras sean comparables.
- **Versión del expediente:** la **más antigua** de cada `entry_id`, que es la que estaba publicada
  mientras se podía presentar una oferta (D30).

Muestreo **estratificado**, porque los contratos ganados son 24 de 120.656 (0,02 %) y una muestra al
azar no traería ninguno:

| Estrato | Qué es | Tamaño |
|---|---|---|
| Ganados | Todos los expedientes que esa empresa ganó de verdad en el periodo | 12 por empresa (24 en total) |
| No ganados | Muestra al azar del resto del universo | 88 por empresa |

100 licitaciones por empresa, 200 en total por variante, 600 triajes en el experimento completo. La
muestra de no ganados se saca con `ORDER BY md5(entry_id || '20260927')`: sale la misma siempre, sin
depender de que nadie guarde un fichero.

**Por qué 88 y no más:** con 138 el coste máximo del experimento salía a 3,72 € y el tope de gasto
del proyecto es de 2,00 € al día (`PRESUPUESTO_DIARIO_EUR`). Se baja el tamaño de la muestra antes de
hacer ninguna llamada, no después de ver ningún resultado. Los 12 contratos ganados por empresa se
mantienen **todos**: es de ellos de donde sale el recall, que es lo que decide. Lo que pierde
precisión es la tasa de paso en no ganados: con 88 casos, su margen es de unos ±10 puntos cuando
ronda el 50 % y de ±6 cuando ronda el 10 %. Para la regla de decisión («que el volumen no sea más
del doble») llega.

**Semilla:** `20260927`.

## 4. Lo que se mide

De cada variante y cada empresa:

- **Recall del triaje (M1):** de los contratos que la empresa ganó, cuántos deja pasar el triaje.
  Pasan los `si` y los `duda`: los dos siguen adelante y se les abre el pliego. Un `no` es el final
  del camino, y si ese contrato lo ganó de verdad, es un fallo demostrado.
- **Tasa de paso en no ganados:** qué porcentaje del resto del universo deja pasar. No es un error:
  que una empresa no ganara un contrato no significa que no debiera presentarse (a lo mejor se
  presentó y lo perdió). Sirve para estimar el volumen, y la precisión se mide aparte con una
  persona (M6, Fase 5).
- **Volumen estimado (M2):** tasa de paso en no ganados × 667 licitaciones publicadas al día en el
  periodo. Se compara con las 50/día del Baseline A y las 215/día del Baseline B.
- **Coste (M8):** euros por 100 licitaciones triadas, de la tabla `llm_llamadas`, con tokens reales.
- **Respuestas inservibles:** licitaciones para las que el modelo no devolvió una decisión válida.
  Cuentan como `revisar` y se publican: un modelo que se deja licitaciones por el camino es peor
  modelo, y eso tiene que verse.

## 5. La regla de decisión, escrita antes de ver los números

Con 12 contratos ganados por empresa, **un contrato son 8,3 puntos de recall**. Cualquier diferencia
menor que eso no es una diferencia: es un contrato. De ahí sale el umbral.

1. **Se elige `haiku_lote20`** si su recall está a **menos de 8 puntos** del de `opus_lote20` y su
   volumen estimado no es más del doble.
2. Si `opus_lote20` gana **8 puntos o más** de recall, se elige Opus, siempre que el coste estimado
   del día completo (667 licitaciones × 7 empresas) se quede por debajo de **0,50 €/día**. Si lo
   pasa, se anota el resultado y se busca una tercera vía (prefiltro en Python antes del modelo)
   antes de decidir.
3. **Agrupar o no:** se agrupan 20 por llamada salvo que `haiku_individual` saque **8 puntos o más**
   de recall que `haiku_lote20`. Agrupar es entre 5 y 8 veces más barato; solo se renuncia a eso si
   se paga con recall.
4. **Empate:** si dos variantes quedan a menos de 8 puntos, gana la más barata. Siempre.
5. Si alguna variante deja **más del 2 %** de las licitaciones sin decisión válida, queda descartada
   sea cual sea su recall: el radar no puede perder licitaciones por el camino.

El resultado, sea el que sea, se escribe en `docs/DECISIONES.md` D06 y en el informe de la Fase 4,
con las cifras y el `run_id` con el que se calcularon.

## 6. Límites de este experimento

Se escriben aquí antes de medir, para no tener la tentación de callárselos después:

1. **n = 12 contratos por empresa.** Es lo que da la regla de selección. Un contrato mueve el recall
   8,3 puntos, así que esto decide entre modelos, no publica una cifra de recall del radar. La cifra
   que se publica sale de la Fase 5, con las cinco empresas de test.
2. **Los ganados están sobrerrepresentados:** son el 8 % de la muestra y el 0,02 % de la realidad.
   El modelo ve un caudal más rico de lo normal y no sabe la proporción real. Afecta igual a las
   tres variantes, así que la comparación se sostiene, pero el recall medido aquí no se puede
   trasladar tal cual a producción.
3. **Los «no ganados» no son «no relevantes».** Por eso su tasa de paso se usa como volumen y nunca
   como error.
4. **Una sola pasada.** Estos modelos no admiten `temperature` cuando razonan, así que no se puede
   fijar a 0 y dos pasadas pueden no coincidir. No se mide esa variación: haría falta repetir el
   experimento varias veces y el presupuesto del proyecto no lo justifica para elegir un modelo.
5. **El prompt es el mismo para los dos modelos.** Un prompt ajustado a cada uno podría cambiar el
   resultado. Se elige el modelo con el prompt v1 y se anota; si después se ajusta el prompt, se
   vuelve a comparar.

## 7. Coste del propio experimento

Se estima **antes** de gastar, contando los tokens de entrada con `count_tokens` (que es gratis) y
suponiendo que la salida llega al máximo. El comando no gasta nada si no se le pasa `--gastar`:

```bash
uv run python -m radar.evaluacion.triaje              # solo estima y lo dice
uv run python -m radar.evaluacion.triaje --gastar     # llama al modelo de verdad
```

El tope de `PRESUPUESTO_DIARIO_EUR` (2,00 €) se sigue comprobando antes de cada llamada. Si se
alcanza, el experimento se para con un mensaje en castellano y se puede reanudar: cada triaje queda
guardado con su `(licitación, empresa, modelo, agrupamiento, versión del prompt)` y no se repite.

---

## Cambios

_Ninguno. Si algún día hay uno, va aquí con su fecha y su motivo, y se vuelve a medir._

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
