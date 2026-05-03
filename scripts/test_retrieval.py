"""
SynapseOS — Retrieval Test Script
Tests hybrid_query with latency benchmarking per phase.
Run: python3 scripts/test_retrieval.py
Requires: Qdrant running with vectors from test_ingest.py
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")

import asyncio
import time

from qdrant_client import AsyncQdrantClient, models
from fastembed import TextEmbedding, SparseTextEmbedding
from sentence_transformers import CrossEncoder


QDRANT_URL = os.environ["QDRANT_URL"]
COLLECTION = "synapse_knowledge"

qdrant = AsyncQdrantClient(url=QDRANT_URL)
dense_model = TextEmbedding("BAAI/bge-base-en-v1.5", threads=4, lazy_load=True)
sparse_model = SparseTextEmbedding("Qdrant/bm25", threads=4)
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)

# Warm models
print("Warming models...")
_ = list(dense_model.embed(["warmup"], batch_size=16))
_ = list(sparse_model.embed(["warmup"]))


async def test_hybrid():
    question = "how does HNSW graph indexing work?"
    tenant_id = "test"

    tenant_filter = models.Filter(
        must=[models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id))]
    )

    # Phase A: Generate embeddings
    t0 = time.perf_counter()
    dense_vec = next(dense_model.embed([question], batch_size=16))
    sparse_vec = next(sparse_model.embed([question]))
    t_a = (time.perf_counter() - t0) * 1000

    # Phase B: Qdrant search
    t1 = time.perf_counter()
    hits = (await qdrant.query_points(
        collection_name=COLLECTION,
        prefetch=[
            models.Prefetch(query=dense_vec.tolist(), using="dense", limit=30, filter=tenant_filter),
            models.Prefetch(query=sparse_vec.as_object(), using="sparse", limit=30, filter=tenant_filter),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        with_payload=True,
        limit=15,
    )).points
    t_b = (time.perf_counter() - t1) * 1000

    if not hits:
        print("❌ No results found. Run test_ingest.py first to populate Qdrant.")
        return

    # Phase C: Cross-encoder reranking
    t2 = time.perf_counter()
    pairs = [[question, h.payload.get("text", "")] for h in hits]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(hits, scores), key=lambda x: x[1], reverse=True)
    top5 = [(h, s) for h, s in ranked[:5] if s > 0.1]
    t_c = (time.perf_counter() - t2) * 1000

    total = t_a + t_b + t_c

    # Print results
    print(f"\n=== Hybrid Query Results ===")
    print(f"Question: {question}\n")
    for i, (h, s) in enumerate(top5, 1):
        text = h.payload.get("text", "")[:120].replace("\n", " ")
        print(f"  [{i}] Score: {s:.3f} | \"{text}...\"")

    print(f"\n=== Latency ===")
    print(f"  Phase A (embed):     {t_a:.0f}ms")
    print(f"  Phase B (Qdrant):    {t_b:.0f}ms")
    print(f"  Phase C (rerank):    {t_c:.0f}ms")
    print(f"  Total:               {total:.0f}ms")
    print(f"  Status: {'✅ PASS (<400ms)' if total < 400 else '⚠️ SLOW (>400ms)'}")

    # Dense-only comparison
    print(f"\n=== Dense-Only Comparison ===")
    dense_hits = (await qdrant.query_points(
        collection_name=COLLECTION,
        query=dense_vec.tolist(),
        using="dense",
        limit=5,
        with_payload=True,
        filter=tenant_filter,
    )).points

    for i, h in enumerate(dense_hits[:3], 1):
        text = h.payload.get("text", "")[:100].replace("\n", " ")
        print(f"  [{i}] \"{text}...\"")

    # Check if hybrid found different chunks
    hybrid_ids = {h.id for h, s in top5}
    dense_ids = {h.id for h in dense_hits[:5]}
    diff = len(hybrid_ids.symmetric_difference(dense_ids))
    print(f"\n  Hybrid found {diff} different chunks than dense-only")


async def main():
    # Verify collection exists and has data
    exists = await qdrant.collection_exists(COLLECTION)
    if not exists:
        print("❌ Collection 'synapse_knowledge' does not exist. Run setup_collection.py first.")
        return

    info = await qdrant.get_collection(COLLECTION)
    print(f"Collection has {info.vectors_count} vectors")

    if info.vectors_count == 0:
        print("❌ No vectors found. Run test_ingest.py first.")
        return

    await test_hybrid()
    await qdrant.close()


if __name__ == "__main__":
    asyncio.run(main())
