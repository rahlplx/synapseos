"""
L2 — Hybrid Retrieval Engine
Dense (BAAI/bge-base-en-v1.5) + BM25 sparse → RRF fusion → cross-encoder rerank
ARM tuned: OMP_NUM_THREADS=4, batch_size=16 query, cross-encoder cap=15 docs
CRAG: Returns confidence signal — "low" if top score below threshold.
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")  # ARM CPU tuning — MUST be before fastembed

import logging
from qdrant_client import AsyncQdrantClient, models
from fastembed import TextEmbedding, SparseTextEmbedding
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

# ─── Clients ──────────────────────────────────────────────────────────────────
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION_KNOWLEDGE = "synapse_knowledge"
COLLECTION_MEMORY = "synapse_memory"

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
CONFIDENCE_THRESHOLD = 0.35 # CRAG: if top reranked score < this, signal "low" confidence
RELEVANCE_GATE = 0.20       # Self-RAG: minimum cross-encoder score for a document to be included in context


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
    # Sparse vector uses models.SparseVector(indices=..., values=...) for
    # compatibility with newer qdrant-client API versions (not raw dict).
    hits = (await qdrant.query_points(
        collection_name=COLLECTION_KNOWLEDGE,
        prefetch=[
            models.Prefetch(
                query=dense_vec.tolist(),
                using="dense",
                limit=prefetch_k,
                filter=tenant_filter,   # tenant filter on DENSE prefetch
            ),
            models.Prefetch(
                query=models.SparseVector(
                    indices=sparse_vec.indices.tolist(),
                    values=sparse_vec.values.tolist(),
                ),
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

    # Filter out low-quality results using Self-RAG relevance gate.
    # Documents below the relevance gate threshold are excluded from LLM context
    # to prevent hallucination from irrelevant retrieved documents (Self-RAG pattern).
    # Attach cross-encoder scores to hits for downstream CRAG confidence gating.
    scored_hits = []
    for h, s in ranked[:final_k]:
        if s >= RELEVANCE_GATE:
            # Store cross-encoder score in payload for confidence gate access
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
    "low" means the top reranked result scored below the threshold —
    the caller should consider web search fallback or early return
    instead of burning LLM tokens on weak context.

    CRAG (Corrective RAG) prevents the #1 production failure:
    confident wrong answers generated from irrelevant context.
    """
    results = await hybrid_query(
        query, tenant_id, prefetch_k, rerank_k, final_k, use_hyde
    )

    if not results:
        logger.info(f"[CRAG] Zero results for query: {query[:80]}")
        return [], "low"

    # Use cross-encoder rerank score for confidence — NOT Qdrant RRF score.
    # The cross-encoder score is a much more reliable signal of relevance
    # because it directly measures query-document similarity, whereas RRF
    # is a rank-based fusion heuristic.
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

    If the initial retrieval returns low confidence, the query is rewritten
    using the fast Groq 8b model to be more specific/search-friendly, and
    retrieval is retried once. This implements the CRAG query-rewrite pattern.

    Falls back to the original results if rewrite doesn't improve confidence.

    Returns (hits, confidence) where confidence is "high" or "low".
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

    # Return original results if rewrite didn't help
    return results, "low"


async def _create_collection_if_missing(name: str):
    """Create a Qdrant collection with ARM-optimized settings if it doesn't exist.
    Shared logic for both synapse_knowledge and synapse_memory collections.
    """
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
    Called on startup by FastAPI lifespan handler.
    """
    # synapse_knowledge — primary RAG knowledge base
    await _create_collection_if_missing(COLLECTION_KNOWLEDGE)

    # synapse_memory — mem0 long-term memory (same vector schema for consistency)
    await _create_collection_if_missing(COLLECTION_MEMORY)
