# Fase 5 — Resultados

**Este fichero lo genera un comando. No se edita a mano:**

```bash
uv run python -m radar.evaluacion --informe
```

Regenerado el 28-09-2026 desde la tabla `eval_resultados`, sin
llamar a la API. El procedimiento estaba congelado antes de medir en
`docs/PLAN_MEDICION.md`; los criterios, en `docs/SPEC.md` §6.

Commits con los que se calcularon estas cifras: 8bfac44, 9961988, a8e6905, c32cd1a, efc752a.

## La tesis

> **Refutada.**

La tesis se sostiene solo si la diferencia de recall es positiva **y** su intervalo de
confianza al 95 % excluye el 0. Una diferencia positiva con un intervalo que cruza el 0 es
«no concluyente», y se publica como tal.

| Comparación | Agente | Rival | Diferencia | IC 95 % | n | Veredicto |
|---|---|---|---|---|---|---|
| frente a baseline a | 74.0 % | 81.8 % | -7.8 % | [-23.4 %, 7.8 %] | 77 | **NO CONCLUYENTE** |
| frente a baseline b | 74.0 % | 88.3 % | -14.3 % | [-26.0 %, -3.9 %] | 77 | **REFUTADA** |

## M1 — recall: de los contratos que la empresa ganó, cuántos estaban en la lista

| Empresa | Contratos | Baseline A | Baseline B | **Agente** |
|---|---|---|---|---|
| Empresa C | 16 | 62.5 % | 56.2 % | **50.0 %** |
| Empresa D | 11 | 81.8 % | 90.9 % | **100.0 %** |
| Empresa E | 13 | 69.2 % | 100.0 % | **92.3 %** |
| Empresa F | 9 | 77.8 % | 88.9 % | **100.0 %** |
| Empresa G | 28 | 100.0 % | 100.0 % | **60.7 %** |

El recall se mide sobre **todos** los contratos ganados del periodo, no sobre una muestra.

## M2 — volumen: cuántas licitaciones al día deja pasar cada uno

| Empresa | Baseline A | Baseline B | **Agente** | Muestra |
|---|---|---|---|---|
| Empresa C | 30,3 | 68,2 | **7,6** | 88 no ganados |
| Empresa D | 30,3 | 166,7 | **53,0** | 88 no ganados |
| Empresa E | 30,3 | 121,2 | **68,2** | 88 no ganados |
| Empresa F | 30,3 | 272,7 | **7,6** | 88 no ganados |
| Empresa G | 30,3 | 287,9 | **53,0** | 88 no ganados |

El volumen del agente es una **estimación** a partir de la muestra de no ganados
(`docs/PLAN_MEDICION.md` §3).

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
| Empresa C | Herramienta de análisis de redes sociales | Herramienta de análisis de redes sociales: software de análisis, fuera del ámbito de equipamiento y sistemas audiovisuales de broa |
| Empresa C | IA aplicada al metadatado de contenidos del Archivo RTVE | IA aplicada a metadatado de contenidos: desarrollo de software especializado, no suministro de equipamiento ni integración de sist |
| Empresa C | Servicios CDN | Servicios CDN: infraestructura de telecomunicaciones, no integración ni distribución de equipamiento audiovisual |
| Empresa E | Mantenimiento y soporte de los productos del software AuditPlus Professional | Mantenimiento de software AuditPlus: es soporte de una aplicación específica de terceros, no de soluciones propias de la empresa. |
| Empresa G | Licenciamiento de productos Adobe | Licenciamiento de productos Adobe. La empresa es partner de Autodesk, no de Adobe; no hay indicios de que distribuya o implante so |
| Empresa G | L’objecte d’aquesta licitació es el subministrament de la renovació del suport i serveis d | Soporte y actualización de licencias PRESTO; no es de sus áreas de especialización (CAD, BIM, GIS, manufacturing). |
| Empresa G | Renovación y actualización de versiones de software técnico de PRESTO | Renovación de software técnico PRESTO. Mismo motivo: PRESTO es de presupuestación y gestión de proyectos, fuera del perímetro de s |
| Empresa G | Servicio de soporte y actualizaciones de software PRESTO. | Soporte y actualizaciones de software PRESTO; no es un producto que la empresa distribuya o soporte. |

Se muestran 4 por empresa. Hay Empresa C: 4 más, Empresa G: 7 más.

Contratos perdidos por empresa: Empresa C 8, Empresa E 1, Empresa G 11.

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
