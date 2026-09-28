# Fase 6 — Romperlo

Cerrada el 28-09-2026. La puerta de salida se comprueba con un comando:

```bash
uv run pytest tests/test_fallos.py
```

La fase consiste en coger la matriz de fallos de `docs/SPEC.md` §8, escribir un test por fila y
mirar si el radar hace lo que la matriz dice que hace. **En tres filas no lo hacía.**

## 1. Lo que ha aparecido al romperlo

### 1.1 La ingesta diaria se habría comido su propia copia del feed

`radar/ingesta.py` reutilizaba lo ya descargado buscando por URL, y la primera página del feed
**siempre tiene la misma URL**. A partir del segundo día, la ingesta habría leído del disco el feed
del primer día: cero licitaciones nuevas, sin error, sin aviso y sin nada raro en los registros.

Salió al escribir la fila «PC apagado a las 07:00»: el test pone un feed distinto en la segunda
pasada y el radar seguía viendo el primero.

- **Por qué estaba así:** la reutilización se hizo para no volver a descargar lo que ya bajó la Fase 1,
  que es correcto para las páginas siguientes —su URL lleva identificador y su contenido no cambia— y
  es un error para la primera.
- **Qué daño hizo:** ninguno todavía. La ingesta automática no ha llegado a ejecutarse ningún día
  (`ejecuciones` no tiene ni una fila de tipo `diaria`) y las pasadas manuales de la Fase 2 fueron
  todas el mismo día. Pero la idempotencia que la Fase 2 dio por demostrada se cumplía **en parte por
  el motivo equivocado**: repetir la pasada no duplicaba nada porque ni siquiera volvía a mirar.
- **Arreglo:** la primera página no se reutiliza nunca; las siguientes, sí.

### 1.2 Una sola entrada rota tumbaba la pasada entera

La matriz dice: «la entrada va a cuarentena; el resto continúa». La columna `estado_parseo` con su
valor `cuarentena` existía en la base desde la primera migración, y **no había una sola línea que la
escribiera**. Una entrada con una fecha ilegible levantaba la excepción, se deshacía la transacción y
la pasada terminaba con «La ingesta se ha interrumpido por un fallo no previsto».

La Plataforma publica miles de entradas al día. Una mala, y ese día no se ingiere nada.

- **Arreglo:** cada entrada se procesa en su propio punto de guardado (`SAVEPOINT`). Si falla, se
  deshace solo ella, se guarda en `stg_entradas` con `estado_parseo = 'cuarentena'`, su XML original y
  el motivo, y la pasada sigue. El resumen de la ejecución trae ahora el recuento.

### 1.3 Si el modelo se niega a contestar, la respuesta llegaba vacía

`stop_reason == "refusal"` no estaba contemplado (fila 15 de la matriz). El texto llega vacío y el
nodo que lo pidió habría seguido como si el pliego no dijera nada: exactamente el fallo silencioso que
este proyecto no se permite. Con un pliego es raro, pero un pliego trae nombres, direcciones y a veces
datos personales.

- **Arreglo:** `radar/llm.py` levanta `ModeloSeNiega` con un mensaje que dice que el expediente queda
  para revisar a mano. La llamada queda apuntada igual, porque se pagó.

## 2. La matriz, fila por fila

| # | Fila de `SPEC.md` §8 | Test | Estado |
|---|---|---|---|
| 1 | Sin red | `test_sin_red_no_se_pierde_nada_y_el_cursor_no_avanza` | cubierta |
| 2 | PLACSP caída o lenta | `test_la_plataforma_caida_se_reintenta_tres_veces_y_luego_avisa` + `test_la_espera_entre_intentos_crece` | cubierta |
| 3 | Certificado TLS | `test_un_certificado_que_no_se_puede_verificar_para_el_radar` + `test_nunca_se_desactiva_la_verificacion_de_certificados` | cubierta |
| 4 | Falta la clave de API | `test_sin_clave_de_anthropic_no_se_llama_a_nada` + `test_una_clave_que_no_tiene_forma_de_clave_se_rechaza` | cubierta |
| 5 | Clave inválida o sin saldo | `test_una_clave_rechazada_por_el_modelo_lo_dice_sin_traza` | cubierta |
| 6 | Límite de uso o saturación | `test_si_el_modelo_esta_saturado_no_se_pierde_lo_hecho` | cubierta |
| 7 | Presupuesto agotado | `test_con_el_presupuesto_agotado_no_se_llama_y_se_dice_cuanto` | cubierta |
| 8 | PDF corrupto | `test_un_pdf_danado_manda_ese_expediente_a_revisar_y_el_resto_sigue` + `test_una_pagina_html_de_error_no_se_confunde_con_un_pliego` | cubierta |
| 9 | PDF escaneado | `test_un_pliego_escaneado_se_dice_no_se_adivina` | **parcial**: la rama de OCR (D21) no está construida; el radar lo dice en lugar de callarlo |
| 10 | Pliego en zip o firmado | `test_un_zip_o_un_xsig_no_se_abren_y_se_dice_cual_es` + `test_la_extension_sale_de_los_bytes_no_de_lo_que_se_esperaba` | cubierta |
| 11 | Postgres caído | `test_sin_base_de_datos_se_dice_como_arrancarla` | cubierta |
| 12 | XML del feed malformado | `test_una_entrada_rota_va_a_cuarentena_y_el_resto_se_ingiere` | **arreglada en esta fase** (§1.2) |
| 13 | Doble ejecución el mismo día | `test_lanzar_la_ingesta_dos_veces_no_duplica_nada` | cubierta |
| 14 | Casilla de formulario ilegible | `test_un_pliego_con_casillas_se_reconoce_como_formulario` + `test_no_se_puede_dar_por_bueno_un_requisito_cuya_cita_no_esta_en_la_pagina` | **parcial**: sin la rama de imagen no se puede leer la casilla; lo que sí se garantiza es que no se inventa su valor |
| 15 | El modelo rechaza la petición | `test_si_el_modelo_se_niega_a_contestar_el_expediente_va_a_revisar` + `test_un_triaje_que_el_modelo_no_contesta_no_descarta_la_licitacion` | **arreglada en esta fase** (§1.3) |
| 16 | PC apagado a las 07:00 | `test_si_se_salta_un_dia_la_siguiente_pasada_recupera_desde_el_cursor` | **arreglada en esta fase** (§1.1) |

## 3. Los mensajes, todos y no solo los de la matriz

La segunda mitad de la fase era revisar si los mensajes los entiende alguien que no programa. En
lugar de leerlos una vez y dar el visto bueno, hay un test que los busca solos: recorre el paquete
con el árbol de sintaxis, saca el texto de **cada** excepción del radar y le exige lo mismo a todas.

- Nada de `Traceback`, `Exception`, `psycopg`, `httpx`, `anthropic` ni `None` dentro del mensaje.
- Frase entera: mayúscula al principio y punto al final.
- Nada de «contacta con soporte», «error desconocido» o «inténtalo de nuevo», que no dicen qué hacer.

Pasa sobre los mensajes que hay hoy, y el día que alguien escriba uno con el nombre de una excepción
dentro, se pone rojo sin que nadie tenga que acordarse de mirarlo.

## 4. Lo que sigue sin cubrirse, dicho aquí

- **La rama de OCR** (fila 9). Un pliego escaneado sale como «revisar» con el motivo escrito. Lo que
  falta es mandar sus páginas al modelo como imagen, que es la decisión D21 y no está construida.
- **La casilla del formulario** (fila 14). Sin la rama anterior no hay forma de leer una casilla, así
  que lo único que se puede garantizar hoy es lo que garantiza la verificación de la cita: que el
  radar no se inventa lo que marca. Si el modelo rellenara el valor, la cita no aparecería en la
  página y el requisito se descartaría.

Las dos van al README como límites, que es donde tienen que estar.

## 5. La puerta

- `uv run pytest tests/test_fallos.py` en verde: **25 tests, uno o dos por fila de la matriz**.
- Ningún camino enseña una traza: comprobado a mano en los tests de cada fila, y en automático por el
  test que audita todos los mensajes del paquete.
- Los tres fallos encontrados tienen su test en rojo antes del arreglo, y el commit lo menciona.
