# syntax=docker/dockerfile:1
# Production Go Dockerfile — Static binary + Scratch
# Tier 3+ pattern | Target: <20MB final image
# Usage: docker build -t myapp:latest .

ARG GO_VERSION=1.23

# ============================================================
# Stage 1: Build static binary
# ============================================================
FROM golang:${GO_VERSION}-alpine AS builder

# Install CA certs and timezone data for scratch
RUN apk add --no-cache ca-certificates tzdata

WORKDIR /app

# Cache dependencies
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download

# Build static binary
COPY . .
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -ldflags="-s -w -X main.version={{VERSION}}" \
    -o /bin/server ./cmd/server

# ============================================================
# Stage 2: Test (optional — use with --target test)
# ============================================================
FROM builder AS test
RUN CGO_ENABLED=0 go test -v ./...

# ============================================================
# Stage 3: Minimal production image
# ============================================================
FROM scratch AS production

# Import CA certs and timezone from builder
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /usr/share/zoneinfo /usr/share/zoneinfo

# Copy binary
COPY --from=builder /bin/server /server

LABEL org.opencontainers.image.title="{{APP_NAME}}" \
      org.opencontainers.image.version="{{VERSION}}"

EXPOSE 8080

# Run as non-root (numeric UID for scratch)
USER 65534:65534

ENTRYPOINT ["/server"]
