"""SynapseOS — FastAPI Entry Point

Middleware order: TenantMiddleware runs FIRST (rate limit + BYOK before any route).
Docs: /docs (Swagger) | /redoc
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.api.middleware.tenant import TenantMiddleware
from src.api.middleware.langfuse_mw import LangfuseMiddleware
from src.api.routes import query, think, ingest, feedback, collections

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
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    from src.core.retrieval import warm_models, ensure_collection
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
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(LangfuseMiddleware)
app.add_middleware(TenantMiddleware)

# ── Routes ──
app.include_router(query.router, prefix="/v1")
app.include_router(think.router, prefix="/v1")
app.include_router(ingest.router, prefix="/v1")
app.include_router(feedback.router, prefix="/v1")
app.include_router(collections.router, prefix="/v1")


@app.get("/health", summary="Health check", tags=["system"])
async def health():
    """Health check endpoint. No authentication required.

    Returns OK status and API version. Skipped by TenantMiddleware.
    """
    return {"status": "ok", "version": "1.0.0"}
