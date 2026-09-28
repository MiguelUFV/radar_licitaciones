# ROADMAP — Radar de licitaciones

Una sesión son unas 2–3 horas de trabajo con Claude Code. Total estimado: 14–18 sesiones.
Ninguna fase empieza sin que la anterior cumpla su criterio de salida.

**Fase activa: 7** (0 a 6 cerradas; informes en `docs/informes/`)

**Resultado de la Fase 5: la tesis principal queda REFUTADA** frente al baseline derivado
del perfil (−14,3 puntos, IC [−26,0, −3,9]) y no concluyente frente al filtro CPV 72/48
(−7,8 puntos, IC [−23,4, +7,8]). La causa está medida: 19 de los 20 contratos perdidos son
productos que el perfil de la empresa no menciona. Ver `docs/informes/fase5_diagnostico.md`.

| Fase | Objetivo | Sesiones | Puerta de salida |
|---|---|---|---|
| 0 | Entorno, cuentas y repositorio | 1 | ✔ Cerrada el 25-09-2026: diagnóstico en verde |
| 1 | Medir los datos reales (go / no-go) | 1–2 | ✔ Cerrada el 25-09-2026: **GO**, las tres puertas cumplidas |
| 2 | Ingesta con trazabilidad | 2 | ✔ Cerrada el 25-09-2026: ingesta diaria idempotente desde n8n |
| 3 | Verdad de referencia y baseline (el "antes") | 1–2 | ✔ Cerrada el 27-09-2026: recall del filtro CPV **79,7 %** |
| 4 | Agente LangGraph v1 | 3 | ✔ Cerrada el 27-09-2026: **M5 = 100 %** (62/62) y D06 decidido |
| 5 | Medición (el "después") | 2 | ✔ Cerrada el 28-09-2026: tesis **refutada**, informe reproducible |
| 6 | Romperlo | 1–2 | ✔ Cerrada el 28-09-2026: 25 tests, **3 fallos reales encontrados** |
| 7 | Interfaz: correo y ficha | 1–2 | Correo diario real recibido |
| 8 | Publicación | 1 | Repo público, README con límites, vídeo |

---

## Fase 0 — Entorno, cuentas y repositorio

**Tú:** crear la cuenta y la clave de Anthropic con límite de gasto, crear la contraseña de
aplicación de Gmail, crear el usuario propietario de n8n y su clave de API. Instrucciones en
`docs/ENTORNO.md`.
**Claude:** `pyproject.toml`, `docker-compose.yml`, CI de GitHub Actions, script de diagnóstico.

- [ ] Carpeta del proyecto sin espacios (opcional, recomendado) — ENTORNO §1
- [ ] Repositorio privado en GitHub con correo `noreply` — ENTORNO §2
- [ ] Clave de Anthropic en un workspace propio con límite mensual — ENTORNO §3
- [ ] `.env` completo a partir de `.env.example` — ENTORNO §4
- [ ] `docker compose up -d`: Postgres y n8n en marcha — ENTORNO §5
- [ ] n8n: propietario, clave de API, credencial SMTP — ENTORNO §6
- [ ] Claude Code conectado a n8n por MCP — ENTORNO §7
- [ ] Plugin context-mode reparado o desactivado — ENTORNO §9
- [ ] `uv run python -m radar.diagnostico` comprueba red, TLS de PLACSP, clave, Postgres y n8n, con un mensaje legible por cada fallo
- [ ] CI (ruff + pytest) en verde en GitHub

**Puerta:** el diagnóstico sale en verde y, con la clave quitada del `.env`, muestra el mensaje en
español, no una traza.

## Fase 1 — Medir los datos reales (go / no-go)

Lo más arriesgado va primero: si los datos no sostienen la tesis, se sabe antes de construir.

- [ ] Volumen diario real: expedientes nuevos (primera aparición en estado PUB) por día, en total y en el universo de servicios y suministros
- [ ] % de expedientes ADJ/RES con NIF de adjudicatario
- [ ] % con solvencia en el feed, % con cifras, % que remiten al pliego (con una muestra ≥ 2.000, no una sola página)
- [ ] Descargar 100 PCAP al azar: % descargables, % con capa de texto, páginas (mediana y p90), formatos (PDF, zip, xsig)
- [ ] % de PCAP donde la sección de solvencia se localiza por palabras clave
- [ ] % de PCAP que son formularios con casillas, cuántos conservan campos de formulario legibles, y cuántas páginas por pliego hay que leer como imagen (afecta al coste: decisión D21)
- [ ] Inventario de tipos de requisito que aparecen de verdad (volumen de negocio, trabajos similares, certificaciones, clasificación, habilitación, adscripción de medios) y con qué frecuencia
- [ ] Confirmar la URL de los ficheros zip mensuales históricos (o el plan B: paginar el feed hacia atrás)
- [ ] Tokens reales de 20 pliegos con `count_tokens` (gratis) → coste estimado por pliego y por día
- [ ] Espacio en disco necesario para 2025 + 2026
- [ ] Informe `docs/informes/fase1_datos.md`, con cada cifra reproducible por un script

**Puerta GO** (se cumplen las tres):
1. ≥ 80 % de los expedientes ADJ/RES traen el NIF del adjudicatario.
2. ≥ 70 % de los PCAP se descargan y se leen (con texto o por la rama OCR).
3. En ≥ 50 % de los expedientes la solvencia con cifras no está en el feed.

**Si falla 1 o 2:** no hay verdad de referencia o no hay material que leer. Se replantea la fuente.
**Si falla 3:** la tesis se debilita. Se reformula ("el feed basta en X % de los casos; el pliego
solo hace falta en el resto") y se mide igualmente. Es un resultado publicable.

## Fase 2 — Ingesta con trazabilidad

- [x] Esquema Postgres por capas (`sql/migraciones/`), según `docs/DATOS.md`
- [x] Descarga del feed con cursor: sigue `rel="next"` hasta el último punto procesado (D23, D24)
- [x] Capa raw: cada fichero con sha256; nunca se sobrescribe. La extensión sale de los bytes
- [x] Parser CODICE → staging → core (licitaciones, lotes, documentos, adjudicaciones)
- [x] Tratamiento de `deleted-entry` (tabla `bajas`; la vista dice si el expediente está anulado)
- [x] Descarga de PCAP con reintentos; el documento queda ligado a su expediente y a su sha256 (D26)
- [x] API FastAPI: `/salud`, `/ingesta`, `/pliegos`, `/resumen/hoy`
- [x] Workflow n8n `radar_diario` v1: 07:00 → `/ingesta` → `/pliegos`; `radar_errores` registra el
      fallo en la tabla `incidencias`. **El aviso por correo pasa a la Fase 7**: necesita la
      credencial de Gmail (D25)
- [x] Tests con entradas reales del feed guardadas como fixtures

**Puerta (cumplida el 25-09-2026):** dos pasadas seguidas no crean duplicados (test
`test_repetir_la_pasada_completa_no_duplica_nada`, y comprobado con las 1.493 licitaciones reales), y
cualquier fila de `licitaciones` se remonta a su fichero raw (test + consulta en el informe).

## Fase 3 — Verdad de referencia y baseline (el "antes")

- [x] Escribir y commitear la **regla de selección de empresas** ANTES de aplicarla → `docs/REGLA_SELECCION.md`, congelada el 25-09-2026
- [x] Carga histórica: 20 meses (ene-2025 a ago-2026) desde los zip mensuales (D28). 122.945 expedientes, 218.062 adjudicaciones
- [x] Aplicar la regla: hecho el 26-09-2026. De 35.129 adjudicatarios, 19 cumplen; sorteadas 2 de desarrollo y 5 de test con semilla 20260925
- [x] Perfiles: escritos por el modelo desde fuentes públicas, sin mirar contratos (cambio del 27-09 en la regla). Congelados con hash en `docs/perfiles_congelados.md`
- [x] Cifra de negocio: cinco en intervalos (se usa el extremo inferior), dos sin localizar y fuera de M3
- [x] Filtro CPV baseline: **dos** filtros, los dos calculados (D29) → `docs/BASELINE.md` y `radar/baseline.py`
- [x] Medir M1 y M2 del baseline → hecho: 79,7 % (A) y 87,3 % (B). Informe en `docs/informes/fase3_baseline.md`

**Puerta (cumplida el 27-09-2026):** baseline medido; regla, procedimiento y perfiles congelados en git antes de escribir una línea del agente, y el orden de los commits lo demuestra.

## Fase 4 — Agente LangGraph v1

- [x] `radar/llm.py`: única puerta al SDK de Anthropic; registra uso, coste y `request_id`; aplica el presupuesto **antes** de llamar
- [x] Nodo de **triaje** (`radar/triaje.py`), con el prompt versionado en `radar/prompts/triaje_v1.md`
- [x] Resto de nodos: documento → localizar → extraer (cita y página) → verificar cita → anexo → evaluar (Python) → ficha. **La rama de OCR no está hecha**: un pliego escaneado sale como «revisar» diciendo que es una imagen
- [x] Checkpointer de Postgres: cada paso del grafo queda guardado (`PostgresSaver`, una licitación reanuda por su `thread_id`)
- [x] Reglas de evaluación versionadas (`radar/reglas/v1.py`), probadas con casos reales
- [x] **Experimento del modelo de triaje:** hecho el 27-09-2026. Diseño congelado en `docs/EXPERIMENTO_TRIAJE.md` antes de medir; 600 triajes reales por 0,83 €. Los tres recalls empatan (24/24), así que gana el más barato: **Haiku 4.5 en lotes de 20** (D06). Informe en `docs/informes/fase4_triaje.md`
- [ ] Ajuste de prompts: **no se ha hecho.** Los dos van por su primera versión (`triaje_v1`,
      `extraccion_v1`) y con eso ya se cumple la puerta, así que ajustarlos habría sido tocar lo que
      funciona sin una medición que lo pidiera. Se hará si M4 o M6 lo piden en la Fase 5

**Puerta (cumplida el 27-09-2026):** M5 = **100 %** (62 de 62 extracciones con la cita comprobada en
la página que dijo el modelo), el grafo recorre sus cuatro ramas y el coste por pliego es de 0,070 €.
Informe en `docs/informes/fase4_agente.md`. Lo que **no** se consigue todavía: ninguna ficha llega a
«puede presentarse», por falta de datos de la empresa y de dos reglas más, y está medido por qué.

## Fase 5 — Medición (el "después")

- [ ] **Descargar los otros documentos del expediente, no solo el PCAP.** Es lo que más frena el
      resultado útil: la cláusula de solvencia remite a un anexo que muchas veces va en otro fichero
      (informe de la Fase 4 §9)
- [ ] **Reglas v2**, con lo observado en la Fase 4 y deliberadamente no cambiado sobre la marcha:
      `adscripcion` no debería forzar «revisar»; falta un tipo para los requisitos económicos que no
      son un volumen (ratios, seguro de responsabilidad civil); y un veredicto intermedio del tipo
      «cumple lo económico, quedan N cosas por comprobar». Se deciden con M6, no antes
- [ ] Ejecución sobre el periodo de test con Batch API (50 % más barato), con un presupuesto fijado de antemano
- [x] M1, M2, M5, M7 y M8 automáticos, con intervalo por bootstrap pareado (`radar/evaluacion/agente.py`, `radar/evaluacion/trabajo.py`). **Medición a medias:** el tope diario cortó la tanda con 40 de los 77 contratos triados; se reanuda con el mismo comando
- [x] M1 y M2 completos: 517 triajes, los 77 contratos ganados de las cinco empresas de test
- [ ] M6: tú etiquetas a ciegas una mezcla (agente, baseline, ambos); la herramienta oculta de dónde viene cada caso
- [x] M7: **10,87 veces menos páginas** (4,7 señaladas frente a 51,5 del pliego) y un documento abierto en lugar de 4,3
- [ ] M7b (opcional, solo si se hizo antes de la Fase 4): minutos cronometrados a mano frente a con el radar
- [x] `uv run python -m radar.evaluacion --informe` regenera el informe sin volver a llamar a la API
- [x] Informe `docs/informes/fase5_resultados.md`, generado por el comando y no a mano. Con la medición a medias dice **no concluyente** frente a los dos baselines
- [ ] M3: leer los pliegos de los contratos ganados de las empresas de test (unos 5,4 €)

**Puerta:** otra persona clona el repo, restaura los datos y obtiene las mismas cifras.

## Fase 6 — Romperlo

- [x] Un test por fila de la matriz de fallos (SPEC §8): `tests/test_fallos.py`, 25 tests
- [x] Cada mensaje revisado, y en automático: un test recorre el paquete con el árbol de sintaxis y
      le exige a **todas** las excepciones del radar castellano, frase entera y ninguna tripa dentro
- [x] Demostración de que cada test falla sin su arreglo, anotada en el commit

**Tres fallos reales encontrados al romperlo** (informe en `docs/informes/fase6_fallos.md`):

1. **La ingesta diaria se habría comido su propia copia del feed.** La primera página tiene siempre
   la misma URL y se reutilizaba del disco: del segundo día en adelante, cero licitaciones nuevas,
   sin error y sin aviso.
2. **Una sola entrada rota tumbaba la pasada entera.** La columna `cuarentena` existía desde la
   primera migración y no había una línea que la escribiera.
3. **`stop_reason == "refusal"` no estaba contemplado**: el texto llegaba vacío y el nodo seguía como
   si el pliego no dijera nada.

**Puerta (cumplida el 28-09-2026):** `uv run pytest tests/test_fallos.py` en verde y ningún camino
muestra una traza al usuario.

## Fase 7 — Interfaz: correo y ficha

- [ ] **Contraseña de aplicación de Gmail y credencial SMTP en n8n (la creas tú, ENTORNO §6).**
      Es lo único que bloquea la fase. Son 16 letras minúsculas en cuatro grupos; la contraseña de
      la cuenta de Google no sirve
- [x] Nodo de correo en `radar_errores`: el aviso sale del texto ya guardado en `incidencias`, y
      **después** de guardarlo, para que un fallo del correo no se lleve el aviso por delante (D25)
- [x] Correo diario: `radar/correo.py` y `GET /correo/hoy`. El agente lo compone y n8n lo envía
- [x] Ficha HTML por licitación: `radar/ficha.py`, con la cita, su página y el enlace al PDF
- [x] Diseño sobrio, con el skill `frontend-design`: dos tipografías para dos voces (el pliego y el
      radar), la página a la izquierda de una regla vertical, y el color marcando la comprobación y
      no la decisión
- [ ] (Opcional) Botones "me presento / no me presento" → webhook de n8n → tabla `feedback_usuario`.
      **No se hace de momento:** con la tesis refutada hay cosas más útiles antes

**Puerta:** correo real recibido durante 5 días laborables seguidos. Informe del estado en
`docs/informes/fase7_interfaz.md`.

## Fase 8 — Publicación

- [ ] README: qué hace, cifras medidas con enlace a su origen, coste real, límites (desde SPEC §9)
- [ ] Empresas anonimizadas (Empresa A–E) en todo lo público
- [ ] Revisión de secretos en el historial (gitleaks) antes de hacer público el repo
- [ ] Licencia MIT; atribución a la fuente de datos
- [ ] Guion y grabación del vídeo de 60 s
- [ ] Post de LinkedIn con la tesis, el resultado (sea cual sea) y el enlace
- [ ] (Opcional) Despliegue en un VPS para que funcione sin tu PC

---

## Cambios fuera de fase (backlog)

_Vacío._
