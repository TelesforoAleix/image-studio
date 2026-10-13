# syntax=docker/dockerfile:1
FROM node:24-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/index.html ./
COPY frontend/src ./src
RUN npm run build

FROM python:3.13-slim AS python-build
COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.13-slim AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FRONTEND_DIST=/app/static \
    STUDIO_FILES=/app/files
WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
COPY --from=python-build /app/.venv /app/.venv
COPY --from=frontend /frontend/dist /app/static
COPY alembic.ini ./
COPY migrations ./migrations
RUN mkdir /app/files && chown 10001:10001 /app/files
USER 10001:10001
EXPOSE 8200
CMD ["sh", "-c", "alembic upgrade head && exec gunicorn --bind 0.0.0.0:8200 --workers 2 --access-logfile - 'image_studio:create_app()'"]
