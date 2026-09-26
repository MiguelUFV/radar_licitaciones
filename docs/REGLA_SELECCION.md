# Regla de selección de las empresas del estudio

**Escrita y congelada el 25-09-2026, antes de mirar los datos históricos.** Ese es el sentido de este
documento: si la regla se escribiera después de ver qué empresas salen, el estudio no valdría nada.
El commit que la introduce es anterior a la carga histórica, y se puede comprobar en el historial de
git.

Cualquier cambio posterior se anota al final, con fecha y motivo, y obliga a volver a medir el
baseline (`docs/SPEC.md` §6).

---

## 1. Para qué se eligen empresas

El radar dice a una empresa a qué licitaciones puede presentarse. Para medir si acierta hace falta
una **verdad de referencia**: contratos que esa empresa ganó de verdad. Si el radar, mirando solo lo
publicado antes del plazo, no habría encontrado un contrato que la empresa acabó ganando, eso es un
fallo medible (métrica M1, recall).

Las empresas no se eligen a mano. Se eligen con esta regla, aplicada por un script.

## 2. Universo

Adjudicaciones de la carga histórica:

- licitaciones **publicadas** entre `2025-01-01` y `2025-06-30`;
- con adjudicación registrada en el feed hasta `2026-08-31` (un contrato tarda meses en resolverse);
- de la sindicación 643 de PLACSP (la misma fuente que usa el radar a diario).

### Cómo se traduce a la base de datos

Esto no cambia ningún criterio: lo concreta, para que aplicarlo no dependa de nadie. Se escribe
también antes de ejecutarlo.

- **Publicada** = la primera vez que ese expediente aparece en el feed, es decir `min(entry_updated)`
  de todas las versiones con el mismo `entry_id`. El feed no trae una "fecha de publicación" aparte.
- **Adjudicación registrada hasta el corte** = existe una versión del expediente con adjudicatario y
  con `entry_updated <= 2026-08-31`.
- **Adjudicaciones distintas** = expedientes distintos. Un mismo expediente aparece varias veces en
  el feed (una por cambio de estado) y eso cuenta como **una**.

## 3. Criterios de inclusión

Una empresa entra en el sorteo si cumple **todos**:

| # | Criterio | Cómo se comprueba, sin interpretar |
|---|---|---|
| 1 | Es persona jurídica | `adjudicaciones.adjudicatario` empieza por letra (NIF de sociedad). Se descartan los NIF de persona física: además de no ser empresas, son datos personales (`docs/DATOS.md` §7) |
| 2 | Es pyme | `es_pyme = true` (campo `SMEAwardedIndicator` del feed) en **todas** sus adjudicaciones del periodo |
| 3 | No es UTE | El NIF no empieza por `U` y el nombre no contiene `UTE` |
| 4 | Volumen suficiente | ≥ **8** adjudicaciones distintas en el periodo |
| 5 | Es de informática | > **50 %** de sus adjudicaciones tienen algún CPV que empiece por `72` o `48` |

**Por qué 8:** con menos, el recall se mide sobre tan pocos casos que un acierto o un fallo mueven la
cifra decenas de puntos y el intervalo de confianza deja de decir nada.

**Por qué "más de la mitad" y no "todas":** una empresa de informática también gana contratos de otra
cosa. Exigir el 100 % dejaría fuera a las empresas reales.

## 4. Reparto entre desarrollo y test

1. Las empresas que cumplen la regla se ordenan por NIF ascendente (orden reproducible, no por
   volumen: ordenar por volumen elegiría siempre a las mismas).
2. Se barajan con semilla fija: `random.Random(20260925)`.
3. Las **2 primeras** son de **desarrollo**. Las **5 siguientes**, de **test** (mínimo 3; si no salen
   3, se amplía el periodo del universo y se anota el cambio aquí).

**Las empresas de desarrollo** son las únicas con las que se ajustan prompts y reglas.

**Las empresas de test no se tocan.** No se miran sus contratos, no se ajusta nada con ellas y no se
mide nada sobre ellas hasta que el agente esté congelado (Fase 5). Es la única forma de que la cifra
final signifique algo.

## 5. Sustituciones permitidas

Solo una, y hay que anotarla: si de una empresa seleccionada **no se encuentra web pública** con la
que escribir su perfil, se sustituye por la siguiente del sorteo. Se comprueba después del sorteo, y
queda registrado qué empresa salió, por cuál se cambió y por qué.

Ninguna otra sustitución está permitida. En concreto, no se puede descartar una empresa porque sus
contratos sean difíciles, raros o poco favorables al radar.

## 6. Los perfiles

El perfil es lo que el radar sabe de la empresa. Se escribe **a partir de la web de la empresa y
nada más**: su descripción de sí misma, sus servicios, su tamaño si lo publica.

- Los escribe Miguel, no el modelo, y **sin mirar los contratos que ganó** la empresa. Escribir el
  perfil sabiendo lo que ganó sería escribir la respuesta en el enunciado.
- Cada perfil se guarda con su `sha256`, la fecha y las URL de las que salió. A partir de ahí queda
  congelado: si se cambia, se vuelve a medir.
- La cifra de negocio se busca aparte, en una fuente pública (cuentas depositadas, web de la
  empresa), y se guarda con su fuente y su fecha. Si no hay cifra pública, esa empresa **no entra en
  M3** (exclusiones erróneas por solvencia), y se dice en el informe.

## 7. Anonimato

En todo lo público (README, informes, vídeo, LinkedIn) las empresas son **Empresa A** … **Empresa G**.
Los NIF y los nombres se quedan en la base de datos local, que no se publica.

---

## Cambios

_Ninguno. Si algún día hay uno, va aquí con su fecha y su motivo._

**26-09-2026 · "Persona jurídica" se comprueba por la letra del NIF, no por "empieza por letra".**
El criterio 1 decía "empieza por letra (NIF de sociedad)". Al auditar los datos se vio el agujero: un
**NIE** (el identificador de un extranjero, que es una persona física) empieza por X, Y o Z, así que
pasaba el criterio y podía entrar en el estudio como si fuera una empresa. En la carga había 129
adjudicaciones con NIE.

Ahora se comprueba contra las letras que la Agencia Tributaria usa para personas jurídicas
(`ABCDEFGHJNPQRSUVW`, en `radar/personas.py`). No cambia la intención del criterio: la concreta para
que haga lo que decía. Hecho antes de aplicar la regla: no hay ninguna empresa seleccionada todavía.

**27-09-2026 · Los perfiles los escribe el modelo, no Miguel.** El apartado 6 decía que los escribía
Miguel. No se ha hecho así: dijo que no sabía cómo hacerlo y que no tenía tiempo, y con siete empresas
la alternativa era que el proyecto se quedara parado aquí.

**Lo que se pierde.** El perfil escrito por una persona se parece al que tendría un cliente real:
desordenado, con lagunas, con las palabras de quien lo escribe. Escrito por el modelo sale más
ordenado y más fácil de aprovechar por una máquina, y eso **juega a favor del radar**. Es un sesgo en
la dirección favorable, va a los límites del SPEC y se dice en el informe.

**Lo que se mantiene, que es lo que da valor a la medición.** El perfil sale **solo de fuentes públicas
sobre la empresa** (su web y directorios de empresas), y **no se ha consultado ni un contrato**. Cada
perfil lleva la lista de direcciones consultadas con su fecha, así que cualquiera puede comprobar de
dónde salió cada frase.

**Controles añadidos:**
- Antes de escribir nada se comprobó que el NIF de cada web coincide con el de la base, para no
  perfilar a la empresa equivocada. Los siete coinciden.
- Cada perfil queda congelado con su sha256 en `docs/perfiles_congelados.md`. Si alguien lo retoca
  después, el comando se para y obliga a volver a medir.
- Dos perfiles se apoyan más en fuentes de segunda mano porque su web bloquea el acceso automatizado.
  Queda anotado en el propio perfil y en el informe: son los dos más débiles.
