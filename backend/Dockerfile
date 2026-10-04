FROM python:3.11-slim

# Copy official uv binary from astral-sh
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
	PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
	uv sync --frozen --no-dev

COPY app /app/app
COPY mcp /app/mcp
COPY run_services.sh /app/run_services.sh
EXPOSE 4000 8001
CMD ["bash", "/app/run_services.sh"]
