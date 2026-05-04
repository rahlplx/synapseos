"""
Shared asyncpg connection pool — used by ingestion, tools, engine, collections.
Prevents connection exhaustion from raw asyncpg.connect() calls.
Pool is lazy-initialized on first use and shared across all modules.
"""
import os
import logging
import asyncpg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the shared asyncpg connection pool.
    Pool size: min=2, max=8 (enough for concurrent API requests without exhausting PG).
    """
    global _pool
    if _pool is None:
        dsn = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
        if not dsn:
            raise RuntimeError("DATABASE_URL not configured")
        _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=8)
        logger.info("[db] Shared asyncpg pool created (min=2, max=8)")
    return _pool


async def close_pool():
    """Gracefully close the shared pool. Called on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("[db] Shared asyncpg pool closed")
