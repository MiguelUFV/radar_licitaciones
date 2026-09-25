# Servicio del radar: la API que dispara n8n.
FROM python:3.12-slim

# uv gestiona las dependencias con el fichero de bloqueo, igual que en local.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

# Primero las dependencias: así una edición del código no obliga a reinstalarlas.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY radar/ ./radar/
COPY sql/ ./sql/
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "radar.api:app", "--host", "0.0.0.0", "--port", "8000"]
