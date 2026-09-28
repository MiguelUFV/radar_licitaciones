# Fase 3 — Verdad de referencia y baseline (el "antes")

> **Aviso del 29-09-2026.** Las cifras de universo de este informe (120.656 expedientes, 666,6
> licitaciones al día) se midieron con el histórico empezando en 2025-01. Al completar 2024 se
> vio que parte de esos expedientes se habían publicado antes del periodo y no debían contar:
> `docs/HALLAZGO_UNIVERSO.md` y `docs/DECISIONES.md` D44. Las cifras vigentes están en
> `docs/informes/fase5_resultados.md`, que se regenera desde la base.


Cerrada el 27-09-2026. Todas las cifras salen de la tabla `eval_resultados` y se regeneran con:

```bash
uv run python -m radar.evaluacion.baselines --desde 2025-01-01 --hasta 2025-07-01 --corte 2026-09-01
```

## 1. El material

| | |
|---|---|
| Periodo de estudio | licitaciones publicadas del 01-01-2025 al 30-06-2025 |
| Corte de adjudicaciones | 31-08-2026 |
| Expedientes en el universo | **120.656** |
| Adjudicatarios distintos en el periodo | 35.129 |
| Empresas que cumplen la regla | **19** |
| Empresas del estudio | 2 de desarrollo + 5 de test |
| Contratos ganados por las siete | **101** |

La carga histórica son 20 meses de zip mensuales de la Plataforma: 122.945 expedientes y 218.062
adjudicaciones en total.

## 2. El resultado: lo que encuentra hoy un filtro CPV

| Empresa | Papel | Contratos ganados | Recall A | Recall B | Volumen A | Volumen B |
|---|---|---|---|---|---|---|
| Empresa A | desarrollo | 12 | 100 % | 100 % | 50 | 243 |
| Empresa B | desarrollo | 12 | 67 % | 75 % | 50 | 232 |
| Empresa C | test | 16 | 62 % | 56 % | 50 | 112 |
| Empresa D | test | 11 | 82 % | 91 % | 50 | 156 |
| Empresa E | test | 13 | 69 % | 100 % | 50 | 173 |
| Empresa F | test | 9 | 78 % | 89 % | 50 | 271 |
| Empresa G | test | 28 | 100 % | 100 % | 50 | 315 |
| **Media** | | **101** | **79,7 %** | **87,3 %** | **50** | **215** |

Volumen en licitaciones por día publicado. *Baseline A* son las divisiones CPV 72 y 48; *Baseline B*,
el filtro derivado del perfil de cada empresa (`docs/BASELINE.md`).

## 3. Dos cosas que cambian cómo hay que leer esto

### 3.1 El rival es mucho más fuerte de lo que parecía, y en parte es culpa de la regla

Un filtro de dos números ya encuentra **el 79,7 %** de los contratos. Al radar le queda un margen de
20 puntos, no de 60.

Y hay un motivo que hay que decir en voz alta: **la regla de selección exige que más de la mitad de
los contratos de cada empresa tengan CPV 72 o 48**, que es exactamente lo que filtra el Baseline A.
Es decir, por construcción el Baseline A no puede bajar del 50 %. El sesgo estaba anotado en
`docs/SPEC.md` §9 desde antes de medir ("las empresas se eligen por haber ganado contratos TI, lo que
favorece al filtro CPV"); ahora está cuantificado.

**Consecuencia:** el radar juega en desventaja. Si gana, gana contra un rival inflado por el diseño
del experimento, y eso hace el resultado más creíble, no menos. Si empata, no se podrá concluir gran
cosa, y también se dirá.

### 3.2 El Baseline B no es "más generoso": es distinto

Se diseñó como versión generosa del rival, y para seis de las siete lo es (recall igual o mayor, con
2 a 6 veces más volumen). Pero **con la Empresa C baja del 62 % al 56 %**.

El motivo no es un fallo: es lo que hace el método. Esa empresa se describe como proveedora de
equipamiento para televisión, así que las palabras de su perfil llevan a códigos CPV de audiovisual,
no a los de informática. El filtro derivado de su perfil se va a otro sitio y pierde contratos que el
72/48 sí veía.

**Consecuencia:** hay que dejar de llamar al Baseline B "el generoso" y llamarlo lo que es: el filtro
que sale de lo que la empresa dice de sí misma. Las dos cifras se publican.

## 4. Las siete empresas

Salieron de un sorteo con semilla fija (`20260925`) sobre las 19 que cumplen la regla congelada el
25-09-2026, antes de cargar un solo dato. El embudo:

| Descartadas por | |
|---|---|
| Menos de 8 adjudicaciones | 17.483 |
| No consta que sean pyme | 8.712 |
| No son persona jurídica (autónomos) | 7.221 |
| Son UTE | 1.111 |
| No son mayoritariamente de informática | 583 |

El cuello de botella es el último: de 602 pymes con 8 o más contratos y sin UTE, solo 19 son
mayoritariamente de informática.

Las siete son más heterogéneas de lo esperado: software de personal, plataforma de venta de entradas,
equipamiento de televisión, evaluación educativa, servicios de sistemas, software hospitalario de
oncología y soluciones CAD/BIM/GIS. La regla selecciona **empresas cuyos contratos están codificados
como informática**, que no es lo mismo que empresas de informática. El caso más difícil es la de
evaluación educativa: su perfil no menciona informática en ninguna parte.

## 5. Los perfiles

Los escribió el modelo, no una persona (cambio del 27-09-2026 en `docs/REGLA_SELECCION.md`), porque
Miguel no iba a poder hacerlo. Salen **solo de fuentes públicas sobre cada empresa** —su web y
directorios— y **sin consultar ni un contrato**. Cada uno lleva sus fuentes con la fecha de consulta.

Antes de escribirlos se comprobó que el NIF de cada web coincide con el de la base: los siete
coinciden, así que ningún perfil es de la empresa equivocada.

Están congelados con su sha256 en `docs/perfiles_congelados.md`. Si alguien retoca uno, el comando se
para y obliga a volver a medir.

**Sesgo que esto introduce, y es el más importante del estudio:** un perfil escrito por el modelo sale
más ordenado y más aprovechable por una máquina que el que escribiría un cliente real. Favorece al
radar. Dos de los siete se apoyan además en fuentes de segunda mano, porque la web de esas empresas
bloquea el acceso automatizado.

## 6. La puerta de la fase

**Cumplida.** Baseline medido; regla, procedimiento y perfiles congelados en git **antes** de escribir
una línea del agente. El orden de los commits lo demuestra:

| Commit | Qué congela |
|---|---|
| `a763341` (25-09) | La regla de selección, antes de cargar ningún dato |
| `dee3b4a` (25-09) | El procedimiento del baseline, antes de tener perfiles |
| `9961988` (26-09) | El sorteo, con su semilla y la huella de la regla |
| este | Los perfiles, con su sha256, y la medición del "antes" |

## 7. Lo que el radar tiene que superar

- **Recall a igual volumen:** más del **79,7 %** con 50 licitaciones al día (Baseline A).
- Y más del **87,3 %** contra el filtro salido del perfil, que además deja pasar 215 al día.

Las dos cifras irán en el informe final, gane o pierda.
