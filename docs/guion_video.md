# Guion del vídeo de 60 segundos

Para la publicación del repositorio (Fase 8). Lo lee Miguel a cámara o en voz en off.

**Quién lo ve:** gente que no conoce el proyecto y le dedicará un minuto — perfiles técnicos y de
datos en LinkedIn. No conocen la contratación pública ni los nombres de las métricas, así que aquí
no aparece ninguno: ni M1, ni recall, ni baseline. Se dicen los números, no sus etiquetas.

**Regla de este guion:** toda cifra que se dice está medida y tiene de dónde salir. Al lado de cada
una va su fuente, entre corchetes, para comprobarla antes de grabar. Los corchetes no se leen.

---

## Narración con tiempos

**0:00–0:08 · El problema**

> Un filtro normal por código de actividad le deja a una empresa doscientas veintisiete
> licitaciones al día para revisar.
> Nadie las lee.

[227,1 al día, Baseline B en Empresa G — `fase5_resultados.md`, M2]

**0:08–0:20 · Qué hace**

> Construí un agente que las lee por ella. Descarta lo que no encaja con su perfil, abre el pliego
> de las que quedan y le dice a cuáles puede presentarse.
> Cada requisito que saca viene con la frase literal del pliego y la página donde está.

[`radar/extraccion.py`: Python comprueba que la cita aparece en esa página antes de usarla]

**0:20–0:30 · La tesis y el método**

> La idea era que leer el pliego encontraría contratos que un filtro por código pierde.
> Antes de medir nada, congelé el método: siete empresas por sorteo y el criterio escrito, con la
> fecha del commit como prueba de que no lo cambié después.

[`docs/REGLA_SELECCION.md`, `docs/PLAN_MEDICION.md` — congelados antes de medir]

**0:30–0:42 · El resultado**

> Lo medí sobre ochenta y cinco mil expedientes y cincuenta y dos contratos que esas empresas
> ganaron de verdad.
> El agente encontró el sesenta y nueve por ciento. El filtro por código, el ochenta y tres.
>
> La idea era mía y no se sostiene.

[85.769 · 52 · 69,2 % · 82,7 % — `fase5_resultados.md`]

**0:42–0:52 · La causa**

> Y sé por qué. Los dieciséis contratos que se le escaparon son productos que el perfil de la
> empresa no nombraba.
> Una distribuidora de Autodesk que también vendía licencias de Adobe. El agente razonó bien sobre
> una descripción incompleta.

[16 de 16 — `fase5_diagnostico.md` §3]

**0:52–1:00 · Por qué se publica**

> Lo publico igual, con los datos y el comando que lo reproduce.
> Un resultado negativo medido bien vale más que uno bueno sin medir.

---

## Qué se ve mientras

| Tiempo | En pantalla |
|---|---|
| 0:00–0:08 | La lista real de licitaciones de un día, haciendo scroll deprisa |
| 0:08–0:20 | Una ficha del radar: la cita del pliego, su página, el enlace al PDF |
| 0:20–0:30 | `git log` de `REGLA_SELECCION.md`, con la fecha anterior a la medición |
| 0:30–0:42 | La tabla de resultados. **El 69,2 % y el 82,7 % en pantalla a la vez** |
| 0:42–0:52 | Los motivos que escribió el agente: «La empresa es partner de Autodesk, no de Adobe» |
| 0:52–1:00 | La terminal ejecutando `uv run python -m radar.evaluacion --informe` |

## Notas para grabar

- **El giro es el minuto 0:38.** No adelantarlo: el vídeo funciona porque parece que va a acabar
  bien. No poner el resultado en la miniatura ni en el primer fotograma.
- **Decir «no se sostiene» sin adornarlo.** Ni disculpa ni chiste ni «pero». La frase siguiente ya
  levanta el vídeo.
- Sin música que suba al final. Sin superlativos. Sin «increíble», «potente» ni «revolucionario».
- Los números se dicen con letra (sesenta y nueve), se ven con cifra en pantalla.
- Si sobra tiempo al montar, lo primero que se quita es el bloque 0:08–0:20: se entiende igual por
  lo que se ve en pantalla.

## Lo que no se dice, y por qué

- **Nada de las empresas.** Salen como «Empresa A» a «Empresa G», también en las capturas.
- **Nada de lo que no está medido.** Que el radar ahorre tiempo a una persona no está medido
  (M6 sin medir, y no hay cronómetro: `PLAN_MEDICION.md` §7). No se insinúa.
- **No se dice que con mejores perfiles funcionaría.** Es lo que apunta el diagnóstico, pero no
  está medido, y decirlo en un vídeo es justo la forma de vender un resultado negativo como si
  fuera uno bueno aplazado.
