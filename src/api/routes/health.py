"""Health check endpoints — basic + detailed with downstream service verification.

GET /health         — Quick liveness check (no downstream calls)
GET /health/detailed — Readiness check (verifies Qdrant, KeyDB, PG, MinIO)
"""
import time
import logging
from fastapi import APIRouter

from src.api.models import _latency_ms

router = APIRouter(tags=["system"])
logger = logging.getLogger(__name__)


@router.get("/health", summary="Liveness check", include_in_schema=False)
async def health():
    """Quick liveness probe. No downstream calls — always fast."""
    return {"status": "ok", "version": "1.0.0"}


@router.get("/health/detailed", summary="Readiness check", response_description="Service health with downstream status")
async def health_detailed():
    """Readiness probe that verifies all downstream services are reachable.

    Checks Qdrant, KeyDB, PostgreSQL, and MinIO connectivity.
    Returns per-service status, latency, and overall health.
    Used by load balancers and orchestrators to determine traffic routing.
    """
    start = time.perf_counter()
    services = {}

    # ── Qdrant ──
    try:
        t0 = time.perf_counter()
        qdrant = get_qdrant()
        collections = await qdrant.get_collections()
        services["qdrant"] = {
            "status": "ok",
            "latency_ms": _latency_ms(t0),
            "collections_count": len(collections.collections) if collections else 0,
        }
    except Exception as e:
        services["qdrant"] = {"status": "error", "error": f"{type(e).__name__}: {str(e)[:200]}"}
        logger.warning(f"[health] Qdrant check failed: {type(e).__name__}: {e}")

    # ── KeyDB / Redis ──
    try:
        t0 = time.perf_counter()
        keydb = get_keydb()
        await keydb.ping()
        services["keydb"] = {"status": "ok", "latency_ms": _latency_ms(t0)}
    except Exception as e:
        services["keydb"] = {"status": "error", "error": f"{type(e).__name__}: {str(e)[:200]}"}
        logger.warning(f"[health] KeyDB check failed: {type(e).__name__}: {e}")

    # ── PostgreSQL ──
    try:
        t0 = time.perf_counter()
        from src.core.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
        services["postgresql"] = {"status": "ok", "latency_ms": _latency_ms(t0), "result": result}
    except Exception as e:
        services["postgresql"] = {"status": "error", "error": f"{type(e).__name__}: {str(e)[:200]}"}
        logger.warning(f"[health] PostgreSQL check failed: {type(e).__name__}: {e}")

    # ── MinIO ──
    try:
        t0 = time.perf_counter()
        minio = get_minio()
        # Simple check: list buckets (always works if MinIO is up)
        buckets = minio.list_buckets()
        services["minio"] = {
            "status": "ok",
            "latency_ms": _latency_ms(t0),
            "buckets_count": len(buckets) if buckets else 0,
        }
    except Exception as e:
        services["minio"] = {"status": "error", "error": f"{type(e).__name__}: {str(e)[:200]}"}
        logger.warning(f"[health] MinIO check failed: {type(e).__name__}: {e}")

    # ── Aggregate ──
    all_ok = all(s.get("status") == "ok" for s in services.values())
    overall = "ok" if all_ok else "degraded"

    return {
        "status": overall,
        "version": "1.0.0",
        "services": services,
        "latency_ms": _latency_ms(start),
    }


# Lazy imports to avoid circular dependency at module level
def get_qdrant():
    from src.core.clients import get_qdrant as _get
    return _get()


def get_keydb():
    from src.core.clients import get_keydb as _get
    return _get()


def get_minio():
    from src.core.clients import get_minio as _get
    return _get()
