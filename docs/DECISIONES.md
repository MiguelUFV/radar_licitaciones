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
- **Triaje:** se decide con el **experimento de la Fase 4**: `claude-opus-5` con esfuerzo bajo frente a `claude-haiku-4-5`, sobre las empresas de desarrollo, por M1 y coste. Mi expectativa es que Haiku baste para juzgar relevancia con título y CPV, pero decide el dato. También se prueba agrupar unas 20 licitaciones por llamada.
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
