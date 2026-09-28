# DECISIONES — Qué se eligió, qué se descartó y por qué

Cada decisión dice cuándo hay que revisarla. Las nuevas se añaden al final con el siguiente número.

## D01 · Fuente de datos: sindicación PLACSP 643 (perfiles alojados, sin menores)
- **Descartado:** agregación autonómica (1044) en la v1, contratos menores, scraping de la web, servicios de pago (Apify y similares).
- **Motivo:** es la fuente oficial, abierta y sin clave. Trae el NIF del adjudicatario (la verdad de referencia) y la solvencia en texto (lo que permite medir si el pliego aporta). La agregada no trae solvencia en el feed. Los menores no se licitan de la misma forma.
- **Revisar si:** la Fase 1 muestra que la cobertura de PLACSP es insuficiente para el sector elegido.

## D02 · Sector: servicios TI y consultoría; universo: servicios y suministros
- **Descartado:** todos los sectores; un solo CPV.
- **Motivo:** hay muchas pymes adjudicatarias (suficiente verdad de referencia) y es un sector que se entiende sin explicación. El agente tiene que ver más allá del CPV del sector para poder demostrar que encuentra lo que el filtro pierde. Por eso su universo es más amplio que el del baseline.
- **Revisar si:** el volumen diario del universo hace inviable el coste del triaje (Fase 1).

## D03 · Orquestación: n8n self-hosted en Docker, versión fijada (2.39.8)
- **Descartado:** n8n Cloud (de pago, y tendría que llegar a un servicio de tu PC); `npx n8n` (sin aislamiento, estado disperso).
- **Motivo:** gratis, local, en la misma red de Docker que la API y la base de datos. Versión fijada para que un cambio de n8n no rompa nada sin aviso.
- **Papel de n8n:** programación diaria, llamadas a la API con reintentos, workflow de errores con aviso por correo, envío del informe y, en la Fase 7, recogida de la respuesta del usuario. Es lo que n8n hace mejor, y queda visible en un lienzo que entiende alguien no técnico.
- **Qué NO hace n8n:** parsear CODICE ni decidir. Ese código tiene que tener tests, y en n8n no los tendría.

## D04 · Agente: LangGraph 1.2 con checkpointer de Postgres
- **Descartado:** cadena lineal; bucle de herramientas libre (el modelo decide qué hacer); Claude Agent SDK.
- **Motivo:** el proceso tiene ramas conocidas (escaneado, anexos, verificación con reintento, presupuesto) que se expresan como grafo con estado tipado. El checkpointer guarda el estado tras cada nodo, lo que da trazabilidad y permite reanudar. Cada nodo es una función que se puede probar por separado.
- **Revisar si:** el grafo acaba siendo lineal en la práctica. Si pasa, se dice.

## D05 · Llamadas al modelo: SDK oficial `anthropic` dentro de los nodos; LangChain solo si ahorra código
- **Descartado:** `langchain-anthropic` como cliente principal.
- **Motivo:** el SDK oficial da acceso directo a `usage` (coste exacto), `request_id`, Batch API, caché de prompts, entrada de PDF y salidas estructuradas. Todo pasa por `radar/llm.py`.
- **Sobre LangChain:** en este proyecto aporta poco. Se usará solo si un componente concreto ahorra código (por ejemplo, un divisor de texto). Meterlo por meterlo sería justo el adorno que quieres evitar, y en el README se dirá así.

## D06 · Modelos
- **Extracción de requisitos:** `claude-opus-5`. Un error aquí descarta un contrato que la empresa podía ganar (M3), y el coste por pliego es bajo en términos absolutos.
- **Triaje: `claude-haiku-4-5`, en lotes de 20 licitaciones por llamada.** Decidido el 27-09-2026 con el experimento diseñado en `docs/EXPERIMENTO_TRIAJE.md` y medido en `docs/informes/fase4_triaje.md` (600 triajes reales sobre las dos empresas de desarrollo, 0,83 € de gasto):

| Variante | Recall (24 contratos ganados) | Volumen al día | € por 100 licitaciones |
|---|---|---|---|
| **`haiku_lote20`** | **24/24** | **37,9 y 53,0** | **0,0403** |
| `haiku_individual` | 24/24 | 7,6 y 53,0 | 0,1845 |
| `opus_lote20` (esfuerzo bajo) | 24/24 | 60,6 y 68,2 | 0,1888 |

  Los tres recalls son idénticos, así que se aplica la regla 4 que estaba escrita antes de medir
  («a menos de 8 puntos, gana la más barata»). Opus no acierta ni un contrato más, deja pasar un
  42 % más de licitaciones (64,4 al día de media frente a 45,5) y cuesta 4,7 veces más. Se confirma la expectativa: Haiku basta para
  juzgar relevancia con el objeto y el CPV.
- **Lo que el experimento no zanjó:** de una en una, Empresa A baja de 37,9 a 7,6 licitaciones al día con el mismo recall, es decir, mirar la licitación sola es **más selectivo**. La regla congelada ordenaba por recall y coste, no por volumen, así que gana el lote; si la precisión (M6) sale floja en la Fase 5, esto es lo primero que hay que volver a probar.
- **Estimación orientativa** (precios oficiales a 2026-06-24 en USD/MTok: Opus 5 5/25, Sonnet 5 2/10, Haiku 4.5 1/5; lectura de caché al 10 % de la entrada; 1 USD = 0,8726 € según el BCE del 2026-09-18):

| | Opus 5 | Sonnet 5 | Haiku 4.5 |
|---|---|---|---|
| Triaje, € por 100 licitaciones (400 tokens nuevos + 2.000 en caché + 150 de salida; +200 de razonamiento en Opus y Sonnet) | 1,03 | 0,41 | 0,12 |
| Extracción, € por pliego con texto (8 páginas ≈ 5.600 tokens + 2.500 en caché; 1.000 de salida + 1.500 de razonamiento) | 0,080 | 0,032 | 0,009 |
| Recargo por pliego escaneado (8 páginas como imagen ≈ 16.000 tokens más) | +0,07 | +0,03 | +0,01 |

Ejemplo **hipotético** (300 licitaciones al día en el universo y 10 pliegos leídos; la Fase 1 mide el volumen real):

| Combinación | € al día | Evaluación histórica con Batch API (hipótesis: 20.000 licitaciones y 1.000 pliegos) |
|---|---|---|
| Opus 5 en todo | 3,89 | ≈ 143 € |
| Haiku 4.5 triaje + Opus 5 extracción | 1,15 | ≈ 52 € |
| Sonnet 5 en todo | 1,55 | ≈ 57 € |

- **Riesgo de la estimación:** si el prefijo fijo no llega al mínimo que el modelo necesita para cachear (entre 512 y 4.096 tokens según el modelo), no hay ahorro por caché. Se comprueba en la Fase 1 con `cache_read_input_tokens`.
- **Qué acertó y qué falló de la estimación** (27-09-2026, con el triaje ya medido): la estimación daba 0,12 € por 100 licitaciones con Haiku y han salido **0,0403 €**, tres veces menos, porque agrupar 20 por llamada reparte el perfil entre las 20 y no hizo falta caché. Con Opus daba 1,03 € y han salido **0,1888 €**: la estimación suponía 200 fichas de razonamiento por licitación y con esfuerzo bajo el lote entero gasta unas 800. Las dos estimaciones eran pesimistas, que es como tenían que estar equivocadas.
- **Revisar:** al cerrar la Fase 1 (tokens reales con `count_tokens`, que es gratis) y al cerrar el experimento de la Fase 4.

## D07 · PDF: `pypdf` para el texto; los escaneados, al modelo como PDF
- **Descartado:** PyMuPDF (licencia AGPL, que contaminaría la licencia MIT del repo); Tesseract (instalación en Windows, calidad irregular en castellano, otro sistema que mantener).
- **Motivo:** `pypdf` (BSD) basta para PDF con capa de texto. Para los escaneados se recortan solo las páginas relevantes y se envían al modelo como documento PDF. Así no se paga por procesar el pliego entero como imagen.
- **Revisar si:** en la Fase 1, `pypdf` falla en más del 10 % de los PDF con texto. Alternativa: `pdfplumber` (MIT).

## D08 · Evidencia verificable: salida estructurada con cita y página, verificada en Python
- **Descartado:** la función de citas de la API. No se puede combinar con salidas estructuradas (la API devuelve un error 400).
- **Motivo:** el modelo devuelve `{valor, cita_literal, pagina}` con un esquema estricto. Python comprueba que la cita está, carácter a carácter (con espacios normalizados), en el texto de esa página. Si no está, se reintenta una vez y después pasa a "revisar". Es la defensa principal contra cifras inventadas.

## D09 · El modelo extrae; Python decide
- **Motivo:** "exige 1,5 veces el valor anual medio" es aritmética, no juicio. Las reglas (`radar/reglas/`) son deterministas, versionadas y probadas con casos reales. Así la decisión se puede reproducir y explicar.

## D10 · Base de datos: Postgres 17 (bases separadas para el radar y para n8n)
- **Descartado:** SQLite (escritura concurrente de n8n y de la API; el checkpointer de producción de LangGraph va sobre Postgres); DuckDB (analítica, no transaccional).
- **Motivo:** un solo motor para los datos, los checkpoints y el estado de n8n. Se consulta con SQL y pandas.

## D11 · Servicio Python: FastAPI; n8n lo llama por HTTP
- **Descartado:** nodos Code o Execute Command de n8n ejecutando Python.
- **Motivo:** frontera limpia y comprobable: n8n no sabe cómo se decide, solo qué endpoint llamar. La API tiene tests.

## D12 · HTTP: `httpx` + `certifi`; prohibido `verify=False`
- **Hallazgo del 2026-09-19:** `contrataciondelsectorpublico.gob.es` presenta una cadena de la FNMT ("AC RAIZ FNMT-RCM SERVIDORES SEGUROS"). El Python de esta máquina falla con `urllib` y su configuración por defecto, pero con `certifi` o `truststore` valida bien. Node (n8n) valida sin problemas.
- **Motivo:** desactivar la verificación sería un agujero de seguridad disfrazado de arreglo.

## D13 · Entorno: Python 3.12, uv, ruff, pytest, GitHub Actions
- **Motivo:** 3.12 ya está instalado y lo soportan todas las dependencias (LangGraph 1.2.11, anthropic 1.7.0, langgraph-checkpoint-postgres 3.1.2, FastAPI 0.141, pypdf 6.19). `uv` fija las versiones con un fichero de bloqueo.

## D14 · Notificación: correo SMTP desde n8n con una cuenta Gmail dedicada
- **Descartado:** Slack y Telegram. Añaden una cuenta más y el usuario real (un gerente de pyme) vive en el correo.
- **Motivo:** es el canal real del usuario, es gratis y n8n lo trae de serie.

## D15 · Observabilidad: tablas propias, sin LangSmith
- **Motivo:** una cuenta menos y ningún dato fuera. Lo importante para ti (coste, trazas, decisiones) queda en Postgres, consultable con SQL y reproducible.
- **Revisar si:** depurar el grafo sin una interfaz de trazas se vuelve lento en la Fase 4 (LangSmith tiene plan gratuito).

## D16 · Evaluación histórica con Batch API
- **Motivo:** reduce el coste un 50 % y no necesita respuesta inmediata. Los resultados se guardan por `custom_id`, nunca por posición.

## D17 · Planificación: `docs/` en el repo, no `.planning/` de GSD
- **Motivo:** una sola fuente de verdad que viaja con el código y se lee en GitHub. Si quieres usar los comandos GSD, `/gsd-import` puede importar estos documentos.

## D18 · Despliegue: local; VPS opcional en la Fase 8
- **Motivo:** coste cero mientras se desarrolla y se mide. La ingesta con cursor recupera los días con el PC apagado. Límite escrito en SPEC §9.

## D19 · Tipo de cambio: BCE vía Frankfurter, guardado por fecha
- **Motivo:** fuente pública, sin clave. Cada euro calculado se remonta a su tipo de cambio.

## D22 · El n8n del proyecto vive en el puerto 5679; el 5678 queda para la instalación propia
- **Situación (25-09-2026):** Miguel ya tenía n8n instalado con npm (versión 2.11.4, cuenta creada y
  39 MB de datos en `~/.n8n`). El contenedor del proyecto ocupaba el mismo puerto y le impedía
  arrancarlo.
- **Decisión:** el contenedor se publica en el 5679, con `N8N_EDITOR_BASE_URL` y `WEBHOOK_URL`
  apuntando a ese puerto para que las URL de los webhooks sean correctas. Las dos instalaciones
  funcionan a la vez.
- **Descartado:** usar la instalación propia para el proyecto (versión más antigua, datos en SQLite
  fuera del proyecto, hay que arrancarla a mano y el entorno deja de ser reproducible en otra
  máquina); y quedarse solo con la de Docker (obligaría a parar el contenedor para usar la suya).
- **Coste de la decisión:** una cuenta local más, la del n8n del proyecto.

## D21 · Las páginas con requisitos se envían al modelo como imagen, no solo como texto
- **Hallazgo del 24-09-2026** (pliego real de la AEMET, 39 páginas): el PCAP es un formulario con
  casillas marcadas. El PDF no tiene campos de formulario (están aplanados) y la extracción de texto
  pierde las marcas: se lee "Disponer de la Norma ISO 9001" tanto si está exigida como si no. En ese
  pliego la ISO 14001 está exigida y la ISO 9001 no, y por el texto plano parecería lo contrario.
- **Decisión:** el texto sirve para localizar las páginas relevantes (que es gratis). La lectura de
  requisitos se hace sobre la **imagen** de esas páginas, que sí muestra las casillas.
- **Descartado:** fiarse solo del texto (produciría exclusiones falsas, que es justo la métrica M3);
  leer el pliego entero como imagen (coste desproporcionado).
- **Consecuencia de coste:** cada página como imagen cuesta del orden de 2.000 tokens de entrada. Si
  se leen entre 3 y 6 páginas por pliego, el coste por pliego sube por encima de la estimación de
  D06. Se vuelve a estimar en la Fase 1 con páginas reales.
- **Consecuencia en la verificación:** la cita literal se sigue comprobando contra el texto de la
  página, pero el valor de la casilla no se puede verificar así. Para los requisitos que dependan de
  una casilla, la decisión guarda también el recorte de imagen como evidencia.
- **Revisar si:** la Fase 1 encuentra que una parte relevante de los pliegos sí trae campos de
  formulario legibles, en cuyo caso se leen directamente y sale gratis.

## D20 · Repositorio privado hasta la Fase 8, correo `noreply`, licencia MIT
- **Motivo:** se publica cuando haya cifras medidas y se haya revisado el historial en busca de secretos. MIT es compatible con todas las dependencias elegidas (por eso se descartó PyMuPDF).

## D23 · El cursor de la ingesta solo avanza si la pasada llegó hasta lo ya conocido
- **Hallazgo del 25-09-2026**, auditando la ingesta antes de seguir: el cursor se movía a la entrada
  más reciente al terminar, aunque la pasada se hubiera quedado sin páginas. Todo lo que quedaba por
  debajo (y era posterior al cursor anterior) no se volvía a leer nunca. Demostrado con un test: 1
  licitación ingerida de 3.
- **Decisión:** el cursor significa "todo lo posterior a esta fecha está ingerido", y solo puede
  afirmar más si la pasada alcanzó lo ya conocido o el final del feed. Si se queda corta, no se mueve
  y la ejecución queda con un aviso; la siguiente vuelve a empezar por arriba.
- **Caso de la primera pasada:** sin cursor previo no hay nada que alcanzar, así que nunca se
  completaría. La primera deja el punto en la entrada **más antigua** leída, que es lo único que se
  puede garantizar. Lo anterior a esa fecha entra con la carga histórica (Fase 3), no con la diaria.
- **Descartado:** dejar el cursor en lo más antiguo siempre (perdería el hueco entre pasadas cortas
  sin avisar, que es el fallo original con otro disfraz).
- **Revisar si:** la carga histórica cambia la forma de recorrer el feed.

## D24 · Las fechas del feed se comparan como instantes, nunca como texto
- **Motivo:** el feed trae `2026-09-23T21:10:08.435+02:00`. Dos veces al año conviven +02:00 y
  +01:00 y el orden alfabético deja de ser el orden real: el 25-10-2026, una entrada de las 02:30
  (+01:00) es media hora **posterior** a otra de las 03:00 (+02:00), pero como texto parece anterior.
  Con la comparación de texto, esa entrada se descartaba por "ya conocida" y se perdía.
- **Decisión:** `feed.momento()` convierte a `datetime` y todas las comparaciones del cursor usan
  instantes. La columna de la base ya era `TIMESTAMPTZ`.

## D25 · El aviso de fallo lo escribe n8n directamente en Postgres, no a través del agente
- **Motivo:** el fallo más probable es que el agente no responda (contenedor parado, PC ocupado). Un
  aviso que pasara por el agente no llegaría justo cuando hace falta.
- **Decisión:** el workflow `radar_errores` (disparador de error) escribe en la tabla `incidencias`
  con una credencial de Postgres propia de n8n. El mensaje se guarda enmarcado en español, con el
  texto original de n8n como detalle técnico.
- **Verificado el 25-09-2026:** con el contenedor del agente parado, el fallo quedó registrado —
  workflow, ejecución, paso y mensaje— sin intervención.
- **Pendiente:** el aviso por correo necesita la contraseña de aplicación de Gmail, que se crea en la
  Fase 7 junto con el correo diario. Hasta entonces, las incidencias se consultan en la tabla.

## D26 · Los pliegos se bajan solo para las candidatas, con tope por pasada
- **Motivo:** el feed referencia 5.438 documentos para 1.493 licitaciones. Bajarlos todos serían
  varios gigas de PDF para leer cuatro páginas de unos pocos.
- **Decisión:** se baja el PCAP de las licitaciones vigentes, no anuladas y con CPV de informática
  (72 o 48), con un tope por ejecución (20 al día). Un documento que falla vuelve a la cola hasta 3
  intentos; uno ilegible (zip, firmado, dañado) no se reintenta, porque no va a cambiar.
- **Provisional:** el filtro por CPV está aquí para acotar el gasto, no es la regla de selección. La
  regla de verdad se escribe y se congela en la Fase 3.

## D27 · Los tests que tocan la base de datos usan una base aparte (`radar_test`)
- **Motivo:** los tests necesitan insertar filas para provocar situaciones (un hueco en el cursor,
  una baja, un pliego ilegible). Hacerlo en la base de trabajo metería datos de prueba entre los
  reales, que es justo lo que prohíbe el innegociable 2.
- **Decisión:** la fixture `bd` crea `radar_test` si no existe, aplica las migraciones y vacía las
  tablas antes de cada test. Si no hay PostgreSQL levantado, esos tests se saltan solos y la
  integración continua sigue funcionando.

## D28 · El histórico se carga desde los zip mensuales, no paginando el feed hacia atrás
- **Comprobado el 25-09-2026:** la Plataforma publica un zip por mes en la misma ruta de sindicación
  (`..._202501.zip`, 139,6 MB, `application/zip`, ~94 ficheros .atom dentro). La Fase 1 lo había
  dejado como incógnita y el plan B era paginar miles de veces hacia atrás.
- **Decisión:** la carga histórica va mes a mes desde esos zip. Es reanudable: lo ya cargado se salta
  y lo ya descargado no se vuelve a pedir.
- **Lo que cuesta:** unos 137 MB y 4 minutos por mes (el servidor va a 0,6 MB/s y no admite descargas
  por rango, así que cada mes se baja entero). Un mes trae unas 46.000 entradas y 20.000
  adjudicaciones.
- **De los meses posteriores al periodo de estudio solo se guarda quién ganó** los expedientes de ese
  periodo. Sin ese filtro habría que cargar 20 meses enteros: más de 3 horas y millones de filas que
  no se usan para nada.
- **Del histórico no se copia el XML a la base:** se guarda el puntero (zip + fichero .atom +
  posición) y `radar.historico.entrada_original()` lo recupera del zip cuando hace falta. Son
  cientos de miles de entradas y el zip es inmutable.
- **Fragilidad conocida:** una descarga de 4 minutos no sobrevive a que el portátil se duerma. Pasó
  el 25-09-2026: la carga se quedó colgada con la ejecución abierta. La espera sin recibir un byte
  bajó de 900 a 120 segundos, y la carga se relanza con el mismo comando y sigue donde estaba.

## D29 · Dos filtros de referencia en lugar de uno, los dos calculados
- El razonamiento completo y las cifras que lo motivan están en `docs/BASELINE.md` (apartados 1 a 3 y
  el registro de cambios). Resumen: con un filtro único derivado del perfil salían 218 códigos,
  incluida la división 50 entera (reparación de barcos y ascensores) porque el perfil decía
  "mantenimiento". Midiendo a igual volumen, un rival así no distingue nada.
- **Decisión:** Baseline A (divisiones CPV 72 y 48, lo que usa cualquiera) y Baseline B (derivado del
  perfil, deliberadamente ancho). Ningún paso a mano en ninguno de los dos. **Se publican las dos
  cifras**, aunque una deje al radar en peor lugar.
- **Revisar si:** el Baseline B resulta tan ancho que deja pasar casi todo; entonces se dirá en el
  informe y la comparación buena será la del A.

## D30 · Las métricas se calculan con la versión del expediente que estaba publicada
- **Motivo:** un expediente cambia de versión cada vez que cambia de estado, y la última puede traer
  datos que solo se supieron al adjudicar (hasta el CPV puede cambiar). Medir con la última versión
  le daría al filtro información que no pudo tener mientras el plazo estaba abierto.
- **Decisión:** M1 y M2 se calculan sobre la **versión más antigua** de cada expediente.
- **Comprobado con un test de control negativo:** midiendo con la última versión, el filtro se apunta
  un contrato que se publicó como obra y solo apareció como informática al adjudicarse.

## D31 · Solo se descarga de los dominios de la Plataforma, y con tope de tamaño
- **Hallazgo del 26-09-2026**, auditando seguridad: las URL de los documentos salen del feed, y en
  el feed publica cualquier organismo. El radar pedía esa URL tal cual y seguía redirecciones a
  ciegas. Un anuncio manipulado podía hacer que pidiera direcciones de la red interna del ordenador
  que lo ejecuta (`http://127.0.0.1:8000/…`, el router, un servicio de metadatos). Comprobado con un
  test: antes del arreglo, la petición a `127.0.0.1` se hacía.
- **Decisión:** solo se descarga de `contrataciondelestado.es` y `contrataciondelsectorpublico.gob.es`
  (o subdominios). Las redirecciones se siguen **a mano**, comprobando el dominio en cada salto, con
  un máximo de cinco: una redirección a `127.0.0.1` no se puede pedir "y luego mirar".
- **Tope de tamaño:** 400 MB por defecto (los zip mensuales pesan unos 200) y 60 MB para un
  documento. Sin tope, un fichero enorme llenaba la memoria del proceso antes de poder mirar qué era.
- **Verificado** después del cambio con descargas reales: dos pliegos y una página del feed de 9,9 MB.

## D32 · La API de n8n se queda apagada salvo para publicar un workflow
- **El problema:** la clave de la API se pegó en un chat el 25-09-2026 y no se va a rotar. Una clave
  filtrada no se puede "desfiltrar": lo único que se puede hacer es quitarle valor.
- **Decisión:** `N8N_PUBLIC_API_DISABLED=true` por defecto. Con la API apagada, n8n responde 401
  **tanto si mandas la clave como si no**, así que la clave no abre nada. Para publicar un workflow
  se enciende un momento y se vuelve a apagar (los pasos salen impresos si lo intentas con la API
  apagada, y están en `docs/ENTORNO.md` §11).
- **Lo que no cambia:** los procesos programados siguen funcionando igual, porque los dispara n8n por
  dentro. Verificado: los dos workflows siguen activos con la API apagada.
- **Riesgo que queda:** la clave sigue siendo válida y sigue existiendo en el registro de la
  conversación, que no está en esta máquina. Se ha borrado de la transcripción local (17 trozos). Si
  algún día se enciende la API y se deja encendida, el riesgo vuelve.
- **Lo correcto sigue siendo rotarla.** Esto es lo segundo mejor.

## D33 · El tipo de cambio va en `.env` hasta que se pueda descargar
- **Motivo:** el coste en euros es una cifra que se publica, así que no puede salir de un número
  puesto a mano sin fuente. La fuente elegida es `api.frankfurter.app`, que publica los tipos del BCE
  (docs/DATOS.md §2).
- **Estado:** `radar/red.py` solo descarga de los dominios de la Plataforma (D31), así que bajar el
  tipo de cambio requiere añadir ese dominio a la lista. Hasta entonces se usa
  `TIPO_CAMBIO_USD_EUR` de `.env`, con su fuente y su fecha escritas al lado, y cada llamada al
  modelo guarda **qué cambio usó y de dónde salía** (columnas `tipo_cambio` y `tipo_cambio_origen`).
- **Decisión:** `radar/llm.py` busca primero el cambio del día en la tabla `tipos_cambio` y solo usa
  el de `.env` si no está. Así, cuando se añada la descarga, el código no cambia.
- **Pendiente de la Fase 4:** añadir `api.frankfurter.app` a los dominios permitidos y guardar la
  respuesta original en la capa raw, como cualquier otro dato descargado.

## D34 · Las páginas del pliego se eligen buscando el ancla y leyendo hacia delante
- **El problema:** un PCAP tiene entre 13 y 112 páginas y los requisitos viven en dos o tres.
  Mandarlo entero al modelo cuesta diez veces más y además lo despista.
- **Dos intentos que salieron mal, los dos vistos con pliegos reales:**
  1. *«Las seis primeras páginas que coincidan con algún patrón»*: el patrón de certificaciones (ISO)
     aparece en el índice y en 20 páginas del apartado técnico, así que en un pliego de 112 páginas
     se llevaba las páginas 1 a 7 y **la solvencia estaba en la 54**.
  2. *«El tramo de seis páginas con más puntos en total»*: seis páginas mediocres seguidas suman más
     que la sección de solvencia de dos páginas.
- **Decisión:** se puntúa cada página (sección de solvencia 3, requisito del núcleo 2, otro requisito
  1, cifra en euros 1, índice −3), se toma la de más puntos como **ancla** y se leen esa y las
  siguientes hasta 6, quitando las del final que no aporten nada. Es lo que hace una persona:
  encuentra el encabezado y sigue leyendo.
- **Medición (36 pliegos descargados, 27-09-2026):** las tres reglas aciertan lo mismo (14 de los 15
  pliegos donde se puede comprobar que la página con el requisito y su cifra entra en la ventana),
  pero el ancla manda **141 páginas en lugar de 182**. Leer solo 4 hacia delante acertaba igual y
  bajaba a 103; no se hace porque el criterio solo se puede comprobar en 15 de los 36 pliegos y no se
  recorta contexto para ahorrar sobre una medición que no cubre el caso. Queda como palanca de coste
  para la Fase 5.
- **Revisar si:** M4 (exactitud de la extracción) sale flojo, que sería el síntoma de que la ventana
  se queda corta.

## D35 · El «remite al Anexo N» se sigue una vez, y solo si el anexo trae cifras
- **Lo que pasa de verdad:** en la mayoría de los pliegos leídos, la cláusula de solvencia no dice
  los requisitos: dice «los exigidos son los del Anexo Nº 1». Sin seguir ese salto, casi todos los
  expedientes acabarían en «revisar» teniendo el dato a veinte páginas. Es la rama `ANX` que ya
  estaba dibujada en `docs/SPEC.md` §4.
- **Decisión:** si de la primera lectura sale algún requisito de tipo `remite` y **ninguna cifra**, se
  busca ese anexo en el mismo documento y se lee. Un solo salto: si el anexo remite a otro sitio, se
  para y va a una persona.
- **Y el anexo solo cuenta si la página trae una cifra en euros.** La primera versión se llevaba la
  otra mención del mismo anexo en otra cláusula, pagaba una segunda llamada y devolvía los mismos
  requisitos genéricos. Comprobado con un pliego real de 86 páginas: **0,06 € por nada**. Si ninguna
  página nombra el anexo con una cifra dentro, el anexo va en otro fichero del expediente y se dice
  así, sin gastar.
- **Consecuencia de coste:** un pliego son una o dos llamadas, nunca más.

## D36 · Una llamada pagada nunca se queda sin apuntar
- **El fallo, del 27-09-2026:** el grafo pasó a `radar/llm.py` un `run_id` que no era un
  identificador. La llamada a Opus 5 se hizo, se pagó, y el `INSERT` en `llm_llamadas` falló
  **después**. Resultado: gasto real que el presupuesto del día no veía, que es justo lo que el
  innegociable 7 existe para evitar.
- **Decisión, en dos partes:**
  1. Los identificadores se comprueban **antes** de llamar al modelo, así que un error de programa
     no cuesta dinero.
  2. Si la fila completa no entra, se apunta una fila con lo imprescindible (nodo, modelo, tokens,
     coste, cambio) y se avisa con un error legible. La cuenta no se pierde nunca; el fallo se ve.
- **Cómo se demuestra:** dos tests en `tests/test_llm.py`, los dos en rojo antes del arreglo.

## D37 · El correo sale de la cuenta personal, con contraseña de aplicación
- **Lo que decía ENTORNO §6:** una cuenta de Gmail nueva y dedicada al radar, para que un descuido
  con esa contraseña no tocara la cuenta personal.
- **Lo que pasó el 28-09-2026:** Google no dejó crear la cuenta. Puede ser el teléfono ya usado en
  otras altas, el CAPTCHA o la detección de automatización; el motivo exacto no se sabe.
- **Decisión:** se usa la cuenta personal con una **contraseña de aplicación**, que no es la
  contraseña de la cuenta y se revoca por separado desde `myaccount.google.com/apppasswords`.
- **Por qué es aceptable:** la contraseña vive cifrada dentro de n8n, en el ordenador de casa, con la
  API de n8n apagada (D32); es revocable en un clic sin cambiar la contraseña de la cuenta; y los
  correos van a esa misma dirección de todas formas.
- **El riesgo que queda, escrito:** una contraseña de aplicación da acceso al buzón por IMAP y SMTP,
  no solo a enviar. Si se filtrara, hay que revocarla **y** revisar la actividad de la cuenta. Con
  una cuenta dedicada el daño se habría quedado en un buzón vacío.
- **Alternativas descartadas:** otra cuenta de Google (es lo que acaba de fallar); un servicio de
  envío como Brevo o Resend (otro registro y otra dependencia para una prueba de cinco días); el
  correo de la universidad (SMTP cerrado en la mayoría de las instalaciones institucionales).
- **Cómo se deshace:** si algún día hay cuenta dedicada, se cambia la credencial en n8n y las dos
  direcciones de `.env`. No hay que tocar código.

## D38 · Los clientes van en su propia tabla, no en la del estudio
- **El problema:** el radar tiene que servir a empresas de verdad, que se dan de alta cuando
  quieren y editan su ficha cuando quieren. La tabla `perfiles` no puede hacer eso: cada fila
  lleva la semilla del sorteo y el sha256 de la regla con la que se eligió esa empresa, y su
  perfil está bajo candado para que nadie lo cambie después de publicar una medición.
- **Decisión:** tabla `clientes` aparte (`sql/migraciones/011`). El estudio y el producto no
  comparten fila. Si la compartieran, una empresa dada de alta hoy parecería un sujeto del
  estudio y el estudio dejaría de demostrar nada.
- **Lo que sí comparten:** el formato del texto que lee el modelo. `clientes.como_lo_lee_el_modelo()`
  genera los mismos apartados que tienen los perfiles congelados, así que el prompt de triaje no
  tiene que distinguir de dónde viene lo que lee, y una empresa nueva se tría exactamente igual
  que una del estudio.
- **Trazabilidad:** `triajes` guarda ahora `perfil_sha256`. Un cliente edita su ficha cuando
  quiere; sin esa columna no se podría explicar por qué el radar descartó algo hace tres semanas.

## D39 · El formulario pregunta por separado lo que la Fase 5 demostró que falta
- **El dato:** de los 20 contratos que el radar dejó escapar en la medición, **19 eran productos
  que el perfil de la empresa no mencionaba** (`docs/informes/fase5_diagnostico.md` §3). El techo
  del radar no es el modelo: es lo poco que sabe de la empresa.
- **Por qué no vale una caja de texto libre:** nadie escribe de sí mismo lo que no cree
  importante. Una distribuidora describe lo que fabrica, no las marcas que revende, y ahí estaban
  los contratos perdidos.
- **Decisión:** el formulario pregunta suelto, con un ejemplo real al lado, y tres campos llevan
  escrito por qué se preguntan: **las marcas que distribuye**, **lo que hace aunque no sea su
  bandera** y **lo que no hace**. El último permite descartar con motivo en lugar de por silencio.
- **Queda por comprobar:** que esto de verdad sube el recall. No se puede medir con las empresas
  del estudio, porque sus perfiles están congelados y volver a escribirlos invalidaría la Fase 5.
  Haría falta un segundo estudio con empresas nuevas de las 12 que cumplen la regla y no se usaron.

## D40 · El alias deja de ser una clave foránea a `perfiles`, y pasa a un disparador
- **El fallo, del 28-09-2026:** `triajes.alias`, `lecturas.alias` y `fichas.alias` apuntaban con
  una clave foránea a `perfiles`, la tabla del estudio. Una empresa dada de alta por el formulario
  nunca está ahí (D38), así que la base rechazaba su primera fila: *«Key (alias)=(Empresa del
  Norte) is not present in table "perfiles"»*. El formulario le prometía que entraba en el aviso
  diario y era mentira: el radar no podía ni triarla.
- **Lo que se descartó:** meter a los clientes en `perfiles`. Es lo que menos código cambia y lo
  peor que se podía hacer: una fila de cliente parecería un sujeto del estudio, y el estudio
  dejaría de demostrar nada.
- **Decisión:** las tres claves foráneas se sustituyen por un disparador que exige que el alias
  sea de alguien —de un cliente o del estudio—. PostgreSQL no permite una clave foránea a la unión
  de dos tablas, pero la comprobación sigue **en la base** y no solo en el código, por lo mismo
  que la de datos personales (007): el día que alguien inserte por otro camino, la base lo para.
- **Y un segundo disparador** impide que un cliente se llame como una empresa del estudio. Si
  coincidieran, el cliente leería en su correo decisiones que no son suyas, y las cifras
  publicadas se mezclarían con el trabajo diario de un cliente.
- **Dónde vive ahora la pregunta «de quién es este alias»:** en `radar/empresas.py`, un solo
  sitio. El candado de la huella está dentro, y es el mismo para los dos: en el estudio porque
  cambiar el texto obliga a volver a medir, en un cliente porque una decisión tiene que poder
  explicarse con el texto exacto que la produjo. Lo que solo consulta —componer el correo de la
  mañana— no lo exige: las decisiones ya están tomadas, y un perfil sin congelar no puede dejar a
  un cliente sin su aviso.

## D41 · El tope diario es de cada cliente, y se gasta triando antes que leyendo
- **El problema:** leer un pliego cuesta dinero de verdad (0,083 € el percentil 90 de lo medido).
  Con varias empresas, alguien tiene que decidir cuántos pliegos se abren al día y con qué
  criterio, y no puede ser una constante escrita en el código.
- **Decisión:** cada empresa pone su tope en el formulario de alta y el trabajo diario se corta
  por ahí, empresa a empresa. Por encima sigue el tope global del `.env`, que protege al radar
  entero (`radar/llm.py`).
- **El orden del gasto:** primero triar todo lo nuevo, después leer pliegos. Si el tope se agota,
  se agota leyendo: quedarse sin triar es no haber mirado una licitación que quizá era la buena,
  mientras que quedarse sin leer solo deja un pliego para mañana. Es el mismo criterio que
  `docs/PLAN_MEDICION.md` §4 usó para ordenar el gasto de la medición.
- **La reserva antes de abrir un pliego sale de lo medido**, no de una cifra inventada: el
  percentil 90 del coste de los pliegos ya leídos, y el percentil y no la media porque tiene que
  cubrir uno caro. Mientras no haya ninguno leído se usa el 0,070 €/pliego de la Fase 4.

## D42 · Cada análisis de un pliego empieza de cero, aunque haya estado guardado
- **El fallo, del 28-09-2026:** el `thread_id` del checkpointer es `licitacion:empresa:reglas`.
  Al volver a leer el mismo pliego —lo que pasa cuando la vez anterior se cortó, que es
  justamente para lo que está el checkpointer— el grafo reanudaba aquel estado y `nodo_extraer`
  **sumaba** los requisitos nuevos a los viejos. La ficha salía con el mismo requisito repetido
  una vez por lectura y el correo decía «de 4 requisitos leídos del pliego: 4 cumplen» de un
  pliego que tenía uno. Se vio en la prueba de extremo a extremo: la misma prueba daba 3
  requisitos, y a la siguiente 4.
- **Decisión:** `analizar()` pone `lecturas`, `saltos` y `motivos` a cero en cada invocación.
- **Lo que se pierde:** reanudar una lectura cortada a la mitad sin volver a pagarla. **Lo que
  se gana:** que no se repita nunca un requisito. Repetir una extracción cuesta unos céntimos y
  solo pasa si el proceso se cayó; una ficha con el mismo requisito cuatro veces la lee el
  cliente. El paso a paso se sigue guardando, que es para lo que está (D04).
- **En los tests:** las tablas del checkpointer no son del radar y las migraciones no las tocan,
  así que la fixture `bd` las vacía también. Si no, el estado de un test entra en el siguiente.

## D43 · El día del radar es el día en España, en Python y en SQL
- **El fallo, del 29-09-2026:** la base corre en UTC (`Etc/UTC` dentro de Docker) y el radar
  trabaja en hora española. Entre medianoche y las dos de la mañana no están en el mismo día: a
  las 00:26 en Madrid, `date.today()` de Python decía 29-09 y `current_date` de la base decía
  28-09. Se vio solo porque la fecha cambió a mitad de sesión y **cuatro pruebas se pusieron en
  rojo sin que nadie hubiera tocado nada**.
- **Por qué importa, y no es cosmético:** el tope diario de cada cliente se calcula sumando lo
  que ha gastado «hoy». Con los dos relojes en días distintos, `gastado_hoy` devolvía cero euros
  con el tope recién agotado, así que **un cliente podía gastarse su tope dos veces** con solo
  lanzar el trabajo de madrugada. El mismo desfase dejaba el correo de la mañana sin las fichas
  del día y colaba en el triaje licitaciones con el plazo ya vencido.
- **Decisión:** una sola definición de «hoy», en `radar/fechas.py`. `hoy()` para Python y
  `el_dia("columna")` para las consultas, que envuelve la columna en `AT TIME ZONE
  'Europe/Madrid'`. La misma zona que ya usaba el reloj de n8n.
- **Dónde se aplica:** el gasto por empresa (`radar/empresas.py`), el presupuesto global
  (`radar/llm.py`), el correo del día, el plazo de presentación en el trabajo diario y el estado.
  Los intervalos relativos —«ejecuciones de hace más de dos horas», «incidencias de los últimos
  siete días»— se quedan como estaban: no comparan días.
- **Lo que enseña:** la prueba que lo cazó no la escribió nadie. La escribió el calendario. Por
  eso ahora hay una que fija la hora a mano (22:30 UTC = 00:30 en Madrid) y no depende de cuándo
  se ejecute.

## D44 · Se completa el histórico de 2024 y se vuelve a medir
- **El hallazgo, del 29-09-2026:** el universo del estudio son los expedientes cuya **primera**
  publicación cae en el primer semestre de 2025, y el histórico empezaba en 2025-01. Un
  expediente publicado en octubre de 2024 y actualizado en marzo de 2025 parecía publicado por
  primera vez en marzo de 2025 y entraba en el universo sin deberlo. El detalle completo está en
  `docs/HALLAZGO_UNIVERSO.md`.
- **Lo que se descartó:** deshacer la carga de 2024 y quedarse con las cifras publicadas. Es
  elegir a sabiendas un dato peor para no tener que tocar nada, y el error seguiría ahí, solo que
  invisible. También se descartó publicar los dos juegos de cifras: un informe con dos verdades
  se lee peor y protege al autor más que al lector.
- **Decisión:** se completa la carga de 2024 y **se vuelve a medir todo lo que dependa del
  universo**, que es lo que este proyecto hace siempre que cambia algo de lo que salen las
  cifras. El recálculo no cuesta dinero: los triajes están guardados y solo cambia qué
  expedientes cuentan.
- **Lo que esto no es:** un cambio de criterio. La definición del universo no se toca; lo que se
  arregla es el dato con el que se aplicaba. Por eso los documentos congelados no se reescriben:
  llevan una entrada en su apartado **Cambios** diciendo que sus cifras se midieron con el
  histórico incompleto, y la medición nueva va en los informes.
- **Lo que enseña:** el aviso no salió de ninguna revisión, salió de un candado escrito el mismo
  día para otra cosa (`radar.diagnostico` compara el universo de ahora con la `n` guardada en
  `eval_resultados`). Sin él, la carga habría cambiado las cifras en silencio y el informe habría
  seguido diciendo 120.656. Merece la pena escribir candados aunque parezcan de más.
