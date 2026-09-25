# Informe de la Fase 1 — datos reales

Generado el 2026-09-25T13:42:49+00:00 con `uv run python -m radar.fase1`.
Todas las cifras salen de ese comando; se reproducen volviendo a ejecutarlo.

## Qué se ha descargado

| Medida | Valor |
|---|---|
| Páginas del feed | 30 (452.3 MB) |
| Entradas leídas (una licitación aparece cada vez que cambia de estado) | 14978 |
| Expedientes distintos | 14015 |
| Periodo cubierto | 2026-08-31 a 2026-09-08 (9 días) |
| **Licitaciones nuevas al día** | **138.2** |
| De informática (CPV 72 o 48) | 1023 entradas (6.8 %); 7.0 nuevas al día |
| Con pliego administrativo enlazado | 91.4 % |
| Con lotes | 18.9 % |

## La tesis, medida sobre el feed

| Medida | Valor |
|---|---|
| Traen bloque de solvencia en el feed | 88.9 % |
| De esos, con cifras | 17.8 % |
| De esos, remiten al pliego | 52.9 % |
| **Licitaciones sin la cifra en el feed** | **84.2 %** |

## Los pliegos

| Medida | Valor |
|---|---|
| Pliegos intentados | 120 |
| Descargados y legibles | 115 (95.8 %) |
| Páginas (mediana / p90 / máximo) | 60 / 108 / 209 |
| Con capa de texto | 97.4 % |
| Escaneados | 2.6 % |
| Formularios con casillas | 21.7 % |
| Sección de solvencia localizada | 90.4 % |
| Con una cifra junto a la solvencia | 43.5 % |
| Remiten a un anexo o al anuncio | 69.6 % |
| Páginas que hay que leer (mediana) | 4 |

### Qué requisitos aparecen (porcentaje de pliegos)

| Requisito | % de pliegos |
|---|---|
| certificaciones | 90.4 % |
| adscripcion | 77.4 % |
| habilitacion | 76.5 % |
| volumen_negocios | 65.2 % |
| trabajos_similares | 53.0 % |
| clasificacion | 28.7 % |

## Coste estimado por día

_Estimación con 4 caracteres por token y sin caché de prompts. Los tokens reales se cuentan en la Fase 4. Es una cota superior: supone leer el pliego de todas las licitaciones de informática nuevas, sin que el triaje descarte ninguna._

Supone triar 138.2 licitaciones nuevas al día y leer 7.0 pliegos (4 páginas cada uno, unos 5274 tokens).

| Modelo | Triaje | Extracción | Total |
|---|---|---|---|
| claude-opus-5 | 0.33 € | 0.39 € | 0.72 € |
| claude-haiku-4-5 | 0.07 € | 0.08 € | 0.14 € |

## Decisión

| Puerta | ¿Se cumple? |
|---|---|
| 1. Adjudicadas con NIF del ganador ≥ 80 % | sí |
| 2. Pliegos descargables y legibles ≥ 70 % | sí |
| 3. Solvencia con cifras ausente del feed ≥ 50 % | sí |

**Veredicto: GO**
