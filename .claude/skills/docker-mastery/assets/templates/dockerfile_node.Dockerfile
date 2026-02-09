# syntax=docker/dockerfile:1
# Production Node.js Dockerfile — Multi-stage + Alpine
# Tier 3+ pattern | Target: <100MB final image
# Usage: docker build -t myapp:latest .

ARG NODE_VERSION=22

# ============================================================
# Stage 1: Install dependencies
# ============================================================
FROM node:${NODE_VERSION}-alpine AS deps

WORKDIR /app

# Install production dependencies only
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --omit=dev --ignore-scripts

# ============================================================
# Stage 2: Build application
# ============================================================
FROM node:${NODE_VERSION}-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY . .
RUN npm run build

# ============================================================
# Stage 3: Test (optional — use with --target test)
# ============================================================
FROM builder AS test
RUN npm test

# ============================================================
# Stage 4: Production runtime
# ============================================================
FROM node:${NODE_VERSION}-alpine AS production

# Security: add non-root user
RUN addgroup -g 1001 -S appgroup && \
    adduser -u 1001 -S appuser -G appgroup

WORKDIR /app

# Copy production deps and built app
COPY --from=deps --chown=appuser:appgroup /app/node_modules ./node_modules
COPY --from=builder --chown=appuser:appgroup /app/dist ./dist
COPY --from=builder --chown=appuser:appgroup /app/package.json ./

# OCI labels
LABEL org.opencontainers.image.title="{{APP_NAME}}" \
      org.opencontainers.image.version="{{VERSION}}"

EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:3000/health"]

USER appuser

ENTRYPOINT ["node", "dist/index.js"]
