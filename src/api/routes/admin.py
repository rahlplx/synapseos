"""Admin API — tenant management, system overview, runtime configuration.

All endpoints require X-Admin-Secret header (configured via ADMIN_SECRET env var).
These endpoints are NOT tenant-scoped — they operate across all tenants.
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Header

from src.api.models import ErrorResponse
from src.core.config import ADMIN_SECRET

router = APIRouter(tags=["admin"])
logger = logging.getLogger(__name__)


def _verify_admin(admin_secret: str = Header(None, alias="X-Admin-Secret")):
    """Verify admin secret header. Raises 401 if missing or incorrect."""
    if not ADMIN_SECRET:
        raise HTTPException(500, "ADMIN_SECRET not configured — admin API disabled")
    if admin_secret != ADMIN_SECRET:
        raise HTTPException(401, "Invalid admin secret")


@router.get(
    "/admin/tenants",
    summary="List all tenants",
    response_description="Tenant list with usage stats",
    dependencies=[_verify_admin],
)
async def list_tenants(request: Request):
    """List all registered tenants with their tier, RPM limit, and usage stats.

    Returns tenant metadata from PostgreSQL and recent query counts from KeyDB.
    This is an admin-only endpoint — requires X-Admin-Secret header.
    """
    from src.core.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT t.id, t.org_name, t.tier, t.rpm_limit, t.created_at,
                   COUNT(il.id) as queries_7d
            FROM tenants t
            LEFT JOIN interaction_logs il ON il.tenant_id = t.id
                AND il.created_at > now() - INTERVAL '7 days'
            GROUP BY t.id, t.org_name, t.tier, t.rpm_limit, t.created_at
            ORDER BY t.created_at DESC
        """)

    tenants = [
        {
            "id": r["id"],
            "org_name": r["org_name"],
            "tier": r["tier"],
            "rpm_limit": r["rpm_limit"],
            "queries_7d": int(r["queries_7d"] or 0),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
    return {"tenants": tenants, "count": len(tenants)}


@router.post(
    "/admin/tenants",
    summary="Create tenant",
    response_description="Created tenant metadata",
    dependencies=[_verify_admin],
)
async def create_tenant(request: Request):
    """Create a new tenant. Body: {"id": "org-xyz", "org_name": "Acme Corp", "tier": "pro", "rpm_limit": 120}"""
    body = await request.json()
    tenant_id = body.get("id")
    org_name = body.get("org_name")
    tier = body.get("tier", "starter")
    rpm_limit = body.get("rpm_limit", 60)

    if not tenant_id or not org_name:
        raise HTTPException(400, "Both 'id' and 'org_name' are required")

    from src.core.db import get_pool
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO tenants (id, org_name, tier, rpm_limit) VALUES ($1, $2, $3, $4)",
                tenant_id, org_name, tier, rpm_limit,
            )
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(409, f"Tenant '{tenant_id}' already exists")
        raise HTTPException(500, f"Failed to create tenant: {type(e).__name__}: {e}")

    # Set RPM limit in KeyDB for the rate limiter
    from src.core.clients import get_keydb
    keydb = get_keydb()
    await keydb.set(f"tenant:{tenant_id}:rpm", rpm_limit)

    logger.info(f"[admin] Tenant created: {tenant_id} ({org_name}, tier={tier})")
    return {"created": True, "id": tenant_id, "org_name": org_name, "tier": tier, "rpm_limit": rpm_limit}


@router.patch(
    "/admin/tenants/{tenant_id}",
    summary="Update tenant",
    response_description="Updated tenant metadata",
    dependencies=[_verify_admin],
)
async def update_tenant(tenant_id: str, request: Request):
    """Update tenant tier and RPM limit. Body: {"tier": "pro", "rpm_limit": 120}"""
    body = await request.json()
    tier = body.get("tier")
    rpm_limit = body.get("rpm_limit")

    from src.core.db import get_pool
    pool = await get_pool()

    updates = []
    params = []
    idx = 1

    if tier:
        idx += 1
        updates.append(f"tier = ${idx}")
        params.append(tier)
    if rpm_limit:
        idx += 1
        updates.append(f"rpm_limit = ${idx}")
        params.append(rpm_limit)

    if not updates:
        raise HTTPException(400, "No fields to update. Provide 'tier' and/or 'rpm_limit'.")

    params.append(tenant_id)
    query = f"UPDATE tenants SET {', '.join(updates)} WHERE id = ${idx + 1}"

    async with pool.acquire() as conn:
        result = await conn.execute(query, *params)
        if result.endswith("0"):
            raise HTTPException(404, f"Tenant '{tenant_id}' not found")

    # Update RPM in KeyDB if changed
    if rpm_limit:
        from src.core.clients import get_keydb
        keydb = get_keydb()
        await keydb.set(f"tenant:{tenant_id}:rpm", rpm_limit)

    logger.info(f"[admin] Tenant updated: {tenant_id} (tier={tier}, rpm={rpm_limit})")
    return {"updated": True, "id": tenant_id, "tier": tier, "rpm_limit": rpm_limit}


@router.delete(
    "/admin/tenants/{tenant_id}",
    summary="Delete tenant",
    response_description="Confirmation of tenant deletion",
    responses={404: {"model": ErrorResponse}},
    dependencies=[_verify_admin],
)
async def delete_tenant(tenant_id: str, request: Request):
    """Delete a tenant and all associated data.

    Cascade deletes: API keys, tools, documents, interaction logs.
    Also clears KeyDB rate limit and session data.
    This action is IRREVERSIBLE.
    """
    from src.core.db import get_pool
    pool = await get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM tenants WHERE id = $1", tenant_id)
        if result.endswith("0"):
            raise HTTPException(404, f"Tenant '{tenant_id}' not found")

    # Clean up KeyDB keys for this tenant
    from src.core.clients import get_keydb
    keydb = get_keydb()
    cursor = b"0"
    while True:
        cursor, keys = await keydb.scan(cursor=cursor, match=f"tenant:{tenant_id}:*", count=100)
        if keys:
            await keydb.delete(*keys)
        if cursor == b"0":
            break

    logger.info(f"[admin] Tenant deleted: {tenant_id}")
    return {"deleted": True, "id": tenant_id}


@router.get(
    "/admin/system",
    summary="System overview",
    response_description="System-wide metrics and configuration",
    dependencies=[_verify_admin],
)
async def system_overview(request: Request):
    """System-wide metrics: total tenants, queries, documents, RAGAS trends, model config.

    Provides a single dashboard-like endpoint with all key operational metrics.
    """
    from src.core.db import get_pool
    pool = await get_pool()

    async with pool.acquire() as conn:
        stats = await conn.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM tenants) as total_tenants,
                (SELECT COUNT(*) FROM interaction_logs WHERE created_at > now() - INTERVAL '24 hours') as queries_24h,
                (SELECT COUNT(*) FROM interaction_logs WHERE created_at > now() - INTERVAL '7 days') as queries_7d,
                (SELECT COUNT(*) FROM documents WHERE status = 'done') as total_documents,
                (SELECT AVG(ragas_combined) FROM interaction_logs
                    WHERE ragas_combined IS NOT NULL AND created_at > now() - INTERVAL '7 days') as avg_ragas_7d
        """)

    # Collection sizes from Qdrant
    collection_stats = {}
    try:
        from src.core.config import COLLECTION_KNOWLEDGE, COLLECTION_MEMORY
        from src.core.clients import get_qdrant
        qdrant = get_qdrant()
        for name in (COLLECTION_KNOWLEDGE, COLLECTION_MEMORY):
            info = await qdrant.get_collection(name)
            collection_stats[name] = {
                "points": info.points_count or 0,
                "status": info.status,
            }
    except Exception as e:
        logger.warning(f"[admin] Qdrant stats failed: {type(e).__name__}: {e}")
        collection_stats = {"error": "unavailable"}

    # KeyDB info
    keydb_info = {}
    try:
        from src.core.clients import get_keydb
        keydb = get_keydb()
        keydb_info = await keydb.info("memory")
    except Exception:
        keydb_info = {"error": "unavailable"}

    return {
        "tenants": int(stats["total_tenants"] or 0),
        "queries_24h": int(stats["queries_24h"] or 0),
        "queries_7d": int(stats["queries_7d"] or 0),
        "total_documents": int(stats["total_documents"] or 0),
        "avg_ragas_7d": round(float(stats["avg_ragas_7d"] or 0), 3),
        "collections": collection_stats,
        "keydb_used_memory_human": keydb_info.get("used_memory_human", "unknown"),
        "models": {
            "generation": "groq/llama-3.1-70b-versatile",
            "fast": "groq/llama-3.1-8b-instant",
            "embedding": "BAAI/bge-base-en-v1.5 (768d)",
            "reranker": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        },
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/admin/logs",
    summary="View recent interaction logs",
    response_description="Recent logs across all tenants",
    dependencies=[_verify_admin],
)
async def admin_logs(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    tenant_id: str = None,
):
    """View interaction logs across all tenants (or filter by tenant).

    Admin-only endpoint for debugging and monitoring. Supports pagination
    and optional tenant_id filter.
    """
    from src.core.db import get_pool
    pool = await get_pool()

    limit = min(limit, 200)
    conditions = []
    params = []
    idx = 1

    if tenant_id:
        conditions.append(f"tenant_id = ${idx}")
        params.append(tenant_id)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with pool.acquire() as conn:
        total = await conn.fetchval(f"SELECT COUNT(*) FROM interaction_logs {where}", *params)

        rows = await conn.fetch(
            f"""
            SELECT id, tenant_id, query, answer, created_at,
                   ragas_faithfulness, ragas_relevancy, ragas_combined
            FROM interaction_logs {where}
            ORDER BY created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params, limit, offset,
        )

    logs = [
        {
            "id": str(r["id"]),
            "tenant_id": r["tenant_id"],
            "query": r["query"][:200],
            "answer": r["answer"][:200] if r["answer"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "ragas_combined": round(float(r["ragas_combined"]), 3) if r["ragas_combined"] else None,
        }
        for r in rows
    ]

    return {"logs": logs, "pagination": {"total": total, "limit": limit, "offset": offset}}
