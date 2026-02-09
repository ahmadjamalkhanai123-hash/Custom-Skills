# syntax=docker/dockerfile:1
# Production Python Dockerfile — Multi-stage + uv + Distroless
# Tier 3+ pattern | Target: <80MB final image
# Usage: docker build -t myapp:latest .

ARG PYTHON_VERSION=3.12

# ============================================================
# Stage 1: Build dependencies
# ============================================================
FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /app

# Install uv for fast dependency resolution
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install uv

# Install dependencies first (cache layer)
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# Copy application source
COPY src/ ./src/

# ============================================================
# Stage 2: Test (optional — use with --target test)
# ============================================================
FROM builder AS test

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

COPY tests/ ./tests/
RUN uv run pytest tests/ -v --tb=short

# ============================================================
# Stage 3: Production runtime
# ============================================================
FROM gcr.io/distroless/python3-debian12:nonroot AS production

WORKDIR /app

# Copy virtual environment and source
COPY --from=builder /app/.venv/lib/python3.12/site-packages /usr/lib/python3.12/site-packages
COPY --from=builder /app/src ./src

# OCI labels
LABEL org.opencontainers.image.title="{{APP_NAME}}" \
      org.opencontainers.image.version="{{VERSION}}" \
      org.opencontainers.image.description="{{DESCRIPTION}}" \
      org.opencontainers.image.source="{{REPO_URL}}"

EXPOSE 8000

# Run as non-root (distroless nonroot = UID 65532)
USER nonroot

# Exec form for proper signal handling
ENTRYPOINT ["python", "-m", "src.main"]

# Override with: docker run myapp:latest --port 9000
CMD ["--host", "0.0.0.0", "--port", "8000"]
