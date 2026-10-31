# The image Cloud Run runs: the API app with the built frontend, served from one origin.

# 1. Build the frontend into `frontend/dist`, with the Node version of `.nvmrc`.
FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2. Install the package and its runtime dependencies into a virtual environment.
FROM python:3.13-slim AS deps
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ ./src/
RUN uv sync --frozen --no-dev --no-editable

# 3. The runtime: the environment and the built frontend, without build tools.
FROM python:3.13-slim AS app
WORKDIR /app
RUN useradd --create-home --uid 10001 imposter
COPY --from=deps /app/.venv /app/.venv
COPY --from=frontend /app/frontend/dist /app/frontend/dist
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    IMPOSTER_FRONTEND_DIR=/app/frontend/dist \
    PORT=8080
USER imposter
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn --factory imposter.api.app:create_app --host 0.0.0.0 --port ${PORT}"]
