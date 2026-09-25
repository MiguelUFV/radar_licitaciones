# DOMINIO — Qué es una licitación pública y qué es un pliego

Explicación del mundo en el que trabaja el proyecto, con un caso real descargado el 24-09-2026.
Si algún día dudas de un término, empieza por aquí.

## 1. El mundo en cinco frases

1. Las administraciones (ayuntamientos, ministerios, hospitales, universidades, empresas públicas)
   compran cosas: servicios informáticos, limpieza, obras, traducciones, auditorías.
2. Como el dinero es público, no pueden llamar a quien quieran: la ley obliga a publicar lo que van a
   comprar y a dejar que se presente cualquiera que cumpla unos requisitos.
3. Ese anuncio público es una **licitación**: un concurso para conseguir un contrato.
4. Las empresas que se presentan son **licitadores**. La que gana es el **adjudicatario**.
5. Todo se publica en un sitio único, la **Plataforma de Contratación del Sector Público** (PLACSP),
   que además lo reparte en datos abiertos. De ahí sale la materia prima del proyecto.

## 2. Quién es quién

| Papel | Quién es | En el ejemplo |
|---|---|---|
| Órgano de contratación | El organismo que compra y firma | Agencia Estatal de Meteorología (AEMET) |
| Licitador | Empresa que se presenta | Cualquier consultora de informática |
| Mesa de contratación | El comité que abre las ofertas y las valora | Funcionarios de la AEMET |
| Adjudicatario | Quien gana | Se publica con su NIF: es la verdad de referencia del proyecto |

## 3. Los documentos: qué es un pliego

**El pliego son las bases del concurso.** Como las bases de una beca o de unas oposiciones: dicen
quién puede presentarse, qué hay que entregar, cuándo, y cómo se decide quién gana. Son de
obligado cumplimiento para las dos partes; si el pliego dice algo, eso es lo que vale.

Vienen en dos documentos, y casi siempre en PDF:

| Documento | Nombre completo | Qué contiene | Por qué importa aquí |
|---|---|---|---|
| **PCAP** | Pliego de Cláusulas Administrativas Particulares | Las reglas del juego: requisitos para poder presentarse (solvencia), plazos, cómo se puntúan las ofertas, penalizaciones, forma de pago | **Es el documento que decide si puedes presentarte.** Es el que lee el agente |
| **PPT** | Pliego de Prescripciones Técnicas | El trabajo en sí: qué hay que hacer, con qué medios, qué niveles de servicio | Sirve para decidir si te interesa, no si puedes |
| Anexos | — | Modelos de declaración, plantillas de oferta | A veces esconden el dato clave |

Dentro del PCAP suele haber un **cuadro resumen** al principio: una tabla con apartados (A, B, C…)
donde están los datos que de verdad se consultan. De ahí vienen frases como "ver apartado G del
cuadro resumen del PCAP", que aparecen constantemente en los datos.

## 4. Cómo transcurre una licitación

1. **Publicación.** El órgano publica el anuncio y cuelga los pliegos. Estado `PUB`.
2. **Plazo de presentación.** Las empresas preparan la oferta y la envían antes de la fecha límite.
   Suelen ser de 15 a 35 días naturales. Si se pasa el plazo, no hay nada que hacer.
3. **Evaluación.** La mesa abre y valora las ofertas. Estado `EV`.
4. **Adjudicación.** Se elige ganador y se publica con su NIF y el importe. Estado `ADJ`.
5. **Formalización.** Se firma el contrato. Estado `RES` (resuelta).

Cada uno de esos cambios genera una actualización en el feed de datos abiertos. Por eso el proyecto
guarda versiones: una misma licitación aparece varias veces a lo largo de su vida.

## 5. Solvencia: la palabra que lo explica todo

**Solvencia es el listón de entrada.** El órgano de contratación no quiere adjudicar un contrato de
200.000 € a una empresa que factura 20.000 € al año y no podría ejecutarlo. Así que exige demostrar
un tamaño y una experiencia mínimos. Hay dos tipos:

- **Solvencia económica y financiera:** normalmente, facturación mínima anual (el "volumen anual de
  negocios") de alguno de los tres últimos ejercicios.
- **Solvencia técnica o profesional:** trabajos parecidos ejecutados en los últimos años, titulaciones
  del equipo, certificaciones.

La ley (Ley de Contratos del Sector Público) pone un tope: la facturación exigida no puede pasar de
**1,5 veces el valor estimado del contrato** (o el valor anual medio, si dura más de un año). Por eso
el requisito casi nunca viene como un número redondo: viene como una fórmula, y hay que calcularlo.

Si no llegas al listón, **no puedes presentarte**. No es que tengas menos posibilidades: es que tu
oferta se excluye sin mirarla. De ahí que este dato decida el día de trabajo de quien busca concursos.

Matiz importante: la ley permite **integrar la solvencia con medios externos** (apoyarte en otra
empresa) o presentarte en **UTE** (unión temporal con otra empresa). Por eso el proyecto declara ese
límite: una empresa pequeña puede acabar ganando un contrato que "no le tocaba" por tamaño.

## 6. El caso real (descargado el 24-09-2026)

| Campo | Valor |
|---|---|
| Objeto | Servicio de soporte técnico a la gestión del entorno de ofimática y puesto de trabajo digital |
| Órgano | Agencia Estatal de Meteorología |
| Expediente | 202600000075 |
| CPV | 72253200 (servicios de apoyo a sistemas) |
| Presupuesto base sin IVA | 208.453,69 € |
| Valor estimado (con prórrogas) | 416.907,37 € |
| Pliego administrativo | PDF de 39 páginas, las 39 con texto |

**Lo que dice el feed de datos abiertos sobre la solvencia:**

> "Se presentará la Declaración Responsable conforme al Anexo III del Pliego Administrativo, sobre
> adscripción de medios… Se presentará el Documento Europeo Único de Contratación debidamente
> cumplimentado…"

Es decir: papeleo. Ni un número.

**Lo que dice el pliego, en su página 6:**

> "a) Volumen anual de negocios referido al mejor ejercicio dentro de los tres últimos disponibles…
> por importe mínimo **312.680,53 €**."
> "…el volumen de negocios anual del licitador deberá ser al menos una vez y media el valor estimado
> del contrato cuando su duración no sea superior a un año."

De dónde sale ese número: el contrato dura más de un año (valor estimado 416.907,37 € repartido en
dos anualidades), así que la anualidad media es 208.453,69 € y el listón es 1,5 × esa anualidad =
312.680,53 €. En el pliego está marcada precisamente esa opción, no la de "1,5 × valor estimado".
Por eso el requisito hay que **calcularlo**, no copiarlo.

**La consecuencia, que es la tesis del proyecto:** una consultora que facture 250.000 € al año no
puede presentarse a este contrato. Pero eso no está en el título, ni en el CPV, ni en el importe, ni
en el feed. Está en la página 6 de un PDF de 39 páginas. Para saberlo hay que abrirlo y leerlo, una
por una, todos los días.

## 5 bis. La facturación es solo una de las puertas

En ese mismo pliego hay seis requisitos que deciden si puedes presentarte, repartidos por el
documento. Todos comprobados en el PDF real:

| # | Requisito | Valor en este pliego | Página |
|---|---|---|---|
| 1 | Volumen anual de negocios | 312.680,53 € mínimo | 6 |
| 2 | Seguro de responsabilidad civil | No exigido (casilla vacía) | 6 |
| 3 | Trabajos similares: importe mínimo anual acumulado en el mejor de los 3 últimos años | 145.917,58 € (70 % de la anualidad media) en servicios del mismo CPV de tres dígitos (722) | 7 |
| 4 | Personal técnico con titulación mínima como solvencia | No exigido (tabla vacía) | 7 |
| 5 | Certificación de gestión ambiental | **ISO 14001 exigida** | 11 |
| 6 | Certificación de calidad ISO 9001 | **No exigida** | 11 |
| 7 | Habilitación empresarial especial | Ninguna | 11 |
| 8 | Compromiso de adscripción de medios | Obligatorio, es obligación esencial del contrato | 5 |
| 9 | Lotes | No hay división en lotes | 2 |

Fíjate en el 5 y el 6: exigen la certificación ambiental y no la de calidad, que es lo contrario de
lo que uno esperaría. Una pyme sin ISO 14001 queda fuera de este contrato aunque facture de sobra.
Ese tipo de detalle es el que no se puede adivinar.

## 5 ter. El problema técnico de verdad: las casillas

El pliego es un formulario. Cada requisito lleva delante una casilla marcada o vacía, y **el texto
que se extrae del PDF no conserva esa marca**: se lee "Disponer de la Norma ISO 9001" tanto si está
exigida como si no. Comprobado en este pliego: no tiene campos de formulario (están aplanados) y las
marcas se pierden al extraer el texto.

Consecuencia de diseño, registrada como decisión D21: en las páginas donde hay requisitos, el
modelo tiene que **ver la página**, no solo leer su texto. La imagen de la página 6 muestra con
claridad qué casillas están marcadas; el texto plano, no. Esto encarece el análisis y se mide en la
Fase 1.

## 7. Qué hace el radar con este caso, paso a paso

1. Ve la licitación en el feed: título, órgano, CPV 72253200, 208.453,69 €, fecha límite.
2. **Triaje:** ¿encaja con lo que hace esta empresa? Soporte de puesto de trabajo, sí. Sigue.
3. Descarga el PCAP (39 páginas) y le saca el texto.
4. Localiza la sección de solvencia por palabras clave, sin gastar modelo en las 39 páginas.
5. Extrae el requisito con su cita literal y su página: 312.680,53 €, página 6.
6. Comprueba que esa frase está de verdad en la página 6. Si no está, no se usa.
7. **Decide en Python:** el perfil declara 250.000 € de facturación. 250.000 < 312.680,53 → **no apta**.
8. En el correo aparece: "AEMET · Soporte de puesto de trabajo digital · 208.453,69 € · No apta:
   exige 312.680,53 € de volumen anual de negocios (PCAP, página 6); tu perfil declara 250.000 €."

Quien recibe ese correo tarda cinco segundos en confirmarlo, en vez de veinte minutos en descubrirlo.

## 8. Vocabulario mínimo

| Palabra | Significado corto |
|---|---|
| Licitación | Concurso público para conseguir un contrato |
| Pliego | Las bases del concurso |
| PCAP | El pliego con las reglas: solvencia, plazos, puntuación |
| PPT | El pliego con el trabajo a realizar |
| Cuadro resumen | Tabla del principio del PCAP con los datos clave por apartados |
| Solvencia | Listón mínimo de facturación y experiencia para poder presentarse |
| CPV | Código europeo que clasifica el objeto del contrato |
| Lote | Parte de un contrato a la que se puede optar por separado |
| Adjudicatario | La empresa que gana |
| Valor estimado | Lo que puede llegar a costar el contrato con prórrogas y modificaciones |
| UTE | Unión temporal de dos o más empresas para presentarse juntas |
| DEUC | Formulario europeo en el que declaras que cumples los requisitos |
| LCSP | Ley de Contratos del Sector Público, la norma que regula todo esto |

## 8 bis. Receta para revisar una licitación a mano

Es el proceso que el radar automatiza. Sirve para cualquier licitación.

1. **Abre la ficha** de la licitación en la Plataforma. Mira cuatro cosas: objeto, importe sin IVA,
   fecha límite de presentación y CPV.
2. **Descarga el pliego administrativo (PCAP)**, en la sección de documentos de la ficha. Es el que
   manda; el técnico (PPT) dice qué hay que hacer, no quién puede presentarse.
3. **Busca dentro del PDF (Ctrl+F), en este orden:**
   `solvencia` · `volumen anual de negocios` · `anual acumulado` · `ISO` · `clasificación` ·
   `adscribir`.
4. **Apunta qué exige y en qué página.** Si aparece una fórmula ("una vez y media el valor anual
   medio"), calcúlala con el importe de la ficha.
5. **Compara con el perfil de la empresa**, requisito por requisito. Basta con fallar uno para
   quedar fuera.
6. **Si el dato no está o el requisito no es una cifra** (por ejemplo, "experiencia en SQL Server"),
   la respuesta correcta es "revisar", no una suposición.

Dónde suele esconderse el dato, por orden de frecuencia: en el cuadro de características del
principio; en un anexo al final (el pliego remite con un "ver apartado 11 del Anexo I"); en el
anuncio de licitación, fuera del PDF; y a veces solo en una casilla marcada.

## 8 ter. Tres casos reales resueltos el 24-09-2026

Perfil usado: consultora de 6 personas, 280.000 € de facturación, 95.000 € en trabajos similares,
con ISO 9001 y sin ISO 14001.

| Licitación | Qué exige | Dónde estaba | Resultado |
|---|---|---|---|
| Autoridad Portuaria de Sevilla, gestión de tráfico marítimo, 475.000 € | 475.000 € de facturación, 475.000 € en trabajos similares, ISO 14001 | Páginas 20 y 35 de 69 | **No puede presentarse**, por tres motivos |
| Madrid Destino, mantenimiento de sus webs, 131.000 € | Cifra de negocios de los 3 últimos años: el pliego no dice cuánto | La cláusula de la página 10 remite al Anexo I (página 55), que remite al anuncio | **Duda**: el dato decisivo no está en el pliego |
| Sareb, herramientas de valoración, 77.600 € | 1,5 veces la anualidad media, 70 % en trabajos similares, y experiencia en SQL Server, SSIS y Azure DevOps | Páginas 6 y 7 de 78 | **Duda**: por tamaño cumple; el requisito técnico no es una cifra |

Lecciones que fijan el diseño del radar: el dato casi nunca está en el anuncio; a veces hay que
seguir dos saltos hasta un anexo; y hay requisitos que no son números, que se marcan para revisión
en lugar de decidirlos.

## 9. Hallazgo técnico del mismo día

Al descargar los pliegos, todas las peticiones devolvían error 500. La causa no era la Plataforma:
las URL vienen dentro de un XML y llevan `&amp;` donde debería ir `&`. Al pedirlas sin convertir, el
servidor recibía un parámetro con nombre inválido. Corregido eso, **19 de 20 pliegos se descargan
bien**, lo que ya supera el umbral que la Fase 1 exige para continuar (70 %).

Queda como caso de la matriz de fallos: un pliego que no se descarga no puede tumbar la ejecución
del día.
