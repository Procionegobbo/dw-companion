# syntax=docker/dockerfile:1
ARG PYTHON_IMAGE=python:3.12-slim
ARG NODE_IMAGE=node:22-slim
ARG UV_VERSION=0.13.5

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# Static site: architecture-independent output, so build on the host platform.
FROM --platform=$BUILDPLATFORM ${NODE_IMAGE} AS site
ENV ASTRO_TELEMETRY_DISABLED=1
WORKDIR /src/site
COPY site/package.json site/package-lock.json ./
RUN npm ci
COPY data/normalized/ /src/data/normalized/
COPY site/ ./
RUN npm run build && npm run check-links

# Python runtime dependencies only (no dev group).
FROM ${PYTHON_IMAGE} AS deps
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

FROM ${PYTHON_IMAGE} AS runtime
RUN useradd --system --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=deps /app/.venv /app/.venv
COPY backend/ /app/backend/
COPY data/normalized/ /app/data/normalized/
COPY data/index/ /app/data/index/
COPY --from=site /src/site/dist/ /app/site/dist/
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 SITE_DIR=/app/site/dist
USER app
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn backend.api.app:create_app --factory --host 0.0.0.0 --port \"${PORT:-8080}\" --workers 1 --no-access-log --proxy-headers --forwarded-allow-ips '*'"]
