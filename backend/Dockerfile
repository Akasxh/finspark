FROM python:3.12-slim AS base

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser

# ----- Development -----
FROM base AS development
RUN uv sync --frozen --extra dev
COPY . .
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "finspark.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ----- Production -----
FROM base AS production
RUN uv sync --frozen --no-dev
COPY . .
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "finspark.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
