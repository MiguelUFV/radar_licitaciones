# El "antes": cómo se construye el filtro con el que se compara el radar

**Escrito y congelado el 25-09-2026, antes de tener perfiles y antes de medir nada.**

El radar tiene que demostrar que mejora algo. Ese algo es lo que hace hoy una persona: entrar en la
Plataforma, filtrar por unos cuantos códigos CPV y mirar lo que sale. Eso es el **baseline**.

## 1. La trampa que hay que evitar

Es facilísimo construir un baseline malo y "ganarle". Un filtro CPV mal elegido a propósito haría que
el radar pareciera brillante sin serlo. Por eso el baseline se construye con tres reglas:

1. **Sale del perfil por un procedimiento escrito**, no a ojo y no después de ver los resultados.
2. **Se le puede añadir, nunca quitar.** Si al revisarlo se ve que falta un código que cualquiera de
   esa empresa buscaría, se añade y se anota el motivo. Quitar códigos está prohibido, porque quitar
   es justo lo que haría que el baseline perdiera.
3. **Se congela antes de medir**, con el hash del perfil del que sale y el del vocabulario oficial.

La regla 2 juega **a favor del baseline**: cuantos más códigos tenga, más contratos encuentra y más
alto es su recall. Si aun así el radar gana, gana contra la versión buena del rival.

## 2. De dónde salen los códigos

**Fuente:** vocabulario oficial CPV 2008 de la Dirección General del Patrimonio del Estado, el mismo
que usa la Plataforma:
`http://contrataciondelestado.es/codice/cl/2.04/CPV2008-2.04.gc` — 9.454 códigos con su descripción
oficial en español. Se guarda en la capa raw con su sha256, como cualquier otro dato descargado.

## 3. Procedimiento

1. Del perfil se toman los apartados **1 (qué hace)** y **2 (servicios)**. Nada más: ni el tamaño ni
   las certificaciones.
2. Ese texto se normaliza: minúsculas, sin tildes, y se quitan las palabras vacías (preposiciones,
   artículos y verbos genéricos como "ofrecer" o "realizar").
3. Quedan los **términos significativos**: palabras de 5 letras o más.
4. Un código CPV entra en la semilla si su descripción oficial contiene alguno de esos términos.
5. Cada código se reduce a su **prefijo sin ceros finales** (`72250000` → `7225`). Una licitación
   pasa el filtro si alguno de sus CPV empieza por alguno de esos prefijos, que es como busca la
   Plataforma.
6. **Revisión humana, una vez:** Miguel mira la lista y puede añadir códigos, cada uno con su motivo
   en una línea. No puede quitar ninguno. Después se congela.

## 4. Palabras clave (opcional)

Si el perfil deja claro que la empresa se define por algo que el CPV no distingue (por ejemplo,
"historia clínica electrónica"), se puede añadir una lista corta de palabras que se buscan en el
título de la licitación. Se congela igual, y se dice en el informe si se usaron.

## 5. Lo que se mide con él

- **M1, recall a igual volumen:** de los contratos que la empresa ganó de verdad, ¿cuántos estaban en
  la lista del baseline? ¿Y en la del radar, recortada al mismo tamaño diario?
- **M2, volumen:** cuántas licitaciones al día deja pasar cada uno.

El baseline no lee ningún pliego: es un filtro sobre lo que ya viene en el feed. Esa es exactamente
la diferencia que el proyecto quiere medir.

## 6. Lo que este baseline NO es

No es "lo mejor que se puede hacer sin IA". Alguien con años de oficio busca mejor que un filtro CPV.
Es **lo que hace la mayoría**, y así se dirá en el informe: el radar se compara con la práctica
habitual, no con el mejor experto posible.

---

## Cambios

_Ninguno. Si algún día hay uno, va aquí con su fecha y su motivo._
