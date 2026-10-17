FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

ENV PATH="/app/.venv/bin:$PATH"
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY . .
EXPOSE 47283
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "47283", "--workers", "1"]

