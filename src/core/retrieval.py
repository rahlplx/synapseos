"""
L2 — Hybrid Retrieval Engine
Dense (BAAI/bge-base-en-v1.5) + BM25 sparse → RRF fusion → cross-encoder rerank
ARM tuned: OMP_NUM_THREADS=4, batch_size=16 query / 64 ingest
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")

from qdrant_client import AsyncQdrantClient, models
from fastembed import TextEmbedding, SparseTextEmbedding
from sentence_transformers import CrossEncoder

QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION = "synapse_knowledge"

qdrant = AsyncQdrantClient(url=QDRANT_URL)
dense_model = TextEmbedding("BAAI/bge-base-en-v1.5", threads=4, lazy_load=True)
sparse_model = SparseTextEmbedding("Qdrant/bm25", threads=4)
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)


async def warm_models():
    """Warm ONNX models on startup to avoid cold-start latency on first query."""
    _ = list(dense_model.embed(["warmup"]))
    _ = list(sparse_model.embed(["warmup"]))


async def hybrid_query(
    query: str,
    tenant_id: str,
    prefetch_k: int = 30,
    rerank_k: int = 15,
    final_k: int = 5,
    use_hyde: bool = False,
) -> list:
    search_query = query
    if use_hyde:
        from src.core.generation import generate_hyde
        search_query = await generate_hyde(query)

    dense_vec = next(dense_model.embed([search_query]))
    sparse_vec = next(sparse_model.embed([search_query]))

    tenant_filter = models.Filter(
        must=[models.FieldCondition(
            key="tenant_id", match=models.MatchValue(value=tenant_id)
        )]
    )

    hits = (await qdrant.query_points(
        collection_name=COLLECTION,
        prefetch=[
            models.Prefetch(query=dense_vec.tolist(), using="dense", limit=prefetch_k, filter=tenant_filter),
            models.Prefetch(query=sparse_vec.as_object(), using="sparse", limit=prefetch_k, filter=tenant_filter),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        with_payload=True,
        limit=rerank_k,
    )).points

    if not hits:
        return []

    pairs = [[query, h.payload.get("text", "")] for h in hits]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(hits, scores), key=lambda x: x[1], reverse=True)
    return [h for h, s in ranked[:final_k] if s > 0.1]


async def ensure_collection():
    """Create Qdrant collection if it doesn't exist."""
    if not await qdrant.collection_exists(COLLECTION):
        await qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config={"dense": models.VectorParams(size=768, distance=models.Distance.COSINE, on_disk=True)},
            sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)},
            optimizers_config=models.OptimizersConfigDiff(memmap_threshold_kb=50_000, indexing_threshold_kb=100_000),
        )
        await qdrant.create_payload_index(COLLECTION, "tenant_id", models.PayloadSchemaType.KEYWORD)
