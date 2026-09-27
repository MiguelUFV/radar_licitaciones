# Fase 4 — El agente que lee el pliego

Medido el 27-09-2026. Las cifras salen de las tablas `lecturas`, `requisitos`, `fichas` y
`llm_llamadas`, y se regeneran sin volver a pagar nada:

```bash
uv run python -m radar.evaluacion.pliegos --solo-medir
```

El experimento que eligió el modelo de triaje está en `docs/informes/fase4_triaje.md`. Este informe
es la otra mitad de la fase: leer el pliego de las candidatas y decidir con lo que dice.

## 1. Qué hace el agente

```
triaje ──► documento ──► localizar ──► extraer ──► decidir ──► ficha
              │              │            │  ▲         │
              │              │            │  └─ anexo ─┘ (un solo salto, D35)
              └──────────────┴────────────┴──────────────► ficha con el motivo escrito
```

Un grafo de LangGraph 1.2 con checkpointer de Postgres, seis nodos y **cuatro ramas que no son
adorno**: sin pliego descargado, sin sección de solvencia, el modelo contestando algo que no se puede
usar, y el salto al anexo al que remite el pliego. Ninguna rama descarta una licitación: todas
terminan en una ficha que dice en castellano qué falta por comprobar.

| Nodo | Qué hace | Modelo |
|---|---|---|
| `documento` | Busca el PCAP descargado del expediente | no |
| `localizar` | Puntúa las páginas, busca el ancla y lee hacia delante, tope 6 (D34) | no |
| `extraer` | Copia los requisitos con **cita literal y página** | Opus 5 |
| *(verificación)* | Busca esa cita en el texto de esa página; si no está, la pide otra vez | no |
| `anexo` | Si el pliego remite a un anexo y no hay ninguna cifra, busca el anexo (D35) | no |
| `decidir` | Apta / no apta / revisar, con `radar/reglas/v1.py` | no |
| `ficha` | Guarda lectura, requisitos (verificados y rechazados) y decisión | no |

El modelo solo entra en `extraer`. Todo lo demás lo decide Python (D09).

## 2. M5, la puerta de salida de la fase

> **M5 = 100,0 % · 62 de 62 extracciones tienen una cita que aparece literal en la página que dijo
> el modelo.** El criterio de la Fase 4 era ≥ 98 %.

| | |
|---|---|
| Pliegos leídos | **15** (de las candidatas del triaje, las dos empresas de desarrollo) |
| Pliegos sin sección de solvencia localizable | 2 |
| Pliegos leídos en los que el modelo no encontró ningún requisito en esas páginas | 2 |
| Requisitos extraídos | 62 |
| Rechazados por la comprobación de la cita | **0** |
| Páginas leídas de media | **4,7 de 51,5** que tiene el pliego (9 %) |
| Llamadas al modelo | 19 (1,3 por pliego: el segundo intento y el salto al anexo) |
| Coste | **1,05 € en total · 0,070 € por pliego** |

Que el rechazo sea 0 no es que la comprobación no haga nada: con la verificación desactivada, dos
tests se ponen en rojo porque una cita inventada pasaría (`tests/test_pliego_leido.py`). Es que el
modelo copia bien cuando se le da el texto exacto contra el que se le va a comprobar.

**n = 62 extracciones de 15 pliegos y 2 empresas.** Con una sola cita mala, M5 bajaría al 98,4 %.
La cifra se volverá a medir en la Fase 5 con las cinco empresas de test.

## 3. Lo que sale de verdad: una ficha real

De un pliego de 81 páginas, el agente leyó 6 y devolvió esto (`Empresa B`, servicio de venta de
entradas). Cada línea lleva la página para poder ir al PDF y comprobarla:

| Requisito | Pág. | Cita del pliego (recortada) |
|---|---|---|
| Volumen anual de negocios ≥ **93.000 €** en el mejor de los tres últimos ejercicios | 52 | «El volumen anual de negocios referido al mejor ejercicio dentro de los tres últimos disponibles será de, al menos, 93…» |
| Seguro de responsabilidad civil ≥ **150.000 €** | 52 | «Se exigirá seguro de responsabilidad civil por importe mínimo de 150.000,00 €.» |
| Servicios similares por importe acumulado de **113.101,50 €** | 52 | «Presentación de documentación acreditativa de haber realizado servicios similares al que es objeto de este contrato p…» |
| No se exige adscripción de medios | 52 | «a) Compromiso de adscripción a la ejecución del contrato de medios [personales] y/o [materiales]: No.» |

Eso es el producto: cuatro requisitos con su cifra y su página, de un documento de 81 páginas, por
siete céntimos. Sin el radar hay que abrir el PDF y buscarlos.

## 4. Y lo que **no** sale: ninguna ficha dice todavía «puede presentarse»

Las 17 fichas salieron **«a revisar»**. Ninguna «apta» y ninguna «no apta». Con M5 al 100 %, esta es
la cifra que importa, y tiene dos causas medidas:

**4.1 De los 66 motivos de las 17 fichas —los 62 requisitos más cuatro fichas sin ningún
requisito—, 63 acaban en «no se puede saber».** No por un fallo del
modelo: porque el radar solo sabe de la empresa lo que dice su perfil, y la mayoría de los requisitos
no se pueden resolver con eso. Clasificación empresarial: hay que mirar el registro oficial.
Habilitación: hay que mirarla. Trabajos similares: el radar **no mira** los contratos que la empresa
ganó, porque son la verdad con la que se le mide (`docs/REGLA_SELECCION.md` §6). Las reglas v1
reservan «no apta» para el volumen de negocios, que es la única comparación de dos números.

**4.2 Y justo el volumen de negocios no se pudo comparar en ningún caso**, por dos motivos que se
cruzan y que con n = 2 empresas es mala suerte:

- **Empresa B** tiene pliegos con cifra (93.000 €, 54.977 €, 15.000 €) y **no tiene cifra de negocio
  pública**: se buscó en cuatro directorios al escribir su perfil y no la publica ninguno.
- **Empresa A** sí tiene cifra (600.000 €, extremo inferior del intervalo publicado), y sus pliegos
  expresan la solvencia sin importe en la página leída: remiten al anexo, o piden un *ratio* de
  liquidez en lugar de un volumen.

Así que la conclusión honesta de la fase es: **el agente localiza y cita los requisitos con
fiabilidad medida, y todavía no puede decidir.** Lo que falta para decidir no es más modelo, son
datos de la empresa y un par de reglas más, y las dos cosas están identificadas aquí abajo.

## 5. Un fallo del dato que llevaba dos días escondido

`perfiles.cifra_negocio` estaba **vacía en las siete empresas**, aunque los siete perfiles congelados
traen su cifra dentro. La Fase 3 dio el dato por recogido y nadie lo había leído desde la tabla,
porque hasta esta fase no había ninguna regla que lo usara.

Se carga ahora del **texto congelado que está en la base**, comprobando su huella antes, sin tocar
ningún perfil:

```bash
uv run python -m radar.perfiles --cifras
```

| Empresa | Cifra que se usa | De dónde |
|---|---|---|
| Empresa A | 600.000 € | extremo inferior de «entre 600.000 € y 1.500.000 €» |
| Empresa D | 600.000 € | ídem |
| Empresa E | 250.001 € | extremo inferior de «entre 250.001 € y 750.000 €» |
| Empresa G | 6.000.000 € | extremo inferior de «entre 6.000.000 € y 30.000.000 €» |
| Empresas B, C y F | — | no la publica ningún directorio; quedan fuera de M3 |

**Corrección al informe de la Fase 3:** decía «cinco en intervalos, dos sin localizar». Los perfiles
congelados dan un intervalo con cifras en **cuatro**; el de Empresa C dice que los directorios la
sitúan en un intervalo pero no escribe ninguna cifra, así que no es utilizable. Son **cuatro con
cifra y tres sin ella**.

Que esto se pudiera arreglar sin volver a pagar nada es la prueba de que separar extracción y
decisión (D09) sirve para algo: `--rehacer-fichas` volvió a decidir las 17 fichas con los requisitos
ya guardados, **gratis**.

## 6. Cuatro fallos encontrados, todos con pliegos reales

| Qué fallaba | Cómo se vio | Coste de no haberlo visto |
|---|---|---|
| La ventana de páginas se llevaba el índice y la parte técnica | Pliego real de 112 páginas: el patrón ISO aparece en 20 páginas técnicas y **la solvencia estaba en la 54** | Leer las páginas equivocadas, en silencio |
| El tramo de 6 páginas «con más puntos en total» | Seis páginas mediocres suman más que la sección de solvencia de dos | Lo mismo |
| El salto al anexo se llevaba otra mención del mismo anexo | Pliego real de 86 páginas: segunda llamada, mismos requisitos genéricos | **0,06 € por nada**, en cada pliego que remita |
| Una llamada pagada podía no quedar apuntada | `run_id` mal pasado: la llamada a Opus se hizo, se pagó, y el `INSERT` falló después | Gasto invisible para el presupuesto del día (D36) |

El último es el más grave de los cuatro y tiene dos tests en rojo que lo demuestran. Y hay un quinto,
de andar por casa pero que cortaba las tandas: el estado del grafo llevaba objetos de Python, y al
reanudar un expediente el checkpointer los devolvía como diccionarios. Ahora el estado son datos
planos, que es lo que se puede guardar en una base y seguir leyendo dentro de un año.

**Y un agujero que no era un fallo sino una ausencia:** «la traza va al log» no tenía log. Un fallo no
previsto decía «Fallo no previsto al leer los pliegos» y el detalle técnico se perdía, así que no
había forma de arreglarlo. Ahora va a la tabla `incidencias` (`radar/incidencias.py`), que es donde
n8n ya escribe los suyos, y el mensaje al usuario dice el número de la incidencia. El fallo del
checkpointer se encontró **con ese mecanismo**, a la primera.

## 7. Lo que cuesta

| | Medido |
|---|---|
| Triaje | 0,000403 € por licitación (0,0403 € / 100) |
| Lectura de un pliego | **0,070 €** (1,3 llamadas a Opus 5, 4,7 páginas) |
| Un día de una empresa: 667 triajes + los pliegos de las que pasen (≈ 45) | 0,27 € + 3,15 € = **3,42 €** |

**El día de una empresa no cabe en el tope de 2 €**, y la mitad del gasto es leer pliegos de
licitaciones que el triaje deja pasar «por si acaso». Palancas, por orden de lo que ahorran:

1. **Batch API: −50 %** en todo lo que no sea del día (la Fase 5 entera va por aquí).
2. **Leer 4 páginas en vez de 6**: medido en los 36 pliegos, acierta igual y baja las páginas de 141
   a 103 (−27 %).
3. **No leer el pliego de los `duda`** hasta que el usuario lo pida. Bajaría el volumen de pliegos a
   la mitad sin tocar el recall del triaje.

Ninguna se aplica todavía: se decide en la Fase 5, con el coste completo medido.

## 8. Puerta de salida de la Fase 4

| Criterio | Estado |
|---|---|
| Grafo completo recorriendo sus ramas | **Sí.** Cuatro ramas, con tests sobre PDF reales construidos en el test; en los datos reales se vieron `solvencia` (14), `solvencia+anexo` (1) y `no_localizada` (2) |
| Modelo de triaje decidido | **Sí**, D06: Haiku 4.5 en lotes de 20 |
| Checkpointer de Postgres | **Sí**, `PostgresSaver`; una licitación reanuda por su `thread_id` |
| Reglas versionadas y probadas con casos reales | **Sí**, `radar/reglas/v1.py` |
| **M5 ≥ 98 % en desarrollo** | **Sí: 100 % (62/62)** |

La fase se cierra. Lo que no se ha hecho, y se dice: los prompts no se han ajustado (van por
`triaje_v1` y `extraccion_v1`, primera versión de los dos), y la rama de OCR para pliegos escaneados
está identificada y no implementada: esos pliegos salen como «revisar» diciendo que son una imagen.

## 9. Lo que se lleva la Fase 5

1. **El anexo que va en otro fichero.** Es la limitación que más frena el resultado útil. Hay que
   descargar los otros documentos del expediente, no solo el PCAP.
2. **Reglas v2**, con lo que se ha visto y **no** se ha cambiado sobre la marcha a propósito:
   - `adscripcion` no es una barrera para presentarse (es un compromiso que se firma en la oferta),
     así que no debería forzar «revisar».
   - Falta un tipo para los requisitos económicos que no son un volumen (ratios de liquidez, seguro
     de responsabilidad civil). Ahora el modelo mete el ratio en `volumen_negocios`, y eso es
     clasificar mal.
   - Un veredicto intermedio del tipo «cumple lo económico, quedan N cosas por comprobar» diría más
     que «revisar».
   Las tres se deciden con M6 (una persona etiquetando a ciegas), no antes.
3. **Coste:** Batch API y las dos palancas del §7.
