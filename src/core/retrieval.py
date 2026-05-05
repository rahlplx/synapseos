"""
L2 — Hybrid Retrieval Engine
Dense (BAAI/bge-base-en-v1.5) + BM25 sparse → RRF fusion → cross-encoder rerank
ARM tuned: OMP_NUM_THREADS=4, batch_size=16 query, cross-encoder cap=15 docs
CRAG: Returns confidence signal — "low" if top score below threshold.
"""
import asyncio
import logging
from qdrant_client import models
from fastembed import TextEmbedding, SparseTextEmbedding
from sentence_transformers import CrossEncoder

from src.core.config import (
    QUERY_BATCH_SIZE, PREFETCH_K, RERANK_K, DEFAULT_FINAL_K,
    CONFIDENCE_THRESHOLD, RELEVANCE_GATE,
    COLLECTION_KNOWLEDGE, COLLECTION_MEMORY,
)
from src.core.clients import get_qdrant

logger = logging.getLogger(__name__)

# ─── Models (lazy_load=True — only allocate RAM on first embed call) ──────────
dense_model = TextEmbedding("BAAI/bge-base-en-v1.5", threads=4, lazy_load=True)
sparse_model = SparseTextEmbedding("Qdrant/bm25", threads=4)
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)


async def warm_models():
    """Warm ONNX models on startup to avoid cold-start latency on first query."""
    _ = list(dense_model.embed(["warmup"], batch_size=QUERY_BATCH_SIZE))
    _ = list(sparse_model.embed(["warmup"]))
    _ = reranker.predict([["warmup", "warmup"]])


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
    qdrant = get_qdrant()
    search_query = query
    if use_hyde:
        from src.core.generation import generate_hyde
        search_query = await generate_hyde(query)

    # Phase A: Generate dense + sparse embeddings for query
    dense_vec = next(dense_model.embed([search_query], batch_size=QUERY_BATCH_SIZE))
    sparse_vec = next(sparse_model.embed([search_query]))

    # Tenant isolation filter — applied to ALL queries
    tenant_filter = models.Filter(
        must=[models.FieldCondition(
            key="tenant_id", match=models.MatchValue(value=tenant_id)
        )]
    )

    # Phase B: Qdrant prefetch + RRF fusion
    hits = (await qdrant.query_points(
        collection_name=COLLECTION_KNOWLEDGE,
        prefetch=[
            models.Prefetch(
                query=dense_vec.tolist(),
                using="dense",
                limit=prefetch_k,
                filter=tenant_filter,
            ),
            models.Prefetch(
                query=models.SparseVector(
                    indices=sparse_vec.indices.tolist(),
                    values=sparse_vec.values.tolist(),
                ),
                using="sparse",
                limit=prefetch_k,
                filter=tenant_filter,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        with_payload=True,
        limit=rerank_k,
    )).points

    if not hits:
        return []

    # Phase C: Cross-encoder reranking (CPU-bound → thread pool)
    pairs = [[query, h.payload.get("text", "")] for h in hits]
    scores = await asyncio.to_thread(reranker.predict, pairs)
    ranked = sorted(zip(hits, scores), key=lambda x: x[1], reverse=True)

    # Self-RAG relevance gate — filter out low-quality results
    scored_hits = []
    for h, s in ranked[:final_k]:
        if s >= RELEVANCE_GATE:
            h.payload["_rerank_score"] = float(s)
            scored_hits.append(h)
        else:
            logger.debug(f"[Self-RAG] Document filtered by relevance gate (score={s:.4f} < {RELEVANCE_GATE})")
    return scored_hits


async def hybrid_query_with_confidence(
    query: str,
    tenant_id: str,
    prefetch_k: int = PREFETCH_K,
    rerank_k: int = RERANK_K,
    final_k: int = DEFAULT_FINAL_K,
    use_hyde: bool = False,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> tuple[list, str]:
    """Hybrid retrieval with CRAG confidence signal.

    Returns (hits, confidence) where confidence is "high" or "low".
    "low" means the top reranked result scored below the threshold.
    """
    results = await hybrid_query(
        query, tenant_id, prefetch_k, rerank_k, final_k, use_hyde
    )

    if not results:
        logger.info(f"[CRAG] Zero results for query: {query[:80]}")
        return [], "low"

    top_rerank_score = results[0].payload.get("_rerank_score", 0.0)

    if top_rerank_score < confidence_threshold:
        logger.info(
            f"[CRAG] Low confidence (rerank_score={top_rerank_score:.4f} < {confidence_threshold}) "
            f"for query: {query[:80]}"
        )
        return results, "low"

    return results, "high"


async def hybrid_query_with_retry(
    query: str,
    tenant_id: str,
    prefetch_k: int = PREFETCH_K,
    rerank_k: int = RERANK_K,
    final_k: int = DEFAULT_FINAL_K,
    use_hyde: bool = False,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> tuple[list, str]:
    """CRAG: Hybrid retrieval with query rewrite on low confidence.

    If initial retrieval returns low confidence, rewrites the query
    using fast Groq 8b and retries once. Falls back to original if no improvement.
    """
    results, confidence = await hybrid_query_with_confidence(
        query, tenant_id, prefetch_k, rerank_k, final_k, use_hyde, confidence_threshold
    )

    if confidence == "high":
        return results, "high"

    # Low confidence — try query rewrite
    try:
        from src.core.generation import fast_complete
        rewritten = await fast_complete(
            f"Rewrite this question to be more specific and search-friendly. "
            f"Keep it concise. Original: {query}\nRewritten:",
            max_tokens=100,
        )
        rewritten = rewritten.strip()
        if rewritten and rewritten.lower() != query.lower():
            logger.info(f"[CRAG] Retrying with rewritten query: {rewritten[:80]}")
            retry_results, retry_conf = await hybrid_query_with_confidence(
                rewritten, tenant_id, prefetch_k, rerank_k, final_k, use_hyde, confidence_threshold
            )
            if retry_conf == "high" or (retry_results and len(retry_results) > len(results)):
                logger.info("[CRAG] Query rewrite improved retrieval")
                return retry_results, retry_conf
    except Exception as e:
        logger.warning(f"[CRAG] Query rewrite failed: {type(e).__name__}: {e}")

    return results, "low"


async def _create_collection_if_missing(name: str):
    """Create a Qdrant collection with ARM-optimized settings if it doesn't exist."""
    qdrant = get_qdrant()
    if await qdrant.collection_exists(name):
        return

    await qdrant.create_collection(
        collection_name=name,
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
        name, "tenant_id", models.PayloadSchemaType.KEYWORD
    )


async def ensure_collection():
    """Create Qdrant collections with ARM-optimized settings if they don't exist.
    Creates BOTH synapse_knowledge (RAG) and synapse_memory (mem0) collections.
    """
    await _create_collection_if_missing(COLLECTION_KNOWLEDGE)
    await _create_collection_if_missing(COLLECTION_MEMORY)
