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
4. Cada fase cerrada deja un informe en `docs/informes/faseN_nombre.md`: qué hay funcionando, la
   evidencia de su puerta de salida con la consulta o el comando que la reproduce, y lo que queda fuera.

## Documentos congelados: no se editan
Estos ficheros valen **porque son anteriores a la medición**. Cambiar uno sin más destruye el estudio,
y el orden de los commits es la prueba de que no se cambió:

| Fichero | Qué congela |
|---|---|
| `docs/REGLA_SELECCION.md` | Quién entra en el estudio. Anterior a la carga de datos |
| `docs/BASELINE.md` | Cómo se construye el rival. Anterior a tener perfiles |
| `docs/perfiles_congelados.md` | El sha256 de cada perfil |
| `docs/baselines/empresa_*.md` | El filtro CPV de cada empresa |
| `docs/EXPERIMENTO_TRIAJE.md` | Variantes, muestra y regla de decisión de D06. Anterior a la primera llamada de triaje |
| `docs/PLAN_MEDICION.md` | Muestra, métricas y criterio de la Fase 5. Anterior a mirar un contrato de las empresas de test |
| `docs/METRICA_EFICIENCIA.md` | Definición y regla de decisión de M9 y M10. **Posterior a M1**, y lo dice en su primera línea; anterior a calcularlas |

Si de verdad hay que cambiar uno: se añade una entrada al apartado **Cambios** del propio documento,
con fecha y motivo, y **se vuelve a medir** lo que dependa de él. Nunca se edita el texto original.
Los perfiles tienen además un candado: `radar.perfiles` se para si el texto no coincide con su huella.

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
   El presupuesto se comprueba **antes** de llamar, contando los tokens de entrada con
   `count_tokens` (gratis) y suponiendo la salida al máximo.

## Comandos
```bash
uv run pytest                                  # todo (los que tocan la base se saltan si no hay Postgres)
uv run pytest tests/test_feed.py -k solvencia  # un fichero, o un test por su nombre
uv run ruff format . && uv run ruff check .    # lo mismo que exige la CI
uv run python -m radar.diagnostico             # entorno: .env, TLS de PLACSP, Postgres, n8n, datos personales
uv run python -m radar.estado                  # qué hay cargado y qué necesita atención
```
Los comandos de carga y de consulta están en `docs/ENTORNO.md` §10; publicar workflows, en §11 (la API
de n8n está apagada a propósito, D32).

**Base de datos de pruebas.** Los tests con base de datos usan la fixture `bd` de `tests/conftest.py`,
que crea `radar_test`, aplica las migraciones y vacía las tablas. La base de trabajo (`radar`) nunca
recibe filas de prueba. Las migraciones son ficheros numerados en `sql/migraciones/` y se aplican con
`radar.bd.aplicar_migraciones()`, que las anota para no repetirlas.

Si un test necesita insertar una adjudicación con el DNI en claro (para probar que se limpia o que se
avisa), la base lo rechaza: hay que envolverlo en `como_antes_de_la_restriccion(bd)`, de `conftest`,
que abre la puerta y vuelve a cerrarla al salir.

**`data/` no está en git y no se puede perder: 4,2 GB.** Contiene la capa raw, de la que se reconstruye
toda la base sin volver a descargar nada, y `data/privado/perfiles/`, con los perfiles de las empresas
(identifican a la empresa, por eso no se versionan). Los tests nunca escriben ahí: usan la fixture
`almacen_temporal`.

## Arquitectura
El dato va siempre en la misma dirección, y cada capa solo conoce la anterior:

```
feed/zip de PLACSP → capa raw (fichero + sha256) → stg_entradas → núcleo → agente → evaluación
     radar/red.py      radar/almacen.py         radar/ingesta.py            │      radar/evaluacion/
                                                radar/historico.py          │
                                    triaje → documento → localizar → extraer → decidir → ficha
                                    radar/triaje.py  radar/pliegos.py  radar/localizar.py
                                    radar/extraccion.py  radar/reglas/  radar/grafo.py
```

- **`radar/red.py`** — única puerta a internet. Solo descarga de los dominios de PLACSP, sigue las
  redirecciones a mano comprobando el dominio en cada salto y tiene tope de tamaño (D31).
- **`radar/almacen.py`** — capa raw: el fichero se guarda por su sha256 y no se sobrescribe nunca.
  La extensión sale de los bytes, no de lo que se esperaba.
- **`radar/feed.py`** — parser CODICE/Atom con expresiones regulares (sin parser de XML: así no hay
  entidades externas). Devuelve `Licitacion`, `Lote` y `Baja`. Aquí no se toca la base de datos.
- **`radar/ingesta.py`** — feed diario → base. Idempotente por `(entry_id, entry_updated)`. El cursor
  solo avanza si la pasada alcanzó lo ya conocido (D23); las fechas se comparan como instantes (D24).
- **`radar/historico.py`** — carga hacia atrás desde los zip mensuales, reanudable (D28).
- **`radar/pliegos.py`** — descarga los PCAP de las candidatas, con reintentos y estado por documento.
- **`radar/personas.py`** — un adjudicatario persona física se guarda seudonimizado y sin nombre.
  La restricción está además en la base (`sql/migraciones/007`), no solo en el código.
- **`radar/api.py`** — frontera con n8n. Los errores previstos se traducen en un solo sitio, un
  manejador de `ErrorRadar`, y salen como 503 con mensaje en español.
- **`radar/n8n.py`** — los workflows se definen en código, se publican por la API y se exportan a
  `n8n/workflows/`. No se editan a mano en el lienzo.
- **`radar/triaje.py`** — primer nodo del grafo. El modelo clasifica con una lista cerrada de tres
  decisiones y Python decide (D09); lo que el modelo no contesta queda como `revisar`, nunca se
  descarta en silencio. Los prompts, en `radar/prompts/` con la versión en el nombre del fichero.
- **`radar/localizar.py`** — qué páginas del pliego se leen. Sin modelo: puntúa las páginas, busca
  el ancla y lee hacia delante con tope de 6 (D34). Es el nodo que fija el coste.
- **`radar/extraccion.py`** — el modelo copia los requisitos con su cita y su página, y **Python
  comprueba que esa cita aparece en esa página** antes de usarla. Una cita que no aparece se pide
  otra vez y, si vuelve a fallar, el requisito no se usa. De aquí sale M5.
- **`radar/reglas/`** — la decisión (apta / no apta / revisar), en Python y con versión en el nombre
  del fichero. Solo el volumen de negocios puede descartar una licitación, porque es la única
  comparación de dos números; el resto manda a revisar, nunca descarta.
- **`radar/grafo.py`** — el grafo de LangGraph que une los nodos, con checkpointer de Postgres. Las
  ramas son reales: sin pliego, sin sección de solvencia, el modelo contestando cualquier cosa y el
  salto al anexo al que remite el pliego (D35). Ninguna rama descarta: todas acaban en una ficha con
  el motivo escrito en castellano.
- **`radar/seleccion.py`, `radar/baseline.py`, `radar/evaluacion/`** — el método del estudio. La regla
  y el procedimiento se congelan **antes** de aplicarlos (`docs/REGLA_SELECCION.md`, `docs/BASELINE.md`);
  estos módulos solo los ejecutan y no deciden nada.

**Lo que no se debe romper al tocar esto:** una fila del núcleo siempre se puede remontar a su fichero
raw (`licitaciones → stg_entradas → raw_ficheros`); repetir cualquier carga no duplica nada; y ningún
camino muestra una traza al usuario.

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
- **Todo va a `main`.** La regla original era una rama por fase; con un solo autor y sin nadie que
  revise, la rama solo añadía ceremonia, y las fases 0 a 3 se cerraron directamente en `main`. Se deja
  escrito así para que coincida con lo que hay. Si algún día hay revisión, se vuelve a ramas por fase.
- Commits pequeños, en español, en imperativo. El mensaje dice **qué fallaba y cómo se demostró**, no
  solo qué se cambió: es la única forma de que dentro de un mes se entienda por qué existe un arreglo.
- Nunca se commitean `.env`, `data/` ni credenciales de n8n.
- Los workflows de n8n se exportan a `n8n/workflows/` y se versionan.
