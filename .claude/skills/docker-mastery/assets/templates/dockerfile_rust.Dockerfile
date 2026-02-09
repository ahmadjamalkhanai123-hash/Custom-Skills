# syntax=docker/dockerfile:1
# Production Rust Dockerfile — cargo-chef + Scratch
# Tier 3+ pattern | Target: <15MB final image
# Usage: docker build -t myapp:latest .

ARG RUST_VERSION=1.80

# ============================================================
# Stage 1: Dependency planner (cargo-chef)
# ============================================================
FROM rust:${RUST_VERSION}-slim AS planner

RUN cargo install cargo-chef --locked
WORKDIR /app
COPY . .
RUN cargo chef prepare --recipe-path recipe.json

# ============================================================
# Stage 2: Build dependencies (cached layer)
# ============================================================
FROM rust:${RUST_VERSION}-slim AS builder

RUN cargo install cargo-chef --locked && \
    apt-get update && apt-get install -y --no-install-recommends \
    pkg-config libssl-dev ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cook dependencies (this layer is cached)
COPY --from=planner /app/recipe.json recipe.json
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    cargo chef cook --release --recipe-path recipe.json

# Build application
COPY . .
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/app/target \
    cargo build --release && \
    cp target/release/{{APP_NAME}} /usr/local/bin/server

# ============================================================
# Stage 3: Minimal production image
# ============================================================
FROM gcr.io/distroless/cc-debian12:nonroot AS production

COPY --from=builder /usr/local/bin/server /server
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

LABEL org.opencontainers.image.title="{{APP_NAME}}" \
      org.opencontainers.image.version="{{VERSION}}"

EXPOSE 8080

USER nonroot

ENTRYPOINT ["/server"]
