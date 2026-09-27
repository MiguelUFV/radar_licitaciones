# Fase 4 — El triaje y el modelo con el que se hace (D06)

Medido el 27-09-2026. Las cifras salen de la tabla `eval_resultados` y se regeneran sin volver a
pagar nada:

```bash
uv run python -m radar.evaluacion.triaje --solo-medir
```

El diseño del experimento —variantes, muestra, métricas y la regla de decisión— se congeló en
`docs/EXPERIMENTO_TRIAJE.md` **antes** de la primera llamada. El commit que lo introduce es anterior
a este informe y se puede comprobar en el historial de git.

## 1. Qué se ha construido

El primer nodo del grafo: `radar/triaje.py`. Recibe el perfil congelado de una empresa y una o
varias licitaciones tal y como se publicaron en el feed —objeto, órgano, CPV y tipo de contrato— y
dice de cada una si merece la pena abrir el pliego: `si`, `duda` o `no`.

- **El modelo clasifica con una lista cerrada; Python decide** (D09). Lo que no sea una de esas tres
  palabras no se interpreta: esa licitación queda como `revisar` y va a una persona.
- **El triaje no ve quién ganó el contrato**, ni el importe. Lo que se le manda lo arma
  `como_se_ve()`, y hay un test que falla si ahí entra el adjudicatario.
- **El prompt lleva la versión en el nombre** (`radar/prompts/triaje_v1.md`). Cambiarlo es crear
  `triaje_v2.md`; cada llamada guarda la versión y el sha256 de lo que se envió.
- **Repetir no duplica ni vuelve a pagar:** la clave de `triajes` es
  `(licitación, empresa, modelo, agrupamiento, versión del prompt)`.

## 2. La muestra

| | |
|---|---|
| Empresas | las **2 de desarrollo**. Las 5 de test no se han tocado |
| Periodo | licitaciones publicadas del 01-01-2025 al 30-06-2025 |
| Universo del periodo | 120.656 expedientes en 181 días con publicaciones (**666,6 al día**) |
| Contratos ganados | 12 por empresa, **todos** los del periodo |
| No ganados | 88 por empresa, al azar con semilla `20260927` |
| Triajes por variante | 200 |

Los 88 no ganados son **los mismos** para las dos empresas: el sorteo con la semilla saca el mismo
orden y solo se le quitan los contratos que cada una ganó. Eso hace que las dos se midan sobre las
mismas licitaciones —bien para comparar variantes— pero también que sus dos estimaciones de volumen
estén correlacionadas: no son dos muestras independientes.

## 3. El resultado

| Variante | Recall Empresa A | Recall Empresa B | Volumen A | Volumen B | € / 100 licitaciones |
|---|---|---|---|---|---|
| `haiku_lote20` | **100 %** (12/12) | **100 %** (12/12) | 37,9 | 53,0 | **0,0403** |
| `haiku_individual` | 100 % (12/12) | 100 % (12/12) | 7,6 | 53,0 | 0,1845 |
| `opus_lote20` (esfuerzo bajo) | 100 % (12/12) | 100 % (12/12) | 60,6 | 68,2 | 0,1888 |

Volumen en licitaciones por día, estimado con la tasa de paso en los no ganados × 666,6.

**Ninguna de las 600 licitaciones se quedó sin decisión válida** (0 `revisar`), así que la regla del
2 % de `EXPERIMENTO_TRIAJE.md` §5 no descarta ninguna variante. Las tres contestaron siempre con el
JSON que se les pidió y con una referencia por licitación.

### La decisión, aplicando la regla congelada

Los tres recalls son **iguales**: 24 de 24 contratos ganados en las tres variantes. La diferencia es
0 puntos, muy por debajo del umbral de 8 (que es lo que vale un contrato con n=12). Se aplica la
regla 4 —«si dos variantes quedan a menos de 8 puntos, gana la más barata»—. Haiku en lotes de 20 es
la más barata con diferencia: cuesta la cuarta parte que las otras dos. Frente a Opus deja pasar
además menos licitaciones; frente a la variante de una en una, más (§5.2):

> **D06 queda decidido: el triaje se hace con `claude-haiku-4-5`, en lotes de 20 licitaciones por
> llamada.** Opus con esfuerzo bajo no acierta ni un contrato más, deja pasar **un 42 % más** de
> licitaciones (64,4 al día de media frente a 45,5) y cuesta **4,7 veces** más.

## 4. Comparación con el "antes"

Sobre las mismas dos empresas y el mismo periodo, frente a los filtros CPV de la Fase 3:

| | Baseline A (CPV 72/48) | Baseline B (del perfil) | Triaje (`haiku_lote20`) |
|---|---|---|---|
| Recall Empresa A | 100 % | 100 % | 100 % |
| Recall Empresa B | 67 % | 75 % | 100 % |
| **Media (24 contratos)** | **83,3 %** | **87,5 %** | **100 %** |
| Volumen Empresa A | 50 | 243 | 37,9 |
| Volumen Empresa B | 50 | 232 | 53,0 |

Los 4 contratos que el filtro CPV pierde son de Empresa B, y se pierden por lo que dice la tesis: de
sus 12 contratos ganados, solo 8 llevan un CPV de la división 72 o 48. Los otros 4 son servicios de
venta de entradas codificados en otras divisiones, y el triaje los encuentra porque lee el objeto.

**No es una cifra publicable todavía.** Son 2 empresas y 24 contratos, y son las empresas con las
que se ajusta el agente. La cifra del estudio sale en la Fase 5, con las 5 de test.

## 5. Tres cosas que cambian cómo hay que leer esto

### 5.1 Nueve de los 12 contratos de Empresa A nombran un producto suyo en el objeto

Los objetos dicen literalmente el nombre de su software. El triaje los reconoce por el nombre, no
por entender la materia: una búsqueda de texto plano los encontraría igual. Empresa B es el
contraste exacto: **ninguno** de sus 12 lleva marca y el triaje los encontró todos por la materia del
contrato. Está anotado en `docs/SPEC.md` §9 y en la Fase 5 se publicará por empresa, porque sin ese
dato el recall se lee mejor de lo que es.

### 5.2 Agrupar de 20 en 20 no cuesta recall, pero de una en una descarta más

Comparadas licitación a licitación, las dos variantes de Haiku coinciden en **191 de 200**, y las 9
que no coinciden se mueven **siempre en el borde de la duda**: nunca un `si` pasa a `no` ni al
contrario.

| | mismo resultado | se mueve dentro del borde (`duda` ↔ `si`/`no`) | `si` ↔ `no` |
|---|---|---|---|
| Haiku de 20 frente a Haiku de 1 | 191 | 9 | **0** |
| Haiku de 20 frente a Opus de 20 | 192 | 8 | **0** |

Hay algo que la regla congelada no ordenaba y conviene decir: de una en una, Empresa A pasa de 37,9
licitaciones al día a **7,6**, con el mismo recall. Las 4 que en lote quedaban en `duda` se resuelven
como `no` cuando la licitación se mira sola. Es decir, de una en una es **más selectiva**, no más
sensible. La regla decidía por recall y coste, y de una en una cuesta 4,6 veces más porque el perfil
viaja en cada llamada: con la regla escrita, gana el lote. Si en la Fase 5 la precisión (M6) sale
floja, esto es lo primero que hay que volver a probar, y queda escrito aquí para no inventarlo
después.

### 5.3 Triar el día completo de las siete empresas no cabe en el presupuesto diario

Con el coste medido, 0,000403 € por licitación triada:

| | Triajes | Coste |
|---|---|---|
| Una empresa, un día | 667 | **0,27 €** |
| Siete empresas, un día | 4.669 | **1,88 €** |
| Cinco empresas de test, los 181 días del periodo | 603.280 | **243 €** |

El tope diario del proyecto es 2,00 € y el mensual 25,00 €. Consecuencias, por orden:

1. **La Fase 5 no puede triar el universo entero.** Se medirá sobre una muestra estratificada por
   empresa, igual que este experimento: todos los contratos ganados más una muestra al azar del
   resto. El coste baja a céntimos y el recall se mide sobre los mismos 100 % de contratos ganados;
   lo que pierde precisión es el volumen, que pasa a ser una estimación con su margen.
2. **El día a día real (una empresa) sí cabe:** 0,27 € al día, 8 € al mes con el tope actual.
3. **Para varias empresas a la vez haría falta un prefiltro en Python** antes del modelo. Queda
   anotado como trabajo de la Fase 5, no de ahora.

## 6. Lo que costó el experimento

| Variante | Llamadas | Coste |
|---|---|---|
| `haiku_lote20` | 10 | 0,0806 € |
| `haiku_individual` | 200 | 0,3689 € |
| `opus_lote20` | 10 | 0,3776 € |
| **Total** | **220** | **0,8270 €** |

La estimación pesimista previa (tokens de entrada reales, salida al tope) era de 2,47 €; el gasto
real fue menos de la mitad, porque la salida real de un lote de 20 son unas 1.100 fichas y el tope
estaba en 4.400. La estimación se hizo con `count_tokens`, que es gratis, y sin `--gastar` el comando
no llama a nada.

## 7. Lo que queda de la Fase 4

Esto cierra el experimento del modelo de triaje, no la fase. Queda:

- Nodos del pliego: documento → texto/OCR → localizar → extraer con cita y página → verificar la
  cita → evaluar en Python → ficha.
- Checkpointer de Postgres y el grafo de LangGraph que une los nodos.
- Reglas de evaluación versionadas en `radar/reglas/`.
- M5 (citas verificadas) ≥ 98 % en desarrollo, que es la puerta de salida de la fase.
