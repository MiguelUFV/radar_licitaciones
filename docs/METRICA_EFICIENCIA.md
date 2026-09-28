# Métrica de eficiencia: M9 y M10

**Este documento se escribe el 29-09-2026, después de conocer M1.** Eso lo hace más débil como
evidencia que `docs/PLAN_MEDICION.md`, que se congeló antes de mirar un solo contrato de las
empresas de test, y hay que leerlo sabiéndolo. Se escribe entero —definición, fórmula y regla de
decisión— **antes de calcular ningún número**, y el orden de los commits es la prueba.

**No sustituye a M1.** M1 salió refutada: 74,0 % frente al 88,3 % del Baseline B, diferencia de
−14,3 puntos con intervalo [−26,0, −3,9]. Eso está publicado y se queda publicado. Lo que sigue
se publica **al lado**, no en su lugar.

## 1. Por qué existe

`docs/SPEC.md` §7 define M1 como **«recall a igual volumen»**. Se midió el recall, y los
volúmenes no se igualaron: el informe de la Fase 5 lo dice en su apartado 4.2 y publica la tabla
que lo demuestra. Frente al Baseline B, el agente entrega entre 4 y 36 veces menos licitaciones.

Falta, entonces, la mitad de la definición que el propio SPEC daba. Un filtro que no filtra tiene
recall perfecto: entregar las 666 licitaciones que se publican al día encuentra el 100 % de los
contratos y no sirve de nada. La pregunta que M1 dejó sin contestar es **cuánto trabajo cuesta
cada acierto**, y esa pregunta ya estaba en el documento congelado.

## 2. Qué se mide

### M9 — Licitaciones que hay que revisar por cada contrato encontrado

Para cada empresa y cada método (agente, Baseline A, Baseline B):

```
contratos_encontrados = recall (M1) × contratos ganados de esa empresa
M9 = (volumen diario (M2) × días del periodo) / contratos_encontrados
```

Unidad: **licitaciones revisadas por contrato encontrado**. Cuanto más bajo, mejor. Si un método
encuentra cero contratos, M9 no está definida y se escribe «no encuentra ninguno», no infinito.

Los días del periodo son los **181 días con publicaciones** del semestre de estudio
(`docs/informes/fase4_triaje.md` §1), no los días naturales.

### M10 — Recall a igual volumen

El recall que tendría cada rival si solo pudiera entregar tantas licitaciones como el agente:

```
M10(rival) = recall(rival) × min(1, volumen(agente) / volumen(rival))
M10(agente) = recall(agente)
```

**La suposición, declarada:** un filtro de CPV no ordena su lista, así que no hay forma de
recortarla por relevancia. Se supone que quien recibe 288 licitaciones al día y solo puede mirar
53 **mira una muestra al azar**, y que los contratos ganados están repartidos por la lista de
forma uniforme. Es la única suposición defendible sin un ranking, y es una suposición fuerte: si
los aciertos del rival se concentraran en alguna parte de su lista, M10 lo infravaloraría.

Por eso M10 va segunda y M9 primera: **M9 no supone nada**.

## 3. De dónde salen los números

De `eval_resultados`, donde ya están M1 y M2 por empresa y por variante, calculadas en la Fase 5.
**No se llama al modelo ni una vez**: esto es aritmética sobre lo ya medido y pagado. El comando
que lo reproduce quedará escrito en el informe.

Las cinco empresas son las mismas cinco de test, con sus mismos 77 contratos. No se añade ni se
quita ninguna.

## 4. Regla de decisión, escrita antes de mirar

| Si sale… | Se publica |
|---|---|
| M9 del agente **menor** que la de los dos baselines en la mayoría de las empresas (3 de 5 o más) | Que el agente encuentra un contrato revisando menos licitaciones, diciendo en la misma frase que M1 sigue refutada |
| M9 del agente **mayor** o empatada | Que el agente tampoco gana en eficiencia, y que entonces no hay nada que rescatar |
| M10 del agente mayor que la de los dos rivales | Que a igualdad de trabajo humano el agente encuentra más, **con la suposición del reparto uniforme escrita al lado** |
| M10 del agente menor | Que ni recortando la lista del rival gana el agente |

**Sale lo que salga, se publica.** Es la misma regla que ya costó publicar una tesis refutada.

## 5. Lo que esto no demuestra, pase lo que pase

- **No demuestra que la lista del agente sirva.** Para eso está M6 —una persona etiquetando a
  ciegas una mezcla de las dos listas— y **sigue sin medirse**. M9 mide densidad de aciertos
  entre los contratos que la empresa ganó, no si el resto de la lista es razonable.
- **No convierte M1 en otra cosa.** Encontrar menos contratos es encontrar menos contratos.
- **No es una métrica de negocio.** Nadie ha medido cuánto cuesta revisar una licitación ni qué
  margen deja un contrato. «Trabajo» aquí es número de licitaciones, no euros ni horas.
- **El volumen del agente (M2) es una estimación** a partir de la muestra de 88 no ganados por
  empresa (`docs/PLAN_MEDICION.md` §3), así que M9 y M10 heredan esa imprecisión.

## 6. Sin intervalos de confianza, y por qué

M9 y M10 son cocientes de dos cantidades estimadas, una de ellas (el volumen) a partir de una
muestra pequeña. Un intervalo construido sobre eso daría una precisión que no existe. Se publican
como **descriptivas**, con sus cinco valores a la vista y sin agregar en una sola cifra que
esconda la dispersión. Quien quiera comparar, que compare empresa por empresa.

Esto es una diferencia deliberada con M1, que sí lleva intervalo porque su unidad —un contrato,
encontrado o no— es un dato, no una estimación.

## Cambios

_Si algún día hay uno, va aquí con su fecha y su motivo, y se vuelve a calcular._

**29-09-2026 · De qué filas de `eval_resultados` sale M2.** El apartado 3 decía «donde ya están
M1 y M2 por empresa y por variante», y al ir a calcular apareció que hay **dos conjuntos de M2
que no son comparables**: las filas sueltas de `baseline_a` y `baseline_b` se calcularon en la
Fase 3 sobre el universo entero (n = 120.656), y el `detalle` de la fila del agente trae las tres
variantes calculadas sobre la misma base (666,61 licitaciones publicadas al día). Dividir un
recall por un volumen medido con otro denominador no mide nada.

Se usa **el conjunto del `detalle` del agente**, que es también el que publica la tabla M2 del
informe de la Fase 5. No cambia la fórmula ni la regla de decisión; precisa de dónde sale uno de
los dos números. Anotado antes de calcular.
