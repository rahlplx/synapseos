"""POST /v1/ingest, POST /v1/ingest/file, GET /v1/ingest/{job_id}"""
import time
from uuid import uuid4
from fastapi import APIRouter, Request, BackgroundTasks, UploadFile, File
from pydantic import BaseModel, Field
from src.core.ingestion import ingest_urls, ingest_file
from src.core.clients import get_keydb

router = APIRouter()


class IngestRequest(BaseModel):
    urls: list[str] = Field(..., max_length=10, description="List of URLs to ingest (max 10)")
    metadata: dict = Field(default_factory=dict)


@router.post("/ingest")
async def ingest_endpoint(body: IngestRequest, request: Request, background_tasks: BackgroundTasks):
    """Queue document ingestion. Returns job ID immediately."""
    tenant_id = request.state.tenant_id
    job_id = str(uuid4())
    keydb = get_keydb()
    await keydb.hset(f"job:{job_id}", mapping={
        "created_at": str(time.time()),
        "tenant_id": tenant_id,
    })
    background_tasks.add_task(ingest_urls, body.urls, tenant_id, job_id, body.metadata)
    return {"job_id": job_id, "status": "queued", "document_count": len(body.urls)}


@router.post("/ingest/file")
async def ingest_file_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """Upload a file (PDF, DOCX, TXT, MD) for ingestion."""
    tenant_id = request.state.tenant_id
    job_id = str(uuid4())
    content = await file.read()
    keydb = get_keydb()
    await keydb.hset(f"job:{job_id}", mapping={
        "created_at": str(time.time()),
        "tenant_id": tenant_id,
    })
    background_tasks.add_task(ingest_file, content, file.filename, tenant_id, job_id)
    return {"job_id": job_id, "status": "queued"}


@router.get("/ingest/{job_id}")
async def ingest_status(job_id: str, request: Request):
    """Poll ingestion job status. Verifies tenant ownership."""
    tenant_id = request.state.tenant_id
    keydb = get_keydb()
    data = await keydb.hgetall(f"job:{job_id}")
    if not data:
        return {"job_id": job_id, "status": "not_found"}

    # Verify tenant ownership — prevent cross-tenant job enumeration
    job_tenant = data.get(b"tenant_id", b"").decode()
    if job_tenant and job_tenant != tenant_id:
        return {"job_id": job_id, "status": "not_found"}

    created_at = float(data.get(b"created_at", 0))
    elapsed_ms = int((time.time() - created_at) * 1000) if created_at else None

    return {
        "job_id": job_id,
        "status": data.get(b"status", b"unknown").decode(),
        "chunk_count": int(data.get(b"chunk_count", 0)),
        "current_url": data.get(b"current_url", b"").decode(),
        "elapsed_ms": elapsed_ms,
        "error": data.get(b"error", b"").decode() if b"error" in data else None,
    }
