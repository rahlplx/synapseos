"""POST /v1/ingest — Queue document ingestion"""
from uuid import uuid4
from fastapi import APIRouter, Request, BackgroundTasks, UploadFile, File
from pydantic import BaseModel
from src.core.ingestion import ingest_urls, ingest_file

router = APIRouter()


class IngestRequest(BaseModel):
    urls: list[str]
    metadata: dict = {}


@router.post("/ingest")
async def ingest_endpoint(body: IngestRequest, request: Request, background_tasks: BackgroundTasks):
    tenant_id = request.state.tenant_id
    job_id = str(uuid4())
    background_tasks.add_task(ingest_urls, body.urls, tenant_id, job_id, body.metadata)
    return {"job_id": job_id, "status": "queued", "document_count": len(body.urls)}


@router.post("/ingest/file")
async def ingest_file_endpoint(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    tenant_id = request.state.tenant_id
    job_id = str(uuid4())
    content = await file.read()
    background_tasks.add_task(ingest_file, content, file.filename, tenant_id, job_id)
    return {"job_id": job_id, "status": "queued"}
