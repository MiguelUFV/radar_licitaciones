# ROADMAP — Radar de licitaciones

Una sesión son unas 2–3 horas de trabajo con Claude Code. Total estimado: 14–18 sesiones.
Ninguna fase empieza sin que la anterior cumpla su criterio de salida.

**Fase activa: 4** (0, 1, 2 y 3 cerradas; informes en `docs/informes/`)

| Fase | Objetivo | Sesiones | Puerta de salida |
|---|---|---|---|
| 0 | Entorno, cuentas y repositorio | 1 | ✔ Cerrada el 25-09-2026: diagnóstico en verde |
| 1 | Medir los datos reales (go / no-go) | 1–2 | ✔ Cerrada el 25-09-2026: **GO**, las tres puertas cumplidas |
| 2 | Ingesta con trazabilidad | 2 | ✔ Cerrada el 25-09-2026: ingesta diaria idempotente desde n8n |
| 3 | Verdad de referencia y baseline (el "antes") | 1–2 | ✔ Cerrada el 27-09-2026: recall del filtro CPV **79,7 %** |
| 4 | Agente LangGraph v1 | 3 | Grafo completo con desarrollo; modelo de triaje decidido |
| 5 | Medición (el "después") | 2 | Informe M1–M8 reproducible con un comando |
| 6 | Romperlo | 1–2 | Matriz de fallos: un test por fila, en verde |
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

- [ ] `radar/llm.py`: única puerta al SDK de Anthropic; registra uso, coste y `request_id`; aplica el presupuesto
- [ ] Nodos: triaje → documento → texto/OCR → localizar → extraer (cita y página) → verificar cita → evaluar (Python) → ficha
- [ ] Checkpointer de Postgres: cada paso del grafo queda guardado
- [ ] Reglas de evaluación versionadas (`radar/reglas/`), probadas con casos reales
- [ ] **Experimento del modelo de triaje:** Opus 5 (esfuerzo bajo) frente a Haiku 4.5, sobre las empresas de desarrollo. Se elige por M1 y coste; queda en DECISIONES D06
- [ ] Ajuste de prompts SOLO con las empresas de desarrollo

**Puerta:** el grafo recorre todas sus ramas con fixtures reales y M5 ≥ 98 % en desarrollo.

## Fase 5 — Medición (el "después")

- [ ] Ejecución sobre el periodo de test con Batch API (50 % más barato), con un presupuesto fijado de antemano
- [ ] M1–M5 y M8 automáticos; intervalos de confianza por bootstrap
- [ ] M6: tú etiquetas a ciegas una mezcla (agente, baseline, ambos); la herramienta oculta de dónde viene cada caso
- [ ] M7: recuento automático del trabajo evitado (páginas por licitación, documentos abiertos, saltos entre documentos)
- [ ] M7b (opcional, solo si se hizo antes de la Fase 4): minutos cronometrados a mano frente a con el radar
- [ ] `uv run python -m radar.evaluacion --informe` regenera el informe sin volver a llamar a la API
- [ ] Informe `docs/informes/fase5_resultados.md`, que dice "sostenida / refutada / no concluyente"

**Puerta:** otra persona clona el repo, restaura los datos y obtiene las mismas cifras.

## Fase 6 — Romperlo

- [ ] Un test por fila de la matriz de fallos (SPEC §8)
- [ ] Cada mensaje revisado: ¿lo entiende alguien no técnico?
- [ ] Demostración de que cada test falla sin su arreglo (anotada en el commit)

**Puerta:** `pytest tests/test_fallos.py` en verde y ningún camino muestra una traza al usuario.

## Fase 7 — Interfaz: correo y ficha

- [ ] Contraseña de aplicación de Gmail y credencial SMTP en n8n (la creas tú, ENTORNO §6)
- [ ] Nodo de correo en `radar_errores`: el aviso de fallo sale de la tabla `incidencias` (viene de la Fase 2, decisión D25)
- [ ] Correo diario: resumen del día (N revisadas, N en la lista, coste del día) y una línea por licitación
- [ ] Ficha HTML por licitación: requisitos, decisión, cita con página y enlace al PDF original
- [ ] Diseño sobrio (tipografía, jerarquía, sin adornos); revisión con el skill `frontend-design`
- [ ] (Opcional) Botones "me presento / no me presento" → webhook de n8n → tabla `feedback_usuario`

**Puerta:** correo real recibido durante 5 días laborables seguidos.

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
