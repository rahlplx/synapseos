"""
SynapseOS — FastAPI Entry Point
Docs: /docs (Swagger) | /redoc
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
    # Startup: warm models, verify connections
    from src.core.retrieval import warm_models
    await warm_models()
    yield
    # Shutdown: flush Langfuse
    from langfuse import Langfuse
    Langfuse().flush()


app = FastAPI(
    title="SynapseOS",
    description="Self-improving BYOK RAG platform with cognitive engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(LangfuseMiddleware)
app.add_middleware(TenantMiddleware)

app.include_router(query.router, prefix="/v1")
app.include_router(think.router, prefix="/v1")
app.include_router(ingest.router, prefix="/v1")
app.include_router(feedback.router, prefix="/v1")
app.include_router(collections.router, prefix="/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
