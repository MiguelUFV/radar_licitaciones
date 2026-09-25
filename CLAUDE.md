# Radar de licitaciones — instrucciones del proyecto

Agente que lee las licitaciones públicas nuevas (Plataforma de Contratación del Sector Público),
abre el pliego de las candidatas y le dice a una empresa a cuáles puede presentarse y por qué,
con la cita y la página que lo justifican.

Documentos de referencia (leer antes de trabajar):
- `docs/SPEC.md` — tesis, alcance, métricas, criterios de éxito, matriz de fallos, límites.
- `docs/ROADMAP.md` — fases, fase activa y criterios de salida.
- `docs/DATOS.md` — trazabilidad del dato de extremo a extremo.
- `docs/DECISIONES.md` — decisiones técnicas tomadas y por qué.
- `docs/ENTORNO.md` — instalación, cuentas y claves.

## Al empezar cada sesión
1. Leer `docs/ROADMAP.md` e identificar la fase activa y su criterio de salida.
2. Trabajar solo en esa fase. Si algo pertenece a otra, anotarlo en el ROADMAP, no hacerlo.
3. Al terminar: marcar lo completado en el ROADMAP y registrar en `docs/DECISIONES.md` cualquier decisión nueva.

## Idioma
Español en código (nombres de funciones y variables incluidos), comentarios, mensajes de error,
commits y documentación. Términos técnicos sin traducción forzada (feed, commit, token).

## Innegociables (operativos)
1. **Medición real.** Toda cifra que se publique sale de `radar/evaluacion/` ejecutable con un comando
   y queda registrada en la tabla `eval_resultados` con `run_id` y commit de git.
2. **Nada ficticio en el camino crítico.** Datos de ejemplo solo en `tests/fixtures/` y `ejemplos/`,
   con la cabecera `DATOS DE EJEMPLO — no usar en producción`. El paquete `radar/` nunca contiene
   registros inventados, valores por defecto que simulen datos ni respuestas simuladas del LLM.
3. **Se tiene que poder romper.** Cada fallo de `docs/SPEC.md` §8 tiene un test y un mensaje en
   español para una persona no técnica. Nunca se muestra una traza al usuario; la traza va al log.
4. **Tests que fallen sin el arreglo.** Bug → primero el test en rojo → se demuestra que falla con el
   arreglo desactivado → arreglo → verde. El commit lo menciona.
5. **Límites escritos.** Todo límite descubierto se añade a `docs/SPEC.md` §9 en el mismo commit.
6. **Interfaz sobria.** Sin emojis, sin superlativos, sin plantillas genéricas.
7. **Coste controlado.** Toda llamada al LLM pasa por `radar/llm.py`, que registra tokens, coste en
   USD y en EUR, y respeta el presupuesto de `.env`. Prohibido llamar al SDK desde otro sitio.

## Reglas técnicas
- Python 3.12 con `uv`. Formato y lint con `ruff`. Tests con `pytest`.
- Los tests no llaman a la API de Anthropic ni a la red: usan fixtures reales grabadas.
- HTTP con `httpx` y certificados de `certifi`. Prohibido `verify=False` (ver DECISIONES D12).
- El LLM extrae; Python decide. Toda extracción lleva cita literal y página, y se verifica que la
  cita aparece en el texto de esa página antes de usarla.
- Los prompts viven en `radar/prompts/`, con versión en el nombre del fichero. Cambiar un prompt es
  crear una versión nueva, no editar la anterior.
- Los ficheros descargados (capa raw) son inmutables y se identifican por su sha256.
- Nada de datos personales de personas físicas en salidas públicas (ver DATOS §7).

## Git
- Rama por fase: `fase-N-nombre`. Commits pequeños, en español, en imperativo.
- Nunca se commitean `.env`, `data/` ni credenciales de n8n.
- Los workflows de n8n se exportan a `n8n/workflows/` y se versionan.
