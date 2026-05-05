"""SynapseOS — FastAPI Entry Point

Middleware order: TenantMiddleware runs FIRST (rate limit + BYOK before any route).
Docs: /docs (Swagger) | /redoc
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.api.middleware.tenant import TenantMiddleware
from src.api.middleware.langfuse_mw import LangfuseMiddleware
from src.api.routes import query, think, ingest, feedback, collections, health, keys, tools, sessions, admin, ws
from src.core.config import CORS_ORIGINS, ADMIN_SECRET

API_DESCRIPTION = """
## SynapseOS — Self-Improving BYOK RAG Platform

Two endpoints for different latency/quality tradeoffs:

| Endpoint | Latency | Use Case |
|----------|---------|----------|
| `POST /v1/query` | ~235ms | Fast RAG — retrieve + generate |
| `POST /v1/think` | ~865ms | Cognitive — memory + reasoning + tools + reflection |

### Authentication
All `/v1/` endpoints require `X-Tenant-ID` header. Rate limited at 60 RPM per tenant.

### Streaming
Both endpoints support SSE streaming. Set `stream: true` in the request body.

### Management APIs
| Endpoint Group | Description |
|----------------|-------------|
| `/v1/keys` | BYOK API key management (register, delete, list providers) |
| `/v1/tools` | Custom tool CRUD (register, list, get, delete HTTP endpoints) |
| `/v1/sessions` | Session management (list, get history, clear) |
| `/v1/interactions` | Interaction log history with pagination |
| `/v1/collections` | Collection stats, analytics, document deletion, datasets |
| `/v1/ingest/batch` | Batch URL ingestion (up to 10 groups × 50 URLs) |
| `/v1/ingest/bulk-files` | Bulk file upload (up to 20 files) |
| `/v1/ws/think` | WebSocket real-time cognitive thinking |
| `/health/detailed` | Readiness check with downstream service status |

### Admin APIs
| Endpoint | Description |
|----------|-------------|
| `/admin/tenants` | Tenant CRUD (requires `X-Admin-Secret` header) |
| `/admin/system` | System-wide metrics dashboard |
| `/admin/logs` | Cross-tenant interaction log viewer |

### Versioning
All endpoints are versioned under `/v1/`. See [API Versioning Strategy](../docs/api-versioning.md) for details.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    from src.core.retrieval import warm_models, ensure_collection

    # Pre-flight health checks — verify dependent services before accepting traffic
    startup_ok = True
    health_results = {}

    # Check KeyDB
    try:
        from src.core.clients import get_keydb
        keydb = get_keydb()
        await keydb.ping()
        health_results["keydb"] = "ok"
    except Exception as e:
        health_results["keydb"] = f"FAILED: {type(e).__name__}: {str(e)[:100]}"
        startup_ok = False

    # Check PostgreSQL
    try:
        from src.core.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        health_results["postgresql"] = "ok"
    except Exception as e:
        health_results["postgresql"] = f"FAILED: {type(e).__name__}: {str(e)[:100]}"
        startup_ok = False

    # Check Qdrant
    try:
        from src.core.clients import get_qdrant
        qdrant = get_qdrant()
        await qdrant.get_collections()
        health_results["qdrant"] = "ok"
    except Exception as e:
        health_results["qdrant"] = f"FAILED: {type(e).__name__}: {str(e)[:100]}"
        startup_ok = False

    # Check MinIO
    try:
        from src.core.clients import get_minio
        minio = get_minio()
        minio.list_buckets()
        health_results["minio"] = "ok"
    except Exception as e:
        health_results["minio"] = f"FAILED: {type(e).__name__}: {str(e)[:100]}"
        # MinIO failure is non-critical — ingestion won't work but queries will

    if startup_ok:
        print(f"✅ SynapseOS startup checks passed: {health_results}")
    else:
        print(f"⚠️  SynapseOS startup checks PARTIAL FAILURE: {health_results}")
        print("   Some endpoints may not function correctly.")

    # Warm models and ensure collections
    await warm_models()
    await ensure_collection()
    print("✅ SynapseOS ready — models warmed, collections ensured")
    yield
    # ── Shutdown ──
    from src.core.ingestion import close_ingestion_clients, drain_tracked_tasks
    await drain_tracked_tasks()
    await close_ingestion_clients()
    from src.core.clients import close_all
    await close_all()
    from langfuse import Langfuse
    Langfuse().flush()
    print("✅ SynapseOS shutdown — clients closed, Langfuse flushed")


app = FastAPI(
    title="SynapseOS",
    description=API_DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
    contact={"name": "SynapseOS", "url": "https://github.com/rahlplx/synapseos"},
    license_info={"name": "MIT"},
)

# ── Middleware (order: last added = first executed) ──
_allowed_origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_allowed_origins, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(LangfuseMiddleware)
app.add_middleware(TenantMiddleware)

# ── Routes ──
app.include_router(query.router, prefix="/v1")
app.include_router(think.router, prefix="/v1")
app.include_router(ingest.router, prefix="/v1")
app.include_router(feedback.router, prefix="/v1")
app.include_router(collections.router, prefix="/v1")
app.include_router(keys.router, prefix="/v1")
app.include_router(tools.router, prefix="/v1")
app.include_router(sessions.router, prefix="/v1")

# WebSocket (under /v1 for consistency with API versioning)
app.include_router(ws.router, prefix="/v1")

# Admin endpoints (no /v1 prefix — admin is version-independent)
if ADMIN_SECRET:
    app.include_router(admin.router)

# Health endpoints (no /v1 prefix — public paths)
app.include_router(health.router)


