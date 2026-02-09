# syntax=docker/dockerfile:1
# MCP Server (FastMCP + Python) — Multi-stage + Alpine
# Tier 2 | Target: <80MB final image
# Build: docker build -t mcp-server:latest .
# Run:   docker compose up -d

ARG PYTHON_VERSION=3.12

# ============================================================
# Stage 1: Build dependencies
# ============================================================
FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /usr/local/bin/uv

# Install dependencies first (cache layer — changes rarely)
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python \
        "fastmcp>=2.0" \
        "redis[hiredis]>=5.0" \
        "pydantic>=2.0" \
        "structlog>=24.0"

# Copy application source (changes often — after deps)
COPY src/ ./src/

# ============================================================
# Stage 2: Test (optional — docker build --target test .)
# ============================================================
FROM builder AS test

RUN uv pip install --python /app/.venv/bin/python pytest pytest-asyncio
COPY tests/ ./tests/
RUN /app/.venv/bin/python -m pytest tests/ -v --tb=short

# ============================================================
# Stage 3: Production runtime
# ============================================================
FROM python:${PYTHON_VERSION}-slim AS production

# Security: non-root user
RUN groupadd -r -g 1001 mcpuser && \
    useradd -r -u 1001 -g mcpuser -d /app -s /sbin/nologin mcpuser

WORKDIR /app

# Copy venv and source from builder
COPY --from=builder --chown=mcpuser:mcpuser /app/.venv /app/.venv
COPY --from=builder --chown=mcpuser:mcpuser /app/src ./src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# OCI labels
LABEL org.opencontainers.image.title="mcp-server" \
      org.opencontainers.image.description="FastMCP server with Redis caching" \
      org.opencontainers.image.source="https://github.com/OWNER/mcp-server"

EXPOSE 8000

# Health check using Python stdlib (no curl needed)
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]

USER mcpuser

# Exec form for proper SIGTERM handling
ENTRYPOINT ["python", "-m", "src.server"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
