"""POST /v1/ingest, POST /v1/ingest/file, GET /v1/ingest/{job_id}"""
from uuid import uuid4
from fastapi import APIRouter, Request, BackgroundTasks, UploadFile, File
from pydantic import BaseModel
from src.core.ingestion import ingest_urls, ingest_file
import redis.asyncio as redis
import os

router = APIRouter()
keydb = redis.from_url(os.environ.get("KEYDB_URL", "redis://keydb:6379"))


class IngestRequest(BaseModel):
    urls: list[str]
    metadata: dict = {}


@router.post("/ingest")
async def ingest_endpoint(body: IngestRequest, request: Request, background_tasks: BackgroundTasks):
    """Queue document ingestion. Returns job ID immediately."""
    tenant_id = request.state.tenant_id
    job_id = str(uuid4())
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
    background_tasks.add_task(ingest_file, content, file.filename, tenant_id, job_id)
    return {"job_id": job_id, "status": "queued"}


@router.get("/ingest/{job_id}")
async def ingest_status(job_id: str, request: Request):
    """Poll ingestion job status."""
    data = await keydb.hgetall(f"job:{job_id}")
    if not data:
        return {"job_id": job_id, "status": "not_found"}
    return {
        "job_id": job_id,
        "status": data.get(b"status", b"unknown").decode(),
        "chunk_count": int(data.get(b"chunk_count", 0)),
        "current_url": data.get(b"current_url", b"").decode(),
        "error": data.get(b"error", b"").decode() if b"error" in data else None,
    }
