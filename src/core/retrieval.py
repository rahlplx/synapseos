"""
L2 — Hybrid Retrieval Engine
Dense (BAAI/bge-base-en-v1.5) + BM25 sparse → RRF fusion → cross-encoder rerank
ARM tuned: OMP_NUM_THREADS=4, batch_size=16 query, cross-encoder cap=15 docs
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")  # ARM CPU tuning — MUST be before fastembed

from qdrant_client import AsyncQdrantClient, models
from fastembed import TextEmbedding, SparseTextEmbedding
from sentence_transformers import CrossEncoder

# ─── Clients ──────────────────────────────────────────────────────────────────
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION = "synapse_knowledge"

qdrant = AsyncQdrantClient(url=QDRANT_URL)

# ─── Models ───────────────────────────────────────────────────────────────────
dense_model = TextEmbedding("BAAI/bge-base-en-v1.5", threads=4, lazy_load=True)
sparse_model = SparseTextEmbedding("Qdrant/bm25", threads=4)
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)

# ─── ARM Constants ────────────────────────────────────────────────────────────
QUERY_BATCH_SIZE = 16       # batch_size=16 for real-time query (architecture doc)
PREFETCH_K = 30             # prefetch 30 via RRF per dense/sparse
RERANK_K = 15               # HARD LIMIT: feed top-15 to cross-encoder (ARM timeout prevention)
DEFAULT_FINAL_K = 5         # return top-5 after reranking


async def warm_models():
    """Warm ONNX models on startup to avoid cold-start latency on first query.
    Called by FastAPI lifespan handler.
    """
    _ = list(dense_model.embed(["warmup"], batch_size=QUERY_BATCH_SIZE))
    _ = list(sparse_model.embed(["warmup"]))
    _ = reranker.predict([["warmup", "warmup"]])  # warm cross-encoder


async def hybrid_query(
    query: str,
    tenant_id: str,
    prefetch_k: int = PREFETCH_K,
    rerank_k: int = RERANK_K,
    final_k: int = DEFAULT_FINAL_K,
    use_hyde: bool = False,
) -> list:
    """Hybrid retrieval: dense + BM25 sparse → RRF fusion → cross-encoder rerank.

    ARM safety:
    - rerank_k capped at 15 (cross-encoder at 30 docs = ~400ms, at 100 = ~2500ms)
    - batch_size=16 for query-time embedding
    - tenant_id filter applied in BOTH prefetch queries (never cross-tenant)
    """
    search_query = query
    if use_hyde:
        from src.core.generation import generate_hyde
        search_query = await generate_hyde(query)

    # Phase A: Generate dense + sparse embeddings for query
    dense_vec = next(dense_model.embed([search_query], batch_size=QUERY_BATCH_SIZE))
    sparse_vec = next(sparse_model.embed([search_query]))

    # Tenant isolation filter — applied to ALL queries, never cross-tenant
    tenant_filter = models.Filter(
        must=[models.FieldCondition(
            key="tenant_id", match=models.MatchValue(value=tenant_id)
        )]
    )

    # Phase B: Qdrant prefetch + RRF fusion
    hits = (await qdrant.query_points(
        collection_name=COLLECTION,
        prefetch=[
            models.Prefetch(
                query=dense_vec.tolist(),
                using="dense",
                limit=prefetch_k,
                filter=tenant_filter,   # tenant filter on DENSE prefetch
            ),
            models.Prefetch(
                query=sparse_vec.as_object(),
                using="sparse",
                limit=prefetch_k,
                filter=tenant_filter,   # tenant filter on SPARSE prefetch
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        with_payload=True,
        limit=rerank_k,  # HARD CAP: max 15 docs to cross-encoder
    )).points

    if not hits:
        return []

    # Phase C: Cross-encoder reranking
    pairs = [[query, h.payload.get("text", "")] for h in hits]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(hits, scores), key=lambda x: x[1], reverse=True)

    # Filter out low-quality results (score < 0.1 means cross-encoder rejects)
    return [h for h, s in ranked[:final_k] if s > 0.1]


async def ensure_collection():
    """Create Qdrant collection with ARM-optimized settings if it doesn't exist.
    Called on startup by FastAPI lifespan handler.
    """
    if not await qdrant.collection_exists(COLLECTION):
        await qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config={
                "dense": models.VectorParams(
                    size=768,
                    distance=models.Distance.COSINE,
                    on_disk=True,  # ARM mmap — critical
                )
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(
                    modifier=models.Modifier.IDF
                )
            },
            shard_number=1,
            optimizers_config=models.OptimizersConfigDiff(
                memmap_threshold_kb=50_000,
                indexing_threshold_kb=100_000,
                max_segment_size_kb=65_536,
            ),
        )
        await qdrant.create_payload_index(
            COLLECTION, "tenant_id", models.PayloadSchemaType.KEYWORD
        )
