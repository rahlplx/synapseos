"""POST /v1/ingest, POST /v1/ingest/file, POST /v1/ingest/batch, POST /v1/ingest/bulk-files, GET /v1/ingest/{job_id}"""
import time
from uuid import uuid4
from fastapi import APIRouter, Request, BackgroundTasks, UploadFile, File

from src.api.models import IngestRequest, BatchIngestRequest
from src.core.ingestion import ingest_urls, ingest_file
from src.core.clients import get_keydb

router = APIRouter(tags=["ingestion"])


@router.post("/ingest", summary="Ingest URLs", response_description="Job ID for tracking")
async def ingest_endpoint(body: IngestRequest, request: Request, background_tasks: BackgroundTasks):
    """Queue document ingestion from URLs.

    Returns a job ID immediately. Poll `GET /v1/ingest/{job_id}` for status.
    Maximum 50 URLs per request. Each URL is scraped, chunked, deduplicated,
    embedded (dense + sparse), and upserted to Qdrant.
    """
    tenant_id = request.state.tenant_id
    job_id = str(uuid4())
    keydb = get_keydb()
    await keydb.hset(f"job:{job_id}", mapping={
        "created_at": str(time.time()),
        "tenant_id": tenant_id,
    })
    background_tasks.add_task(ingest_urls, body.urls, tenant_id, job_id, body.metadata)
    return {"job_id": job_id, "status": "queued", "document_count": len(body.urls)}


@router.post("/ingest/batch", summary="Batch ingest URL groups", response_description="Job IDs for each group")
async def ingest_batch_endpoint(body: BatchIngestRequest, request: Request, background_tasks: BackgroundTasks):
    """Batch ingestion — submit multiple URL groups, each with its own metadata.

    Each group is processed as a separate job with independent tracking.
    Maximum 10 groups per request, 50 URLs per group.
    Returns one job ID per group for granular progress tracking.
    """
    tenant_id = request.state.tenant_id
    keydb = get_keydb()
    jobs = []

    for group in body.groups:
        urls = group.get("urls", [])
        metadata = group.get("metadata", {})

        if not urls or len(urls) > 50:
            continue  # Skip invalid groups silently

        job_id = str(uuid4())
        await keydb.hset(f"job:{job_id}", mapping={
            "created_at": str(time.time()),
            "tenant_id": tenant_id,
        })
        background_tasks.add_task(ingest_urls, urls, tenant_id, job_id, metadata)
        jobs.append({"job_id": job_id, "url_count": len(urls)})

    return {"status": "queued", "jobs": jobs, "total_groups": len(jobs)}


@router.post("/ingest/file", summary="Ingest uploaded file", response_description="Job ID for tracking")
async def ingest_file_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF, DOCX, TXT, or MD file"),
):
    """Upload a file (PDF, DOCX, TXT, MD) for ingestion.

    Returns a job ID immediately. Poll `GET /v1/ingest/{job_id}` for status.
    The file is parsed with Docling, chunked, deduplicated, embedded, and upserted.
    """
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


@router.post("/ingest/bulk-files", summary="Bulk file upload", response_description="Job IDs for each file")
async def ingest_bulk_files_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(..., description="Multiple PDF, DOCX, TXT, or MD files (max 20)"),
):
    """Upload multiple files for ingestion (max 20 files per request).

    Each file is processed as a separate job with independent tracking.
    Returns one job ID per file for granular progress tracking.
    Maximum 20 files per request to prevent memory exhaustion on ARM.
    """
    tenant_id = request.state.tenant_id
    keydb = get_keydb()

    if len(files) > 20:
        return {"status": "error", "message": "Maximum 20 files per bulk upload"}

    jobs = []
    for file in files:
        job_id = str(uuid4())
        content = await file.read()
        await keydb.hset(f"job:{job_id}", mapping={
            "created_at": str(time.time()),
            "tenant_id": tenant_id,
        })
        background_tasks.add_task(ingest_file, content, file.filename, tenant_id, job_id)
        jobs.append({"job_id": job_id, "filename": file.filename})

    return {"status": "queued", "jobs": jobs, "total_files": len(jobs)}


@router.get("/ingest/{job_id}", summary="Check ingestion status", response_description="Job status and progress")
async def ingest_status(job_id: str, request: Request):
    """Poll ingestion job status.

    Returns current status (queued/processing/done/failed), chunk count,
    and elapsed time. Verifies tenant ownership to prevent cross-tenant access.
    """
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
