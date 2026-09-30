# El periodo del estudio estaba mal delimitado, y se descubrió cargando 2024

**29-09-2026. Abierto: hay una decisión que tomar y está al final.**

## 1. Qué ha pasado

El universo del estudio son «los expedientes cuya **primera** publicación cae en el primer
semestre de 2025». La carga histórica empezaba en 2025-01, así que un expediente publicado en
octubre de 2024 y actualizado en marzo de 2025 aparecía en la base con su primera versión en
marzo de 2025, y entraba en el universo. No debía estar.

Al cargar los primeros meses de 2024 esos expedientes recuperan su versión verdadera y salen del
periodo. El aviso lo dio solo el diagnóstico, que se había escrito unas horas antes para eso
mismo:

> El periodo del estudio tiene ahora 112.924 expedientes y las cifras publicadas se midieron
> sobre 120.656.

## 2. Cuánto se mueve

Con **solo dos meses de 2024 cargados** (noviembre y diciembre); la carga del año entero está en
curso y estas cifras aún pueden crecer.

| | Publicado | Con 2024 parcial |
|---|---|---|
| Universo del periodo | 120.656 | **112.924** |
| Contratos ganados de las 5 empresas de test | 77 | **66** |
| Expedientes triados que siguen en el periodo | 165 | **148** (17 se salen) |

Por empresa, los contratos ganados: C 16 → 13, D 11 → 9, E 13 → 12, F 9 → 8, G 28 → 24.

**Lo que no se mueve:** las adjudicaciones del periodo (139.157) ni el número de contratos
contados por fecha de actualización. Solo cambia lo que depende de la **primera** publicación,
que es justo la definición del universo (D30).

## 3. Lo que esto le hace a la tesis

Recalculando el recall del agente con los triajes que ya están guardados —sin llamar al modelo
ni una vez, porque las decisiones no cambian, solo cambia qué expedientes cuentan:

| | Contratos | Recall |
|---|---|---|
| M1 publicado | 77 | 74,0 % |
| M1 con el periodo corregido | 66 | **74,2 %** |

**La conclusión aguanta.** Los once contratos que salen estaban repartidos entre aciertos y
fallos casi en la misma proporción, así que el recall del agente se queda donde estaba. Eso es
una buena noticia sobre la solidez del estudio y **no** es todavía el resultado: falta recalcular
los dos baselines, la diferencia y su intervalo de confianza. Eso también se hace sin gastar.

## 4. De quién es el error

Del estudio, y es mío. El periodo se eligió sabiendo que el histórico empezaba en 2025-01, y
nadie comprobó qué pasaba con los expedientes que venían de antes. La regla de selección y el
plan de medición están bien escritos; lo que faltaba era el dato.

No lo cazó ninguna revisión: lo cazó un candado escrito el mismo día para otra cosa. Sin él, la
carga de 2024 habría cambiado las cifras en silencio y el informe habría seguido diciendo 120.656.

## 5. La decisión

Hay tres caminos y **no los decide quien escribe esto**:

| | Qué implica | A favor | En contra |
|---|---|---|---|
| **A. Deshacer la carga de 2024** | Volver al histórico que empieza en 2025-01 | Las cifras publicadas siguen correspondiendo a los datos | Se elige a sabiendas un dato peor para no tener que tocar nada. El error seguiría ahí, solo que invisible |
| **B. Completar 2024 y volver a medir** | Recalcular M1, M2, la diferencia, el intervalo, M9 y M10 con el periodo corregido | Es lo que manda el propio proyecto cuando cambia algo de lo que dependen las cifras. No cuesta dinero: los triajes están guardados | Cambia cifras ya publicadas, y hay que reescribir los informes y el dossier |
| **C. Publicar las dos** | Mantener lo medido y añadir el recálculo al lado, con este documento | Es lo más honesto: enseña el error y su efecto | Un informe con dos juegos de cifras se lee peor |

**Lo que recomienda quien escribe esto: B, y este documento se queda como explicación del
cambio.** El recálculo sale gratis, el dato es mejor, y la primera comprobación dice que la
conclusión no se mueve. Publicar dos juegos de cifras (C) protege al autor más que al lector.

Lo que **no** se puede hacer es quedarse a medias: con 2024 cargado a la mitad, ni el universo
viejo ni el nuevo son ciertos.

## 6. Lo que queda cuando se decida

- Terminar la carga de 2024 (en curso, no cuesta dinero).
- `uv run python -m radar.evaluacion.agente --solo-medir` y `radar.evaluacion.baselines`: vuelven
  a medir sin llamar al modelo.
- `radar.evaluacion.eficiencia --guardar` para M9 y M10, que salen de M2.
- Regenerar el informe de la Fase 5 y el dossier, que leen las cifras de la base.
- Convertir esto en una entrada de `docs/DECISIONES.md` con lo que se decidió y por qué.

## 6. Cierre (30-09-2026), y en qué se equivocó este documento

Los doce meses de 2024 están cargados y la medición está rehecha. Las cifras de los apartados 2
y 3 eran provisionales —el propio documento avisaba de que podían crecer— y crecieron bastante
más de lo que se esperaba.

| | Publicado | Con 2 meses (apdo. 2) | **Final, 2024 entero** |
|---|---|---|---|
| Universo del periodo | 120.656 | 112.924 | **85.769** |
| Contratos ganados de las 5 de test | 77 | 66 | **52** |
| Recall del agente | 74,0 % | 74,2 % | **69,2 %** |

**El apartado 3 se equivocó, y conviene que quede escrito.** Decía «la conclusión aguanta» y que
«el recall del agente se queda donde estaba», porque con dos meses los contratos que salían
estaban repartidos entre aciertos y fallos casi en la misma proporción. Con el año entero deja de
ser verdad: el recall del agente cae **4,8 puntos**, mientras que los dos baselines se mueven
menos de medio punto (81,8 → 82,7 y 88,3 → 88,5).

Dicho de otro modo: **los expedientes que sobraban favorecían al agente.** La diferencia contra
el Baseline B pasa de −14,3 a −19,2 puntos, y contra el Baseline A de −7,8 a −13,5. El veredicto
no cambia —refutada frente a B, no concluyente frente a A— pero el margen empeora en los dos.

La lección no es que el apartado 3 estuviera mal escrito: estaba bien escrito, avisaba de que era
provisional y no lo vendió como resultado. La lección es que **una muestra parcial de un sesgo no
dice la dirección del sesgo entero**, y que si aquel 74,2 % se hubiera publicado por las prisas,
habría sido una cifra tranquilizadora y falsa.

Detalle y cifras por empresa en `docs/informes/fase5_diagnostico.md` §7.
