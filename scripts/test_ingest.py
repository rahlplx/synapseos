"""
SynapseOS — Ingestion Test Script
End-to-end test: scrape URL → chunk → dedup → embed → upsert to Qdrant.
Run: python3 scripts/test_ingest.py
Requires: Qdrant running, fastembed + crawl4ai installed
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("KEYDB_URL", "redis://localhost:6379")

import asyncio
import time

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from scripts.setup_collection import create_collection
from qdrant_client import AsyncQdrantClient, models


QDRANT_URL = os.environ["QDRANT_URL"]
COLLECTION = "synapse_knowledge"
TEST_URL = "https://qdrant.tech/documentation/concepts/"
TENANT_ID = "test"


async def main():
    print("=== SynapseOS — Ingestion Test ===\n")

    # Step 0: Ensure collections exist
    client = AsyncQdrantClient(url=QDRANT_URL)
    await create_collection(client, "synapse_knowledge", "RAG document vectors")
    await create_collection(client, "synapse_memory", "mem0 memory vectors")

    # Import ingestion pipeline
    from src.core.ingestion import (
        scrape_url, semantic_chunk, dedup_chunks,
        embed_and_upsert, keydb,
    )

    job_id = "test-ingest-manual"
    start = time.perf_counter()

    # Step 1: Scrape URL
    print("Scraping URL...")
    t1 = time.perf_counter()
    markdown = await scrape_url(TEST_URL)
    t_scrape = time.perf_counter() - t1
    print(f"  Scraped {len(markdown)} characters in {t_scrape:.1f}s")

    # Step 2: Chunk
    print("Chunking...")
    t2 = time.perf_counter()
    chunks = semantic_chunk(markdown)
    t_chunk = time.perf_counter() - t2
    print(f"  Created {len(chunks)} chunks in {t_chunk:.1f}s")

    # Step 3: Dedup
    print("Deduplicating...")
    t3 = time.perf_counter()
    unique = await dedup_chunks(chunks, TENANT_ID)
    t_dedup = time.perf_counter() - t3
    print(f"  {len(unique)} unique chunks ({len(chunks) - len(unique)} duplicates) in {t_dedup:.1f}s")

    # Step 4: Embed + Upsert
    print("Embedding + Storing in Qdrant...")
    t4 = time.perf_counter()
    await embed_and_upsert(unique, TENANT_ID, {"source_url": TEST_URL})
    t_embed = time.perf_counter() - t4
    print(f"  Embedded and stored in {t_embed:.1f}s")

    total_time = time.perf_counter() - start

    # Step 5: Verify in Qdrant
    info = await client.get_collection(COLLECTION)
    vector_count = info.vectors_count or 0

    # Count vectors for our specific tenant
    tenant_results = await client.query_points(
        collection_name=COLLECTION,
        query=[0.0] * 768,  # dummy vector
        using="dense",
        limit=1,
        with_payload=False,
        filter=models.Filter(
            must=[models.FieldCondition(
                key="tenant_id",
                match=models.MatchValue(value=TENANT_ID),
            )]
        ),
    )

    # Print results
    print(f"\n=== Results ===")
    print(f"  Chunks stored: {len(unique)}")
    print(f"  Total time: {total_time:.1f}s")
    if HAS_PSUTIL:
        mem = psutil.Process().memory_info().rss / (1024 * 1024)
        print(f"  Memory used: {mem:.0f}MB")
    print(f"  Vectors in Qdrant (total): {vector_count}")
    print(f"\n=== Timing Breakdown ===")
    print(f"  Scrape:   {t_scrape:.1f}s")
    print(f"  Chunk:    {t_chunk:.1f}s")
    print(f"  Dedup:    {t_dedup:.1f}s")
    print(f"  Embed:    {t_embed:.1f}s")

    # Verify in Qdrant dashboard
    print(f"\n=== Verification ===")
    print(f"  Qdrant Dashboard: http://localhost:6333/dashboard")
    print(f"  Look for '{COLLECTION}' with {vector_count} vectors")
    print(f"  Status: {'✅ PASS' if vector_count > 0 else '❌ FAIL — no vectors stored'}")

    await client.close()

    # Clean up dedup hashes from test (optional — comment out to keep for next run)
    # await keydb.delete(f"tenant:{TENANT_ID}:hashes")


if __name__ == "__main__":
    asyncio.run(main())
