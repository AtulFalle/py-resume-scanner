FROM python:3.15.2-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=500 \
    UV_HTTP_RETRIES=5 \
    UV_CONCURRENT_DOWNLOADS=1

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv,sharing=shared \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src

EXPOSE 8000 8501

CMD ["uv", "run", "--no-sync", "uvicorn", "resume_ai.main:app", "--host", "0.0.0.0", "--port", "8000"]