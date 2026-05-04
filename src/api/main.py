"""
SynapseOS — FastAPI Entry Point
Docs: /docs (Swagger) | /redoc
Middleware order matters: TenantMiddleware runs FIRST (rate limit + BYOK before any route)
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")  # ARM CPU tuning

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.api.middleware.tenant import TenantMiddleware
from src.api.middleware.langfuse_mw import LangfuseMiddleware
from src.api.routes import query, think, ingest, feedback, collections


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    # 1. Warm ONNX models (avoid cold-start latency on first query)
    from src.core.retrieval import warm_models, ensure_collection
    await warm_models()
    # 2. Ensure Qdrant collections exist (synapse_knowledge + synapse_memory)
    await ensure_collection()
    print("✅ SynapseOS ready — models warmed, collections ensured")
    yield
    # ── Shutdown ──
    from src.core.ingestion import close_ingestion_clients
    await close_ingestion_clients()
    from langfuse import Langfuse
    Langfuse().flush()
    print("✅ SynapseOS shutdown — clients closed, Langfuse flushed")


app = FastAPI(
    title="SynapseOS",
    description="Self-improving BYOK RAG platform with cognitive engine",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Middleware (order: last added = first executed) ──
# TenantMiddleware MUST run before routes (rate limit + BYOK injection)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(LangfuseMiddleware)
app.add_middleware(TenantMiddleware)

# ── Routes ──
app.include_router(query.router, prefix="/v1")
app.include_router(think.router, prefix="/v1")
app.include_router(ingest.router, prefix="/v1")
app.include_router(feedback.router, prefix="/v1")
app.include_router(collections.router, prefix="/v1")


@app.get("/health")
async def health():
    """Health check — skipped by TenantMiddleware (no auth required)."""
    return {"status": "ok", "version": "1.0.0"}
