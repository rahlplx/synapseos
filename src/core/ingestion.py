"""
L1 — Ingestion Engine
Crawl4AI → Docling → SemanticChunker → SHA-256 dedup → fastembed → Qdrant + MinIO + PG
ARM: Docling concurrency=1, batch_size=64 ingestion, OMP_NUM_THREADS=4
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")  # ARM CPU tuning — MUST be before fastembed

import hashlib
import tempfile
from uuid import uuid4
from typing import Optional

from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import AsyncQdrantClient, models
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter
import redis.asyncio as redis

# ─── Clients ──────────────────────────────────────────────────────────────────
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
KEYDB_URL = os.environ.get("KEYDB_URL", "redis://keydb:6379")
COLLECTION = "synapse_knowledge"

qdrant = AsyncQdrantClient(url=QDRANT_URL)
keydb = redis.from_url(KEYDB_URL)

# ─── Models (lazy_load=True — only allocate RAM on first embed call) ──────────
dense_model = TextEmbedding("BAAI/bge-base-en-v1.5", threads=4, lazy_load=True)
sparse_model = SparseTextEmbedding("Qdrant/bm25", threads=4)

# ─── ARM Constants ────────────────────────────────────────────────────────────
INGEST_BATCH_SIZE = 64   # batch_size=64 for ingestion (architecture doc)
SCROLL_DELAY = 1.5       # Crawl4AI scroll delay for full page render


async def scrape_url(url: str) -> str:
    """Scrape a URL using Crawl4AI with JS rendering and pruning content filter.
    ARM gotcha: Only 1 concurrent Chromium process on this budget.
    """
    md_gen = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.48)
    )
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        markdown_generator=md_gen,
        page_timeout=30000,       # 30s hard timeout — prevents DOM hang
        scan_full_page=True,
        scroll_delay=SCROLL_DELAY,
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=config)
        if not result.markdown or not result.markdown.fit_markdown:
            raise ValueError(f"Scraping returned empty content for {url}")
        return result.markdown.fit_markdown


def parse_document(file_bytes: bytes, filename: str) -> str:
    """Parse a PDF/DOCX file using Docling (layout-aware → markdown).
    ARM gotcha: Docling peaks at ~3.5GB RAM per 100-page PDF.
    Queue concurrency MUST be 1. Set DOCLING_CPU_ONLY=1.
    """
    from docling.document_converter import DocumentConverter

    suffix = os.path.splitext(filename)[1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(file_bytes)
        tmp_path = f.name
    try:
        converter = DocumentConverter()
        doc = converter.convert(source=f"file://{tmp_path}")
        markdown = doc.export_to_markdown()
        if not markdown or not markdown.strip():
            raise ValueError(f"Docling returned empty content for {filename}")
        return markdown
    finally:
        os.unlink(tmp_path)


def semantic_chunk(text: str, max_tokens: int = 512, overlap: int = 64) -> list[str]:
    """Split text into semantic chunks using the embedding tokenizer.
    chunk_size=512 tokens, overlap=64 tokens (architecture doc).
    """
    from semchunk import SemanticChunker
    chunker = SemanticChunker(
        tokenizer="BAAI/bge-base-en-v1.5",
        chunk_size=max_tokens,
        overlap=overlap,
    )
    chunks = chunker.chunk_text(text)
    if not chunks:
        raise ValueError("Semantic chunking produced zero chunks — input may be too short")
    return chunks


async def dedup_chunks(chunks: list[str], tenant_id: str) -> list[str]:
    """SHA-256 dedup — check KeyDB set per tenant.
    Prevents re-ingesting identical chunks on repeated scrapes.
    """
    unique = []
    for chunk in chunks:
        h = hashlib.sha256(chunk.encode()).hexdigest()
        added = await keydb.sadd(f"tenant:{tenant_id}:hashes", h)
        if added:
            unique.append(chunk)
    return unique


async def embed_and_upsert(chunks: list[str], tenant_id: str, metadata: dict):
    """Generate dual vectors (dense 768d + sparse BM25) and upsert to Qdrant.
    batch_size=64 for ingestion per ARM rules.
    """
    if not chunks:
        return

    dense_vecs = list(dense_model.embed(chunks, batch_size=INGEST_BATCH_SIZE))
    sparse_vecs = list(sparse_model.embed(chunks, batch_size=INGEST_BATCH_SIZE))

    points = [
        models.PointStruct(
            id=str(uuid4()),
            vector={
                "dense": dense_vecs[i].tolist(),
                "sparse": sparse_vecs[i].as_object(),
            },
            payload={"text": chunks[i], "tenant_id": tenant_id, **metadata},
        )
        for i in range(len(chunks))
    ]
    await qdrant.upsert(collection_name=COLLECTION, points=points)


async def ingest_urls(
    urls: list[str],
    tenant_id: str,
    job_id: str,
    metadata: Optional[dict] = None,
):
    """Ingest a list of URLs: scrape → chunk → dedup → embed → upsert.
    Updates job status in KeyDB for polling.
    """
    metadata = metadata or {}
    await keydb.hset(f"job:{job_id}", mapping={"status": "processing", "total": len(urls), "done": 0})

    for url in urls:
        try:
            # 1. Scrape
            await keydb.hset(f"job:{job_id}", "current_url", url)
            markdown = await scrape_url(url)

            # 2. Chunk
            chunks = semantic_chunk(markdown)

            # 3. Dedup
            unique = await dedup_chunks(chunks, tenant_id)

            # 4. Embed + Upsert
            await embed_and_upsert(unique, tenant_id, {**metadata, "source_url": url})

            # 5. Update progress
            done_count = int(await keydb.hget(f"job:{job_id}", "done") or 0)
            await keydb.hset(f"job:{job_id}", "done", done_count + 1)
        except Exception as e:
            await keydb.hset(f"job:{job_id}", f"error:{url}", str(e)[:500])

    await keydb.hset(f"job:{job_id}", "status", "done")
    # Set job TTL to 24 hours so it auto-cleans
    await keydb.expire(f"job:{job_id}", 86400)


async def ingest_file(
    file_bytes: bytes,
    filename: str,
    tenant_id: str,
    job_id: str,
):
    """Ingest an uploaded file: parse → chunk → dedup → embed → upsert.
    Docling concurrency=1 enforced at worker level.
    """
    await keydb.hset(f"job:{job_id}", "status", "processing")
    try:
        # 1. Parse document
        markdown = parse_document(file_bytes, filename)

        # 2. Chunk
        chunks = semantic_chunk(markdown)

        # 3. Dedup
        unique = await dedup_chunks(chunks, tenant_id)

        # 4. Embed + Upsert
        await embed_and_upsert(unique, tenant_id, {"source_filename": filename})

        # 5. Record chunk count
        await keydb.hset(f"job:{job_id}", mapping={"status": "done", "chunk_count": len(unique)})
    except Exception as e:
        await keydb.hset(f"job:{job_id}", mapping={"status": "failed", "error": str(e)[:500]})

    # Set job TTL to 24 hours
    await keydb.expire(f"job:{job_id}", 86400)
