FROM node:22.14.0-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /bin/uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/app ./app
COPY backend/mcp ./mcp
COPY backend/tables ./tables
COPY backend/run_services.sh ./run_services.sh
COPY backend/service_runner.py ./service_runner.py
COPY deploy /app/deploy
COPY --from=frontend /build/dist /app/frontend-dist
RUN useradd --uid 10001 --create-home pulse && chown -R pulse:pulse /app
ENV PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PULSE_HOSTED_DEMO=true FRONTEND_DIST=/app/frontend-dist \
    EMAIL_DELIVERY_MODE=mock FORWARDED_ALLOW_IPS=* FASTMCP_CHECK_FOR_UPDATES=off
USER pulse
EXPOSE 10000
CMD ["bash", "/app/deploy/start.sh"]
