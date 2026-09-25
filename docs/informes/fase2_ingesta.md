# Fase 2 — Ingesta con trazabilidad

Cerrada el 25-09-2026. Todas las cifras salen de la base de datos y se pueden volver a sacar con las
consultas que se indican.

## Qué hay funcionando

| Pieza | Estado |
|---|---|
| Esquema por capas | 3 migraciones aplicadas: raw → staging → núcleo → análisis |
| Ingesta del feed | `POST /ingesta`, idempotente, con cursor que no pierde entradas (D23) |
| Descarga de pliegos | `POST /pliegos`, con reintentos y tope por pasada (D26) |
| Automatización | n8n `radar_diario`, activo, 07:00 de lunes a viernes |
| Aviso de fallo | n8n `radar_errores` → tabla `incidencias` (D25) |
| Tests | 45 en verde; los que tocan la base usan `radar_test` (D27) |

## Lo cargado

Tres páginas del feed, que es lo que se descargó en la Fase 1 y se reutiliza sin volver a pedirlo:

| Tabla | Filas |
|---|---|
| `licitaciones` | 1.493 |
| `stg_entradas` | 1.493 |
| `documentos` | 5.438 |
| `lotes` | 989 |
| `adjudicaciones` | 732 |

Capa raw: 8 ficheros, 50,3 MB (3 páginas del feed y 5 pliegos).

## La puerta de la fase

**1. Dos pasadas seguidas no crean duplicados.** La segunda pasada sobre las mismas páginas dio 0
licitaciones nuevas. Comprobado además con un test (`test_repetir_la_pasada_completa_no_duplica_nada`)
y con la restricción `UNIQUE (entry_id, entry_updated)`, que lo impide a nivel de base de datos.

**2. Cualquier fila se remonta a su fichero raw.**

```sql
SELECT count(*) FROM licitaciones l
LEFT JOIN stg_entradas s ON s.id = l.stg_entrada
LEFT JOIN raw_ficheros r ON r.sha256 = s.raw_fichero
WHERE r.sha256 IS NULL;   -- 0
```

Recorrido completo de una licitación cualquiera: expediente `Suministros 1/2026` → entrada nº 0 del
fichero `1432b4eb2fda…` → 17.168.257 bytes descargados de la URL del feed → ejecución que lo trajo,
con el commit de git `3f2c72d`.

## Pliegos descargados (Plataforma real)

5 PCAP, 5,2 MB, **14, 112, 86, 14 y 13 páginas** (media 48). Los cinco con capa de texto, cada uno
ligado a su expediente por el sha256 del fichero.

## Caminos de fallo comprobados, no supuestos

| Qué se rompió | Qué hizo el radar |
|---|---|
| Contenedor del agente parado, con el workflow lanzándose | Incidencia registrada en `incidencias` con el paso que falló y un mensaje en español |
| Base de datos caída (`/salud`, `/resumen/hoy`) | 503 con mensaje legible, sin traza |
| Pliego que no es un PDF | Marcado `ilegible` con el motivo; no se reintenta |
| Red caída a mitad de la descarga | Lo ya bajado se conserva; la ejecución queda en `error` con mensaje legible |
| Fuente que rechaza un documento | Vuelve a la cola, hasta 3 intentos; 3 fallos seguidos paran la pasada |

## Lo que queda fuera

- El **aviso por correo** necesita la credencial de Gmail: pasa a la Fase 7 (D25). Hasta entonces las
  incidencias se consultan en la tabla.
- La ingesta diaria garantiza lo publicado **desde la primera pasada**. Lo anterior es la carga
  histórica de la Fase 3.
- El filtro por CPV de la descarga de pliegos está para acotar el gasto; la regla de selección de
  verdad se escribe y se congela en la Fase 3 (D26).
