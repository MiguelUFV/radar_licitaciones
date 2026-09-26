# ENTORNO — Instalación, cuentas y claves (Fase 0)

Los comandos son para PowerShell salvo que se indique otra cosa. Sigue las secciones en orden.

## 0. Estado de tu máquina (comprobado el 2026-09-19)

| Herramienta | Versión | Estado |
|---|---|---|
| Git | 2.52.0 | OK. Identidad global: MiguelUFV / correo de la universidad (ver §2) |
| Python | 3.12.8 (`python`) y 3.14.0 (`py`) | OK. Usaremos 3.12 fijado con uv |
| uv | 0.9.30 | OK |
| Docker Desktop | 29.3.1, WSL2, 8 CPU, 16 GB | OK, daemon en marcha |
| Node / npm | 24.14.0 / 11.9.0 | OK (necesario para el MCP de n8n) |
| GitHub CLI | 2.88.1 | OK, sesión iniciada como MiguelUFV |
| VS Code | 1.124.2 | OK |
| Clave de Anthropic | — | **Falta** (§3) |
| CLI `ant` de Anthropic | — | No hace falta |

## 1. Carpeta del proyecto (recomendado)

La carpeta actual (`Documents\proyecto claude code`) tiene espacios y un nombre genérico. Los
espacios dan problemas en scripts y montajes de Docker. Recomendación:

1. Cierra VS Code.
2. Mueve la carpeta a `C:\Users\migue\dev\radar_licitaciones`.
3. Abre esa carpeta en VS Code y arranca Claude Code desde ella.

La memoria de Claude Code va ligada a la ruta. Al moverla empieza de cero, y ahora mismo no hay
nada guardado.

## 2. Repositorio en GitHub

Tu correo global de git es el de la universidad. Si el repo se hace público, ese correo aparecerá
en cada commit. Para este repo, usa el correo `noreply` que te da GitHub:

```powershell
git init -b main
git config user.name "Miguel Martín-Caro"
git config user.email "198183446+MiguelUFV@users.noreply.github.com"
gh repo create radar_licitaciones --private --source . --remote origin
```

- Privado hasta la Fase 8. Se hace público después de revisar secretos e historial.
- El conector de GitHub de Claude Code falla ("Authorization header is badly formatted"). No hace
  falta: se trabaja con `gh`, que sí tiene sesión iniciada.

## 3. Clave de Anthropic (la única clave de pago)

En [console.anthropic.com](https://console.anthropic.com):

1. Crea la cuenta u organización.
2. **Billing:** añade crédito de prepago. Recomendado: 20 $ para las Fases 1–4. Antes de la Fase 5
   se amplía según el presupuesto que salga de la Fase 1. No actives la recarga automática.
3. **Workspaces:** crea `radar_licitaciones`. Así el gasto de este proyecto queda separado y medible.
4. En ese workspace, fija un **límite de gasto mensual**. Recomendado: 30 $.
5. **API keys:** crea una clave en ese workspace, con el nombre `radar-local`.
6. Pégala en `.env` (§4). Nunca en el chat, en un commit ni en n8n.

Precios de referencia (tabla oficial a 2026-06-24; se re-verifican en la Fase 1), en USD por
millón de tokens, entrada/salida: Opus 5 5/25 · Sonnet 5 2/10 · Haiku 4.5 1/5. La Batch API
cuesta un 50 % menos. Estimaciones por licitación y por pliego: `docs/DECISIONES.md` D06.

## 4. Fichero `.env`

```powershell
Copy-Item .env.example .env
uv run python -c "import secrets; print(secrets.token_hex(32))"   # → POSTGRES_PASSWORD
uv run python -c "import secrets; print(secrets.token_hex(32))"   # → N8N_ENCRYPTION_KEY
```

Guarda `N8N_ENCRYPTION_KEY` también en un gestor de contraseñas. Si se pierde, n8n no puede
descifrar las credenciales guardadas (SMTP) y hay que volver a crearlas.

## 5. Docker: Postgres y n8n

Claude escribe `docker-compose.yml` en la Fase 0. Contenido previsto:

| Servicio | Imagen | Puerto (solo localhost) | Para qué |
|---|---|---|---|
| `postgres` | `postgres:17` | 127.0.0.1:5432 | Dos bases: `radar` (datos del proyecto) y `n8n` (estado de n8n) |
| `n8n` | `docker.n8n.io/n8nio/n8n:2.39.8` (versión fijada) | 127.0.0.1:**5679** | Orquestación |
| `agente` | imagen propia (se añade en la Fase 2) | 127.0.0.1:8000 | API FastAPI + grafo LangGraph |

```powershell
docker compose up -d
docker compose ps        # los servicios deben aparecer como "healthy"
```

Los puertos se abren solo en `127.0.0.1`: nada queda expuesto a la red de tu casa.

## 6. n8n

**Dos instalaciones, sin pisarse** (decisión D22): la instalación propia de Miguel (`n8n start`,
versión 2.11.4, datos en `~/.n8n`) sigue en el puerto **5678**. La del proyecto, en Docker y con
los datos en Postgres, está en el **5679**. Se pueden usar a la vez.

1. Abre `http://localhost:5679` y crea el usuario propietario del n8n del proyecto. Es local; no es
   una cuenta en la nube y no tiene nada que ver con la que ya tienes.
2. **Settings → n8n API → Create API key.** Cópiala en `.env` como `N8N_API_KEY`.
3. **Credenciales de correo (SMTP):**
   - Recomendado: una cuenta de Gmail nueva, solo para el radar (no la personal ni la de la universidad).
   - Activa la verificación en dos pasos en esa cuenta y crea una contraseña de aplicación en
     [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
   - En n8n: **Credentials → New → SMTP**: host `smtp.gmail.com`, puerto `465`, SSL activado,
     usuario = la cuenta, contraseña = la contraseña de aplicación.
   - Esta contraseña vive cifrada dentro de n8n, no en `.env`.
4. Zona horaria: el compose fija `GENERIC_TIMEZONE=Europe/Madrid` para que "07:00" sea hora española.

## 7. Conectar Claude Code con n8n (MCP)

Esto permite que Claude cree, valide y ejecute workflows en tu n8n. El plugin `n8n-mcp-skills` ya
está instalado; falta el servidor. Ejecútalo en **Git Bash**, con la clave de §6 (en PowerShell 5.1
el `--` puede perderse):

```bash
claude mcp add n8n-mcp -s local \
  -e MCP_MODE=stdio -e LOG_LEVEL=error -e DISABLE_CONSOLE_OUTPUT=true \
  -e N8N_API_URL=http://localhost:5679 -e N8N_API_KEY=PEGA_AQUI_TU_CLAVE \
  -- cmd /c npx -y n8n-mcp@2.87.0
claude mcp list
```

- `-s local`: la configuración se guarda en tu usuario, no en el repo, así que la clave no acaba en GitHub.
- `cmd /c`: en Windows nativo, los servidores MCP lanzados con `npx` lo necesitan.
- Regla del proyecto: al final de cada sesión, los workflows se exportan a `n8n/workflows/`.

## 8. Python

```powershell
uv python pin 3.12
uv sync            # cuando exista pyproject.toml (lo crea Claude en la Fase 0)
```

`py` apunta a Python 3.14 y `python` a 3.12. Con `uv run` no hay ambigüedad.

**Certificados:** la Plataforma de Contratación usa la raíz de la FNMT. El Python de esta máquina no
la encuentra por defecto (error `self-signed certificate in certificate chain`). Con `certifi`
(el almacén que usa `httpx`) la conexión se verifica correctamente. Por eso el proyecto usa httpx y
prohíbe `verify=False`.

## 9. Claude Code: plugins que hay que arreglar

| Plugin | Problema | Acción |
|---|---|---|
| context-mode 1.0.111 | Le falta un módulo de `better-sqlite3` y su hook bloquea WebFetch. Rompe la consulta de documentación | Ejecuta `/ctx-upgrade` (hay una versión 1.0.169) o desactívalo en este proyecto |
| GitHub MCP | Cabecera de autorización mal formada | Opcional. Se usa `gh` |
| claude-mem | Conexión fallida (reintenta sola) | Opcional |

## 10. Qué cuentas y claves hacen falta

| Qué | Para qué | Coste | Dónde se guarda |
|---|---|---|---|
| Clave de API de Anthropic | Triaje y extracción | Pago por uso, con límite | `.env` |
| GitHub | Repositorio y CI | Gratis | Ya configurado (`gh`) |
| Propietario de n8n + clave de API | Orquestación y conexión MCP | Gratis (self-hosted) | n8n / `.env` / config local de Claude |
| Contraseña de aplicación de Gmail | Enviar el informe diario | Gratis | Credenciales cifradas de n8n |
| `POSTGRES_PASSWORD`, `N8N_ENCRYPTION_KEY` | Base de datos y cifrado de n8n | Generadas | `.env` (+ gestor de contraseñas) |

**No hace falta:** clave de la Plataforma de Contratación (datos abiertos), clave del BCE
(el tipo de cambio es público), LangSmith, OpenAI, servicios de OCR, n8n Cloud, Vercel.

## 11. Comprobación final de la Fase 0

```powershell
docker compose ps                          # postgres y n8n "healthy"
gh repo view --json name,visibility        # radar_licitaciones, PRIVATE
claude mcp list                            # n8n-mcp: connected
uv run python -m radar.diagnostico         # todo en verde (lo escribe Claude en la Fase 0)
```

Prueba de rotura: comenta `ANTHROPIC_API_KEY` en `.env` y vuelve a lanzar el diagnóstico. Tiene que
decir en español qué falta, sin traza.

---

## 10. Comandos del día a día

Todos se ejecutan en una terminal, dentro de la carpeta del proyecto.

| Para qué | Comando |
|---|---|
| Ver cómo va todo | `uv run python -m radar.estado` |
| Comprobar que el entorno está bien | `uv run python -m radar.diagnostico` |
| Mirar licitaciones guardadas | `uv run python -m radar.ver --buscar sanidad` |
| …solo informática, ya adjudicadas | `uv run python -m radar.ver --informatica --ganadas` |
| …una en concreto | `uv run python -m radar.ver --expediente M220032` |
| Descargar lo nuevo del feed | `uv run python -m radar.ingesta --paginas 10` |
| Bajar pliegos pendientes | `uv run python -m radar.pliegos --limite 20` |
| Carga histórica (reanudable) | `uv run python -m radar.historico --desde 2025-01 --hasta 2026-08 --ventana 2025-01 2025-06` |
| Ver los procesos automáticos | Abrir `http://localhost:5679` en el navegador |

Arreglos que solo hacen falta si el diagnóstico los pide:

| Para qué | Comando |
|---|---|
| Seudonimizar DNI que quedaran en claro | `uv run python -m radar.personas --anonimizar` |
| Traducir los códigos del XML (`&quot;`) | `uv run python -m radar.reparar --textos` |

**Si algo se queda colgado:** los procesos largos son reanudables. Se lanzan otra vez con el mismo
comando y siguen donde estaban, sin volver a descargar lo que ya tienen.
