"""GET /v1/collections, DELETE /v1/documents/{id}"""
from fastapi import APIRouter, Request
from qdrant_client import AsyncQdrantClient
import os

router = APIRouter()
qdrant = AsyncQdrantClient(url=os.environ.get("QDRANT_URL", "http://qdrant:6333"))


@router.get("/collections")
async def get_collections(request: Request):
    tenant_id = request.state.tenant_id
    info = await qdrant.get_collection("synapse_knowledge")
    return {
        "tenant_id": tenant_id,
        "vector_count": info.vectors_count,
        "status": info.status,
    }
