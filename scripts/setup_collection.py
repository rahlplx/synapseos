"""
SynapseOS — Qdrant Collection Setup
Creates synapse_knowledge and synapse_memory collections with ARM-optimized settings.
Run: python3 scripts/setup_collection.py
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")

import asyncio
from qdrant_client import AsyncQdrantClient, models


QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTIONS = {
    "synapse_knowledge": "RAG document vectors (768d dense + BM25 sparse)",
    "synapse_memory": "mem0 user memory vectors (768d dense)",
}


async def create_collection(client: AsyncQdrantClient, name: str, description: str):
    """Create a Qdrant collection with ARM-optimized settings if it doesn't exist."""
    exists = await client.collection_exists(name)
    if exists:
        info = await client.get_collection(name)
        print(f"✅ Collection '{name}' already exists — {info.vectors_count} vectors")
        return

    await client.create_collection(
        collection_name=name,
        vectors_config={
            "dense": models.VectorParams(
                size=768,
                distance=models.Distance.COSINE,
                on_disk=True,  # ARM mmap — critical for 24GB RAM budget
            )
        },
        sparse_vectors_config={
            "sparse": models.SparseVectorParams(
                modifier=models.Modifier.IDF  # BM25 IDF at index time
            )
        },
        shard_number=1,
        optimizers_config=models.OptimizersConfigDiff(
            memmap_threshold_kb=50_000,   # ARM mmap threshold
            indexing_threshold_kb=100_000,
            max_segment_size_kb=65_536,
        ),
    )

    # Create payload index for tenant isolation — O(log n) filter performance
    await client.create_payload_index(
        collection_name=name,
        field_name="tenant_id",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )

    print(f"✅ Collection '{name}' created — {description}")


async def main():
    print("=== SynapseOS — Qdrant Collection Setup ===\n")
    client = AsyncQdrantClient(url=QDRANT_URL)

    for name, description in COLLECTIONS.items():
        await create_collection(client, name, description)

    # Print summary
    print("\n--- Summary ---")
    for name in COLLECTIONS:
        info = await client.get_collection(name)
        print(f"  {name}: {info.vectors_count} vectors | status: {info.status}")

    await client.close()
    print("\n✅ All collections ready.")


if __name__ == "__main__":
    asyncio.run(main())
