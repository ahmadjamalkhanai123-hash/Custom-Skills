"""MCP Server with Redis caching — containerized with Docker."""

import os
import json
import hashlib
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from fastmcp import FastMCP

log = structlog.get_logger()

# ── Configuration ──────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # 5 minutes
SERVER_NAME = os.getenv("MCP_SERVER_NAME", "mcp-server")

# ── Redis client (lazy init) ──────────────────────────────
_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get or create Redis connection."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


# ── MCP Server ─────────────────────────────────────────────
mcp = FastMCP(SERVER_NAME)


@mcp.tool()
async def cached_lookup(key: str) -> str:
    """Look up a cached value by key. Returns cached result or 'not found'."""
    r = await get_redis()
    value = await r.get(f"mcp:{key}")
    if value:
        log.info("cache_hit", key=key)
        return value
    log.info("cache_miss", key=key)
    return "not found"


@mcp.tool()
async def cache_store(key: str, value: str, ttl: int = CACHE_TTL) -> str:
    """Store a value in cache with TTL (seconds). Returns confirmation."""
    r = await get_redis()
    await r.set(f"mcp:{key}", value, ex=ttl)
    log.info("cache_set", key=key, ttl=ttl)
    return f"Stored '{key}' with TTL={ttl}s"


@mcp.tool()
async def cache_delete(key: str) -> str:
    """Delete a cached value by key."""
    r = await get_redis()
    deleted = await r.delete(f"mcp:{key}")
    log.info("cache_delete", key=key, deleted=bool(deleted))
    return f"Deleted '{key}'" if deleted else f"Key '{key}' not found"


# ── Health endpoint (used by Docker HEALTHCHECK) ───────────
@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Health check endpoint for Docker."""
    from starlette.responses import JSONResponse

    try:
        r = await get_redis()
        await r.ping()
        return JSONResponse({"status": "healthy", "redis": "connected"})
    except Exception as e:
        return JSONResponse(
            {"status": "unhealthy", "redis": str(e)},
            status_code=503,
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    mcp.run(transport="streamable-http", host=args.host, port=args.port)
