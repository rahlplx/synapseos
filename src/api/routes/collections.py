"""Collection management, analytics, document deletion, dataset listing, and interaction logs."""
import logging
from fastapi import APIRouter, Request, HTTPException
from qdrant_client import models

from src.api.models import ErrorResponse
from src.core.clients import get_qdrant, get_minio
from src.core.config import COLLECTION_KNOWLEDGE, COLLECTION_MEMORY, MINIO_DATASET_BUCKET

router = APIRouter(tags=["collections"])
logger = logging.getLogger(__name__)


@router.get("/collections", summary="List collections", response_description="Tenant-scoped collection stats")
async def get_collections(request: Request):
    """List document collection stats for the tenant.

    Returns TENANT-SCOPED vector counts (not global counts) for both
    synapse_knowledge (RAG) and synapse_memory (mem0) collections.
    """
    tenant_id = request.state.tenant_id
    qdrant = get_qdrant()
    result = {"tenant_id": tenant_id, "collections": {}}

    for name in (COLLECTION_KNOWLEDGE, COLLECTION_MEMORY):
        try:
            info = await qdrant.get_collection(name)
            tenant_count = await qdrant.count(
                name,
                count_filter=models.Filter(
                    must=[models.FieldCondition(
                        key="tenant_id", match=models.MatchValue(value=tenant_id)
                    )]
                ),
                exact=False,
            )
            result["collections"][name] = {
                "vector_count": tenant_count.count if tenant_count else 0,
                "total_collection_size": info.points_count or 0,
                "status": info.status,
            }
        except Exception as e:
            logger.warning(f"[non-critical] get_collections failed for '{name}': {type(e).__name__}: {e}")
            result["collections"][name] = {"vector_count": 0, "status": "not_found"}

    return result


@router.get("/analytics", summary="Usage analytics", response_description="RAGAS scores and top queries")
async def get_analytics(request: Request):
    """RAGAS score trends + usage metrics for the last 7 days.

    Returns faithfulness, answer relevancy, and combined RAGAS scores,
    along with total query count and top-5 most frequent queries.
    """
    tenant_id = request.state.tenant_id
    from src.core.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COUNT(*) as queries_7d,
                AVG(ragas_faithfulness) as faithfulness,
                AVG(ragas_relevancy) as relevancy,
                AVG(ragas_combined) as combined
            FROM interaction_logs
            WHERE tenant_id = $1 AND created_at > now() - INTERVAL '7 days'
        """, tenant_id)

        top_queries = await conn.fetch("""
            SELECT query, COUNT(*) as cnt
            FROM interaction_logs
            WHERE tenant_id = $1 AND created_at > now() - INTERVAL '7 days'
            GROUP BY query ORDER BY cnt DESC LIMIT 5
        """, tenant_id)

    return {
        "ragas_7d": {
            "faithfulness": round(float(row["faithfulness"] or 0), 3),
            "answer_relevancy": round(float(row["relevancy"] or 0), 3),
            "combined": round(float(row["combined"] or 0), 3),
        },
        "queries_7d": int(row["queries_7d"] or 0),
        "top_queries": [r["query"] for r in top_queries],
    }


@router.delete(
    "/documents/{document_id}",
    summary="Delete document",
    responses={404: {"model": ErrorResponse}},
)
async def delete_document(document_id: str, request: Request):
    """Remove a document from PostgreSQL and all its vectors from Qdrant.

    Performs cascade delete: removes the document row from PostgreSQL,
    then deletes all associated vectors from Qdrant using source_url or
    source_filename filters. Both filters include tenant_id to prevent
    cross-tenant data deletion.
    """
    tenant_id = request.state.tenant_id
    qdrant = get_qdrant()
    from src.core.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        doc = await conn.fetchrow(
            "SELECT * FROM documents WHERE id=$1::uuid AND tenant_id=$2",
            document_id, tenant_id,
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        await conn.execute(
            "DELETE FROM documents WHERE id=$1::uuid AND tenant_id=$2",
            document_id, tenant_id,
        )

    # Delete vectors — MUST include tenant_id to prevent cross-tenant deletion
    source_url = doc["source_url"]
    if source_url:
        await qdrant.delete(
            collection_name=COLLECTION_KNOWLEDGE,
            points_selector=models.FilterSelector(
                filter=models.Filter(must=[
                    models.FieldCondition(key="source_url", match=models.MatchValue(value=source_url)),
                    models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id)),
                ])
            ),
        )

    source_filename = doc["source_filename"]
    if source_filename and not source_url:
        await qdrant.delete(
            collection_name=COLLECTION_KNOWLEDGE,
            points_selector=models.FilterSelector(
                filter=models.Filter(must=[
                    models.FieldCondition(key="source_filename", match=models.MatchValue(value=source_filename)),
                    models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id)),
                ])
            ),
        )

    return {"deleted": True, "document_id": document_id}


@router.get("/datasets", summary="List fine-tuning datasets", response_description="Exported datasets in MinIO")
async def list_datasets(request: Request):
    """List exported fine-tuning datasets in MinIO.

    Datasets are generated by the nightly optimizer (RAGAS scoring +
    SFT/DPO JSONL export). Each dataset version is stored under
    `datasets/{version}/` in the synapseos bucket.
    """
    minio = get_minio()
    datasets = []
    try:
        response = minio.list_objects_v2(Bucket=MINIO_DATASET_BUCKET, Prefix="datasets/")
        for obj in response.get("Contents", []):
            datasets.append({
                "key": obj["Key"],
                "size": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
            })
    except Exception as e:
        logger.warning(f"[non-critical] list_datasets failed: {type(e).__name__}: {e}")

    return {"datasets": datasets}


@router.get(
    "/interactions",
    summary="List interaction logs",
    response_description="Paginated interaction history",
)
async def list_interactions(
    request: Request,
    limit: int = 20,
    offset: int = 0,
):
    """List interaction logs for this tenant with pagination.

    Returns query, answer, RAGAS scores, and timestamps for each interaction.
    Use `limit` and `offset` for pagination. Maximum limit is 100.
    Results are ordered by most recent first.
    """
    tenant_id = request.state.tenant_id
    from src.core.db import get_pool

    limit = min(limit, 100)  # Cap at 100 to prevent memory issues
    offset = max(offset, 0)

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Get total count for pagination metadata
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM interaction_logs WHERE tenant_id = $1",
            tenant_id,
        )

        rows = await conn.fetch(
            """
            SELECT id, query, answer, contexts, created_at,
                   ragas_faithfulness, ragas_relevancy, ragas_combined
            FROM interaction_logs
            WHERE tenant_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            tenant_id, limit, offset,
        )

    interactions = [
        {
            "id": str(r["id"]),
            "query": r["query"],
            "answer": r["answer"][:500] if r["answer"] else None,  # Truncate long answers
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "ragas": {
                "faithfulness": round(float(r["ragas_faithfulness"]), 3) if r["ragas_faithfulness"] else None,
                "relevancy": round(float(r["ragas_relevancy"]), 3) if r["ragas_relevancy"] else None,
                "combined": round(float(r["ragas_combined"]), 3) if r["ragas_combined"] else None,
            },
        }
        for r in rows
    ]

    return {
        "interactions": interactions,
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        },
    }
