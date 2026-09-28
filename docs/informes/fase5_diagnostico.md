# Fase 5 — Por qué sale lo que sale

Las cifras están en `docs/informes/fase5_resultados.md`, que lo genera un comando y no se toca a
mano. Este documento es la lectura de esas cifras, escrita por una persona, y separada a propósito:
los números no se discuten, la interpretación sí.

## 1. El resultado, sin rodeos

| Comparación | Agente | Rival | Diferencia | IC 95 % | Veredicto |
|---|---|---|---|---|---|
| frente a Baseline A (CPV 72/48) | 74,0 % | 81,8 % | −7,8 puntos | [−23,4, +7,8] | no concluyente |
| frente a Baseline B (del perfil) | 74,0 % | 88,3 % | **−14,3 puntos** | [−26,0, −3,9] | **refutada** |

**El radar encuentra menos contratos que un filtro de CPV.** La tesis del proyecto era que leer el
pliego encontraría contratos que el filtro pierde, y sobre las cinco empresas de test eso no pasa.
Se publica así, que es para lo que se congeló el criterio antes de medir.

## 2. De dónde viene la pérdida: dos empresas de cinco

De los 77 contratos, el agente descartó 20. **Diecinueve de esos 20 son de dos empresas**:

| Empresa | Contratos | Perdidos | Agente | Baseline A | Baseline B |
|---|---|---|---|---|---|
| Empresa C | 16 | 8 | 50,0 % | 62,5 % | 56,2 % |
| Empresa D | 11 | 0 | **100 %** | 81,8 % | 90,9 % |
| Empresa E | 13 | 1 | 92,3 % | 69,2 % | 100 % |
| Empresa F | 9 | 0 | **100 %** | 77,8 % | 88,9 % |
| Empresa G | 28 | 11 | 60,7 % | 100 % | 100 % |

En tres de las cinco empresas el agente gana o empata. En las otras dos pierde, y una de ellas
(Empresa G) pesa 28 de los 77 contratos.

Para señalar de dónde sale la pérdida, y **no** como resultado: sin Empresa G, sobre los 49 contratos
restantes el agente saca 81,6 %, el Baseline A 71,4 % y el Baseline B 81,6 %. La cifra que cuenta es
la del apartado 1, que incluye a G; esto solo dice dónde está el agujero. Se puede comprobar sumando
la tabla de arriba.

## 3. La causa, y no es el modelo

Los contratos que el agente descartó llevan su motivo escrito. Los de Empresa G:

> «Licenciamiento de productos Adobe. La empresa es partner de Autodesk, no de Adobe.»
> «Soporte y actualizaciones de software PRESTO; no es un producto que la empresa distribuya.»

El razonamiento es correcto **según el perfil**: el perfil de Empresa G dice que es partner de
Autodesk y que trabaja en CAD, BIM y GIS. Y resulta que Empresa G ganó, de verdad, once contratos de
licencias de **Adobe** y de **PRESTO**. Es una distribuidora de software: vende las licencias que le
pide el cliente, y su web solo habla de Autodesk.

Empresa C es el mismo caso con otra ropa. Su perfil dice integración de equipos de televisión, y los
contratos que perdió son de analítica de redes sociales, CDN, DRM y distribución de contenidos:

> «Servicios CDN: infraestructura de telecomunicaciones, no integración ni distribución de equipos.»
> «Herramienta de análisis de redes sociales: software de análisis, fuera del ámbito de equipos.»

**El techo del radar es el perfil, no el modelo.** El triaje razonó bien sobre una descripción
demasiado estrecha de lo que hace la empresa. Estaba escrito como riesgo en `docs/SPEC.md` §9
(«Perfil declarativo: el radar sabe de la empresa lo que dice su perfil; si el perfil está mal, la
decisión también») y ahora está medido: **19 de 20 contratos perdidos son productos o servicios que
el perfil no menciona.**

## 4. Tres cosas que hay que tener delante al leer el resultado

**4.1 La pérdida ocurre en el triaje, antes de abrir ningún pliego.** M1 mide la lista corta, y esa
lista la hace el filtro barato con el objeto y el CPV. La parte que lee el pliego funciona: M5 = 100 %
(62 de 62 citas comprobadas) y M7 = 10,87 veces menos páginas que leer. Lo que no funciona es el
filtro de entrada, y es el más fácil de arreglar de los dos.

**4.2 El agente juega con una lista mucho más corta que su rival.** M1 se definió como recall «a igual
volumen», y los volúmenes no son iguales: son favorables al rival.

| Empresa | Agente | Baseline A | Baseline B |
|---|---|---|---|
| Empresa C | 7,6 | 30,3 | 68,2 |
| Empresa D | 53,0 | 30,3 | 166,7 |
| Empresa E | 68,2 | 30,3 | 121,2 |
| Empresa F | 7,6 | 30,3 | 272,7 |
| Empresa G | 53,0 | 30,3 | 287,9 |

Licitaciones al día. Frente al Baseline B, el agente entrega entre **4 y 36 veces menos**
licitaciones y aun así pierde 14 puntos de recall. Frente al Baseline A los volúmenes son del mismo
orden. Nada de esto rescata el resultado —perder es perder— pero dice dónde está el margen: el agente
puede permitirse dudar mucho más de lo que duda sin acercarse al volumen del rival.

**4.3 Nadie ha medido si la lista del rival sirve.** El Baseline B entrega 288 licitaciones al día para
Empresa G. Un humano no las mira. La métrica que diría si esa lista vale algo es M6 (una persona
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
   cuando sea del sector pero de otra marca, cambiaría justo estos 19 casos. Sería `triaje_v2`, y
   obliga a repetir la medición sobre las empresas de test, que ya están usadas: haría falta ampliar
   el sorteo con empresas nuevas.
3. **Dos etapas de triaje**: el barato decide `no` solo con lo evidente y el caro revisa los dudosos.
   Cuesta más y no está claro que arregle el problema, porque el problema es el perfil.

La 1 y la 2 no se pueden aplicar y volver a publicar sobre estas cinco empresas. Lo que se puede
publicar hoy es esto, y decir por qué.

## 6. Qué queda de este proyecto entonces

Lo medido y verificable, con la tesis principal refutada:

- **La lectura del pliego funciona:** 100 % de las citas comprobadas (62 de 62), 4,7 páginas leídas de
  las 51,5 que tiene un pliego, 0,070 € por pliego. Eso no lo hace ningún filtro de CPV.
- **El filtro de entrada del agente es más selectivo que el rival** (hasta 36 veces menos volumen) y
  pierde 14 puntos de recall haciéndolo.
- **La causa está identificada y medida**, no supuesta: 19 de 20 contratos perdidos son productos que
  el perfil de la empresa no menciona.
- **La medición se reproduce con un comando** y cada cifra lleva su commit.

Un resultado negativo medido bien vale más que uno positivo sin medir. Lo que no valdría nada es
ajustar el agente hasta que la cifra saliera bonita, y por eso no se va a hacer.
