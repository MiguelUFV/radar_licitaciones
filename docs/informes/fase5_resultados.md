# Fase 5 — Resultados

**Este fichero lo genera un comando. No se edita a mano:**

```bash
uv run python -m radar.evaluacion --informe
```

Regenerado el 29-09-2026 desde la tabla `eval_resultados`, sin
llamar a la API. El procedimiento estaba congelado antes de medir en
`docs/PLAN_MEDICION.md`; los criterios, en `docs/SPEC.md` §6.

Commits con los que se calcularon estas cifras: 8353420, 8bfac44, a8e6905, c32cd1a.

## La tesis

> **Refutada.**

La tesis se sostiene solo si la diferencia de recall es positiva **y** su intervalo de
confianza al 95 % excluye el 0. Una diferencia positiva con un intervalo que cruza el 0 es
«no concluyente», y se publica como tal.

| Comparación | Agente | Rival | Diferencia | IC 95 % | n | Veredicto |
|---|---|---|---|---|---|---|
| frente a baseline a | 69.2 % | 82.7 % | -13.5 % | [-32.7 %, 5.8 %] | 52 | **NO CONCLUYENTE** |
| frente a baseline b | 69.2 % | 88.5 % | -19.2 % | [-32.7 %, -7.7 %] | 52 | **REFUTADA** |

## M1 — recall: de los contratos que la empresa ganó, cuántos estaban en la lista

| Empresa | Contratos | Baseline A | Baseline B | **Agente** |
|---|---|---|---|---|
| Empresa C | 8 | 75.0 % | 37.5 % | **37.5 %** |
| Empresa D | 7 | 71.4 % | 85.7 % | **100.0 %** |
| Empresa E | 11 | 63.6 % | 100.0 % | **90.9 %** |
| Empresa F | 6 | 83.3 % | 100.0 % | **100.0 %** |
| Empresa G | 20 | 100.0 % | 100.0 % | **50.0 %** |

El recall se mide sobre **todos** los contratos ganados del periodo, no sobre una muestra.

## M2 — volumen: cuántas licitaciones al día deja pasar cada uno

| Empresa | Baseline A | Baseline B | **Agente** | Muestra |
|---|---|---|---|---|
| Empresa C | 39,5 | 74,0 | **29,6** | 96 no ganados |
| Empresa D | 41,2 | 133,9 | **56,7** | 92 no ganados |
| Empresa E | 31,6 | 94,8 | **57,9** | 90 no ganados |
| Empresa F | 31,2 | 197,9 | **20,8** | 91 no ganados |
| Empresa G | 59,2 | 227,1 | **69,1** | 96 no ganados |

El volumen del agente es una **estimación** a partir de la muestra de no ganados
(`docs/PLAN_MEDICION.md` §3).

## M9 y M10 — lo que cuesta cada acierto

**Estas dos métricas se definieron el 29-09-2026, después de conocer M1**
(`docs/METRICA_EFICIENCIA.md`). No sustituyen a M1, que sigue refutada: van al lado.

### M9 — licitaciones que hay que revisar por cada contrato encontrado

| Empresa | **Agente** | Baseline A | Baseline B |
|---|---|---|---|
| Empresa C | **1787** | 1191 | 4467 |
| Empresa D | **1465** | 1492 | 4040 |
| Empresa E | **1048** | 817 | 1559 |
| Empresa F | **628** | 1131 | 5969 |
| Empresa G | **1251** | 536 | 2055 |

Menos es mejor. No supone nada: es el volumen medido por el periodo, dividido entre los
contratos que cada método encuentra.

### M10 — recall si todos entregaran el mismo volumen que el agente

| Empresa | **Agente** | Baseline A | Baseline B |
|---|---|---|---|
| Empresa C | **37.5 %** | 56.2 % | 15.0 % |
| Empresa D | **100.0 %** | 71.4 % | 36.3 % |
| Empresa E | **90.9 %** | 63.6 % | 61.1 % |
| Empresa F | **100.0 %** | 55.6 % | 10.5 % |
| Empresa G | **50.0 %** | 100.0 % | 30.4 % |

**Con una suposición fuerte:** un filtro de CPV no ordena su lista, así que se supone que
quien solo puede mirar una parte la mira **al azar** y que los aciertos están repartidos de
forma uniforme. Si se concentraran en alguna parte de la lista, M10 infravaloraría al rival.

Ninguna de las dos lleva intervalo de confianza, y no es un olvido: son cocientes de
cantidades estimadas y un intervalo daría una precisión que no existe
(`docs/METRICA_EFICIENCIA.md` §6).

## M5 — citas verificadas

**100.0 %** de las 62 extracciones tienen una cita que aparece
literal en la página que dijo el modelo. Rechazadas: 0.
Pliegos leídos: 17. El criterio de fiabilidad es ≥ 98 %.

## M7 — trabajo evitado

Se leen **10,87 veces menos páginas**:
4,7 páginas señaladas por el radar frente a
51,5 que tiene el pliego, sobre 15 pliegos.
Y un documento abierto en lugar de 4,3
que trae el expediente.

No hay cifra de minutos: había que cronometrarla antes de construir el agente y no se
hizo (`docs/PLAN_MEDICION.md` §7).

## M8 — coste

- `triaje_haiku_individual`: **0,1845 €** por 100 licitaciones triadas (200 triadas en 200 llamadas, 0,3689 € en total).
- `triaje_haiku_lote20`: **0,0403 €** por 100 licitaciones triadas (200 triadas en 10 llamadas, 0,0806 € en total).
- `triaje_opus_lote20`: **0,1888 €** por 100 licitaciones triadas (200 triadas en 10 llamadas, 0,3775 € en total).

## Dónde falla: los contratos que la empresa ganó y el agente descartó

| Empresa | Contrato que ganó y el agente descartó | Motivo que dio el agente |
|---|---|---|
| Empresa C | Herramienta de análisis de competidores en redes sociales | Herramienta de análisis de competidores en redes sociales: software de análisis, fuera del ámbito audiovisual de broadcast |
| Empresa C | IA aplicada al metadatado de contenidos del Archivo RTVE | IA aplicada a metadatado de contenidos: desarrollo de software especializado, no suministro de equipamiento ni integración de sist |
| Empresa C | Servicios CDN | Servicios CDN: infraestructura de telecomunicaciones, no integración ni distribución de equipamiento audiovisual |
| Empresa C | Servicios de protección de origen | Servicios de protección de origen (DRM): software de seguridad de contenidos, no integración ni suministro de sistemas audiovisual |
| Empresa E | Mantenimiento y soporte de los productos del software AuditPlus Professional | Mantenimiento de software AuditPlus: es soporte de una aplicación específica de terceros, no de soluciones propias de la empresa. |
| Empresa G | Licenciamiento de productos Adobe | Licenciamiento de productos Adobe. La empresa es partner de Autodesk, no de Adobe; no hay indicios de que distribuya o implante so |
| Empresa G | L’objecte d’aquesta licitació es el subministrament de la renovació del suport i serveis d | Soporte y actualización de licencias PRESTO; no es de sus áreas de especialización (CAD, BIM, GIS, manufacturing). |
| Empresa G | Renovación y actualización de versiones de software técnico de PRESTO | Renovación de software técnico PRESTO. Mismo motivo: PRESTO es de presupuestación y gestión de proyectos, fuera del perímetro de s |
| Empresa G | Servicio de soporte y actualizaciones de software PRESTO. | Soporte y actualizaciones de software PRESTO; no es un producto que la empresa distribuya o soporte. |

Se muestran 4 por empresa. Hay Empresa C: 1 más, Empresa G: 6 más.

Contratos perdidos por empresa: Empresa C 5, Empresa E 1, Empresa G 10.

## Lo que falta por medir

- M3 (exclusiones erróneas por solvencia)
- M4 (exactitud de la extracción)
- M6 (precisión, etiquetado a ciegas)

---

Cada cifra de este informe sale de una fila de `eval_resultados` con su `run_id`, su
comando y su commit. Para verlas todas:

```sql
SELECT metrica, variante, alias, valor, ic_inferior, ic_superior, n, git_commit
FROM eval_resultados ORDER BY calculada_en DESC;
```
