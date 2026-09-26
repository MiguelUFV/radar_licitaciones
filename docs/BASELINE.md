# El "antes": los filtros con los que se compara el radar

**Escrito y congelado el 25-09-2026, antes de tener perfiles y antes de medir nada.**

El radar tiene que demostrar que mejora algo. Ese algo es lo que hace hoy una persona: entrar en la
Plataforma, filtrar por unos cuantos códigos CPV y mirar lo que sale. Eso es el **baseline**.

## 1. La trampa que hay que evitar

Es facilísimo construir un rival malo y "ganarle". Un filtro CPV elegido a conveniencia haría que el
radar pareciera brillante sin serlo. La defensa de este proyecto es no elegir **ninguno** a mano:

- Los dos filtros se calculan solos, sin que nadie decida qué códigos entran.
- Los dos se congelan antes de medir nada.
- Los dos se publican en el informe, con sus cifras, aunque uno deje al radar en peor lugar.

## 2. Los dos filtros

### Baseline A — el que usa todo el mundo

Divisiones CPV **72** (servicios TI) y **48** (paquetes de software). Es lo que tiene configurado
cualquier empresa de informática en su alerta, y no hay nada que decidir: son dos números.

Es **estrecho**: en la muestra de la Fase 1, solo el 4 % de las licitaciones llevan un CPV 72 o 48.
Deja fuera lo que se publica bajo otros códigos (equipos informáticos en la 30, servicios
empresariales en la 79), que es justo donde la tesis dice que hay contratos perdidos.

### Baseline B — uno generoso, derivado del perfil

Se saca del perfil de cada empresa con este procedimiento:

1. Del perfil se toman **solo los apartados 1 (qué hace) y 2 (servicios)**. Ni certificaciones, ni
   tamaño, ni lo que la empresa declara no hacer.
2. Ese texto se normaliza (minúsculas, sin tildes) y se parte en palabras de 5 letras o más.
3. Se descartan las palabras generales (`servicios`, `suministro`, `gestion`…). La lista está en
   `radar/baseline.py`, es corta a propósito y se congela con el resto.
4. Entra en el filtro todo código de **división** (`XX000000`) o de **grupo** (`XXXX0000`) cuya
   descripción oficial use alguna de esas palabras como palabra suelta.
5. Cada código se reduce a su prefijo sin ceros finales, **nunca a menos de dos dígitos**
   (`72250000` → `7225`; `30000000` → `30`, no `3`, que sería agricultura). Una licitación pasa el
   filtro si alguno de sus CPV empieza por alguno de esos prefijos, que es como busca la Plataforma.

**Fuente:** vocabulario oficial CPV 2008 de la Dirección General del Patrimonio del Estado, el mismo
que usa la Plataforma: `http://contrataciondelestado.es/codice/cl/2.04/CPV2008-2.04.gc`, 9.454
códigos. Se guarda en la capa raw con su sha256.

Es **ancho**, y a propósito. Con el perfil de ejemplo salen 47 prefijos que cubren divisiones enteras
(48, 50, 51, 72, 73, 75…). Ningún humano marcaría tantas casillas: este filtro le da al rival mucho
más de lo que tendría en la realidad.

## 3. Por qué dos y no uno

Porque cada uno tiene un defecto opuesto, y juntos lo tapan:

| | Baseline A | Baseline B |
|---|---|---|
| Amplitud | Estrecho (4 % de las licitaciones) | Ancho (divisiones enteras) |
| Riesgo | Que sea un rival demasiado fácil | Que deje pasar tanto que gane por volumen |
| Qué demuestra si el radar gana | Que encuentra lo que el filtro típico no ve | Que no es solo cuestión de mirar más |

Si el radar solo ganara a A, el resultado sería flojo y se diría. **Las dos cifras se publican.**

## 4. Lo que se mide

- **M1, recall a igual volumen:** de los contratos que la empresa ganó de verdad, ¿cuántos estaban en
  la lista? La lista del radar se recorta al mismo tamaño diario medio que la del baseline con el que
  se compara.
- **M2, volumen:** cuántas licitaciones al día deja pasar cada uno.

Ninguno de los dos baselines lee un pliego: son filtros sobre lo que ya viene en el feed. Esa es
exactamente la diferencia que el proyecto quiere medir.

## 5. Lo que estos baselines NO son

No son "lo mejor que se puede hacer sin IA". Alguien con años de oficio busca mejor. Son **lo que
hace la mayoría** (A) y **una versión deliberadamente generosa** (B), y así se dirá en el informe: el
radar se compara con la práctica habitual, no con el mejor experto posible.

---

## Cambios

**25-09-2026 · Solo se buscan términos en los códigos de división y de grupo, y el prefijo nunca baja
de dos dígitos.** El procedimiento decía "un código entra si su descripción contiene el término", sin
distinguir el nivel. Al montarlo se vio que "software" aparece en 313 de los 9.454 códigos, casi
todos de ocho dígitos; al reducirlos a su prefijo salían filtros tan estrechos (`48311`) que dejarían
fuera licitaciones vecinas (`48312`). Además, `30000000` sin ceros finales se quedaba en `3`, que
casa con agricultura.

**25-09-2026 · De un baseline a dos, y se quita el paso humano.** El procedimiento original tenía un
filtro único derivado del perfil, que una persona podía ampliar (nunca recortar). Al probarlo con un
perfil de ejemplo salieron **218 códigos**, incluida la división 50 entera (reparación de barcos y de
ascensores) porque el perfil decía "mantenimiento", y la 35 (equipos de defensa) porque decía
"seguridad". Un rival así deja pasar tanto que, midiendo a igual volumen, la comparación no
distinguiría nada; y la regla de "solo añadir" lo empeoraba, porque estaba pensada para un filtro
demasiado estrecho, que era lo contrario de lo que pasó.

Se sustituye por dos filtros calculados, sin ningún paso a mano, y se publican las dos cifras. Es más
exigente para el radar: ahora tiene que ganar a los dos.

Hecho antes de tener perfiles y antes de medir nada: en este momento no se sabe todavía qué empresas
entran en el estudio, así que no hay forma de ajustar esto a un resultado.
