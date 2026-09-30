# Fase 5 — Por qué sale lo que sale

Las cifras están en `docs/informes/fase5_resultados.md`, que lo genera un comando y no se toca a
mano. Este documento es la lectura de esas cifras, escrita por una persona, y separada a propósito:
los números no se discuten, la interpretación sí.

**Reescrito el 30-09-2026.** Todas las cifras de este documento se han vuelto a medir sobre el
universo corregido de D44 (85.769 expedientes, no 120.656). Las de la versión anterior se midieron
con el histórico de 2024 sin cargar y **no eran ciertas**: metían en el estudio 34.887 expedientes
cuya primera publicación era de 2024. Lo que cambia y lo que no está en el apartado 7.

## 1. El resultado, sin rodeos

| Comparación | Agente | Rival | Diferencia | IC 95 % | Veredicto |
|---|---|---|---|---|---|
| frente a Baseline A (CPV 72/48) | 69,2 % | 82,7 % | −13,5 puntos | [−32,7, +5,8] | no concluyente |
| frente a Baseline B (del perfil) | 69,2 % | 88,5 % | **−19,2 puntos** | [−32,7, −7,7] | **refutada** |

**El radar encuentra menos contratos que un filtro de CPV.** La tesis del proyecto era que leer el
pliego encontraría contratos que el filtro pierde, y sobre las cinco empresas de test eso no pasa.
Se publica así, que es para lo que se congeló el criterio antes de medir.

## 2. De dónde viene la pérdida: dos empresas de cinco

De los 52 contratos, el agente descartó 16. **Quince de esos 16 son de dos empresas**:

| Empresa | Contratos | Perdidos | Agente | Baseline A | Baseline B |
|---|---|---|---|---|---|
| Empresa C | 8 | 5 | 37,5 % | 75,0 % | 37,5 % |
| Empresa D | 7 | 0 | **100 %** | 71,4 % | 85,7 % |
| Empresa E | 11 | 1 | 90,9 % | 63,6 % | 100 % |
| Empresa F | 6 | 0 | **100 %** | 83,3 % | 100 % |
| Empresa G | 20 | 10 | 50,0 % | 100 % | 100 % |

En dos de las cinco empresas el agente saca el 100 %, y en una tercera el 90,9 %. En las otras dos
se hunde, y una de ellas (Empresa G) pesa 20 de los 52 contratos.

Para señalar de dónde sale la pérdida, y **no** como resultado: sin Empresa G, sobre los 32
contratos restantes el agente saca 81,2 %, el Baseline A 71,9 % y el Baseline B 81,2 %. La cifra
que cuenta es la del apartado 1, que incluye a G; esto solo dice dónde está el agujero. Se puede
comprobar sumando la tabla de arriba.

## 3. La causa, y no es el modelo

Los contratos que el agente descartó llevan su motivo escrito. Se han leído **los dieciséis**, no
una muestra. Los de Empresa G:

> «Licenciamiento de productos Adobe. La empresa es partner de Autodesk, no de Adobe.»
> «Soporte y actualizaciones de software PRESTO; no es un producto que la empresa distribuya.»

El razonamiento es correcto **según el perfil**: el perfil de Empresa G dice que es partner de
Autodesk y que trabaja en CAD, BIM y GIS. Y resulta que Empresa G ganó, de verdad, diez contratos
de licencias de **Adobe** (seis) y de **PRESTO** (cuatro). Es una distribuidora de software: vende
las licencias que le pide el cliente, y su web solo habla de Autodesk.

Empresa C es el mismo caso con otra ropa. Su perfil dice integración de equipos de televisión, y
los cinco contratos que perdió son de analítica de redes sociales, IA para metadatado de archivo,
CDN, DRM y distribución de contenidos:

> «Servicios CDN: infraestructura de telecomunicaciones, no integración ni distribución de equipos.»
> «Herramienta de análisis de redes sociales: software de análisis, fuera del ámbito de equipos.»

El único perdido fuera de esas dos empresas, el de Empresa E, es del mismo tipo: mantenimiento del
software AuditPlus, descartado por ser «una aplicación específica de terceros, no soluciones propias
de la empresa».

**El techo del radar es el perfil, no el modelo.** El triaje razonó bien sobre una descripción
demasiado estrecha de lo que hace la empresa. Estaba escrito como riesgo en `docs/SPEC.md` §9
(«Perfil declarativo: el radar sabe de la empresa lo que dice su perfil; si el perfil está mal, la
decisión también») y ahora está medido: **los 16 contratos perdidos, sin excepción, son productos o
servicios que el perfil de la empresa no menciona.**

## 4. Tres cosas que hay que tener delante al leer el resultado

**4.1 La pérdida ocurre en el triaje, antes de abrir ningún pliego.** M1 mide la lista corta, y esa
lista la hace el filtro barato con el objeto y el CPV. La parte que lee el pliego funciona: M5 = 100 %
(62 de 62 citas comprobadas) y M7 = 10,87 veces menos páginas que leer. Lo que no funciona es el
filtro de entrada, y es el más fácil de arreglar de los dos. Ninguna de esas dos métricas depende del
universo, así que no cambian con la corrección de D44.

**4.2 El agente juega con una lista más corta que el Baseline B, pero no siempre más que el A.**
M1 se definió como recall «a igual volumen», y los volúmenes no son iguales.

| Empresa | Agente | Baseline A | Baseline B |
|---|---|---|---|
| Empresa C | 29,6 | 39,5 | 74,0 |
| Empresa D | 56,7 | 41,2 | 133,9 |
| Empresa E | 57,9 | 31,6 | 94,8 |
| Empresa F | 20,8 | 31,2 | 197,9 |
| Empresa G | 69,1 | 59,2 | 227,1 |

Licitaciones al día. Frente al Baseline B, el agente entrega entre **1,6 y 9,5 veces menos**
licitaciones y aun así pierde 19 puntos de recall. Frente al Baseline A entrega **menos en dos
empresas y más en tres**. Nada de esto rescata el resultado —perder es perder— pero dice dónde está
el margen frente al B: el agente puede permitirse dudar bastante más de lo que duda sin acercarse a
su volumen.

**4.3 Nadie ha medido si la lista del rival sirve.** El Baseline B entrega 227 licitaciones al día
para Empresa G. Un humano no las mira. La métrica que diría si esa lista vale algo es M6 (una persona
etiquetando a ciegas) y **no está medida**. Con lo que hay, la comparación es de recall a coste de
volumen, y el volumen del rival no lo paga nadie en la métrica.

## 5. Lo que se podría hacer, y lo que no se va a hacer

**No se va a tocar el prompt ni las reglas con estos datos.** Ajustar el agente después de ver el
resultado de las empresas de test convierte el test en desarrollo, y entonces no queda nada con lo que
medir. Está escrito en `docs/PLAN_MEDICION.md` §7 desde antes de medir.

Lo que sí se puede hacer, por orden de lo que arreglaría:

1. **Perfiles que digan lo que la empresa vende de verdad**, no solo lo que destaca en su web: marcas
   que distribuye, servicios adyacentes, lo que ha hecho para otros clientes. Es un cambio en el
   procedimiento de la Fase 3, obliga a volver a congelar los perfiles y a **volver a medir todo**, y
   hay que anotarlo en `docs/REGLA_SELECCION.md`. Es la vía honesta, y probablemente la que convierte
   el resultado.
2. **Un triaje que dude más.** El prompt dice «ante la duda, `duda`», y produjo `no` firmes sobre
   productos que el perfil no nombra. Un `no` solo cuando el objeto sea de otro sector, y `duda`
   cuando sea del sector pero de otra marca, cambiaría justo estos 16 casos. Sería `triaje_v2`, y
   obliga a repetir la medición sobre las empresas de test, que ya están usadas: haría falta ampliar
   el sorteo con empresas nuevas.
3. **Dos etapas de triaje**: el barato decide `no` solo con lo evidente y el caro revisa los dudosos.
   Cuesta más y no está claro que arregle el problema, porque el problema es el perfil.

La 1 y la 2 no se pueden aplicar y volver a publicar sobre estas cinco empresas. Lo que se puede
publicar hoy es esto, y decir por qué.

## 5 bis. Lo que dice medir el volumen (M9 y M10)

El apartado 4.2 dejaba una pregunta abierta: el agente entrega menos papel que el Baseline B, y eso
no lo pagaba nadie en la métrica. Se definieron dos métricas para contestarla
—`docs/METRICA_EFICIENCIA.md`, escritas **después** de conocer M1 y con su regla de decisión fijada
antes de calcular— y las cifras están en el informe de resultados. No rescatan nada.

**M9 (licitaciones que hay que revisar por cada contrato encontrado) dice que no.** La regla pedía
que el agente ganara a los dos rivales en 3 de las 5 empresas. Gana en 2: Empresa D (1.465 frente a
1.492 y 4.040) y Empresa F (628 frente a 1.131 y 5.969). En Empresa C, E y G el Baseline A encuentra
un contrato revisando menos licitaciones que el agente.

**M10 (recall si todos entregaran el mismo volumen que el agente) dice otra cosa, y las dos son
verdad.** Frente al Baseline B el agente gana en las cinco empresas, casi siempre por mucho: 100 %
frente a 10,5 % en Empresa F. Frente al Baseline A gana en tres de cinco (D, E y F) y pierde en
C y G.

No es una contradicción, son dos preguntas distintas: M10 pregunta quién acierta más con el mismo
trabajo, y M9 cuánto trabajo cuesta cada acierto. En Empresa D el agente tiene a la vez mejor recall
y más volumen que el Baseline A, y M9 le penaliza el volumen de más casi tanto como le premia el
recall de más.

**Lo que queda en pie, entonces:**

- **El Baseline B compra su recall con volumen.** Entrega entre 1,6 y 9,5 veces más licitaciones, y
  a igual volumen encuentra menos que el agente en las cinco empresas. Los 19 puntos con los que
  gana M1 salen de repartir 227 licitaciones al día a una empresa que no las va a mirar.
- **Frente al Baseline A —el filtro de CPV estándar— el agente no gana por ningún lado.** Ni en
  recall (69,2 % contra 82,7 %, no concluyente), ni en eficiencia (pierde en 3 de 5), ni en volumen
  (entrega más en 3 de 5).
- **Sigue sin medirse M6**, que es lo único que diría si alguna de las dos listas sirve.

Que la regla de decisión estuviera escrita antes es lo que hace que este apartado valga algo: el
resultado salió en contra de quien lo escribió, otra vez, y se publica otra vez.

## 6. Qué queda de este proyecto entonces

Lo medido y verificable, con la tesis principal refutada:

- **La lectura del pliego funciona:** 100 % de las citas comprobadas (62 de 62), 4,7 páginas leídas de
  las 51,5 que tiene un pliego. Eso no lo hace ningún filtro de CPV, y no depende del universo.
- **El filtro de entrada del agente es más selectivo que el Baseline B** (hasta 9,5 veces menos
  volumen) y pierde 19 puntos de recall haciéndolo. Frente al Baseline A **no** es más selectivo en
  3 de las 5 empresas.
- **La causa está identificada y medida**, no supuesta: los 16 contratos perdidos son productos que
  el perfil de la empresa no menciona.
- **La medición se reproduce con un comando** y cada cifra lleva su commit.

Un resultado negativo medido bien vale más que uno positivo sin medir. Lo que no valdría nada es
ajustar el agente hasta que la cifra saliera bonita, y por eso no se va a hacer.

## 7. Qué cambió al corregir el universo (D44, 30-09-2026)

El histórico empezaba en 2025-01, así que un expediente publicado por primera vez en 2024 y
actualizado en 2025 parecía nuevo y entraba en el estudio. Al cargar 2024 entero, el universo pasa de
120.656 a **85.769** expedientes: sobraban 34.887, casi uno de cada tres. La previsión inicial, hecha
con solo tres meses de 2024 cargados, era de 7.732 — quedó corta por un factor de cuatro y medio,
porque cuanto más histórico hay, más contratos se descubren que ya existían.

| | Antes (n=120.656) | Ahora (n=85.769) |
|---|---|---|
| Contratos de la muestra | 77 | **52** |
| Recall del agente | 74,0 % | **69,2 %** |
| Baseline A | 81,8 % | **82,7 %** |
| Baseline B | 88,3 % | **88,5 %** |
| Diferencia vs. A | −7,8 · IC [−23,4, +7,8] | **−13,5** · IC [−32,7, +5,8] |
| Diferencia vs. B | −14,3 · IC [−26,0, −3,9] | **−19,2** · IC [−32,7, −7,7] |
| Contratos perdidos | 20 | **16** |

**El veredicto no cambia:** refutada frente al Baseline B, no concluyente frente al A. Lo que cambia
es el margen, y a peor: los expedientes que sobraban inflaban el recall del agente casi cinco puntos,
mientras que los de los dos baselines apenas se movían. Dicho de otro modo, **el error favorecía al
agente**, que es la dirección incómoda.

Dos afirmaciones concretas de la versión anterior de este documento han quedado desmentidas y se
corrigen arriba, no se borran:

- Decía «19 de 20 contratos perdidos». Ahora son **16 de 16**: todos, sin la excepción que había.
- Decía que el agente entrega «entre 4 y 36 veces menos» que el Baseline B. Con el universo
  corregido son **entre 1,6 y 9,5 veces menos**. El margen para dudar más sigue existiendo, pero es
  mucho menor de lo que este documento afirmaba.

Nada de esto salió de una revisión. Salió de un candado escrito el mismo día para otra cosa:
`radar.diagnostico` compara el universo de ahora con la `n` guardada en `eval_resultados`, y cantó al
no cuadrar. Sin él, la carga de 2024 habría cambiado las cifras en silencio y este informe seguiría
diciendo 74,0 %.
